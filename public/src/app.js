const metricLabels = {
  dollarSales: "Dollar Sales",
  dollarSalesYearAgo: "Dollar Sales YA",
  unitSales: "Unit Sales",
  unitSalesYearAgo: "Unit Sales YA",
  warehousesSelling: "Warehouses Selling",
  warehousesSellingYearAgo: "Warehouses Selling YA",
  numberOfWarehouses: "Warehouses",
  numberOfWarehousesYearAgo: "Warehouses YA",
  inventoryOnHand: "Inventory",
  coverageRate: "Coverage Rate"
};

const dimensionLabels = {
  item: "Costco Item",
  itemCode: "Item Code",
  commonName: "Item",
  venue: "Venue",
  time: "Time",
  dateLabel: "Date Label",
  weekStart: "Week",
  year: "Year"
};

const state = {
  data: null,
  config: null,
  charts: [],
  search: "",
  metric: "unitSales",
  selectedVenues: new Set(),
  selectedItems: new Set(),
  startDate: "",
  endDate: ""
};

const els = {
  sourceMeta: document.querySelector("#sourceMeta"),
  dashboardTitle: document.querySelector("#dashboardTitle"),
  activeSummary: document.querySelector("#activeSummary"),
  searchInput: document.querySelector("#searchInput"),
  metricSelect: document.querySelector("#metricSelect"),
  startDate: document.querySelector("#startDate"),
  endDate: document.querySelector("#endDate"),
  venueFacet: document.querySelector("#venueFacet"),
  itemFacet: document.querySelector("#itemFacet"),
  clearVenues: document.querySelector("#clearVenues"),
  clearItems: document.querySelector("#clearItems"),
  refreshButton: document.querySelector("#refreshButton"),
  addChartButton: document.querySelector("#addChartButton"),
  kpiRow: document.querySelector("#kpiRow"),
  chartGrid: document.querySelector("#chartGrid"),
  tableSummary: document.querySelector("#tableSummary"),
  tableHead: document.querySelector("#tableHead"),
  tableBody: document.querySelector("#tableBody"),
  downloadButton: document.querySelector("#downloadButton"),
  chartDialog: document.querySelector("#chartDialog"),
  chartTitle: document.querySelector("#chartTitle"),
  chartType: document.querySelector("#chartType"),
  chartDimension: document.querySelector("#chartDimension"),
  chartMetric: document.querySelector("#chartMetric"),
  chartAggregation: document.querySelector("#chartAggregation"),
  saveChartButton: document.querySelector("#saveChartButton")
};

function formatNumber(value, metric = "") {
  if (value == null || Number.isNaN(value)) return "-";
  if (metric === "dollarSales" || metric === "dollarSalesYearAgo") {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
  }
  if (metric === "coverageRate") {
    return new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 }).format(value);
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function sum(rows, field) {
  return rows.reduce((total, row) => total + (Number(row[field]) || 0), 0);
}

