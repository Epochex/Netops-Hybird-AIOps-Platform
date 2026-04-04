import { CompareCharts } from './CompareCharts'
import type { CompareSampleUnit, CompareTabId } from '../../types'

const tabs: Array<{ id: CompareTabId; label: string; subtitle: string }> = [
  {
    id: 'explanation',
    label: 'Explanation Quality',
    subtitle: 'Completeness and evidence attachment on the same bundle.',
  },
  {
    id: 'action',
    label: 'Action Quality',
    subtitle: 'Specificity and review usefulness of the suggested action path.',
  },
  {
    id: 'stability',
    label: 'Stability & Auditability',
    subtitle: 'Replay consistency, review path, and failure visibility.',
  },
  {
    id: 'runtime',
    label: 'Cost & Runtime',
    subtitle: 'Latency, spend, and provider-side runtime behavior.',
  },
]

interface CompareAnalysisTabsProps {
  activeTab: CompareTabId
  samples: CompareSampleUnit[]
  onTabChange: (tabId: CompareTabId) => void
}

export function CompareAnalysisTabs({
  activeTab,
  samples,
  onTabChange,
}: CompareAnalysisTabsProps) {
  const activeTabMeta = tabs.find((tab) => tab.id === activeTab) ?? tabs[0]

  return (
    <section className="section compare-shell-section">
      <div className="compare-section-head">
        <div>
          <h3 className="compare-section-title">Analytical Area</h3>
          <p className="compare-section-copy">{activeTabMeta.subtitle}</p>
        </div>
      </div>

      <div className="compare-tab-strip" role="tablist" aria-label="Compare analysis tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`compare-tab ${tab.id === activeTab ? 'is-active' : ''}`}
            type="button"
            role="tab"
            aria-selected={tab.id === activeTab}
            onClick={() => onTabChange(tab.id)}
          >
            <span>{tab.label}</span>
            <small>{tab.subtitle}</small>
          </button>
        ))}
      </div>

      <CompareCharts activeTab={activeTab} samples={samples} />
    </section>
  )
}
