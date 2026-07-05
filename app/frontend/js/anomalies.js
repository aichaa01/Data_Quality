let allSummary = [];
let currentRule = null;
let currentOffset = 0;
let currentRecordId = null;
let currentData = [];
const PAGE = 20;

const RULE_ID_COL = {
  'TX_GAB_SANS_ID':              'transaction_id',
  'TX_NON_GAB_AVEC_ID':          'transaction_id',
  'CARTE_ACTIVE_COMPTE_CLOTURE': 'carte_id',
  'TX_COMPTE_INEXISTANT':        'transaction_id',
  'CLIENT_AGENCE_FERMEE':        'client_id',
  'COMPTE_CLIENT_INEXISTANT':    'compte_id',
  'DIGITAL_CLIENT_INEXISTANT':   'usage_id',
  'CONTACT_INVALIDE':            'client_id',
};

document.getElementById('current-date').textContent =
  new Date().toLocaleDateString('fr-MA', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  });

async function api(url, opts) {
  const r = await fetch(url, opts);
  return r.json();
}

function dimBadge(dim) {
  const map = {
    'coherence':  'badge-coherence',
    'unicite':    'badge-unicite',
    'completude': 'badge-completude',
    'exactitude': 'badge-exactitude',
    'fraicheur':  'badge-fraicheur'
  };
  return `<span class="badge ${map[dim] || 'badge-gray'}">${dim}</span>`;
}

function progressBar(pct) {
  const color = pct > 10 ? 'var(--red)' : pct > 5 ? '#F59E0B' : '#15803D';
  return `
    <div style="display:flex;align-items:center;gap:8px;">
      <div class="progress-bar" style="width:90px;">
        <div class="progress-fill" style="width:${Math.min(pct,100)}%;background:${color};"></div>
      </div>
      <span style="font-size:12px;color:var(--muted);">${pct}%</span>
    </div>`;
}

async function loadSummary() {
  allSummary = await api('/api/anomalies/summary');
  const total = allSummary.reduce((s, r) => s + r.anomaly_count, 0);
  document.getElementById('total-badge').textContent =
    total.toLocaleString('fr-FR') + ' anomalies';
  renderSummary(allSummary);
}

function renderSummary(data) {
  const tbody = document.getElementById('summary-body');
  if (!data.length) {
    tbody.innerHTML = `<tr><td colspan="7">
      <div class="empty-state"><p>Aucune anomalie detectee</p></div>
    </td></tr>`;
    return;
  }
  tbody.innerHTML = data.map(r => `
    <tr>
      <td><code style="font-size:11px;color:var(--red);">${r.rule_id}</code></td>
      <td style="max-width:220px;">${r.description}</td>
      <td>${dimBadge(r.dimension)}</td>
      <td><strong style="color:var(--red);">${r.anomaly_count.toLocaleString('fr-FR')}</strong></td>
      <td>${r.anomaly_pct}%</td>
      <td style="min-width:160px;">${progressBar(r.anomaly_pct)}</td>
      <td>
        <button class="btn btn-primary btn-sm"
          onclick="openDetail('${r.rule_id}','${r.description}',${r.anomaly_count})">
          Inspecter
        </button>
      </td>
    </tr>`).join('');
}

function filterSummary() {
  const dim = document.getElementById('filter-dimension').value;
  const filtered = dim ? allSummary.filter(r => r.dimension === dim) : allSummary;
  renderSummary(filtered);
}

async function openDetail(ruleId, desc, count) {
  currentRule = ruleId;
  currentOffset = 0;
  const card = document.getElementById('detail-card');
  card.style.display = 'block';
  document.getElementById('detail-title').textContent = desc;
  document.getElementById('detail-count').textContent =
    count.toLocaleString('fr-FR') + ' anomalies';
  document.getElementById('detail-body').innerHTML =
    '<tr><td colspan="10" class="loading"><div class="spinner"></div></td></tr>';
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  await fetchDetail();
}

async function fetchDetail() {
  const data = await api(
    `/api/anomalies/${currentRule}?limit=${PAGE}&offset=${currentOffset}`
  );

  if (!data.data || !data.data.length) {
    document.getElementById('detail-thead').innerHTML = '';
    document.getElementById('detail-body').innerHTML =
      `<tr><td colspan="10">
        <div class="empty-state"><p>Aucun enregistrement en attente</p></div>
      </td></tr>`;
    document.getElementById('pagination-info').textContent = '';
    document.getElementById('btn-prev').disabled = true;
    document.getElementById('btn-next').disabled = true;
    return;
  }

  currentData = data.data;
  const cols = Object.keys(data.data[0]);
  const idCol = RULE_ID_COL[currentRule] || cols[0];

  document.getElementById('detail-thead').innerHTML =
    '<tr>' + cols.map(c => `<th>${c}</th>`).join('') +
    '<th style="min-width:160px;">Action</th></tr>';

  document.getElementById('detail-body').innerHTML = data.data.map(row => {
    const id = row[idCol] ?? row[cols[0]];
    return `<tr>
      ${cols.map(c => `
        <td>${row[c] == null
          ? '<span style="color:var(--red);font-size:11px;font-weight:600;">NULL</span>'
          : String(row[c]).length > 40
            ? '<span title="' + row[c] + '">' + String(row[c]).substring(0, 40) + '…</span>'
            : row[c]}
        </td>`).join('')}
      <td>
        <div style="display:flex;gap:6px;">
          <button class="btn btn-success btn-sm"
            onclick="openModal(${id}, 'accepted')">
            Accepter
          </button>
          <button class="btn btn-danger btn-sm"
            onclick="openModal(${id}, 'rejected')">
            Rejeter
          </button>
        </div>
      </td>
    </tr>`;
  }).join('');

  const total = data.page.total;
  const page  = Math.floor(currentOffset / PAGE) + 1;
  const pages = Math.ceil(total / PAGE);
  document.getElementById('pagination-info').textContent =
    `Page ${page} / ${pages} — ${total.toLocaleString('fr-FR')} anomalies`;
  document.getElementById('btn-prev').disabled = currentOffset === 0;
  document.getElementById('btn-next').disabled = currentOffset + PAGE >= total;
}

