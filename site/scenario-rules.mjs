const total=a=>a.reduce((s,x)=>s+x,0);
const bound=(x,low,high,fallback=0)=>typeof x==='number'&&Number.isFinite(x)?Math.max(low,Math.min(high,x)):fallback;
export function unpackMatrix(matrix){
  if(Array.isArray(matrix))return matrix;
  if(matrix?.v===1&&Array.isArray(matrix.ids)&&Array.isArray(matrix.rows))return matrix.rows.slice(0,200).map(r=>({from:matrix.ids[r[0]],to:matrix.ids[r[1]],rate:r[2]}));
  return [];
}
export function ruleFields(edit,ids){
  const unique=new Map();
  for(const edge of unpackMatrix(edit.matrix).slice(0,200)){
    if(!edge||!ids.includes(edge.from)||!ids.includes(edge.to)||edge.from===edge.to)continue;
    const key=JSON.stringify([edge.from,edge.to]),rate=bound(edge.rate,0,100);
    unique.set(key,{from:edge.from,to:edge.to,rate:Math.min(100,(unique.get(key)?.rate||0)+rate)});
  }
  const matrix=[...unique.values()].filter(e=>e.rate>0).sort((a,b)=>a.from.localeCompare(b.from)||a.to.localeCompare(b.to));
  for(const id of ids){const outgoing=total(matrix.filter(e=>e.from===id).map(e=>e.rate));if(outgoing>100)for(const e of matrix)if(e.from===id)e.rate*=100/outgoing;}
  return {matrix,matrixMode:edit.matrixMode==='loss'?'loss':'transfer',
    strategy:['off','close','legacy'].includes(edit.strategy)?edit.strategy:'legacy',
    cutoff:bound(edit.cutoff,1,30,15),topSplit:bound(edit.topSplit,0,100,50)};
}
export function packMatrices(state){
  const packed=structuredClone(state);
  for(const e of Object.values(packed.edits||{}))if(e.matrix?.length){const ids=[...new Set(e.matrix.flatMap(r=>[r.from,r.to]))].sort();e.matrix={v:1,ids,rows:e.matrix.map(r=>[ids.indexOf(r.from),ids.indexOf(r.to),r.rate])};}
  return packed;
}
export function applyMatrix(base,current,ids,edges,mode){
  if(!edges?.length)return [...current];
  const start=[...current],out=[...current],incoming=ids.map(()=>0),drains=ids.map(()=>0);
  for(const e of edges){const from=ids.indexOf(e.from),to=ids.indexOf(e.to);if(from<0||to<0||from===to)continue;
    const pool=mode==='loss'?Math.max(0,base[from]-start[from]):start[from];
    const amount=pool*e.rate/100;drains[from]+=amount;incoming[to]+=amount;
  }
  if(mode==='loss'){
    const gains=start.map((v,i)=>Math.max(0,v-base[i])),available=total(gains),moved=total(drains);
    if(available<=1e-12)return out;
    for(let i=0;i<out.length;i++)out[i]-=gains[i]*Math.min(1,moved/available);
  }else for(let i=0;i<out.length;i++)out[i]-=drains[i];
  return out.map((v,i)=>v+incoming[i]);
}
export function applyStrategy(values,race,edit){
  if(edit.strategy==='off'||!edit.tactical||race.candidates.length<3)return [...values];
  const ids=race.candidates.map(c=>c.candidate_id),rank=ids.map((_,i)=>i).sort((a,b)=>race.candidates[b].mean-race.candidates[a].mean||ids[a].localeCompare(ids[b]));
  const close=edit.strategy==='close',margin=race.candidates[rank[0]].mean-race.candidates[rank[1]].mean;
  const damping=close?Math.max(0,1-margin/edit.cutoff):1,split=close?edit.topSplit/100:0;
  const out=[...values];
  for(const donor of rank.slice(2)){const amount=values[donor]*edit.tactical/100*damping;out[donor]-=amount;out[rank[0]]+=amount*split;out[rank[1]]+=amount*(1-split);}
  return out;
}
