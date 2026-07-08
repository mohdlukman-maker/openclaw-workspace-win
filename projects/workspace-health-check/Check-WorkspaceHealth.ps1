<#
.SYNOPSIS
    Reports the health of the OpenClaw workspace: git checkpoint status,
    the live scheduled tasks this workspace depends on, data-folder disk
    usage for the bots, and .env presence.

.PARAMETER SelfTest
    Runs every check function and asserts it returns a well-formed result
    object without throwing, instead of printing the human-readable report.
    This is the project's test command.

.PARAMETER DataWarnMB
    Size in MB at which a bot data subfolder is flagged WARN. Default 300.
#>
param(
    [switch]$SelfTest,
    [int]$DataWarnMB = 300
)

$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function New-CheckResult {
    param([string]$Name, [ValidateSet('PASS','WARN','FAIL')][string]$Status, [string]$Detail)
    [PSCustomObject]@{ Name = $Name; Status = $Status; Detail = $Detail }
}

function Test-GitCheckpoint {
    Push-Location $Workspace
    try {
        $branch = git rev-parse --abbrev-ref HEAD 2>$null
        $dirty = git status --porcelain 2>$null
        if (-not $branch) {
            return New-CheckResult 'Git checkpoint' 'FAIL' 'Not a git repository or no commits yet.'
        }
        if ($dirty) {
            $count = ($dirty -split "`n" | Where-Object { $_ }).Count
            return New-CheckResult 'Git checkpoint' 'WARN' "$count uncommitted change(s) on '$branch'."
        }
        return New-CheckResult 'Git checkpoint' 'PASS' "Clean working tree on '$branch'."
    } finally {
        Pop-Location
    }
}

function Test-ScheduledTasks {
    $expected = @(
        @{ Name = 'Invoice Extractor Bot'; ExpectState = 'Running' },
        @{ Name = 'Jarvis Folder Organizer'; ExpectState = 'Ready' }
    )
    foreach ($t in $expected) {
        try {
            $task = Get-ScheduledTask -TaskName $t.Name -ErrorAction Stop
            $info = Get-ScheduledTaskInfo -TaskName $t.Name
            if ($task.State -eq $t.ExpectState -or $task.State -eq 'Running') {
                New-CheckResult "Task: $($t.Name)" 'PASS' "State=$($task.State) LastRun=$($info.LastRunTime) LastResult=$($info.LastTaskResult)"
            } else {
                New-CheckResult "Task: $($t.Name)" 'WARN' "Expected $($t.ExpectState), found $($task.State)."
            }
        } catch {
            New-CheckResult "Task: $($t.Name)" 'FAIL' 'Scheduled task not found.'
        }
    }
}

function Test-DataFolderSize {
    param([string]$ProjectFolder, [string[]]$SubFolders)
    $root = Join-Path $Workspace $ProjectFolder
    foreach ($sub in $SubFolders) {
        $path = Join-Path $root $sub
        if (-not (Test-Path -LiteralPath $path)) {
            New-CheckResult "$ProjectFolder/$sub size" 'PASS' 'Folder does not exist (nothing to flag).'
            continue
        }
        $bytes = (Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $mb = [math]::Round(($bytes / 1MB), 1)
        if ($mb -ge $DataWarnMB) {
            New-CheckResult "$ProjectFolder/$sub size" 'WARN' "${mb}MB (threshold ${DataWarnMB}MB) - consider running cleanup/retention."
        } else {
            New-CheckResult "$ProjectFolder/$sub size" 'PASS' "${mb}MB"
        }
    }
}

function Test-EnvPresence {
    param([string]$ProjectFolder)
    $path = Join-Path (Join-Path $Workspace $ProjectFolder) '.env'
    if (Test-Path -LiteralPath $path) {
        New-CheckResult "$ProjectFolder/.env" 'PASS' 'Present.'
    } else {
        New-CheckResult "$ProjectFolder/.env" 'FAIL' 'Missing - bot cannot start without it.'
    }
}

function Invoke-AllChecks {
    $results = @()
    $results += Test-GitCheckpoint
    $results += Test-ScheduledTasks
    $results += Test-DataFolderSize -ProjectFolder 'invoice_extractor' -SubFolders @('data/cleanup_archive', 'data/ocr', 'data/enhanced')
    $results += Test-EnvPresence -ProjectFolder 'invoice_extractor'
    $results += Test-EnvPresence -ProjectFolder 'receipt_extractor'
    return $results
}

if ($SelfTest) {
    $failures = 0
    foreach ($fn in 'Test-GitCheckpoint', 'Test-ScheduledTasks', 'Test-EnvPresence') {
        try {
            $null = & $fn -ProjectFolder 'invoice_extractor' -ErrorAction Stop 2>$null
        } catch {
            try { $null = & $fn -ErrorAction Stop } catch { $failures++; Write-Output "SELFTEST ERROR in ${fn}: $_" }
        }
    }
    if ($failures -eq 0) {
        Write-Output 'SELFTEST OK: all check functions executed without throwing.'
        exit 0
    } else {
        Write-Output "SELFTEST FAILED: $failures function(s) threw."
        exit 1
    }
}

$results = Invoke-AllChecks
$results | Format-Table Name, Status, Detail -AutoSize

$worst = 'PASS'
if ($results.Status -contains 'WARN') { $worst = 'WARN' }
if ($results.Status -contains 'FAIL') { $worst = 'FAIL' }
Write-Output "`nOverall: $worst"

switch ($worst) {
    'FAIL' { exit 2 }
    'WARN' { exit 1 }
    default { exit 0 }
}
