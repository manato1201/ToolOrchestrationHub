"""hub/tool_identity.py(ツールの丸い記号と固定色。UI改善 U3)のテスト。"""
from __future__ import annotations

from hub.registry import ToolRegistry
from hub.tool_identity import color_for, hue_to_hex, identity_for_unregistered, symbol_for

TEXT_COLOR = "#e9ebdf"  # style.css の --text-parchment


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_every_shipped_tool_has_a_unique_symbol_of_one_or_two_characters():
    registry = ToolRegistry.load()
    symbols = [symbol_for(e) for e in registry.all()]
    assert all(1 <= len(s) <= 2 for s in symbols)
    assert len(set(symbols)) == len(symbols), f"記号が重複しています: {symbols}"


def test_every_shipped_tool_has_a_unique_fixed_color_readable_with_the_text_color():
    registry = ToolRegistry.load()
    colors = [color_for(e) for e in registry.all()]
    assert len(set(colors)) == len(colors), f"色が重複しています: {colors}"
    for entry in registry.all():
        assert entry.color is not None, f"{entry.tool_id}: 固定色がregistry.yamlに無い"
        assert _contrast(color_for(entry), TEXT_COLOR) >= 4.5, entry.tool_id


def test_registry_values_take_priority_over_generated_fallbacks():
    registry = ToolRegistry.load()
    entry = registry.get("asset_data_insight_suite")
    assert symbol_for(entry) == "As"
    assert color_for(entry) == "#406d62"


def test_fallback_is_stable_so_a_tool_keeps_its_symbol_and_color_across_renders():
    from hub.registry import ToolEntry

    raw = {
        "tool_id": "brand_new_tool",
        "display_name": "BrandNewTool",
        "transport": "static_site",
        "health_check": None,
        "category": "excluded",
    }
    first = ToolEntry.from_dict(raw)
    second = ToolEntry.from_dict(raw)
    assert symbol_for(first) == symbol_for(second) == "Br"
    assert color_for(first) == color_for(second)


def test_fallback_colors_are_readable_for_every_hue():
    """生成色は色相に依らず文字色とのコントラストが4.5:1以上(新しいツールを足しても読める)。"""
    for hue in range(360):
        assert _contrast(hue_to_hex(hue), TEXT_COLOR) >= 4.5, f"hue={hue}"


def test_unregistered_source_gets_a_deterministic_identity():
    assert identity_for_unregistered("external_tool") == identity_for_unregistered("external_tool")
    symbol, color = identity_for_unregistered("external_tool")
    assert symbol == "Ex"
    assert color.startswith("#") and len(color) == 7
