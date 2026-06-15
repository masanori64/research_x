param(
    [string]$OutputRoot = (Join-Path $env:USERPROFILE "Desktop\dev-env-backup")
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

function Copy-IfExists {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-Path $Source) {
        New-Item -ItemType Directory -Path (Split-Path $Destination -Parent) -Force | Out-Null
        Copy-Item $Source $Destination -Force
    }
}

function Robocopy-IfExists {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-Path $Source) {
        robocopy $Source $Destination /E /R:1 /W:1 | Out-Null
    }
}

Write-Host "Exporting package inventory..."
if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget export --output (Join-Path $OutputRoot "dev-env-winget-export.json") --include-versions --disable-interactivity
    winget list --disable-interactivity | Out-File (Join-Path $OutputRoot "winget-list.txt") -Encoding utf8
}

if (Get-Command code -ErrorAction SilentlyContinue) {
    code --list-extensions --show-versions | Out-File (Join-Path $OutputRoot "vscode-extensions.txt") -Encoding utf8
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv tool list | Out-File (Join-Path $OutputRoot "uv-tools.txt") -Encoding utf8
}

if (Get-Command git -ErrorAction SilentlyContinue) {
    git config --global --list --show-origin | Out-File (Join-Path $OutputRoot "git-global-config.txt") -Encoding utf8
}

Write-Host "Copying user configuration..."
Copy-IfExists (Join-Path $env:USERPROFILE ".gitconfig") (Join-Path $OutputRoot ".gitconfig")
Copy-IfExists (Join-Path $env:APPDATA "Code\User\settings.json") (Join-Path $OutputRoot "Code\User\settings.json")
Copy-IfExists (Join-Path $env:APPDATA "Code\User\keybindings.json") (Join-Path $OutputRoot "Code\User\keybindings.json")
Robocopy-IfExists (Join-Path $env:APPDATA "Code\User\snippets") (Join-Path $OutputRoot "Code\User\snippets")

$codexSource = Join-Path $env:USERPROFILE ".codex"
$codexOut = Join-Path $OutputRoot ".codex"
if (Test-Path $codexSource) {
    New-Item -ItemType Directory -Path $codexOut -Force | Out-Null
    foreach ($file in @("AGENTS.md", "config.toml")) {
        Copy-IfExists (Join-Path $codexSource $file) (Join-Path $codexOut $file)
    }
    foreach ($dir in @("skills", "plugins", "prompts", "rules", "memories", "vendor_imports")) {
        Robocopy-IfExists (Join-Path $codexSource $dir) (Join-Path $codexOut $dir)
    }
}

Copy-IfExists (Join-Path $PSScriptRoot "dev-env-bootstrap.ps1") (Join-Path $OutputRoot "dev-env-bootstrap.ps1")
Copy-IfExists (Join-Path $PSScriptRoot "dev-env-winget-export.json") (Join-Path $OutputRoot "dev-env-winget-export.json")

Write-Host ""
Write-Host "Export complete: $OutputRoot"
Write-Host "Not copied: .codex/auth.json, .codex/.sandbox-secrets, sessions, sqlite logs, npm cache, and SSH keys."
Write-Host "If you need SSH keys or auth tokens, move them manually over an encrypted channel and rotate them if unsure."
