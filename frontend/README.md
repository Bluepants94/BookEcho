# BookEcho Frontend

Vue 3 + Vite + Vue Router + Pinia 听书前端（用户端 + 管理端）。

## 本地开发

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：`http://127.0.0.1:5173`  
`/api` 会代理到 `http://127.0.0.1:8000`。

## 构建

```bash
npm run build
```

产物在 `dist/`。

## Docker

```bash
docker build -t bookecho-frontend .
```

`nginx.conf` 会将 `/api/` 反代到 compose 服务 `api:8000`。

## 安全与可见性

- TTS Key 只保存在浏览器本地；播放时由后端按次代理 TTS（内存使用，不落库不落盘）
- 公共书对登录用户可见；普通用户上传默认为私有，仅管理员可选择发布为公共