import { formatCellMetric } from '../../data/compareWorkbench'
import type { CompareSampleUnit } from '../../types'

interface CompareSampleTableProps {
  samples: CompareSampleUnit[]
  selectedSampleId: string
  sortKey: string
  sortDirection: 'asc' | 'desc'
  onRowSelect: (sampleId: string) => void
  onSortChange: (sortKey: string) => void
}

const columns = [
  { id: 'bundleId', label: 'bundle_id' },
  { id: 'alertId', label: 'alert_id' },
  { id: 'ruleId', label: 'rule_id' },
  { id: 'severity', label: 'severity' },
  { id: 'service', label: 'service' },
  { id: 'device', label: 'device' },
  { id: 'baselineStatus', label: 'baseline' },
  { id: 'llmStatus', label: 'llm' },
  { id: 'baseline.explanationCompleteness', label: 'exp. / B' },
  { id: 'llm.explanationCompleteness', label: 'exp. / L' },
  { id: 'baseline.actionability', label: 'act. / B' },
  { id: 'llm.actionability', label: 'act. / L' },
  { id: 'baseline.evidenceBinding', label: 'bind / B' },
  { id: 'llm.evidenceBinding', label: 'bind / L' },
  { id: 'llm.hallucinationRate', label: 'halluc.' },
  { id: 'baseline.latencyMs', label: 'lat. / B' },
  { id: 'llm.latencyMs', label: 'lat. / L' },
  { id: 'llm.estimatedCostUsd', label: 'cost' },
  { id: 'llm.failureRate', label: 'fail' },
  { id: 'replayLabel', label: 'replay' },
] as const

function SortButton(props: {
  columnId: string
  label: string
  sortKey: string
  sortDirection: 'asc' | 'desc'
  onSortChange: (sortKey: string) => void
}) {
  const isActive = props.sortKey === props.columnId
  return (
    <button
      type="button"
      className={`compare-sort-button ${isActive ? 'is-active' : ''}`}
      onClick={() => props.onSortChange(props.columnId)}
    >
      {props.label}
      <span>{isActive ? (props.sortDirection === 'asc' ? '↑' : '↓') : '·'}</span>
    </button>
  )
}

export function CompareSampleTable({
  samples,
  selectedSampleId,
  sortKey,
  sortDirection,
  onRowSelect,
  onSortChange,
}: CompareSampleTableProps) {
  return (
    <section className="section compare-shell-section">
      <div className="compare-section-head">
        <div>
          <h3 className="compare-section-title">Sample-Level Comparison</h3>
          <p className="compare-section-copy">
            Each row is one alert / evidence bundle comparison unit.
          </p>
        </div>
        <span className="compare-inline-note">{samples.length} rows</span>
      </div>

      <div className="compare-table-wrap">
        <table className="compare-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.id}>
                  <SortButton
                    columnId={column.id}
                    label={column.label}
                    sortKey={sortKey}
                    sortDirection={sortDirection}
                    onSortChange={onSortChange}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {samples.map((sample) => (
              <tr
                key={sample.id}
                className={sample.id === selectedSampleId ? 'is-selected' : ''}
                onClick={() => onRowSelect(sample.id)}
              >
                <td>{sample.bundleId}</td>
                <td>{sample.alertId}</td>
                <td>{sample.ruleId}</td>
                <td>{sample.severity}</td>
                <td>{sample.service}</td>
                <td>{sample.device}</td>
                <td>{sample.baseline.status}</td>
                <td>{sample.llm.status}</td>
                <td>{formatCellMetric(sample, 'baseline', 'explanationCompleteness')}</td>
                <td>{formatCellMetric(sample, 'llm', 'explanationCompleteness')}</td>
                <td>{formatCellMetric(sample, 'baseline', 'actionability')}</td>
                <td>{formatCellMetric(sample, 'llm', 'actionability')}</td>
                <td>{formatCellMetric(sample, 'baseline', 'evidenceBinding')}</td>
                <td>{formatCellMetric(sample, 'llm', 'evidenceBinding')}</td>
                <td>{formatCellMetric(sample, 'llm', 'hallucinationRate')}</td>
                <td>{formatCellMetric(sample, 'baseline', 'latencyMs')}</td>
                <td>{formatCellMetric(sample, 'llm', 'latencyMs')}</td>
                <td>{formatCellMetric(sample, 'llm', 'estimatedCostUsd')}</td>
                <td>{formatCellMetric(sample, 'llm', 'failureRate')}</td>
                <td>{sample.replay.replayLabel}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
