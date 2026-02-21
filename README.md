# Towards NetOps： AIOps Driven 分布式深度根因追踪与智能自动化处置系统

该项目旨在构建一个分布式架构的，面向复杂网络运维场景的分布式 AIOps 引擎，通过边缘事实日志沉淀与核心流式关联推理，实现异常因果追踪与证据驱动运维决策支持

## 1.1 项目定位与当前架构边界
项目当架构围绕 **r230（边缘采集）→ r450（核心数据平面与分析处理）** 展开，即在边缘侧完成近源采集与事实化，在核心侧承载后续流式处理、关联分析、证据链归因与自动化处置能力的实现。意味着本项目已完成平台建设中最关键的输入面落地工作，并进入面向核心能力扩展的架构推进阶段。

当前处于 **边缘事实接入层（Edge Fact Ingestion Layer）已部署并稳定运行**、**核心分析与处置层（Core Analytics / Causality / Remediation）持续建设中** 的阶段。系统运行于 **k3s** 集群；其中 `edge` 边缘侧 `fortigate-ingest` 组件 已完成容器化部署并持续运行，承担 FortiGate 日志的边缘侧接入与事实化处理任务。当前节点角色划分为：**netops-node2（r230）负责边缘接入**，**netops-node1（r450）作为核心数据平面与分析侧承载节点**。已进入集群运行态的 AIOps 平台基础组件阶段。

> [!IMPORTANT]
> 当前阶段的架构重点是以已运行的边缘接入组件为基础，向核心侧数据平面与分析能力扩展

节点角色划分如下：
- **netops-node2（r230）**：边缘接入侧（Edge Ingestion，已完成Ingest Pod开发与部署，并稳定运行）
- **netops-node1（r450）**：核心侧（Data Plane / Core Analytics，正在持续建设中）




## 1.2 当前已开发组件（Edge / FortiGate Ingestion）
`edge/fortigate-ingest` 已在 k3s 集群中完成容器化部署并持续运行，当前承担以下职责：

- 接入 FortiGate syslog 输入（active log + rotated log，含 `.gz`）
- 按既定顺序处理历史补偿与准实时跟读（rotated → active）
- 解析 syslog header 与 FortiGate `key=value` payload
- 完成字段类型标准化与结构化事件生成
- 输出可直接消费的事实事件流（JSONL）
- 输出 DLQ 与 ingest metrics（用于异常样本隔离与运行状态观测）
- 持久化 checkpoint（含 `inode/offset` 与 completed 去重账本），支持重启恢复、轮转处理与可追溯回放定位

当前边缘侧已经基于总体环境路由器形成稳定的 **事实事件生产链路**，为后续核心侧流式消费、关联分析与根因推理提供统一输入


---
## 2. Edge 边缘侧 组件
### 2.1 Ingest 组件  
> ## FortiGate Log Input / Ingest / Parsed Output Specification
原始日志（`/data/fortigate-runtime/input/fortigate.log`）格式分析
FortiGate 日志输入格式、结构化事件输出格式（JSONL）、字段语义及 ingest 处理链路，用于数据接入、分析开发、排障审计与后续流式处理对接。

### 2.1.1 Raw FortiGate Log Format (Input)
`edge/fortigate-ingest` 的输入不是单一文件，而是 **同一目录下的一组 FortiGate 日志文件集合**：当前持续追加写入的 active 文件 `fortigate.log`，以及由外部轮转机制生成的历史文件 `fortigate.log-YYYYMMDD-HHMMSS` 和 `fortigate.log-YYYYMMDD-HHMMSS.gz`。ingest 在启动与主循环中会先扫描并按文件名时间戳顺序处理所有匹配命名规则的 rotated 文件（用于补齐历史日志），随后再基于 checkpoint 中记录的 `active.inode + active.offset` 对 `fortigate.log` 执行增量 tail（用于准实时接入新日志）。rotated 文件采用整文件读取（`.gz` 通过 gzip 解压后逐行读取，`source.offset=null`；非 `.gz` rotated 记录逐行 offset），active 文件采用按字节 offset 的持续跟读；在运行过程中，主循环会周期性重新扫描 rotated 列表并结合 `completed(path|inode|size|mtime)` 去重账本避免重复补历史，同时对 active 文件通过 `inode` 变化与文件大小/offset 状态处理轮转切换与截断恢复。该处理模型的职责边界是：**ingest 负责识别并消费 active/rotated 输入集合，外部组件负责产生日志轮转文件**。

