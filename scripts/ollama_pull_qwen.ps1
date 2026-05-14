# Suggested Qwen / coder models for GitMaestro (Ollama). Run from repo root or any directory.
# For Qwen 3.5 / 3.6 families see also: .\scripts\ollama_pull_qwen_nextgen.ps1
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
  "qwen2.5-coder:7b",
  "qwen2.5-coder:14b",
  "qwen3-coder:latest",
  "qwen3-coder:30b"
)
foreach ($m in $models) {
  Write-Host "Pulling $m ..."
  & $ollamaExe pull $m
}
