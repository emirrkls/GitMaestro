# Targets ~12 GB VRAM (RTX 3060 class) + modest RAM; avoids huge MoE/BF16 pulls.
# Resolves ollama.exe from PATH or %LOCALAPPDATA%\Programs\Ollama\ollama.exe
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\OllamaPath.ps1"
$ollamaExe = Resolve-OllamaExecutable
if (-not $ollamaExe) {
    Write-Error "ollama.exe not found. Install from https://ollama.com/download or add Ollama to PATH."
    exit 1
}
Write-Host "Using: $ollamaExe"
$models = @(
  "qwen3.5:latest",
  "qwen2.5-coder:7b",
  "qwen2.5-coder:14b"
)
foreach ($m in $models) {
  Write-Host "Pulling $m ..."
  & $ollamaExe pull $m
}
