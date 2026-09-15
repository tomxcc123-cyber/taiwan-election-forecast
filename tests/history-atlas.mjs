import assert from 'node:assert/strict';
import {HISTORY_YEARS,buildHistoryFrame,historyRecord,nextHistoryYear,previousHistoryYear,twoPartyMargin} from '../site/history-atlas.mjs';

const race={name:'彰化縣',history_series:[
  {year:2018,turnout_pct:70,valid_votes:100,candidates:[{name:'甲',party:'KMT',share_pct:53,winner:true},{name:'乙',party:'DPP',share_pct:40,winner:false}],party_shares_pct:{KMT:53,DPP:40}},
  {year:2022,turnout_pct:65,valid_votes:90,candidates:[{name:'甲',party:'KMT',share_pct:57,winner:true},{name:'乙',party:'DPP',share_pct:42,winner:false}],party_shares_pct:{KMT:57,DPP:42}},
]};
const forecast={name:'彰化縣',candidates:[{name:'乙',party:'DPP',mean:51,probability:.58},{name:'甲',party:'KMT',mean:48,probability:.42}]};

assert.deepEqual(HISTORY_YEARS,[2014,2018,2022,2026]);
assert.equal(previousHistoryYear(2022),2018);
assert.equal(previousHistoryYear(2014),null);
assert.equal(nextHistoryYear(2026),2014);
assert.equal(historyRecord(race,forecast,2022).winner.name,'甲');
assert.equal(historyRecord(race,forecast,2026).kind,'forecast');
assert.equal(twoPartyMargin(historyRecord(race,forecast,2022)),-15);
const resultFrame=buildHistoryFrame([race],[forecast],2022,'result');
assert.equal(resultFrame.overrides['彰化縣'].party,'KMT');
assert.equal(resultFrame.records['彰化縣'].swing,-2);
const swingFrame=buildHistoryFrame([race],[forecast],2026,'swing');
assert.equal(swingFrame.records['彰化縣'].swing,18);
assert.equal(swingFrame.overrides['彰化縣'].party,'DPP');
assert.match(swingFrame.overrides['彰化縣'].value,/DPP \+18\.0/);
console.log(JSON.stringify({passed:true,years:HISTORY_YEARS.length}));
