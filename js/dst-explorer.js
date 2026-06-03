// ============================================================
// dst-explorer.js
// Live DST API explorer for the AreaStat DK profile page.
// Fetches data directly from api.statbank.dk (CORS-enabled, free).
// ============================================================

const DST_API = 'https://api.statbank.dk/v1/';

// ── State ────────────────────────────────────────────────────
let _explorerKommune = [];   // 4-digit DAWA kodes of selected zones
let _explorerZoneType = 'kommune';
let _activeTableId = null;
let _tableInfoCache = {};    // tableId → tableinfo JSON
let _activeVariables = {};   // current variable selections
let _activeChartType = 'bar'; // 'bar' or 'line'
let _explorerChartInstances = [];

// ── Helpers ──────────────────────────────────────────────────

// Convert 4-digit DAWA kommunekode to 3-digit DST code
function dawaToDs(kode) {
  return String(parseInt(kode, 10));
}

function parseDSTcsv(text) {
  const lines = text.replace(/^﻿/, '').trim().split('\n');
  if (!lines.length) return { headers: [], rows: [] };
  const headers = lines[0].split(';').map(h => h.trim().replace(/^"|"$/g, ''));
  const rows = lines.slice(1).map(line => {
    const cells = line.split(';').map(c => c.trim().replace(/^"|"$/g, ''));
    const obj = {};
    headers.forEach((h, i) => { obj[h] = cells[i] ?? ''; });
    return obj;
  }).filter(r => Object.values(r).some(v => v !== ''));
  return { headers, rows };
}

async function dstFetch(tableId, variables) {
  const body = { table: tableId, format: 'CSV', delimiter: ';', lang: 'en', variables };
  try {
    const resp = await fetch(DST_API + 'data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(err.slice(0, 120));
    }
    return parseDSTcsv(await resp.text());
  } catch (e) {
    throw new Error('DST API: ' + e.message);
  }
}

async function dstTableInfo(tableId) {
  if (_tableInfoCache[tableId]) return _tableInfoCache[tableId];
  const resp = await fetch(DST_API + 'tableinfo/' + tableId + '?lang=en');
  if (!resp.ok) throw new Error('tableinfo failed: ' + resp.status);
  const info = await resp.json();
  _tableInfoCache[tableId] = info;
  return info;
}

function latestTidValue(tidVar) {
  const vals = tidVar?.values || [];
  return vals.length ? vals[vals.length - 1].id : null;
}

// ── Explorer initialisation ───────────────────────────────────

function initExplorer(selectedIds, zoneType) {
  _explorerKommune = Array.from(selectedIds || []);
  _explorerZoneType = zoneType || 'kommune';
  renderExplorerSidebar();
  if (_activeTableId) loadExplorerTable(_activeTableId);
}

// ── Sidebar rendering ─────────────────────────────────────────

function renderExplorerSidebar() {
  const sidebar = document.getElementById('explorer-sidebar');
  if (!sidebar) return;

  const sectors = getDSTSectors();
  sidebar.innerHTML = '';

  sectors.forEach(sector => {
    const tables = getDSTTablesForSector(sector);
    const icon = DST_SECTOR_ICONS[sector] || '📊';

    const section = document.createElement('div');
    section.className = 'exp-sector';

    const header = document.createElement('button');
    header.className = 'exp-sector-header';
    header.innerHTML = `<span class="exp-sector-icon">${escapeHtml(icon)}</span>
      <span class="exp-sector-name">${escapeHtml(sector)}</span>
      <span class="exp-sector-count">${tables.length}</span>
      <span class="exp-sector-chevron">▶</span>`;

    const list = document.createElement('div');
    list.className = 'exp-sector-tables';
    list.style.display = 'none';

    tables.forEach(tbl => {
      const item = document.createElement('button');
      item.className = 'exp-table-item';
      item.dataset.tableId = tbl.id;
      if (tbl.id === _activeTableId) item.classList.add('active');
      item.innerHTML = `<span class="exp-table-id">${escapeHtml(tbl.id)}</span>
        <span class="exp-table-title">${escapeHtml(tbl.title)}</span>`;
      item.addEventListener('click', () => loadExplorerTable(tbl.id));
      list.appendChild(item);
    });

    header.addEventListener('click', () => {
      const open = list.style.display !== 'none';
      list.style.display = open ? 'none' : 'block';
      header.querySelector('.exp-sector-chevron').textContent = open ? '▶' : '▼';
    });

    // Auto-expand sector containing active table
    if (_activeTableId && tables.some(t => t.id === _activeTableId)) {
      list.style.display = 'block';
      header.querySelector('.exp-sector-chevron').textContent = '▼';
    }

    section.appendChild(header);
    section.appendChild(list);
    sidebar.appendChild(section);
  });
}

