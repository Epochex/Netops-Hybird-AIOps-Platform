import { startTransition, useEffect, useState } from 'react'
import { runtimeSnapshot as fallbackSnapshot } from '../data/runtimeModel'
import type {
  RuntimeSnapshot,
  RuntimeStreamDelta,
  RuntimeStreamEnvelope,
} from '../types'

export type RuntimeConnectionState =
  | 'connecting'
  | 'live'
  | 'degraded'
  | 'fallback'

const SNAPSHOT_ENDPOINT = '/api/runtime/snapshot'
const STREAM_ENDPOINT = '/api/runtime/stream'

export function useRuntimeSnapshot() {
  const [snapshot, setSnapshot] = useState<RuntimeSnapshot>(fallbackSnapshot)
  const [latestDelta, setLatestDelta] = useState<RuntimeStreamDelta | null>(null)
  const [connectionState, setConnectionState] =
    useState<RuntimeConnectionState>('connecting')

  useEffect(() => {
    const controller = new AbortController()

    async function hydrate() {
      try {
        const response = await fetch(SNAPSHOT_ENDPOINT, {
          signal: controller.signal,
          headers: { Accept: 'application/json' },
        })
        if (!response.ok) {
          throw new Error(`snapshot request failed: ${response.status}`)
        }
        const nextSnapshot = (await response.json()) as RuntimeSnapshot
        startTransition(() => setSnapshot(nextSnapshot))
        setConnectionState('live')
      } catch {
        if (!controller.signal.aborted) {
          setConnectionState('fallback')
        }
      }
    }

    hydrate()
    return () => controller.abort()
  }, [])

  useEffect(() => {
    let isMounted = true
    let retryTimer: number | undefined
    let eventSource: EventSource | undefined

    const connect = () => {
      if (!isMounted) {
        return
      }
      setConnectionState((previousState) =>
        previousState === 'live' ? 'live' : 'connecting',
      )
      eventSource = new EventSource(STREAM_ENDPOINT)

      const handleEnvelope = (
        event: MessageEvent<string>,
        expectedType: RuntimeStreamEnvelope['type'],
      ) => {
        try {
          const envelope = JSON.parse(event.data) as RuntimeStreamEnvelope
          if (envelope.type !== expectedType) {
            return
          }
          if (!isMounted) {
            return
          }
          if (envelope.type === 'heartbeat') {
            setConnectionState('live')
            return
          }
          startTransition(() => setSnapshot(envelope.snapshot))
          if (envelope.type === 'delta') {
            setLatestDelta(envelope.delta)
          } else {
            setLatestDelta(null)
          }
          setConnectionState('live')
        } catch {
          if (isMounted) {
            setConnectionState('degraded')
          }
        }
      }

      eventSource.addEventListener('snapshot', (event) =>
        handleEnvelope(event as MessageEvent<string>, 'snapshot'),
      )
      eventSource.addEventListener('delta', (event) =>
        handleEnvelope(event as MessageEvent<string>, 'delta'),
      )
      eventSource.addEventListener('heartbeat', (event) =>
        handleEnvelope(event as MessageEvent<string>, 'heartbeat'),
      )

      eventSource.onerror = () => {
        eventSource?.close()
        if (!isMounted) {
          return
        }
        setConnectionState((previousState) =>
          previousState === 'live' ? 'degraded' : 'fallback',
        )
        retryTimer = window.setTimeout(connect, 5000)
      }
    }

    connect()

    return () => {
      isMounted = false
      eventSource?.close()
      if (retryTimer) {
        window.clearTimeout(retryTimer)
      }
    }
  }, [])

  return { snapshot, latestDelta, connectionState }
}
