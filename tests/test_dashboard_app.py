"""hub/dashboard/app.py のHTTPレイヤー結合テスト。

TestClientでlifespan込みの挙動(バックグラウンドタスクが起動・継続すること)を検証する:
registry.yamlのホットリロード(自動監視 + 手動トリガ)、ダッシュボードの自動更新、
アラート永続化、heartbeat/ci-success受信エンドポイント。
"""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

import hub.dashboard.app as app_module
from hub.alert_aggregator import normalize_from_health_check
from hub.alert_store import SqliteAlertStore
from hub.health.base import HealthResult
from hub.repo_sync import RepoRegistry


@pytest.fixture(autouse=True)
def _no_real_repo_sync(monkeypatch):
    """このファイルのテストはデフォルトでrepo_sync機能(13リポジトリのgit fetch)を
    実行させない。

    create_app()はlifespan起動時に_repo_check_loop経由でRepoSyncManager.check_all()を
    即座に1回実行するため、何もしないと実際のGitHub上の13リポジトリへ本物のgit fetchが
    走ってしまう(テストが遅くなる・ネットワークに依存する・実マシンのフォルダ構成に
    依存するため不適切)。repos_pathを明示的に渡したテスト(独自の小さなrepos.yamlで
    HTTP層の配線だけを検証したいテスト)は従来通りRepoRegistry.load()の実装で読み込み、
    repos_path省略時のみ空レジストリにフォールバックする。
    """
    original_load = RepoRegistry.load.__func__

    def _load(cls, path=None):
        if path is not None:
            return original_load(cls, path)
        return cls([])

    monkeypatch.setattr(RepoRegistry, "load", classmethod(_load))

_REGISTRY_V1 = """
tools:
  - tool_id: tool_a
    display_name: "A"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
"""

_REGISTRY_V2 = """
tools:
  - tool_id: tool_a
    display_name: "A"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
  - tool_id: tool_b
    display_name: "B"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
"""


def test_manual_reload_endpoint_reflects_file_changes(tmp_path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3")
    )
    with TestClient(app) as client:
        assert len(client.get("/api/registry").json()) == 1

        registry_path.write_text(_REGISTRY_V2, encoding="utf-8")

        res = client.post("/api/registry/reload")
        assert res.status_code == 200
        body = res.json()
        assert body["reloaded"] is True
        assert body["tool_count"] == 2

        assert len(client.get("/api/registry").json()) == 2


def test_manual_reload_endpoint_rejects_invalid_yaml_and_keeps_previous_registry(tmp_path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3")
    )
    with TestClient(app) as client:
        assert len(client.get("/api/registry").json()) == 1

        registry_path.write_text("not: [valid, tools, schema", encoding="utf-8")

        res = client.post("/api/registry/reload")
        assert res.status_code == 400

        # 不正な内容には差し替わらず、直前の有効なRegistryのまま
        assert len(client.get("/api/registry").json()) == 1


def test_registry_watch_loop_auto_reloads_on_change(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "REGISTRY_WATCH_INTERVAL_S", 0.05)

    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3")
    )
    with TestClient(app) as client:
        assert len(client.get("/api/registry").json()) == 1

        time.sleep(0.1)  # ファイルシステムのmtime解像度に対する安全マージン
        registry_path.write_text(_REGISTRY_V2, encoding="utf-8")

        for _ in range(40):
            if len(client.get("/api/registry").json()) == 2:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("registry_watch_loopが自動リロードを検知しなかった")


def test_dashboard_auto_refreshes_by_default(tmp_path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3")
    )
    with TestClient(app) as client:
        res = client.get("/")
        assert 'http-equiv="refresh" content="20"' in res.text

        res = client.get("/?refresh=0")
        assert "http-equiv=\"refresh\"" not in res.text
        assert "自動更新は停止中です" in res.text


def test_alerts_persist_across_app_restarts(tmp_path):
    """Hubプロセス再起動を模して、同じdb_pathで作り直したアプリが
    以前のアラート履歴を/api/alertsに反映することを確認する。
    """
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")
    db_path = tmp_path / "hub_state.sqlite3"

    # 事前にアラートを1件永続化しておく(実際にはpoll_loop経由でingestされる想定)
    seed_store = SqliteAlertStore(db_path)
    seed_store.save(normalize_from_health_check("tool_a", HealthResult(is_up=False)))
    seed_store.close()

    app = app_module.create_app(registry_path=str(registry_path), db_path=str(db_path))
    with TestClient(app) as client:
        rows = client.get("/api/alerts").json()
        assert len(rows) == 1
        assert rows[0]["source_tool_id"] == "tool_a"
        assert rows[0]["status"] == "open"