- **Active log**
  - `/data/fortigate-runtime/input/fortigate.log`
- **Rotated logs**
  - `/data/fortigate-runtime/input/fortigate.log-YYYYMMDD-HHMMSS`
  - `/data/fortigate-runtime/input/fortigate.log-YYYYMMDD-HHMMSS.gz`

### Line Format

每行日志由两部分组成：
*Input sample（raw）**：证明原始日志具备可直接抽取的网络语义 + 资产画像语义（接口、策略、动作、设备厂商/类型/OS/MAC）
1. **Syslog header** - 4 tokens 维度
2. **FortiGate key-value payload** - 43 维度
### Input log raw 字段清单（43 个FortiGate KV字段 + 4 个 syslog header 子字段）

**Example (real sample):**
```text
Feb 21 15:45:27 _gateway date=2026-02-21 time=15:45:26 devname="DAHUA_FORTIGATE" devid="FG100ETK20014183" logid="0001000014" type="traffic" subtype="local" level="notice" vd="root" eventtime=1771685127249713472 tz="+0100" srcip=192.168.16.41 srcname="es-73847E56DA65" srcport=48689 srcintf="LACP" srcintfrole="lan" dstip=255.255.255.255 dstport=48689 dstintf="unknown0" dstintfrole="undefined" sessionid=1211202700 proto=17 action="deny" policyid=0 policytype="local-in-policy" service="udp/48689" dstcountry="Reserved" srccountry="Reserved" trandisp="noop" app="udp/48689" duration=0 sentbyte=0 rcvdbyte=0 sentpkt=0 appcat="unscanned" srchwvendor="Samsung" devtype="Phone" srcfamily="Galaxy" osname="Android" srcswversion="16" mastersrcmac="78:66:9d:a3:4f:51" srcmac="78:66:9d:a3:4f:51" srcserver=0
```

Input 字段分析（
| 字段名            | 样本值                   | 作用                   |
| -------------- | --------------------- | -------------------- |
| `syslog_month` | `Feb`      | syslog 头时间（月份）  |
| `syslog_day`   | `21`       | syslog 头时间（日期）  |
| `syslog_time`  | `15:45:27` | syslog 接收时间（秒级） |
| `host`         | `_gateway` | syslog 发送主机名    |
| `date`         | `2026-02-21`          | FortiGate 事件日期（业务时间） |
| `time`         | `15:45:26`            | FortiGate 事件时间（业务时间） |
| `devname`      | `DAHUA_FORTIGATE`     | 防火墙设备名               |
| `devid`        | `FG100ETK20014183`    | 防火墙设备唯一 ID           |
| `logid`        | `0001000014`          | FortiGate 日志类型 ID    |
| `type`         | `traffic`             | 日志主类（流量类）            |
| `subtype`      | `local`               | 日志子类（本机面 traffic）    |
| `level`        | `notice`              | 事件等级                 |
| `vd`           | `root`                | VDOM 名称              |
| `eventtime`    | `1771685127249713472` | 高精度原生事件时间戳           |
| `tz`           | `+0100`               | 时区                   |
| `srcip`        | `192.168.16.41`       | 源 IP                 |
| `srcname`      | `es-73847E56DA65`     | 源端名称/终端标识            |
| `srcport`      | `48689`               | 源端口                  |
| `srcintf`      | `LACP`                | 源接口                  |
| `srcintfrole`  | `lan`                 | 源接口角色                |
| `dstip`        | `255.255.255.255`     | 目的 IP（广播地址）          |
| `dstport`      | `48689`               | 目的端口                 |
| `dstintf`      | `unknown0`            | 目的接口（本机面/特殊目标线索）     |
| `dstintfrole`  | `undefined`           | 目的接口角色               |
| `sessionid`    | `1211202700`          | 会话 ID（关联键）           |
| `proto`        | `17`                  | 协议号（UDP）             |
| `action`       | `deny`                | 动作结果（拒绝）             |
| `policyid`     | `0`                   | 策略 ID                |
| `policytype`   | `local-in-policy`     | 命中策略类型（本机面）          |
| `service`      | `udp/48689`           | 服务/端口标签              |
| `dstcountry`   | `Reserved`            | 目的国家（保留地址）           |
| `srccountry`   | `Reserved`            | 源国家（保留地址）            |
| `trandisp`     | `noop`                | 传输/处理状态信息            |
| `app`          | `udp/48689`           | 应用识别结果（端口级）          |
| `duration`     | `0`                   | 会话持续时长               |
| `sentbyte`     | `0`                   | 发送字节数                |
| `rcvdbyte`     | `0`                   | 接收字节数                |
| `sentpkt`      | `0`                   | 发送包数                 |
| `appcat`       | `unscanned`           | 应用分类状态               |
| `srchwvendor`  | `Samsung`             | 源端硬件厂商（资产画像）         |
| `devtype`      | `Phone`               | 设备类型（资产画像）           |
| `srcfamily`    | `Galaxy`              | 设备家族（资产画像）           |
| `osname`       | `Android`             | OS 名称（资产画像）          |
| `srcswversion` | `16`                  | OS/软件版本（资产画像）        |
| `mastersrcmac` | `78:66:9d:a3:4f:51`   | 主源 MAC（设备归一线索）       |
| `srcmac`       | `78:66:9d:a3:4f:51`   | 源 MAC（设备归一线索）        |
| `srcserver`    | `0`                   | 设备角色提示（终端/非服务器）      |


