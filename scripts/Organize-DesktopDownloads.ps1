param(
    [switch]$DryRun,
    [int]$MinimumAgeHours = 24
)

$ErrorActionPreference = 'Stop'

$Workspace = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Workspace 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$RunStamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$LogPath = Join-Path $LogDir "folder-organizer-$RunStamp.log"
$Cutoff = (Get-Date).AddHours(-1 * $MinimumAgeHours)

function Write-OrganizerLog {
    param([string]$Message)
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $LogPath -Value $line
    Write-Output $line
}

function Get-ExpandedUserShellFolder {
    param([string]$Name)
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
    $value = (Get-ItemProperty -LiteralPath $key).$Name
    if (-not $value) { return $null }
    return [Environment]::ExpandEnvironmentVariables($value)
}

function Ensure-Folder {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        if ($DryRun) {
            Write-OrganizerLog "DRYRUN create folder: $Path"
        } else {
            New-Item -ItemType Directory -Force -Path $Path | Out-Null
            Write-OrganizerLog "Created folder: $Path"
        }
    }
}

function Get-UniqueDestination {
    param(
        [string]$Directory,
        [string]$FileName
    )

    $destination = Join-Path $Directory $FileName
    if (-not (Test-Path -LiteralPath $destination)) { return $destination }

    $base = [IO.Path]::GetFileNameWithoutExtension($FileName)
    $extension = [IO.Path]::GetExtension($FileName)
    $i = 1
    do {
        $candidateName = '{0} ({1}){2}' -f $base, $i, $extension
        $destination = Join-Path $Directory $candidateName
        $i++
    } while (Test-Path -LiteralPath $destination)

    return $destination
}

function Test-FileNameLike {
    param(
        [IO.FileInfo]$File,
        [string[]]$Patterns
    )

    $text = ($File.BaseName + ' ' + $File.Extension).ToLowerInvariant()
    foreach ($pattern in $Patterns) {
        if ($text -match $pattern) { return $true }
    }
    return $false
}

function Get-DownloadsCategory {
    param([IO.FileInfo]$File)

    $ext = $File.Extension.ToLowerInvariant()

    if (Test-FileNameLike $File @('hpj', 'construction', 'tender', 'drawing', 'boq', 'rfi', 'site', 'tapak', 'mesyuarat', 'minit', 'petra', 'medical equipment')) {
        return '03 Construction Engineering HPJ'
    }
    if (Test-FileNameLike $File @('invoice', 'receipt', 'bank', 'statement', 'tax', 'finance', 'trading', 'payment')) {
        return '11 Finance Trading'
    }
    if (Test-FileNameLike $File @('thesis', 'assignment', 'research', 'journal', 'paper', 'academic')) {
        return '01 Academic - Thesis Research Assignments'
    }
    if (Test-FileNameLike $File @('project management', 'course', 'pmp', 'schedule', 'wbs')) {
        return '02 Project Management Course Materials'
    }
    if (Test-FileNameLike $File @('business', 'marketing', 'airasia', 'zus', 'brand', 'campaign')) {
        return '04 Business Marketing AirAsia ZUS'
    }
    if (Test-FileNameLike $File @('book', 'ebook', 'reference', 'manual', 'guide')) {
        return '05 Books References'
    }

    switch ($ext) {
        { $_ -in '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.svg', '.psd', '.ai', '.fig', '.skp', '.layout' } {
            return '07 Images Design Assets'
        }
        { $_ -in '.mp3', '.wav', '.m4a', '.flac', '.aac', '.mp4', '.mov', '.mkv', '.avi', '.wmv', '.srt', '.vtt' } {
            return '06 Media Recordings Subtitles'
        }
        { $_ -in '.zip', '.rar', '.7z', '.tar', '.gz', '.iso' } {
            return '09 Archives Compressed'
        }
        { $_ -in '.exe', '.msi', '.msix', '.appx', '.apk', '.dmg' } {
            return '08 Software Installers'
        }
        { $_ -in '.html', '.htm', '.css', '.js', '.ts', '.json', '.xml', '.csv', '.sql', '.py', '.ipynb', '.php', '.java', '.cs', '.cpp', '.zipx' } {
            return '10 Web Code Data'
        }
        { $_ -in '.doc', '.docx', '.pdf', '.ppt', '.pptx', '.txt', '.rtf', '.odt' } {
            return 'Documents'
        }
        { $_ -in '.xls', '.xlsx', '.xlsm', '.ods' } {
            return 'Documents'
        }
        default {
            return '99 Needs Review'
        }
    }
}

function Get-DesktopCategory {
    param([IO.FileInfo]$File)

    $ext = $File.Extension.ToLowerInvariant()

    if ($ext -eq '.lnk') { return $null }
    if ($ext -in '.zip', '.rar', '.7z', '.tar', '.gz', '.iso') { return '4. ARCHIVES' }
    if (Test-FileNameLike $File @('project', 'hpj', 'construction', 'tender', 'drawing', 'boq', 'rfi', 'site', 'tapak', 'mesyuarat', 'minit', 'petra')) {
        return '1. PROJECTS'
    }
    if (Test-FileNameLike $File @('finance', 'trading', 'invoice', 'receipt', 'tax', 'bank', 'health', 'admin')) {
        return '2. AREAS'
    }

    return '3. RESOURCES'
}

function Organize-RootFiles {
    param(
        [string]$Root,
        [scriptblock]$CategoryResolver,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        Write-OrganizerLog "Skipped missing $Label path: $Root"
        return
    }

    Write-OrganizerLog "Scanning $Label root: $Root"

    Get-ChildItem -LiteralPath $Root -File -Force | ForEach-Object {
        $file = $_

        if (($file.Attributes -band [IO.FileAttributes]::Hidden) -or ($file.Attributes -band [IO.FileAttributes]::System)) {
            Write-OrganizerLog "Skipped hidden/system file: $($file.FullName)"
            return
        }
        if ($file.LastWriteTime -gt $Cutoff) {
            Write-OrganizerLog "Skipped recent file: $($file.FullName)"
            return
        }
        if ($file.Name -in 'desktop.ini', 'Thumbs.db') {
            Write-OrganizerLog "Skipped protected shell file: $($file.FullName)"
            return
        }

        $category = & $CategoryResolver $file
        if (-not $category) {
            Write-OrganizerLog "Skipped by rule: $($file.FullName)"
            return
        }

        $targetDir = Join-Path $Root $category
        Ensure-Folder $targetDir
        $destination = Get-UniqueDestination -Directory $targetDir -FileName $file.Name

        if ($DryRun) {
            Write-OrganizerLog "DRYRUN move: $($file.FullName) -> $destination"
        } else {
            Move-Item -LiteralPath $file.FullName -Destination $destination
            Write-OrganizerLog "Moved: $($file.FullName) -> $destination"
        }
    }
}

$desktop = Get-ExpandedUserShellFolder 'Desktop'
$downloads = Get-ExpandedUserShellFolder '{374DE290-123F-4565-9164-39C4925E467B}'

Write-OrganizerLog "Folder organizer started. DryRun=$DryRun MinimumAgeHours=$MinimumAgeHours"
Organize-RootFiles -Root $desktop -CategoryResolver ${function:Get-DesktopCategory} -Label 'Desktop'
Organize-RootFiles -Root $downloads -CategoryResolver ${function:Get-DownloadsCategory} -Label 'Downloads'
Write-OrganizerLog "Folder organizer finished. Log=$LogPath"
