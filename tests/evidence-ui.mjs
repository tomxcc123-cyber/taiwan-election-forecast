import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PRESETS,presetState,comparisonSnapshot,competition,probabilityLabel,updatesPage} from '../site/evidence-ui.mjs';
import {analyze,adjust} from '../site/candidate-engine.mjs';
const data=JSON.parse(fs.readFileSync(new URL('../dist/candidate-model.json',import.meta.url),'utf8'));
const base=analyze(data),r=data.counties.find(r=>r.candidates.length>=3),ids=r.candidates.map(c=>c.candidate_id);
const original=JSON.stringify(data),selection={boostId:ids[0],from:ids[0],to:ids[1],boost:12,flow:80,tactical:50};
for(const p of PRESETS){
 const state=presetState(data,r.name,p.id,selection),out=analyze(data,state);
 assert.deepEqual(out,analyze(data,state));
 assert.equal(Object.keys(state.edits).length,1);assert.deepEqual(state.constraints,{});
 assert.equal(out.originalSimulations,base.originalSimulations);
 assert.ok(Math.abs(out.summary.reduce((s,x)=>s+x.mean,0)-22)<1e-9);
 for(const row of r.draws.slice(0,50)){const v=adjust(row,r,state.edits[r.race_id]);assert.ok(v.every(x=>x>=0&&x<=100));assert.ok(Math.abs(v.reduce((s,x)=>s+x,0)-100)<1e-8);}
}
assert.equal(JSON.stringify(data),original);
assert.throws(()=>presetState(data,r.name,'flow-low',{...selection,to:ids[0]}));
assert.throws(()=>presetState(data,r.name,'gain',{...selection,boostId:'unknown'}));
assert.throws(()=>presetState(data,r.name,'unknown',selection));
const actual=base.counties.find(r=>r.name==='新竹市');assert.ok(actual.quality.evidence.support_proxy_evidence.length);
const risk={...actual,quality:{evidence:{grade:'D'}}};assert.equal(competition(risk),'模型缺項');
assert.ok(probabilityLabel(risk,risk.candidates[0]).includes('暫不評級'));
const noHistory={...data,tracking:{snapshots:[],notice:''}};
assert.equal(comparisonSnapshot(noHistory,'7'),null);assert.ok(updatesPage(noHistory,'7').includes('不補造'));
const earlier={generated_at:'2026-09-08T06:00:00Z',model_version:'earlier',poll_ids:[],counties:[]};
assert.equal(comparisonSnapshot({...data,tracking:{snapshots:[earlier]}},'version'),earlier);
console.log('Evidence UI: six deterministic presets, conservation, source grades and missing-history states passed');
