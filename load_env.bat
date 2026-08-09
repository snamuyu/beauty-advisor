@echo off
setlocal enabledelayedexpansion

if not exist ".env" (
    echo [ERROR] .env file not found!
    pause
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    set "line=%%a"
    if not "!line:~0,1!"=="#" (
        set "key=%%a"
        set "val=%%b"
        set "key=!key: =!"
        set "val=!val: =!"
        if not "!key!"=="" (
            set "!key!=!val!"
            echo [OK] !key! = !val!
        )
    )
)

echo.
echo Environment variables loaded successfully!
pause