param(
    [Parameter(Mandatory = $true)]
    [int]$ProposedProcessId,

    [Parameter(Mandatory = $true)]
    [int]$VidalProcessId,

    [Parameter(Mandatory = $true)]
    [string]$PythonExe
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$resultRoot = Join-Path $projectDir 'benchmark_results'
$proposedRuns = Join-Path $resultRoot 'paper_exact_v2_seed2\runs.csv'
$vidalRuns = Join-Path $resultRoot 'paper_exact_vidal_seed2\runs.csv'
$outputDir = Join-Path $resultRoot 'paper_merged_exact_seed2'

Write-Output "Waiting for Proposed PID $ProposedProcessId and Vidal PID $VidalProcessId"
Wait-Process -Id $ProposedProcessId -ErrorAction SilentlyContinue
Wait-Process -Id $VidalProcessId -ErrorAction SilentlyContinue

$proposed = @(Import-Csv -LiteralPath $proposedRuns)
$vidal = @(Import-Csv -LiteralPath $vidalRuns)
$proposedOk = @($proposed | Where-Object { $_.status -eq 'ok' -and $_.feasible -eq 'True' })
$vidalOk = @($vidal | Where-Object { $_.status -eq 'ok' -and $_.feasible -eq 'True' })
if ($proposedOk.Count -ne 30 -or $vidalOk.Count -ne 30) {
    throw "Incomplete exact runs: Proposed=$($proposedOk.Count)/30, Vidal=$($vidalOk.Count)/30"
}

& $PythonExe (Join-Path $projectDir 'make_merged_paper_table.py') `
    '--references' (Join-Path $projectDir 'paper_reference_values.csv') `
    '--proposed-runs' $proposedRuns `
    '--vidal-runs' $vidalRuns `
    '--seed' '2' `
    '--output-dir' $outputDir `
    '--title' 'Merged comparison under the paper time limits (seed 2)'
if ($LASTEXITCODE -ne 0) {
    throw "Table generation failed with exit code $LASTEXITCODE"
}
Write-Output "Merged table completed: $outputDir"