// ── Table loading ─────────────────────────────────────────────

async function loadExplorerTable(tableId) {
  _activeTableId = tableId;

  // Update active state in sidebar
  document.querySelectorAll('.exp-table-item').forEach(el => {
    el.classList.toggle('active', el.dataset.tableId === tableId);
  });

  const panel = document.getElementById('explorer-panel');
  if (!panel) return;

  const catEntry = DST_TABLE_INDEX[tableId];
  panel.innerHTML = `<div class="exp-loading">
    <div class="exp-spinner"></div>
    <span>Loading ${escapeHtml(tableId)} metadata…</span>
  </div>`;

  try {
    const info = await dstTableInfo(tableId);
    const tidVar = info.variables.find(v => v.id === 'Tid');
    const areaVar = info.variables.find(v =>
      ['OMRÅDE','KOMKODE','BOPOMR','BOPKODE','REGION'].includes(v.id));

    // Build variable controls
    _activeVariables = {};
    info.variables.forEach(v => {
      if (v.id === 'Tid') {
        _activeVariables[v.id] = latestTidValue(v);
      } else if (v.id === areaVar?.id) {
        _activeVariables[v.id] = '__kommuner__'; // special: use selected kommuner
      } else {
        // Use default from catalogue, or first value
        const catDefault = (catEntry?.defaults || []).find(d => d.code === v.id);
        _activeVariables[v.id] = catDefault ? catDefault.val : (v.values?.[0]?.id || '');
      }
    });

    renderExplorerPanel(info, catEntry, areaVar, tidVar);
    await fetchAndRenderExplorerData(info, catEntry, areaVar, tidVar);

  } catch (e) {
    panel.innerHTML = `<div class="exp-error">
      <strong>Failed to load ${escapeHtml(tableId)}:</strong><br>${escapeHtml(e.message)}
    </div>`;
  }
}

// ── Panel structure rendering ─────────────────────────────────

