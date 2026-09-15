# ============================================================
# Bootstrap Script — Indian Quant Research Agent
# Run: .\bootstrap.ps1
# ============================================================
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Indian Quant Research Agent — Bootstrap" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Check prerequisites
Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Write-Host "ERROR: Python not found" -ForegroundColor Red; exit 1 }
Write-Host "  Python: $(python --version)" -ForegroundColor Green

$uv = Get-Command uv -ErrorAction SilentlyContinue
$pip = Get-Command pip -ErrorAction SilentlyContinue
$git = Get-Command git -ErrorAction SilentlyContinue

# Create virtual environment
Write-Host "[2/6] Creating virtual environment..." -ForegroundColor Yellow
if ($uv) {
    Write-Host "  Using uv..." -ForegroundColor Green
    Set-Location $root
    uv venv .venv
    uv pip install -e ".[dev]" 2>$null
    if ($LASTEXITCODE -ne 0) {
        uv pip install -r requirements.txt 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  Installing dependencies individually..." -ForegroundColor Yellow
            uv pip install pandas polars numpy pyarrow duckdb scipy scikit-learn statsmodels xgboost lightgbm hmmlearn pandas-ta yfinance requests feedparser beautifulsoup4 lxml fastapi uvicorn python-dotenv httpx plotly jupyter matplotlib schedule rich click pydantic tqdm pytest
        }
    }
} elseif ($pip) {
    Write-Host "  Using pip..." -ForegroundColor Green
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install pandas polars numpy pyarrow duckdb scipy scikit-learn statsmodels xgboost lightgbm hmmlearn pandas-ta yfinance requests feedparser beautifulsoup4 lxml fastapi uvicorn python-dotenv httpx plotly jupyter matplotlib schedule rich click pydantic tqdm pytest
}

# Setup .env
Write-Host "[3/6] Setting up environment..." -ForegroundColor Yellow
if (-not (Test-Path "$root\.env")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host "  Created .env from .env.example" -ForegroundColor Green
} else {
    Write-Host "  .env already exists" -ForegroundColor Green
}

# Initialize git
Write-Host "[4/6] Initializing git..." -ForegroundColor Yellow
if ($git) {
    if (-not (Test-Path "$root\.git")) {
        Set-Location $root
        git init
        git add -A
        git commit -m "v0.1-initial-scaffold — Indian Quant Research Agent"
        Write-Host "  Git initialized with initial commit" -ForegroundColor Green
    } else {
        Write-Host "  Git already initialized" -ForegroundColor Green
    }
}

# Verify structure
Write-Host "[5/6] Verifying directory structure..." -ForegroundColor Yellow
$dirs = @("data/raw", "data/processed", "data/features", "data/news", "data/events",
          "research/notebooks", "strategies", "models/checkpoints", "experiments",
          "reports", "logs", "state", "src")
foreach ($d in $dirs) {
    if (-not (Test-Path "$root\$d")) {
        New-Item -ItemType Directory -Force -Path "$root\$d" | Out-Null
    }
}
Write-Host "  All directories verified" -ForegroundColor Green

# Dry run
Write-Host "[6/6] Running verification..." -ForegroundColor Yellow
try {
    python "$root\research_agent.py" --dry-run
    Write-Host "`n  Setup verified successfully!" -ForegroundColor Green
} catch {
    Write-Host "  Dry run had issues (dependencies may still be installing)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Bootstrap Complete!" -ForegroundColor Cyan
Write-Host "" 
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "    python research_agent.py --autonomous    # Full research pipeline" -ForegroundColor White
Write-Host "    python research_agent.py --data-only     # Download data only" -ForegroundColor White
Write-Host "    python research_agent.py --backtest-only  # Backtest only" -ForegroundColor White
Write-Host "    python research_agent.py --dashboard      # Start dashboard" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
