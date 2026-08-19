param(
    [int]$Port = 0,
    [switch]$NoLog
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
# Use the dedicated conda environment "beauty-advisor"
$Py = "F:\conda-envs\beauty-advisor\python.exe"
if (-not (Test-Path -LiteralPath $Py)) { $Py = "python" }

# 未指定端口时读取 config.py 的 APP_PORT
if ($Port -eq 0) {
    $PortText = & $Py -c "import config; print(config.APP_PORT)" 2>$null
    if ($PortText -match "^\d+$") { $Port = [int]$PortText } else { $Port = 8000 }
}

$LogDir = Join-Path $Root "log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$UvicornArgs = @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$Port")

function Start-Hidden {
    param([string[]]$ArgumentList)
    $common = @{
        FilePath = $Py
        ArgumentList = $ArgumentList
        WorkingDirectory = $Root
        WindowStyle = "Hidden"
        PassThru = $true
    }
    try {
        if (-not $NoLog) {
            return Start-Process @common `
                -RedirectStandardOutput (Join-Path $LogDir "api.log") `
                -RedirectStandardError (Join-Path $LogDir "api.err.log")
        }
        return Start-Process @common
    } catch {
        # PS 5.1 环境变量大小写重复的已知 bug：去掉重定向重试
        return Start-Process @common
    }
}

Start-Hidden -ArgumentList $UvicornArgs | Out-Null
Write-Host "Beauty Advisor API started at http://127.0.0.1:$Port"
Write-Host "Frontend page: http://127.0.0.1:$Port/"
if ($NoLog) {
    Write-Host "Log: disabled (--NoLog)"
} else {
    Write-Host "Log: $LogDir\api.log"
}