def test_artifact_panel_renders_non_ascii_content_without_unicode_escapes(tmp_path):
    """Jinja2の`tojson`は既定でensure_ascii=True相当のため、日本語等の非ASCII文字を
    含むアーティファクトが\\uXXXXエスケープのまま表示されてしまう回帰を防ぐ
    (ProfilingTool実装時に発見した問題と同根)。
    """
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        '{"entries": [{"asset_id": "x", "message": "ポリゴン数が予算を超過しています"}]}',
        encoding="utf-8",
    )
    (tmp_path / "registry_with_manifest.yaml").write_text(
        _REGISTRY_V1.rstrip()
        + f"""
  - tool_id: asset_data_insight_suite
    display_name: "AssetDataInsightSuite"
    transport: cli_batch
    endpoint: null
    health_check: ci_pipeline_check
    category: monitored
    poll_interval_s: 86400
    check_params:
      report_manifest_path: "{manifest_path.as_posix()}"
""",
        encoding="utf-8",
    )

    app = app_module.create_app(
        registry_path=str(tmp_path / "registry_with_manifest.yaml"),
        db_path=str(tmp_path / "hub_state.sqlite3"),
    )
    with TestClient(app) as client:
        res = client.get("/")
        assert "ポリゴン数が予算を超過しています" in res.text
        assert "\\u30dd" not in res.text  # 「ポ」のunicodeエスケープが残っていないこと


_REGISTRY_WITH_RPC_AND_CI = """
tools:
  - tool_id: sound_middleware
    display_name: "SoundMiddleware"
    transport: rpc
    endpoint: null
    health_check: rpc_check
    category: observed_only
    check_params:
      heartbeat_interval_s: 10
  - tool_id: research_collector
    display_name: "Research-Collector"
    transport: cli_batch
    endpoint: null
    health_check: ci_pipeline_check
    category: monitored
    poll_interval_s: 21600
    check_params:
      expected_interval_s: 21600
      grace_multiplier: 1.5
  - tool_id: color_encyclopedia
    display_name: "ColorEncyclopedia"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
"""


def _app_with_rpc_and_ci(tmp_path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_WITH_RPC_AND_CI, encoding="utf-8")
    return app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3")
    )


def test_heartbeat_endpoint_records_signal_that_liveness_check_picks_up(tmp_path):
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        # 受信前はまだシグナルが無いのでunknownのまま
        rows = client.get("/api/registry").json()
        row = next(r for r in rows if r["tool_id"] == "sound_middleware")
        assert row["is_up"] is None

        res = client.post("/api/heartbeat/sound_middleware")
        assert res.status_code == 200
        assert res.json() == {"tool_id": "sound_middleware", "recorded": True}

        # 受信したハートビートはLivenessMonitorに直接反映されている
        # (poll_loopの巡回を待たずにcheck_onceで確認する)
        entry = app.state.registry.get("sound_middleware")
        result = asyncio.run(app.state.monitor.check_once(entry))
        assert result is not None
        assert result.is_up is True


def test_heartbeat_endpoint_rejects_unknown_tool(tmp_path):
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        res = client.post("/api/heartbeat/does_not_exist")
        assert res.status_code == 404


def test_heartbeat_endpoint_rejects_tool_with_different_health_check(tmp_path):
    """research_collectorはci_pipeline_check対象であり、heartbeat受信口の対象ではない。"""
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        res = client.post("/api/heartbeat/research_collector")
        assert res.status_code == 400


def test_ci_success_endpoint_records_signal_that_liveness_check_picks_up(tmp_path):
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        res = client.post("/api/ci-success/research_collector")
        assert res.status_code == 200
        assert res.json() == {"tool_id": "research_collector", "recorded": True}

        # research_collectorはmonitored/poll_interval_s=21600(6時間)のため、
        # 背後のpoll_loopが直前に1回チェック済みだとレート制限に引っかかる。
        # ここではpoll_interval_sを超えた未来時刻を指定して強制的に再チェックさせる。
        entry = app.state.registry.get("research_collector")
        future = time.monotonic() + entry.poll_interval_s + 1
        result = asyncio.run(app.state.monitor.check_once(entry, now=future))
        assert result is not None
        assert result.is_up is True


def test_ci_success_endpoint_rejects_excluded_tool(tmp_path):
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        res = client.post("/api/ci-success/color_encyclopedia")
        assert res.status_code == 400


