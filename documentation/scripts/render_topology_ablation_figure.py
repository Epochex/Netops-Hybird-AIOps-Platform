from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "documentation" / "images" / "topology_ablation_summary.svg"
OFFICE_REPORT = Path("/data/netops-runtime/observability/topology-subgraph-ablation-latest.json")
LCORE_REPORT = Path("/data/netops-runtime/LCORE-D/work/topology-subgraph-ablation.json")


DEFAULT_OFFICE = {
    "alerts_scanned": 886,
    "full_invocation_requests": 886,
    "topology_gated_requests": 0,
    "llm_call_reduction_percent": 100.0,
    "high_value_alerts": 0,
    "high_value_alert_recall": 0.0,
    "avg_selected_nodes": 2.0,
    "avg_noise_nodes": 1.099,
}

DEFAULT_LCORE = {
    "alerts_scanned": 1302,
    "full_invocation_requests": 1302,
    "topology_gated_requests": 173,
    "llm_call_reduction_percent": 86.71,
    "high_value_alerts": 173,
    "high_value_alert_recall": 1.0,
    "avg_selected_nodes": 2.0,
    "avg_noise_nodes": 1.968,
}


class Svg:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.parts: list[str] = []

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def text(
        self,
        x: float,
        y: float,
        value: str,
        *,
        size: int = 22,
        weight: int = 400,
        fill: str = "#1f2933",
        anchor: str = "start",
        family: str = "Arial, Helvetica, sans-serif",
        opacity: float | None = None,
    ) -> None:
        opacity_attr = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" '
            f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
            f'fill="{fill}"{opacity_attr}>{escape(value)}</text>'
        )

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str = "none",
        stroke: str = "none",
        stroke_width: float = 1,
        rx: float = 0,
        opacity: float | None = None,
    ) -> None:
        opacity_attr = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx:.1f}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{stroke_width:.1f}"{opacity_attr}/>'
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: str = "#1f2933",
        stroke_width: float = 2,
        dash: str | None = None,
        opacity: float | None = None,
    ) -> None:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        opacity_attr = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{stroke_width:.1f}"{dash_attr}{opacity_attr}/>'
        )

    def circle(
        self,
        cx: float,
        cy: float,
        r: float,
        *,
        fill: str,
        stroke: str = "#ffffff",
        stroke_width: float = 2,
        opacity: float | None = None,
    ) -> None:
        opacity_attr = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_width:.1f}"{opacity_attr}/>'
        )

    def path(
        self,
        d: str,
        *,
        fill: str = "none",
        stroke: str = "#1f2933",
        stroke_width: float = 2,
        dash: str | None = None,
        opacity: float | None = None,
    ) -> None:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        opacity_attr = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{stroke_width:.1f}"{dash_attr}{opacity_attr}/>'
        )

    def render(self) -> str:
        body = "\n".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}">\n'
            "<defs>\n"
            '<linearGradient id="panelBg" x1="0" x2="1" y1="0" y2="1">\n'
            '<stop offset="0%" stop-color="#ffffff"/>\n'
            '<stop offset="100%" stop-color="#f6f7f9"/>\n'
            "</linearGradient>\n"
            '<pattern id="diag" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">\n'
            '<line x1="0" y1="0" x2="0" y2="8" stroke="#a7b0bc" stroke-width="2"/>\n'
            "</pattern>\n"
            "</defs>\n"
            f"{body}\n"
            "</svg>\n"
        )


def _load_report(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback)
    merged = dict(fallback)
    merged.update(data)
    return merged


def _pct(value: float) -> str:
    return f"{value:.2f}%"


def _panel(svg: Svg, x: int, y: int, w: int, h: int, label: str, title: str) -> None:
    svg.rect(x, y, w, h, fill="url(#panelBg)", stroke="#c8d0da", stroke_width=1.2, rx=18)
    svg.text(x + 22, y + 38, label, size=24, weight=700, fill="#c54a1f")
    svg.text(x + 62, y + 38, title, size=23, weight=700, fill="#202733")


def _axis_grid(svg: Svg, x: int, y: int, w: int, h: int, *, max_y: int, ticks: list[int]) -> None:
    svg.line(x, y + h, x + w, y + h, stroke="#293241", stroke_width=1.4)
    svg.line(x, y, x, y + h, stroke="#293241", stroke_width=1.4)
    for tick in ticks:
        yy = y + h - (tick / max_y) * h
        svg.line(x, yy, x + w, yy, stroke="#d8dde5", stroke_width=1, dash="3 5")
        svg.text(x - 12, yy + 5, str(tick), size=15, fill="#667281", anchor="end")


