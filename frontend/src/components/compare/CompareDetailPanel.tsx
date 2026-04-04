import { exportCompareSampleDetail } from '../../utils/compareExport'
import type { CompareProviderEvaluation, CompareSampleUnit } from '../../types'

interface CompareDetailPanelProps {
  sample: CompareSampleUnit | undefined
}

function EvaluationColumn(props: {
  title: string
  evaluation: CompareProviderEvaluation
  accent: 'baseline' | 'llm'
}) {
  return (
    <article className={`compare-detail-column compare-detail-column-${props.accent}`}>
      <header className="compare-detail-column-head">
        <div>
          <p>{props.title}</p>
          <strong>{props.evaluation.providerName}</strong>
        </div>
        <span className={`compare-status-chip status-${props.evaluation.status}`}>
          {props.evaluation.status}
        </span>
      </header>

      <div className="compare-detail-metrics">
        <div>
          <span>Completeness</span>
          <strong>{metricLabel(props.evaluation.metrics.explanationCompleteness)}</strong>
        </div>
        <div>
          <span>Actionability</span>
          <strong>{metricLabel(props.evaluation.metrics.actionability)}</strong>
        </div>
        <div>
          <span>Binding</span>
          <strong>{metricLabel(props.evaluation.metrics.evidenceBinding)}</strong>
        </div>
        <div>
          <span>Latency</span>
          <strong>{runtimeLabel(props.evaluation.runtime.latencyMs, 'ms')}</strong>
        </div>
      </div>

      <div className="compare-detail-output">
        {props.evaluation.outputBlocks.map((block) => (
          <section key={`${props.title}-${block.title}`} className="compare-output-block">
            <span>{block.title}</span>
            <ul>
              {block.lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className="compare-detail-output compare-detail-actions">
        <section className="compare-output-block">
          <span>Recommended Actions</span>
          {props.evaluation.recommendedActions.length > 0 ? (
            <ol>
              {props.evaluation.recommendedActions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ol>
          ) : (
            <p className="compare-empty-copy">No action output.</p>
          )}
        </section>
      </div>
    </article>
  )
}

function metricLabel(value: number | null) {
  if (value === null) {
    return 'pending'
  }
  return `${Math.round(value * 100)}%`
}

function runtimeLabel(value: number | null, unit: 'ms' | 'usd') {
  if (value === null) {
    return 'pending'
  }
  return unit === 'ms' ? `${Math.round(value)} ms` : `$${value.toFixed(3)}`
}

export function CompareDetailPanel({ sample }: CompareDetailPanelProps) {
  if (!sample) {
    return (
      <aside className="section compare-shell-section compare-detail-panel is-empty">
        <div className="compare-detail-empty">
          <h3>Detail Panel</h3>
          <p>Select one comparison row to inspect provider outputs, evidence references, and unsupported claims.</p>
        </div>
      </aside>
    )
  }

  return (
    <aside className="section compare-shell-section compare-detail-panel">
      <div className="compare-section-head compare-detail-head">
        <div>
          <h3 className="compare-section-title">A/B Detail</h3>
          <p className="compare-section-copy">
            {sample.bundleId} · {sample.ruleId} · {sample.service}
          </p>
        </div>
        <button
          className="compare-action"
          type="button"
          onClick={() => exportCompareSampleDetail(sample)}
        >
          Export Detail
        </button>
      </div>

      <div className="compare-detail-grid">
        <EvaluationColumn title="Baseline" evaluation={sample.baseline} accent="baseline" />
        <EvaluationColumn title="LLM" evaluation={sample.llm} accent="llm" />
      </div>

      <div className="compare-evidence-section">
        <article className="compare-evidence-card">
          <strong>Evidence Bundle</strong>
          <div className="compare-evidence-grid">
            <section>
              <span>Topology</span>
              <ul>
                {Object.entries(sample.evidenceBundle.topology).map(([key, value]) => (
                  <li key={key}>
                    <code>{key}</code> {Array.isArray(value) ? value.join(', ') : String(value)}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <span>Device</span>
              <ul>
                {Object.entries(sample.evidenceBundle.device).map(([key, value]) => (
                  <li key={key}>
                    <code>{key}</code> {Array.isArray(value) ? value.join(', ') : String(value)}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <span>Change</span>
              <ul>
                {Object.entries(sample.evidenceBundle.change).map(([key, value]) => (
                  <li key={key}>
                    <code>{key}</code> {Array.isArray(value) ? value.join(', ') : String(value)}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <span>Historical</span>
              <ul>
                {Object.entries(sample.evidenceBundle.historical).map(([key, value]) => (
                  <li key={key}>
                    <code>{key}</code> {Array.isArray(value) ? value.join(', ') : String(value)}
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </article>

        <article className="compare-evidence-card">
          <strong>Evidence-Reference Mapping</strong>
          <div className="compare-reference-map">
            {sample.baseline.evidenceReferences.map((reference) => (
              <div key={reference.id} className="compare-reference-row baseline">
                <span className="compare-reference-claim">{reference.claim}</span>
                <span className="compare-reference-line" />
                <span className="compare-reference-source">
                  {reference.sourceSection}.{reference.sourceField}
                </span>
              </div>
            ))}
            {sample.llm.evidenceReferences.map((reference) => (
              <div key={reference.id} className="compare-reference-row llm">
                <span className="compare-reference-claim">{reference.claim}</span>
                <span className="compare-reference-line" />
                <span className="compare-reference-source">
                  {reference.sourceSection}.{reference.sourceField}
                </span>
              </div>
            ))}
          </div>
        </article>

        <article className="compare-evidence-card">
          <strong>Unsupported Claims</strong>
          {sample.llm.unsupportedClaims.length > 0 ? (
            <ul className="compare-unsupported-list">
              {sample.llm.unsupportedClaims.map((claim) => (
                <li key={claim.id}>
                  <span className={`compare-status-chip severity-${claim.severity}`}>
                    {claim.severity}
                  </span>
                  <div>
                    <strong>{claim.claim}</strong>
                    <p>{claim.reason}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="compare-empty-copy">No unsupported claims recorded for the active LLM slice.</p>
          )}
        </article>

        <article className="compare-evidence-card">
          <strong>Metric Reasoning Notes</strong>
          <ul className="compare-note-list">
            {sample.reviewNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
            {sample.baseline.notes.map((note) => (
              <li key={`baseline-${note}`}>Baseline: {note}</li>
            ))}
            {sample.llm.notes.map((note) => (
              <li key={`llm-${note}`}>LLM: {note}</li>
            ))}
          </ul>
          <div className="compare-runtime-ledger">
            <span>{sample.replay.replayLabel}</span>
            <span>run {sample.replay.runId}</span>
            <span>baseline {runtimeLabel(sample.baseline.runtime.estimatedCostUsd, 'usd')}</span>
            <span>llm {runtimeLabel(sample.llm.runtime.estimatedCostUsd, 'usd')}</span>
          </div>
        </article>
      </div>
    </aside>
  )
}
