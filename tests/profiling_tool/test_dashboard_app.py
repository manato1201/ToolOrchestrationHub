"""dashboard/app.py のHTTPレイヤー結合テスト。"""
from __future__ import annotations

from fastapi.testclient import TestClient

import profiling_tool.dashboard.app as app_module
from profiling_tool.core import chrome_trace
from profiling_tool.core.recorder import TraceWriter


def _seed_trace(traces_dir):
    writer = TraceWriter(target="videofactory", run_id="run001", traces_dir=traces_dir)
    writer.append(
        [
            chrome_trace.span("Narrate", ts=0, dur=1_000_000),
            chrome_trace.span("AssembleAndRender", ts=1_000_000, dur=4_000_000),
            chrome_trace.counter("active_voices", value=4, ts=0),
            chrome_trace.counter("active_voices", value=8, ts=1_000_000),
            chrome_trace.event("reasoning_trace", ts=0, payload={"reasoning": "テスト用の実データ"}),
        ]
    )
    return writer


def test_root_lists_runs_and_shows_selected_run_details(tmp_path):
    traces_dir = tmp_path / "traces"
    _seed_trace(traces_dir)

    app = app_module.create_app(traces_dir=str(traces_dir), checkpoint_dir=str(tmp_path / "checkpoints"))
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert "videofactory" in res.text
        assert "run001" in res.text
        assert "Narrate" in res.text
        assert "active_voices" in res.text


def test_root_with_no_runs_shows_empty_state(tmp_path):
    app = app_module.create_app(traces_dir=str(tmp_path / "traces"), checkpoint_dir=str(tmp_path / "checkpoints"))
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert "まだトレースがありません" in res.text


def test_api_runs_returns_seeded_run(tmp_path):
    traces_dir = tmp_path / "traces"
    _seed_trace(traces_dir)
    app = app_module.create_app(traces_dir=str(traces_dir), checkpoint_dir=str(tmp_path / "checkpoints"))
    with TestClient(app) as client:
        res = client.get("/api/runs")
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1
        assert body[0]["target"] == "videofactory"


def test_api_run_summary_returns_latency_and_usage(tmp_path):
    traces_dir = tmp_path / "traces"
    _seed_trace(traces_dir)
    app = app_module.create_app(traces_dir=str(traces_dir), checkpoint_dir=str(tmp_path / "checkpoints"))
    with TestClient(app) as client:
        res = client.get("/api/runs/videofactory/run001/summary")
        body = res.json()
        assert "Narrate" in body["latency"]
        assert "active_voices" in body["usage"]


def test_service_integration_panel_reports_hub_unreachable_when_not_running(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILING_HUB_URL", "http://127.0.0.1:1")  # 何も listen していないポート
    monkeypatch.delenv("PROFILING_WEBHOOK_URL", raising=False)

    app = app_module.create_app(traces_dir=str(tmp_path / "traces"), checkpoint_dir=str(tmp_path / "checkpoints"))
    with TestClient(app) as client:
        res = client.get("/")
        assert "unreachable" in res.text
        assert "not configured" in res.text


def test_backend_panel_shows_captured_data_sample_unmasked(tmp_path):
    traces_dir = tmp_path / "traces"
    _seed_trace(traces_dir)
    app = app_module.create_app(traces_dir=str(traces_dir), checkpoint_dir=str(tmp_path / "checkpoints"))
    with TestClient(app) as client:
        res = client.get("/")
        assert "テスト用の実データ" in res.text
        assert "データベースは使用しない" in res.text
