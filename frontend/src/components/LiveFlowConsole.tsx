import { useState } from 'react'
import type {
  FeedEvent,
  RuntimeSnapshot,
  RuntimeStreamDelta,
  StageNode,
  StageTelemetry,
  StrategyControl,
  SuggestionRecord,
} from '../types'
import {
  formatDurationMs,
  formatMaybeTimestamp,
  timestampTooltip,
} from '../utils/time'

interface LiveFlowConsoleProps {
  snapshot: RuntimeSnapshot
  latestDelta: RuntimeStreamDelta | null
  selectedSuggestion: SuggestionRecord
  onSelectSuggestion: (suggestionId: string) => void
}

interface LifecycleBand {
  mode: StageTelemetry['mode']
  state: StageTelemetry['state']
  label: string
  value: string
  detail: string
  stamp?: string
  meter: number
  tone: 'raw' | 'alert' | 'suggestion' | 'neutral' | 'planned'
}

interface LifecyclePhase {
  id: string
  title: string
  purpose: string
  systems: string
  status: StageNode['status']
  stageIds: string[]
  facts: string[]
  band: LifecycleBand
}

function controlValue(controls: StrategyControl[], label: string) {
  return controls.find((control) => control.label === label)?.currentValue ?? 'n/a'
}

function stageMetricValue(node: StageNode | undefined, label: string) {
  return node?.metrics.find((metric) => metric.label === label)?.value ?? 'n/a'
}

