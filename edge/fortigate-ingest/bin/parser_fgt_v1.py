# FILE: Netops-causality-remediation/edge/fortigate-ingest/bin/parser_fgt_v1.py
import datetime
import hashlib
import re
from typing import Any, Dict, Optional, Tuple

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}

SYSLOG_RE = re.compile(
    r"^(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<body>.*)$"
)

# 只保留“对安全/流量分析有价值、且常见”的 KV 子集，避免无限膨胀输出
# 注意：这里把“设备识别/资产感知”相关字段补全，以支持后续 R450 态势感知/画像。
KV_SUBSET_KEYS = [
    # 时间/标识
    "date", "time", "tz", "eventtime", "logid",

    # 通用分类
    "type", "subtype", "level", "vd", "action", "policyid", "policytype",

    # 资产/设备
    "devname", "devid",

    # 连接/会话
    "sessionid", "proto", "service", "srcip", "srcport", "srcintf", "srcintfrole",
    "dstip", "dstport", "dstintf", "dstintfrole", "trandisp", "duration",

    # 计数
    "sentbyte", "rcvdbyte", "sentpkt", "rcvdpkt",

    # 应用识别
    "app", "appcat",

    # 端点/地理/身份（经常用于溯源/资产识别）
    "srcname", "dstcountry", "srccountry", "osname", "srcswversion",
    "srcmac", "mastersrcmac", "srcserver",

    # 资产指纹（你日志里实际会出现）
    "srchwvendor", "devtype", "srcfamily", "srchwversion", "srchwmodel",

    # 管理/认证类（system event）
    "user", "status", "reason", "msg", "logdesc", "ui", "method",
]

def _has_binary_garbage(s: str) -> bool:
    if "\x00" in s:
        return True
    bad = sum(1 for ch in s if ord(ch) < 9 or (11 <= ord(ch) < 32))
    return bad > 5

