param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$datasetDir = Join-Path $projectDir 'Dataset-VRP'
$runner = Join-Path $projectDir 'run_experiments.py'
$ablationRoot = Join-Path $projectDir 'benchmark_results\ablations'

$instances = @(Get-ChildItem -LiteralPath $datasetDir -File -Filter '*.vrp' |
    Where-Object { $_.Name -notlike 'XL-*' } |
    Sort-Object Name |
    ForEach-Object { $_.Name })
if ($instances.Count -ne 30) {
    throw "Expected 30 paper instances, found $($instances.Count)"
}

$configurations = @(
    @{
        Name = 'alns_only'
        Extra = @('--search-mode', 'alns_only')
    },
    @{
        Name = 'recombination_only'
        Extra = @(
            '--search-mode', 'recombination_only',
            '--fixed-removal', '--fixed-operator-weights'
        )
    },
    @{
        Name = 'full_fixed_penalty'
        Extra = @('--search-mode', 'full', '--fixed-penalty')
    },
    @{
        Name = 'full_fixed_removal'
        Extra = @('--search-mode', 'full', '--fixed-removal')
    },
    @{
        Name = 'full_fixed_operator_weights'
        Extra = @('--search-mode', 'full', '--fixed-operator-weights')
    }
)

foreach ($configuration in $configurations) {
    $outputDir = Join-Path $ablationRoot $configuration.Name
    $arguments = @('-u', $runner) + $instances + @(
        '--seeds', '1-10',
        '--output-dir', $outputDir,
        '--resume'
    ) + $configuration.Extra
    Write-Output "Starting ablation $($configuration.Name)"
    & $PythonExe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Ablation $($configuration.Name) failed with exit code $LASTEXITCODE"
    }
}

Write-Output 'All ablation batches completed successfully.'