function average(rows, field) {
  const values = rows.map(row => Number(row[field])).filter(Number.isFinite);
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

function normalizeRecords(records) {
  return records.map(row => {
    const selling = Number(row.warehousesSelling);
    const warehouses = Number(row.numberOfWarehouses);
    return {
      ...row,
      coverageRate: Number.isFinite(selling) && Number.isFinite(warehouses) && warehouses > 0 ? selling / warehouses : null
    };
  });
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load ${path}`);
  return response.json();
}

async function init() {
  const [config, data] = await Promise.all([
    loadJson("/public/dashboard.config.json"),
    loadJson("/api/data")
  ]);
  state.config = config;
  state.data = { ...data, records: normalizeRecords(data.records) };
  state.metric = config.defaultMetric || "unitSales";
  state.charts = loadCharts(config.charts);
  setupControls();
  render();
}

function loadCharts(defaultCharts) {
  const saved = localStorage.getItem("costcoDashboardCharts");
  if (!saved) return defaultCharts;
  try {
    const parsed = JSON.parse(saved);
    return Array.isArray(parsed) && parsed.length ? parsed : defaultCharts;
  } catch {
    return defaultCharts;
  }
}

function saveCharts() {
  localStorage.setItem("costcoDashboardCharts", JSON.stringify(state.charts));
}

function setupControls() {
  const metadata = state.data.metadata;
  els.dashboardTitle.textContent = state.config.title || "Dashboard";
  els.sourceMeta.textContent = `${metadata.rowCount.toLocaleString()} rows from ${metadata.sourceSheet}`;
  els.startDate.value = metadata.weekRange.min || "";
  els.endDate.value = metadata.weekRange.max || "";
  state.startDate = els.startDate.value;
  state.endDate = els.endDate.value;

  const metrics = [...metadata.fields.metrics, "coverageRate"];
  fillSelect(els.metricSelect, metrics, metricLabels);
  fillSelect(els.chartMetric, metrics, metricLabels);
  fillSelect(els.chartDimension, metadata.fields.dimensions, dimensionLabels);
  els.metricSelect.value = state.metric;

  els.searchInput.addEventListener("input", () => {
    state.search = els.searchInput.value.trim().toLowerCase();
    render();
  });
  els.metricSelect.addEventListener("change", () => {
    state.metric = els.metricSelect.value;
    render();
  });
  els.startDate.addEventListener("change", () => {
    state.startDate = els.startDate.value;
    render();
  });
  els.endDate.addEventListener("change", () => {
    state.endDate = els.endDate.value;
    render();
  });
  els.clearVenues.addEventListener("click", () => {
    state.selectedVenues.clear();
    render();
  });
  els.clearItems.addEventListener("click", () => {
    state.selectedItems.clear();
    render();
  });
  els.refreshButton.addEventListener("click", refreshData);
  els.addChartButton.addEventListener("click", () => els.chartDialog.showModal());
  els.saveChartButton.addEventListener("click", event => {
    event.preventDefault();
    addChart();
  });
  els.downloadButton.addEventListener("click", downloadCsv);
}

function fillSelect(select, values, labels) {
  select.innerHTML = "";
  values.forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labels[value] || value;
    select.append(option);
  });
}

function filteredRows() {
  return state.data.records.filter(row => {
    if (state.startDate && row.weekStart < state.startDate) return false;
    if (state.endDate && row.weekStart > state.endDate) return false;
    if (state.selectedVenues.size && !state.selectedVenues.has(row.venue)) return false;
    if (state.selectedItems.size && !state.selectedItems.has(row.commonName)) return false;
    if (state.search) {
      const haystack = [row.commonName, row.item, row.itemCode, row.venue, row.dateLabel].join(" ").toLowerCase();
      if (!haystack.includes(state.search)) return false;
    }
    return true;
  });
}

function render() {
  const rows = filteredRows();
  renderFacets(rows);
  renderKpis(rows);
  renderCharts(rows);
  renderTable(rows);
  els.activeSummary.textContent = `${rows.length.toLocaleString()} filtered rows, ${state.selectedItems.size || "all"} items, ${state.selectedVenues.size || "all"} venues`;
}

function renderFacets(rows) {
  renderFacet(els.venueFacet, rows, "venue", state.selectedVenues);
  renderFacet(els.itemFacet, rows, "commonName", state.selectedItems, 60);
}

function renderFacet(container, rows, field, selected, limit = 40) {
  const counts = new Map();
  state.data.records.forEach(row => {
    const value = row[field] || "(blank)";
    const basePass = rows.includes(row) || selected.has(value);
    if (basePass) counts.set(value, (counts.get(value) || 0) + 1);
  });
  const options = [...counts.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]))).slice(0, limit);
  container.innerHTML = "";
  options.forEach(([value, count]) => {
    const label = document.createElement("label");
    label.className = "facet-option";
    label.innerHTML = `<input type="checkbox"><span title="${escapeHtml(value)}">${escapeHtml(value)}</span><small>${count.toLocaleString()}</small>`;
    const input = label.querySelector("input");
    input.checked = selected.has(value);
    input.addEventListener("change", () => {
      input.checked ? selected.add(value) : selected.delete(value);
      render();
    });
    container.append(label);
  });
}

function renderKpis(rows) {
  const kpis = [
    ["Dollar Sales", sum(rows, "dollarSales"), "dollarSales"],
    ["Unit Sales", sum(rows, "unitSales"), "unitSales"],
    ["Inventory", sum(rows, "inventoryOnHand"), "inventoryOnHand"],
    ["Avg Coverage", average(rows, "coverageRate"), "coverageRate"],
    ["Active Items", new Set(rows.map(row => row.commonName).filter(Boolean)).size, ""]
  ];
  els.kpiRow.innerHTML = kpis.map(([label, value, metric]) => `
    <article class="kpi">
      <span>${label}</span>
      <strong>${formatNumber(value, metric)}</strong>
    </article>
  `).join("");
}

function aggregate(rows, chart) {
  const groups = new Map();
  rows.forEach(row => {
    const key = row[chart.dimension] || "(blank)";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  });
  let points = [...groups.entries()].map(([key, values]) => {
    let value;
    if (chart.aggregation === "avg") value = average(values, chart.metric);
    else if (chart.aggregation === "count") value = values.length;
    else value = sum(values, chart.metric);
    return { key, value: value || 0 };
  });
  if (chart.dimension === "weekStart" || chart.dimension === "dateLabel" || chart.dimension === "year") {
    points.sort((a, b) => String(a.key).localeCompare(String(b.key)));
  } else {
    points.sort((a, b) => b.value - a.value);
  }
  if (chart.limit) points = points.slice(0, chart.limit);
  return points;
}

function renderCharts(rows) {
  els.chartGrid.innerHTML = "";
  state.charts.forEach(chart => {
    const card = document.createElement("article");
    card.className = "chart-card";
    const subtitle = `${dimensionLabels[chart.dimension] || chart.dimension} by ${metricLabels[chart.metric] || chart.metric} (${chart.aggregation})`;
    card.innerHTML = `
      <div class="chart-toolbar">
        <div><h3>${escapeHtml(chart.title)}</h3><p>${escapeHtml(subtitle)}</p></div>
        <button class="icon-button" title="Remove chart" aria-label="Remove chart">x</button>
      </div>
      <svg class="chart" role="img" aria-label="${escapeHtml(chart.title)}"></svg>
    `;
    card.querySelector("button").addEventListener("click", () => {
      state.charts = state.charts.filter(item => item.id !== chart.id);
      saveCharts();
      render();
    });
    els.chartGrid.append(card);
    drawChart(card.querySelector("svg"), aggregate(rows, chart), chart);
  });
}

function drawChart(svg, data, chart) {
  const width = svg.clientWidth || 600;
  const height = svg.clientHeight || 292;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = "";
  if (!data.length) {
    svg.innerHTML = `<text class="empty" x="${width / 2}" y="${height / 2}" text-anchor="middle">No data for selected filters</text>`;
    return;
  }
  chart.type === "line" ? drawLine(svg, data, chart, width, height) : drawBar(svg, data, chart, width, height);
}

function drawLine(svg, data, chart, width, height) {
  const margin = { top: 12, right: 18, bottom: 38, left: 58 };
  const max = Math.max(...data.map(d => d.value), 1);
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const x = i => margin.left + (data.length === 1 ? plotW / 2 : i * plotW / (data.length - 1));
  const y = value => margin.top + plotH - (value / max) * plotH;
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.value).toFixed(1)}`).join(" ");
  svg.insertAdjacentHTML("beforeend", `
    <line class="axis" x1="${margin.left}" y1="${margin.top + plotH}" x2="${width - margin.right}" y2="${margin.top + plotH}"></line>
    <line class="axis" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotH}"></line>
    <text class="axis-label" x="8" y="${margin.top + 4}">${formatNumber(max, chart.metric)}</text>
    <path class="line-path" d="${path}"></path>
  `);
  data.forEach((d, i) => {
    if (i % Math.ceil(data.length / 8) === 0 || i === data.length - 1) {
      svg.insertAdjacentHTML("beforeend", `<text class="axis-label" x="${x(i)}" y="${height - 12}" text-anchor="middle">${escapeHtml(shortLabel(d.key))}</text>`);
    }
    svg.insertAdjacentHTML("beforeend", `<circle class="point" cx="${x(i)}" cy="${y(d.value)}" r="3"><title>${escapeHtml(d.key)}: ${formatNumber(d.value, chart.metric)}</title></circle>`);
  });
}

