@echo off
echo ===========================================
echo      Photo Master - Auto Start Script
echo ===========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js is not installed or not in PATH
    echo Please install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)

echo ✅ Python and Node.js are installed
echo.

REM Check if backend directory exists
if not exist "backend" (
    echo ❌ Backend directory not found
    pause
    exit /b 1
)

REM Check if frontend directory exists
if not exist "frontend" (
    echo ❌ Frontend directory not found
    pause
    exit /b 1
)

echo 📦 Installing backend dependencies...
cd backend
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install Python dependencies
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Failed to install Python dependencies
    pause
    exit /b 1
)

echo ✅ Backend dependencies installed
echo.

echo 📦 Installing frontend dependencies...
cd ..\frontend

REM Check if node_modules exists, if not install dependencies
if not exist "node_modules" (
    npm install
    if errorlevel 1 (
        echo ❌ Failed to install Node.js dependencies
        pause
        exit /b 1
    )
)

echo ✅ Frontend dependencies installed
echo.

REM Return to root directory
cd ..

echo 🚀 Starting servers...
echo.

REM Start backend in new window
echo Starting backend server on http://localhost:8000
start "Photo Master - Backend" cmd /k "cd backend && call venv\Scripts\activate.bat && python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000"

REM Wait a moment for backend to start
timeout /t 3 /nobreak >nul

REM Start frontend in new window
echo Starting frontend server on http://localhost:5173
start "Photo Master - Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ===========================================
echo 🎉 Servers are starting up!
echo ===========================================
echo.
echo 📱 Frontend: http://localhost:5173
echo 🔧 Backend API: http://localhost:8000
echo.
echo Press any key to close this window...
echo (Servers will continue running in background)
pause >nul
