import type { ReactNode } from 'react'
import {
  buildMetricDistribution,
  buildMetricMatrix,
  buildProviderScatter,
  buildReplayGroups,
  buildRuleGroups,
  buildSeverityGroups,
  buildStatusCounts,
} from '../../data/compareWorkbench'
import type { CompareSampleUnit, CompareTabId } from '../../types'

interface CompareChartsProps {
  activeTab: CompareTabId
  samples: CompareSampleUnit[]
}

function percentLabel(value: number | null) {
  if (value === null) {
    return 'pending'
  }
  return `${Math.round(value * 100)}%`
}

function MetricBlock(props: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <article className="compare-chart-block">
      <div className="compare-chart-meta">
        <strong>{props.title}</strong>
        <p>{props.subtitle}</p>
      </div>
      {props.children}
    </article>
  )
}

function GroupedMetricChart(props: {
  title: string
  groups: Array<{
    label: string
    baseline: Record<string, number | null>
    llm: Record<string, number | null>
  }>
  metricKey: string
  formatter?: (value: number | null) => string
}) {
  const width = 620
  const height = 260
  const left = 24
  const right = 16
  const top = 18
  const bottom = 52
  const chartWidth = width - left - right
  const chartHeight = height - top - bottom
  const groupWidth = chartWidth / Math.max(props.groups.length, 1)
  const barWidth = Math.min(26, groupWidth / 4)

  return (
    <MetricBlock
      title={props.title}
      subtitle="Grouped provider averages. The same alert / evidence unit stays fixed."
    >
      <svg className="compare-svg" viewBox={`0 0 ${width} ${height}`} role="img">
        <line x1={left} y1={top + chartHeight} x2={width - right} y2={top + chartHeight} className="compare-axis" />
        <line x1={left} y1={top} x2={left} y2={top + chartHeight} className="compare-axis" />
        {props.groups.map((group, index) => {
          const baselineValue = group.baseline[props.metricKey] ?? 0
          const llmValue = group.llm[props.metricKey] ?? 0
          const x = left + groupWidth * index + groupWidth / 2
          const baselineHeight = chartHeight * baselineValue
          const llmHeight = chartHeight * llmValue
          return (
            <g key={group.label}>
              <line
                x1={left + groupWidth * index}
                y1={top + chartHeight}
                x2={left + groupWidth * index}
                y2={top}
                className="compare-guide"
              />
              <rect
                x={x - barWidth - 4}
                y={top + chartHeight - baselineHeight}
                width={barWidth}
                height={baselineHeight}
                className="compare-bar compare-bar-baseline"
              />
              <rect
                x={x + 4}
                y={top + chartHeight - llmHeight}
                width={barWidth}
                height={llmHeight}
                className="compare-bar compare-bar-llm"
              />
              <text x={x - barWidth / 2 - 4} y={top + chartHeight - baselineHeight - 6} className="compare-value-text">
                {props.formatter ? props.formatter(group.baseline[props.metricKey] ?? null) : percentLabel(group.baseline[props.metricKey] ?? null)}
              </text>
              <text x={x + barWidth / 2 + 4} y={top + chartHeight - llmHeight - 6} className="compare-value-text compare-value-text-llm">
                {props.formatter ? props.formatter(group.llm[props.metricKey] ?? null) : percentLabel(group.llm[props.metricKey] ?? null)}
              </text>
              <text x={x} y={height - 18} textAnchor="middle" className="compare-axis-label">
                {group.label}
              </text>
            </g>
          )
        })}
      </svg>
    </MetricBlock>
  )
}

function MetricHeatmap(props: {
  matrix: Array<{
    id: string
    label: string
    baseline: Record<string, number | null>
    llm: Record<string, number | null>
  }>
  metricKeys: string[]
}) {
  return (
    <MetricBlock
      title="Metric Matrix"
      subtitle="Per-bundle metric field. Baseline and LLM cells share the same row anchor."
    >
      <div className="compare-heatmap">
        <div className="compare-heatmap-header">
          <span>Bundle</span>
          {props.metricKeys.flatMap((metricKey) => [
            <span key={`${metricKey}-b`}>{metricKey} / B</span>,
            <span key={`${metricKey}-l`}>{metricKey} / L</span>,
          ])}
        </div>
        {props.matrix.map((row) => (
          <div key={row.id} className="compare-heatmap-row">
            <span className="compare-heatmap-label">{row.label}</span>
            {props.metricKeys.flatMap((metricKey) => [
              <span
                key={`${row.id}-${metricKey}-b`}
                className="compare-heatmap-cell baseline"
                style={cellStyle(row.baseline[metricKey] ?? null)}
              >
                {percentLabel(row.baseline[metricKey] ?? null)}
              </span>,
              <span
                key={`${row.id}-${metricKey}-l`}
                className="compare-heatmap-cell llm"
                style={cellStyle(row.llm[metricKey] ?? null)}
              >
                {percentLabel(row.llm[metricKey] ?? null)}
              </span>,
            ])}
          </div>
        ))}
      </div>
    </MetricBlock>
  )
}

