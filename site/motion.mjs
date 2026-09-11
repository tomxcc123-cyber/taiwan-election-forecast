const page = document.querySelector('#page');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const revealSelector = [
  '.page-head',
  '.summary-band',
  '.map-desk',
  '.ratings',
  '.panel',
  '.filterbar',
  '.poll-meta',
  '.poll-row',
  '.check-list > div',
  '.prose section',
  '.narrative'
].join(',');

function reveal(root = page) {
  if (!root) return;
  const nodes = [...root.querySelectorAll(revealSelector)].filter(el => !el.dataset.motionReady);
  nodes.forEach((el, index) => {
    el.dataset.motionReady = '1';
    if (reduceMotion) return;
    el.classList.add('motion-reveal');
    el.style.setProperty('--motion-delay', `${Math.min(index * 42, 260)}ms`);
    requestAnimationFrame(() => el.classList.add('motion-visible'));
  });
}

function animateNumbers(root = page) {
  if (!root || reduceMotion) return;
  root.querySelectorAll('.big-prob,.numeral,.poll-values b,.poll-meta strong,.interval-row strong,output').forEach(el => {
    if (el.dataset.motionNumberReady) return;
    el.dataset.motionNumberReady = '1';
    el.classList.add('motion-number-pop');
    el.addEventListener('animationend', () => el.classList.remove('motion-number-pop'), { once: true });
  });
}

function animateChartPaths(root = page) {
  if (!root || reduceMotion) return;
  root.querySelectorAll('.chart path').forEach(path => {
    if (path.dataset.motionPathReady || path.getAttribute('fill') && path.getAttribute('fill') !== 'none') return;
    let length = 0;
    try { length = path.getTotalLength(); } catch { return; }
    if (!Number.isFinite(length) || length < 20) return;
    path.dataset.motionPathReady = '1';
    path.style.setProperty('--motion-path-length', `${Math.ceil(length)}`);
    path.classList.add('motion-chart-path');
  });
}

function runMotion(root = page) {
  reveal(root);
  animateNumbers(root);
  animateChartPaths(root);
}

function enterPage() {
  if (!page || reduceMotion) return;
  page.classList.remove('motion-page-enter');
  void page.offsetWidth;
  page.classList.add('motion-page-enter');
  page.addEventListener('animationend', () => page.classList.remove('motion-page-enter'), { once: true });
}

if (page) {
  const observer = new MutationObserver(mutations => {
    const meaningful = mutations.some(m => m.addedNodes.length || m.type === 'characterData');
    if (!meaningful) return;
    requestAnimationFrame(() => runMotion(page));
  });
  observer.observe(page, { childList: true, subtree: true, characterData: true });
  runMotion(page);

  // App views are rendered into #page. Detect a top-level replacement and animate it as a view transition.
  let previousSignature = page.firstElementChild?.className || '';
  new MutationObserver(() => {
    const signature = `${page.firstElementChild?.className || ''}|${page.querySelector('h1')?.textContent || ''}`;
    if (signature && signature !== previousSignature) {
      previousSignature = signature;
      enterPage();
    }
  }).observe(page, { childList: true, subtree: false });
}

// Re-run a small data-change animation when controls change the model output.
document.addEventListener('input', event => {
  if (!event.target.matches('input[type="range"],select')) return;
  requestAnimationFrame(() => {
    document.querySelectorAll('.big-prob,output,.interval-row strong').forEach(el => {
      if (reduceMotion) return;
      el.classList.remove('motion-number-pop');
      void el.offsetWidth;
      el.classList.add('motion-number-pop');
    });
  });
});