function renderExplorerPanel(info, catEntry, areaVar, tidVar) {
  const panel = document.getElementById('explorer-panel');
  if (!panel) return;

  const title  = catEntry?.title || info.text;
  const desc   = catEntry?.desc  || '';
  const unit   = catEntry?.unit  || '';
  const hasTid = !!tidVar;

  panel.innerHTML = `
    <div class="exp-panel-header">
      <div>
        <h2 class="exp-panel-title">${escapeHtml(title)}</h2>
        <p class="exp-panel-desc">${escapeHtml(desc)}</p>
        <span class="exp-panel-meta">
          DST table <strong>${escapeHtml(info.id)}</strong>
          · Updated ${escapeHtml(info.updated || '')}
          · ${hasTid ? escapeHtml(info.variables.find(v=>v.id==='Tid')?.values?.[0]?.id||'') + '–' + escapeHtml(latestTidValue(tidVar)||'') : 'Static'}
        </span>
      </div>
    </div>

    <div class="exp-controls">
      <div class="exp-var-row" id="exp-var-controls"></div>
      <div class="exp-chart-toggle">
        <button class="exp-chart-btn ${_activeChartType==='bar'?'active':''}" data-type="bar">📊 Bar</button>
        ${hasTid ? `<button class="exp-chart-btn ${_activeChartType==='line'?'active':''}" data-type="line">📈 Time Series</button>` : ''}
      </div>
    </div>

    <div id="exp-loading-bar" class="exp-loading" style="display:none">
      <div class="exp-spinner"></div><span>Fetching data…</span>
    </div>
    <div id="exp-error-msg" class="exp-error" style="display:none"></div>

    <div id="exp-chart-container" class="exp-chart-container"></div>
    <div id="exp-data-table-container" class="exp-data-table-wrap"></div>
  `;

  // Populate variable dropdowns (skip area and Tid)
  const varControls = document.getElementById('exp-var-controls');
  info.variables.forEach(v => {
    if (v.id === 'Tid' || v.id === areaVar?.id) return;
    if (!v.values || v.values.length <= 1) return;

    const wrap = document.createElement('div');
    wrap.className = 'exp-var-control';

    const lbl = document.createElement('label');
    lbl.textContent = v.text || v.id;
    lbl.className = 'exp-var-label';

    const sel = document.createElement('select');
    sel.className = 'exp-var-select';
    sel.dataset.varId = v.id;
    v.values.forEach(val => {
      const opt = document.createElement('option');
      opt.value = val.id;
      opt.textContent = `${val.text || val.id}`;
      if (val.id === _activeVariables[v.id]) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener('change', async () => {
      _activeVariables[v.id] = sel.value;
      await fetchAndRenderExplorerData(info, catEntry, areaVar, tidVar);
    });

    wrap.appendChild(lbl);
    wrap.appendChild(sel);
    varControls.appendChild(wrap);
  });

  // Time period dropdown
  if (hasTid) {
    const wrap = document.createElement('div');
    wrap.className = 'exp-var-control';
    const lbl = document.createElement('label');
    lbl.textContent = 'Period';
    lbl.className = 'exp-var-label';

    const sel = document.createElement('select');
    sel.className = 'exp-var-select';
    sel.dataset.varId = 'Tid';
    tidVar.values.forEach(val => {
      const opt = document.createElement('option');
      opt.value = val.id;
      opt.textContent = val.text || val.id;
      if (val.id === _activeVariables['Tid']) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener('change', async () => {
      if (_activeChartType !== 'line') {
        _activeVariables['Tid'] = sel.value;
        await fetchAndRenderExplorerData(info, catEntry, areaVar, tidVar);
      }
    });
    wrap.appendChild(lbl);
    wrap.appendChild(sel);
    varControls.appendChild(wrap);
  }

  // Chart type toggle
  panel.querySelectorAll('.exp-chart-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      _activeChartType = btn.dataset.type;
      panel.querySelectorAll('.exp-chart-btn').forEach(b => b.classList.toggle('active', b === btn));
      await fetchAndRenderExplorerData(info, catEntry, areaVar, tidVar);
    });
  });
}

// ── Data fetching + rendering ─────────────────────────────────

async function fetchAndRenderExplorerData(info, catEntry, areaVar, tidVar) {
  const loadBar = document.getElementById('exp-loading-bar');
  const errMsg  = document.getElementById('exp-error-msg');
  if (loadBar) { loadBar.style.display = 'flex'; }
  if (errMsg)  { errMsg.style.display = 'none'; }

  try {
    const kommunerDST = _explorerKommune.map(dawaToDs);
    if (!kommunerDST.length) throw new Error('No zones selected — go back to the map and select some kommuner first.');

    // Build variable list for the API call
    const buildVars = (tidOverride) => {
      return info.variables.map(v => {
        if (v.id === areaVar?.id) {
          // Include selected kommuner + "000" (Denmark total) as reference
          return { code: v.id, values: [...kommunerDST, '000'] };
        }
        if (v.id === 'Tid') {
          if (tidOverride) return { code: 'Tid', values: tidOverride };
          return { code: 'Tid', values: [_activeVariables['Tid'] || latestTidValue(tidVar)] };
        }
        const val = _activeVariables[v.id];
        if (!val) return null;
        return { code: v.id, values: [val] };
      }).filter(Boolean);
    };

    // Find value column name in response
    const findValueCol = (headers) =>
      headers.find(h => /indhold|value|antal|number|count|amount|dkk|pct|per cent|km|persons|vehicles/i.test(h))
      || headers[headers.length - 1];

    // Find area column name
    const findAreaCol = (headers, varId) =>
      headers.find(h => new RegExp(varId, 'i').test(h))
      || headers.find(h => /omr|area|komm|region|bop/i.test(h))
      || headers[0];

    if (_activeChartType === 'line' && tidVar) {
      // Time series: fetch all Tid periods
      const allTid = tidVar.values.map(v => v.id).slice(-20); // last 20 periods
      const vars = buildVars(allTid);
      const { rows, headers } = await dstFetch(info.id, vars);
      if (!rows.length) throw new Error('No data returned for this selection.');

      const valCol  = findValueCol(headers);
      const areaCol = findAreaCol(headers, areaVar?.id || 'OMRADE');
      const tidCol  = headers.find(h => /tid|time|period/i.test(h)) || 'Tid';

      // Group by area + time
      const series = {};
      rows.forEach(r => {
        const area = r[areaCol] || '';
        const tid  = r[tidCol]  || '';
        const val  = parseFloat(String(r[valCol] || '').replace(',','.'));
        if (isNaN(val)) return;
        if (!series[area]) series[area] = {};
        series[area][tid] = (series[area][tid] || 0) + val;
      });

      const periods = [...new Set(rows.map(r => r[tidCol]))].sort();
      renderExplorerTimeSeries(series, periods, catEntry, kommunerDST);
      renderExplorerDataTable(rows, headers, valCol);

    } else {
      // Bar chart: single period
      const vars = buildVars(null);
      const { rows, headers } = await dstFetch(info.id, vars);
      if (!rows.length) throw new Error('No data returned for this selection.');

      const valCol  = findValueCol(headers);
      const areaCol = findAreaCol(headers, areaVar?.id || 'OMRADE');

      // Aggregate by area (in case there are residual breakdowns)
      const aggregated = {};
      rows.forEach(r => {
        const area = r[areaCol] || '?';
        const val  = parseFloat(String(r[valCol] || '').replace(',','.'));
        if (!isNaN(val)) aggregated[area] = (aggregated[area] || 0) + val;
      });

      renderExplorerBarChart(aggregated, catEntry, kommunerDST);
      renderExplorerDataTable(rows, headers, valCol);
    }

  } catch (e) {
    if (errMsg) {
      errMsg.style.display = 'block';
      errMsg.innerHTML = `<strong>Error:</strong> ${escapeHtml(e.message)}`;
    }
    document.getElementById('exp-chart-container').innerHTML = '';
    document.getElementById('exp-data-table-container').innerHTML = '';
  } finally {
    if (loadBar) loadBar.style.display = 'none';
  }
}

// ── Bar chart ─────────────────────────────────────────────────

function renderExplorerBarChart(aggregated, catEntry, kommunerDST) {
  const container = document.getElementById('exp-chart-container');
  if (!container) return;
  container.innerHTML = '';

  _explorerChartInstances.forEach(c => c?.destroy?.());
  _explorerChartInstances = [];

  const unit = catEntry?.unit || '';
  const dk   = aggregated['000'] ?? aggregated['All Denmark'] ?? null;

  // Only show selected kommuner (exclude "000" / Denmark total row)
  const entries = Object.entries(aggregated)
    .filter(([k]) => k !== '000' && k !== 'All Denmark' && k !== 'Hele landet')
    .sort((a, b) => b[1] - a[1]);

  if (!entries.length) {
    container.innerHTML = '<p class="exp-nodata">No data to display for selected kommuner.</p>';
    return;
  }

  const labels = entries.map(([k]) => window.gcdNameMap?.[k.padStart(4,'0')] || k);
  const values = entries.map(([, v]) => v);
  const zoneMax = Math.max(...values) || 1;
  // Exclude Denmark reference from axis scale if it dwarfs zone values (e.g. national total vs municipal)
  const dkScaleOk = dk !== null && Math.abs(dk) < zoneMax * 5 && Math.abs(dk) > zoneMax / 5;
  const maxVal = Math.max(...values, dkScaleOk ? dk : 0) * 1.15 || 1;

  const wrap = document.createElement('div');
  wrap.className = 'exp-bar-wrap';
  wrap.innerHTML = `<h3 class="exp-chart-title">${escapeHtml(catEntry?.title || '')} — ${escapeHtml(unit)}</h3>`;

  if (dk !== null) {
    const dkLabel = dkScaleOk
      ? `Denmark avg: <strong>${formatExpValue(dk, unit)}</strong>`
      : `Denmark total: <strong>${formatExpValue(dk, unit)}</strong> <em style="color:#9ca3af;font-size:.72rem;">(not shown on chart — national scale)</em>`;
    wrap.innerHTML += `<div class="exp-dk-legend"><span class="exp-dk-swatch"></span> ${dkLabel}</div>`;
  }

  const canvasWrap = document.createElement('div');
  canvasWrap.style.cssText = `position:relative;height:${Math.max(200, entries.length * 28 + 60)}px;width:100%;`;
  const canvas = document.createElement('canvas');
  canvasWrap.appendChild(canvas);
  wrap.appendChild(canvasWrap);
  container.appendChild(wrap);

  const chart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: '#1e3a5f',
        borderWidth: 0,
        barPercentage: 0.7,
        categoryPercentage: 0.85
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${formatExpValue(ctx.raw, unit)}`
          }
        }
      },
      scales: {
        x: {
          beginAtZero: true,
          max: maxVal,
          ticks: { callback: v => formatExpValue(Number(v), unit) },
          grid: { color: '#f0f0f0' }
        },
        y: { grid: { display: false } }
      },
      animation: { duration: 250 }
    },
    plugins: [{
      id: 'dkLine',
      afterDatasetsDraw(ch) {
        if (dk === null || !dkScaleOk) return;
        const x = ch.scales.x.getPixelForValue(dk);
        const { top, bottom } = ch.chartArea;
        const ctx = ch.ctx;
        ctx.save();
        ctx.strokeStyle = '#dc2626';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
        ctx.stroke();
        ctx.restore();
      }
    }]
  });

  _explorerChartInstances.push(chart);
}

// ── Time series chart ─────────────────────────────────────────

function renderExplorerTimeSeries(series, periods, catEntry, kommunerDST) {
  const container = document.getElementById('exp-chart-container');
  if (!container) return;
  container.innerHTML = '';

  _explorerChartInstances.forEach(c => c?.destroy?.());
  _explorerChartInstances = [];

  const unit   = catEntry?.unit || '';
  const COLORS = ['#1d6fa5','#e07520','#2ca25f','#6b2d8b','#dc2626','#0e7490','#b45309'];
  const dkKey  = Object.keys(series).find(k => ['000','All Denmark','Hele landet'].includes(k));

  const kommuneEntries = Object.entries(series)
    .filter(([k]) => !['000','All Denmark','Hele landet'].includes(k));

  const wrap = document.createElement('div');
  wrap.className = 'exp-ts-wrap';
  wrap.innerHTML = `<h3 class="exp-chart-title">${escapeHtml(catEntry?.title || '')} — Time Series</h3>`;

  const canvasWrap = document.createElement('div');
  canvasWrap.style.cssText = 'position:relative;height:320px;width:100%;';
  const canvas = document.createElement('canvas');
  canvasWrap.appendChild(canvas);
  wrap.appendChild(canvasWrap);
  container.appendChild(wrap);

  const datasets = kommuneEntries.map(([area, values], i) => ({
    label: window.gcdNameMap?.[area.padStart(4,'0')] || area,
    data: periods.map(p => values[p] ?? null),
    borderColor: COLORS[i % COLORS.length],
    backgroundColor: COLORS[i % COLORS.length] + '22',
    borderWidth: 2.5,
    pointRadius: periods.length > 20 ? 0 : 3,
    tension: 0.3,
    fill: false,
    spanGaps: true
  }));

  // Denmark reference line — only if its scale is comparable to zone values
  if (dkKey) {
    const dkVals = periods.map(p => series[dkKey][p]).filter(v => v != null);
    const zVals  = kommuneEntries.flatMap(([, v]) => periods.map(p => v[p])).filter(v => v != null);
    const dkMed  = dkVals.length ? dkVals.reduce((a,b) => a+b, 0) / dkVals.length : 0;
    const zMed   = zVals.length  ? zVals.reduce((a,b) => a+b, 0)  / zVals.length  : 0;
    const scaleOk = zMed > 0 && dkMed / zMed < 5 && dkMed / zMed > 0.2;
    if (scaleOk) {
      datasets.push({
        label: 'Denmark',
        data: periods.map(p => series[dkKey][p] ?? null),
        borderColor: '#94a3b8',
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        borderDash: [6, 4],
        pointRadius: 0,
        fill: false,
        spanGaps: true
      });
    }
  }

  const chart = new Chart(canvas, {
    type: 'line',
    data: { labels: periods, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${formatExpValue(ctx.raw, unit)}`
          }
        }
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 12, font: { size: 10 } },
          grid: { color: '#f0f0f0' }
        },
        y: {
          beginAtZero: false,
          ticks: { callback: v => formatExpValue(Number(v), unit) },
          grid: { color: '#f0f0f0' }
        }
      },
      animation: { duration: 250 }
    }
  });

  _explorerChartInstances.push(chart);
}

