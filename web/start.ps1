$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

if (-not (Test-Path (Join-Path $backend ".venv\Scripts\python.exe"))) {
    throw "后端环境尚未安装。请先按照仓库根目录 README.md 完成首次安装。"
}
if (-not (Test-Path (Join-Path $frontend "dist\index.html"))) {
    throw "前端尚未构建。请先按照仓库根目录 README.md 完成首次安装。"
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    throw "缺少 web/backend/.env。请从 .env.example 复制并填写 DIFY_API_KEY。"
}

Set-Location $backend
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
