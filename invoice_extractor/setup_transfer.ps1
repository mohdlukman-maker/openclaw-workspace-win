param(
    [switch]$RegisterTask,
    [switch]$CreateTransferZip
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "python"
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$EnvPath = Join-Path $ProjectDir ".env"
$EnvExamplePath = Join-Path $ProjectDir ".env.example"

Set-Location $ProjectDir

if (-not (Test-Path $VenvPython)) {
    & $Python -m venv .venv
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

if (-not (Test-Path $EnvPath)) {
    Copy-Item -Path $EnvExamplePath -Destination $EnvPath
    Write-Host "Created .env from .env.example. Edit .env before starting the bot."
}

New-Item -ItemType Directory -Force -Path `
    (Join-Path $ProjectDir "data\images"), `
    (Join-Path $ProjectDir "data\enhanced"), `
    (Join-Path $ProjectDir "data\extractions"), `
    (Join-Path $ProjectDir "data\ocr"), `
    (Join-Path $ProjectDir "data\pending"), `
    (Join-Path $ProjectDir "data\cleanup_archive"), `
    (Join-Path $ProjectDir "logs") | Out-Null

& $VenvPython -m py_compile invoice_bot.py procurement.py pending_store.py retention.py suppliers.py
& $VenvPython -m unittest discover -s tests -v
& $VenvPython invoice_bot.py --init-workbook

if ($RegisterTask) {
    $TaskName = "Invoice Extractor Bot"
    $Action = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$ProjectDir\invoice_bot.py`"" -WorkingDirectory $ProjectDir
    $Trigger = New-ScheduledTaskTrigger -AtLogOn
    $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Registered and started scheduled task: $TaskName"
}

if ($CreateTransferZip) {
    $PackageDir = Join-Path $ProjectDir "transfer_packages"
    $StageDir = Join-Path $PackageDir "_stage_invoice_extractor"
    $ZipPath = Join-Path $PackageDir ("invoice_extractor_transfer_{0}.zip" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
    New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null
    if (Test-Path $StageDir) {
        Remove-Item -Recurse -Force -Path $StageDir
    }
    New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

    Get-ChildItem -Path $ProjectDir -Recurse -File -Force |
        Where-Object {
            $relative = [System.IO.Path]::GetRelativePath($ProjectDir, $_.FullName)
            $parts = $relative -split '[\\/]'
            $_.Name -ne ".env" -and
                $parts -notcontains "logs" -and
                $parts -notcontains "__pycache__" -and
                $parts -notcontains "transfer_packages" -and
                $parts -notcontains ".venv"
        } |
        ForEach-Object {
            $relative = [System.IO.Path]::GetRelativePath($ProjectDir, $_.FullName)
            $target = Join-Path $StageDir $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -Path $_.FullName -Destination $target
        }

    Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
    Remove-Item -Recurse -Force -Path $StageDir
    Write-Host "Created transfer package: $ZipPath"
}

Write-Host "Invoice Extractor transfer setup complete."