function cellStyle(value: number | null) {
  if (value === null) {
    return { opacity: 0.45 }
  }
  return {
    opacity: Math.max(0.22, value),
  }
}

function ScatterChart(props: {
  points: Array<{
    id: string
    label: string
    provider: string
    x: number | null
    y: number | null
    alertId: string
    ruleId: string
    state: string
  }>
}) {
  const width = 620
  const height = 260
  const left = 34
  const right = 18
  const top = 18
  const bottom = 36
  const chartWidth = width - left - right
  const chartHeight = height - top - bottom

  return (
    <MetricBlock
      title="Actionability vs Evidence Binding"
      subtitle="Each point is one provider output on the same comparison unit."
    >
      <svg className="compare-svg" viewBox={`0 0 ${width} ${height}`} role="img">
        <line x1={left} y1={top + chartHeight} x2={width - right} y2={top + chartHeight} className="compare-axis" />
        <line x1={left} y1={top} x2={left} y2={top + chartHeight} className="compare-axis" />
        {[0.25, 0.5, 0.75, 1].map((tick) => (
          <g key={tick}>
            <line
              x1={left}
              y1={top + chartHeight - chartHeight * tick}
              x2={width - right}
              y2={top + chartHeight - chartHeight * tick}
              className="compare-guide"
            />
            <text x={8} y={top + chartHeight - chartHeight * tick + 4} className="compare-axis-label">
              {Math.round(tick * 100)}
            </text>
          </g>
        ))}
        {props.points.map((point) => {
          if (point.x === null || point.y === null) {
            return null
          }
          const x = left + chartWidth * point.x
          const y = top + chartHeight - chartHeight * point.y
          return (
            <g key={point.id}>
              <circle
                cx={x}
                cy={y}
                r={point.provider === 'Baseline' ? 5 : 7}
                className={point.provider === 'Baseline' ? 'compare-point-baseline' : 'compare-point-llm'}
              />
              <text x={x + 8} y={y - 8} className="compare-axis-label">
                {point.label}
              </text>
            </g>
          )
        })}
      </svg>
    </MetricBlock>
  )
}

function quantile(values: number[], position: number) {
  if (values.length === 0) {
    return null
  }
  const sorted = [...values].sort((left, right) => left - right)
  const index = (sorted.length - 1) * position
  const lower = Math.floor(index)
  const upper = Math.ceil(index)
  if (lower === upper) {
    return sorted[lower]
  }
  const weight = index - lower
  return sorted[lower] * (1 - weight) + sorted[upper] * weight
}

function BoxPlot(props: {
  baseline: number[]
  llm: number[]
  unit: 'ms' | 'usd'
  title: string
  subtitle: string
}) {
  const maxValue = Math.max(...props.baseline, ...props.llm, 1)
  const width = 420
  const height = 180
  const left = 24
  const right = 16
  const top = 22
  const bottom = 28
  const chartWidth = width - left - right
  const chartHeight = height - top - bottom
  const centerBaseline = left + chartWidth * 0.3
  const centerLlm = left + chartWidth * 0.7

  const renderBox = (values: number[], centerX: number, className: string) => {
    if (values.length === 0) {
      return null
    }
    const q1 = quantile(values, 0.25) ?? 0
    const median = quantile(values, 0.5) ?? 0
    const q3 = quantile(values, 0.75) ?? 0
    const low = quantile(values, 0) ?? 0
    const high = quantile(values, 1) ?? 0
    const scale = (value: number) => top + chartHeight - (value / maxValue) * chartHeight
    return (
      <g className={className}>
        <line x1={centerX} y1={scale(low)} x2={centerX} y2={scale(high)} className="compare-axis" />
        <rect x={centerX - 26} y={scale(q3)} width={52} height={Math.max(8, scale(q1) - scale(q3))} className="compare-box" />
        <line x1={centerX - 26} y1={scale(median)} x2={centerX + 26} y2={scale(median)} className="compare-axis" />
        <line x1={centerX - 18} y1={scale(low)} x2={centerX + 18} y2={scale(low)} className="compare-axis" />
        <line x1={centerX - 18} y1={scale(high)} x2={centerX + 18} y2={scale(high)} className="compare-axis" />
      </g>
    )
  }

  return (
    <MetricBlock title={props.title} subtitle={props.subtitle}>
      <svg className="compare-svg" viewBox={`0 0 ${width} ${height}`} role="img">
        <line x1={left} y1={top + chartHeight} x2={width - right} y2={top + chartHeight} className="compare-axis" />
        <line x1={left} y1={top} x2={left} y2={top + chartHeight} className="compare-axis" />
        {renderBox(props.baseline, centerBaseline, 'compare-box-baseline')}
        {renderBox(props.llm, centerLlm, 'compare-box-llm')}
        <text x={centerBaseline} y={height - 10} textAnchor="middle" className="compare-axis-label">
          Baseline
        </text>
        <text x={centerLlm} y={height - 10} textAnchor="middle" className="compare-axis-label">
          LLM
        </text>
        <text x={left} y={12} className="compare-axis-label">
          {props.unit === 'ms' ? 'ms' : 'usd'}
        </text>
      </svg>
    </MetricBlock>
  )
}