function drawBar(svg, data, chart, width, height) {
  const margin = { top: 8, right: 18, bottom: 20, left: 150 };
  const max = Math.max(...data.map(d => d.value), 1);
  const rowH = Math.max(18, Math.min(30, (height - margin.top - margin.bottom) / data.length));
  const plotW = width - margin.left - margin.right;
  data.forEach((d, i) => {
    const y = margin.top + i * rowH;
    const barW = (d.value / max) * plotW;
    svg.insertAdjacentHTML("beforeend", `
      <text class="bar-label" x="0" y="${y + rowH * 0.65}">${escapeHtml(shortLabel(d.key, 22))}</text>
      <rect class="bar" x="${margin.left}" y="${y + 3}" width="${barW}" height="${Math.max(4, rowH - 7)}" rx="3"></rect>
      <text class="axis-label" x="${Math.min(width - 74, margin.left + barW + 6)}" y="${y + rowH * 0.65}">${formatNumber(d.value, chart.metric)}</text>
    `);
  });
}

function renderTable(rows) {
  const columns = ["weekStart", "venue", "commonName", "unitSales", "dollarSales", "inventoryOnHand", "warehousesSelling", "numberOfWarehouses"];
  els.tableSummary.textContent = `Showing ${Math.min(rows.length, 250).toLocaleString()} of ${rows.length.toLocaleString()} rows`;
  els.tableHead.innerHTML = `<tr>${columns.map(col => `<th>${dimensionLabels[col] || metricLabels[col] || col}</th>`).join("")}</tr>`;
  els.tableBody.innerHTML = rows.slice(0, 250).map(row => `<tr>${
    columns.map(col => `<td>${escapeHtml(formatCell(row[col], col))}</td>`).join("")
  }</tr>`).join("");
}

