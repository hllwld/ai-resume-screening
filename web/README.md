# 简历评估 Web 工作台

这是现有 Dify 简历分析工作流的 Web 前端。浏览器批量读取 PDF 简历并提取文字，FastAPI 后端调用 Dify Workflow API，结果可在页面筛选、查看证据并下载格式化 Excel。

## 功能

- 选择文件夹或一次选择多个 PDF，单批最多 10 份。
- PDF 在浏览器本地解析，原文件不会上传到后端。
- 检测疑似扫描件、加密文件、损坏文件和超限文件。
- 填写岗位 JD 和受控的补充评价要求。
- 并发调用 Dify，显示逐份状态与总进度。
- 按候选人、推荐结论和分数筛选排序。
- 下载 UTF-8 CSV 或带格式、筛选、下拉框的 XLSX。

> 浏览器会把提取后的简历文字发送到本地后端及你配置的 Dify 服务。首版不提供 OCR；疑似扫描件会标记为“需要 OCR”。

## 首次安装

### 1. 后端

在 `web/backend` 目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`：

```dotenv
DIFY_BASE_URL=https://api.dify.ai/v1
DIFY_API_KEY=app-your-real-key
DIFY_CONCURRENCY=3
DIFY_TIMEOUT_SECONDS=120
TASK_TTL_SECONDS=7200
APP_ACCESS_CODE=
SESSION_SECRET=
PER_IP_DAILY_RESUME_LIMIT=10
GLOBAL_DAILY_RESUME_LIMIT=50
QUOTA_DB_PATH=
```

API Key 必须来自已经发布的 Dify Workflow 应用，不要写进前端代码或提交到 Git。
本地开发可以留空 `APP_ACCESS_CODE`；公网生产环境必须配置访问口令，并为
`SESSION_SECRET` 设置至少 32 个字符的随机值。

### 2. 前端

在 `web/frontend` 目录执行：

```powershell
pnpm install
pnpm run build
```

## 启动

完成首次安装和前端构建后，在 `web` 目录执行：

```powershell
.\start.ps1
```

浏览器打开 <http://127.0.0.1:8000>。

开发前端时可分别启动：

```powershell
# 终端一：web/backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# 终端二：web/frontend
pnpm run dev
```

开发页面地址为 <http://127.0.0.1:5173>，Vite 会把 `/api` 转发到 FastAPI。

## Dify 要求

导入仓库中的 `workflow/简历分析助手.yml` 并发布。工作流输入为：

| 字段 | 必填 | 说明 |
|---|---|---|
| `resume_text` | 是 | 浏览器提取的单份简历文字 |
| `job_description` | 是 | 岗位 JD |
| `custom_instructions` | 否 | 只能补充业务关注点 |

后端优先读取 `parsed_json`，也兼容 Dify 将结果放在 `result` 或展平输出字段中的情况。

## 运行边界

- 任务只保存在后端内存中，刷新页面后不恢复，服务重启后丢失。
- 默认单文件不超过 10 MB、30 页、60,000 字符。
- 每个任务最多 10 份简历；单个 IP 每天最多评估 10 份，全站每天最多
  评估 50 份，按北京时间零点重置。
- 单个 PDF 最大 10 MB、30 页，提取文本最多 60,000 字符。
- 并发数默认 3，任务和下载绑定当前浏览器会话。
- 网络错误、超时、429 和服务端错误最多自动重试两次。
- Excel 只导出成功结果；失败和取消项会写入“处理说明”工作表。
- AI 输出仅供人工复核，不能自动决定录用或淘汰。

## Render 公网部署

仓库根目录的 `render.yaml` 默认配置为 Render 新加坡区域的免费实例，使用
单个 Docker 容器提供前端和 API。创建 Blueprint 时必须在 Render 控制台填写：

- `DIFY_API_KEY`：已发布 Dify Workflow 的 API Key。
- `APP_ACCESS_CODE`：演示访问口令，不要使用模型或 Dify 密钥作为口令。

`APP_ACCESS_CODE` 至少需要 12 个字符；`SESSION_SECRET` 由 Render 自动生成。
生产环境会强制校验以上安全配置，
使用 HTTPS Cookie、隐藏 API 文档，并信任 Render 反向代理提供的客户端 IP。

免费实例不支持持久磁盘，因此每日额度（IP 在内存中仅保存为不可逆摘要）、
评估任务和结果都会在服务重启或休眠后清空。免费实例闲置后还会休眠，首次
访问需要等待冷启动；这符合低频作品集演示场景。改回付费常驻实例时，可重新
启用持久磁盘和 `QUOTA_DB_PATH`。若以后开放注册或横向扩容，应把任务和额度
迁移到 Redis/PostgreSQL。

若 Render 要求 Blueprint 绑定付款方式，可改为手动创建单个 Web Service：
选择 `codex/render-free` 分支、Docker 运行时、Singapore 区域和 Free 实例。
仓库根目录的 `Dockerfile` 可被 Render 自动识别。

## 验证

```powershell
# 后端
cd web/backend
.\.venv\Scripts\python.exe -m pytest -q

# 前端
cd web/frontend
pnpm run build
```
