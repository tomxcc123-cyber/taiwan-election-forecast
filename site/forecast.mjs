export const LABELS = ['藍白情境', '綠營情境', '其他整合情境'];
export const COLORS = ['#2864c8', '#14805e', '#737b89'];
export function normalize(a) {
  if (a.some(x => !Number.isFinite(x) || x < 0) || !a.some(x => x > 0)) throw Error('Invalid shares');
  const total = a.reduce((x, y) => x + y, 0);
  return a.map(x => x / total * 100);
}
export function normalGenerator(seed) {
  let s = seed >>> 0;
  const uniform = () => {s += 0x6D2B79F5; let t = s; t = Math.imul(t ^ t >>> 15, t | 1); t ^= t + Math.imul(t ^ t >>> 7, t | 61); return ((t ^ t >>> 14) >>> 0) / 4294967296;};
  return () => Math.sqrt(-2 * Math.log(Math.max(1e-12, uniform()))) * Math.cos(2 * Math.PI * uniform());
}
export function quantile(sorted, p) {
  const h = (sorted.length - 1) * p, lo = Math.floor(h);
  return sorted[lo] + (sorted[Math.ceil(h)] - sorted[lo]) * (h - lo);
}
const alr = a => [Math.log(Math.max(.25, a[0]) / Math.max(.25, a[1])), Math.log(Math.max(.25, a[2]) / Math.max(.25, a[1]))];
const softmax = x => {const a = [x[0], 0, x[1]], m = Math.max(...a); return normalize(a.map(v => Math.exp(v - m)));};
const day = s => Date.parse(s.slice(0, 10) + 'T00:00:00Z') / 86400000;
// Symmetric 2x2 matrices use [a, b, d] for [[a,b],[b,d]].
const inverse = ([a,b,d]) => {const det=a*d-b*b;if(det<=0)throw Error('Invalid covariance');return [d/det,-b/det,a/det];};
const multiply = ([a,b,d],[x,y]) => [a*x+b*y,b*x+d*y];
const numeric = (x, fallback, min, max) => typeof x === 'number' && Number.isFinite(x) ? Math.max(min, Math.min(max, x)) : fallback;
export function cleanState(input = {}, counties = []) {
  const county = counties.includes(input.county) ? input.county : counties[0];
  const flips = {};
  for (const name of counties) if (Number.isInteger(input.flips?.[name]) && input.flips[name] >= 0 && input.flips[name] <= 2) flips[name] = input.flips[name];
  return {county, swing: numeric(input.swing, 0, -15, 15), flow: numeric(input.flow, 0, -100, 100),
    tactical: numeric(input.tactical, 0, 0, 100), flips};
}
export function validateFeed(feed, names, asOf) {
  if (feed?.schema_version !== 1 || !Array.isArray(feed.records) || !Array.isArray(feed.polls)) throw Error('民調資料格式不符');
  const ids = new Set();
  for (const p of feed.polls) {
    if (ids.has(p.id) || !names.includes(p.county) || typeof p.source !== 'string' || !p.source ||
        !/^\d{4}-\d{2}-\d{2}$/.test(p.date || '') || !Number.isFinite(day(p.date)) || day(p.date) > day(asOf) ||
        !Number.isFinite(p.sample_n) || p.sample_n < 100 ||
        ['blue', 'dpp', 'third', 'other', 'undecided'].some(k => !Number.isFinite(p[k]) || p[k] < 0 || p[k] > 100) ||
        Math.abs(['blue', 'dpp', 'third', 'other', 'undecided'].reduce((s,k)=>s+p[k],0)-100)>3 ||
        !feed.records.some(r => r.id === p.id && r.model_eligible === true)) throw Error('民調輸入未通過校驗');
    ids.add(p.id);
  }
  return feed;
}
export function posterior(county, feed, data) {
  const a = data.assumptions;
  const prior = alr(normalize(county.baseline));
  const precision = [1 / a.prior_sd ** 2, 0, 1 / a.prior_sd ** 2];
  const numerator = multiply(precision, prior);
  // One latest report per institute prevents repeated releases from multiplying information.
  const latest = new Map();
  for (const p of feed.polls) if (p.county === county.name && p.date > data.baseline_date && p.date <= data.generated_at.slice(0,10)) {
    if (!latest.has(p.source) || p.date > latest.get(p.source).date) latest.set(p.source, p);
  }
  const inputs = [];
  for (const p of latest.values()) {
    const decided = p.blue + p.dpp + p.third + p.other;
    if (decided < 20) continue;
    const q = normalize([p.blue, p.dpp, p.third + p.other]);
    const z = alr(q);
    const age = Math.max(0, day(data.generated_at) - day(p.date));
    const n = p.sample_n * decided / 100 / a.design_effect;
    const decay = Math.pow(2, -age / a.half_life_days);
    const reference = 1 / (n * Math.max(.005,q[1]/100));
    const extra = a.house_sd ** 2 + (p.undecided / 100 * .4) ** 2;
    // Both log-ratios share the DPP denominator, so their sampling errors covary.
    const covariance = [reference+1/(n*Math.max(.005,q[0]/100))+extra,
      reference, reference+1/(n*Math.max(.005,q[2]/100))+extra];
    const weight=inverse(covariance).map(v=>v*decay), contribution=multiply(weight,z);
    weight.forEach((v,j)=>precision[j]+=v);contribution.forEach((v,j)=>numerator[j]+=v);
    inputs.push({id: p.id, source: p.source, date: p.date, effective_n: n, decay});
  }
  const covariance=inverse(precision);
  return {mean: multiply(covariance,numerator), covariance, sd:[Math.sqrt(covariance[0]),Math.sqrt(covariance[2])], inputs};
}
export function scenarioShares(shares, state) {
  let a = shares.slice();
  // Explicit transfers conserve votes; percentages here are assumptions, not causal estimates.
  const transfer = Math.min(state.swing >= 0 ? a[1] : a[0], Math.abs(state.swing));
  a[0] += state.swing >= 0 ? transfer : -transfer; a[1] -= state.swing >= 0 ? transfer : -transfer;
  const third = a[2] * Math.abs(state.flow) / 100;
  a[state.flow >= 0 ? 0 : 1] += third; a[2] -= third;
  const order = [0,1,2].sort((i,j)=>a[j]-a[i]);
  const tactical = a[order[2]] * state.tactical / 100;
  a[order[2]] -= tactical; a[order[1]] += tactical;
  return normalize(a);
}
export function simulate(data, feed, input = {}) {
  validateFeed(feed, data.counties.map(c=>c.name), data.generated_at);
  const state = cleanState(input, data.counties.map(c=>c.name)), a = data.assumptions;
  const normal = normalGenerator(a.seed), count = a.simulations;
  const regions = [...new Set(data.counties.map(c=>c.region))];
  const horizon = Math.max(0, Math.min(180, day('2026-11-28') - day(data.generated_at)));
  const staleDays = Math.max(0, day(data.generated_at) - day(data.baseline_date));
  const posteriors = data.counties.map(c=>posterior(c,feed,data));
  const results = data.counties.map((c,i)=>({...c, draws:[[],[],[]], wins:[0,0,0], inputs:posteriors[i].inputs}));
  const seats = [[],[],[]];
  for(let n=0;n<count;n++) {
    const national = [normal()*a.national_sd, normal()*a.national_sd];
    const regional = Object.fromEntries(regions.map(r=>[r,[normal()*a.regional_sd,normal()*a.regional_sd]]));
    const totals = [0,0,0];
    results.forEach((c,i)=>{
      const p = posteriors[i];
      const movement = a.future_variance_per_day * horizon + (p.inputs.length ? 0 : Math.min(staleDays,180)*.0003);
      const l00=Math.sqrt(p.covariance[0]+movement), l10=p.covariance[1]/l00;
      const l11=Math.sqrt(Math.max(0,p.covariance[2]+movement-l10*l10));
      const u=normal(),v=normal(),local=[l00*u,l10*u+l11*v];
      const z = p.mean.map((v,j)=>v+national[j]+regional[c.region][j]+local[j]);
      const shares = scenarioShares(softmax(z),state);
      shares.forEach((v,k)=>c.draws[k].push(v));
      const winner = Object.hasOwn(state.flips,c.name) ? state.flips[c.name] : shares.indexOf(Math.max(...shares));
      c.wins[winner]++;totals[winner]++;
    });
    totals.forEach((v,k)=>seats[k].push(v));
  }
  for(const c of results){
    c.shares = c.draws.map(d=>{d.sort((x,y)=>x-y);return {mean:d.reduce((x,y)=>x+y,0)/count,p05:quantile(d,.05),median:quantile(d,.5),p95:quantile(d,.95)};});
    c.probability = c.wins.map(x=>x/count);c.winner=c.wins.indexOf(Math.max(...c.wins));delete c.draws;
  }
  const summary = seats.map(d=>{d.sort((x,y)=>x-y);return {mean:d.reduce((x,y)=>x+y,0)/count,p05:quantile(d,.05),p95:quantile(d,.95),majority:d.filter(n=>n>=12).length/count,histogram:Array.from({length:23},(_,i)=>d.filter(n=>n===i).length/count)};});
  return {counties:results,summary,simulations:count,state,model_version:data.model_version,seed:a.seed};
}
