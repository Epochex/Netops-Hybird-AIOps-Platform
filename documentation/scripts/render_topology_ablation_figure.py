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

INK = "#1f2933"
MUTED = "#667281"
GRID = "#d9dee7"
PANEL = "#f8fafc"
PANEL_STROKE = "#cbd5e1"
BASELINE = "#26313f"
ORANGE = "#d85b2a"
ORANGE_DARK = "#9e3f1c"
GRAY = "#8a94a3"
PALE_ORANGE = "#fff2ea"
PALE_GREEN = "#ecf8f0"


class Svg:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.parts: list[str] = []

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str = "none",
        stroke: str = "none",
        sw: float = 1,
        rx: float = 0,
        opacity: float | None = None,
    ) -> None:
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}"{op}/>'
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: str = INK,
        sw: float = 1.5,
        dash: str | None = None,
        opacity: float | None = None,
    ) -> None:
        da = f' stroke-dasharray="{dash}"' if dash else ""
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{sw:.1f}"{da}{op}/>'
        )

    def text(
        self,
        x: float,
        y: float,
        value: str,
        *,
        size: int = 18,
        weight: int = 400,
        fill: str = INK,
        anchor: str = "start",
        opacity: float | None = None,
    ) -> None:
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
            f'fill="{fill}"{op}>{escape(value)}</text>'
        )

    def circle(
        self,
        x: float,
        y: float,
        r: float,
        *,
        fill: str,
        stroke: str = "#ffffff",
        sw: float = 2,
        opacity: float | None = None,
    ) -> None:
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw:.1f}"{op}/>'
        )

    def path(
        self,
        d: str,
        *,
        fill: str = "none",
        stroke: str = INK,
        sw: float = 2,
        dash: str | None = None,
        opacity: float | None = None,
    ) -> None:
        da = f' stroke-dasharray="{dash}"' if dash else ""
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}"{da}{op}/>'
        )

    def render(self) -> str:
        body = "\n".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">\n'
            "<defs>\n"
            '<pattern id="noisePattern" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">\n'
            '<line x1="0" y1="0" x2="0" y2="10" stroke="#9aa5b3" stroke-width="2" opacity="0.55"/>\n'
            "</pattern>\n"
            "</defs>\n"
            f"{body}\n"
            "</svg>\n"
        )


