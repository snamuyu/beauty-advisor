$ErrorActionPreference = "SilentlyContinue"

# 只结束命令行匹配 "uvicorn main:app" 的进程，避免误杀其它 Python
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match "uvicorn main:app" } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        "Stopped Beauty Advisor API (PID $($_.ProcessId))"
    }

Write-Host "Done."
