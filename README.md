# ToolOrchestrationHub

今まで作ってきたシステム・機能を**中継・モニタリング**し、使用者にとって使いやすくするための**監視の中継所**です。
13 個のツールの**生死・アラート**と、15 個のリポジトリの**git の状態**を、1 つの画面と通知に集めます。**見るだけ**で、ツールの権限は奪いません。

![構成図](docs/diagrams/architecture.svg)

## 状態

| 項目 | 内容 |
|---|---|
| 版 | v2.7(認証・役割・監査ログ。経緯は [変更履歴](docs/reference/changelog.md)) |
| 台帳 | 13 ツール(`hub/registry.yaml`)・15 リポジトリ(`hub/repos.yaml`) |
| テスト | `uv run pytest -q` で全部通る(Hub 本体 + `profiling_tool` + 文書の検査) |
| 画面の確認 | 実ブラウザは **Chrome のみ**。Firefox・Safari・スマホ実機は**未確認** |
| 認証 | 既定は**なし**(`HUB_AUTH=off`。Host・Origin の検査だけ)。複数人なら `HUB_AUTH=required` |
| 既知の問題 | [トラブルと保守](docs/learn/06-troubleshooting-maintenance.md)(CI 系の「未確認」が長引く等) |

## クイックスタート

```bash
uv sync --extra dev
uv run pytest -q
uv run hub          # http://127.0.0.1:8790 でダッシュボードを起動
```

**ダブルクリックで開く**(2026-11-17): `Start-Hub.cmd`(または `tools/start_hub.ps1`)が、Hub を起動して(動いていれば起動し直さず)、Edge のアプリ窓(アドレスバーの無い専用ウィンドウ)で開きます。デスクトップへのショートカットは `tools/start_hub.ps1 -InstallShortcut` で作れます(付けなければ何も作りません)。Hub を終わらせるときは、最小化されたコンソールを閉じます。

**Unsloth とセットで開く**(2026-11-24): `tools/start_hub.ps1 -InstallShortcut -WithUnsloth` で、デスクトップに「ToolOrchestrationHub + Unsloth」のショートカットを作れます。このアイコンを開くと、Hub を開き、Unsloth Desktop を開き(開いていれば何もしない)、LocalLLMHarness の `llh autostart`(見張り)を非表示で起動します。見張りが、Unsloth の起動を見て、窓口と、LocalLLMHarness の `config.toml` に書いたサービス(ChapterLens のエンジンなど)を自動で起動し、Unsloth を閉じると、起動したものを止めます。Unsloth Desktop や LocalLLMHarness が見つからなければ、その分だけ飛ばして、Hub は開きます。**事前に**: LocalLLMHarness の `config.toml` の `[autostart]`(説明は LocalLLMHarness の README)と、`LLH_BACKEND_API_KEY`(`setx` で保存)が要ります。Hub の「リポジトリ」の LocalLLMHarness の行の「見張り(Unsloth とセット)」でも、同じ見張りを起動できます。**実機の Unsloth Desktop では未確認**(`-DryRun` の表示と、偽の Unsloth での見張りの動作だけ確認)。

**起動と停止**(2026-11-17): 各ツールの行の `Start` で起動し、`Stop` で止めます。状態は 3 つ(▶ 稼働中 / … 起動中 / ■ 停止中)。**止められるのは、この Hub が起動したものだけ**です(起動時に記録した PID の、コマンドプロセッサと子プロセス。Hub の外で起動したものや、PID が別のプロセスに使い回されたものは止めません)。ログの収集・自動再起動は、引き続きしません。

