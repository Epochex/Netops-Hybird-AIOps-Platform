# NetOps 项目状态

- 最后更新：2026-03-30 UTC
- 本文范围：当前仓库状态、实时链路形态以及现阶段边界

## 当前目标

仓库当前已经不再停留在“证明原始日志能不能解析”这个层面。
现阶段主目标是把整条链路持续做稳：

1. FortiGate syslog 进入 edge 节点
2. edge ingest 把原始文本变成可回放的结构化事实
3. 事实流进入 Kafka，并转成确定性告警
4. 告警同时进入审计存储和热查询存储
5. AIOps 在告警契约之上产出有边界的建议
6. 前端运行台把这条链路投影成操作员可读的状态面

当前阶段的判断标准不是页面好不好看，而是下面这些事是否成立：

- 链路处理的是实时设备流量，而不是只靠 fixture
- 关键证据字段能否从 edge 一直进入 core alert
- 运行时输出既能从文件追溯，也能从 ClickHouse 查询
- 前端能否如实表达运行时路径，而不是假装已经具备执行控制面

## 实时链路

当前实时主路径是：

`FortiGate -> edge/fortigate-ingest -> edge/edge_forwarder -> netops.facts.raw.v1 -> core/correlator -> netops.alerts.v1 -> alerts_sink / alerts_store / aiops_agent -> netops.aiops.suggestions.v1 -> frontend runtime gateway`

几个关键运行态事实：

- edge ingest 读取 `/data/fortigate-runtime/input/fortigate.log*`
- 解析后的事实写入 `/data/fortigate-runtime/output/parsed/events-*.jsonl`
- 告警写入 `/data/netops-runtime/alerts/alerts-*.jsonl`
- 建议写入 `/data/netops-runtime/aiops/suggestions-*.jsonl`
- ClickHouse 保存热告警视图，供近期历史查询和 AIOps 上下文检索

## 当前已工作的部分

仓库里已经落地的内容包括：

- 可回放的 FortiGate 接入与结构化事实输出
- 进入 Kafka 原始事实 Topic 的 edge 转发
- 基于规则的确定性告警链路
- 告警 JSONL 审计落盘
- 基于 ClickHouse 的热告警存储
- 同时支持告警级和簇级的有边界建议链路
- 运行时网关与操作员控制台

当前仓库没有对外宣称的能力包括：

- 面向设备的自动化处置
- 会修改线上状态的审批流
- 生产级闭环执行平面
- 基于全量原始日志的一次性模型判定

## 当前约束

当前架构反映的是现实运行条件，而不是理想形态。

- 运行环境资源有限，推理不能被视为零成本热路径依赖
- 当前最重要的仍然是回放、审计和可定位性
- 前端是运行时投影层，不是控制平面
- JSONL 和 ClickHouse 必须并存，因为审计和热检索是两件不同的事

## 相关文档

- [FortiGate 接入字段参考](./FORTIGATE_INGEST_FIELD_REFERENCE_CN.md)
- [前端运行时架构](./FRONTEND_RUNTIME_ARCHITECTURE_20260328_CN.md)
- [核心模块 README](../core/README_CN.md)
- [边缘模块 README](../edge/README_CN.md)
- [前端模块 README](../frontend/README_CN.md)
