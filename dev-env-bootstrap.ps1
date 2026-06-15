param(
    [switch]$InstallOptionalApps,
    [switch]$UseWingetExport,
    [string]$BackupRoot
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Script
    )

    Write-Host ""
    Write-Host "==> $Name"
    try {
        & $Script
    }
    catch {
        Write-Warning "$Name failed: $($_.Exception.Message)"
    }
}

function Install-WingetPackage {
    param(
        [string]$Id,
        [string]$Source = "",
        [string]$Name = $Id
    )

    $args = @(
        "install",
        "--id", $Id,
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity"
    )

    if ($Source) {
        $args += @("--source", $Source)
    }

    Write-Host "winget install $Name ($Id)"
    winget @args
}

function Add-UserPathEntry {
    param([string]$PathEntry)

    if (-not (Test-Path $PathEntry)) {
        New-Item -ItemType Directory -Path $PathEntry -Force | Out-Null
    }

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @()
    if ($userPath) {
        $entries = $userPath -split ";"
    }

    if ($entries -notcontains $PathEntry) {
        $newPath = if ($userPath) { "$userPath;$PathEntry" } else { $PathEntry }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    }

    if (($env:Path -split ";") -notcontains $PathEntry) {
        $env:Path = "$env:Path;$PathEntry"
    }
}

$coreWingetPackages = @(
    @{ Id = "Codex"; Source = "msstore"; Name = "Codex App" },
    @{ Id = "Microsoft.PowerShell"; Name = "PowerShell" },
    @{ Id = "Microsoft.WindowsTerminal"; Name = "Windows Terminal" },
    @{ Id = "Git.Git"; Name = "Git" },
    @{ Id = "OpenJS.NodeJS.LTS"; Name = "Node.js LTS" },
    @{ Id = "Microsoft.VisualStudioCode"; Name = "Visual Studio Code" },
    @{ Id = "Microsoft.WSL"; Name = "Windows Subsystem for Linux" },
    @{ Id = "RProject.R"; Name = "R" },
    @{ Id = "Posit.RStudio"; Name = "RStudio" },
    @{ Id = "Cloudflare.cloudflared"; Name = "cloudflared" },
    @{ Id = "Microsoft.VCRedist.2015+.x64"; Name = "VC++ Redistributable x64" },
    @{ Id = "Microsoft.VCRedist.2015+.x86"; Name = "VC++ Redistributable x86" }
)

$optionalWingetPackages = @(
    @{ Id = "Google.Chrome.EXE"; Name = "Google Chrome" },
    @{ Id = "Google.ChromeRemoteDesktopHost"; Name = "Chrome Remote Desktop Host" },
    @{ Id = "Microsoft.Edge"; Name = "Microsoft Edge" },
    @{ Id = "Microsoft.Office"; Name = "Microsoft 365 Apps" },
    @{ Id = "Microsoft.OneDrive"; Name = "OneDrive" },
    @{ Id = "Microsoft.Teams"; Name = "Microsoft Teams" },
    @{ Id = "Microsoft.Teams.Free"; Name = "Microsoft Teams personal" },
    @{ Id = "Zoom.Zoom.EXE"; Name = "Zoom Workplace" },
    @{ Id = "BlenderFoundation.Blender"; Name = "Blender" },
    @{ Id = "Microsoft.SurfaceApp"; Name = "Surface app" },
    @{ Id = "XPDC2RH70K22MN"; Source = "msstore"; Name = "Discord" }
)

$vscodeExtensions = @(
    "ms-ceintl.vscode-language-pack-ja",
    "ms-python.debugpy",
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-python.vscode-python-envs",
    "openai.chatgpt"
)

