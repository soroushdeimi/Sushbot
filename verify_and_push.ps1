#!/usr/bin/env pwsh
# =============================================================================
# verify_and_push.ps1 - Local CI verification before pushing
# =============================================================================
# Run this script to ensure your code will pass CI before pushing.
# If all checks pass, it will auto-commit and push.
# =============================================================================

$ErrorActionPreference = "Continue"

function Write-Step {
    param([string]$Message)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  $Message" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

# Change to script directory
Set-Location $PSScriptRoot

Write-Host "`n🚀 Starting CI verification..." -ForegroundColor Yellow
Write-Host "   Working directory: $(Get-Location)" -ForegroundColor Gray

# ---------------------------------------------------------------------------
# Step 1: Format code with Ruff
# ---------------------------------------------------------------------------
Write-Step "Step 1/5: Formatting code with Ruff"
python -m ruff format .
Write-Success "Code formatted"

# ---------------------------------------------------------------------------
# Step 2: Fix linting issues with Ruff
# ---------------------------------------------------------------------------
Write-Step "Step 2/5: Fixing lint issues with Ruff"
python -m ruff check . --fix
Write-Success "Auto-fixable lint issues fixed"

# ---------------------------------------------------------------------------
# Step 3: Verify no remaining lint errors
# ---------------------------------------------------------------------------
Write-Step "Step 3/5: Verifying no lint errors remain"
$ruffResult = python -m ruff check . 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Lint errors remain. Fix manually:"
    Write-Host $ruffResult -ForegroundColor Red
    exit 1
}
Write-Success "No lint errors"

# ---------------------------------------------------------------------------
# Step 4: Bandit security scan (BLOCKS on High severity)
# ---------------------------------------------------------------------------
Write-Step "Step 4/5: Running Bandit security scan"
$banditResult = python -m bandit -c pyproject.toml -r . -ll 2>&1
$banditExit = $LASTEXITCODE

if ($banditExit -ne 0) {
    Write-Fail "SECURITY ISSUES FOUND! Fix before pushing:"
    Write-Host $banditResult -ForegroundColor Red
    Write-Host "`n⚠️  Common fixes:" -ForegroundColor Yellow
    Write-Host "   - B105/B106: Hardcoded passwords → use environment variables" -ForegroundColor Yellow
    Write-Host "   - B104: bind 0.0.0.0 → use 127.0.0.1 or make configurable" -ForegroundColor Yellow
    Write-Host "   - B608: SQL injection → use parameterized queries" -ForegroundColor Yellow
    exit 1
}
Write-Success "Security scan passed"

# ---------------------------------------------------------------------------
# Step 5: Run pytest
# ---------------------------------------------------------------------------
Write-Step "Step 5/5: Running pytest"
$env:PYTHONPATH = $PSScriptRoot
python -m pytest tests/ -x -q --tb=short 2>&1 | Tee-Object -Variable testResult
$testExit = $LASTEXITCODE

if ($testExit -ne 0) {
    Write-Fail "Tests failed. Fix and retry."
    exit 1
}
Write-Success "All tests passed"

# ---------------------------------------------------------------------------
# All checks passed - commit and push
# ---------------------------------------------------------------------------
Write-Host "`n" -NoNewline
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✅ ALL CHECKS PASSED!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# Check for changes
$changes = git status --porcelain
if (-not $changes) {
    Write-Host "`n📝 No changes to commit. Everything is already up to date." -ForegroundColor Yellow
    exit 0
}

Write-Host "`n📦 Staging changes..." -ForegroundColor Cyan
git add -A

Write-Host "📝 Committing..." -ForegroundColor Cyan
$commitMsg = Read-Host "Enter commit message (or press Enter for default)"
if ([string]::IsNullOrWhiteSpace($commitMsg)) {
    $commitMsg = "chore: code cleanup and ci fixes"
}
git commit -m $commitMsg

Write-Host "🚀 Pushing to remote..." -ForegroundColor Cyan
git push

Write-Host "`n🎉 Done! Check your CI at GitHub." -ForegroundColor Green