def _bar_panel(svg: Svg, office: dict[str, Any], lcore: dict[str, Any]) -> None:
    x, y, w, h = 50, 110, 510, 285
    _panel(svg, 30, 70, 560, 380, "A", "LLM request volume")
    chart_x, chart_y, chart_w, chart_h = x + 55, y + 40, w - 95, h - 55
    max_y = 1400
    _axis_grid(svg, chart_x, chart_y, chart_w, chart_h, max_y=max_y, ticks=[0, 350, 700, 1050, 1400])

    groups = [
        ("Office", int(office["full_invocation_requests"]), int(office["topology_gated_requests"]), "#7d8794"),
        ("LCORE-D", int(lcore["full_invocation_requests"]), int(lcore["topology_gated_requests"]), "#d95f2d"),
    ]
    group_centers = [chart_x + chart_w * 0.30, chart_x + chart_w * 0.73]
    bar_w = 44
    for center, (name, full, gated, color) in zip(group_centers, groups):
        for offset, value, fill, label in [
            (-bar_w * 0.65, full, "#26313f", "invoke-all"),
            (bar_w * 0.65, gated, color, "topology-gated"),
        ]:
            bh = (value / max_y) * chart_h
            bx = center + offset - bar_w / 2
            by = chart_y + chart_h - bh
            svg.rect(bx, by, bar_w, bh, fill=fill, rx=5)
            svg.text(bx + bar_w / 2, by - 8, str(value), size=16, weight=700, fill=fill, anchor="middle")
        svg.text(center, chart_y + chart_h + 32, name, size=18, weight=700, fill="#293241", anchor="middle")

    svg.rect(chart_x + 24, chart_y - 28, 16, 16, fill="#26313f", rx=3)
    svg.text(chart_x + 48, chart_y - 15, "invoke-all baseline", size=15, fill="#4d5968")
    svg.rect(chart_x + 205, chart_y - 28, 16, 16, fill="#d95f2d", rx=3)
    svg.text(chart_x + 229, chart_y - 15, "topology-gated", size=15, fill="#4d5968")

    reduction = float(lcore["llm_call_reduction_percent"])
    svg.path(
        f"M {group_centers[1] - 55:.1f} {chart_y + 18:.1f} C {group_centers[1] - 5:.1f} "
        f"{chart_y - 20:.1f}, {group_centers[1] + 60:.1f} {chart_y - 20:.1f}, "
        f"{group_centers[1] + 105:.1f} {chart_y + 18:.1f}",
        stroke="#d95f2d",
        stroke_width=2.4,
    )
    svg.text(group_centers[1] + 23, chart_y - 30, f"-{reduction:.2f}% calls", size=18, weight=800, fill="#d95f2d", anchor="middle")
    svg.text(chart_x + chart_w - 6, chart_y + chart_h + 54, "requests", size=14, fill="#667281", anchor="end")


def _frontier_panel(svg: Svg, office: dict[str, Any], lcore: dict[str, Any]) -> None:
    _panel(svg, 620, 70, 560, 380, "B", "Efficiency-quality frontier")
    x, y, w, h = 695, 150, 400, 225
    svg.line(x, y + h, x + w, y + h, stroke="#293241", stroke_width=1.4)
    svg.line(x, y, x, y + h, stroke="#293241", stroke_width=1.4)
    for tick in [0, 25, 50, 75, 100]:
        xx = x + (tick / 100) * w
        yy = y + h - (tick / 100) * h
        svg.line(xx, y, xx, y + h, stroke="#e0e5eb", stroke_width=1, dash="3 5")
        svg.line(x, yy, x + w, yy, stroke="#e0e5eb", stroke_width=1, dash="3 5")
        svg.text(xx, y + h + 25, str(tick), size=14, fill="#667281", anchor="middle")
        svg.text(x - 12, yy + 5, str(tick), size=14, fill="#667281", anchor="end")

    def point(call_reduction: float, recall: float) -> tuple[float, float]:
        return x + (call_reduction / 100) * w, y + h - (recall / 100) * h

    baseline_x, baseline_y = point(0, 100)
    lcore_x, lcore_y = point(float(lcore["llm_call_reduction_percent"]), float(lcore["high_value_alert_recall"]) * 100)
    office_x, office_y = point(float(office["llm_call_reduction_percent"]), float(office["high_value_alert_recall"]) * 100)

    svg.path(f"M {baseline_x:.1f} {baseline_y:.1f} L {lcore_x:.1f} {lcore_y:.1f}", stroke="#d95f2d", stroke_width=3)
    svg.circle(baseline_x, baseline_y, 10, fill="#26313f")
    svg.text(baseline_x + 14, baseline_y - 12, "invoke-all", size=15, weight=700, fill="#26313f")
    svg.text(baseline_x + 14, baseline_y + 8, "0% reduction / 100% recall", size=13, fill="#5f6b7a")

    svg.circle(lcore_x, lcore_y, 20, fill="#d95f2d")
    svg.text(lcore_x - 4, lcore_y - 30, "LCORE topology gate", size=16, weight=800, fill="#d95f2d", anchor="middle")
    svg.text(lcore_x - 4, lcore_y - 10, "86.71% reduction / 100% recall", size=13, fill="#99401e", anchor="middle")

    svg.circle(office_x, office_y, 12, fill="#a7b0bc", opacity=0.65)
    svg.text(office_x - 8, office_y + 30, "office: no high-value labels", size=13, fill="#687482", anchor="end")

    svg.text(x + w / 2, y + h + 52, "LLM call reduction (%)", size=15, fill="#293241", anchor="middle")
    svg.text(x - 55, y - 16, "high-value recall (%)", size=15, fill="#293241")
    svg.text(x + w - 4, y + 18, "desired region", size=14, weight=700, fill="#d95f2d", anchor="end")
    svg.rect(x + w - 126, y + 28, 122, 26, fill="#fff0e8", stroke="#f0b08f", rx=6)
    svg.text(x + w - 65, y + 46, "low cost + high recall", size=13, fill="#9a3d1e", anchor="middle")


