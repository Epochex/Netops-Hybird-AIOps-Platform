# Edge 侧组件

## 目录职责

这个目录只放边缘节点相关的组件和部署入口，不承载核心分析或前端逻辑。

- `edge/deployments`：边缘命名空间和边缘侧资源清单
- `edge/fortigate-ingest`：FortiGate 日志接入、解析、checkpoint 与 JSONL 输出
- `edge/edge_forwarder`：把解析后的 JSONL 事实事件送入 Kafka 原始事实 Topic

## 当前边界

边缘侧的职责很明确：

- 接住原始设备日志
- 把文件语义、轮转语义和回放语义处理干净
- 输出结构化事实
- 把结构化事实送到 `netops.facts.raw.v1`

边缘侧不负责：

- 核心侧规则判断
- 告警生成
- AIOps 建议
- 前端运行台表达

## 基线部署

```bash
kubectl apply -f edge/deployments/00-edge-namespace.yaml
kubectl apply -f edge/fortigate-ingest/ingest_pod.yaml
kubectl apply -f edge/edge_forwarder/deployments/30-edge-forwarder.yaml
```

## 发布脚本

```bash
./edge/fortigate-ingest/scripts/deploy_ingest.sh
./edge/edge_forwarder/scripts/deploy_edge_forwarder.sh
```