function prevPage() {
  currentOffset = Math.max(0, currentOffset - PAGE);
  fetchDetail();
}

function nextPage() {
  currentOffset += PAGE;
  fetchDetail();
}

function closeDetail() {
  document.getElementById('detail-card').style.display = 'none';
  currentRule = null;
}

async function openModal(recordId, defaultDecision) {
  currentRecordId = recordId;
  document.getElementById('modal-decision').value = defaultDecision;
  document.getElementById('modal-severity').value = 'medium';
  document.getElementById('modal-comment').value = '';
  document.getElementById('modal-record-info').textContent =
    `Regle: ${currentRule} | ID enregistrement: ${recordId}`;

  // Zone d'avertissement cascade
  const warnBox = document.getElementById('cascade-warning');
  if (warnBox) {
    warnBox.style.display = 'none';
    warnBox.innerHTML = '';
  }

  document.getElementById('decision-modal').style.display = 'flex';

  // Si rejet d'un client/compte, on previsualise la cascade
  if (defaultDecision === 'rejected' && warnBox) {
    try {
      const preview = await api(
        `/api/decisions/cascade-preview?rule_id=${currentRule}&record_id=${recordId}`
      );
      if (preview.total > 0) {
        const d = preview.details;
        const parts = [];
        if (d.comptes)       parts.push(`${d.comptes} compte(s)`);
        if (d.transactions)  parts.push(`${d.transactions} transaction(s)`);
        if (d.cartes)        parts.push(`${d.cartes} carte(s)`);
        if (d.digital_usage) parts.push(`${d.digital_usage} usage(s) digital(aux)`);

        warnBox.innerHTML = `
          <strong style="display:block;margin-bottom:6px;">
            Attention — rejet en cascade
          </strong>
          Rejeter cet enregistrement va aussi rejeter automatiquement :
          <strong>${parts.join(', ')}</strong>
          (soit ${preview.total} enregistrement(s) au total).
        `;
        warnBox.style.display = 'block';
      }
    } catch (e) {
      console.error('cascade-preview error:', e);
    }
  }
}

function closeModal() {
  document.getElementById('decision-modal').style.display = 'none';
}

// Re-evaluer la cascade si l'admin change accepted <-> rejected dans le modal
async function onDecisionChange() {
  const decision = document.getElementById('modal-decision').value;
  const warnBox = document.getElementById('cascade-warning');
  if (!warnBox) return;

  if (decision !== 'rejected') {
    warnBox.style.display = 'none';
    warnBox.innerHTML = '';
    return;
  }
  // Relancer la preview
  await openModalRefreshCascade();
}

async function openModalRefreshCascade() {
  const warnBox = document.getElementById('cascade-warning');
  if (!warnBox || currentRecordId == null) return;
  try {
    const preview = await api(
      `/api/decisions/cascade-preview?rule_id=${currentRule}&record_id=${currentRecordId}`
    );
    if (preview.total > 0) {
      const d = preview.details;
      const parts = [];
      if (d.comptes)       parts.push(`${d.comptes} compte(s)`);
      if (d.transactions)  parts.push(`${d.transactions} transaction(s)`);
      if (d.cartes)        parts.push(`${d.cartes} carte(s)`);
      if (d.digital_usage) parts.push(`${d.digital_usage} usage(s) digital(aux)`);
      warnBox.innerHTML = `
        <strong style="display:block;margin-bottom:6px;">
          Attention — rejet en cascade
        </strong>
        Rejeter cet enregistrement va aussi rejeter automatiquement :
        <strong>${parts.join(', ')}</strong>
        (soit ${preview.total} enregistrement(s) au total).
      `;
      warnBox.style.display = 'block';
    } else {
      warnBox.style.display = 'none';
    }
  } catch (e) {
    console.error('cascade refresh error:', e);
  }
}

async function submitDecision() {
  const decision = document.getElementById('modal-decision').value;
  const severity = document.getElementById('modal-severity').value;
  const comment  = document.getElementById('modal-comment').value;

  const btn = document.querySelector('#decision-modal .btn-primary');
  btn.disabled = true;
  btn.textContent = 'Enregistrement...';

  try {
    const res = await api('/api/decisions/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rule_id:    currentRule,
        table_name: currentRule,
        record_id:  currentRecordId,
        decision,
        severity,
        comment
      })
    });
    closeModal();
    if (res.cascade_count && res.cascade_count > 0) {
      alert(`Decision enregistree. ${res.cascade_count} enregistrement(s) rejete(s) en cascade.`);
    }
    await Promise.all([fetchDetail(), loadSummary()]);
  } catch (e) {
    alert('Erreur lors de l\'enregistrement');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Confirmer la decision';
  }
}

async function openBulkDecision(decision) {
  const label = decision === 'accepted' ? 'Accepter tout' : 'Rejeter tout';
  if (!confirm(`Confirmer "${label}" pour la regle ${currentRule} ?`)) return;

  try {
    const res = await api('/api/decisions/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rule_id:  currentRule,
        decision,
        severity: 'medium',
        comment:  'Decision groupee'
      })
    });
    alert(res.processed + ' enregistrements traites.');
    await Promise.all([fetchDetail(), loadSummary()]);
  } catch (e) {
    alert('Erreur: ' + e.message);
  }
}

document.getElementById('decision-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('decision-modal')) closeModal();
});

loadSummary();