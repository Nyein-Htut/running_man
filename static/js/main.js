const episodeInput = document.getElementById('episodeInput');
const episodeBtn = document.getElementById('episodeBtn');
const keywordInput = document.getElementById('keywordInput');
const keywordBtn = document.getElementById('keywordBtn');
const statusLine = document.getElementById('statusLine');
const resultsArea = document.getElementById('resultsArea');
const faqGrid = document.getElementById('faqGrid');

function setStatus(text, kind) {
  statusLine.textContent = text;
  statusLine.className = 'status-line' + (kind ? ` is-${kind}` : '');
}

function setLoading(button, isLoading, labelIdle, labelBusy) {
  button.disabled = isLoading;
  button.querySelector('.tear-btn-label').textContent = isLoading ? labelBusy : labelIdle;
}

function showLoadingSkeleton() {
  resultsArea.innerHTML = `
    <div class="placeholder">
      <span class="spinner"></span>
      <p style="margin-top:14px;">Digging through the archives...</p>
    </div>`;
}

function showError(message) {
  resultsArea.innerHTML = `
    <div class="error-box">
      <span class="err-emoji">🚫</span>
      <p>${message}</p>
    </div>`;
}

function clearActiveChips() {
  document.querySelectorAll('.faq-chip').forEach(c => c.classList.remove('is-active'));
}

/* ---------------------------------------------------------------------
   Single episode lookup
   --------------------------------------------------------------------- */
async function searchEpisode() {
  const raw = episodeInput.value.trim();
  if (!/^\d+$/.test(raw)) {
    setStatus('Please enter a valid episode number.', 'error');
    return;
  }

  clearActiveChips();
  setStatus('Querying archives...', 'info');
  setLoading(episodeBtn, true, 'Search', 'Searching...');
  showLoadingSkeleton();

  try {
    const res = await fetch(`/api/episode/${raw}`);
    const data = await res.json();

    if (!res.ok) {
      setStatus('No match found.', 'error');
      showError(data.error || `No database entry found for Episode ${raw}.`);
      return;
    }

    setStatus('Data retrieved successfully.', 'success');
    renderEpisodeCard(data);
  } catch (err) {
    setStatus('Network error — try again.', 'error');
    showError('Could not reach the server. Check your connection and retry.');
  } finally {
    setLoading(episodeBtn, false, 'Search', 'Searching...');
  }
}

function renderEpisodeCard(data) {
  const guestCount = (data['Guest(s)'] || '')
    .split(',')
    .map(g => g.trim())
    .filter(Boolean).length || 1;

  resultsArea.innerHTML = `
    <div class="episode-card">
      <p class="eyebrow-tag">EPISODE ${data.Episode}</p>
      <h3>${escapeHtml(data.Title)}</h3>
      <div class="chip-row">
        <span class="stat-chip">📅 ${escapeHtml(data.Year)}</span>
        <span class="stat-chip">🎤 ${guestCount} Guest${guestCount !== 1 ? 's' : ''}</span>
        <span class="stat-chip">📺 Ep. ${data.Episode}</span>
      </div>
      <div id="fieldRows"></div>
    </div>`;

  const fields = [
    ['📅', 'Air Date'],
    ['🎤', 'Guest(s)'],
    ['👥', 'Teams'],
    ['🎯', 'Mission'],
    ['🏆', 'Results'],
  ];
  const container = document.getElementById('fieldRows');

  fields.forEach(([emoji, key], i) => {
    const row = document.createElement('div');
    row.className = 'field-row';
    row.style.animationDelay = `${i * 70}ms`;
    row.innerHTML = `
      <div class="field-label">${emoji} ${key}</div>
      <div class="field-value">${escapeHtml(data[key] || 'N/A')}</div>`;
    container.appendChild(row);
  });
}

/* ---------------------------------------------------------------------
   Keyword search
   --------------------------------------------------------------------- */
async function searchKeyword() {
  const q = keywordInput.value.trim();
  if (q.length < 2) {
    setStatus('Type at least 2 characters to search.', 'error');
    return;
  }

  clearActiveChips();
  setStatus('Scanning every episode for a match — this can take a moment the first time...', 'info');
  setLoading(keywordBtn, true, 'Search', 'Searching...');
  showLoadingSkeleton();

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();

    if (!res.ok) {
      setStatus('Search failed.', 'error');
      showError(data.error || 'Something went wrong with that search.');
      return;
    }

    setStatus(`Found ${data.count} match${data.count !== 1 ? 'es' : ''} for "${data.query}".`, 'success');
    renderResultList(data.results, `Results for "${data.query}"`, data.count);
  } catch (err) {
    setStatus('Network error — try again.', 'error');
    showError('Could not reach the server. Check your connection and retry.');
  } finally {
    setLoading(keywordBtn, false, 'Search', 'Searching...');
  }
}

/* ---------------------------------------------------------------------
   FAQ presets
   --------------------------------------------------------------------- */
async function loadFaqCategory(slug, chipEl) {
  clearActiveChips();
  chipEl.classList.add('is-active');
  setStatus('Pulling that theme from the archive...', 'info');
  showLoadingSkeleton();

  try {
    const res = await fetch(`/api/faq/${slug}`);
    const data = await res.json();

    if (!res.ok) {
      setStatus('Could not load that category.', 'error');
      showError(data.error || 'Something went wrong.');
      return;
    }

    setStatus(`Found ${data.count} episode${data.count !== 1 ? 's' : ''} tagged "${data.label}".`, 'success');
    renderResultList(data.results, `${data.emoji} ${data.label}`, data.count);
  } catch (err) {
    setStatus('Network error — try again.', 'error');
    showError('Could not reach the server. Check your connection and retry.');
  }
}

function renderResultList(results, headerText, count) {
  if (!results || results.length === 0) {
    showError('No episodes matched. Try a broader keyword.');
    return;
  }

  const cappedNote = count > results.length
    ? ` (showing first ${results.length})`
    : '';

  resultsArea.innerHTML = `
    <p class="result-list-header">${escapeHtml(headerText)} — ${count} found${cappedNote}</p>
    <div id="resultItems"></div>`;

  const container = document.getElementById('resultItems');

  results.forEach((ep, i) => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.style.animationDelay = `${Math.min(i * 35, 600)}ms`;
    item.innerHTML = `
      <span class="result-ep">#${ep.Episode}</span>
      <div class="result-body">
        <div class="result-title">${escapeHtml(ep.Title || 'Untitled')}</div>
        <div class="result-meta">${escapeHtml(ep['Guest(s)'] || 'N/A')}</div>
      </div>
      <span class="result-year">${escapeHtml(ep.Year)}</span>`;
    item.addEventListener('click', () => {
      episodeInput.value = ep.Episode;
      window.scrollTo({ top: 0, behavior: 'smooth' });
      renderEpisodeCard(ep);
      setStatus(`Showing Episode ${ep.Episode}.`, 'success');
    });
    container.appendChild(item);
  });
}

/* ---------------------------------------------------------------------
   Helpers & wiring
   --------------------------------------------------------------------- */
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

episodeBtn.addEventListener('click', searchEpisode);
episodeInput.addEventListener('keydown', e => { if (e.key === 'Enter') searchEpisode(); });

keywordBtn.addEventListener('click', searchKeyword);
keywordInput.addEventListener('keydown', e => { if (e.key === 'Enter') searchKeyword(); });

faqGrid.addEventListener('click', e => {
  const chip = e.target.closest('.faq-chip');
  if (!chip) return;
  loadFaqCategory(chip.dataset.slug, chip);
});
