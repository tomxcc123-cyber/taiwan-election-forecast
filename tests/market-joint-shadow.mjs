import assert from 'node:assert/strict';
import {jointMarketShadow} from '../site/market-joint-shadow.mjs';

const N=200,asOf='2026-10-28T05:00:00Z';
const counties=[];
for(let i=0;i<22;i++){
  const name=i===0?'台北市':i===1?'桃園市':'測試縣市'+i;
  const person0=i===0?'蔣萬安':i===1?'張善政':'甲'+i;
  const person1=i===0?'沈伯洋':i===1?'黃世杰':'乙'+i;
  const paired=i<2;
  const draws=Array.from({length:N},(_,j)=>paired&&j>=100?[200000,800000]:[800000,200000]);
  counties.push({name,race_id:'R'+i,
    candidates:[
      {candidate_id:'k'+i,name:person0,party:'KMT',probability:paired?.5:1},
      {candidate_id:'d'+i,name:person1,party:'DPP',probability:paired?.5:0}
    ],draws});
}
const model={counties,simulations:N,generated_at:asOf,model_version:'v5-test'};
const market={schema_version:1,checked_at:'2026-10-28T04:59:00Z',status:'ok',events:[
 {county:'台北市',slug:'taipei-mayor-election-winner-20260813125857100',
   quote_as_of:'2026-10-28T04:55:00Z',stale:false,volume_usd:100000,liquidity_usd:100000,
   outcomes:[{name:'Chiang Wan-an',probability:.75,spread:.01},{name:'Puma Shen',probability:.25,spread:.01}]},
 {county:'桃園市',slug:'taoyuan-mayor-election-winner-20260813125857300',
   quote_as_of:'2026-10-28T04:55:00Z',stale:false,volume_usd:100000,liquidity_usd:100000,
   outcomes:[{name:'Chang San-cheng',probability:.8,spread:.01},{name:'Huang Shih-chieh',probability:.2,spread:.01}]}
]};
const unweighted=jointMarketShadow(model,market,0);
const five=jointMarketShadow(model,market,0.05);
const ten=jointMarketShadow(model,market,0.10);
for(const result of [unweighted,five,ten]){
 assert.equal(result.available,true, result.reason);
 assert.equal(result.official_model_unchanged,true);
 assert.equal(result.diagnostics.eligible_count,2);
 assert.equal(result.diagnostics.simulations,N);
 assert.equal(result.national.reduce((s,x)=>s+x.mean,0),22);
 assert.equal(result.diagnostics.joint_gate_passed,true);
 assert.equal(result.national.find(x=>x.party==='KMT').histogram[21],0,
   'both linked races must win or lose together, never 21 seats');
}
assert.equal(unweighted.national.find(x=>x.party==='KMT').mean,21);
assert.ok(five.national.find(x=>x.party==='KMT').mean>21);
assert.ok(ten.national.find(x=>x.party==='KMT').mean>five.national.find(x=>x.party==='KMT').mean);
assert.ok(ten.diagnostics.effective_sample_fraction<=1.0001);
assert.equal(model.counties[0].candidates[0].probability,.5);
assert.equal(model.counties[0].draws[0][0],800000);
assert.deepEqual(unweighted.counties.map(x=>x.eligible_market).slice(0,3),[true,true,false]);
const fresh=structuredClone(market);
fresh.checked_at='2026-10-28T06:00:00Z';
assert.equal(jointMarketShadow(model,fresh,.05).available,false);
const thin=structuredClone(market);
thin.events.forEach(x=>x.liquidity_usd=50);
assert.equal(jointMarketShadow(model,thin,.05).available,false);
const broken=structuredClone(model);
broken.counties[0].draws.pop();
assert.equal(jointMarketShadow(broken,market,.05).available,false);
assert.equal(jointMarketShadow(model,market,.3).available,false);
console.log(JSON.stringify({passed:true,paired_races:2,shadow_only:true,baseline_KMT_22_races:21,
  joint_five_mean_KMT:five.national.find(x=>x.party==='KMT').mean,
  effective_samples:five.diagnostics.effective_sample_size}));