### 2.1.2 Ingest Pod 处理链路（`edge/fortigate-ingest`）

`edge/fortigate-ingest` 的职责不是“简单转存日志”，而是将 FortiGate 原始 syslog 文本（`/data/fortigate-runtime/input/fortigate.log` 及轮转文件 `fortigate.log-YYYYMMDD-HHMMSS[.gz]`）转换为可审计、可回放、可直接做聚合分析的结构化事实事件流（JSONL）。主循环处理顺序固定为 **先 rotated（补历史）→ 再 active（准实时 tail）**：轮转文件通过文件名时间戳排序后依次扫描，避免启动/重启后漏补历史；active 文件则基于 byte offset 持续跟读，兼顾实时性与可恢复性。输出按小时切分写入 `events-YYYYMMDD-HH.jsonl`（另有 DLQ/metrics JSONL），便于下游批流统一消费。:contentReference[oaicite:0]{index=0} :contentReference[oaicite:1]{index=1}

处理单行日志时，pipeline 会先拆分 **syslog header** 与 **FortiGate key=value payload**，再执行字段解析与类型标准化（数值类字段转 `int`，缺失字段保留为 `null`），并生成结构化事件：包括标准化 `event_ts`（优先 `date+time+tz`）、保留原始时间语义字段（如 `eventtime`/`tz`）、派生统计字段（如 `bytes_total` / `pkts_total`）、设备归一化键（`src_device_key`，用于资产级聚合/异常关联），以及用于回溯与 schema 扩展的 `kv_subset`。成功解析的事件写入 `events-*.jsonl`，失败行进入 DLQ（附带 `reason/raw/source`），从而保证“原始文本 → 结构化事件”的转换链路具备容错与排障能力。:contentReference[oaicite:2]{index=2} :contentReference[oaicite:3]{index=3}

该组件的关键可靠性设计在于 **checkpoint + inode/offset + completed 去重机制**。`checkpoint.json` 保存三类状态：`active`（当前 active 文件的 `path/inode/offset/last_event_ts_seen`）、`completed`（已完整处理的轮转文件记录，使用 `path|inode|size|mtime` 组成唯一 key，防止重复补历史）、`counters`（lines/bytes/events/dlq/parse_fail/write_fail/checkpoint_fail 等累计计数）。rotated 文件完成后调用 `mark_completed()` 落账；active 文件 tail 时使用 checkpoint 中的 `inode+offset` 从断点续读，并在检测到 **inode 变化（轮转切换）** 或 **文件截断（`size < offset`）** 时执行 offset 重置与重新扫描，避免越界/重复/漏读。checkpoint 通过临时文件写入 + `fsync` + `os.replace` 原子落盘，事件侧统一附加 `ingest_ts`（UTC）与 `source.path/inode/offset`（`.gz` 通常 `offset=null`），从而支持精确审计、回放定位与幂等重处理。:contentReference[oaicite:4]{index=4} :contentReference[oaicite:5]{index=5} :contentReference[oaicite:6]{index=6}


