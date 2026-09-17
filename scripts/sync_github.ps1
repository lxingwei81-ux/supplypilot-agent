param(
    [string]$Message = "chore: sync project updates"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

# Reuse the Windows system proxy for Git/GitHub CLI without changing global settings.
$githubUri = [uri]"https://github.com"
$systemProxy = [System.Net.WebRequest]::GetSystemWebProxy().GetProxy($githubUri)
if ($systemProxy -and $systemProxy.AbsoluteUri -ne $githubUri.AbsoluteUri) {
    $env:HTTPS_PROXY = $systemProxy.AbsoluteUri.TrimEnd("/")
    $env:HTTP_PROXY = $env:HTTPS_PROXY
}

$temporaryRoot = Join-Path $projectRoot "temp"
New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
$pytestRoot = Join-Path $temporaryRoot ("pytest-sync-" + $PID)

python -m pytest -q --basetemp $pytestRoot
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed; GitHub sync was stopped."
}

git add -A
if ($LASTEXITCODE -ne 0) {
    throw "git add failed."
}

$blockedFiles = git diff --cached --name-only | Where-Object {
    ($_ -ne ".env.example") -and
    ($_ -match '(^|/)\.env($|\.)|\.pem$|\.key$|secrets\.toml$')
}
if ($blockedFiles) {
    throw "Sensitive files are staged: $($blockedFiles -join ', ')"
}

git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "No changes to sync."
    exit 0
}

git commit -m $Message
if ($LASTEXITCODE -ne 0) {
    throw "git commit failed."
}

git pull --rebase origin main
if ($LASTEXITCODE -ne 0) {
    throw "git pull --rebase failed; resolve the conflict before pushing."
}

git push origin main
if ($LASTEXITCODE -ne 0) {
    throw "git push failed."
}

Write-Host "SupplyPilot was synchronized to GitHub."