// ── Data table ────────────────────────────────────────────────

function renderExplorerDataTable(rows, headers, valCol) {
  const container = document.getElementById('exp-data-table-container');
  if (!container || !rows.length) return;

  const unit = DST_TABLE_INDEX[_activeTableId]?.unit || '';

  // Show max 200 rows
  const display = rows.slice(0, 200);

  let html = `<h3 class="exp-table-heading">Data table
    <span class="exp-table-count">${rows.length} rows${rows.length > 200 ? ' (showing first 200)' : ''}</span>
    <button class="exp-dl-csv" onclick="downloadExplorerCSV()">⬇ CSV</button>
  </h3>
  <div class="exp-table-scroll">
  <table class="exp-data-table">
    <thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
    <tbody>
      ${display.map(row =>
        `<tr>${headers.map(h => {
          const cell = row[h] ?? '';
          const isVal = h === valCol;
          const num = parseFloat(String(cell).replace(',','.'));
          return `<td${isVal ? ' class="exp-val-cell"' : ''}>${escapeHtml(isVal && !isNaN(num) ? formatExpValue(num, unit) : cell)}</td>`;
        }).join('')}</tr>`
      ).join('')}
    </tbody>
  </table>
  </div>`;

  container.innerHTML = html;
  window._explorerCSVRows = rows;
  window._explorerCSVHeaders = headers;
}

