import argparse
import json
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.aiops_agent.cluster_aggregator import AlertClusterAggregator
from core.aiops_agent.evidence_bundle import build_cluster_evidence_bundle
from core.aiops_agent.inference_queue import InMemoryInferenceQueue
from core.aiops_agent.inference_schema import build_cluster_inference_request
from core.aiops_agent.inference_worker import InferenceWorker
from core.aiops_agent.providers import HTTPInferenceProvider, TemplateProvider


def _parse_alert_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iter_alerts(alert_dir: Path, limit_files: int | None) -> list[dict[str, Any]]:
    files = sorted(alert_dir.glob("alerts-*.jsonl"))
    if limit_files is not None and limit_files > 0:
        files = files[-limit_files:]

    alerts: list[dict[str, Any]] = []
    for path in files:
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    alert = json.loads(line)
                except json.JSONDecodeError:
                    continue
                alert["_source_file"] = path.name
                alerts.append(alert)

    alerts.sort(key=lambda x: (_parse_alert_ts(x.get("alert_ts")) or datetime.min.replace(tzinfo=timezone.utc), str(x.get("alert_id") or "")))
    return alerts


def _build_provider(args: argparse.Namespace):
    provider_name = args.provider.lower()
    if provider_name == "http":
        if not args.http_endpoint_url:
            raise SystemExit("--http-endpoint-url is required when --provider=http")
        return HTTPInferenceProvider(
            endpoint_url=args.http_endpoint_url,
            api_key=args.http_api_key,
            model=args.http_model,
            timeout_sec=max(args.http_timeout_sec, 5),
        )
    return TemplateProvider()


