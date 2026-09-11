const page = document.querySelector('#page');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let snapshots = [];
let index = 0;
let timer = null;
let timelineReady = false;

const fmtDate = value => new Date(value).toLocaleString('zh-TW', {timeZone:'Asia/Taipei', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
const pct = value => `${Math.round(Number(value || 0) * 100)}%`;
const leader = county => [...(county?.candidates || [])].sort((a,b)=>(b.probability ?? 0)-(a.probability ?? 0))[0] || null;

function currentCountyName() {
  return document.querySelector('#county')?.value || document.querySelector('#countyMap .county-path.selected')?.getAttribute('data-county') || snapshots.at(-1)?.counties?.[0]?.name || '';
}

function countyAt(snapshot, name) {
  return snapshot?.counties?.find(c => c.name === name) || null;
}

function changedCount(prev, next) {
  if (!prev || !next) return 0;
  return next.counties.reduce((count, county) => {
    const before = leader(countyAt(prev, county.name));
    const after = leader(county);
    return count + (before?.candidate_id && after?.candidate_id && before.candidate_id !== after.candidate_id ? 1 : 0);
  }, 0);
}

function changedCountyNames(prev, next) {
  if (!prev || !next) return [];
  return next.counties.filter(county => {
    const before = leader(countyAt(prev, county.name));
    const after = leader(county);
    return before?.candidate_id && after?.candidate_id && before.candidate_id !== after.candidate_id;
  }).map(c => c.name);
}

function timelineMarkup() {
  const last = snapshots.length - 1;
  return `<section class="forecast-timeline" aria-label="模型歷史回放">
    <div class="timeline-head">
      <div class="timeline-title"><strong>模型時間軸</strong><span>真實歸檔快照 · 拖動或播放查看模型如何變化</span></div>
      <div class="timeline-actions"><button type="button" data-timeline-first title="最早快照">起點</button><button type="button" data-timeline-play aria-pressed="false">播放</button><button type="button" data-timeline-live title="回到最新快照">最新</button></div>
    </div>
    <div class="timeline-body">
      <div class="timeline-track">
        <input type="range" min="0" max="${last}" value="${last}" step="1" data-timeline-slider aria-label="模型歷史快照">
        <div class="timeline-meta"><span>${fmtDate(snapshots[0].generated_at)}</span><span class="timeline-live">${snapshots.length} 個真實快照</span><span>${fmtDate(snapshots[last].generated_at)}</span></div>
        <div class="timeline-progress"><span></span></div>
      </div>
      <div class="timeline-detail" data-timeline-detail></div>
    </div>
  </section>`;
}

function detailMarkup(snapshot, previous) {
  const name = currentCountyName();
  const county = countyAt(snapshot, name) || snapshot.counties?.[0];
  const candidates = [...(county?.candidates || [])].sort((a,b)=>(b.probability ?? 0)-(a.probability ?? 0));
  const flips = changedCount(previous, snapshot);
  return `<div class="timeline-detail-top"><h3>${county?.name || '縣市'} · 歷史快照</h3><span class="timeline-date">${fmtDate(snapshot.generated_at)}</span></div>
    <div class="timeline-model">${snapshot.model_version || 'model'} · ${String(snapshot.fingerprint || '').slice(0,10)}</div>
    <div class="timeline-candidates">${candidates.slice(0,5).map(c=>`<div class="timeline-candidate"><span class="timeline-candidate-name">${c.name}</span><span class="timeline-candidate-bar"><span style="--candidate-prob:${Math.max(0,Math.min(100,(c.probability||0)*100))}%"></span></span><b>${pct(c.probability)}</b></div>`).join('')}</div>
    <div class="timeline-flips">${previous ? `與上一快照相比：<strong>${flips}</strong> 個縣市領先者改變` : '最早保存的模型快照'} · 收錄民調 ${snapshot.poll_ids?.length ?? 0} 題</div>`;
}

function animateMapChanges(previous, snapshot) {
  const figure = document.querySelector('.map-figure');
  const svg = document.querySelector('#countyMap');
  if (!figure || !svg) return;
  const changed = new Set(changedCountyNames(previous, snapshot));
  svg.querySelectorAll('.county-path').forEach(path => {
    path.classList.remove('timeline-changed');
    if (changed.has(path.getAttribute('data-county'))) {
      void path.getBoundingClientRect();
      path.classList.add('timeline-changed');
      setTimeout(() => path.classList.remove('timeline-changed'), 850);
    }
  });
  if (!reduceMotion) {
    figure.classList.remove('timeline-replay');
    void figure.offsetWidth;
    figure.classList.add('timeline-replay');
    setTimeout(() => figure.classList.remove('timeline-replay'), 480);
  }
}

function renderAt(nextIndex, animate=true) {
  if (!snapshots.length) return;
  index = Math.max(0, Math.min(snapshots.length - 1, Number(nextIndex)));
  const root = document.querySelector('.forecast-timeline');
  if (!root) return;
  const slider = root.querySelector('[data-timeline-slider]');
  if (slider) slider.value = String(index);
  root.style.setProperty('--timeline-progress', `${snapshots.length <= 1 ? 100 : index/(snapshots.length-1)*100}%`);
  const snapshot = snapshots[index];
  const previous = index > 0 ? snapshots[index - 1] : null;
  const detail = root.querySelector('[data-timeline-detail]');
  if (detail) {
    detail.innerHTML = detailMarkup(snapshot, previous);
    if (animate && !reduceMotion) detail.animate([{opacity:.35,transform:'translateX(8px)'},{opacity:1,transform:'none'}],{duration:300,easing:'cubic-bezier(.22,1,.36,1)'});
  }
  if (animate) animateMapChanges(previous, snapshot);
}

function stopPlayback() {
  if (timer) clearInterval(timer);
  timer = null;
  const root = document.querySelector('.forecast-timeline');
  root?.classList.remove('is-playing');
  const button = root?.querySelector('[data-timeline-play]');
  if (button) { button.textContent = '播放'; button.setAttribute('aria-pressed','false'); }
}

function startPlayback() {
  const root = document.querySelector('.forecast-timeline');
  if (!root || snapshots.length < 2) return;
  if (index >= snapshots.length - 1) renderAt(0, false);
  root.classList.add('is-playing');
  const button = root.querySelector('[data-timeline-play]');
  if (button) { button.textContent = '暫停'; button.setAttribute('aria-pressed','true'); }
  timer = setInterval(() => {
    if (index >= snapshots.length - 1) { stopPlayback(); return; }
    renderAt(index + 1, true);
  }, reduceMotion ? 1200 : 1450);
}

function bindTimeline(root) {
  root.querySelector('[data-timeline-slider]')?.addEventListener('input', e => { stopPlayback(); renderAt(e.target.value, true); });
  root.querySelector('[data-timeline-play]')?.addEventListener('click', () => timer ? stopPlayback() : startPlayback());
  root.querySelector('[data-timeline-first]')?.addEventListener('click', () => { stopPlayback(); renderAt(0, true); });
  root.querySelector('[data-timeline-live]')?.addEventListener('click', () => { stopPlayback(); renderAt(snapshots.length - 1, true); });
}

function mountTimeline() {
  if (!timelineReady || snapshots.length < 1) return;
  const existing = document.querySelector('.forecast-timeline');
  const mapDesk = document.querySelector('.map-desk');
  const head = document.querySelector('.page-head');
  if (!mapDesk || !head) { if (existing) existing.remove(); return; }
  if (!existing) {
    head.insertAdjacentHTML('afterend', timelineMarkup());
    const root = document.querySelector('.forecast-timeline');
    bindTimeline(root);
    index = snapshots.length - 1;
    renderAt(index, false);
  }
}

async function loadHistory() {
  try {
    const response = await fetch('./forecast-history.json', {cache:'no-store'});
    if (!response.ok) throw new Error('history unavailable');
    const data = await response.json();
    snapshots = [...(data.snapshots || [])].filter(s => Array.isArray(s.counties)).sort((a,b)=>new Date(a.generated_at)-new Date(b.generated_at));
    timelineReady = snapshots.length > 0;
    mountTimeline();
  } catch {
    timelineReady = false;
  }
}

if (page) {
  new MutationObserver(() => requestAnimationFrame(mountTimeline)).observe(page,{childList:true,subtree:true});
}

document.addEventListener('change', event => {
  if (event.target.matches('#county')) renderAt(index, false);
});
document.addEventListener('click', event => {
  if (event.target.closest('.county-path')) setTimeout(()=>renderAt(index,false),90);
});
document.addEventListener('visibilitychange', () => { if (document.hidden) stopPlayback(); });

loadHistory();
