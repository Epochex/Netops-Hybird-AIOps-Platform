from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from typing import Any

from core.aiops_agent.alert_reasoning_runtime import (
    build_alert_runtime_seed,
    build_cluster_runtime_seed,
)
from core.aiops_agent.app_config import AgentConfig
from core.aiops_agent.cluster_aggregator import ClusterKey, ClusterTrigger
from core.aiops_agent.evidence_pack_v2 import build_evidence_pack_v2
from core.aiops_agent.hypothesis_set import build_hypothesis_set
from core.aiops_agent.inference_schema import InferenceRequest, InferenceResult
from core.aiops_agent.reasoning_stage_requests import build_reasoning_stage_requests
from core.aiops_agent.review_verdict import build_review_verdict
from core.aiops_agent.runbook_draft import build_runbook_draft


def is_legacy_suggestion_payload(payload: dict[str, Any]) -> bool:
    return "reasoning_stage_requests" not in payload


def upgrade_legacy_suggestion_payload(
    payload: dict[str, Any],
    *,
    config: AgentConfig,
) -> dict[str, Any]:
    if not is_legacy_suggestion_payload(payload):
        return payload

    upgraded = copy.deepcopy(payload)
    evidence_bundle = _upgrade_evidence_bundle(upgraded)
    inference_request = _inference_request_from_payload(upgraded, evidence_bundle)
    inference_result = _inference_result_from_payload(upgraded)
    reasoning_runtime_seed = evidence_bundle.get("reasoning_runtime_seed") or {}
    runbook_plan_outline = reasoning_runtime_seed.get("runbook_plan_outline") or {}

    hypothesis_set = build_hypothesis_set(
        inference_request=inference_request,
        evidence_bundle=evidence_bundle,
        inference_result=inference_result,
    )
    review_verdict = build_review_verdict(
        inference_request=inference_request,
        evidence_bundle=evidence_bundle,
        inference_result=inference_result,
        hypothesis_set=hypothesis_set,
        runbook_plan_outline=runbook_plan_outline,
    )
    runbook_draft = build_runbook_draft(
        inference_request=inference_request,
        evidence_bundle=evidence_bundle,
        hypothesis_set=hypothesis_set,
        review_verdict=review_verdict,
        runbook_plan_outline=runbook_plan_outline,
        recommended_actions=inference_result.recommended_actions,
    )

    context = dict(upgraded.get("context") or {})
    candidate_event_graph = reasoning_runtime_seed.get("candidate_event_graph") or {}
    investigation_session = reasoning_runtime_seed.get("investigation_session") or {}
    reasoning_trace_seed = reasoning_runtime_seed.get("reasoning_trace_seed") or {}
    context["candidate_event_graph_id"] = str(candidate_event_graph.get("graph_id") or "")
    context["investigation_session_id"] = str(investigation_session.get("session_id") or "")
    context["reasoning_trace_id"] = str(reasoning_trace_seed.get("trace_id") or "")
    context["hypothesis_set_id"] = str(hypothesis_set.get("set_id") or "")
    context["review_verdict_id"] = str(review_verdict.get("verdict_id") or "")
    context["runbook_draft_id"] = str(runbook_draft.get("plan_id") or "")

    projection_basis = upgraded.get("projection_basis")
    if not isinstance(projection_basis, dict):
        projection_basis = {}
    raw_response = inference_result.raw_response if isinstance(inference_result.raw_response, dict) else {}
    if not projection_basis and isinstance(raw_response.get("projection_basis"), dict):
        projection_basis = raw_response.get("projection_basis") or {}

    upgraded["schema_version"] = max(2, int(upgraded.get("schema_version") or 0))
    upgraded["context"] = context
    upgraded["evidence_bundle"] = evidence_bundle
    upgraded["reasoning_runtime_seed"] = reasoning_runtime_seed
    upgraded["projection_basis"] = projection_basis
    upgraded["inference"] = inference_result.to_payload()
    upgraded["hypotheses"] = inference_result.hypotheses
    upgraded["hypothesis_set"] = hypothesis_set
    upgraded["recommended_actions"] = inference_result.recommended_actions
    upgraded["runbook_plan_outline"] = runbook_plan_outline
    upgraded["runbook_draft"] = runbook_draft
    upgraded["review_verdict"] = review_verdict
    upgraded["confidence"] = inference_result.confidence_score
    upgraded["confidence_label"] = inference_result.confidence_label
    upgraded["confidence_reason"] = inference_result.confidence_reason
    upgraded["reasoning_stage_requests"] = build_reasoning_stage_requests(
        config=config,
        inference_request=inference_request,
        suggestion_payload=upgraded,
    )
    return upgraded


