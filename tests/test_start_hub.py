"""tools/start_hub.ps1 の「Unsloth とセット」(-WithUnsloth)。-DryRun は何も起動しないので、やることの表示だけを確かめる。"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "start_hub.ps1"

pytestmark = pytest.mark.skipif(sys.platform != "win32" or shutil.which("powershell") is None, reason="PowerShell(Windows)が要る")


def run(*args: str) -> str:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-DryRun", "-NoWindow", "-Port", "18790", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_without_the_switch_nothing_about_unsloth_happens():
    out = run()
    assert "Unsloth" not in out and "llh autostart" not in out


def test_with_unsloth_starts_unsloth_and_the_watcher(tmp_path):
    exe = tmp_path / "unsloth-studio.exe"
    exe.write_bytes(b"")
    llh = tmp_path / "LocalLLMHarness"
    llh.mkdir()
    out = run("-WithUnsloth", "-UnslothPath", str(exe), "-LlhDir", str(llh))
    assert f"[dry-run] start Unsloth Desktop: {exe}" in out
    assert "[dry-run] start: uv run llh autostart" in out and str(llh) in out
    assert out.index("start Unsloth Desktop") < out.index("llh autostart"), "Unsloth を先に開く"


def test_missing_unsloth_or_harness_is_skipped_not_fatal(tmp_path):
    out = run("-WithUnsloth", "-UnslothPath", str(tmp_path / "nope.exe"), "-LlhDir", str(tmp_path / "nope"))
    assert "Unsloth Desktop not found" in out and "LocalLLMHarness not found" in out
    assert "[dry-run] start Unsloth Desktop" not in out and "llh autostart" not in out.replace("LocalLLMHarness not found", "")


def test_shortcut_name_and_arguments_follow_the_switch():
    plain = run("-InstallShortcut")
    assert "ToolOrchestrationHub.lnk" in plain and "+ Unsloth" not in plain
    both = run("-InstallShortcut", "-WithUnsloth", "-UnslothPath", "x.exe", "-LlhDir", "x")
    assert "ToolOrchestrationHub + Unsloth.lnk" in both
