# BookEcho

本地优先的有声书 / 阅读回声工具。后端提供鉴权、书库与按次 TTS 代理；前端负责阅读体验，并将 TTS Key 保存在浏览器本地。

## 快速开始

前置：已安装 [Docker](https://docs.docker.com/get-docker/) 与 Docker Compose。

```bash
# 1. 进入项目根目录
cd BookEcho

# 2. 准备环境变量
cp .env.example .env
# 建议修改 JWT_SECRET 与 BOOTSTRAP_ADMIN_PASSWORD

# 3. 构建并启动
docker compose up -d --build
```

启动后：

| 服务 | 地址 |
|------|------|
| 前端 Web | http://localhost:25698 |
| 后端 API（直连） | http://localhost:56418 |
| 经前端反代的 API | http://localhost:25698/api |

停止：

```bash
docker compose down
```

数据卷保留时，SQLite 数据不会丢失；若要一并清除数据：

```bash
docker compose down -v
```

## 默认管理员

来自 `.env.example` / `.env` 中的引导账号：

- 用户名：`admin`
- 密码：`admin123`

首次部署后请立即修改密码，并更换 `JWT_SECRET`。

## 功能说明

- 账号体系：JWT 登录鉴权，支持引导管理员（`BOOTSTRAP_ADMIN_*`）
- 书库与进度：服务端使用 SQLite 持久化（`DATABASE_URL`，默认 `/data/bookecho.db`）
- 用户书籍源文件：按用户/书籍落盘到 `DATA_DIR/users/{user_id}/books/{book_id}/`（默认 `data/`）
- 私有书架：书籍仅本人可见；公共书库（`public`）已移除，不再对其他登录用户共享
- Web 前端：浏览器访问阅读界面（Vue + Vite）
- 浏览器侧 TTS 配置：用户自备 TTS Key / 模型参数，仅保存在浏览器本地
- 播放时 TTS：前端按次将配置随请求提交给后端；后端**仅内存中**代理调用第三方 TTS，音频响应返回后即结束，**不落库、不落盘**

## 安全说明

- **TTS / 语音 API Key 只保存在用户浏览器本地**（如 `localStorage`），不写入服务端配置文件、环境变量或数据库
- 播放合成时，Key 会随**当次** TTS 代理请求提交给后端；后端仅在请求生命周期的**内存**中使用该 Key 转发第三方 TTS，**不落库、不落盘、不写入服务端持久配置**
- 服务端业务库只处理账号、书库、进度等业务数据与鉴权，不持久化第三方 TTS 密钥或合成音频
- `JWT_SECRET` 会同步映射为后端 `SECRET_KEY`
- 生产环境请：
  - 使用足够长且随机的 `JWT_SECRET`
  - 修改默认管理员密码
  - 按实际域名收紧 `CORS_ORIGINS`
  - 在反向代理层启用 HTTPS

## 目录结构

```text
BookEcho/
├── backend/                 # 后端 API
│   └── Dockerfile
├── frontend/                # 前端 Web
│   ├── Dockerfile
│   └── nginx.conf           # 容器内 Nginx：静态资源 + /api 反代
├── deploy/                  # 额外部署配置（可选）
│   └── nginx.web.conf       # 与 frontend/nginx.conf 同步的参考配置
├── docker-compose.yml       # 编排：api + web
├── .env.example             # 环境变量模板（无 TTS Key）
└── README.md
```
