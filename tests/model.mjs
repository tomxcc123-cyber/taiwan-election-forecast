import assert from 'node:assert/strict';
import fs from 'node:fs';
import {simulate,normalize,cleanState,scenarioShares,posterior,validateFeed} from '../site/forecast.mjs';
const data=JSON.parse(fs.readFileSync(new URL('../dist/model-data.json',import.meta.url)));
const feed=JSON.parse(fs.readFileSync(new URL('../dist/polls.json',import.meta.url)));
const r=simulate(data,feed), r2=simulate(data,feed);
assert.deepEqual(r,r2,'fixed seed and input reproduce exactly');
assert.equal(r.counties.length,22);
for(const c of r.counties){
 assert.ok(Math.abs(c.probability.reduce((a,b)=>a+b,0)-1)<1e-9);
 assert.ok(Math.abs(c.shares.reduce((a,b)=>a+b.mean,0)-100)<1e-8);
 for(const s of c.shares)assert.ok(s.p05>=0&&s.p95<=100&&s.p05<=s.median&&s.median<=s.p95);
}
assert.ok(Math.abs(r.summary.reduce((a,s)=>a+s.mean,0)-22)<1e-9);
for(const s of r.summary){assert.ok(Math.abs(s.histogram.reduce((a,b)=>a+b,0)-1)<1e-9);assert.ok(Math.abs(s.histogram.slice(12).reduce((a,b)=>a+b,0)-s.majority)<1e-9);}
for(const flow of [-100,0,100])for(const swing of [-15,0,15])for(const tactical of [0,100]){const a=scenarioShares([1,98,1],{flow,swing,tactical});assert.ok(a.every(x=>x>=0));assert.ok(Math.abs(a.reduce((x,y)=>x+y,0)-100)<1e-8);}
assert.notDeepEqual(simulate(data,feed,{flow:50}).summary,r.summary);
assert.notDeepEqual(simulate(data,feed,{tactical:50}).summary,r.summary);
const locked=simulate(data,feed,{flips:{[data.counties[0].name]:1}});
assert.equal(locked.counties[0].probability[1],1);
const all=simulate(data,feed,{flips:Object.fromEntries(data.counties.map(c=>[c.name,0]))});
assert.equal(all.summary[0].mean,22);assert.equal(all.summary[0].majority,1);
const independent=structuredClone(data);independent.assumptions.national_sd=0;independent.assumptions.regional_sd=0;
assert.notDeepEqual(simulate(independent,feed).summary,r.summary,'shared errors affect distribution');
assert.equal(cleanState({swing:Infinity,tactical:-50,flips:{bad:0}},['台北市']).swing,0);
assert.throws(()=>normalize([-1,2,3]));
const mock=structuredClone(feed),record=structuredClone(feed.records[0]);
record.id='synthetic-test';record.date='2026-08-26';record.model_eligible=true;
mock.records.push(record);mock.polls=[{id:record.id,county:record.county,source:record.source,date:record.date,sample_n:900,blue:40,dpp:49,third:0,other:0,undecided:11}];
validateFeed(mock,data.counties.map(c=>c.name),data.generated_at);
const target=data.counties.find(c=>c.name===record.county);
assert.ok(target,'synthetic poll county must exist in model data');
const before=posterior(target,feed,data),after=posterior(target,mock,data);
assert.notDeepEqual(before.mean,after.mean);assert.ok(after.sd[0]<before.sd[0]);
const baseRace=r.counties.find(c=>c.name===record.county),mockRace=simulate(data,mock).counties.find(c=>c.name===record.county);
assert.ok(baseRace&&mockRace,'synthetic poll county must exist in simulation output');
assert.notDeepEqual(mockRace.shares,baseRace.shares);
mock.polls.push(structuredClone(mock.polls[0]));assert.throws(()=>simulate(data,mock));mock.polls.pop();
mock.polls[0].blue=400;assert.throws(()=>simulate(data,mock));
console.log('PASS: 22 counties, normalization, reproducibility, intervals, joint seats, all scenario controls, locks, correlation, poll posterior, invalid data rejection');