function StatusBlock(props: {
  counts: {
    baselineReady: number
    llmReady: number
    llmPlaceholder: number
    llmFailed: number
    hallucinationFlags: number
  }
}) {
  return (
    <MetricBlock
      title="Status Ledger"
      subtitle="Runtime review counts anchored to provider status and unsupported-claim markers."
    >
      <div className="compare-ledger">
        <div>
          <span>Baseline ready</span>
          <strong>{props.counts.baselineReady}</strong>
        </div>
        <div>
          <span>LLM ready</span>
          <strong>{props.counts.llmReady}</strong>
        </div>
        <div>
          <span>LLM placeholder</span>
          <strong>{props.counts.llmPlaceholder}</strong>
        </div>
        <div>
          <span>LLM failed</span>
          <strong>{props.counts.llmFailed}</strong>
        </div>
        <div>
          <span>Hallucination flags</span>
          <strong>{props.counts.hallucinationFlags}</strong>
        </div>
      </div>
    </MetricBlock>
  )
}

function NoteBlock(props: { title: string; notes: string[] }) {
  return (
    <MetricBlock title={props.title} subtitle="Evaluation notes for the active filtered slice.">
      <ul className="compare-note-list">
        {props.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </MetricBlock>
  )
}

export function CompareCharts({ activeTab, samples }: CompareChartsProps) {
  const ruleGroups = buildRuleGroups(samples)
  const severityGroups = buildSeverityGroups(samples)
  const replayGroups = buildReplayGroups(samples)
  const matrix = buildMetricMatrix(samples, [
    'explanationCompleteness',
    'actionability',
    'evidenceBinding',
  ])
  const scatter = buildProviderScatter(samples)
  const latencyDistribution = buildMetricDistribution(samples, 'latencyMs')
  const costDistribution = buildMetricDistribution(samples, 'estimatedCostUsd')
  const statusCounts = buildStatusCounts(samples)

  if (activeTab === 'explanation') {
    return (
      <div className="compare-analysis-grid">
        <GroupedMetricChart title="Rule Group View" groups={ruleGroups} metricKey="explanationCompleteness" />
        <MetricHeatmap matrix={matrix} metricKeys={['explanationCompleteness', 'evidenceBinding']} />
        <NoteBlock
          title="Interpretation"
          notes={[
            'This tab compares explanation coverage on the same alert and evidence bundle.',
            'High completeness without matching evidence binding should be reviewed in the detail panel.',
            'Rows with placeholder or failed LLM outputs stay visible instead of being dropped from the slice.',
          ]}
        />
      </div>
    )
  }

  if (activeTab === 'action') {
    return (
      <div className="compare-analysis-grid">
        <ScatterChart points={scatter} />
        <GroupedMetricChart title="Actionability by Rule" groups={ruleGroups} metricKey="actionability" />
        <NoteBlock
          title="Interpretation"
          notes={[
            'Actionability is evaluated against the same evidence unit, not against anomaly detection success.',
            'Points moving right without moving upward indicate better evidence attachment without better action specificity.',
            'Rows with unsupported causal wording should be reviewed in the evidence-reference mapping panel.',
          ]}
        />
      </div>
    )
  }

  if (activeTab === 'stability') {
    return (
      <div className="compare-analysis-grid">
        <GroupedMetricChart title="Replay Group View" groups={replayGroups} metricKey="stability" />
        <GroupedMetricChart title="Severity Group View" groups={severityGroups} metricKey="auditability" />
        <StatusBlock counts={statusCounts} />
      </div>
    )
  }

  return (
    <div className="compare-analysis-grid">
      <BoxPlot
        baseline={latencyDistribution.baseline}
        llm={latencyDistribution.llm}
        unit="ms"
        title="Latency Distribution"
        subtitle="Per-suggestion runtime spread under the active filter set."
      />
      <BoxPlot
        baseline={costDistribution.baseline}
        llm={costDistribution.llm}
        unit="usd"
        title="Cost Distribution"
        subtitle="Estimated per-suggestion spend for the compared provider path."
      />
      <StatusBlock counts={statusCounts} />
    </div>
  )
}