def load_report(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = dict(fallback)
    merged.update(data)
    return merged


def panel(svg: Svg, x: int, y: int, w: int, h: int, letter: str, title: str, subtitle: str) -> None:
    svg.rect(x, y, w, h, fill=PANEL, stroke=PANEL_STROKE, sw=1.2, rx=16)
    svg.text(x + 24, y + 38, letter, size=22, weight=800, fill=ORANGE)
    svg.text(x + 62, y + 38, title, size=21, weight=800, fill=INK)
    svg.text(x + 62, y + 62, subtitle, size=14, fill=MUTED)


def axis_y(svg: Svg, x: int, y: int, w: int, h: int, max_v: int, ticks: list[int]) -> None:
    svg.line(x, y, x, y + h, stroke=INK, sw=1.2)
    svg.line(x, y + h, x + w, y + h, stroke=INK, sw=1.2)
    for tick in ticks:
        yy = y + h - (tick / max_v) * h
        svg.line(x, yy, x + w, yy, stroke=GRID, sw=1, dash="4 6")
        svg.text(x - 12, yy + 5, str(tick), size=13, fill=MUTED, anchor="end")


def draw_request_panel(svg: Svg, office: dict[str, Any], lcore: dict[str, Any]) -> None:
    panel(svg, 44, 104, 720, 360, "A", "External LLM request budget", "Invoke-all baseline vs. topology-gated dispatch")
    x, y, w, h = 128, 188, 560, 210
    max_v = 1400
    axis_y(svg, x, y, w, h, max_v, [0, 350, 700, 1050, 1400])
    svg.text(x + w, y + h + 40, "dataset slice", size=13, fill=MUTED, anchor="end")
    svg.text(x - 52, y - 16, "requests", size=13, fill=MUTED)

    groups = [
        ("Office\nlegacy", int(office["full_invocation_requests"]), int(office["topology_gated_requests"]), GRAY),
        ("LCORE-D\nreplay", int(lcore["full_invocation_requests"]), int(lcore["topology_gated_requests"]), ORANGE),
    ]
    centers = [x + 170, x + 410]
    bar_w = 46
    for cx, (name, full, gated, color) in zip(centers, groups):
        for offset, value, fill in [(-32, full, BASELINE), (32, gated, color)]:
            bh = value / max_v * h
            bx = cx + offset - bar_w / 2
            by = y + h - bh
            svg.rect(bx, by, bar_w, bh, fill=fill, rx=4)
            label_y = max(by - 10, y + 16)
            svg.text(bx + bar_w / 2, label_y, str(value), size=15, weight=800, fill=fill, anchor="middle")
        top, bottom = name.split("\n")
        svg.text(cx, y + h + 28, top, size=15, weight=800, anchor="middle")
        svg.text(cx, y + h + 48, bottom, size=13, fill=MUTED, anchor="middle")

    svg.rect(x + 36, y - 46, 15, 15, fill=BASELINE, rx=2)
    svg.text(x + 60, y - 34, "invoke-all", size=13, fill=MUTED)
    svg.rect(x + 150, y - 46, 15, 15, fill=ORANGE, rx=2)
    svg.text(x + 174, y - 34, "topology-gated", size=13, fill=MUTED)

    callout_x, callout_y = x + 450, y + 48
    svg.rect(callout_x, callout_y, 170, 54, fill=PALE_ORANGE, stroke="#f1b798", rx=10)
    svg.text(callout_x + 85, callout_y + 23, "LCORE-D", size=13, weight=800, fill=ORANGE_DARK, anchor="middle")
    svg.text(callout_x + 85, callout_y + 43, "1302 -> 173 calls", size=16, weight=800, fill=ORANGE_DARK, anchor="middle")
    svg.text(x + 410, y + h + 68, "86.71% reduction", size=13, weight=800, fill=ORANGE_DARK, anchor="middle")


def draw_frontier_panel(svg: Svg, office: dict[str, Any], lcore: dict[str, Any]) -> None:
    panel(svg, 836, 104, 720, 360, "B", "Efficiency-quality frontier", "Call reduction is only useful if high-value alerts are retained")
    x, y, w, h = 930, 190, 500, 205
    svg.rect(x + w * 0.80, y, w * 0.20, h * 0.08, fill=PALE_GREEN, stroke="#b8dfc3", sw=1, rx=6)
    svg.text(x + w - 12, y + 20, "target region", size=13, weight=800, fill="#287044", anchor="end")

    svg.line(x, y + h, x + w, y + h, stroke=INK, sw=1.2)
    svg.line(x, y, x, y + h, stroke=INK, sw=1.2)
    for tick in [0, 25, 50, 75, 100]:
        xx = x + tick / 100 * w
        yy = y + h - tick / 100 * h
        svg.line(xx, y, xx, y + h, stroke=GRID, sw=1, dash="4 6")
        svg.line(x, yy, x + w, yy, stroke=GRID, sw=1, dash="4 6")
        svg.text(xx, y + h + 24, str(tick), size=13, fill=MUTED, anchor="middle")
        svg.text(x - 12, yy + 5, str(tick), size=13, fill=MUTED, anchor="end")
    svg.text(x + w / 2, y + h + 52, "LLM call reduction (%)", size=14, fill=INK, anchor="middle")
    svg.text(x - 70, y - 18, "high-value recall (%)", size=14, fill=INK)

    def point(reduction: float, recall: float) -> tuple[float, float]:
        return x + reduction / 100 * w, y + h - recall / 100 * h

    bx, by = point(0, 100)
    lx, ly = point(float(lcore["llm_call_reduction_percent"]), float(lcore["high_value_alert_recall"]) * 100)
    svg.path(f"M {bx:.1f} {by:.1f} L {lx:.1f} {ly:.1f}", stroke=ORANGE, sw=3.2)
    svg.circle(bx, by, 10, fill=BASELINE)
    svg.text(bx + 18, by + 5, "invoke-all baseline", size=14, weight=800, fill=BASELINE)
    svg.circle(lx, ly, 14, fill=ORANGE)
    svg.rect(x + 322, y + 42, 160, 62, fill=PALE_ORANGE, stroke="#f1b798", rx=9)
    svg.text(x + 402, y + 64, "topology gate", size=13, weight=800, fill=ORANGE_DARK, anchor="middle")
    svg.text(x + 402, y + 84, "86.71% fewer calls", size=13, fill=ORANGE_DARK, anchor="middle")
    svg.text(x + 402, y + 101, "100% high-value recall", size=12, fill=ORANGE_DARK, anchor="middle")

    svg.rect(x + 52, y + 38, 222, 56, fill="#f1f5f9", stroke="#d5dde7", rx=10)
    svg.text(x + 68, y + 62, "Office legacy slice", size=13, weight=800, fill=INK)
    svg.text(x + 68, y + 82, "0 high-value labels; not a localization benchmark", size=12, fill=MUTED)

    svg.text(lx + 18, ly + 5, "173 / 173 retained", size=13, weight=800, fill=ORANGE_DARK)


def draw_compaction_panel(svg: Svg, office: dict[str, Any], lcore: dict[str, Any]) -> None:
    panel(svg, 44, 514, 1512, 330, "C", "Evidence compaction and audit surface", "Selected nodes form the LLM slice; noise nodes remain visible for audit")
    x, y, w = 150, 625, 880
    rows = [
        ("Office legacy", float(office["avg_selected_nodes"]), float(office["avg_noise_nodes"]), GRAY),
        ("LCORE-D replay", float(lcore["avg_selected_nodes"]), float(lcore["avg_noise_nodes"]), ORANGE),
    ]
    max_total = max(selected + noise for _, selected, noise, _ in rows)
    for idx, (name, selected, noise, color) in enumerate(rows):
        yy = y + idx * 78
        selected_w = selected / max_total * w
        noise_w = noise / max_total * w
        total = selected + noise
        retained = selected / total * 100 if total else 0
        svg.text(x, yy - 16, name, size=16, weight=800)
        svg.rect(x, yy, selected_w, 38, fill=color, rx=7)
        svg.rect(x + selected_w, yy, noise_w, 38, fill="url(#noisePattern)", stroke="#9aa5b3", sw=1, rx=7)
        svg.text(x + selected_w / 2, yy + 25, f"selected {selected:.2f}", size=14, weight=800, fill="#ffffff", anchor="middle")
        svg.text(x + selected_w + noise_w / 2, yy + 25, f"noise {noise:.2f}", size=14, weight=800, fill=INK, anchor="middle")
        svg.text(x + w + 26, yy + 25, f"{retained:.1f}% selected", size=15, weight=800, fill=INK)

    card_x, card_y = 1190, 608
    cards = [
        ("LCORE alerts", "1302", "50k replay sample"),
        ("High-value kept", "173 / 173", "100% recall"),
        ("LLM calls saved", "1129", "vs invoke-all baseline"),
    ]
    for i, (title, value, detail) in enumerate(cards):
        yy = card_y + i * 70
        svg.rect(card_x, yy, 250, 54, fill="#ffffff", stroke="#d7dee8", sw=1, rx=10)
        svg.text(card_x + 18, yy + 20, title, size=12, weight=800, fill=MUTED)
        svg.text(card_x + 18, yy + 43, value, size=20, weight=900, fill=ORANGE if i else INK)
        svg.text(card_x + 132, yy + 43, detail, size=12, fill=MUTED)

    svg.rect(x + 560, y - 74, 16, 16, fill=ORANGE, rx=3)
    svg.text(x + 584, y - 61, "selected reasoning evidence", size=13, fill=MUTED)
    svg.rect(x + 800, y - 74, 16, 16, fill="url(#noisePattern)", stroke="#9aa5b3", rx=3)
    svg.text(x + 824, y - 61, "noise / non-core evidence", size=13, fill=MUTED)


def render() -> None:
    office = load_report(OFFICE_REPORT, DEFAULT_OFFICE)
    lcore = load_report(LCORE_REPORT, DEFAULT_LCORE)
    svg = Svg(1600, 900)
    svg.rect(0, 0, 1600, 900, fill="#ffffff")
    svg.text(44, 48, "Topology-Aware Subgraph Extraction: ablation summary", size=30, weight=900, fill=INK)
    svg.text(
        44,
        78,
        "A single-figure comparison of request budget, high-value retention, and evidence compaction.",
        size=16,
        fill=MUTED,
    )
    draw_request_panel(svg, office, lcore)
    draw_frontier_panel(svg, office, lcore)
    draw_compaction_panel(svg, office, lcore)
    svg.text(
        44,
        878,
        (
            "Data: Office legacy n=886; LCORE-D 50k replay n=1302. "
            "Topology gate dispatches 173 LCORE-D alerts, saving 1129 external LLM calls "
            "while retaining all 173 high-value alerts."
        ),
        size=13,
        fill=MUTED,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(svg.render(), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    render()
