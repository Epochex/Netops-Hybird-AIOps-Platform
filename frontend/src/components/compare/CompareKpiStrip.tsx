import type { CompareKpiCard } from '../../types'

interface CompareKpiStripProps {
  cards: CompareKpiCard[]
}

export function CompareKpiStrip({ cards }: CompareKpiStripProps) {
  return (
    <section className="section compare-shell-section">
      <div className="compare-section-head">
        <div>
          <h3 className="compare-section-title">Summary Strip</h3>
          <p className="compare-section-copy">
            Same-unit provider comparison across explanation, action, evidence, stability, and runtime.
          </p>
        </div>
      </div>

      <div className="compare-kpi-strip">
        {cards.map((card) => (
          <article key={card.id} className={`compare-kpi-card delta-${card.deltaState}`}>
            <div className="compare-kpi-head">
              <span className="compare-kpi-label">{card.label}</span>
              <span className="compare-kpi-delta">{card.deltaDisplay}</span>
            </div>

            <div className="compare-kpi-values">
              <div>
                <span className="compare-kpi-side">Baseline</span>
                <strong>{card.ruleDisplay}</strong>
              </div>
              <div>
                <span className="compare-kpi-side">LLM</span>
                <strong>{card.llmDisplay}</strong>
              </div>
            </div>

            <p className="compare-kpi-note">{card.note}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