Invoke-Step "Install winget packages" {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is not available. Install App Installer from Microsoft Store first."
    }

    if ($UseWingetExport) {
        $exportFile = Join-Path $PSScriptRoot "dev-env-winget-export.json"
        if (Test-Path $exportFile) {
            winget import --import-file $exportFile --accept-package-agreements --accept-source-agreements --disable-interactivity
        }
        else {
            Write-Warning "dev-env-winget-export.json was not found next to this script; falling back to curated package list."
        }
    }

    foreach ($pkg in $coreWingetPackages) { Install-WingetPackage @pkg }
    if ($InstallOptionalApps) {
        foreach ($pkg in $optionalWingetPackages) { Install-WingetPackage @pkg }
    }
}

Invoke-Step "Prepare user PATH and npm directories" {
    Add-UserPathEntry (Join-Path $env:USERPROFILE ".local\bin")
    Add-UserPathEntry (Join-Path $env:APPDATA "npm")
    New-Item -ItemType Directory -Path (Join-Path $env:APPDATA "npm\node_modules") -Force | Out-Null
}

Invoke-Step "Install uv if missing" {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        try {
            Install-WingetPackage -Id "astral-sh.uv" -Name "uv"
        }
        catch {
            Write-Warning "winget uv install failed; using the official uv installer script."
            irm https://astral.sh/uv/install.ps1 | iex
            Add-UserPathEntry (Join-Path $env:USERPROFILE ".local\bin")
        }
    }

    uv --version
}

Invoke-Step "Install uv tools" {
    uv tool install "basic-memory==0.21.6"
}

Invoke-Step "Configure Git identity" {
    git config --global user.name "ozaki masanori"
    git config --global user.email "23fi025@ms.dendai.ac.jp"
}

Invoke-Step "Install VS Code extensions" {
    $code = Get-Command code -ErrorAction SilentlyContinue
    if (-not $code) {
        $env:Path = "$env:Path;$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin"
    }

    foreach ($extension in $vscodeExtensions) {
        code --install-extension $extension --force
    }
}

Invoke-Step "Restore editor and Codex settings from backup" {
    if (-not $BackupRoot) {
        Write-Host "No -BackupRoot supplied; skipping settings restore."
        return
    }

    $codeBackup = Join-Path $BackupRoot "Code\User"
    if (Test-Path (Join-Path $codeBackup "settings.json")) {
        New-Item -ItemType Directory -Path (Join-Path $env:APPDATA "Code\User") -Force | Out-Null
        Copy-Item (Join-Path $codeBackup "settings.json") (Join-Path $env:APPDATA "Code\User\settings.json") -Force
    }
    if (Test-Path (Join-Path $codeBackup "snippets")) {
        robocopy (Join-Path $codeBackup "snippets") (Join-Path $env:APPDATA "Code\User\snippets") /E /R:1 /W:1 | Out-Null
    }

    $gitconfig = Join-Path $BackupRoot ".gitconfig"
    if (Test-Path $gitconfig) {
        Copy-Item $gitconfig (Join-Path $env:USERPROFILE ".gitconfig") -Force
    }

    $codexBackup = Join-Path $BackupRoot ".codex"
    $codexTarget = Join-Path $env:USERPROFILE ".codex"
    if (Test-Path $codexBackup) {
        New-Item -ItemType Directory -Path $codexTarget -Force | Out-Null
        foreach ($file in @("AGENTS.md", "config.toml")) {
            $source = Join-Path $codexBackup $file
            if (Test-Path $source) {
                Copy-Item $source (Join-Path $codexTarget $file) -Force
            }
        }
        foreach ($dir in @("skills", "plugins", "prompts", "rules", "memories", "vendor_imports")) {
            $source = Join-Path $codexBackup $dir
            if (Test-Path $source) {
                robocopy $source (Join-Path $codexTarget $dir) /E /R:1 /W:1 | Out-Null
            }
        }
    }
}

Write-Host ""
Write-Host "Done. Restart the terminal so User PATH changes are visible everywhere."
Write-Host "WSL distributions were not detected on the source PC. If you need one, run: wsl --install -d Ubuntu"
