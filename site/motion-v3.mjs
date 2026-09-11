const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function currentFigure() { return document.querySelector('.map-figure'); }
function currentSvg() { return document.querySelector('#countyMap'); }

function ensureTargetRing(figure) {
  let ring = figure.querySelector('.map-target-ring');
  if (!ring) {
    ring = document.createElement('span');
    ring.className = 'map-target-ring';
    ring.setAttribute('aria-hidden','true');
    figure.appendChild(ring);
  }
  return ring;
}

function selectedPath(svg) {
  return svg?.querySelector('.county-path.selected') || null;
}

function focusSelected() {
  const figure = currentFigure();
  const svg = currentSvg();
  const path = selectedPath(svg);
  if (!figure || !svg || !path) return;
  const svgRect = svg.getBoundingClientRect();
  const pathRect = path.getBoundingClientRect();
  if (!svgRect.width || !svgRect.height) return;
  const cx = pathRect.left + pathRect.width / 2;
  const cy = pathRect.top + pathRect.height / 2;
  const x = ((cx - svgRect.left) / svgRect.width) * 100;
  const y = ((cy - svgRect.top) / svgRect.height) * 100;
  const county = path.getAttribute('data-county') || '目前縣市';
  const isSmall = Math.max(pathRect.width, pathRect.height) < Math.min(svgRect.width, svgRect.height) * .12;
  const scale = window.innerWidth < 760 ? 1.35 : (isSmall ? 1.85 : 1.55);
  figure.style.setProperty('--zoom-x', `${x.toFixed(2)}%`);
  figure.style.setProperty('--zoom-y', `${y.toFixed(2)}%`);
  figure.style.setProperty('--zoom-scale', scale);
  figure.classList.add('is-zoomed');
  const ring = ensureTargetRing(figure);
  const figRect = figure.getBoundingClientRect();
  ring.style.left = `${cx - figRect.left}px`;
  ring.style.top = `${cy - figRect.top}px`;
  const label = figure.querySelector('.map-focus-label'); if (label) label.textContent = county;
  const btn = figure.querySelector('[data-map-focus]'); if (btn) btn.textContent = '返回全台';
  if (!reduceMotion) {
    figure.classList.remove('motion-camera-zoom'); void figure.offsetWidth; figure.classList.add('motion-camera-zoom');
    setTimeout(()=>figure.classList.remove('motion-camera-zoom'), 700);
  }
}

function resetFocus() {
  const figure = currentFigure(); if (!figure) return;
  figure.classList.remove('is-zoomed');
  figure.style.setProperty('--zoom-scale',1);
  const label = figure.querySelector('.map-focus-label'); if (label) label.textContent = '全台';
  const btn = figure.querySelector('[data-map-focus]'); if (btn) btn.textContent = '聚焦縣市';
  if (!reduceMotion) {
    figure.classList.remove('motion-camera-reset'); void figure.offsetWidth; figure.classList.add('motion-camera-reset');
    setTimeout(()=>figure.classList.remove('motion-camera-reset'), 550);
  }
}

function toggleFocus() {
  const figure = currentFigure(); if (!figure) return;
  figure.classList.contains('is-zoomed') ? resetFocus() : focusSelected();
}

async function toggleFullscreen() {
  const figure = currentFigure(); if (!figure) return;
  try {
    if (document.fullscreenElement === figure) await document.exitFullscreen();
    else await figure.requestFullscreen();
  } catch {}
}

function buildCommandbar(figure) {
  if (!figure || figure.querySelector('.map-commandbar')) return;
  const bar = document.createElement('div');
  bar.className = 'map-commandbar';
  bar.innerHTML = '<span class="map-focus-label">全台</span><button type="button" data-map-focus>聚焦縣市</button><button type="button" data-map-fullscreen aria-label="切換全螢幕地圖">全螢幕</button>';
  bar.querySelector('[data-map-focus]').addEventListener('click', e => { e.stopPropagation(); toggleFocus(); });
  bar.querySelector('[data-map-fullscreen]').addEventListener('click', e => { e.stopPropagation(); toggleFullscreen(); });
  figure.appendChild(bar);
  ensureTargetRing(figure);
}

function refreshMapControls() {
  const figure = currentFigure();
  if (!figure) return;
  buildCommandbar(figure);
  if (figure.classList.contains('is-zoomed')) setTimeout(focusSelected, 30);
}

new MutationObserver(() => requestAnimationFrame(refreshMapControls)).observe(document.querySelector('#page'), {subtree:true, childList:true});
refreshMapControls();

document.addEventListener('click', event => {
  if (!event.target.closest('.county-path')) return;
  setTimeout(() => {
    const figure = currentFigure();
    if (figure?.classList.contains('is-zoomed')) focusSelected();
  }, 80);
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && currentFigure()?.classList.contains('is-zoomed') && !document.fullscreenElement) resetFocus();
  if ((event.key === 'f' || event.key === 'F') && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '')) toggleFullscreen();
  if ((event.key === 'z' || event.key === 'Z') && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '')) toggleFocus();
});

document.addEventListener('fullscreenchange', () => {
  const figure = currentFigure(); if (!figure) return;
  const btn = figure.querySelector('[data-map-fullscreen]');
  if (btn) btn.textContent = document.fullscreenElement === figure ? '退出全螢幕' : '全螢幕';
  setTimeout(() => { if (figure.classList.contains('is-zoomed')) focusSelected(); }, 80);
});
