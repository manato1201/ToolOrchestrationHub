<#
.SYNOPSIS
  ToolOrchestrationHub を起動して、Edge のアプリ窓(アドレスバーの無い専用ウィンドウ)で開く。

.DESCRIPTION
  - すでに Hub が動いていれば、起動し直さず、窓だけ開く。
  - 動いていなければ、`uv run hub` を最小化したコンソールで起動し、応答するまで待ってから窓を開く。
    (コンソールはタスクバーに残る。Hub を終わらせるときは、そのコンソールを閉じる)
  - Edge が無ければ、既定のブラウザで開く。
  - -InstallShortcut を付けると、デスクトップにショートカットを 1 つ作る(付けなければ、何も作らない)。
  - -DryRun は、何も起動せず、やることだけ表示する。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\start_hub.ps1
  powershell -ExecutionPolicy Bypass -File tools\start_hub.ps1 -InstallShortcut
#>
param(
  [int]$Port = 8790,
  [int]$WaitSeconds = 40,
  [switch]$NoWindow,
  [switch]$InstallShortcut,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Url = "http://127.0.0.1:$Port/"

function Test-Hub {
  try { $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2; return $true } catch { return $false }
}

function Find-Edge {
  $candidates = @(
    "$env:ProgramFiles (x86)\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
  )
  foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
  return $null
}

if ($InstallShortcut) {
  $target = Join-Path $PSScriptRoot "start_hub.ps1"
  $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "ToolOrchestrationHub.lnk"
  if ($DryRun) { Write-Host "[dry-run] create shortcut: $lnk" }
  else {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = "powershell.exe"
    $sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$target`" -Port $Port"
    $sc.WorkingDirectory = $Root
    # アイコンは Edge のものにする(既定のままだと PowerShell の青いアイコンになり、タスクバーで見分けにくい)
    $edgeForIcon = Find-Edge
    if ($edgeForIcon) { $sc.IconLocation = "$edgeForIcon,0" }
    $sc.Description = "ToolOrchestrationHub を起動して開く"
    $sc.Save()
    Write-Host "created: $lnk"
  }
}

$running = Test-Hub
if ($running) {
  Write-Host "Hub is already running: $Url"
} elseif ($DryRun) {
  Write-Host "[dry-run] start: uv run hub --port $Port  (cwd: $Root, minimized)"
} else {
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not on PATH. Install uv first (https://docs.astral.sh/uv/)."
  }
  $proc = Start-Process -FilePath "uv" -ArgumentList @("run", "hub", "--port", "$Port") -WorkingDirectory $Root -WindowStyle Minimized -PassThru
  Write-Host "starting Hub (console pid $($proc.Id)) ..."
  $deadline = (Get-Date).AddSeconds($WaitSeconds)
  while (-not (Test-Hub)) {
    if ($proc.HasExited) { Write-Error "Hub exited while starting (exit code $($proc.ExitCode)). Run 'uv run hub' in a terminal to see the error." }
    if ((Get-Date) -gt $deadline) { Write-Error "Hub did not respond within $WaitSeconds seconds. Check the minimized console window." }
    Start-Sleep -Milliseconds 500
  }
  Write-Host "Hub is up: $Url"
}

Write-Host "(To stop the Hub, close its minimized console window. Closing the app window leaves the Hub running.)"
if ($NoWindow) { return }
$edge = Find-Edge
if ($DryRun) {
  if ($edge) { Write-Host "[dry-run] open app window: msedge --app=$Url" } else { Write-Host "[dry-run] open default browser: $Url" }
} elseif ($edge) {
  Start-Process -FilePath $edge -ArgumentList @("--app=$Url")
} else {
  Start-Process $Url
}
