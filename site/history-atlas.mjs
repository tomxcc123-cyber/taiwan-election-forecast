export const HISTORY_YEARS = Object.freeze([2014, 2018, 2022, 2026]);

const GROUP_COLORS = Object.freeze({
  KMT: '#2468d5',
  DPP: '#16845f',
  TPP: '#15939a',
  IND: '#7b8894',
  OTHER: '#9aa5ae',
});

const normalizeGroup = candidate => candidate?.legacy_bloc
  || (candidate?.party === 'KMT' || candidate?.party === 'DPP' || candidate?.party === 'TPP' ? candidate.party : null)
  || (candidate?.party ? 'OTHER' : 'IND');

const ranked = candidates => [...(candidates || [])].sort((a, b) => Number(b.share_pct ?? b.mean ?? 0) - Number(a.share_pct ?? a.mean ?? 0));

function partyShares(candidates, valueKey) {
  return candidates.reduce((shares, candidate) => {
    const key = normalizeGroup(candidate);
    shares[key] = (shares[key] || 0) + Number(candidate[valueKey] || 0);
    return shares;
  }, {});
}

function recordFromHistory(race, year) {
  const source = race.history_series?.find(item => Number(item.year) === Number(year));
  if (!source) return null;
  const candidates = ranked(source.candidates);
  const winner = candidates.find(candidate => candidate.winner) || candidates[0];
  const runner = candidates.find(candidate => candidate !== winner) || null;
  return {
    county: race.name,
    year: Number(year),
    kind: 'actual',
    source,
    winner,
    runner,
    winnerGroup: normalizeGroup(winner),
    winnerShare: Number(winner?.share_pct || 0),
    runnerShare: Number(runner?.share_pct || 0),
    margin: Math.max(0, Number(winner?.share_pct || 0) - Number(runner?.share_pct || 0)),
    turnout: Number(source.turnout_pct || 0),
    validVotes: Number(source.valid_votes || 0),
    partyShares: {...partyShares(candidates, 'share_pct'), ...(source.party_shares_pct || {})},
  };
}

function recordFromForecast(race, forecast) {
  if (!forecast) return null;
  const candidates = ranked(forecast.candidates);
  const winner = candidates[0];
  const runner = candidates[1] || null;
  return {
    county: race.name,
    year: 2026,
    kind: 'forecast',
    source: forecast,
    winner,
    runner,
    winnerGroup: normalizeGroup(winner),
    winnerShare: Number(winner?.mean || 0),
    runnerShare: Number(runner?.mean || 0),
    margin: Math.max(0, Number(winner?.mean || 0) - Number(runner?.mean || 0)),
    turnout: null,
    validVotes: null,
    probability: Number(winner?.probability || 0),
    partyShares: partyShares(candidates, 'mean'),
  };
}

export function historyRecord(race, forecast, year) {
  return Number(year) === 2026 ? recordFromForecast(race, forecast) : recordFromHistory(race, year);
}

export function twoPartyMargin(record) {
  if (!record) return null;
  const dpp = Number(record.partyShares?.DPP || 0);
  const kmt = Number(record.partyShares?.KMT || 0);
  return dpp > 0 && kmt > 0 ? dpp - kmt : null;
}

export function previousHistoryYear(year) {
  const index = HISTORY_YEARS.indexOf(Number(year));
  return index > 0 ? HISTORY_YEARS[index - 1] : null;
}

export function nextHistoryYear(year) {
  const index = HISTORY_YEARS.indexOf(Number(year));
  return HISTORY_YEARS[(index + 1 + HISTORY_YEARS.length) % HISTORY_YEARS.length];
}

export function buildHistoryFrame(counties, forecastCounties, year, metric = 'result') {
  const forecastByName = new Map(forecastCounties.map(race => [race.name, race]));
  const selectedYear = HISTORY_YEARS.includes(Number(year)) ? Number(year) : 2022;
  const previousYear = previousHistoryYear(selectedYear);
  const records = {};
  const overrides = {};

  for (const race of counties) {
    const forecast = forecastByName.get(race.name);
    const record = historyRecord(race, forecast, selectedYear);
    if (!record) continue;
    const previous = previousYear === null ? null : historyRecord(race, forecast, previousYear);
    const currentMargin = twoPartyMargin(record);
    const previousMargin = twoPartyMargin(previous);
    const swing = currentMargin === null || previousMargin === null ? null : currentMargin - previousMargin;
    const swingGroup = swing === null ? 'OTHER' : swing >= 0 ? 'DPP' : 'KMT';
    const value = metric === 'swing'
      ? (swing === null ? '主要政黨配對不完整' : `${swingGroup} ${swing >= 0 ? '+' : '−'}${Math.abs(swing).toFixed(1)}`)
      : `${record.winner?.name || '無資料'} +${record.margin.toFixed(1)}`;
    const strength = metric === 'swing' ? Math.abs(swing || 0) : record.margin;
    const party = metric === 'swing' ? swingGroup : record.winnerGroup;
    records[race.name] = {...record, previous, previousYear, swing};
    overrides[race.name] = {
      fill: GROUP_COLORS[party] || GROUP_COLORS.OTHER,
      opacity: metric === 'swing'
        ? (swing === null ? 0.22 : Math.min(0.9, 0.34 + Math.abs(swing) / 24))
        : Math.min(0.9, 0.54 + record.margin / 48),
      party,
      leader: metric === 'swing' ? `相較 ${previousYear || '前次'}` : record.winner?.name || '無資料',
      value,
      evidence: record.kind === 'actual' ? 'CEC' : 'MODEL',
      elevation: 160 + Math.round(Math.min(1, strength / (metric === 'swing' ? 18 : 28)) * 1080),
    };
  }

  return {year: selectedYear, metric, previousYear, records, overrides};
}
