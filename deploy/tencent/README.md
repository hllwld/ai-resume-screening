# 腾讯云香港快速部署

适用于腾讯云轻量应用服务器（中国香港、Docker CE/Ubuntu 24.04、2 核 2 GB
或更高配置）。Caddy 自动申请和续期 HTTPS 证书，应用只在容器网络中开放，
每日限额数据库保存在 Docker volume 中。

## 前置条件

1. 为根域名 `zerodot.top` 添加一条主机记录为 `@` 的 `A` 记录，指向服务器公网 IP `43.132.155.30`。
2. 轻量服务器防火墙只额外开放 TCP 80、TCP 443 和 UDP 443。
3. 在服务器中安装 Git 和 Docker Compose 插件。

## 部署

```bash
git clone --branch codex/tencent-hk https://github.com/hllwld/ai-resume-screening.git
cd ai-resume-screening/deploy/tencent
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
docker compose logs --tail=100
```

`.env` 中必须替换 `APP_DOMAIN`、`DIFY_API_KEY`、`APP_ACCESS_CODE` 和
`SESSION_SECRET`。不要提交 `.env`。

健康检查地址：

```text
https://zerodot.top/api/health
```

更新应用：

```bash
git pull --ff-only
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f --tail=200 app caddy
```
