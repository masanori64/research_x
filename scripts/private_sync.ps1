param(
    [ValidateSet("Plan", "Copy")]
    [string]$Mode = "Plan",

    [string]$SourceHost = "",
    [string]$ResearchShare = "research-x-raw",
    [string]$CodexShare = "codex-home-raw",
    [string]$SourceResearchRoot = "",
    [string]$SourceCodexHome = "",

    [string]$DestinationResearchRoot = (Get-Location).Path,
    [string]$DestinationCodexHome = (Join-Path $env:USERPROFILE ".codex"),

    [ValidateSet("Secrets", "Env", "CodexHome", "RunDb", "Runs")]
    [string[]]$Items = @("Secrets", "CodexHome", "RunDb"),

    [switch]$BackupDestination,
    [switch]$ReplaceCodexHome,
    [int]$Threads = 16
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-PrivateSyncPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }
    if ($Path -like "\\*") {
        return $Path.TrimEnd("\")
    }
    return [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
}

function Assert-NotHostedPath {
    param([string]$Path, [string]$Label)
    if ($Path -match "^(?i:https?://|git@|ssh://)" -or $Path -match "(?i)github\.com") {
        throw "$Label must be a local, UNC, or drive path. Do not use GitHub for private sync."
    }
}

function Assert-SafeDestination {
    param([string]$Path, [string]$Label)
    $full = Resolve-PrivateSyncPath $Path
    if ([string]::IsNullOrWhiteSpace($full)) {
        throw "$Label is empty."
    }
    $profile = [System.IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd("\")
    if (-not $full.StartsWith($profile, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must stay under USERPROFILE: $full"
    }
    if ($full -ieq $profile) {
        throw "$Label must not be USERPROFILE itself."
    }
}

function New-BackupRoot {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $root = Join-Path $env:USERPROFILE "research_x_private_sync_backups"
    $backup = Join-Path $root $stamp
    if ($Mode -eq "Copy") {
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
    }
    return $backup
}

function Invoke-RobocopyChecked {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$FileName = "",
        [int]$ThreadCount = 16
    )

    Assert-NotHostedPath $Source "Source"
    Assert-NotHostedPath $Destination "Destination"

    $args = @($Source, $Destination)
    if (-not [string]::IsNullOrWhiteSpace($FileName)) {
        $args += $FileName
    }
    $args += @("/COPY:DAT", "/DCOPY:DAT", "/XJ", "/R:2", "/W:2", "/NFL", "/NDL", "/NP")
    if ([string]::IsNullOrWhiteSpace($FileName)) {
        $args += "/E"
    }
    if ($ThreadCount -gt 1 -and [string]::IsNullOrWhiteSpace($FileName)) {
        $args += "/MT:$ThreadCount"
    }
    if ($Mode -eq "Plan") {
        $args += "/L"
    }

    $displayFile = ""
    if (-not [string]::IsNullOrWhiteSpace($FileName)) {
        $displayFile = " $FileName"
    }
    Write-Host "robocopy $Source -> $Destination$displayFile"
    & robocopy @args
    $exit = $LASTEXITCODE
    if ($exit -ge 8) {
        throw "robocopy failed with exit code $exit"
    }
    Write-Host "robocopy exit code: $exit"
}

function Backup-ExistingPath {
    param([string]$Path, [string]$BackupRoot, [string]$Name)
    if (-not $BackupDestination) {
        return
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $target = Join-Path $BackupRoot $Name
    if ($Mode -eq "Plan") {
        Write-Host "backup plan: $Path -> $target"
        return
    }
    if ((Get-Item -LiteralPath $Path).PSIsContainer) {
        Invoke-RobocopyChecked -Source $Path -Destination $target -ThreadCount $Threads
    } else {
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $Path -Destination $target -Force
        Write-Host "backed up file: $Name"
    }
}

if ([string]::IsNullOrWhiteSpace($SourceResearchRoot) -and -not [string]::IsNullOrWhiteSpace($SourceHost)) {
    $SourceResearchRoot = "\\$SourceHost\$ResearchShare"
}
if ([string]::IsNullOrWhiteSpace($SourceCodexHome) -and -not [string]::IsNullOrWhiteSpace($SourceHost)) {
    $SourceCodexHome = "\\$SourceHost\$CodexShare"
}

$SourceResearchRoot = Resolve-PrivateSyncPath $SourceResearchRoot
$SourceCodexHome = Resolve-PrivateSyncPath $SourceCodexHome
$DestinationResearchRoot = Resolve-PrivateSyncPath $DestinationResearchRoot
$DestinationCodexHome = Resolve-PrivateSyncPath $DestinationCodexHome

Assert-NotHostedPath $SourceResearchRoot "SourceResearchRoot"
Assert-NotHostedPath $SourceCodexHome "SourceCodexHome"
Assert-SafeDestination $DestinationResearchRoot "DestinationResearchRoot"
Assert-SafeDestination $DestinationCodexHome "DestinationCodexHome"

if (-not (Test-Path -LiteralPath $DestinationResearchRoot)) {
    throw "DestinationResearchRoot does not exist: $DestinationResearchRoot"
}

$backupRoot = New-BackupRoot
Write-Host "private sync mode: $Mode"
Write-Host "items: $($Items -join ', ')"
if ($BackupDestination) {
    Write-Host "backup root: $backupRoot"
}

foreach ($item in $Items) {
    switch ($item) {
        "Secrets" {
            if ([string]::IsNullOrWhiteSpace($SourceResearchRoot)) { throw "SourceResearchRoot is required for Secrets." }
            $src = Join-Path $SourceResearchRoot ".secrets"
            $dst = Join-Path $DestinationResearchRoot ".secrets"
            Backup-ExistingPath -Path $dst -BackupRoot $backupRoot -Name "research_x.secrets"
            Invoke-RobocopyChecked -Source $src -Destination $dst -ThreadCount $Threads
        }
        "Env" {
            if ([string]::IsNullOrWhiteSpace($SourceResearchRoot)) { throw "SourceResearchRoot is required for Env." }
            $srcDir = $SourceResearchRoot
            $dstDir = $DestinationResearchRoot
            $dst = Join-Path $DestinationResearchRoot ".env"
            Backup-ExistingPath -Path $dst -BackupRoot $backupRoot -Name "research_x.env"
            Invoke-RobocopyChecked -Source $srcDir -Destination $dstDir -FileName ".env" -ThreadCount 1
        }
        "CodexHome" {
            if ([string]::IsNullOrWhiteSpace($SourceCodexHome)) { throw "SourceCodexHome is required for CodexHome." }
            if ($ReplaceCodexHome -and (Test-Path -LiteralPath $DestinationCodexHome)) {
                Backup-ExistingPath -Path $DestinationCodexHome -BackupRoot $backupRoot -Name "codex_home"
                if ($Mode -eq "Plan") {
                    Write-Host "replace plan: existing Codex home would be renamed before copy."
                } else {
                    $replaceTarget = Join-Path $backupRoot "codex_home_replaced"
                    Move-Item -LiteralPath $DestinationCodexHome -Destination $replaceTarget
                    Write-Host "moved existing Codex home to backup."
                }
            } else {
                Backup-ExistingPath -Path $DestinationCodexHome -BackupRoot $backupRoot -Name "codex_home"
            }
            Invoke-RobocopyChecked -Source $SourceCodexHome -Destination $DestinationCodexHome -ThreadCount $Threads
        }
        "RunDb" {
            if ([string]::IsNullOrWhiteSpace($SourceResearchRoot)) { throw "SourceResearchRoot is required for RunDb." }
            $srcDir = Join-Path $SourceResearchRoot "runs"
            $dstDir = Join-Path $DestinationResearchRoot "runs"
            $dst = Join-Path $dstDir "x_data.sqlite3"
            Backup-ExistingPath -Path $dst -BackupRoot $backupRoot -Name "runs.x_data.sqlite3"
            if ($Mode -eq "Copy") {
                New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
            }
            Invoke-RobocopyChecked -Source $srcDir -Destination $dstDir -FileName "x_data.sqlite3" -ThreadCount 1
        }
        "Runs" {
            if ([string]::IsNullOrWhiteSpace($SourceResearchRoot)) { throw "SourceResearchRoot is required for Runs." }
            $src = Join-Path $SourceResearchRoot "runs"
            $dst = Join-Path $DestinationResearchRoot "runs"
            Backup-ExistingPath -Path $dst -BackupRoot $backupRoot -Name "runs"
            Invoke-RobocopyChecked -Source $src -Destination $dst -ThreadCount $Threads
        }
    }
}

Write-Host "private sync completed: $Mode"
