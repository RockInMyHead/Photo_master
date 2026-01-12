@echo off
echo ===========================================
echo         Photo Master - Quick Start
echo ===========================================
echo.

REM Check if Python virtual environment exists
if not exist "backend\venv" (
    echo ❌ Python virtual environment not found
    echo Please run start.bat first to set up the environment
    pause
    exit /b 1
)

REM Check if frontend node_modules exists
if not exist "frontend\node_modules" (
    echo ❌ Frontend dependencies not installed
    echo Please run start.bat first to install dependencies
    pause
    exit /b 1
)

echo 🚀 Starting servers...
echo.

REM Start backend in new window
echo Starting backend server on http://localhost:8000
start "Photo Master - Backend" cmd /k "cd backend && call venv\Scripts\activate.bat && python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000"

REM Wait a moment for backend to start
timeout /t 2 /nobreak >nul

REM Start frontend in new window
echo Starting frontend server on http://localhost:5173
start "Photo Master - Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ===========================================
echo 🎉 Application started successfully!
echo ===========================================
echo.
echo 📱 Open browser: http://localhost:5173
echo 🔧 Backend API: http://localhost:8000
echo.
echo Both servers are running in background windows.
echo Close those windows to stop the servers.
echo.
pause