def _upgrade_evidence_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    bundle = copy.deepcopy(payload.get("evidence_bundle") or {})
    context = payload.get("context") or {}
    topology = dict(bundle.get("topology_context") or {})
    historical = dict(bundle.get("historical_context") or {})
    rule_context = dict(bundle.get("rule_context") or {})
    window_context = dict(bundle.get("window_context") or {})
    device_context = dict(bundle.get("device_context") or {})
    change_context = dict(bundle.get("change_context") or {})

    service = str(topology.get("service") or context.get("service") or "")
    src_device_key = str(topology.get("src_device_key") or context.get("src_device_key") or "")
    srcintf = str(topology.get("srcintf") or "")
    dstintf = str(topology.get("dstintf") or "")
    path_signature = str(topology.get("path_signature") or f"{srcintf or 'unknown'}->{dstintf or 'unknown'}")
    topology["service"] = service
    topology["src_device_key"] = src_device_key
    topology["srcip"] = str(topology.get("srcip") or "")
    topology["dstip"] = str(topology.get("dstip") or "")
    topology["srcport"] = str(topology.get("srcport") or "")
    topology["dstport"] = str(topology.get("dstport") or "")
    topology["srcintf"] = srcintf
    topology["dstintf"] = dstintf
    topology["srcintfrole"] = str(topology.get("srcintfrole") or "")
    topology["dstintfrole"] = str(topology.get("dstintfrole") or "")
    topology["site"] = str(topology.get("site") or device_context.get("site") or "")
    topology["zone"] = str(topology.get("zone") or "")
    topology["path_signature"] = path_signature
    topology["neighbor_refs"] = _string_list(topology.get("neighbor_refs"))

    device_context["src_device_key"] = str(device_context.get("src_device_key") or src_device_key)
    device_context["device_role"] = str(device_context.get("device_role") or "")
    device_context["site"] = str(device_context.get("site") or "")
    device_context["vendor"] = str(device_context.get("vendor") or "")
    device_context["device_name"] = str(device_context.get("device_name") or "")
    device_context["osname"] = str(device_context.get("osname") or "")
    device_context["family"] = str(device_context.get("family") or "")
    device_context["srcmac"] = str(device_context.get("srcmac") or "")
    device_context["model"] = str(device_context.get("model") or "")
    device_context["version"] = str(device_context.get("version") or "")
    device_context["asset_tags"] = _string_list(device_context.get("asset_tags"))
    device_context["known_services"] = _string_list(device_context.get("known_services"))

    change_context["suspected_change"] = bool(change_context.get("suspected_change"))
    change_context["change_window_min"] = int(change_context.get("change_window_min") or 0)
    change_context["change_refs"] = _string_list(change_context.get("change_refs"))
    change_context["score"] = change_context.get("score")
    change_context["action"] = str(change_context.get("action") or "")
    change_context["level"] = str(change_context.get("level") or "")

    historical["recent_similar_1h"] = int(historical.get("recent_similar_1h") or context.get("recent_similar_1h") or 0)
    historical["cluster_size"] = int(historical.get("cluster_size") or context.get("cluster_size") or 1)
    historical["cluster_window_sec"] = int(historical.get("cluster_window_sec") or context.get("cluster_window_sec") or 0)
    historical["cluster_first_alert_ts"] = str(historical.get("cluster_first_alert_ts") or context.get("cluster_first_alert_ts") or "")
    historical["cluster_last_alert_ts"] = str(historical.get("cluster_last_alert_ts") or context.get("cluster_last_alert_ts") or "")
    historical["cluster_sample_alert_ids"] = _string_list(historical.get("cluster_sample_alert_ids") or context.get("cluster_sample_alert_ids"))
    historical["recent_alert_samples"] = historical.get("recent_alert_samples") or []
    historical["historical_baseline"] = historical.get("historical_baseline") or {}
    historical["recent_change_records"] = historical.get("recent_change_records") or []

    path_context = {
        "srcintf": srcintf,
        "dstintf": dstintf,
        "srcintfrole": str(topology.get("srcintfrole") or ""),
        "dstintfrole": str(topology.get("dstintfrole") or ""),
        "path_signature": path_signature,
        "recent_path_hits": [],
    }
    policy_context = {
        "policyid": str(topology.get("policyid") or ""),
        "policytype": str(topology.get("policytype") or ""),
        "recent_policy_hits": [],
    }
    sample_context = {
        "recent_alert_samples": historical.get("recent_alert_samples") or [],
    }
    window_context["cluster_size"] = int(window_context.get("cluster_size") or historical.get("cluster_size") or 1)
    window_context["window_sec"] = int(window_context.get("window_sec") or historical.get("cluster_window_sec") or 0)
    window_context["sample_alert_ids"] = _string_list(window_context.get("sample_alert_ids") or historical.get("cluster_sample_alert_ids"))

    bundle["schema_version"] = max(1, int(bundle.get("schema_version") or 0))
    bundle["bundle_id"] = str(bundle.get("bundle_id") or _hash_text(f"{payload.get('alert_id') or ''}|{payload.get('rule_id') or ''}|{payload.get('suggestion_scope') or 'alert'}"))
    bundle["bundle_ts"] = str(bundle.get("bundle_ts") or payload.get("suggestion_ts") or datetime.now(timezone.utc).isoformat())
    bundle["bundle_scope"] = str(bundle.get("bundle_scope") or payload.get("suggestion_scope") or "alert")
    bundle["alert_ref"] = {
        "alert_id": str((bundle.get("alert_ref") or {}).get("alert_id") or payload.get("alert_id") or ""),
        "rule_id": str((bundle.get("alert_ref") or {}).get("rule_id") or payload.get("rule_id") or "unknown"),
        "severity": str((bundle.get("alert_ref") or {}).get("severity") or payload.get("severity") or "unknown").lower(),
    }
    bundle["topology_context"] = topology
    bundle["historical_context"] = historical
    bundle["rule_context"] = {
        "rule_id": str(rule_context.get("rule_id") or payload.get("rule_id") or "unknown"),
        "severity": str(rule_context.get("severity") or payload.get("severity") or "unknown").lower(),
        "metrics": rule_context.get("metrics") or {},
        "dimensions": rule_context.get("dimensions") or {},
        "rule_hits": rule_context.get("rule_hits") or [
            {
                "rule_id": str(rule_context.get("rule_id") or payload.get("rule_id") or "unknown"),
                "severity": str(rule_context.get("severity") or payload.get("severity") or "unknown").lower(),
                "cluster_size": int(historical.get("cluster_size") or 1),
            }
        ],
    }
    bundle["path_context"] = path_context
    bundle["policy_context"] = policy_context
    bundle["sample_context"] = sample_context
    bundle["window_context"] = window_context
    bundle["device_context"] = device_context
    bundle["change_context"] = change_context

    pseudo_alert = _pseudo_alert_from_bundle(payload, bundle)
    history_support = {
        "recent_alert_samples": historical.get("recent_alert_samples") or [],
        "historical_baseline": historical.get("historical_baseline") or {},
        "recent_change_records": historical.get("recent_change_records") or [],
        "recent_path_hits": path_context.get("recent_path_hits") or [],
        "recent_policy_hits": policy_context.get("recent_policy_hits") or [],
    }
    recent_similar_1h = int(historical.get("recent_similar_1h") or 0)
    if bundle["bundle_scope"] == "cluster":
        trigger = ClusterTrigger(
            key=ClusterKey(
                rule_id=bundle["alert_ref"]["rule_id"],
                severity=bundle["alert_ref"]["severity"],
                service=service or "unknown",
                src_device_key=src_device_key or "unknown",
            ),
            cluster_size=int(historical.get("cluster_size") or 1),
            first_alert_ts=str(historical.get("cluster_first_alert_ts") or payload.get("suggestion_ts") or ""),
            last_alert_ts=str(historical.get("cluster_last_alert_ts") or payload.get("suggestion_ts") or ""),
            window_sec=int(historical.get("cluster_window_sec") or 0),
            sample_alert_ids=_string_list(historical.get("cluster_sample_alert_ids")),
        )
        bundle["reasoning_runtime_seed"] = build_cluster_runtime_seed(
            alert=pseudo_alert,
            trigger=trigger,
            recent_similar_1h=recent_similar_1h,
            history_support=history_support,
        )
    else:
        bundle["reasoning_runtime_seed"] = build_alert_runtime_seed(
            alert=pseudo_alert,
            recent_similar_1h=recent_similar_1h,
            history_support=history_support,
        )
    bundle["evidence_pack_v2"] = build_evidence_pack_v2(bundle)
    return bundle


