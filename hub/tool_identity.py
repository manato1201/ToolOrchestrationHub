"""hub/tool_identity.py

ダッシュボード全体で共通に使う「ツールの丸い記号(1〜2文字)と固定色」(UI改善 U3 / 原則 P1)。

registry.yamlに symbol / color があればそれを使い、無い(新しく追加したばかりの)ツールにも
同じ規則で必ず値が付くようにフォールバックを持つ。フォールバックはtool_idだけから決まるため、
再読込しても・何度描画しても同じ記号・同じ色になる(「固定」)。

色は暗い地に文字色(#e9ebdf)を載せても4.5:1以上のコントラストが出る明度に揃え、
状態色(緑/橙/赤)と取り違えないよう彩度を抑えている。
"""
from __future__ import annotations

import colorsys
import hashlib

from .registry import ToolEntry

# 記号の丸に載せる文字色(style.cssの--text-parchmentと同じ値)。
_SYMBOL_TEXT_COLOR = "#e9ebdf"
# 記号の丸の背景色の彩度と、明度の上限。緑〜黄の色相は同じ明度でも明るく見えて文字との
# コントラストが足りなくなるため、色相ごとに明度を下げて、必ず下の最小コントラストを満たす。
_SYMBOL_SATURATION = 0.26
_SYMBOL_LIGHTNESS = 0.34
_MIN_CONTRAST = 4.6  # WCAGの本文の基準4.5:1に少し余裕を持たせる
_MIN_LIGHTNESS = 0.18


def _symbol_from_name(name: str) -> str:
    chars = [c for c in name if c.isalnum()]
    if not chars:
        return "?"
    first = chars[0].upper()
    if len(chars) == 1:
        return first
    return first + chars[1].lower()


def _color_from_id(tool_id: str) -> str:
    digest = hashlib.sha256(tool_id.encode("utf-8")).digest()
    return hue_to_hex(int.from_bytes(digest[:2], "big") % 360)


def symbol_for(entry: ToolEntry) -> str:
    """丸い記号に入れる1〜2文字。registryの指定を優先し、無ければ表示名の頭文字から作る。"""
    return entry.symbol or _symbol_from_name(entry.display_name)


def color_for(entry: ToolEntry) -> str:
    """丸い記号の背景色(#rrggbb)。registryの指定を優先し、無ければtool_idから決める。"""
    return entry.color or _color_from_id(entry.tool_id)


def identity_for_unregistered(tool_id: str) -> tuple[str, str]:
    """台帳に無いtool_id(外部から届いたアラートの発生元など)の記号と色。同じIDなら常に同じ値。"""
    return _symbol_from_name(tool_id), _color_from_id(tool_id)


def _hls_hex(hue_degrees: float, lightness: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue_degrees / 360, lightness, _SYMBOL_SATURATION)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(color_a: str, color_b: str) -> float:
    hi, lo = sorted((_luminance(color_a), _luminance(color_b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def hue_to_hex(hue_degrees: float) -> str:
    """色相から記号の背景色を作る。文字色とのコントラストが足りない色相は明度を下げて満たす。"""
    lightness = _SYMBOL_LIGHTNESS
    color = _hls_hex(hue_degrees, lightness)
    while contrast_ratio(color, _SYMBOL_TEXT_COLOR) < _MIN_CONTRAST and lightness > _MIN_LIGHTNESS:
        lightness = round(lightness - 0.01, 2)
        color = _hls_hex(hue_degrees, lightness)
    return color
