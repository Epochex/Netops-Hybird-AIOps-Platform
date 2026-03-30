# Frontend

这个目录是独立的前端工作区，与 `core/`、`edge/` 和 `documentation/` 并列存在。

## 为什么单独拆一个 `frontend/`

这是当前阶段更诚实的工程形态。

- `core/` 专注确定性数据面和 AIOps 运行模块
- `edge/` 专注日志接入与转发
- `frontend/` 可以在不污染后端边界的前提下独立演进
- UI 有自己的依赖、构建流程和交互节奏

这样做的结果是：运行时处理逻辑不会和展示层代码混成一团。

## 当前范围

前端当前不是一个通用后台模板，而是一个围绕真实后端链路组织的信息界面：

- `FortiGate -> edge ingest -> edge-forwarder -> netops.facts.raw.v1`
- `core-correlator -> netops.alerts.v1`
- `core-alerts-sink / ClickHouse`
- `core-aiops-agent -> netops.aiops.suggestions.v1`
- 显式保留的 remediation boundary

主要界面块都对应仓库里已经存在的真实运行对象：

- 全局运行态概览
- Event Flow / Pipeline Topology
- Runtime Chain
- Evidence Drawer
- Cluster Pre-Trigger Watch

## 常用命令

当前工作区依赖 `/data/.local/node` 下的 Node 工具链。
薄网关的 Python 依赖可以装到本地目标目录，不污染既有后端环境。

```bash
PATH=/data/.local/node/bin:$PATH npm install
python3 -m pip install --target /data/.local/netops-console-py -r frontend/gateway/requirements.txt

PATH=/data/.local/node/bin:$PATH npm run dev
PATH=/data/.local/node/bin:$PATH npm run dev:gateway
PATH=/data/.local/node/bin:$PATH npm run build
```

本地开发默认使用：

- 前端 UI：`:5173`
- FastAPI 网关：`:8026`
- 通过 Vite 代理 `/api`

## 运行时形态

前端现在不再只是静态页面。

- `GET /api/runtime/snapshot` 返回当前 `RuntimeSnapshot`
- `GET /api/runtime/stream` 通过 `SSE` 推送更新
- 网关会读取 `/data/netops-runtime` 和仓库中的 deployment 环境变量

React 应用仍然保留一份本地静态 snapshot 作为保底 fallback，但真实运行态优先来自网关投影。

## 部署建议

当前阶段最省事、也最符合实际的路径仍然是：

- 本地 Vite 开发服务器
- 本地 FastAPI 薄网关
- 不急着先把前端塞进 k3s

原因很简单：

- 当前前端语义还在围绕真实后端行为持续收敛
- 布局、交互和证据映射在宿主机上迭代更快
- 网关本身是只读、很薄，过早引入集群部署复杂度收益不高

当需要共享或评审环境时，推荐的宿主机形态是：

- 前端先构建静态资源
- `nginx` 暴露 `:2026`
- `uvicorn/FastAPI` 在内部 `:8026`

## 技术栈

- `React + Vite + TypeScript`
- `ECharts`
- `React Flow`
- `FastAPI + SSE`
- `nginx + systemd`
- `PyYAML`
- `Docker + k3s Deployment` 作为可选封装层

## 设计方向

当前界面的方向是明确的：

- 以过程为中心，而不是以指标卡片为中心
- 以现场判断为中心，而不是以装饰性视觉为中心
- 明确区分 live、inferred 和 boundary
- 不把尚未落地的执行能力包装成“已经存在”
