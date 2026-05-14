# Dot-source from other scripts: . "$PSScriptRoot\OllamaPath.ps1"
function Resolve-OllamaExecutable {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    foreach ($candidate in @(
            (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
            "${env:ProgramFiles}\Ollama\ollama.exe"
        )) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}
