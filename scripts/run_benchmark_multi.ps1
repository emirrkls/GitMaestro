# Run MaestroComparisonTests issues 1-8 (multi-agent). Logs to runs/benchmark_multi_batch.log
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$line = Get-Content (Join-Path $RepoRoot ".env") -ErrorAction SilentlyContinue | Where-Object { $_ -match '^GITHUB_TOKEN=' } | Select-Object -First 1
if ($line) { $env:GITHUB_TOKEN = $line.Split('=', 2)[1].Trim() }

$LogFile = Join-Path $RepoRoot "runs\benchmark_multi_batch.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

Log "=== Benchmark multi-agent batch start ==="
$results = @()

foreach ($n in 1..8) {
    Log "--- Issue $n start ---"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $out = python -m maestro run --repo emirrkls/MaestroComparisonTests --issue $n --config config.ollama.yaml 2>&1
        $code = $LASTEXITCODE
        $out | ForEach-Object { Log "  $_" }
    } catch {
        $code = 1
        Log "  EXCEPTION: $_"
    }
    $sw.Stop()
    $taskId = ($out | Where-Object { $_ -match '\[maestro\] task_id=' }) -replace '.*task_id=', '' | Select-Object -First 1
    $runDir = ($out | Where-Object { $_ -match '\[maestro\] run_dir=' }) -replace '.*run_dir=', '' | Select-Object -First 1
    Log "--- Issue $n done exit=$code elapsed=$([int]$sw.Elapsed.TotalSeconds)s task_id=$taskId ---"
    $results += [PSCustomObject]@{ Issue = $n; Exit = $code; Seconds = [int]$sw.Elapsed.TotalSeconds; TaskId = $taskId; RunDir = $runDir }
}

Log "=== Summary ==="
$results | ForEach-Object { Log ("Issue {0}: exit={1} seconds={2} task_id={3}" -f $_.Issue, $_.Exit, $_.Seconds, $_.TaskId) }
Log "=== Batch complete ==="