function downloadExplorerCSV() {
  const rows = window._explorerCSVRows || [];
  const headers = window._explorerCSVHeaders || [];
  if (!rows.length) return;
  const csv = [headers.join(';'),
    ...rows.map(r => headers.map(h => r[h] ?? '').join(';'))
  ].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `dst_${_activeTableId || 'data'}.csv`;
  link.click();
}

// ── Value formatter ───────────────────────────────────────────

function formatExpValue(v, unit) {
  if (v === null || v === undefined || isNaN(v)) return '–';
  const u = (unit || '').toLowerCase();
  if (u.includes('per cent') || u.includes('%')) return v.toFixed(1) + '%';
  if (u.includes('dkk') || u.includes('kr')) {
    if (Math.abs(v) >= 1e9)  return (v/1e9).toFixed(2)  + ' bn DKK';
    if (Math.abs(v) >= 1e6)  return (v/1e6).toFixed(1)  + ' m DKK';
    if (Math.abs(v) >= 1000) return (v/1000).toFixed(0) + 'k DKK';
    return v.toFixed(0) + ' DKK';
  }
  if (Math.abs(v) >= 1e6)  return (v/1e6).toFixed(2)  + 'm';
  if (Math.abs(v) >= 1000) return (v/1000).toFixed(1) + 'k';
  return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(1);
}
