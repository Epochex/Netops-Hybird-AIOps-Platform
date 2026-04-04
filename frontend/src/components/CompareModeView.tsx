import {
  startTransition,
  useDeferredValue,
  useMemo,
  useState,
} from 'react'
import './CompareModeView.css'
import {
  buildDefaultFilters,
  buildFilterOptions,
  compareWorkbenchDatasets,
  getCompareDataset,
  sortCompareSamples,
  summarizeCompareKpis,
  filterCompareSamples,
} from '../data/compareWorkbench'
import { CompareAnalysisTabs } from './compare/CompareAnalysisTabs'
import { CompareDetailPanel } from './compare/CompareDetailPanel'
import { CompareKpiStrip } from './compare/CompareKpiStrip'
import { CompareSampleTable } from './compare/CompareSampleTable'
import { CompareWorkbenchHeader } from './compare/CompareWorkbenchHeader'
import { exportCompareSamples } from '../utils/compareExport'
import type { CompareDatasetFilters, CompareTabId } from '../types'

export function CompareModeView() {
  const [activeDatasetId, setActiveDatasetId] = useState(compareWorkbenchDatasets[0].id)
  const dataset = useMemo(() => getCompareDataset(activeDatasetId), [activeDatasetId])
  const [filters, setFilters] = useState<CompareDatasetFilters>(() => buildDefaultFilters(dataset))
  const [activeTab, setActiveTab] = useState<CompareTabId>('explanation')
  const [sortKey, setSortKey] = useState('bundleId')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [selectedSampleId, setSelectedSampleId] = useState(dataset.samples[0]?.id ?? '')

  const deferredQuery = useDeferredValue(filters.query)
  const effectiveFilters = useMemo(
    () => ({
      ...filters,
      query: deferredQuery,
    }),
    [deferredQuery, filters],
  )

  const filterOptions = useMemo(() => buildFilterOptions(dataset), [dataset])
  const filteredSamples = useMemo(
    () => filterCompareSamples(dataset, effectiveFilters),
    [dataset, effectiveFilters],
  )
  const sortedSamples = useMemo(
    () => sortCompareSamples(filteredSamples, sortKey, sortDirection),
    [filteredSamples, sortDirection, sortKey],
  )
  const kpiCards = useMemo(() => summarizeCompareKpis(sortedSamples), [sortedSamples])
  const activeSelectedSampleId = sortedSamples.some((sample) => sample.id === selectedSampleId)
    ? selectedSampleId
    : sortedSamples[0]?.id ?? ''
  const selectedSample = sortedSamples.find((sample) => sample.id === activeSelectedSampleId)

  function handleDatasetChange(datasetId: string) {
    startTransition(() => {
      const nextDataset = getCompareDataset(datasetId)
      setActiveDatasetId(datasetId)
      setFilters(buildDefaultFilters(nextDataset))
      setSelectedSampleId(nextDataset.samples[0]?.id ?? '')
      setActiveTab('explanation')
      setSortKey('bundleId')
      setSortDirection('asc')
    })
  }

  function handleFilterChange(patch: Partial<CompareDatasetFilters>) {
    startTransition(() => {
      setFilters((current) => ({
        ...current,
        ...patch,
      }))
    })
  }

  function handleSortChange(nextSortKey: string) {
    startTransition(() => {
      if (nextSortKey === sortKey) {
        setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
        return
      }
      setSortKey(nextSortKey)
      setSortDirection('asc')
    })
  }

  return (
    <section className="page compare-workbench">
      <CompareWorkbenchHeader
        datasets={compareWorkbenchDatasets}
        activeDatasetId={activeDatasetId}
        filters={filters}
        replayOptions={filterOptions.replays}
        providerOptions={filterOptions.providers}
        severityOptions={filterOptions.severities}
        ruleOptions={filterOptions.rules}
        serviceOptions={filterOptions.services}
        statusOptions={filterOptions.statuses}
        onDatasetChange={handleDatasetChange}
        onFilterChange={handleFilterChange}
        onExportJson={() => exportCompareSamples(sortedSamples, dataset.label, 'json')}
        onExportCsv={() => exportCompareSamples(sortedSamples, dataset.label, 'csv')}
      />

      <CompareKpiStrip cards={kpiCards} />

      <CompareAnalysisTabs
        activeTab={activeTab}
        samples={sortedSamples}
        onTabChange={(tabId) => startTransition(() => setActiveTab(tabId))}
      />

      <div className="compare-review-grid">
        <CompareSampleTable
          samples={sortedSamples}
          selectedSampleId={activeSelectedSampleId}
          sortKey={sortKey}
          sortDirection={sortDirection}
          onRowSelect={(sampleId) => setSelectedSampleId(sampleId)}
          onSortChange={handleSortChange}
        />
        <CompareDetailPanel sample={selectedSample} />
      </div>
    </section>
  )
}
