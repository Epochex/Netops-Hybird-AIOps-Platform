import { useMemo } from 'react'
import type {
  FeedEvent,
  RuntimeSnapshot,
  StageNode,
  StrategyControl,
  SuggestionRecord,
} from '../types'

interface LiveFlowConsoleProps {
  snapshot: RuntimeSnapshot
  selectedSuggestion: SuggestionRecord
  onSelectSuggestion: (suggestionId: string) => void
}

interface LifecycleBlock {
  id: string
  title: string
  subtitle: string
  status: StageNode['status']
  metrics: Array<{ label: string; value: string }>
}

function controlValue(controls: StrategyControl[], label: string) {
  return controls.find((control) => control.label === label)?.currentValue ?? 'n/a'
}

function buildLifecycle(snapshot: RuntimeSnapshot): LifecycleBlock[] {
  const stageLookup = new Map(snapshot.stageNodes.map((node) => [node.id, node]))
  const clusterTarget = Number.parseInt(
    controlValue(snapshot.strategyControls, 'AIOPS_CLUSTER_MIN_ALERTS'),
    10,
  )
  const clusterWindow = controlValue(
    snapshot.strategyControls,
    'AIOPS_CLUSTER_WINDOW_SEC',
  )
  const clusterProgress = Math.max(
    0,
    ...snapshot.clusterWatch.map((item) => item.progress),
  )
  const clusterLive = snapshot.suggestions.some(
    (suggestion) => suggestion.scope === 'cluster',
  )
  const clusterStatus: StageNode['status'] = clusterLive
    ? 'flowing'
    : clusterProgress > 0
      ? 'watch'
      : 'steady'

  const sourceIds = [
    'fortigate',
    'ingest',
    'forwarder',
    'raw-topic',
    'correlator',
    'alerts-topic',
    'aiops-agent',
    'suggestions-topic',
    'remediation',
  ]

  const orderedStages = sourceIds
    .map((id) => stageLookup.get(id))
    .filter((stage): stage is StageNode => Boolean(stage))
    .map((stage) => ({
      id: stage.id,
      title: stage.title,
      subtitle: stage.subtitle,
      status: stage.status,
      metrics: stage.metrics.slice(0, 2),
    }))

  const clusterBlock: LifecycleBlock = {
    id: 'cluster-window',
    title: 'cluster window',
    subtitle: 'same-key aggregation gate',
    status: clusterStatus,
    metrics: [
      {
        label: 'progress',
        value: `${clusterProgress}/${Number.isFinite(clusterTarget) ? clusterTarget : 3}`,
      },
      {
        label: 'window',
        value: `${clusterWindow}s`,
      },
    ],
  }

  return [
    ...orderedStages.slice(0, 6),
    clusterBlock,
    ...orderedStages.slice(6),
  ]
}

function pulseStageIds(kind: FeedEvent['kind'], scope: SuggestionRecord['scope']) {
  if (kind === 'raw') {
    return ['fortigate', 'ingest', 'forwarder', 'raw-topic']
  }

  if (kind === 'alert') {
    return ['correlator', 'alerts-topic', 'cluster-window']
  }

  return scope === 'cluster'
    ? ['cluster-window', 'aiops-agent', 'suggestions-topic', 'remediation']
    : ['aiops-agent', 'suggestions-topic', 'remediation']
}

function currentStageIndex(blocks: LifecycleBlock[], kind: FeedEvent['kind']) {
  if (kind === 'raw') {
    return blocks.findIndex((block) => block.id === 'raw-topic')
  }

  if (kind === 'alert') {
    return blocks.findIndex((block) => block.id === 'cluster-window')
  }

  return blocks.findIndex((block) => block.id === 'suggestions-topic')
}