def parse_kv(body: str) -> Dict[str, str]:
    """
    Parse FortiGate kv pairs: key=value or key="value with spaces"
    Supports backslash-escaped quotes inside quoted values.
    """
    out: Dict[str, str] = {}
    i = 0
    n = len(body)

    while i < n:
        while i < n and body[i] == " ":
            i += 1
        if i >= n:
            break

        k_start = i
        while i < n and body[i] not in "= ":
            i += 1
        key = body[k_start:i]
        if not key or i >= n or body[i] != "=":
            break
        i += 1  # skip '='

        if i < n and body[i] == '"':
            i += 1
            v_chars = []
            while i < n:
                ch = body[i]
                if ch == "\\" and i + 1 < n:
                    v_chars.append(body[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    i += 1
                    break
                v_chars.append(ch)
                i += 1
            value = "".join(v_chars)
            while i < n and body[i] == " ":
                i += 1
        else:
            v_start = i
            while i < n and body[i] != " ":
                i += 1
            value = body[v_start:i]
            while i < n and body[i] == " ":
                i += 1

        out[key] = value

    return out

def parse_event_ts(
    kv: Dict[str, str],
    default_year: int,
    fallback_mon: int,
    fallback_day: int,
    fallback_time: str
) -> Optional[str]:
    """
    event_ts 优先使用 kv 中的 date/time/tz 组合；如果解析失败，回退到 syslog 头的 月/日/时间。
    event_ts 保持 ISO8601 字符串。
    """
    tz = kv.get("tz")
    if tz:
        tz_clean = tz.strip().strip('"')
        if re.fullmatch(r"[+-]\d{4}", tz_clean):
            tz_norm = tz_clean[:3] + ":" + tz_clean[3:]
        else:
            tz_norm = None
    else:
        tz_norm = None

    date_s = kv.get("date")  # YYYY-MM-DD
    time_s = kv.get("time")  # HH:MM:SS
    if date_s and time_s:
        try:
            dt = datetime.datetime.fromisoformat(f"{date_s}T{time_s}")
            if tz_norm:
                sign = 1 if tz_norm[0] == "+" else -1
                hh = int(tz_norm[1:3])
                mm = int(tz_norm[4:6])
                return dt.replace(
                    tzinfo=datetime.timezone(datetime.timedelta(hours=sign * hh, minutes=sign * mm))
                ).isoformat()
            return dt.isoformat()
        except Exception:
            pass

    try:
        hh, mm, ss = [int(x) for x in fallback_time.split(":")]
        dt = datetime.datetime(default_year, fallback_mon, fallback_day, hh, mm, ss)
        if tz_norm:
            sign = 1 if tz_norm[0] == "+" else -1
            h = int(tz_norm[1:3])
            m = int(tz_norm[4:6])
            return dt.replace(
                tzinfo=datetime.timezone(datetime.timedelta(hours=sign * h, minutes=sign * m))
            ).isoformat()
        return dt.isoformat()
    except Exception:
        return None

def stable_event_id(raw_line: str) -> str:
    h = hashlib.sha256(raw_line.encode("utf-8", errors="replace")).hexdigest()
    return h[:32]

def _to_int(x: Optional[str]) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        return None

def _pick_kv_subset(kv: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k in KV_SUBSET_KEYS:
        v = kv.get(k)
        if v is not None:
            out[k] = v
    return out

def _bytes_total(sent: Optional[int], rcvd: Optional[int]) -> Optional[int]:
    if sent is None and rcvd is None:
        return None
    return int(sent or 0) + int(rcvd or 0)

def _pkts_total(sentpkt: Optional[int], rcvdpkt: Optional[int]) -> Optional[int]:
    if sentpkt is None and rcvdpkt is None:
        return None
    return int(sentpkt or 0) + int(rcvdpkt or 0)

def _device_key(kv: Dict[str, str]) -> Optional[str]:
    """
    尽量稳定地把事件归属到“设备/终端”，用于后续 R450 聚合：
    优先 mac，其次 mastersrcmac，其次 srcname，其次 srcip。
    """
    for k in ["srcmac", "mastersrcmac", "srcname", "srcip"]:
        v = kv.get(k)
        if v:
            return v
    return None

def parse_fortigate_line(raw_line: str, now_year: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Return (event, dlq). One of them is None.

    Notes:
    - Event output does NOT include full raw line to avoid output amplification.
    - DLQ keeps raw for debugging/forensics.
    - schema_version=1 保持不变；新增字段均为可选（None 或缺失不会破坏旧消费方）。
    """
    line = raw_line.rstrip("\n")
    if not line:
        return None, {"reason": "empty_line", "raw": raw_line}

    if _has_binary_garbage(line):
        return None, {"reason": "non_text_or_binary", "raw": raw_line}

    m = SYSLOG_RE.match(line)
    if not m:
        return None, {"reason": "syslog_header_parse_fail", "raw": raw_line}

    mon = m.group("mon")
    day = int(m.group("day"))
    tstr = m.group("time")
    host = m.group("host")
    body = m.group("body")

    mon_i = MONTHS.get(mon)
    if not mon_i:
        return None, {"reason": "invalid_month", "raw": raw_line}

    try:
        kv = parse_kv(body)
    except Exception:
        return None, {"reason": "kv_parse_exception", "raw": raw_line}

    event_ts = parse_event_ts(kv, now_year, mon_i, day, tstr)

    sentbyte = _to_int(kv.get("sentbyte"))
    rcvdbyte = _to_int(kv.get("rcvdbyte"))
    sentpkt = _to_int(kv.get("sentpkt"))
    rcvdpkt = _to_int(kv.get("rcvdpkt"))

    # 基础字段（保持原字段不变）
    event: Dict[str, Any] = {
        "schema_version": 1,
        "event_id": stable_event_id(raw_line),
        "host": host,
        "event_ts": event_ts,

        "type": kv.get("type"),
        "subtype": kv.get("subtype"),
        "level": kv.get("level"),

        "devname": kv.get("devname"),
        "devid": kv.get("devid"),
        "vd": kv.get("vd"),

        "action": kv.get("action"),
        "policyid": _to_int(kv.get("policyid")),
        "policytype": kv.get("policytype"),

        "sessionid": _to_int(kv.get("sessionid")),
        "proto": _to_int(kv.get("proto")),
        "service": kv.get("service"),

        "srcip": kv.get("srcip"),
        "srcport": _to_int(kv.get("srcport")),
        "srcintf": kv.get("srcintf"),
        "srcintfrole": kv.get("srcintfrole"),

        "dstip": kv.get("dstip"),
        "dstport": _to_int(kv.get("dstport")),
        "dstintf": kv.get("dstintf"),
        "dstintfrole": kv.get("dstintfrole"),

        "sentbyte": sentbyte,
        "rcvdbyte": rcvdbyte,
        "sentpkt": sentpkt,
        "rcvdpkt": rcvdpkt,

        # 新增：便于 R450 直接做流量/会话统计
        "bytes_total": _bytes_total(sentbyte, rcvdbyte),
        "pkts_total": _pkts_total(sentpkt, rcvdpkt),

        "parse_status": "ok",
    }

    # 时间/标识
    event["logid"] = kv.get("logid")
    event["eventtime"] = kv.get("eventtime")  # 先保留字符串，避免溢出/误解析
    event["tz"] = kv.get("tz")

    # system event（管理登录/审计）
    event["logdesc"] = kv.get("logdesc")
    event["user"] = kv.get("user")
    event["ui"] = kv.get("ui")
    event["method"] = kv.get("method")
    event["status"] = kv.get("status")
    event["reason"] = kv.get("reason")
    event["msg"] = kv.get("msg")

    # traffic event（会话/策略/应用）
    event["trandisp"] = kv.get("trandisp")
    event["app"] = kv.get("app")
    event["appcat"] = kv.get("appcat")
    event["duration"] = _to_int(kv.get("duration"))

    # 端点/地理/资产特征（用于“精确到设备”）
    event["srcname"] = kv.get("srcname")
    event["srccountry"] = kv.get("srccountry")
    event["dstcountry"] = kv.get("dstcountry")

    event["osname"] = kv.get("osname")
    event["srcswversion"] = kv.get("srcswversion")

    event["srcmac"] = kv.get("srcmac")
    event["mastersrcmac"] = kv.get("mastersrcmac")
    event["srcserver"] = _to_int(kv.get("srcserver"))

    # 新增：资产指纹（你日志样本里会出现）
    event["srchwvendor"] = kv.get("srchwvendor")
    event["devtype"] = kv.get("devtype")
    event["srcfamily"] = kv.get("srcfamily")
    event["srchwversion"] = kv.get("srchwversion")
    event["srchwmodel"] = kv.get("srchwmodel")

    # 新增：稳定设备 key（R450 聚合主键）
    event["src_device_key"] = _device_key(kv)

    # 保留一份 KV 子集（未来扩展/回溯分析）
    event["kv_subset"] = _pick_kv_subset(kv)

    # partial 判定：type/subtype 缺失则标记为 partial
    core_missing = (event.get("type") is None) or (event.get("subtype") is None)
    if core_missing:
        event["parse_status"] = "partial"

    return event, None
