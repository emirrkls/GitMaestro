# Qwen 3.5 / 3.6 families on Ollama (newer than qwen2.5-coder / qwen3-coder).
# Tags and sizes change — see https://ollama.com/library/qwen3.5/tags and .../qwen3.6/tags
# Disk-heavy: comment out lines you do not need before running.
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
  # ~6.6GB — default "latest" multimodal line (good first experiment)
  "qwen3.5:latest",
  # ~22GB — MoE coding-focused (stronger for patches / JSON; needs VRAM + disk)
  "qwen3.5:35b-a3b-coding-nvfp4",
  # ~20GB — Qwen3.6 coding variant (newer agentic-coding line per Ollama listing)
  "qwen3.6:27b-coding-nvfp4"
)
foreach ($m in $models) {
  Write-Host "Pulling $m ..."
  & $ollamaExe pull $m
}
