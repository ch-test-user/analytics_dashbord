# Costco Dashboard System Flow

This dashboard is a local Streamlit application that reads one configured Google Sheet, parses each product tab, normalizes the data, calculates metrics, and renders the dashboard.

## State Machine View

```mermaid
stateDiagram-v2
    [*] --> AppStart

    AppStart --> LoadConfig: read app.config.json
    LoadConfig --> ResolveGoogleAuth: read service account JSON path
    ResolveGoogleAuth --> ValidateConfig: require sheet URL and credentials file
    ValidateConfig --> TrySheetsAPI: connect to Google Sheets API

    TrySheetsAPI --> SheetsAPIWorkbook: native Google Sheet
    TrySheetsAPI --> DriveDownloadWorkbook: Office Excel file fallback
    SheetsAPIWorkbook --> ReadAllTabs
    DriveDownloadWorkbook --> ReadAllTabs

    ReadAllTabs --> SkipSummaryTabs: exclude summary / unsupported sheets
    SkipSummaryTabs --> ParseProductTabs: each usable tab is one product
    ParseProductTabs --> DetectDemoWeeks: read blue highlighted source rows
    DetectDemoWeeks --> NormalizeColumns

    NormalizeColumns --> ParseWeekEnding: parse week ending / week start dates
    ParseWeekEnding --> BuildCanonicalData: product, region, sales, units, inventory
    BuildCanonicalData --> DataQualityWarnings: skipped tabs / parse issues
    DataQualityWarnings --> CacheDataset: Streamlit cache

    CacheDataset --> SidebarFilters
    SidebarFilters --> FilteredDataset: date, product, region, tab filters

    FilteredDataset --> MetricLayer
    MetricLayer --> OverviewMetrics: revenue, units, active items, velocity, coverage
    MetricLayer --> TimeSeriesMetrics: sales, units, velocity, warehouses, coverage
    MetricLayer --> ProductMetrics: top products, product mix, demo week velocity
    MetricLayer --> RegionMetrics: top regions, region mix, product velocity by region
    MetricLayer --> InventoryMetrics: inventory and supply health
    MetricLayer --> CustomAnalysis: user-selected dimensions and metrics

    OverviewMetrics --> RenderDashboard
    TimeSeriesMetrics --> RenderDashboard
    ProductMetrics --> RenderDashboard
    RegionMetrics --> RenderDashboard
    InventoryMetrics --> RenderDashboard
    CustomAnalysis --> RenderDashboard

    RenderDashboard --> UserInteraction: hover, filter, search, export
    UserInteraction --> SidebarFilters: filters recalculate charts
    UserInteraction --> RefreshCache: refresh data cache button
    RefreshCache --> TrySheetsAPI

    DataQualityWarnings --> ShowWarnings: show warning with sheet name
    ShowWarnings --> RenderDashboard

    RenderDashboard --> [*]
```

## Layered Flow

```mermaid
flowchart TD
    A[Configured Google Sheet] --> B[Google auth using service account]
    B --> C{Workbook type}
    C -->|Native Google Sheet| D[Sheets API reads tabs]
    C -->|Office Excel file| E[Drive API downloads XLSX]
    E --> F[openpyxl reads values and cell colors]
    D --> G[Product tab parser]
    F --> G

    G --> H[Normalize data in app_core/data.py]
    H --> I[Canonical dataframe]
    I --> J[Metric definitions and calculations in app_core/metrics.py]
    J --> K[Streamlit UI in streamlit_app.py]
    K --> L[Dashboard charts, KPI cards, filters, exports]

    H --> M[Warnings: skipped sheets, missing fields, date parse issues]
    M --> K
```

## Main Responsibilities

- `app.config.json`: stores the Google Sheet URL and service account path.
- `app_core/google_sheets.py`: connects to Google, downloads/reads all tabs, and detects demo week blue highlighting.
- `app_core/data.py`: converts raw Google workbook tabs into a single normalized dataframe.
- `app_core/metrics.py`: source of truth for metric definitions and reusable metric calculations.
- `streamlit_app.py`: renders filters, KPI cards, charts, warnings, tables, and exports.
- `setup_and_run.sh`: creates/uses the Python environment, installs requirements, and starts Streamlit.

## Important Behavior

- Google Sheets is the only supported dashboard data source.
- Filters apply globally to the dashboard.
- Google Sheets are read-only from the dashboard; the app does not write back to the source sheet.
- Demo weeks are detected from existing blue-highlighted rows in the workbook and highlighted inside dashboard charts.
- Skipped sheets or parsing issues appear as dashboard warnings with the relevant sheet name.
- Adding new charts should generally mean adding metric logic in `app_core/metrics.py`, then rendering it in `streamlit_app.py`.
