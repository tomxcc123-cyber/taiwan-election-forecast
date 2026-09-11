const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const body = document.body;
const page = document.querySelector('#page');
const warRoom = document.querySelector('#warRoom');

function setWarRoom(on) {
  body.classList.toggle('war-room', on);
  if (warRoom) {
    warRoom.setAttribute('aria-pressed', String(on));
    warRoom.title = on ? '退出戰情模式' : '進入戰情模式';
  }
  try { localStorage.setItem('war-room', on ? '1' : '0'); } catch {}
  if (!reduceMotion) {
    body.animate(
      [{ opacity: .88 }, { opacity: 1 }],
      { duration: 260, easing: 'cubic-bezier(.22,1,.36,1)' }
    );
  }
}

if (warRoom) {
  let saved = false;
  try { saved = localStorage.getItem('war-room') === '1'; } catch {}
  setWarRoom(saved);
  warRoom.addEventListener('click', () => setWarRoom(!body.classList.contains('war-room')));
}

function addMapFocus() {
  const svg = document.querySelector('#countyMap');
  const selected = svg?.querySelector('.county-path.selected');
  if (!svg || !selected || svg.querySelector('.motion-focus-outline')) return;
  const clone = selected.cloneNode(false);
  clone.removeAttribute('tabindex');
  clone.removeAttribute('role');
  clone.removeAttribute('aria-label');
  clone.removeAttribute('aria-pressed');
  clone.removeAttribute('data-county');
  clone.setAttribute('class', 'motion-focus-outline');
  clone.setAttribute('aria-hidden', 'true');
  selected.parentNode?.appendChild(clone);
}

function scanMap() {
  if (reduceMotion) return;
  const figure = document.querySelector('.map-figure');
  const svg = document.querySelector('#countyMap');
  if (!figure || !svg) return;
  figure.classList.remove('motion-scan');
  svg.classList.remove('motion-map-refresh');
  void figure.offsetWidth;
  figure.classList.add('motion-scan');
  svg.classList.add('motion-map-refresh');
  window.setTimeout(() => figure.classList.remove('motion-scan'), 760);
  window.setTimeout(() => svg.classList.remove('motion-map-refresh'), 520);
}

function animateInspector() {
  if (reduceMotion) return;
  const inspector = document.querySelector('#inspector');
  if (!inspector) return;
  inspector.classList.remove('motion-inspector-swap');
  void inspector.offsetWidth;
  inspector.classList.add('motion-inspector-swap');
  window.setTimeout(() => inspector.classList.remove('motion-inspector-swap'), 460);
}

function enhanceCurrentView() {
  addMapFocus();
}

if (page) {
  const observer = new MutationObserver(mutations => {
    const mapChanged = mutations.some(m =>
      [...m.addedNodes].some(node => node.nodeType === 1 && (
        node.matches?.('#countyMap,.map-desk,.inspector') || node.querySelector?.('#countyMap,.map-desk,.inspector')
      ))
    );
    requestAnimationFrame(() => {
      enhanceCurrentView();
      if (mapChanged) addMapFocus();
    });
  });
  observer.observe(page, { childList: true, subtree: true });
  enhanceCurrentView();
}

// Map display mode buttons: make the redraw feel like a deliberate data transition.
document.addEventListener('click', event => {
  const modeButton = event.target.closest?.('[data-mode]');
  if (modeButton) requestAnimationFrame(() => window.setTimeout(scanMap, 0));

  const county = event.target.closest?.('.county-path');
  if (county) {
    const figure = county.closest('.map-figure');
    if (!reduceMotion && figure) {
      const rect = county.getBoundingClientRect();
      const fRect = figure.getBoundingClientRect();
      const x = rect.left + rect.width / 2 - fRect.left;
      const y = rect.top + rect.height / 2 - fRect.top;
      const pulse = document.createElement('span');
      pulse.className = 'motion-map-pulse';
      pulse.style.left = `${x}px`;
      pulse.style.top = `${y}px`;
      figure.appendChild(pulse);
      window.setTimeout(() => pulse.remove(), 620);
    }
    requestAnimationFrame(() => window.setTimeout(() => {
      addMapFocus();
      animateInspector();
    }, 0));
  }
});

// Select-driven county changes also receive the camera/inspector transition.
document.addEventListener('change', event => {
  if (event.target.matches('#county')) {
    requestAnimationFrame(() => window.setTimeout(() => {
      scanMap();
      addMapFocus();
      animateInspector();
    }, 0));
  }
});

// Scenario sliders: continuously communicate that the model is being recomputed.
let scenarioFrame = 0;
document.addEventListener('input', event => {
  if (!event.target.matches('.scenario-controls input[type="range"], .scenario-grid input[type="range"]')) return;
  cancelAnimationFrame(scenarioFrame);
  scenarioFrame = requestAnimationFrame(() => {
    const mapDesk = document.querySelector('.scenario-grid .map-desk');
    if (!mapDesk || reduceMotion) return;
    mapDesk.animate(
      [
        { transform: 'scale(.997)', filter: 'brightness(.98)' },
        { transform: 'scale(1)', filter: 'brightness(1)' }
      ],
      { duration: 220, easing: 'cubic-bezier(.22,1,.36,1)' }
    );
  });
});

// Data tables and validation plots get a directional transition when controls change.
document.addEventListener('change', event => {
  if (!event.target.matches('.filterbar select,.filterbar input,#seatGroup')) return;
  if (reduceMotion) return;
  const target = event.target.closest('.data-layout,.panel,.inspector,.history') || document.querySelector('.data-layout,.ratings');
  target?.animate(
    [{ opacity: .62, transform: 'translateY(4px)' }, { opacity: 1, transform: 'none' }],
    { duration: 320, easing: 'cubic-bezier(.22,1,.36,1)' }
  );
});
