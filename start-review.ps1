# 知味验收启动入口。只准备独立本机开发库，不重置现有台账。
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

function Require-Command([string]$name, [string]$help) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $found) { throw "$help（缺少 $name）" }
    return $found.Source
}

try {
    $node = Require-Command 'node.exe' '请安装 Node.js 22.12 或更新版本'
    $nodeVersion = (& $node --version).TrimStart('v')
    if ([version]$nodeVersion -lt [version]'22.12.0') {
        throw "Node.js 版本为 $nodeVersion，需要 22.12 或更新版本"
    }
    $pnpm = Require-Command 'pnpm.cmd' '请安装 pnpm 11（可运行 corepack enable）'
    $docker = Require-Command 'docker.exe' '请安装并启动 Docker Desktop'
    & $docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop 尚未启动，请启动后重试' }

    try {
        $front = Invoke-WebRequest 'http://127.0.0.1:5173/login' -UseBasicParsing -TimeoutSec 2
        $api = Invoke-WebRequest 'http://127.0.0.1:8002/health' -UseBasicParsing -TimeoutSec 2
        $agent = Invoke-WebRequest 'http://127.0.0.1:8001/health' -UseBasicParsing -TimeoutSec 2
        if ($front.StatusCode -eq 200 -and $api.StatusCode -eq 200 -and $agent.StatusCode -eq 200) {
            Write-Host '知味已在运行：http://127.0.0.1:5173/login'
            exit 0
        }
    } catch { # 服务尚未启动；继续检查环境并启动。
    }

    $pythonExe = Join-Path $projectRoot 'apps/api/.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        $launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
        if ($launcher) {
            & $launcher.Source -3.13 -m venv (Join-Path $projectRoot 'apps/api/.venv')
        } else {
            $python = Require-Command 'python.exe' '请安装 Python 3.13'
            $version = (& $python --version)
            if ($version -notmatch '^Python 3\.13\.') { throw "需要 Python 3.13，当前为 $version" }
            & $python -m venv (Join-Path $projectRoot 'apps/api/.venv')
        }
        if ($LASTEXITCODE -ne 0) { throw 'Python 虚拟环境创建失败' }
    }

    & $pythonExe --version | Out-Host
    if ($LASTEXITCODE -ne 0 -or (& $pythonExe --version) -notmatch '^Python 3\.13\.') {
        throw '现有 apps/api/.venv 需要使用 Python 3.13；请检查该虚拟环境'
    }

    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'node_modules/.pnpm'))) {
        Write-Host '首次启动：安装前端依赖……'
        & $pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
    }
    $needsPythonInstall = $false
    try {
        & $pythonExe -c 'import fastapi, sqlalchemy, zhiwei_agent' *> $null
        $needsPythonInstall = $LASTEXITCODE -ne 0
    } catch {
        $needsPythonInstall = $true
    }
    if ($needsPythonInstall) {
        Write-Host '首次启动：安装业务服务和 Agent 依赖……'
        & $pythonExe -m pip install -e 'apps/api[dev]' -e 'apps/agent[dev]'
        if ($LASTEXITCODE -ne 0) { throw 'Python 依赖安装失败' }
    }

    Write-Host '启动本地 PostgreSQL……'
    & $docker compose -f infra/docker-compose.dev.yml up -d
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL 启动失败' }

    Write-Host '启动知味。就绪后打开 http://127.0.0.1:5173/login；关闭此窗口会停止三个应用服务。'
    & $pnpm dev:demo
    if ($LASTEXITCODE -ne 0) { throw '项目启动失败，请查看上方日志' }
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
