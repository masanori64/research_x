param(
    [switch]$InstallTools,
    [switch]$WriteIgnores,
    [switch]$StartSyncthing,
    [switch]$AddSyncthingFolders,
    [switch]$Status,
    [switch]$All,
    [switch]$IncludeSecretsFolder
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunsPath = Join-Path $RepoRoot "runs"
$SecretsPath = Join-Path $RepoRoot ".secrets"

function Update-PathFromMachine {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user;$env:Path"
}

function Install-WingetPackage {
    param([string]$Id)
    winget install --id $Id -e --accept-package-agreements --accept-source-agreements
}

function Find-Exe {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"),
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)}
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    $filters = @("$Name.exe")
    if ($Name -eq "restic") {
        $filters += "restic*.exe"
    }

    foreach ($root in $candidates) {
        $matches = foreach ($filter in $filters) {
            Get-ChildItem -LiteralPath $root -Recurse -Filter $filter -File -ErrorAction SilentlyContinue
        }
        $match = $matches | Select-Object -First 1
        if ($match) {
            return $match.FullName
        }
    }

    return $null
}

function Write-TextIfChanged {
    param([string]$Path, [string]$Content)
    $dir = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    if ((Test-Path -LiteralPath $Path) -and ((Get-Content -LiteralPath $Path -Raw) -eq $Content)) {
        return
    }
    Set-Content -LiteralPath $Path -Value $Content -Encoding ascii
}

function Write-SyncIgnores {
    $runsIgnore = @'
// research_x live DB and transient files are not Syncthing-safe.
x_data.sqlite3
x_data.sqlite3-*
*.sqlite
*.sqlite3
*.sqlite-*
*.sqlite3-*
*.db
*.db-*
*-wal
*-shm
*.lock
*.tmp
*.temp
.stfolder
'@

    $secretsIgnore = @'
// Keep active auth/cookie/token state out of routine bidirectional sync.
accounts/
bin/
*.db
*.sqlite
*.sqlite3
*.db-*
*-wal
*-shm
*cookie*
*cookies*
*token*
*auth*
playwright_x_state.json
scweet_state.db
twscrape_accounts.db
.stfolder
'@

    Write-TextIfChanged -Path (Join-Path $RunsPath ".stignore") -Content $runsIgnore
    Write-TextIfChanged -Path (Join-Path $SecretsPath ".stignore") -Content $secretsIgnore
}

function Start-SyncthingIfNeeded {
    $syncthing = Find-Exe "syncthing"
    if (-not $syncthing) {
        throw "syncthing.exe not found. Run with -InstallTools first or reopen PowerShell."
    }
    $running = Get-Process -Name "syncthing" -ErrorAction SilentlyContinue
    if (-not $running) {
        Start-Process -FilePath $syncthing -ArgumentList @("serve", "--no-browser", "--no-console") -WindowStyle Hidden
        Start-Sleep -Seconds 5
    }
}

function Invoke-Syncthing {
    param([string[]]$Arguments)
    $syncthing = Find-Exe "syncthing"
    if (-not $syncthing) {
        throw "syncthing.exe not found."
    }
    & $syncthing @Arguments
}

function Test-SyncthingFolderExists {
    param([string]$FolderId)
    $items = Invoke-Syncthing -Arguments @("cli", "config", "folders", "list")
    return ($items -contains $FolderId)
}

function Add-SyncthingFolder {
    param(
        [string]$FolderId,
        [string]$Label,
        [string]$Path,
        [string]$Type = "sendreceive"
    )
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    if (Test-SyncthingFolderExists -FolderId $FolderId) {
        return
    }
    Invoke-Syncthing -Arguments @(
        "cli", "config", "folders", "add",
        "--id", $FolderId,
        "--label", $Label,
        "--path", $Path,
        "--type", $Type,
        "--rescan-intervals", "3600",
        "--fswatcher-enabled"
    ) | Out-Null
}

function Add-ResearchXSyncthingFolders {
    Start-SyncthingIfNeeded
    Add-SyncthingFolder -FolderId "research-x-runs-diff" -Label "research_x runs diff" -Path $RunsPath
    if ($IncludeSecretsFolder) {
        Add-SyncthingFolder -FolderId "research-x-secrets-sendonly" -Label "research_x secrets send-only" -Path $SecretsPath -Type "sendonly"
    }
}

function Show-FreeSyncStatus {
    Update-PathFromMachine
    $tools = "tailscale", "syncthing", "rclone", "restic", "sops", "age", "age-keygen"
    $rows = foreach ($tool in $tools) {
        $path = Find-Exe $tool
        [pscustomobject]@{
            Tool = $tool
            Found = [bool]$path
            Path = $path
        }
    }
    $rows | Format-Table -AutoSize

    $tailscale = "C:\Program Files\Tailscale\tailscale.exe"
    if (Test-Path -LiteralPath $tailscale) {
        & $tailscale ip
    }

    $syncthing = Find-Exe "syncthing"
    if ($syncthing) {
        & $syncthing device-id
        & $syncthing cli config folders list
    }
}

if ($All) {
    $InstallTools = $true
    $WriteIgnores = $true
    $StartSyncthing = $true
    $AddSyncthingFolders = $true
    $Status = $true
}

if (-not ($InstallTools -or $WriteIgnores -or $StartSyncthing -or $AddSyncthingFolders -or $Status)) {
    $Status = $true
}

if ($InstallTools) {
    Install-WingetPackage "Tailscale.Tailscale"
    Install-WingetPackage "Syncthing.Syncthing"
    Install-WingetPackage "Rclone.Rclone"
    Install-WingetPackage "restic.restic"
    Install-WingetPackage "Mozilla.SOPS"
    Install-WingetPackage "FiloSottile.age"
    Update-PathFromMachine
}

if ($WriteIgnores) {
    Write-SyncIgnores
}

if ($StartSyncthing) {
    Start-SyncthingIfNeeded
}

if ($AddSyncthingFolders) {
    Add-ResearchXSyncthingFolders
}

if ($Status) {
    Show-FreeSyncStatus
}