export function LiveFlowConsole({
  snapshot,
  selectedSuggestion,
  onSelectSuggestion,
}: LiveFlowConsoleProps) {
  const pulseKind = snapshot.feed[0]?.kind ?? 'suggestion'
  const lifecycle = useMemo(() => buildLifecycle(snapshot), [snapshot])
  const pulseIds = useMemo(
    () => pulseStageIds(pulseKind, selectedSuggestion.scope),
    [pulseKind, selectedSuggestion.scope],
  )
  const leadEventId =
    snapshot.feed[0]?.id ??
    snapshot.runtime.latestSuggestionTs ??
    snapshot.runtime.latestAlertTs
  const tickerFeed = snapshot.feed.slice(0, 8)
  const compactMetrics = snapshot.overviewMetrics.filter((metric) =>
    ['raw-freshness', 'backlog', 'current-day-volume', 'closure'].includes(
      metric.id,
    ),
  )
  const activeStageIndex = currentStageIndex(lifecycle, pulseKind)

  return (
    <section className="page console-page">
      <section className="section lifecycle-stage">
        <div className="section-header">
          <div>
            <h2 className="section-title">Live Event Lifecycle</h2>
            <span className="section-subtitle">
              Process first: ingest, deterministic alerting, cluster gate,
              suggestion, remediation boundary.
            </span>
          </div>
          <div className="annotation-stack">
            <span className="section-kicker">directional runtime flow</span>
            <span className={`signal-chip tone-${pulseKind}`}>{pulseKind}</span>
          </div>
        </div>

        <div className="lifecycle-track">
          {lifecycle.map((block, index) => {
            const isPulsing = pulseIds.includes(block.id)
            const pulseClass = isPulsing
              ? `pulse-${leadEventId.length % 2}`
              : ''
            const reached = index <= activeStageIndex ? 'is-reached' : ''

            return (
              <div
                key={`${block.id}-${isPulsing ? leadEventId : 'steady'}`}
                className="stage-segment"
              >
                <article
                  className={`stage-card state-${block.status} ${pulseClass} ${reached}`}
                >
                  <div className="stage-header">
                    <span className="stage-index">
                      {(index + 1).toString().padStart(2, '0')}
                    </span>
                    <div>
                      <strong>{block.title}</strong>
                      <span>{block.subtitle}</span>
                    </div>
                  </div>
                  <ul className="stage-metrics">
                    {block.metrics.map((metric) => (
                      <li key={`${block.id}-${metric.label}`}>
                        <span>{metric.label}</span>
                        <strong>{metric.value}</strong>
                      </li>
                    ))}
                  </ul>
                </article>

                {index < lifecycle.length - 1 ? (
                  <div
                    className={`stage-link ${pulseIds.includes(lifecycle[index + 1].id) ? `pulse-${leadEventId.length % 2}` : ''}`}
                    aria-hidden="true"
                  >
                    <span className="stage-link-line" />
                    <span className="stage-link-runner" />
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>

        <div className="micro-metric-rail">
          {compactMetrics.map((metric) => (
            <div key={metric.id} className={`micro-metric state-${metric.state}`}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      </section>

      <div className="console-core">
        <section className="section cluster-rail">
          <div className="section-header">
            <div>
              <h2 className="section-title">Cluster Watch</h2>
              <span className="section-subtitle">
                Same-key pre-trigger surface for the live cluster path.
              </span>
            </div>
            <span className="section-kicker">600s / min=3</span>
          </div>
          <ul className="cluster-list">
            {snapshot.clusterWatch.map((item) => (
              <li key={item.key} className="cluster-item">
                <div className="cluster-head">
                  <div>
                    <strong>{item.service}</strong>
                    <span>{item.device}</span>
                  </div>
                  <span className="cluster-ratio">
                    {item.progress}/{item.target}
                  </span>
                </div>
                <div className="cluster-progress" aria-hidden="true">
                  <span
                    style={{
                      width: `${Math.min(100, (item.progress / item.target) * 100)}%`,
                    }}
                  />
                </div>
                <p>{item.note}</p>
              </li>
            ))}
          </ul>
        </section>

        <section key={selectedSuggestion.id} className="section story-panel">
          <div className="section-header">
            <div>
              <h2 className="section-title">Selected Runtime Story</h2>
              <span className="section-subtitle">
                Timeline-driven explanation for the active suggestion slice.
              </span>
            </div>
            <span className="section-kicker">{selectedSuggestion.scope}-scope</span>
          </div>

          <div className="story-summary">
            <div>
              <p className="story-marker">active slice</p>
              <h3>{selectedSuggestion.summary}</h3>
            </div>
            <div className="story-badges">
              <span className="signal-chip tone-suggestion">
                {selectedSuggestion.context.service}
              </span>
              <span className="signal-chip tone-neutral">
                {selectedSuggestion.context.srcDeviceKey}
              </span>
              <span className="signal-chip tone-alert">
                {selectedSuggestion.priority}
              </span>
            </div>
          </div>

          <ol className="timeline-list">
            {snapshot.timeline.map((step, index) => (
              <li
                key={`${selectedSuggestion.id}-${step.id}`}
                className={`timeline-item ${index <= activeStageIndex ? 'is-active' : ''}`}
                style={{ animationDelay: `${index * 90}ms` }}
              >
                <span className="timeline-stamp">{step.stamp}</span>
                <div className="timeline-body">
                  <h3>{step.title}</h3>
                  <p>{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="section slice-panel">
          <div className="section-header">
            <div>
              <h2 className="section-title">Live Slices</h2>
              <span className="section-subtitle">
                Select the current alert or cluster thread. The right drawer
                pivots with it.
              </span>
            </div>
            <span className="section-kicker">evidence pivot</span>
          </div>

          <ul className="slice-list">
            {snapshot.suggestions.slice(0, 12).map((suggestion) => (
              <li key={suggestion.id}>
                <button
                  type="button"
                  className={
                    selectedSuggestion.id === suggestion.id
                      ? 'slice-button is-active'
                      : 'slice-button'
                  }
                  onClick={() => onSelectSuggestion(suggestion.id)}
                >
                  <div className="slice-button-head">
                    <span className={`signal-chip tone-${suggestion.scope === 'cluster' ? 'alert' : 'suggestion'}`}>
                      {suggestion.scope}
                    </span>
                    <span>{suggestion.suggestionTs}</span>
                  </div>
                  <strong>{suggestion.context.service}</strong>
                  <span>{suggestion.context.srcDeviceKey}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="section activity-strip">
        <div className="section-header">
          <div>
            <h2 className="section-title">Live Activity Strip</h2>
            <span className="section-subtitle">
              Runtime motion is carried by real feed events, not decorative
              animation.
            </span>
          </div>
          <span className="section-kicker">raw → alert → suggestion</span>
        </div>

        <div key={leadEventId} className="ticker-window">
          <div className="ticker-track">
            {[...tickerFeed, ...tickerFeed].map((event, index) => (
              <article
                key={`${event.id}-${index}`}
                className={`ticker-item kind-${event.kind}`}
              >
                <span className="ticker-stamp">{event.stamp}</span>
                <span className="ticker-kind">{event.kind}</span>
                <strong>{event.title}</strong>
                <span>{event.detail}</span>
              </article>
            ))}
          </div>
        </div>
      </section>
    </section>
  )
}
