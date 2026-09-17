param(
    [int]$Port = 8501,
    [int]$Width = 1440,
    [int]$Height = 1000
)

$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "capture_screenshots.py") `
    --port $Port `
    --width $Width `
    --height $Height

if ($LASTEXITCODE -ne 0) {
    throw "Screenshot capture failed with exit code $LASTEXITCODE"
}
