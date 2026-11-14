# ToolOrchestrationHub 講義(基礎から)

Hub の**基礎的な考え方・コード・アルゴリズム・専門用語**を、順に学ぶ講義です。各回は「**この回のゴール → 説明と実行できる例 → 確認問題 → 解答 → まとめ**」の形で、コードは実際に動かして確かめてあります(`tests/test_docs.py` が、コードのずれと出力を検査します)。

| 回 | 題 | 学ぶこと | 目安 |
|---|---|---|---|
| [0](00-introduction.md) | Hub とは何か | 解きたい問題・登場人物・**能動と受動**・台帳を読み込む | 1 h |
| [1](01-registry.md) | 台帳(registry) | `ToolEntry`・`Enum`・読み込み時の検証・**循環の検出(DFS)**・ホットリロード | 2 h |
| [2](02-health-checks.md) | 死活監視 | 3 種の判定・`time.monotonic()`・**信号なしを正常にしない**・間引き | 3 h |
| [3](03-alerts.md) | アラート | ライフサイクル・`alert_id`(ハッシュ)・**dedup**・再発・正規化・スヌーズ | 3 h |
| [4](04-state-and-priority.md) | 状態と見る順番 | 5 つの状態・**純関数**・ライブと履歴で同じ規則・ルールベースの優先度・`Protocol` | 2.5 h |
| [5](05-security-and-auth.md) | Hub 自身を守る | **CSRF・DNS rebinding**・Host/Origin・API キー(ハッシュ・定数時間)・役割・監査・fail-closed | 3.5 h |
| [6](06-testing-capstone.md) | テストと総合演習 | テストの置き方・外へ出る処理の差し替え・`profiling_tool`(span → トレース → p95)・**新しい送り手を足す** | 半日 |

## 進め方

- **前提**: Python の基本(関数・クラス・辞書・`async/await` を見たことがある)。FastAPI は、第 5 回で必要な分だけ出てくる。
- 例は、リポジトリのルートで動かします(`uv run python -c "..."` か、`.venv` の Python)。**本物のネットワーク・git・通知は使いません**。
- 詰まったら、先に [学習資料の用語集](../learn/glossary.md)。
- 講義を終えたら、保守・拡張の実務へ: [学習資料](../learn/index.md)。
