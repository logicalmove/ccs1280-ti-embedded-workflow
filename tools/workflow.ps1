[CmdletBinding()]
param(
    [ValidateSet('plan', 'build', 'verify', 'test')]
    [string]$Action = 'build',
    [ValidateSet('small', 'big', 'both')]
    [string]$Target = 'small',
    [switch]$Force,
    [string]$Python = 'python',
    [string]$CompilerRoot = 'C:\ti\ccs1280\ccs\tools\compiler\ti-cgt-c2000_22.6.1.LTS',
    [string]$DeviceHeaders,
    [string]$DeviceCommon,
    [string]$DeviceLib
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$engineering = Join-Path $PSScriptRoot 'engineering.py'
$workflowLogDir = Join-Path $root 'build\workflow'
New-Item -ItemType Directory -Force -Path $workflowLogDir | Out-Null

function Invoke-Checked {
    param([string[]]$Arguments)
    & $Python @Arguments 2>&1 | Tee-Object -FilePath $script:logPath
    if ($LASTEXITCODE -ne 0) {
        throw "WORKFLOW_FAILED: python exit code $LASTEXITCODE; log=$script:logPath"
    }
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$script:logPath = Join-Path $workflowLogDir "$stamp`_$Action`_$Target.log"
$engineeringAction = if ($Action -eq 'plan') { 'build' } else { $Action }
$common = @($engineering, $engineeringAction, '--target', $Target,
    '--compiler-root', $CompilerRoot)
if ($DeviceHeaders) { $common += @('--device-headers', $DeviceHeaders) }
if ($DeviceCommon) { $common += @('--device-common', $DeviceCommon) }
if ($DeviceLib) { $common += @('--device-lib', $DeviceLib) }

try {
    switch ($Action) {
        'plan' {
            Invoke-Checked ($common + '--plan')
        }
        'build' {
            $arguments = $common
            if ($Force) { $arguments += '--force' }
            Invoke-Checked $arguments
        }
        'verify' {
            Invoke-Checked $common
        }
        'test' {
            $test = Join-Path $root 'tests\test_engineering.py'
            $stdout = "$script:logPath.stdout"
            $stderr = "$script:logPath.stderr"
            $process = Start-Process -FilePath $Python -ArgumentList @($test) -Wait -NoNewWindow -PassThru `
                -RedirectStandardOutput $stdout -RedirectStandardError $stderr
            Get-Content -LiteralPath $stdout, $stderr -ErrorAction SilentlyContinue | Tee-Object -FilePath $script:logPath
            Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
            if ($process.ExitCode -ne 0) {
                throw "WORKFLOW_FAILED: offline tests exit code $($process.ExitCode); log=$script:logPath"
            }
        }
    }
    Write-Output "RESULT:WORKFLOW_OK|ACTION:$Action|TARGET:$Target|LOG:$script:logPath|FLASH:NOT_PERFORMED"
    exit 0
}
catch {
    Write-Error $_
    Write-Output "RESULT:WORKFLOW_FAIL|ACTION:$Action|TARGET:$Target|LOG:$script:logPath|FLASH:NOT_PERFORMED"
    exit 1
}
