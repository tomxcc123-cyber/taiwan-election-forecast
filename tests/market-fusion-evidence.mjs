import assert from 'node:assert/strict';
import {pairedSnapshot,upsertHistory,appendArchive} from '../scripts/archive_market_fusion.mjs';
import {evaluate,scoreDistribution,validateOfficialResults} from '../scripts/evaluate_market_fusion.mjs';

const ASOF='2026-11-21T05:00:00Z',MARKET_CHECK='2026-11-21T04:56:00Z';
const races=[{name:'台北市',race_id:'TPE',candidates:[
  {candidate_id:'taipei-chiang',name:'蔣萬安',probability:.6},
  {candidate_id:'taipei-shen',name:'沈伯洋',probability:.4}
]}];
for(let i=1;i<22;i++)races.push({name:'sample-county-'+i,race_id:'S'+i,
  candidates:[{candidate_id:'x'+i,name:'候選甲',probability:.51},{candidate_id:'y'+i,name:'候選乙',probability:.49}]});
const model={fingerprint:'sha-example-001',model_version:'v5-test',generated_at:ASOF,counties:races};
const markets={schema_version:1,checked_at:MARKET_CHECK,status:'ok',registry_count:1,events:[{
  slug:'taipei-mayor-election-winner-20260813125857100',county:'台北市',
  source_url:'https://polymarket.com/event/taipei-mayor-election-winner-20260813125857100',
  quote_as_of:'2026-11-21T04:50:00Z',retrieved_at:MARKET_CHECK,
  stale:false,liquidity_usd:200000,volume_usd:1000000,outcomes:[
    {name:'Chiang Wan-an',market_id:'c1',probability:.67,spread:.01},
    {name:'Puma Shen',market_id:'c2',probability:.33,spread:.01}
  ]
}]};
const snap=pairedSnapshot(model,markets);
assert.equal(snap.races.length,22);
assert.equal(snap.included_races,1);
assert.equal(snap.excluded_races,21);
assert.equal(snap.taipei_day,'2026-11-21');
assert.equal(snap.provenance.market_checked_at,MARKET_CHECK);
const taipei=snap.races.find(x=>x.county==='台北市');
assert.equal(taipei.candidates[0].probability,.6);
assert.equal(taipei.candidates[0].market_yes,.67);
assert.equal(taipei.candidates[0].market_aligned,.67);
assert.ok(taipei.candidates[0].fused_10>.6);
assert.equal(races[0].candidates[0].probability,.6);
const one=upsertHistory({},snap);
assert.equal(one.snapshots.length,1);
const copied=upsertHistory(one,snap);
assert.equal(copied.snapshots.length,1);
const next=structuredClone(model);
next.generated_at='2026-11-21T11:00:00Z';
next.fingerprint='sha-example-002';
const newerMarket=structuredClone(markets);
newerMarket.checked_at='2026-11-21T10:55:00Z';
newerMarket.events[0].quote_as_of='2026-11-21T10:50:00Z';
const newer=appendArchive(next,newerMarket,one);
assert.equal(newer.snapshots.length,1);
assert.equal(newer.snapshots[0].as_of,next.generated_at);
const oldAgain=upsertHistory(newer,snap);
assert.equal(oldAgain.snapshots[0].as_of,next.generated_at);
const contradictory=structuredClone(newer.snapshots[0]);contradictory.source_digest='modified';
assert.throws(()=>upsertHistory(newer,contradictory),/Conflicting/);
const mismatchedTime=structuredClone(markets);
mismatchedTime.checked_at='2026-11-21T06:00:00Z';
assert.throws(()=>pairedSnapshot(model,mismatchedTime),/timestamps/);
const missing=structuredClone(markets);
missing.events=[];
assert.equal(pairedSnapshot(model,missing).included_races,0);

assert.deepEqual(scoreDistribution(taipei.candidates,'taipei-chiang','probability').brier,.32000000000000006);
assert.ok(scoreDistribution(taipei.candidates,'taipei-chiang','market_aligned').brier<
          scoreDistribution(taipei.candidates,'taipei-chiang','probability').brier);
const finals={schema_version:1,election_date:'2026-11-28',status:'official_final',races:[
  {county:'台北市',winner_candidate_id:'taipei-chiang',official_source_url:'https://db.cec.gov.tw/ElecTable/Election?testcase=fixture'}
]};
validateOfficialResults(finals);
const scored=evaluate(one,finals);
const row7=scored.coverage.find(x=>x.horizon_days===7);
assert.equal(row7.evaluated_counties,1);
assert.equal(scored.coverage.find(x=>x.horizon_days===1).evaluated_counties,0);
assert.equal(scored.summary.find(x=>x.horizon_days===7).n,1);
assert.equal(scored.rows.filter(x=>x.horizon_days===7).length,4);
assert.ok(scored.summary.find(x=>x.horizon_days===7).scores.market.brier<
          scored.summary.find(x=>x.horizon_days===7).scores.baseline.brier);
assert.equal(scored.no_p_value_claims,true);
const tooLate=structuredClone(one);
tooLate.snapshots[0].as_of='2026-11-28T08:10:00Z';
assert.equal(evaluate(tooLate,finals).summary.every(x=>x.n===0),true);
const invalidFinal=structuredClone(finals);invalidFinal.status='provisional';
assert.throws(()=>evaluate(one,invalidFinal),/Only.*official/);
const badDomain=structuredClone(finals);badDomain.races[0].official_source_url='https://fake-cec.example.com/';
assert.throws(()=>evaluate(one,badDomain),/Unverified/);
const badDate=structuredClone(finals);badDate.election_date='2026-10-28';
assert.throws(()=>evaluate(one,badDate),/Only.*official/);
console.log(JSON.stringify({passed:true,archives:one.snapshots.length,
  included_races:snap.included_races,evaluation_fixture_only:true}));