function buildLifecycle(
  snapshot: RuntimeSnapshot,
  linkedSuggestion: SuggestionRecord,
): LifecyclePhase[] {
  const stageLookup = new Map(snapshot.stageNodes.map((node) => [node.id, node]))
  const telemetryLookup = new Map(
    (linkedSuggestion.stageTelemetry ?? []).map((item) => [item.stageId, item]),
  )
  const clusterTarget = Number.parseInt(
    controlValue(snapshot.strategyControls, 'AIOPS_CLUSTER_MIN_ALERTS'),
    10,
  )
  const clusterWindow = Number.parseInt(
    controlValue(snapshot.strategyControls, 'AIOPS_CLUSTER_WINDOW_SEC'),
    10,
  )
  const safeClusterTarget = Number.isFinite(clusterTarget) ? clusterTarget : 3
  const safeClusterWindow = Number.isFinite(clusterWindow) ? clusterWindow : 600
  const clusterProgress = Math.max(
    0,
    ...snapshot.clusterWatch.map((item) => item.progress),
  )
  const clusterRemaining = Math.max(0, safeClusterTarget - clusterProgress)
  const fortigate = stageLookup.get('fortigate')
  const ingest = stageLookup.get('ingest')
  const forwarder = stageLookup.get('forwarder')
  const rawTopic = stageLookup.get('raw-topic')
  const correlator = stageLookup.get('correlator')
  const alertsTopic = stageLookup.get('alerts-topic')
  const aiopsAgent = stageLookup.get('aiops-agent')
  const suggestionsTopic = stageLookup.get('suggestions-topic')
  const remediation = stageLookup.get('remediation')
  const sourceTs =
    telemetryLookup.get('raw-topic')?.endedAt ??
    telemetryLookup.get('ingest')?.endedAt ??
    telemetryLookup.get('fortigate')?.endedAt
  const handoffTs =
    telemetryLookup.get('raw-topic')?.endedAt ??
    telemetryLookup.get('forwarder')?.endedAt ??
    telemetryLookup.get('ingest')?.endedAt
  const alertTs =
    telemetryLookup.get('alerts-topic')?.endedAt ??
    telemetryLookup.get('correlator')?.endedAt
  const suggestionTs =
    telemetryLookup.get('suggestions-topic')?.endedAt ??
    telemetryLookup.get('aiops-agent')?.endedAt
  const clusterTelemetry = telemetryLookup.get('cluster-window')
  const clusterState: StageNode['status'] =
    linkedSuggestion.scope === 'cluster'
      ? 'flowing'
      : clusterProgress > 0
        ? 'watch'
        : 'steady'

  return [
    {
      id: 'source-signal',
      title: 'Source Signal',
      purpose: 'A real device log has entered the platform.',
      systems: 'FortiGate',
      status: fortigate?.status ?? 'steady',
      stageIds: ['fortigate'],
      facts: [
        stageMetricValue(fortigate, 'mode'),
        stageMetricValue(fortigate, 'signal'),
      ],
      band: {
        mode: 'timestamp',
        state: 'active',
        label: 'seen',
        value: sourceTs ? formatMaybeTimestamp(sourceTs, 'time') : 'live',
        detail: 'source plane stays hot until a new raw fact arrives',
        stamp: sourceTs,
        meter: 100,
        tone: 'raw',
      },
    },
    {
      id: 'edge-handoff',
      title: 'Edge Parse + Handoff',
      purpose: 'The edge normalizes, checkpoints, and hands the fact to the raw stream.',
      systems: 'fortigate-ingest -> edge-forwarder -> netops.facts.raw.v1',
      status:
        rawTopic?.status === 'flowing' || ingest?.status === 'flowing'
          ? 'flowing'
          : 'steady',
      stageIds: ['ingest', 'forwarder', 'raw-topic'],
      facts: [
        `parsed ${stageMetricValue(ingest, 'parsed')}`,
        `freshness ${stageMetricValue(rawTopic, 'freshness')}`,
        `drop local deny ${stageMetricValue(forwarder, 'drop local deny')}`,
      ],
      band: {
        mode: 'timestamp',
        state: 'complete',
        label: 'handoff',
        value: handoffTs ? formatMaybeTimestamp(handoffTs, 'time') : 'ready',
        detail: `backlog ${stageMetricValue(ingest, 'backlog')} · raw topic ready`,
        stamp: handoffTs,
        meter: 100,
        tone: 'raw',
      },
    },
    {
      id: 'deterministic-alert',
      title: 'Deterministic Alert',
      purpose: 'The correlator decides whether the event crosses the rule threshold.',
      systems: 'core-correlator -> netops.alerts.v1',
      status:
        alertsTopic?.status === 'flowing' || correlator?.status === 'flowing'
          ? 'flowing'
          : 'steady',
      stageIds: ['correlator', 'alerts-topic'],
      facts: [
        `threshold ${stageMetricValue(correlator, 'deny threshold')}`,
        `latest ${stageMetricValue(alertsTopic, 'latest')}`,
      ],
      band: {
        mode: telemetryLookup.get('correlator')?.mode ?? 'duration',
        state: telemetryLookup.get('correlator')?.state ?? 'steady',
        label: 'elapsed',
        value: formatDurationMs(telemetryLookup.get('correlator')?.durationMs),
        detail:
          alertTs && sourceTs
            ? `${formatMaybeTimestamp(sourceTs, 'time')} -> ${formatMaybeTimestamp(alertTs, 'time')}`
            : 'source fact to alert emission',
        stamp: alertTs,
        meter: 100,
        tone: 'alert',
      },
    },
    {
      id: 'cluster-gate',
      title: 'Cluster Gate',
      purpose: 'Repeated same-key alerts are counted until they become cluster-legible.',
      systems: 'same-key aggregation window',
      status: clusterState,
      stageIds: ['cluster-window'],
      facts: [
        `${clusterProgress}/${safeClusterTarget} in ${safeClusterWindow}s`,
        linkedSuggestion.scope === 'cluster'
          ? 'cluster path already reached'
          : `${clusterRemaining} more needed for cluster trigger`,
      ],
      band: {
        mode: 'gate',
        state: clusterTelemetry?.state ?? (clusterProgress > 0 ? 'watch' : 'steady'),
        label: 'progress',
        value: `${clusterProgress}/${safeClusterTarget}`,
        detail:
          linkedSuggestion.scope === 'cluster'
            ? `cluster gate reached inside ${safeClusterWindow}s`
            : `${clusterRemaining} more matching alert(s) needed inside ${safeClusterWindow}s`,
        stamp: clusterTelemetry?.endedAt,
        meter:
          safeClusterTarget > 0
            ? Math.max(10, Math.min(100, (clusterProgress / safeClusterTarget) * 100))
            : 0,
        tone: 'alert',
      },
    },
    {
      id: 'suggestion-emission',
      title: 'AIOps Suggestion',
      purpose: 'Evidence is bundled into structured operator guidance.',
      systems: 'core-aiops-agent -> netops.aiops.suggestions.v1',
      status:
        suggestionsTopic?.status === 'flowing' || aiopsAgent?.status === 'flowing'
          ? 'flowing'
          : 'steady',
      stageIds: ['aiops-agent', 'suggestions-topic'],
      facts: [
        `${linkedSuggestion.scope}-scope via ${linkedSuggestion.context.provider}`,
        stageMetricValue(suggestionsTopic, 'current day'),
      ],
      band: {
        mode: telemetryLookup.get('aiops-agent')?.mode ?? 'duration',
        state: telemetryLookup.get('aiops-agent')?.state ?? 'steady',
        label: 'elapsed',
        value: formatDurationMs(telemetryLookup.get('aiops-agent')?.durationMs),
        detail:
          suggestionTs && alertTs
            ? `${formatMaybeTimestamp(alertTs, 'time')} -> ${formatMaybeTimestamp(suggestionTs, 'time')}`
            : 'alert evidence to suggestion emission',
        stamp: suggestionTs,
        meter: 100,
        tone: 'suggestion',
      },
    },
    {
      id: 'remediation-boundary',
      title: 'Remediation Boundary',
      purpose: 'Approval, execution, and feedback stay visible as the next control surface.',
      systems: 'approval -> execution -> feedback',
      status: remediation?.status ?? 'planned',
      stageIds: ['remediation'],
      facts: [
        stageMetricValue(remediation, 'status'),
        stageMetricValue(remediation, 'feedback'),
      ],
      band: {
        mode: 'reserved',
        state: 'planned',
        label: 'boundary',
        value: 'manual',
        detail: 'reserved control point · execution path not wired',
        meter: 10,
        tone: 'planned',
      },
    },
  ]
}