function formatCell(value, col) {
  if (metricLabels[col]) return formatNumber(value, col);
  return value ?? "";
}

function addChart() {
  state.charts.push({
    id: `chart-${Date.now()}`,
    title: els.chartTitle.value.trim() || "New Chart",
    type: els.chartType.value,
    dimension: els.chartDimension.value,
    metric: els.chartMetric.value,
    aggregation: els.chartAggregation.value,
    limit: els.chartType.value === "bar" ? 12 : undefined
  });
  saveCharts();
  els.chartDialog.close();
  render();
}

async function refreshData() {
  els.refreshButton.disabled = true;
  els.refreshButton.textContent = "Refreshing";
  try {
    const response = await fetch("/api/refresh", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Refresh failed");
    const data = await loadJson("/api/data");
    state.data = { ...data, records: normalizeRecords(data.records) };
    render();
  } catch (error) {
    alert(error.message);
  } finally {
    els.refreshButton.disabled = false;
    els.refreshButton.textContent = "Refresh Excel Data";
  }
}

function downloadCsv() {
  const rows = filteredRows();
  const columns = Object.keys(rows[0] || {});
  const csv = [columns.join(","), ...rows.map(row => columns.map(col => csvValue(row[col])).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "costco_filtered_rows.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function csvValue(value) {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function shortLabel(value, length = 14) {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, length - 1)}...` : text;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

init().catch(error => {
  document.body.innerHTML = `<main class="workspace"><h2>Dashboard failed to load</h2><p>${escapeHtml(error.message)}</p></main>`;
});
