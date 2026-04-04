import type { CompareDatasetFilters, CompareWorkbenchDataset } from '../../types'

interface CompareWorkbenchHeaderProps {
  datasets: readonly CompareWorkbenchDataset[]
  activeDatasetId: string
  filters: CompareDatasetFilters
  replayOptions: Array<[string, string]>
  providerOptions: Array<[string, string]>
  severityOptions: Array<[string, string]>
  ruleOptions: Array<[string, string]>
  serviceOptions: Array<[string, string]>
  statusOptions: Array<[string, string]>
  onDatasetChange: (datasetId: string) => void
  onFilterChange: (patch: Partial<CompareDatasetFilters>) => void
  onExportJson: () => void
  onExportCsv: () => void
}

function SelectField(props: {
  label: string
  value: string
  options: Array<[string, string]>
  onChange: (value: string) => void
}) {
  return (
    <label className="compare-control compare-control-select">
      <span className="compare-control-label">{props.label}</span>
      <select
        className="compare-select"
        value={props.value}
        onChange={(event) => props.onChange(event.target.value)}
      >
        <option value="all">All</option>
        {props.options.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function CompareWorkbenchHeader({
  datasets,
  activeDatasetId,
  filters,
  replayOptions,
  providerOptions,
  severityOptions,
  ruleOptions,
  serviceOptions,
  statusOptions,
  onDatasetChange,
  onFilterChange,
  onExportJson,
  onExportCsv,
}: CompareWorkbenchHeaderProps) {
  const activeDataset =
    datasets.find((dataset) => dataset.id === activeDatasetId) ?? datasets[0]

  return (
    <section className="section compare-shell-section">
      <div className="compare-workbench-header">
        <div className="compare-header-title-block">
          <p className="compare-eyebrow">Evaluation Workbench</p>
          <h2 className="compare-workbench-title">
            Baseline Template vs Future LLM Evaluation
          </h2>
          <p className="compare-workbench-copy">{activeDataset.description}</p>
        </div>

        <div className="compare-header-actions">
          <button className="compare-action" type="button" onClick={onExportJson}>
            Export JSON
          </button>
          <button className="compare-action compare-action-accent" type="button" onClick={onExportCsv}>
            Export CSV
          </button>
        </div>
      </div>

      <div className="compare-controls-grid">
        <label className="compare-control compare-control-select">
          <span className="compare-control-label">Dataset</span>
          <select
            className="compare-select"
            value={activeDatasetId}
            onChange={(event) => onDatasetChange(event.target.value)}
          >
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.label}
              </option>
            ))}
          </select>
        </label>

        <SelectField
          label="Replay"
          value={filters.replayId}
          options={replayOptions}
          onChange={(value) => onFilterChange({ replayId: value })}
        />

        <SelectField
          label="Provider"
          value={filters.providerName}
          options={providerOptions}
          onChange={(value) => onFilterChange({ providerName: value })}
        />

        <SelectField
          label="Severity"
          value={filters.severity}
          options={severityOptions}
          onChange={(value) => onFilterChange({ severity: value })}
        />

        <SelectField
          label="Rule"
          value={filters.ruleId}
          options={ruleOptions}
          onChange={(value) => onFilterChange({ ruleId: value })}
        />

        <SelectField
          label="Service"
          value={filters.service}
          options={serviceOptions}
          onChange={(value) => onFilterChange({ service: value })}
        />

        <SelectField
          label="Row State"
          value={filters.status}
          options={statusOptions.filter(([value]) => value !== 'all')}
          onChange={(value) => onFilterChange({ status: value })}
        />

        <label className="compare-control compare-control-search">
          <span className="compare-control-label">Search</span>
          <input
            className="compare-search"
            type="search"
            value={filters.query}
            onChange={(event) => onFilterChange({ query: event.target.value })}
            placeholder="bundle / alert / rule / device"
          />
        </label>
      </div>
    </section>
  )
}
