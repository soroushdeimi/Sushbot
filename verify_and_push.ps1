#!/usr/bin/env pwsh
# =============================================================================
# verify_and_push.ps1 - Local CI verification before pushing
# =============================================================================
# Run this script to ensure your code will pass CI before pushing.
# If all checks pass, it will auto-commit and push.
# =============================================================================

$ErrorActionPreference = "Stop"

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
try {
    python -m ruff format .
    if ($LASTEXITCODE -ne 0) { throw "Ruff format failed" }
    Write-Success "Code formatted successfully"
} catch {
    Write-Fail "Ruff format failed: $_"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 2: Fix linting issues with Ruff
# ---------------------------------------------------------------------------
Write-Step "Step 2/5: Fixing lint issues with Ruff"
try {
    python -m ruff check . --fix
    if ($LASTEXITCODE -ne 0) { throw "Ruff check failed" }
    Write-Success "Lint issues fixed"
} catch {
    Write-Fail "Ruff check failed: $_"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 3: Verify no remaining lint errors
# ---------------------------------------------------------------------------
Write-Step "Step 3/5: Verifying no lint errors remain"
try {
    python -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw "Ruff check still has errors" }
    Write-Success "No lint errors"
} catch {
    Write-Fail "Lint errors remain. Fix manually and retry."
    exit 1
}

# ---------------------------------------------------------------------------
# Step 4: Bandit security scan
# ---------------------------------------------------------------------------
Write-Step "Step 4/5: Running Bandit security scan"
try {
    # Run bandit - we allow it to find issues but just report them
    python -m bandit -c pyproject.toml -r . -ll
    Write-Success "Security scan completed (check output for warnings)"
} catch {
    Write-Host "⚠️  Bandit found issues (review above)" -ForegroundColor Yellow
    # Don't fail - bandit findings are informational
}

# ---------------------------------------------------------------------------
# Step 5: Run pytest
# ---------------------------------------------------------------------------
Write-Step "Step 5/5: Running pytest"
try {
    python -m pytest tests/ -x -q --tb=short
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    Write-Success "All tests passed"
} catch {
    Write-Fail "Tests failed. Fix and retry."
    exit 1
}

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
git commit -m "chore: full ci fix and formatting"

Write-Host "🚀 Pushing to remote..." -ForegroundColor Cyan
git push

Write-Host "`n🎉 Done! Check your CI at GitHub." -ForegroundColor Green