### 2.1.3 Output Sample（parsed JSONL）字段清单（62 个顶层字段+3个source 子字段）
**Output sample（parsed）**：证明 ingest 已把文本日志稳定转换为可分析 schema（时间标准化、派生字段、设备键、source审计元数据

```text
{"schema_version":1,"event_id":"d811b6b7c362dd6367f3736a19bc9ade","host":"_gateway","event_ts":"2026-01-15T16:49:21+01:00","type":"traffic","subtype":"forward","level":"notice","devname":"DAHUA_FORTIGATE","devid":"FG100ETK20014183","vd":"root","action":"deny","policyid":0,"policytype":"policy","sessionid":1066028432,"proto":17,"service":"udp/3702","srcip":"192.168.1.133","srcport":3702,"srcintf":"fortilink","srcintfrole":"lan","dstip":"192.168.2.108","dstport":3702,"dstintf":"LAN2","dstintfrole":"lan","sentbyte":0,"rcvdbyte":0,"sentpkt":0,"rcvdpkt":null,"bytes_total":0,"pkts_total":0,"parse_status":"ok","logid":"0000000013","eventtime":"1768492161732986577","tz":"+0100","logdesc":null,"user":null,"ui":null,"method":null,"status":null,"reason":null,"msg":null,"trandisp":"noop","app":null,"appcat":"unscanned","duration":0,"srcname":null,"srccountry":"Reserved","dstcountry":"Reserved","osname":null,"srcswversion":null,"srcmac":"b4:4c:3b:c1:29:c1","mastersrcmac":"b4:4c:3b:c1:29:c1","srcserver":0,"srchwvendor":"Dahua","devtype":"IP Camera","srcfamily":"IP Camera","srchwversion":"DHI-VTO4202FB-P","srchwmodel":null,"src_device_key":"b4:4c:3b:c1:29:c1","kv_subset":{"date":"2026-01-15","time":"16:49:21","tz":"+0100","eventtime":"1768492161732986577","logid":"0000000013","type":"traffic","subtype":"forward","level":"notice","vd":"root","action":"deny","policyid":"0","policytype":"policy","devname":"DAHUA_FORTIGATE","devid":"FG100ETK20014183","sessionid":"1066028432","proto":"17","service":"udp/3702","srcip":"192.168.1.133","srcport":"3702","srcintf":"fortilink","srcintfrole":"lan","dstip":"192.168.2.108","dstport":"3702","dstintf":"LAN2","dstintfrole":"lan","trandisp":"noop","duration":"0","sentbyte":"0","rcvdbyte":"0","sentpkt":"0","appcat":"unscanned","dstcountry":"Reserved","srccountry":"Reserved","srcmac":"b4:4c:3b:c1:29:c1","mastersrcmac":"b4:4c:3b:c1:29:c1","srcserver":"0","srchwvendor":"Dahua","devtype":"IP Camera","srcfamily":"IP Camera","srchwversion":"DHI-VTO4202FB-P"},"ingest_ts":"2026-02-16T19:59:59.808411+00:00","source":{"path":"/data/fortigate-runtime/input/fortigate.log-20260130-000004.gz","inode":6160578,"offset":null}}
```
| 字段名              | 样本值                                            | 作用                         |
| ---------------- | ---------------------------------------------- | -------------------------- |
| `source.path`   | `/data/fortigate-runtime/input/fortigate.log-20260130-000004.gz` | 来源文件路径（轮转文件定位） |
| `source.inode`  | `6160578`                                                        | 文件 inode（文件身份） |
| `source.offset` | `null`                                                           | 偏移量（压缩文件常为空）   |
| `schema_version` | `1`                                            | 输出 schema 版本               |
| `event_id`       | `d811b6b7c362dd6367f3736a19bc9ade`             | 事件唯一 ID（去重/幂等）             |
| `host`           | `_gateway`                                     | 保留 syslog host             |
| `event_ts`       | `2026-01-15T16:49:21+01:00`                    | 标准化事件时间（下游窗口/排序主字段）        |
| `type`           | `traffic`                                      | 日志主类                       |
| `subtype`        | `forward`                                      | 日志子类（转发流量）                 |
| `level`          | `notice`                                       | 事件等级                       |
| `devname`        | `DAHUA_FORTIGATE`                              | 防火墙设备名                     |
| `devid`          | `FG100ETK20014183`                             | 防火墙设备 ID                   |
| `vd`             | `root`                                         | VDOM                       |
| `action`         | `deny`                                         | 动作结果                       |
| `policyid`       | `0`                                            | 策略 ID                      |
| `policytype`     | `policy`                                       | 策略类型（普通转发策略）               |
| `sessionid`      | `1066028432`                                   | 会话关联键                      |
| `proto`          | `17`                                           | 协议号（UDP）                   |
| `service`        | `udp/3702`                                     | 服务/端口标签                    |
| `srcip`          | `192.168.1.133`                                | 源 IP                       |
| `srcport`        | `3702`                                         | 源端口                        |
| `srcintf`        | `fortilink`                                    | 源接口                        |
| `srcintfrole`    | `lan`                                          | 源接口角色                      |
| `dstip`          | `192.168.2.108`                                | 目的 IP                      |
| `dstport`        | `3702`                                         | 目的端口                       |
| `dstintf`        | `LAN2`                                         | 目的接口                       |
| `dstintfrole`    | `lan`                                          | 目的接口角色                     |
| `sentbyte`       | `0`                                            | 发送字节数                      |
| `rcvdbyte`       | `0`                                            | 接收字节数                      |
| `sentpkt`        | `0`                                            | 发送包数                       |
| `rcvdpkt`        | `null`                                         | 接收包数（可空）                   |
| `bytes_total`    | `0`                                            | 派生总字节数（便于聚合）               |
| `pkts_total`     | `0`                                            | 派生总包数（便于聚合）                |
| `parse_status`   | `ok`                                           | 解析状态                       |
| `logid`          | `0000000013`                                   | FortiGate 日志 ID            |
| `eventtime`      | `1768492161732986577`                          | 原生高精度事件时间                  |
| `tz`             | `+0100`                                        | 时区                         |
| `logdesc`        | `null`                                         | 原生日志描述（可空）                 |
| `user`           | `null`                                         | 用户字段（可空）                   |
| `ui`             | `null`                                         | UI/入口字段（可空）                |
| `method`         | `null`                                         | 方法/动作字段（可空）                |
| `status`         | `null`                                         | 状态字段（可空）                   |
| `reason`         | `null`                                         | 原因字段（可空）                   |
| `msg`            | `null`                                         | 文本消息字段（可空）                 |
| `trandisp`       | `noop`                                         | 传输/处理状态信息                  |
| `app`            | `null`                                         | 应用识别（可空）                   |
| `appcat`         | `unscanned`                                    | 应用分类状态                     |
| `duration`       | `0`                                            | 会话时长                       |
| `srcname`        | `null`                                         | 源端名称（可空）                   |
| `srccountry`     | `Reserved`                                     | 源国家/地址空间分类                 |
| `dstcountry`     | `Reserved`                                     | 目的国家/地址空间分类                |
| `osname`         | `null`                                         | OS 名称（可空）                  |
| `srcswversion`   | `null`                                         | 软件/OS 版本（可空）               |
| `srcmac`         | `b4:4c:3b:c1:29:c1`                            | 源 MAC                      |
| `mastersrcmac`   | `b4:4c:3b:c1:29:c1`                            | 主源 MAC                     |
| `srcserver`      | `0`                                            | 设备角色提示                     |
| `srchwvendor`    | `Dahua`                                        | 硬件厂商（资产画像）                 |
| `devtype`        | `IP Camera`                                    | 设备类型（资产画像）                 |
| `srcfamily`      | `IP Camera`                                    | 设备家族（资产画像）                 |
| `srchwversion`   | `DHI-VTO4202FB-P`                              | 硬件型号/版本（资产画像）              |
| `srchwmodel`     | `null`                                         | 硬件型号字段（可空）                 |
| `src_device_key` | `b4:4c:3b:c1:29:c1`                            | 归一化设备键（资产基线核心）             |
| `kv_subset`      | `{...}`                                        | 原始 KV 子集快照（回溯/校验/schema扩展） |
| `ingest_ts`      | `2026-02-16T19:59:59.808411+00:00`             | ingest 输出时间                |
| `source`         | `{"path":"...","inode":6160578,"offset":null}` | 输入来源元数据（审计/回放定位）           |






