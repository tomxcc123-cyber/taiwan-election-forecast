import assert from 'node:assert/strict';
import {marketFusion,MARKET_FUSION_WEIGHTS} from '../site/market-fusion.mjs';

const now='2026-10-28T05:05:00.000Z';
const model={model_version:'v5-research-test',counties:[{
  name:'台北市',candidates:[
    {candidate_id:'c1',name:'蔣萬安',probability:.6,mean:43.4},
    {candidate_id:'c2',name:'沈伯洋',probability:.4,mean:43.0},
    {candidate_id:'c3',name:'郭璽',probability:0,mean:2.0}]
}]};
const event={county:'台北市',slug:'taipei-mayor-election-winner-20260813125857100',
  quote_as_of:'2026-10-28T05:00:00.000Z',volume_usd:250000,liquidity_usd:30000,stale:false,
  outcomes:[
    {name:'Chiang Wan-an',probability:.67,spread:.01},
    {name:'Puma Shen',probability:.325,spread:.02},
    {name:'Kuo Hsi',probability:.005,spread:null}
  ]};
const copy=x=>structuredClone(x);
const zero=marketFusion(model,event,0,now);
const low=marketFusion(model,event,.05,now);
const high=marketFusion(model,event,.10,now);
assert.equal(zero.eligible,true);
assert.equal(low.eligible,true);
assert.equal(high.eligible,true);
assert.equal(zero.probabilities.find(x=>x.name==='蔣萬安').fused,.6);
assert.ok(low.probabilities.find(x=>x.name==='蔣萬安').fused>.6);
assert.ok(high.probabilities.find(x=>x.name==='蔣萬安').fused>low.probabilities.find(x=>x.name==='蔣萬安').fused);
assert.ok(Math.abs(high.probabilities.reduce((s,x)=>s+x.fused,0)-1)<1e-10);
assert.equal(model.counties[0].candidates[0].probability,.6);
assert.equal(model.counties[0].candidates[0].mean,43.4);
assert.deepEqual(MARKET_FUSION_WEIGHTS,[0,.05,.10]);
assert.equal(marketFusion(model,event,.99,now).eligible,false);
const stale=copy(event);stale.stale=true;
assert.equal(marketFusion(model,stale,.1,now).eligible,false);
const tooOld=copy(event);tooOld.quote_as_of='2026-10-27T10:00:00Z';
assert.equal(marketFusion(model,tooOld,.1,now).eligible,false);
const thin=copy(event);thin.liquidity_usd=15;
assert.equal(marketFusion(model,thin,.1,now).eligible,false);
const mismatched=copy(event);mismatched.outcomes[0].name='Unregistered Famous Person';
assert.equal(marketFusion(model,mismatched,.1,now).eligible,false);
const distorted=copy(event);distorted.outcomes[0].probability=.91;
assert.equal(marketFusion(model,distorted,.1,now).eligible,false);
const spread=copy(event);spread.outcomes[0].spread=.35;
assert.equal(marketFusion(model,spread,.1,now).eligible,false);
const missing=copy(event);missing.outcomes[0].spread=null;
assert.equal(marketFusion(model,missing,.1,now).eligible,false);
const twin=copy(event);twin.outcomes[1].name='Chiang Wan-an';
assert.equal(marketFusion(model,twin,.1,now).eligible,false);
console.log(JSON.stringify({passed:true,weights:MARKET_FUSION_WEIGHTS,local_only:true,unchanged_mean:model.counties[0].candidates[0].mean}));