def _subgraph_panel(svg: Svg, office: dict[str, Any], lcore: dict[str, Any]) -> None:
    _panel(svg, 1210, 70, 560, 380, "C", "Evidence compaction inside selected subgraph")
    x, y = 1285, 165
    bar_w, bar_h = 390, 34
    rows = [
        ("Office legacy", float(office["avg_selected_nodes"]), float(office["avg_noise_nodes"]), "#7d8794"),
        ("LCORE-D replay", float(lcore["avg_selected_nodes"]), float(lcore["avg_noise_nodes"]), "#d95f2d"),
    ]
    max_total = max(selected + noise for _, selected, noise, _ in rows)
    for i, (name, selected, noise, color) in enumerate(rows):
        yy = y + i * 95
        selected_w = selected / max_total * bar_w
        noise_w = noise / max_total * bar_w
        svg.text(x, yy - 14, name, size=17, weight=700, fill="#293241")
        svg.rect(x, yy, selected_w, bar_h, fill=color, rx=7)
        svg.rect(x + selected_w, yy, noise_w, bar_h, fill="url(#diag)", stroke="#a7b0bc", rx=7)
        svg.text(x + selected_w / 2, yy + 23, f"selected {selected:.2f}", size=14, weight=700, fill="#ffffff", anchor="middle")
        svg.text(x + selected_w + noise_w / 2, yy + 23, f"noise {noise:.2f}", size=14, weight=700, fill="#344054", anchor="middle")
        total = selected + noise
        ratio = selected / total * 100 if total else 0
        svg.text(x + bar_w + 20, yy + 23, f"{ratio:.1f}% retained", size=15, fill="#4d5968")

    svg.text(x, y + 225, "Average nodes per alert after deterministic role assignment.", size=15, fill="#5f6b7a")
    svg.text(x, y + 250, "Noise remains visible for audit, but is excluded from the core LLM evidence slice.", size=15, fill="#5f6b7a")

    svg.rect(x, y + 282, 16, 16, fill="#d95f2d", rx=3)
    svg.text(x + 24, y + 296, "selected reasoning evidence", size=14, fill="#4d5968")
    svg.rect(x + 228, y + 282, 16, 16, fill="url(#diag)", stroke="#a7b0bc", rx=3)
    svg.text(x + 252, y + 296, "noise / non-core evidence", size=14, fill="#4d5968")


def render() -> None:
    office = _load_report(OFFICE_REPORT, DEFAULT_OFFICE)
    lcore = _load_report(LCORE_REPORT, DEFAULT_LCORE)

    svg = Svg(1800, 560)
    svg.rect(0, 0, 1800, 560, fill="#ffffff")
    svg.text(40, 38, "Topology-Aware Subgraph Extraction Ablation", size=28, weight=800, fill="#111827")
    svg.text(
        40,
        64,
        "Invoke-all baseline vs. topology-gated reasoning on legacy office trace and LCORE-D replay",
        size=16,
        fill="#667281",
    )
    _bar_panel(svg, office, lcore)
    _frontier_panel(svg, office, lcore)
    _subgraph_panel(svg, office, lcore)
    svg.text(
        40,
        535,
        (
            "Data: office legacy trace n=886, LCORE-D 50k replay n=1302. "
            "LCORE gate keeps 173 high-value alerts, reduces external LLM calls by "
            f"{float(lcore['llm_call_reduction_percent']):.2f}%, and preserves "
            f"{float(lcore['high_value_alert_recall']) * 100:.0f}% high-value recall."
        ),
        size=14,
        fill="#667281",
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(svg.render(), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    render()
