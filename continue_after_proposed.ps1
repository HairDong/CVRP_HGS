param(
    [Parameter(Mandatory = $true)]
    [int]$ProposedProcessId,

    [Parameter(Mandatory = $true)]
    [string]$PythonExe,

    [Parameter(Mandatory = $true)]
    [string]$HgsExe
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$datasetDir = Join-Path $projectDir 'Dataset-VRP'
$proposedDir = Join-Path $projectDir 'benchmark_results\paper_proposed_adaptive'
$proposedRuns = Join-Path $proposedDir 'runs.csv'
$vidalDir = Join-Path $projectDir 'benchmark_results\paper_vidal_hgs'
$vidalSmokeDir = Join-Path $projectDir 'benchmark_results\vidal_smoke'

Write-Output "Waiting for Proposed PID $ProposedProcessId"
Wait-Process -Id $ProposedProcessId -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $proposedRuns)) {
    throw "Proposed runs file was not created: $proposedRuns"
}

$proposedRows = @(Import-Csv -LiteralPath $proposedRuns)
$proposedErrors = @($proposedRows | Where-Object {
    $_.status -ne 'ok' -or $_.feasible -ne 'True'
})
if ($proposedRows.Count -ne 300 -or $proposedErrors.Count -ne 0) {
    throw "Proposed batch incomplete: rows=$($proposedRows.Count), errors=$($proposedErrors.Count). Vidal was not started."
}

$instances = @(Get-ChildItem -LiteralPath $datasetDir -File -Filter '*.vrp' |
    Where-Object { $_.Name -notlike 'XL-*' } |
    Sort-Object Name |
    ForEach-Object { $_.Name })
if ($instances.Count -ne 30) {
    throw "Expected 30 paper instances, found $($instances.Count)"
}

Write-Output 'Running one-second Vidal smoke test'
& $PythonExe -u (Join-Path $projectDir 'run_vidal_experiments.py') `
    'A-n32-k5.vrp' `
    '--hgs-exe' $HgsExe `
    '--seeds' '1' `
    '--time-limit' '1' `
    '--output-dir' $vidalSmokeDir
if ($LASTEXITCODE -ne 0) {
    throw "Vidal smoke test failed with exit code $LASTEXITCODE"
}

Write-Output 'Starting matched 30-instance x 10-seed Vidal batch'
& $PythonExe -u (Join-Path $projectDir 'run_vidal_experiments.py') `
    @instances `
    '--hgs-exe' $HgsExe `
    '--seeds' '1-10' `
    '--output-dir' $vidalDir `
    '--resume'
if ($LASTEXITCODE -ne 0) {
    throw "Vidal batch failed with exit code $LASTEXITCODE"
}

Write-Output 'Starting sequential ablation batches'
& (Join-Path $projectDir 'run_ablations.ps1') -PythonExe $PythonExe
if ($LASTEXITCODE -ne 0) {
    throw "Ablation pipeline failed with exit code $LASTEXITCODE"
}

Write-Output 'Proposed, Vidal, and ablation batches completed successfully.'
