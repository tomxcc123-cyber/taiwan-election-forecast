import {ruleFields,applyMatrix,applyStrategy} from './scenario-rules.mjs';
export const GROUPS=['KMT','DPP','TPP','IND','OTHER'];
export const NAMES={KMT:'國民黨',DPP:'民進黨',TPP:'民眾黨',IND:'無黨籍',OTHER:'其他政黨'};
export const COLORS={KMT:'#2864c8',DPP:'#14805e',TPP:'#087f8c',IND:'#737b89',OTHER:'#a34c79'};
export const group=c=>['KMT','DPP','TPP'].includes(c.party)?c.party:c.party===null?'IND':'OTHER';
const sum=a=>a.reduce((x,y)=>x+y,0);
const bound=(x,min,max)=>typeof x==='number'&&Number.isFinite(x)?Math.min(max,Math.max(min,x)):0;
export function validate(data){
 if(data?.schema_version!==2||!Array.isArray(data.counties)||data.counties.length!==22||!Number.isInteger(data.simulations)||data.simulations<100)throw Error('候選人模型資料格式錯誤');
 const ids=new Set(),races=new Set();
 for(const r of data.counties){if(races.has(r.race_id)||!r.candidates.length||r.draws.length!==data.simulations)throw Error('候選名單或抽樣數錯誤');races.add(r.race_id);
  for(const c of r.candidates){if(ids.has(c.candidate_id)||typeof c.name!=='string')throw Error('候選人識別碼錯誤');ids.add(c.candidate_id);}
  for(const row of r.draws)if(row.length!==r.candidates.length||row.some(x=>!Number.isInteger(x)||x<0||x>1000000)||sum(row)<=0)throw Error('抽樣資料未通過校驗');
 }
 return data;
}
export function cleanState(input,data){
 const s={county:data.counties.some(r=>r.name===input?.county)?input.county:data.counties[0].name,edits:{},constraints:{}};
 for(const r of data.counties){const ids=r.candidates.map(c=>c.candidate_id),e=input?.edits?.[r.race_id],c=input?.constraints?.[r.race_id];
  if(e){const edit={boostId:ids.includes(e.boostId)?e.boostId:ids[0],boost:bound(e.boost,-20,20),from:ids.includes(e.from)?e.from:ids[0],to:ids.includes(e.to)?e.to:ids[1]||ids[0],flow:bound(e.flow,0,100),tactical:bound(e.tactical,0,100),...ruleFields(e,ids)};s.edits[r.race_id]=edit;}
  if(c&&ids.includes(c.candidate)&&['lock','condition'].includes(c.mode))s.constraints[r.race_id]={candidate:c.candidate,mode:c.mode};
 }
 return s;
}
export function adjust(row,race,edit){
 let a=row.map(x=>x/sum(row)*100);if(!edit)return a;const original=[...a];
 const ids=race.candidates.map(c=>c.candidate_id),j=ids.indexOf(edit.boostId);
 if(a.length>1){const change=Math.max(-a[j],Math.min(100-a[j],edit.boost)),others=100-a[j];
  a.forEach((v,k)=>{if(k!==j)a[k]=others>1e-9?v-change*v/others:-change/(a.length-1);});a[j]+=change;
 }
 const from=ids.indexOf(edit.from),to=ids.indexOf(edit.to);
 if(from!==to){const flow=a[from]*edit.flow/100;a[from]-=flow;a[to]+=flow;}
 a=applyMatrix(original,a,ids,edit.matrix,edit.matrixMode);
 a=applyStrategy(a,race,edit);
 return a.map(v=>Math.max(0,v)/sum(a)*100);
}
const quantile=(a,p)=>{const t=(a.length-1)*p,i=Math.floor(t);return a[i]+(a[Math.ceil(t)]-a[i])*(t-i);};
export function analyze(data,input={}){
 const state=cleanState(input,data),transformed={},winners={};
 for(const race of data.counties){const rows=race.draws.map(row=>adjust(row,race,state.edits[race.race_id]));transformed[race.race_id]=rows;winners[race.race_id]=rows.map(a=>a.indexOf(Math.max(...a)));}
 const keep=Array.from({length:data.simulations},(_,i)=>i).filter(i=>data.counties.every(r=>{const c=state.constraints[r.race_id];return !c||c.mode!=='condition'||r.candidates[winners[r.race_id][i]].candidate_id===c.candidate;}));
 if(keep.length<100)throw Error(`條件過於稀少：僅保留 ${keep.length} 次模擬，至少需要100次。請減少勝選條件。`);
 const seats=Object.fromEntries(GROUPS.map(g=>[g,Array(keep.length).fill(0)]));
 const counties=data.counties.map(r=>{
  const wins=Array(r.candidates.length).fill(0),constraint=state.constraints[r.race_id];
  keep.forEach((i,k)=>{const j=constraint?.mode==='lock'?r.candidates.findIndex(c=>c.candidate_id===constraint.candidate):winners[r.race_id][i];wins[j]++;seats[group(r.candidates[j])][k]++;});
  const candidates=r.candidates.map((c,j)=>{const v=keep.map(i=>transformed[r.race_id][i][j]).sort((a,b)=>a-b);return {...c,mean:sum(v)/v.length,p05:quantile(v,.05),p95:quantile(v,.95),probability:wins[j]/v.length};});
  const winner=wins.indexOf(Math.max(...wins)),leader=candidates[winner];
  return {...r,draws:undefined,candidates,winner,probability:candidates.map(c=>c.probability),leaderLabel:leader.name,leaderColor:COLORS[group(leader)],leaderProbability:leader.probability};
 });
 const summary=GROUPS.map(g=>{const a=seats[g].sort((a,b)=>a-b);return {group:g,name:NAMES[g],color:COLORS[g],mean:sum(a)/a.length,p05:quantile(a,.05),p95:quantile(a,.95),majority:a.filter(n=>n>=12).length/a.length,histogram:Array.from({length:23},(_,n)=>a.filter(x=>x===n).length/a.length)};});
 return {state,counties,summary,simulations:keep.length,originalSimulations:data.simulations,acceptance:keep.length/data.simulations};
}
