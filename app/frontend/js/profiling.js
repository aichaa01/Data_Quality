async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function completenessColor(pct) {
  if (pct >= 95) return 'var(--success)';
  if (pct >= 80) return 'var(--warning)';
  return 'var(--danger)';
}

async function loadOverview() {
  try {
    const data = await fetchJSON('/api/profiling/summary');
    const tbody = document.getElementById('overview-body');
    tbody.innerHTML = data.map(t => `
      <tr>
        <td><strong>${t.table_name}</strong></td>
        <td>${(t.row_count || 0).toLocaleString('fr-FR')}</td>
      </tr>
    `).join('');
  } catch (e) {
    console.error('loadOverview error:', e);
  }
}

async function loadTableProfile() {
  const table = document.getElementById('table-select').value;
  if (!table) {
    document.getElementById('table-detail').style.display = 'none';
    return;
  }

  document.getElementById('table-detail').style.display = 'block';
  document.getElementById('columns-body').innerHTML =
    '<tr><td colspan="6" style="text-align:center;padding:20px;"><div class="spinner"></div></td></tr>';

  try {
    const data = await fetchJSON(`/api/profiling/${table}`);

    document.getElementById('detail-table-name').textContent = data.table_name + ' — Colonnes';
    document.getElementById('detail-row-count').textContent =
      (data.row_count || 0).toLocaleString('fr-FR') + ' lignes';

    document.getElementById('columns-body').innerHTML = (data.columns || []).map(col => `
      <tr>
        <td><strong>${col.column_name}</strong></td>
        <td><code style="font-size:11px;color:var(--muted);">${col.data_type}</code></td>
        <td>${(col.null_count || 0).toLocaleString('fr-FR')}</td>
        <td>
          <span style="font-weight:600;color:${completenessColor(col.completude)};">
            ${col.completude}%
          </span>
        </td>
        <td>${(col.distinct_count || 0).toLocaleString('fr-FR')}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px;">
            <div class="progress-bar" style="width:120px;">
              <div class="progress-fill" style="
                width:${col.completude}%;
                background:${completenessColor(col.completude)};
              "></div>
            </div>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    document.getElementById('columns-body').innerHTML =
      '<tr><td colspan="6" style="text-align:center;color:var(--danger);padding:20px;">Erreur chargement: ' + e.message + '</td></tr>';
    console.error('loadTableProfile error:', e);
  }
}

loadOverview();