def test_profiling_tool_alert_endpoint_ingests_then_resolves(tmp_path):
    """DESIGN.md Phase3の4ソースのうち、Profiling Tool(主経路)からの生アラートが
    実際にAlertAggregatorへ届き、dedup/resolveライフサイクルに乗ることを確認する。
    """
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        res = client.post(
            "/api/alerts/profiling-tool",
            json={"signature": "gpu_frame_budget_exceeded", "severity": "critical", "message": "frame budget exceeded"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["action"] == "ingested"
        alert_id = body["alert_id"]

        alerts = client.get("/api/alerts").json()
        assert any(a["alert_id"] == alert_id and a["status"] == "open" for a in alerts)

        # 同一シグネチャをseverity="info"で送ると解消シグナルとして扱われる
        res = client.post(
            "/api/alerts/profiling-tool",
            json={"signature": "gpu_frame_budget_exceeded", "severity": "info", "message": "recovered"},
        )
        assert res.status_code == 200
        assert res.json()["action"] == "resolved"

        alerts = client.get("/api/alerts").json()
        assert any(a["alert_id"] == alert_id and a["status"] == "resolved" for a in alerts)


def test_visual_regression_qa_alert_endpoint_ingests_failure(tmp_path):
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        res = client.post(
            "/api/alerts/visual-regression-qa",
            json={"case_id": "battle_hud_overlay", "passed": False, "message": "pixel diff 3.4%"},
        )
        assert res.status_code == 200
        assert res.json()["action"] == "ingested"
        assert res.json()["severity"] == "critical"

        alerts = client.get("/api/alerts").json()
        assert any(a["source_tool_id"] == "visual_regression_qa_tool" and a["status"] == "open" for a in alerts)


def test_visual_regression_qa_alert_endpoint_resolves_on_pass(tmp_path):
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        client.post(
            "/api/alerts/visual-regression-qa",
            json={"case_id": "battle_hud_overlay", "passed": False},
        )
        res = client.post(
            "/api/alerts/visual-regression-qa",
            json={"case_id": "battle_hud_overlay", "passed": True},
        )
        assert res.json()["action"] == "resolved"

        alerts = client.get("/api/alerts").json()
        assert all(a["status"] == "resolved" for a in alerts if a["source_tool_id"] == "visual_regression_qa_tool")


def test_asset_data_insight_alert_endpoint_ingests_warning(tmp_path):
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        res = client.post(
            "/api/alerts/asset-data-insight",
            json={"asset_id": "characters/hero_base_mesh", "severity": "warn", "message": "polycount budget exceeded"},
        )
        assert res.status_code == 200
        assert res.json()["action"] == "ingested"

        alerts = client.get("/api/alerts").json()
        assert any(a["source_tool_id"] == "asset_data_insight_suite" for a in alerts)


def test_alert_ingestion_endpoint_rejects_invalid_severity(tmp_path):
    app = _app_with_rpc_and_ci(tmp_path)
    with TestClient(app) as client:
        res = client.post(
            "/api/alerts/profiling-tool",
            json={"signature": "x", "severity": "not-a-real-severity"},
        )
        assert res.status_code == 400


def test_profiling_section_shows_runs_from_profiling_tool_subpackage(tmp_path):
    """v2.0: profiling_toolはHubのサブ機能として統合されている。Hubのダッシュボードが
    profiling_tool.dashboard.data_sources経由(同一プロセス内呼び出し)でトレースを
    表示できることを確認する。
    """
    from profiling_tool.core import chrome_trace
    from profiling_tool.core.recorder import TraceWriter

    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    traces_dir = tmp_path / "profiling_traces"
    writer = TraceWriter(target="videofactory", run_id="run001", traces_dir=traces_dir)
    writer.append(
        [
            chrome_trace.span("Narrate", ts=0, dur=1_000_000),
            chrome_trace.counter("active_voices", value=4, ts=0),
        ]
    )

    app = app_module.create_app(
        registry_path=str(registry_path),
        db_path=str(tmp_path / "hub_state.sqlite3"),
        profiling_traces_dir=str(traces_dir),
    )
    with TestClient(app) as client:
        res = client.get("/")
        assert "videofactory" in res.text
        assert "run001" in res.text
        assert "Narrate" in res.text
        assert "active_voices" in res.text


def test_profiling_section_empty_state_when_no_traces(tmp_path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path),
        db_path=str(tmp_path / "hub_state.sqlite3"),
        profiling_traces_dir=str(tmp_path / "empty_traces"),
    )
    with TestClient(app) as client:
        res = client.get("/")
        assert "まだトレースがありません" in res.text


def test_profiling_section_does_not_break_hub_dashboard_when_traces_dir_is_a_file(tmp_path):
    """非機能要件: profiling_toolの不具合でHub本体のダッシュボードが落ちないこと。
    traces_dirとして本来ディレクトリであるべき場所にファイルを置き、意図的に
    profiling_tool側の読み込みを壊した状態でもHubのダッシュボード自体は200を返すことを確認する。
    """
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    broken_traces_path = tmp_path / "not_a_directory"
    broken_traces_path.write_text("not a directory", encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path),
        db_path=str(tmp_path / "hub_state.sqlite3"),
        profiling_traces_dir=str(broken_traces_path),
    )
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200


