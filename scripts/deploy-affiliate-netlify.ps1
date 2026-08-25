param(
  [ValidateSet("iphone", "spaghetti")]
  [string]$Product = "iphone",

  [string]$SiteId = $env:NETLIFY_SITE_ID,

  [switch]$Draft
)

$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$projects = Join-Path $workspace "projects"
$configPath = Join-Path $workspace "scripts\netlify-site.local.json"

if (-not $SiteId -and (Test-Path -LiteralPath $configPath)) {
  $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
  $SiteId = $config.site_id
}

if (-not $SiteId) {
  Write-Host "Missing Netlify site ID."
  Write-Host ""
  Write-Host "One-time setup:"
  Write-Host "  1. Run: npx --yes netlify-cli login"
  Write-Host "  2. Create or choose ONE Netlify site."
  Write-Host "  3. Save its site ID in either:"
  Write-Host "     - environment variable NETLIFY_SITE_ID"
  Write-Host "     - scripts\\netlify-site.local.json using scripts\\netlify-site.example.json as template"
  Write-Host ""
  Write-Host "This script always deploys to that same site ID, so the public URL stays the same."
  exit 1
}

$siteMap = @{
  "iphone"    = "iphone-lens-case-affiliate-site"
  "spaghetti" = "wow-spaghetti-affiliate-site"
}

$sourceDir = Join-Path $projects $siteMap[$Product]
$indexPath = Join-Path $sourceDir "index.html"

if (-not (Test-Path -LiteralPath $indexPath)) {
  throw "index.html not found: $indexPath"
}

$htmlFiles = @(Get-ChildItem -LiteralPath $sourceDir -Recurse -File -Filter "*.html")
if ($htmlFiles.Count -ne 1) {
  throw "Expected exactly one HTML file in deploy folder, found $($htmlFiles.Count)."
}

$affiliateLine = Select-String -LiteralPath $indexPath -Pattern "const AFFILIATE_URL" -SimpleMatch | Select-Object -First 1
if ($affiliateLine) {
  Write-Host "Affiliate URL line:"
  Write-Host "  $($affiliateLine.Line.Trim())"
}

$modeArgs = @("deploy", "--dir", $sourceDir, "--site", $SiteId, "--json")
if (-not $Draft) {
  $modeArgs += "--prod"
}

$netlify = Get-Command netlify -ErrorAction SilentlyContinue
if ($netlify) {
  Write-Host "Deploying with installed Netlify CLI..."
  & netlify @modeArgs
} else {
  Write-Host "Deploying with npx netlify-cli..."
  & npx --yes netlify-cli @modeArgs
}

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