**URL の表示と、自動で開く**(2026-11-24): 起動する対象に `url` があれば、行にリンクとして出します(止まっていても出るので、あとからでも開けます)。Web 画面のある対象(`open` を省いたもの)は、`Start` を押すと、ブラウザの**新しいタブを先に開いて待ち**、URL に届いたら(最大 90 秒)そこへ移ります。画面の無い対象(ヘルスチェック・API。`hub/repos.yaml` で `open: false`)は、タブを開かず、URL の表示だけです。タブを開けなかった(ブロックされた)・90 秒たっても届かなかったときは、その旨を出すので、行の URL から開いてください。`Start all` は、自動で開く対象のうち**先頭の 1 つ**だけ、タブを先に開きます(残りは届いたら開き、ブロックされたら行の URL から)。表示するのは `http://` `https://` の URL だけです。

**ChapterLens の起動・停止**(2026-11-24): 「リポジトリ」に ChapterLens を足しました(15 件目)。`Start: エンジン(ローカル)` で、Chrome 拡張の相手(`uv run python -m chapterlens serve`。拡張の固定の ID だけを許可、`127.0.0.1:8787`)を起動し、`Stop` で止めます。止められるのは**この Hub が起動したものだけ**です。Unsloth とセットの `llh autostart` が起動したエンジンは、Hub の外で起動したものなので、ここからは止められません(Unsloth を閉じると止まります)。題名・大見出し(ローカル LLM)を使うなら、先に `uv run python -m chapterlens admin llm on` を一度実行し、窓口も起動しておきます。

**状態変化の動き(ばね)**(2026-11-26): 絞り込み・表示・並べ替えのチップは、選択中の下地がばねで滑って移ります。`Start` は「回る輪 + 状態の文字 → ✓ と緑」で読み込みから完了までを示し、失敗すると揺れます。管理画面の `Sync`(git pull)は、確認ダイアログの代わりに**長押し(約 1.2 秒)**で実行します(押してすぐ離しても実行しない・Space / Enter の長押しでも可)。動きは designbookmark.com の Motion 部品(Segmented control・Loading to success・Hold to publish)を元に、**ばねの値だけを合わせて書き直した**もの(元のコードはライセンスの記載が無いので使っていない)。値は `style.css` の `--spring-*`、計算は `static/spring.js`。動きを減らす設定では、すぐ切り替わります。

```bash
# 各ツールからの信号(認証を必須にしたときは X-API-Key を付ける)
curl -X POST http://127.0.0.1:8790/api/heartbeat/sound_middleware
curl -X POST http://127.0.0.1:8790/api/ci-success/research_collector
curl -X POST http://127.0.0.1:8790/api/alerts/profiling-tool -H "Content-Type: application/json" \
  -d '{"signature": "gpu_frame_budget_exceeded", "severity": "critical", "message": "frame budget exceeded"}'
```

`hub/registry.yaml` の `poll_interval_s`・`check_params` は**暫定値**です。ツール側が固まったら、このファイルだけを直せば追従します(再起動不要・5 秒で反映)。

## できること

- **台帳**(`hub/registry.py`・`registry.yaml`): ツールをデータで持つ。ホットリロード、壊れた台帳は拒否して古いまま動く。
- **死活監視**(`hub/health/`): HTTP の `/health`(能動)・ハートビート(受動)・CI の最終成功(経過時間)。**信号が無い間は「未確認」**(偽の正常を出さない)。
- **アラート**(`hub/alert_aggregator.py`): 4 つの送り手を同じ形に正規化し、重複を 1 件にまとめ、解消まで追う。SQLite に保存し、再起動後も履歴が残る。
- **通知**(`hub/notify.py`): Windows トースト、`HUB_SLACK_WEBHOOK_URL` を設定すると Slack も。
- **ダッシュボード**(`hub/dashboard/`): ツール一覧・詳細・サマリ・履歴スライダー・オフィス表示・アラートのフィルタ・エクスポート。
- **リポジトリ**(`hub/repo_sync.py`・`process_launcher.py`): `git fetch` で差分を検知(自動)、`git pull --ff-only` は**人が押したときだけ**、起動は固定のコマンドを新しい窓で。
- **入口の守り**(`hub/security.py`・`auth.py`・`audit.py`): Host の許可リスト、Origin の検査、API キー、`viewer` / `operator` / `admin`、監査ログ、`/admin` の分離。
- **`profiling_tool/`**(サブ機能): span・counter・event の計測 → Chrome Trace 形式 → 集計(p50・p95)。