def _stable_signature(payload: dict[str, Any]) -> str:
    stable = {
        "summary": payload.get("summary"),
        "hypotheses": payload.get("hypotheses"),
        "recommended_actions": payload.get("recommended_actions"),
        "confidence_score": payload.get("confidence_score"),
        "confidence_label": payload.get("confidence_label"),
        "confidence_reason": payload.get("confidence_reason"),
    }
    return json.dumps(stable, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay real alert history through the AIOps slow path.")
    parser.add_argument("--alert-dir", default="/data/netops-runtime/alerts")
    parser.add_argument("--provider", choices=["template", "http"], default="template")
    parser.add_argument("--http-endpoint-url", default="")
    parser.add_argument("--http-api-key", default="")
    parser.add_argument("--http-model", default="generic-aiops")
    parser.add_argument("--http-timeout-sec", type=int, default=30)
    parser.add_argument("--cluster-window-sec", type=int, default=300)
    parser.add_argument("--cluster-min-alerts", type=int, default=3)
    parser.add_argument("--cluster-cooldown-sec", type=int, default=300)
    parser.add_argument("--limit-files", type=int, default=0)
    parser.add_argument("--stability-runs", type=int, default=2)
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    alert_dir = Path(args.alert_dir)
    if not alert_dir.exists():
        raise SystemExit(f"alert directory not found: {alert_dir}")

    provider = _build_provider(args)
    worker = InferenceWorker(provider)
    queue = InMemoryInferenceQueue()
    aggregator = AlertClusterAggregator(
        window_sec=max(args.cluster_window_sec, 10),
        min_alerts=max(args.cluster_min_alerts, 2),
        cooldown_sec=max(args.cluster_cooldown_sec, 10),
    )
    history: deque[tuple[datetime, str, str]] = deque()
    alerts = _iter_alerts(alert_dir, args.limit_files or None)

    stats: dict[str, Any] = {
        "validation_ts": datetime.now(timezone.utc).isoformat(),
        "provider": provider.name,
        "provider_kind": provider.kind,
        "input_files_scanned": 0,
        "alerts_scanned": 0,
        "cluster_triggers": 0,
        "pipeline_outputs": 0,
        "provider_errors": 0,
        "provider_stability_pass": 0,
        "provider_stability_fail": 0,
        "service_present": 0,
        "src_device_key_present": 0,
        "srcip_present": 0,
        "dstip_present": 0,
        "site_present": 0,
        "device_profile_present": 0,
        "change_context_present": 0,
        "recent_similar_nonzero": 0,
        "confidence_high": 0,
        "confidence_medium": 0,
        "confidence_low": 0,
        "trigger_rule_counts": Counter(),
        "trigger_service_counts": Counter(),
        "confidence_by_cluster_size": Counter(),
        "first_alert_ts": "",
        "last_alert_ts": "",
        "sample_request_summaries": [],
    }

    unique_files = {str(a.get("_source_file") or "") for a in alerts if a.get("_source_file")}
    stats["input_files_scanned"] = len(unique_files)

    for alert in alerts:
        alert_ts = _parse_alert_ts(alert.get("alert_ts"))
        if alert_ts is None:
            continue
        if not stats["first_alert_ts"]:
            stats["first_alert_ts"] = alert_ts.isoformat()
        stats["last_alert_ts"] = alert_ts.isoformat()
        stats["alerts_scanned"] += 1

        trigger = aggregator.observe(alert)

        excerpt = alert.get("event_excerpt") or {}
        rule_id = str(alert.get("rule_id") or "unknown")
        service = str(excerpt.get("service") or "unknown")
        while history and history[0][0] < (alert_ts - timedelta(hours=1)):
            history.popleft()
        recent_similar_1h = sum(1 for ts, hist_rule, hist_service in history if hist_rule == rule_id and hist_service == service)
        history.append((alert_ts, rule_id, service))

        if trigger is None:
            continue

        stats["cluster_triggers"] += 1
        stats["trigger_rule_counts"][trigger.key.rule_id] += 1
        stats["trigger_service_counts"][trigger.key.service] += 1

        evidence_bundle = build_cluster_evidence_bundle(alert, trigger, recent_similar_1h)
        request_payload = build_cluster_inference_request(alert, trigger, evidence_bundle, provider.name)
        queue.enqueue(request_payload)

        try:
            result = worker.run_once(queue)
        except Exception:
            stats["provider_errors"] += 1
            continue

        if result is None:
            stats["provider_errors"] += 1
            continue

        stats["pipeline_outputs"] += 1
        topology = evidence_bundle.get("topology_context") or {}
        device_context = evidence_bundle.get("device_context") or {}
        change_context = evidence_bundle.get("change_context") or {}
        history_context = evidence_bundle.get("historical_context") or {}

        if topology.get("service"):
            stats["service_present"] += 1
        if topology.get("src_device_key"):
            stats["src_device_key_present"] += 1
        if topology.get("srcip"):
            stats["srcip_present"] += 1
        if topology.get("dstip"):
            stats["dstip_present"] += 1
        if topology.get("site"):
            stats["site_present"] += 1
        if device_context.get("device_role") or device_context.get("vendor") or device_context.get("asset_tags"):
            stats["device_profile_present"] += 1
        if change_context.get("suspected_change") or change_context.get("change_refs"):
            stats["change_context_present"] += 1
        if int(history_context.get("recent_similar_1h") or 0) > 0:
            stats["recent_similar_nonzero"] += 1

        label = result.confidence_label
        if label == "high":
            stats["confidence_high"] += 1
        elif label == "medium":
            stats["confidence_medium"] += 1
        else:
            stats["confidence_low"] += 1

        cluster_size = int(history_context.get("cluster_size") or 0)
        stats["confidence_by_cluster_size"][f"{cluster_size}:{label}"] += 1

        signatures = [_stable_signature(result.to_payload())]
        for _ in range(max(args.stability_runs - 1, 0)):
            repeated = provider.infer(request_payload)
            signatures.append(_stable_signature(repeated.to_payload()))
        if len(set(signatures)) == 1:
            stats["provider_stability_pass"] += 1
        else:
            stats["provider_stability_fail"] += 1

        if len(stats["sample_request_summaries"]) < 5:
            stats["sample_request_summaries"].append(
                {
                    "alert_id": str(alert.get("alert_id") or ""),
                    "service": trigger.key.service,
                    "src_device_key": trigger.key.src_device_key,
                    "cluster_size": cluster_size,
                    "recent_similar_1h": int(history_context.get("recent_similar_1h") or 0),
                    "confidence_label": result.confidence_label,
                    "confidence_score": result.confidence_score,
                    "summary": result.summary,
                }
            )

    outputs = max(stats["pipeline_outputs"], 1)
    report = {
        "validation_ts": stats["validation_ts"],
        "provider": stats["provider"],
        "provider_kind": stats["provider_kind"],
        "input_files_scanned": stats["input_files_scanned"],
        "alerts_scanned": stats["alerts_scanned"],
        "cluster_triggers": stats["cluster_triggers"],
        "pipeline_outputs": stats["pipeline_outputs"],
        "provider_errors": stats["provider_errors"],
        "provider_stability_rate": round(stats["provider_stability_pass"] / outputs, 6),
        "provider_stability_failures": stats["provider_stability_fail"],
        "evidence_presence_rates": {
            "service": round(stats["service_present"] / outputs, 6),
            "src_device_key": round(stats["src_device_key_present"] / outputs, 6),
            "srcip": round(stats["srcip_present"] / outputs, 6),
            "dstip": round(stats["dstip_present"] / outputs, 6),
            "site": round(stats["site_present"] / outputs, 6),
            "device_profile": round(stats["device_profile_present"] / outputs, 6),
            "change_context": round(stats["change_context_present"] / outputs, 6),
            "recent_similar_nonzero": round(stats["recent_similar_nonzero"] / outputs, 6),
        },
        "confidence_distribution": {
            "high": stats["confidence_high"],
            "medium": stats["confidence_medium"],
            "low": stats["confidence_low"],
        },
        "trigger_rule_counts": dict(stats["trigger_rule_counts"]),
        "trigger_service_counts_top10": stats["trigger_service_counts"].most_common(10),
        "confidence_by_cluster_size": dict(stats["confidence_by_cluster_size"]),
        "first_alert_ts": stats["first_alert_ts"],
        "last_alert_ts": stats["last_alert_ts"],
        "sample_request_summaries": stats["sample_request_summaries"],
    }

    text = json.dumps(report, ensure_ascii=True, sort_keys=True)
    print(text)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
