/* ── Upload page ────────────────────────────────────────────────────── */
function initUploadPage() {
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const submitBtn = document.getElementById('submitBtn');
  const selectedFileName = document.getElementById('selectedFileName');

  if (!dropZone) return;

  dropZone.addEventListener('click', () => fileInput.click());

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      fileInput.files = files;
      handleFileSelection(files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFileSelection(fileInput.files[0]);
    }
  });

  function handleFileSelection(file) {
    if (!file.name.toLowerCase().endsWith('.csv')) {
      selectedFileName.textContent = 'Only .csv files are supported.';
      selectedFileName.style.color = 'var(--bs-danger)';
      submitBtn.disabled = true;
      return;
    }
    selectedFileName.textContent = file.name;
    selectedFileName.style.color = '';
    submitBtn.disabled = false;
  }
}

/* ── Dashboard page ─────────────────────────────────────────────────── */
function initDashboard() {
  const chartTypeEl = document.getElementById('chartType');
  const xColGroup = document.getElementById('xColGroup');
  const yColGroup = document.getElementById('yColGroup');
  const colorColGroup = document.getElementById('colorColGroup');
  const buildBtn = document.getElementById('buildChartBtn');
  const chartContainer = document.getElementById('chartContainer');
  const chartError = document.getElementById('chartError');

  if (!chartTypeEl) return;

  const needsXOnly = ['histogram', 'box', 'pie'];
  const needsXY = ['scatter', 'bar', 'line'];
  const noAxes = ['heatmap'];

  function updateControls() {
    const ct = chartTypeEl.value;
    xColGroup.style.display = noAxes.includes(ct) ? 'none' : '';
    yColGroup.style.display = (needsXY.includes(ct)) ? '' : 'none';
    colorColGroup.style.display = noAxes.includes(ct) ? 'none' : '';
  }

  chartTypeEl.addEventListener('change', updateControls);
  updateControls();

  buildBtn.addEventListener('click', async () => {
    const payload = {
      chart_type: chartTypeEl.value,
      x: document.getElementById('xCol').value || null,
      y: document.getElementById('yCol').value || null,
      color: document.getElementById('colorCol').value || null,
    };

    chartError.classList.add('d-none');
    buildBtn.disabled = true;
    buildBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Building…';

    try {
      const resp = await fetch('/api/chart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();

      if (!resp.ok || data.error) {
        showError(data.error || 'Failed to build chart.');
        return;
      }

      chartContainer.innerHTML = '<div id="plotDiv" style="width:100%;height:480px;"></div>';
      Plotly.newPlot('plotDiv', data.data, data.layout, { responsive: true });
    } catch (err) {
      showError('An unexpected error occurred.');
    } finally {
      buildBtn.disabled = false;
      buildBtn.innerHTML = '<i class="bi bi-bar-chart me-2"></i>Build Chart';
    }
  });

  function showError(msg) {
    chartError.textContent = msg;
    chartError.classList.remove('d-none');
  }
}

/* ── Analysis page ──────────────────────────────────────────────────── */
function initAnalysis() {
  loadColumnOverview();

  const inspectBtn = document.getElementById('inspectBtn');
  if (inspectBtn) {
    inspectBtn.addEventListener('click', inspectColumn);
  }
}

async function loadColumnOverview() {
  const tbody = document.getElementById('colOverviewBody');
  if (!tbody) return;

  try {
    const resp = await fetch('/api/stats');
    if (!resp.ok) throw new Error('Failed to load stats');
    const cols = await resp.json();

    tbody.innerHTML = cols.map((c) => `
      <tr>
        <td class="fw-semibold">${escHtml(c.column)}</td>
        <td><span class="badge-dtype">${escHtml(c.dtype)}</span></td>
        <td>${c.unique}</td>
        <td class="${c.missing > 0 ? 'text-warning fw-semibold' : ''}">${c.missing}</td>
        <td>${c.mean !== undefined ? c.mean : '—'}</td>
        <td>${c.std !== undefined ? c.std : '—'}</td>
      </tr>
    `).join('');
  } catch {
    tbody.innerHTML = '<tr><td colspan="6" class="text-danger p-3">Could not load column overview.</td></tr>';
  }
}

async function inspectColumn() {
  const colEl = document.getElementById('inspectCol');
  const container = document.getElementById('colStatsContainer');
  const table = document.getElementById('colStatsTable');

  const col = colEl.value;
  if (!col) return;

  try {
    const resp = await fetch(`/api/stats?col=${encodeURIComponent(col)}`);
    if (!resp.ok) throw new Error('Failed to load stats');
    const s = await resp.json();

    const rows = Object.entries(s)
      .filter(([k]) => k !== 'column')
      .map(([k, v]) => `<tr><td class="text-muted">${escHtml(k)}</td><td class="fw-semibold">${escHtml(String(v))}</td></tr>`)
      .join('');

    table.innerHTML = rows;
    container.classList.remove('d-none');
  } catch {
    container.classList.add('d-none');
  }
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