## ドキュメント

| 読みたいもの | 場所 |
|---|---|
| 全体の地図 | [docs/index.md](docs/index.md) |
| **基礎から学ぶ**(講義 7 回) | [docs/lecture/](docs/lecture/index.md) |
| **保守・拡張する**(レシピ・テスト・トラブル・用語集) | [docs/learn/](docs/learn/index.md) |
| バージョンごとの記録(v1.1〜v2.7) | [docs/reference/changelog.md](docs/reference/changelog.md) |
| 設計書 | [ToolOrchestrationHub_DESIGN.md](ToolOrchestrationHub_DESIGN.md)・[UI 設計](ToolOrchestrationHub_UI_DESIGN.md) |
| 改善の設計と計画(2026-10) | [IMPROVEMENT_DESIGN_2026-10.md](IMPROVEMENT_DESIGN_2026-10.md)・[IMPROVEMENT_PLAN_2026-10.md](IMPROVEMENT_PLAN_2026-10.md) |
| セキュリティ点検 | [docs/SECURITY_REVIEW_2026-10.md](docs/SECURITY_REVIEW_2026-10.md) |

## セキュリティの要点

- Hub は**認証のないローカル API**として始まったので、まず **Host の許可リスト**(DNS rebinding)と、変更操作の **Origin の一致**(CSRF)を検査します。`127.0.0.1`・`localhost`・`::1` 以外の名前で開くときは、環境変数 `HUB_ALLOWED_HOSTS` に足してください(足さないと 403)。
- **複数人で使うときは `HUB_AUTH=required`**。ユーザーが 1 人もいなければ**起動しません**(fail-closed)。API キーは**ハッシュだけ**保存されます。
  ```bash
  uv run python -m hub.auth add --name alice --role admin   # キーは 1 度だけ表示される
  HUB_AUTH=required uv run hub
  ```
- `hub/repos.yaml` の `command` は**シェルとして実行**されます。書き換えられる人は、信頼できる人に限ってください。
- 秘密(Slack の Webhook URL・API キー)は**環境変数**で渡し、リポジトリに書かないでください。

## 限界(正直に)

- 受信時刻・スヌーズ・起動の記録は**メモリだけ**。再起動すると、受動のツールは**次の信号まで「未確認」**に戻ります(アラート履歴は残ります)。
- 履歴スライダーが再現できるのは**アラートの発生・解消だけ**です(死活監視の結果そのものは残りません)。
- 優先度(緊急・通常・情報不足)は**ルールベースの目安**で、較正された確率ではありません。通知・dedup には**つながっていません**。
- 実装していない追補(H3 構造図の自動生成・H5 TransferKit・Cloudflare ミラーなど)の理由は、[変更履歴](docs/reference/changelog.md)にあります。

## ライセンス

[PolyForm Noncommercial License 1.0.0](LICENSE) です。**個人・研究・教育・非営利の利用は無料**で、自由に使えます。**営利目的の利用(会社の業務での利用、有償の製品・サービスへの組み込みなど)は許可されていません**。

- 商用利用をご希望の場合は、[Issue](https://github.com/manato1201/ToolOrchestrationHub/issues)(ラベル `commercial`)でご相談ください。別途の許諾をお出しします。
- 著作権者: 松浦真聖 (Matsuura Manato)。表示事項は [NOTICE](NOTICE) にあります。再配布するときは、`LICENSE` と `NOTICE` を一緒に渡してください。
- 第三者の著作物(依存パッケージ・同梱の素材・外部サービスのデータなど)は、それぞれのライセンスに従います。
- この節は条文の要約です。**条文(LICENSE)が優先します**。

English: licensed under the PolyForm Noncommercial License 1.0.0. Noncommercial use is free; commercial use requires a separate license (open an issue labeled `commercial`).
