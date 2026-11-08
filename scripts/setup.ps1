# Create the virtual environment, install dependencies and run the tests (Windows PowerShell).
# If scripts are blocked:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is required." }
python -c "import tkinter"
if ($LASTEXITCODE -ne 0) { throw "Tkinter is missing: re-run the Python installer and tick 'tcl/tk and IDLE'." }

python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python -m unittest -v

Write-Host ""
Write-Host "Setup finished."
Write-Host "  Activate : .\.venv\Scripts\Activate.ps1"
Write-Host "  Run      : python -m mailpilot"
