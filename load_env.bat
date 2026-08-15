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
        call :trim key
        call :trim val
        if not "!key!"=="" (
            set "!key!=!val!"
            echo [OK] !key! configured
        )
    )
)

echo.
echo Environment variables loaded successfully!
pause
exit /b 0

rem 去掉变量首尾空格（保留中间空格）
:trim
set "%~1=!%~1!"
for /f "tokens=* delims= " %%v in ("!%~1!") do set "%~1=%%v"
for /l %%i in (1,1,100) do if "!%~1:~-1!"==" " set "%~1=!%~1:~0,-1!"
exit /b
