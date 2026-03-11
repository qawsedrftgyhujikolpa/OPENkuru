@echo off
chcp 65001 >nul
echo ============================================
echo   Screen Commentator Win - All-in-One
echo ============================================

set PYTHON=C:\Users\tanak\anaconda3\python.exe

if not exist ".venv" (
    echo [INFO] Creating venv...
    "%PYTHON%" -m venv .venv
)

call .venv\Scripts\activate

pip show mss >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing dependencies...
    pip install mss pillow python-dotenv
) else (
    echo [OK] Dependencies ready.
)

echo.
echo [INFO] Starting Screen Commentator Win...
echo [INFO] Press Esc to exit.
echo.

python screen_commentator_win.py
pause