def _pseudo_alert_from_bundle(payload: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    topology = bundle.get("topology_context") or {}
    historical = bundle.get("historical_context") or {}
    rule_context = bundle.get("rule_context") or {}
    device = bundle.get("device_context") or {}
    change = bundle.get("change_context") or {}
    alert_ref = bundle.get("alert_ref") or {}
    policy_context = bundle.get("policy_context") or {}
    return {
        "alert_id": str(alert_ref.get("alert_id") or payload.get("alert_id") or ""),
        "rule_id": str(alert_ref.get("rule_id") or payload.get("rule_id") or "unknown"),
        "severity": str(alert_ref.get("severity") or payload.get("severity") or "unknown").lower(),
        "alert_ts": str(
            historical.get("cluster_last_alert_ts")
            or historical.get("cluster_first_alert_ts")
            or payload.get("suggestion_ts")
            or datetime.now(timezone.utc).isoformat()
        ),
        "metrics": rule_context.get("metrics") or {},
        "dimensions": rule_context.get("dimensions") or {},
        "event_excerpt": {
            "service": topology.get("service"),
            "srcip": topology.get("srcip"),
            "dstip": topology.get("dstip"),
            "srcport": topology.get("srcport"),
            "dstport": topology.get("dstport"),
            "srcintf": topology.get("srcintf"),
            "dstintf": topology.get("dstintf"),
            "srcintfrole": topology.get("srcintfrole"),
            "dstintfrole": topology.get("dstintfrole"),
            "src_device_key": topology.get("src_device_key") or device.get("src_device_key"),
            "policyid": policy_context.get("policyid"),
            "policytype": policy_context.get("policytype"),
            "srcname": device.get("device_name"),
        },
        "topology_context": topology,
        "device_profile": device,
        "change_context": change,
    }


def _inference_request_from_payload(payload: dict[str, Any], evidence_bundle: dict[str, Any]) -> InferenceRequest:
    scope = str(payload.get("suggestion_scope") or "alert")
    provider = str((payload.get("inference") or {}).get("provider_name") or (payload.get("context") or {}).get("provider") or "template")
    alert_id = str(payload.get("alert_id") or "")
    rule_id = str(payload.get("rule_id") or "unknown")
    severity = str(payload.get("severity") or "unknown").lower()
    request_id = str((payload.get("context") or {}).get("inference_request_id") or _hash_text(f"{alert_id}|{rule_id}|{scope}|{provider}"))
    return InferenceRequest(
        schema_version=1,
        request_id=request_id,
        request_ts=str(payload.get("suggestion_ts") or datetime.now(timezone.utc).isoformat()),
        request_kind="cluster_triage" if scope == "cluster" else "alert_triage",
        provider=provider,
        alert_id=alert_id,
        rule_id=rule_id,
        severity=severity,
        priority=str(payload.get("priority") or ("P2" if severity == "warning" else "P1")),
        suggestion_scope=scope,
        evidence_bundle=evidence_bundle,
        expected_response_schema={
            "summary": "string",
            "hypotheses": ["string"],
            "recommended_actions": ["string"],
            "confidence_score": "float[0,1]",
            "confidence_label": "low|medium|high",
            "confidence_reason": "string",
        },
    )


def _inference_result_from_payload(payload: dict[str, Any]) -> InferenceResult:
    inference = payload.get("inference") or {}
    hypotheses = inference.get("hypotheses")
    if not isinstance(hypotheses, list):
        hypotheses = payload.get("hypotheses") or []
    recommended_actions = inference.get("recommended_actions")
    if not isinstance(recommended_actions, list):
        recommended_actions = payload.get("recommended_actions") or []
    raw_response = inference.get("raw_response")
    if not isinstance(raw_response, dict):
        raw_response = {}
    return InferenceResult(
        schema_version=1,
        request_id=str(inference.get("request_id") or (payload.get("context") or {}).get("inference_request_id") or ""),
        provider_name=str(inference.get("provider_name") or (payload.get("context") or {}).get("provider") or "template"),
        provider_kind=str(inference.get("provider_kind") or "legacy_runtime"),
        inference_ts=str(inference.get("inference_ts") or payload.get("suggestion_ts") or datetime.now(timezone.utc).isoformat()),
        summary=str(inference.get("summary") or payload.get("summary") or ""),
        hypotheses=[str(item).strip() for item in hypotheses if str(item).strip()],
        recommended_actions=[str(item).strip() for item in recommended_actions if str(item).strip()],
        confidence_score=float(inference.get("confidence_score") or payload.get("confidence") or 0.5),
        confidence_label=str(inference.get("confidence_label") or payload.get("confidence_label") or "medium"),
        confidence_reason=str(inference.get("confidence_reason") or payload.get("confidence_reason") or ""),
        raw_response=raw_response,
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            items.append(text)
    return items


def _hash_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).hexdigest()
