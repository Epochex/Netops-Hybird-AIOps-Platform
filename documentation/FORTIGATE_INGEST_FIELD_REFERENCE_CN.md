# FortiGate 接入字段参考

这份说明把字段契约从根 README 里拆出来，专门讲解析、回放和下游分析真正依赖的部分。

## 这份文档解决什么问题

`edge/fortigate-ingest` 做的事不只是把 FortiGate syslog 切成若干 key。
它还必须同时满足四件后续工作：

- 能基于文件和偏移安全续跑
- 能把事件身份和时间字段规范化
- 能让 core 侧做确定性关联分析
- 能保留足够的来源信息，便于回放和审计

当前解析管线主要围绕下面这些文件：

- `edge/fortigate-ingest/bin/source_file.py`
- `edge/fortigate-ingest/bin/parser_fgt_v1.py`
- `edge/fortigate-ingest/bin/sink_jsonl.py`
- `edge/fortigate-ingest/bin/checkpoint.py`

## 输入形态

输入是 FortiGate syslog，通常会带着这些类型的字段：

- 时间字段：`date`、`time`、`eventtime`、`tz`
- 设备标识：`devname`、`devid`
- 流量身份：`srcip`、`srcport`、`dstip`、`dstport`、`proto`、`service`
- 判定字段：`action`、`policyid`、`policytype`
- 资产线索：`srcmac`、`mastersrcmac`、`srchwvendor`、`devtype`、`srcfamily`、`osname`

原始日志行本身很重要，但它还不能直接作为核心侧共享契约。

## 输出契约

输出是 JSONL，字段中真正被后续链路依赖的重点如下。

| 字段组 | 代表字段 | 作用 |
| --- | --- | --- |
| 回放与来源 | `source.path`、`source.inode`、`source.offset`、`ingest_ts` | 让 edge 侧能安全续跑，并解释一条事实事件来自哪里 |
| 稳定身份 | `event_id`、`src_device_key`、`sessionid` | 支撑去重、设备级聚合和后续关联 |
| 规范化时间 | `event_ts`、`eventtime`、`tz` | 给下游规则提供可排序、可回放的事件时间契约 |
| 网络语义 | `srcip`、`srcport`、`dstip`、`dstport`、`proto`、`service` | 保留关联规则真正依赖的流量形状 |
| 判定上下文 | `action`、`policyid`、`policytype`、`level`、`subtype` | 保留策略命中结果和流量类别 |
| 资产画像线索 | `srcmac`、`mastersrcmac`、`srchwvendor`、`devtype`、`srcfamily`、`srcswversion` | 供后续设备画像和定位使用 |
| 解析可追溯性 | `parse_status`、`kv_subset` | 保留紧凑的原始 KV 快照，便于校验和未来 schema 演进 |

## 为什么要保留 `src_device_key`

仓库需要一个能够跨回放、跨聚合、跨上下文查询持续工作的设备级键。
FortiGate 原始字段在不同场景下并不总是足够稳定，`src_device_key` 是当前阶段最实用的折中：它让后续模块可以围绕设备做重复行为分析、告警簇聚合和 incident 定位，而不必把整个 parser 状态一路带下去。

## 为什么要保留 `kv_subset`

解析后的 JSONL 是规范化契约，但系统仍然需要一条紧凑的回溯桥。
`kv_subset` 的意义就在这里。它不是主分析面，而是为了让 schema 演进、解析验证和事件复盘不至于每次都回头翻原始日志文件。

## 边界说明

这份文档只讲字段契约，不展开 parser 的全部实现细节。
如果需要系统级上下文，请先看根 README；如果需要看当前运行态，请看 [PROJECT_STATE_CN.md](./PROJECT_STATE_CN.md)。
