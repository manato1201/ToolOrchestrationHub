@echo off
rem ToolOrchestrationHub を起動して、Edge のアプリ窓で開く(ダブルクリック用)。詳細は tools\start_hub.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_hub.ps1" %*
