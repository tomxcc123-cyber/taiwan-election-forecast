import assert from 'node:assert/strict';
import fs from 'node:fs';
import {validate,analyze,adjust,cleanState} from '../site/candidate-engine.mjs';
const data=validate(JSON.parse(fs.readFileSync(new URL('../dist/candidate-model.json',import.meta.url),'utf8'))),base=analyze(data);
assert.equal(base.counties.length,22);assert.equal(base.counties.reduce((n,r)=>n+r.candidates.length,0),81);
assert.deepEqual(analyze(data),base);
assert.ok(Math.abs(base.summary.reduce((n,s)=>n+s.mean,0)-22)<1e-8);
for(const r of base.counties){assert.ok(Math.abs(r.candidates.reduce((n,c)=>n+c.mean,0)-100)<1e-8);assert.ok(Math.abs(r.candidates.reduce((n,c)=>n+c.probability,0)-1)<1e-8);}
const race=data.counties.find(r=>r.name==='台北市'),ids=race.candidates.map(c=>c.candidate_id);
const edit={boostId:ids[0],boost:10,from:ids[1],to:ids[0],flow:50,tactical:30};
const result=analyze(data,{county:race.name,edits:{[race.race_id]:edit}});
assert.notDeepEqual(result.counties.find(r=>r.race_id===race.race_id).candidates,base.counties.find(r=>r.race_id===race.race_id).candidates);
for(const row of race.draws.slice(0,30)){const next=adjust(row,race,edit);assert.ok(next.every(x=>x>=0));assert.ok(Math.abs(next.reduce((a,b)=>a+b,0)-100)<1e-8);}
const winner=base.counties.find(r=>r.race_id===race.race_id).candidates.toSorted((a,b)=>b.probability-a.probability)[0].candidate_id;
const conditioned=analyze(data,{constraints:{[race.race_id]:{mode:'condition',candidate:winner}}});
assert.ok(conditioned.simulations>=100&&conditioned.simulations<=data.simulations);
assert.equal(conditioned.counties.find(r=>r.race_id===race.race_id).candidates.find(c=>c.candidate_id===winner).probability,1);
const locked=analyze(data,{constraints:{[race.race_id]:{mode:'lock',candidate:ids[0]}}});assert.equal(locked.simulations,data.simulations);
assert.equal(locked.counties.find(r=>r.race_id===race.race_id).candidates[0].probability,1);
const bad=structuredClone(data);bad.counties[0].draws[0][0]=-1;assert.throws(()=>validate(bad));
assert.deepEqual(cleanState({constraints:{evil:{mode:'lock',candidate:'bad'}}},data).constraints,{});
console.log('PASS: 81 candidates, 22 seats, conservation, reproducibility, shifts, flows, strategic scenarios, true conditioning and display-only locks');
