# BookEcho

本地优先的有声书 / 阅读播放工具。

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

数据卷保留时，SQLite 与书籍文件不会丢失；若要一并清除数据：

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
- 私有书架：书籍仅本人可见；公共书库（`public`）已移除
- Web 前端：浏览器访问阅读界面（Vue + Vite）
- TTS 配置：经 `/api/auth/tts-settings` **按用户加密写入服务端**；API 响应中的 Key 脱敏；浏览器本地缓存完整 Key 供播放使用
- 上传解析：书籍上传后**异步解析**（`jobs`）；详情页会轮询直到章节就绪（测试可设 `PARSE_INLINE=true` 同步解析）
- 章节进入：点击章节**立即进入播放页并展示正文**；TTS 音频异步加载，不阻塞正文渲染
- 播放控件：音频未就绪时，播放页主按钮与迷你播放器按钮显示转圈加载态
- 播放时 TTS：前端按次将当前 TTS 配置提交给后端；后端在请求生命周期内代理第三方 TTS，不缓存合成音频（浏览器可做章节音频缓存）
- 限流：登录/注册与 TTS 代理有进程内滑动窗口限流

## 安全说明

- TTS API Key **按用户加密保存在服务端数据库**（`users.tts_settings_json`，`enc:` + Fernet，密钥派生自 `SECRET_KEY`/`JWT_SECRET`）
- 读取 TTS 设置接口返回**脱敏 Key**；空值或脱敏占位不会覆盖已保存密钥
- 前端在 hydrate / 保存后若服务端回传脱敏 Key，会优先保留浏览器本地完整 Key，避免播放配置被冲掉
- 不要把 TTS Key 写进 `.env`、`docker-compose.yml` 或镜像构建参数
- 播放合成时，Key 随当次 TTS 代理请求提交；后端仅内存转发，不把合成音频落盘
- 删除用户会清理其书籍记录、播放进度与磁盘目录
- `JWT_SECRET` 同步映射为后端 `SECRET_KEY`
- 生产环境请：
  - 使用足够长且随机的 `JWT_SECRET`
  - 修改默认管理员密码
  - 按实际域名收紧 `CORS_ORIGINS`
  - 在反向代理层启用 HTTPS
  - 保护 SQLite / 数据卷备份（含加密后的用户 TTS 配置）
  - 避免不必要地对外暴露 `56418`（优先只暴露 web `25698`）

## 架构与数据流

```text
Browser (Vue3 + Pinia)
  ├─ 书架 / 上传 / 设置 / 播放页 / 迷你播放器
  ├─ localStorage：完整 TTS Key + 音频缓存元数据
  └─ /api 反代 ──► FastAPI
                     ├─ SQLite（用户、书籍、章节、进度、加密 TTS 配置、jobs）
                     ├─ 文件：DATA_DIR/users/{uid}/books/{bid}/
                     └─ 按次代理第三方 TTS（内存转发，限流）
```

## 目录结构

```text
BookEcho/
├── backend/                   # 后端 API
│   └── Dockerfile
├── frontend/                  # 前端 Web
│   ├── Dockerfile
│   └── nginx.conf             # 容器内 Nginx：静态资源 + /api 反代
├── deploy/                    # 额外部署配置（可选）
│   ├── nginx.web.conf         # 与 frontend/nginx.conf 同步的参考配置
│   └── nginx.bookecho.conf    # 宿主机 / 网关反代到 web:25698 的示例
├── docker-compose.yml         # 编排：api + web
├── .env.example               # 环境变量模板（不含 TTS Key）
└── README.md
```
