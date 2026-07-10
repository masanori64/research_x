param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]] $ArgsForBuild
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $root
try {
  npm run presentation:build -- @ArgsForBuild
}
finally {
  Pop-Location
}