def _init_git_remote_and_clone(tmp_path, name: str) -> tuple:
    """test_repo_sync.pyと同じ最小git remote/cloneセットアップ(ローカル完結、実GitHubに触れない)。"""
    import subprocess

    def _git(args, cwd):
        subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)

    remote = tmp_path / f"{name}_remote"
    remote.mkdir()
    _git(["init", "-b", "main"], remote)
    _git(["config", "user.email", "test@example.com"], remote)
    _git(["config", "user.name", "Test"], remote)
    (remote / "file.txt").write_text("v1", encoding="utf-8")
    _git(["add", "file.txt"], remote)
    _git(["commit", "-m", "initial"], remote)

    local = tmp_path / f"{name}_local"
    _git(["clone", str(remote), str(local)], tmp_path)
    _git(["config", "user.email", "test@example.com"], local)
    _git(["config", "user.name", "Test"], local)
    return remote, local


def _write_repos_yaml(tmp_path, repo_id: str, local_dir_name: str, remote_path) -> str:
    """テスト用repos.yamlを書き出す。

    RepoSyncManagerはHub自身のリポジトリルートを基準にlocal_path(相対)を解決するため、
    tmp_path配下に作ったクローンを指すにはlocal_pathを絶対パスで書く必要がある。
    """
    repos_path = tmp_path / "repos.yaml"
    local_path = (tmp_path / local_dir_name).resolve()
    repos_path.write_text(
        f"""
repos:
  - repo_id: {repo_id}
    display_name: "{repo_id}"
    local_path: "{str(local_path).replace(chr(92), '/')}"
    remote_url: "{str(remote_path).replace(chr(92), '/')}"
    branch: main
""",
        encoding="utf-8",
    )
    return str(repos_path)


def test_repos_endpoint_lists_registered_repo_with_status(tmp_path):
    _remote, _local = _init_git_remote_and_clone(tmp_path, "sample")
    repos_path = _write_repos_yaml(tmp_path, "sample", "sample_local", _remote)

    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path),
        db_path=str(tmp_path / "hub_state.sqlite3"),
        repos_path=repos_path,
    )
    with TestClient(app) as client:
        rows = client.get("/api/repos").json()
        assert len(rows) == 1
        assert rows[0]["repo_id"] == "sample"
        # バックグラウンドの_repo_check_loopはlifespan起動時に1回チェックするが、
        # HTTPリクエストとの実行順は保証されないため、ここでは明示的にcheckをトリガして
        # 決定的に検証する(バックグラウンドチェック自体の存在はtest_repo_sync.pyで検証済み)。
        rows = client.post("/api/repos/check").json()
        assert rows[0]["is_up_to_date"] is True


def test_repos_check_endpoint_detects_new_commits_without_mutating_working_tree(tmp_path):
    import subprocess

    remote, local = _init_git_remote_and_clone(tmp_path, "sample")
    (remote / "file.txt").write_text("v2", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=str(remote), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "update"], cwd=str(remote), check=True, capture_output=True)

    repos_path = _write_repos_yaml(tmp_path, "sample", "sample_local", remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path),
        db_path=str(tmp_path / "hub_state.sqlite3"),
        repos_path=repos_path,
    )
    with TestClient(app) as client:
        rows = client.post("/api/repos/check").json()
        assert rows[0]["commits_behind"] == 1
        assert rows[0]["can_sync"] is True
        # checkはfetchのみ。ワーキングツリーは変更されていない
        assert (local / "file.txt").read_text(encoding="utf-8") == "v1"


def test_repo_sync_endpoint_pulls_new_commits(tmp_path):
    import subprocess

    remote, local = _init_git_remote_and_clone(tmp_path, "sample")
    (remote / "file.txt").write_text("v2-synced", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=str(remote), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "update"], cwd=str(remote), check=True, capture_output=True)

    repos_path = _write_repos_yaml(tmp_path, "sample", "sample_local", remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path),
        db_path=str(tmp_path / "hub_state.sqlite3"),
        repos_path=repos_path,
    )
    with TestClient(app) as client:
        res = client.post("/api/repos/sample/sync")
        assert res.status_code == 200
        assert res.json()["ok"] is True

    assert (local / "file.txt").read_text(encoding="utf-8") == "v2-synced"


