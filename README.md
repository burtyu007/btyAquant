# Quant Platform

前后端分离的量化平台示例项目：

- 后端：FastAPI + SQLAlchemy + MySQL 8
- 前端：Vue 3 + Vite
- 数据：mx skills（东方财富妙想 API）
- 当前策略：布林带均值回归

## 目录

- `backend/`：FastAPI 后端
- `frontend/`：Vue 3 前端

## 数据库

默认连接：

- Host: `127.0.0.1`
- Port: `3380`
- User: `root`
- Password: `Burtyu1989`
- Database: `quant`

系统启动后会自动建表，并创建默认管理员：

- 用户名：`admin`
- 密码：`admin`

## 后端启动

```bash
cd .../backend
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 前端启动

```bash
cd .../frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

## 当前功能

- 管理员登录与用户管理
- 每个用户只能查看自己的分析记录和自选股票
- 每个用户最多 50 只自选股票
- 手动刷新自选股当前价格
- 左侧财经热点新闻
- 股票代码输入后返回策略结果
- 预留多策略扩展入口，当前启用 `bollinger_mean_reversion`
