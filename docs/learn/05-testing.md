# 5. テストの書き方と実行

## 実行

```bash
uv sync --extra dev        # 初回(pytest・pytest-asyncio)
uv run pytest -q           # 全部(Hub 本体 + profiling_tool + 文書の検査)
uv run pytest tests/test_tool_state.py -q          # 1 ファイルだけ
uv run pytest -k "heartbeat" -q                    # 名前で絞る
```

- `pyproject.toml` の `asyncio_mode = "auto"`: `async def test_...` が、**印なしで**そのまま動く(`pytest-asyncio`)。
- 速度: 全体で **約 1 分**(548 件。うち文書の検査が 88 件)。ほとんどは、ネットワークや本物の `git` を使わない。

## テストの置き場所と、何を確かめるか

| ファイル | 確かめるもの | 主な道具 |
|---|---|---|
| `test_registry.py` | 台帳の読み込み・検証・循環・ホットリロード | `tmp_path` に YAML を書く |
| `test_health_checks.py`・`test_runner.py` | 3 種の判定・間引き・信号なし | 時刻を引数で渡す(`now=`・`at=`)、`httpx.MockTransport` |
| `test_alert_aggregator.py`・`test_alert_store.py` | dedup・再発・解消・スヌーズ・SQLite・旧 DB の移行 | メモリ・一時ファイルの DB |
| `test_tool_state.py`・`test_overview.py` | 状態の判定・概況・履歴の再現 | 純関数なので入力を作るだけ |
| `test_dashboard_app.py` ほか `test_dashboard_*.py` | 画面・API・テンプレート・CSS・JS の決めごと | `TestClient(create_app(...))` |
| `test_security.py`・`test_auth.py`・`test_admin_split.py` | Host・Origin・役割・監査・`/admin` | `TestClient`・環境変数 |
| `test_repo_sync.py`・`test_process_launcher.py` | git の同期・起動(**偽物で**) | `monkeypatch`・`popen=` の差し替え口 |
| `test_notify.py` | 通知先の閾値・失敗の隔離 | 送信の差し替え |
| `tests/profiling_tool/` | 計測基盤 | 時刻を固定した span |
| `test_docs.py` | 文書の検査(下) | `tools/quote_code.py` |

## よく使う型

**1. 時刻を引数にして、待たずに「後」を作る**

```python
def test_rpc_is_down_after_two_intervals():
    now = time.monotonic()
    assert rpc_check("t", now - 25, 10.0).is_up is False   # 25 秒前 > 10 × 2
```

**2. 外へ出る処理を、差し替える**(`monkeypatch`・`popen=`・`is_command_available=`)。本物の `git`・本物の起動をしない。`tests/conftest.py` の `no_real_repo_sync` を使うと、`create_app()` が 15 リポジトリへ `git fetch` しない。

**3. `TestClient` で、サーバーを起動せずに API を叩く**

```python
client = TestClient(create_app(db_path=str(tmp_path / "alerts.sqlite3")))
assert client.post("/api/heartbeat/sound_middleware").status_code == 200
```

`TestClient` の Host は `testserver` なので、`tests/conftest.py` の自動フィクスチャ(`_allow_testserver_host`)が、許可リストに足している。

**4. 環境変数は、`monkeypatch.setenv`**: テストの後に元へ戻る(`os.environ` を直接書き換えると、他のテストに漏れる)。

**5. テストの名前は、挙動の文**(`test_upsert_alert_does_not_overwrite_first_seen_at`)。

## 新しい機能のテストを書く手順

1. **失敗するテストを先に書く**(期待する挙動を、関数の名前と `assert` で表す)。
2. 実装して通す。
3. **異常系**も書く: 壊れた入力(400)・権限不足(403)・未登録(404)・外部の失敗(隔離されること)。
4. **「しないこと」**も書く: 例)補助(優先度)が壊れても、通知は出る。`excluded` に能動の接続を開かない。

## 文書の検査

`docs/` と README の中の**コード**は、実際のソースと一致している必要があります。

```bash
python tools/check_docs.py             # 検査(pytest 不要・標準ライブラリだけ)
python tools/check_docs.py --update    # 引用の更新・実行例の出力の作り直しをしてから検査
python tools/check_mermaid.py          # Mermaid が描画できるか(mmdc が要る)
python tools/make_diagrams.py          # 構成図(SVG)を作り直す
```

`tests/test_docs.py`(同じ検査を pytest で)が確かめること:

- `@@引用 パス::名前@@` で展開した**引用ブロックは、今のソースと完全に一致**する(関数を直したら、`--update` で更新)。
- `# 抜粋` ブロックの各行は、そのソースに**この順で**現れる。
- `# 実行できる` のブロックは、**2 回走らせて**、直後の `# 出力` と一致する(乱数・時刻・一時フォルダのパスを出す例は、2 回目で落ちる)。
- 講義に、標準の節(ゴール・確認問題・解答・まとめ)がある。
- 相対リンクと画像の参照先が実在する。Mermaid が標準の `%%{init}%%` の行で始まる。

> **実行例を書くコツ**: 出力は**決まった値だけ**にする(長さ・ラベル・真偽)。ハッシュ・時刻・`tempfile` のパス・集合の並び(`set` の順は実行ごとに変わる)を、そのまま `print` しない。

## 確かめていないこと(正直に)

- 実ブラウザは **Chrome のみ**で確認した。Firefox・Safari・スマホ実機は**未確認**。
- `prefers-reduced-motion` は、CSS と JS の分岐を**テストで確認**したのみ(OS の設定での実機確認はしていない)。
- 蜂の巣(ASCII)の描画コストは**未測定**。
- 本物のトースト・Slack・Cloudflare Access の**実環境での送受信**は、自動テストでは確かめていない(送信は差し替えて確認)。
- 複数人・長時間の運用での、監査ログ・SQLite の肥大化は**未測定**。