def test_repo_sync_endpoint_rejects_unknown_repo_id(tmp_path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3")
    )
    with TestClient(app) as client:
        res = client.post("/api/repos/does_not_exist/sync")
        assert res.status_code == 404


def test_dashboard_renders_repositories_section(tmp_path):
    _remote, _local = _init_git_remote_and_clone(tmp_path, "sample")
    repos_path = _write_repos_yaml(tmp_path, "sample", "sample_local", _remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path),
        db_path=str(tmp_path / "hub_state.sqlite3"),
        repos_path=repos_path,
    )
    with TestClient(app) as client:
        res = client.get("/")
        assert "sample" in res.text


def _write_repos_yaml_with_launch(tmp_path, local_dir_name: str, remote_path) -> str:
    repos_path = tmp_path / "repos.yaml"
    local_path = (tmp_path / local_dir_name).resolve()
    repos_path.write_text(
        f"""
repos:
  - repo_id: sample
    display_name: "Sample"
    local_path: "{str(local_path).replace(chr(92), '/')}"
    remote_url: "{str(remote_path).replace(chr(92), '/')}"
    branch: main
    launch:
      - name: "Dev server"
        command: "npm run dev"
        cwd: "."
        url: "http://127.0.0.1:1"
    launch_note: "test note"
""",
        encoding="utf-8",
    )
    return str(repos_path)


def test_repo_launch_endpoint_invokes_process_launcher(tmp_path, monkeypatch):
    from hub.process_launcher import LaunchResult

    remote, _local = _init_git_remote_and_clone(tmp_path, "sample")
    repos_path = _write_repos_yaml_with_launch(tmp_path, "sample_local", remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    captured = {}

    def fake_launch(entry, target, repo_root):
        captured["entry"] = entry
        captured["target"] = target
        return LaunchResult(ok=True, message="started", pid=999)

    monkeypatch.setattr(app_module, "launch", fake_launch)

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3"), repos_path=repos_path
    )
    with TestClient(app) as client:
        res = client.post("/api/repos/sample/launch/0")
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["pid"] == 999

    assert captured["entry"].repo_id == "sample"
    assert captured["target"].name == "Dev server"


def test_repo_launch_endpoint_rejects_unknown_target_index(tmp_path):
    remote, _local = _init_git_remote_and_clone(tmp_path, "sample")
    repos_path = _write_repos_yaml_with_launch(tmp_path, "sample_local", remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3"), repos_path=repos_path
    )
    with TestClient(app) as client:
        res = client.post("/api/repos/sample/launch/99")
        assert res.status_code == 404


def test_repo_launch_endpoint_returns_500_when_launcher_fails(tmp_path, monkeypatch):
    from hub.process_launcher import LaunchResult

    remote, _local = _init_git_remote_and_clone(tmp_path, "sample")
    repos_path = _write_repos_yaml_with_launch(tmp_path, "sample_local", remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    monkeypatch.setattr(
        app_module, "launch", lambda entry, target, repo_root: LaunchResult(ok=False, message="boom")
    )

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3"), repos_path=repos_path
    )
    with TestClient(app) as client:
        res = client.post("/api/repos/sample/launch/0")
        assert res.status_code == 500


def test_repo_open_folder_endpoint_invokes_process_launcher(tmp_path, monkeypatch):
    from hub.process_launcher import LaunchResult

    remote, _local = _init_git_remote_and_clone(tmp_path, "sample")
    repos_path = _write_repos_yaml_with_launch(tmp_path, "sample_local", remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    captured = {}

    def fake_open_folder(entry, repo_root):
        captured["entry"] = entry
        return LaunchResult(ok=True, message="opened")

    monkeypatch.setattr(app_module, "open_folder", fake_open_folder)

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3"), repos_path=repos_path
    )
    with TestClient(app) as client:
        res = client.post("/api/repos/sample/open-folder")
        assert res.status_code == 200
        assert res.json()["ok"] is True

    assert captured["entry"].repo_id == "sample"


def test_dashboard_renders_launch_buttons_and_note(tmp_path):
    remote, _local = _init_git_remote_and_clone(tmp_path, "sample")
    repos_path = _write_repos_yaml_with_launch(tmp_path, "sample_local", remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY_V1, encoding="utf-8")

    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub_state.sqlite3"), repos_path=repos_path
    )
    with TestClient(app) as client:
        res = client.get("/")
        assert "Start: Dev server" in res.text
        assert "Open folder" in res.text
        assert "test note" in res.text