function buildLifecyclePhases(
  snapshot: RuntimeSnapshot,
  linkedSuggestion: SuggestionRecord,
): LifecyclePhase[] {
  return buildLifecycle(snapshot, linkedSuggestion)
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

function pulseKindForDelta(
  kind: RuntimeStreamDelta['kind'] | FeedEvent['kind'] | undefined,
): FeedEvent['kind'] {
  if (kind === 'raw' || kind === 'alert') {
    return kind
  }
  return 'suggestion'
}

function toneForDelta(
  kind: RuntimeStreamDelta['kind'] | FeedEvent['kind'] | undefined,
) {
  if (kind === 'system') {
    return 'live'
  }
  return pulseKindForDelta(kind)
}

function phaseIsPulsing(phase: LifecyclePhase, pulseIds: string[]) {
  return phase.stageIds.some((stageId) => pulseIds.includes(stageId))
}

function currentPhaseId(
  deltaKind: RuntimeStreamDelta['kind'] | undefined,
  eventKind: FeedEvent['kind'] | undefined,
) {
  if (deltaKind === 'cluster') {
    return 'cluster-gate'
  }

  if (eventKind === 'raw') {
    return 'edge-handoff'
  }

  if (eventKind === 'alert') {
    return 'deterministic-alert'
  }

  return 'suggestion-emission'
}

function suggestionForEvent(
  event: FeedEvent | undefined,
  suggestions: SuggestionRecord[],
  fallback: SuggestionRecord,
) {
  if (!event) {
    return fallback
  }

  if (event.relatedSuggestionId) {
    const direct = suggestions.find(
      (suggestion) => suggestion.id === event.relatedSuggestionId,
    )
    if (direct) {
      return direct
    }
  }

  if (event.relatedAlertId) {
    const fromAlert = suggestions.find(
      (suggestion) => suggestion.alertId === event.relatedAlertId,
    )
    if (fromAlert) {
      return fromAlert
    }
  }

  if (event.service || event.device) {
    const byContext = suggestions.find(
      (suggestion) =>
        suggestion.context.service === event.service &&
        suggestion.context.srcDeviceKey === event.device,
    )
    if (byContext) {
      return byContext
    }
  }

  return fallback
}

function eventPath(event: FeedEvent, linkedSuggestion: SuggestionRecord) {
  if (event.kind === 'raw') {
    return ['fortigate', 'ingest', 'forwarder', 'raw-topic']
  }

  if (event.kind === 'alert') {
    return ['raw-topic', 'correlator', 'alerts-topic', 'cluster-window']
  }

  return linkedSuggestion.scope === 'cluster'
    ? [
        'alerts-topic',
        'cluster-window',
        'aiops-agent',
        'suggestions-topic',
        'remediation',
      ]
    : ['alerts-topic', 'aiops-agent', 'suggestions-topic', 'remediation']
}

function eventSummary(event: FeedEvent, linkedSuggestion: SuggestionRecord) {
  if (event.kind === 'raw') {
    return {
      heading: 'raw ingest sample',
      detail: `service=${event.service ?? 'unknown'} device=${event.device ?? 'unknown'} entered the live edge path.`,
      annotations: [
        `path=${eventPath(event, linkedSuggestion).join(' -> ')}`,
        'status=awaiting deterministic correlation',
      ],
    }
  }

  if (event.kind === 'alert') {
    return {
      heading: 'deterministic alert fired',
      detail: event.detail,
      annotations: [
        `path=${eventPath(event, linkedSuggestion).join(' -> ')}`,
        `evidence=${event.evidence ?? 'none'}`,
      ],
    }
  }

  return {
    heading: `${event.scope ?? 'alert'}-scope suggestion emitted`,
    detail: event.detail,
    annotations: [
      `provider=${event.provider ?? linkedSuggestion.context.provider}`,
      `actions=${event.actionCount ?? linkedSuggestion.recommendedActions.length}`,
      `hypotheses=${event.hypothesisCount ?? linkedSuggestion.hypotheses.length}`,
    ],
  }
}

export function LiveFlowConsole({
  snapshot,
  latestDelta,
  selectedSuggestion,
  onSelectSuggestion,
}: LiveFlowConsoleProps) {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)

  const queueEvents = snapshot.feed.slice(0, 10)
  const compactMetrics = snapshot.overviewMetrics.filter((metric) =>
    ['raw-freshness', 'backlog', 'current-day-volume', 'closure'].includes(
      metric.id,
    ),
  )

  const activeEvent =
    queueEvents.find((event) => event.id === selectedEventId) ?? queueEvents[0]
  const linkedSuggestion = suggestionForEvent(
    activeEvent,
    snapshot.suggestions,
    selectedSuggestion,
  )
  const lifecycle = buildLifecyclePhases(snapshot, linkedSuggestion)
  const pulseKind = pulseKindForDelta(latestDelta?.kind ?? snapshot.feed[0]?.kind)
  const pulseTone = toneForDelta(latestDelta?.kind ?? snapshot.feed[0]?.kind)
  const pulseIds =
    latestDelta?.stageIds.length
      ? latestDelta.stageIds
      : pulseStageIds(pulseKind, linkedSuggestion.scope)
  const leadEventId =
    latestDelta?.id ??
    snapshot.feed[0]?.id ??
    snapshot.runtime.latestSuggestionTs ??
    snapshot.runtime.latestAlertTs
  const currentPhase = currentPhaseId(latestDelta?.kind, activeEvent?.kind ?? pulseKind)
  const activeStageIndex = lifecycle.findIndex((phase) => phase.id === currentPhase)
  const activeSummary = activeEvent
    ? eventSummary(activeEvent, linkedSuggestion)
    : null

  return (
    <section className="page console-page">
      <section className="section lifecycle-stage">
        <div className="section-header">
          <div>
            <h2 className="section-title">Live Event Lifecycle</h2>
            <span className="section-subtitle">
              Action view first: signal arrival, alerting, cluster gate,
              suggestion emission, remediation boundary.
            </span>
          </div>
          <div className="annotation-stack">
            <span className="section-kicker">meaningful action flow</span>
            <span className={`signal-chip tone-${pulseTone}`}>{pulseTone}</span>
          </div>
        </div>

        <div className="lifecycle-track">
          {lifecycle.map((phase, index) => {
            const isPulsing = phaseIsPulsing(phase, pulseIds)
            const pulseClass = isPulsing ? `pulse-${leadEventId.length % 2}` : ''
            const reached = index <= activeStageIndex ? 'is-reached' : ''
            const current = index === activeStageIndex ? 'is-current' : ''
            const nextPhase = lifecycle[index + 1]
            const nextPulse = nextPhase && phaseIsPulsing(nextPhase, pulseIds)

            return (
              <div
                key={`${phase.id}-${isPulsing ? leadEventId : 'steady'}`}
                className="phase-segment"
              >
                <article
                  className={`phase-card state-${phase.status} ${pulseClass} ${reached} ${current}`}
                >
                  <div className="phase-header">
                    <span className="phase-index">
                      {(index + 1).toString().padStart(2, '0')}
                    </span>
                    <div>
                      <strong>{phase.title}</strong>
                      <span>{phase.purpose}</span>
                    </div>
                  </div>

                  <div className="phase-system-line">{phase.systems}</div>

                  <ul className="phase-facts">
                    {phase.facts.map((fact) => (
                      <li key={`${phase.id}-${fact}`}>{fact}</li>
                    ))}
                  </ul>

                  <div
                    className={`phase-band mode-${phase.band.mode} state-${phase.band.state} tone-${phase.band.tone} ${pulseClass}`}
                    title={timestampTooltip(phase.band.stamp)}
                  >
                    <div className="phase-band-head">
                      <span>{phase.band.label}</span>
                      <strong>{phase.band.value}</strong>
                    </div>
                    <span className="phase-band-detail">{phase.band.detail}</span>
                    <div className="phase-band-track" aria-hidden="true">
                      <span style={{ width: `${phase.band.meter}%` }} />
                    </div>
                  </div>
                </article>

                {index < lifecycle.length - 1 ? (
                  <div
                    className={`phase-link ${nextPulse ? `pulse-${leadEventId.length % 2}` : ''} ${index < activeStageIndex ? 'is-reached' : ''}`}
                    aria-hidden="true"
                  >
                    <span className="phase-link-line" />
                    <span className="phase-link-runner" />
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
                Which repeated alert paths are closest to becoming cluster-scope suggestions.
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
                <p>
                  {item.progress >= item.target
                    ? `Reached cluster threshold inside the last ${item.windowSec}s.`
                    : `${item.progress} matching alert(s) in the last ${item.windowSec}s; ${item.target - item.progress} more needed.`}
                </p>
              </li>
            ))}
          </ul>
        </section>

        <section key={linkedSuggestion.id} className="section story-panel">
          <div className="section-header">
            <div>
              <h2 className="section-title">Selected Runtime Story</h2>
              <span className="section-subtitle">
                Timeline-driven explanation for the active suggestion slice.
              </span>
            </div>
            <span className="section-kicker">{linkedSuggestion.scope}-scope</span>
          </div>

          <div className="story-summary">
            <div>
              <p className="story-marker">active slice</p>
              <h3>{linkedSuggestion.summary}</h3>
            </div>
            <div className="story-badges">
              <span className="signal-chip tone-suggestion">
                {linkedSuggestion.context.service}
              </span>
              <span className="signal-chip tone-neutral">
                {linkedSuggestion.context.srcDeviceKey}
              </span>
              <span className="signal-chip tone-alert">
                {linkedSuggestion.priority}
              </span>
            </div>
          </div>

          <ol className="timeline-list">
            {(linkedSuggestion.timeline ?? snapshot.timeline).map((step, index) => (
              <li
                key={`${linkedSuggestion.id}-${step.id}`}
                className={`timeline-item ${index <= activeStageIndex ? 'is-active' : ''}`}
                style={{ animationDelay: `${index * 90}ms` }}
              >
                <span className="timeline-stamp" title={timestampTooltip(step.stamp)}>
                  {formatMaybeTimestamp(step.stamp)}
                </span>
                <div className="timeline-body">
                  <h3>{step.title}</h3>
                  <p>{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="section event-stack-panel">
          <div className="section-header">
            <div>
              <h2 className="section-title">Event Queue</h2>
              <span className="section-subtitle">
                Static by default. New events push to the top and call attention
                to themselves once.
              </span>
            </div>
            <span className="section-kicker">newest first / click to inspect</span>
          </div>

          <div className="event-stack">
            {queueEvents.map((event, index) => {
              const isLead = latestDelta?.feedIds.includes(event.id) ?? index === 0
              const isActive = activeEvent?.id === event.id

              return (
                <button
                  key={event.id}
                  type="button"
                  className={`event-row kind-${event.kind} ${isLead ? 'is-lead' : ''} ${isActive ? 'is-active' : ''}`}
                  onClick={() => {
                    setSelectedEventId(event.id)
                    const suggestion = suggestionForEvent(
                      event,
                      snapshot.suggestions,
                      selectedSuggestion,
                    )
                    if (suggestion.id !== selectedSuggestion.id) {
                      onSelectSuggestion(suggestion.id)
                    }
                  }}
                >
                  <div className="event-row-head">
                    <span className={`signal-chip tone-${event.kind}`}>
                      {event.scope ? `${event.kind}/${event.scope}` : event.kind}
                    </span>
                    <span
                      className="event-stamp"
                      title={timestampTooltip(event.stamp)}
                    >
                      {formatMaybeTimestamp(event.stamp, 'time')}
                    </span>
                  </div>
                  <strong>{event.title}</strong>
                  <p>{event.detail}</p>
                  <div className="event-row-meta">
                    <span>{event.service ?? 'n/a'}</span>
                    <span>{event.device ?? event.provider ?? 'runtime'}</span>
                  </div>
                </button>
              )
            })}
          </div>
        </section>

        <section className="section event-focus-panel">
          <div className="section-header">
            <div>
              <h2 className="section-title">Event Focus</h2>
              <span className="section-subtitle">
                Drill into the active event instead of watching a decorative
                ticker.
              </span>
            </div>
            <span className="section-kicker">
              {activeEvent?.kind ?? 'waiting'}
            </span>
          </div>

          {activeEvent && activeSummary ? (
            <div key={activeEvent.id} className="event-focus-body">
              <div className="event-focus-summary">
                <div className="event-focus-topline">
                  <span className={`signal-chip tone-${activeEvent.kind}`}>
                    {activeEvent.scope
                      ? `${activeEvent.kind}/${activeEvent.scope}`
                      : activeEvent.kind}
                  </span>
                  <span
                    className="event-focus-stamp"
                    title={timestampTooltip(activeEvent.stamp)}
                  >
                    {formatMaybeTimestamp(activeEvent.stamp, 'time')}
                  </span>
                </div>
                <h3>{activeEvent.title}</h3>
                <p>{activeSummary.detail}</p>
              </div>

              <div className="event-focus-grid">
                <article className="focus-card">
                  <strong>{activeSummary.heading}</strong>
                  <ul className="focus-list">
                    {activeSummary.annotations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </article>

                <article className="focus-card">
                  <strong>linked analysis</strong>
                  <ul className="focus-list">
                    <li>service={linkedSuggestion.context.service}</li>
                    <li>device={linkedSuggestion.context.srcDeviceKey}</li>
                    <li>confidence={linkedSuggestion.confidenceLabel}</li>
                    <li>actions={linkedSuggestion.recommendedActions.length}</li>
                  </ul>
                </article>
              </div>

              <div className="event-path">
                {eventPath(activeEvent, linkedSuggestion).map((step, index) => (
                  <div key={`${activeEvent.id}-${step}`} className="event-path-step">
                    <span>{step}</span>
                    {index < eventPath(activeEvent, linkedSuggestion).length - 1 ? (
                      <i aria-hidden="true" />
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </section>
  )
}
