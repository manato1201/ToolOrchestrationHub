"""Phase 1: ツールレジストリ。

12ツールの存在・transport・ヘルスチェック契約を単一の台帳として持つ。
後続の全フェーズ(ヘルスチェック、アラート集約、ダッシュボード)はこのレジストリを起点にする。

v1は静的registry.yamlのみを読み込む。動的自己登録は将来課題としてスコープ外。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_REGISTRY_PATH = Path(__file__).parent / "registry.yaml"


class TransportKind(str, Enum):
    """統合対象棚卸し表で実際に登場した4パターン。新規に発明した抽象ではない。"""

    HTTP_BRIDGE = "http_bridge"  # 例: DevelopmentRAGEnvironmentの:8766ブリッジ
    RPC = "rpc"  # 例: LoreDesktopAndWebSystemのQLocalSocket、SoundMiddlewareの独自RPC
    CI_BATCH = "cli_batch"  # 例: Research-Collectorのcron実行、AssetDataInsightSuiteのCI定期実行
    STATIC_SITE = "static_site"  # 例: The-Algorithm-Illustrated、ColorEncyclopedia(監視対象外)


class ToolCategory(str, Enum):
    """Hubがそのツールにどう関わるかを型レベルで明示する3値。"""

    MONITORED = "monitored"  # Hubが能動的にヘルスチェックする
    OBSERVED_ONLY = "observed_only"  # 他ツール経由の間接メトリクス/受動ハートビートのみ
    EXCLUDED = "excluded"  # Registryには載せるが監視対象外


class IsolationKind(str, Enum):
    """ツール実行の隔離方式(IMPROVEMENT_PLAN_2026-10 H4)。事故の被害範囲を限定するための方針。

    Hub自身はツールを起動・隔離しない(監視のみ)。ここは「そのツールをどの方式で動かす方針か」を
    台帳に残すための項目で、値の選び方は「何が分離されるか / Dockerの要否 / 手間」の3軸で決める。
    """

    NONE = "none"  # 隔離なし(ホスト上でそのまま動かす)
    SANDBOX_BASH = "sandbox-bash"  # OSレベルのサンドボックス(ファイル/ネットワーク制限)
    CONTAINER = "container"  # コンテナ(Docker等)
    VM = "vm"  # 仮想マシン(使い捨てCIランナーを含む)


class RegistryError(Exception):
    """registry.yamlのパース/スキーマ検証に失敗した場合に送出する。"""


_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class ToolEntry:
    tool_id: str
    display_name: str
    transport: TransportKind
    endpoint: Optional[str]  # http_bridge/rpcのみ意味を持つ。cli_batch/static_siteはNone
    health_check: Optional[str]  # 対応するhealth/*_check.pyの関数名。無ければNone
    category: ToolCategory
    # 以下はPhase1のToolEntryスキーマ本体には無いが、Phase2のランナーが
    # 「対象ツール自身の間隔より高頻度でポーリングしない」を実装するために
    # registry.yaml側に静的設定として持たせる拡張フィールド。
    poll_interval_s: Optional[float] = None
    check_params: dict[str, Any] = field(default_factory=dict)
    # 2026-10 改善(IMPROVEMENT_PLAN H4 / UI U3)で追加した任意フィールド。いずれも未指定でも動く。
    isolation: Optional[IsolationKind] = None  # 隔離方式。未指定はダッシュボードで「未設定」と表示する
    owner_rules: tuple[str, ...] = ()  # そのツール固有の「Hubが守る/運用側が守る制約」の短文
    symbol: Optional[str] = None  # ダッシュボード共通の丸い記号(1〜2文字)。未指定は名前から自動生成
    color: Optional[str] = None  # 記号の固定色(#rrggbb)。未指定はtool_idから自動生成

    @classmethod
    def from_dict(cls, raw: dict) -> "ToolEntry":
        required = {"tool_id", "display_name", "transport", "health_check", "category"}
        missing = required - raw.keys()
        if missing:
            raise RegistryError(f"ToolEntryに必須フィールドが不足しています: {missing} (raw={raw})")
        try:
            transport = TransportKind(raw["transport"])
        except ValueError as exc:
            raise RegistryError(f"未知のtransport種別です: {raw['transport']!r}") from exc
        try:
            category = ToolCategory(raw["category"])
        except ValueError as exc:
            raise RegistryError(f"未知のcategory種別です: {raw['category']!r}") from exc

        tool_id = raw["tool_id"]
        isolation = None
        if raw.get("isolation") is not None:
            try:
                isolation = IsolationKind(raw["isolation"])
            except ValueError as exc:
                allowed = ", ".join(k.value for k in IsolationKind)
                raise RegistryError(
                    f"{tool_id}: 未知のisolation種別です: {raw['isolation']!r}(使える値: {allowed})"
                ) from exc

        owner_rules = raw.get("owner_rules") or []
        if not isinstance(owner_rules, list) or not all(isinstance(r, str) for r in owner_rules):
            raise RegistryError(f"{tool_id}: owner_rulesは文字列のリストで指定してください: {owner_rules!r}")

        symbol = raw.get("symbol")
        if symbol is not None and (not isinstance(symbol, str) or not 1 <= len(symbol) <= 2):
            raise RegistryError(f"{tool_id}: symbolは1〜2文字の文字列で指定してください: {symbol!r}")

        color = raw.get("color")
        if color is not None and (not isinstance(color, str) or not _COLOR_RE.match(color)):
            raise RegistryError(f"{tool_id}: colorは#rrggbb形式で指定してください: {color!r}")

        return cls(
            tool_id=tool_id,
            display_name=raw["display_name"],
            transport=transport,
            endpoint=raw.get("endpoint"),
            health_check=raw.get("health_check"),
            category=category,
            poll_interval_s=raw.get("poll_interval_s"),
            check_params=raw.get("check_params") or {},
            isolation=isolation,
            owner_rules=tuple(owner_rules),
            symbol=symbol,
            color=color,
        )


class ToolRegistry:
    """`registry.yaml`から読み込んだToolEntryの一覧を保持する。

    Registryのエントリ追加・削除はHubの再起動なしで反映できることが望ましいが、
    v1では静的ファイルの再読込(reload())で足りるとする。
    """

    def __init__(self, entries: list[ToolEntry], source_path: Optional[Path] = None) -> None:
        self._entries_by_id: dict[str, ToolEntry] = {}
        for e in entries:
            if e.tool_id in self._entries_by_id:
                raise RegistryError(f"tool_idが重複しています: {e.tool_id}")
            self._entries_by_id[e.tool_id] = e
        self._source_path = source_path
        self._loaded_mtime = self._stat_mtime(source_path)

    @staticmethod
    def _stat_mtime(path: Optional[Path]) -> Optional[float]:
        if path is None or not path.exists():
            return None
        return path.stat().st_mtime

    @classmethod
    def load(cls, path: Path | str = DEFAULT_REGISTRY_PATH) -> "ToolRegistry":
        path = Path(path)
        try:
            with path.open(encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            # ホットリロード中に書き換え途中のYAMLを読んでしまうケースを想定し、
            # 呼び出し側(app.pyのregistry_watch_loop/reloadエンドポイント)が
            # 一律にRegistryErrorだけを捕まえればよいようにラップする。
            raise RegistryError(f"{path} のYAMLパースに失敗しました: {exc}") from exc
        tools_raw = raw.get("tools")
        if tools_raw is None:
            raise RegistryError(f"{path} に 'tools' キーがありません")
        entries = [ToolEntry.from_dict(t) for t in tools_raw]
        return cls(entries, source_path=path)

    @property
    def source_path(self) -> Optional[Path]:
        return self._source_path

    def has_changed_on_disk(self) -> bool:
        """load()/reload()以降にsource_pathのmtimeが変化したか(ホットリロードの判定用)。"""
        return self._stat_mtime(self._source_path) != self._loaded_mtime

    def reload(self, path: Optional[Path | str] = None) -> "ToolRegistry":
        """静的ファイルを再読込する。v1の「再起動なし反映」要件を満たす最小実装。

        pathを省略した場合は直近load()したパス(source_path)を再読込する。
        """
        target = Path(path) if path is not None else self._source_path or DEFAULT_REGISTRY_PATH
        fresh = ToolRegistry.load(target)
        self._entries_by_id = fresh._entries_by_id
        self._source_path = fresh._source_path
        self._loaded_mtime = fresh._loaded_mtime
        return self

    def all(self) -> list[ToolEntry]:
        return list(self._entries_by_id.values())

    def get(self, tool_id: str) -> Optional[ToolEntry]:
        return self._entries_by_id.get(tool_id)

    def by_category(self, category: ToolCategory) -> list[ToolEntry]:
        return [e for e in self._entries_by_id.values() if e.category is category]

    def monitored(self) -> list[ToolEntry]:
        """category: excluded / observed_onlyのツールはここに含まれない。

        Phase2以降のヘルスチェックループはこのメソッドの返り値のみを対象にする。
        """
        return self.by_category(ToolCategory.MONITORED)
