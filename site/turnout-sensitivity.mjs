// Turnout sensitivity uses observed eligible-voter / ballots-cast counts and
// the archived valid-vote-share draws.  It does NOT infer how new voters vote
// from ecological turnout alone, nor alter canonical election simulations.
export const TURNOUT_DELTA_OPTIONS=Object.freeze([-10,-5,0,5,10]);
const clamp=(x,min,max)=>Math.max(min,Math.min(max,x));
const finite=n=>typeof n==='number'&&Number.isFinite(n);

export function historicalTurnout(source){
  if(source?.schema_version!==1||!Array.isArray(source.records)||source.records.length!==22)
    throw new Error('投票率歷史資料不完整');
  const unique=new Set(),totals={2018:{eligible:0,cast:0},2022:{eligible:0,cast:0}};
  const rows=source.records.map(r=>{
    const county=String(r.county||'').replaceAll('臺','台');
    if(!county||unique.has(county))throw new Error('投票率縣市重複或缺漏');
    unique.add(county);
    const years={};
    for(const y of ['2018','2022']){
      const item=r.years?.[y];
      if(!Number.isInteger(item?.eligible)||!Number.isInteger(item?.cast)||
         item.cast<=0||item.eligible<item.cast)throw new Error('投票數或選舉人數無效');
      totals[y].eligible+=item.eligible;totals[y].cast+=item.cast;
      years[y]={...item,rate:item.cast/item.eligible};
    }
    return {county,years,delta_pp:(years['2022'].rate-years['2018'].rate)*100,
      special_note:r.notes||null};
  });
  for(const y of ['2018','2022']){
    if(totals[y].eligible!==source.national?.[y]?.eligible||totals[y].cast!==source.national?.[y]?.cast)
      throw new Error('縣市合計與中選會報告全國數不一致');
  }
  return {rows,totals,source:source.source,notice:source.notice};
}

// Dimensionless turnout rates T are a fraction of the eligible electorate.
// Turnout observed counts include invalid ballots, whereas candidate shares
// refer to valid ballots; unchanged invalid-ballot fraction is assumed for
// these mathematical bounds only, not measured by the source tables.
export function turnoutShareBounds(share,t0,deltaPp){
  if(!finite(share)||share<0||share>1||!finite(t0)||t0<=0||t0>=1||
     !finite(deltaPp)||Math.abs(deltaPp)>15)throw new Error('敏感度參數超出預定區間');
  const d=deltaPp/100,t1=t0+d;
  if(t1<=0||t1>=1)throw new Error('假設投票率落在無效區間');
  const votes=t0*share;
  if(d>=0){
    return {lower:clamp(votes/t1,0,1),
      upper:clamp((votes+d)/t1,0,1),proportional:share};
  }
  const lost=-d;
  return {lower:clamp((votes-lost)/t1,0,1),
    upper:clamp(votes/t1,0,1),proportional:share};
}
function leadingMargin(row){
  const sum=row.reduce((s,x)=>s+x,0);
  if(sum<=0||row.some(x=>!finite(x)||x<0))return null;
  const order=[...row].sort((a,b)=>b-a);
  return (order[0]-order[1])/sum;
}

export function turnoutScenario(model,source,{county='台北市',deltaPp=0}={}){
  if(!TURNOUT_DELTA_OPTIONS.includes(deltaPp))
    throw new Error('投票率變動只接受已標示的情境');
  const historical=historicalTurnout(source);
  const base=historical.rows.find(x=>x.county===county);
  const race=model?.counties?.find(x=>x.name===county);
  if(!base||!race||!Array.isArray(race.draws)||race.draws.length<100||
     race.candidates?.length<2||race.draws.some(r=>r.length!==race.candidates.length))
    throw new Error('縣市或候選人聯合抽樣不完整');
  const t0=base.years['2022'].rate,t1=t0+deltaPp/100;
  if(t1<=0||t1>=1)throw new Error('假設投票率無效');
  let robust=0,usable=0;
  const means=Array(race.candidates.length).fill(0);
  for(const row of race.draws){
    const margin=leadingMargin(row);
    if(margin===null)throw new Error('候選人模擬票數無效');
    const sum=row.reduce((a,b)=>a+b,0);
    row.forEach((x,j)=>means[j]+=x/sum);
    // Exact worst-case pairwise advantage bound: under +/-|delta|,
    // all affected ballots could favor a challenger or leave the leader.
    if(margin*t0>Math.abs(deltaPp)/100+1e-12)robust++;
    usable++;
  }
  const candidates=race.candidates.map((c,j)=>{
    const share=means[j]/usable;
    return {candidate_id:c.candidate_id,name:c.name,
      model_valid_vote_share:share,...turnoutShareBounds(share,t0,deltaPp)};
  });
  return {
    county,year_anchor:2022,delta_pp:deltaPp,
    historical_2018_pct:base.years['2018'].rate*100,
    historical_2022_pct:t0*100,
    observed_2018_to_2022_pp:base.delta_pp,
    scenario_turnout_pct:t1*100,
    electorate_reference:base.years['2022'].eligible,
    scenario_change_ballots:Math.round(base.years['2022'].eligible*deltaPp/100),
    robustness_share:robust/usable,robust_draws:robust,total_draws:usable,
    interpretation:'Robustness is the fraction of model draws whose leading margin could not be overtaken under ANY distribution of turnout change of the given magnitude. Nonrobust means reversal is mathematically possible, not predicted.',
    notes:base.special_note,
    candidates,official_model_unchanged:true,
    conditioned_on:'2022 county turnout as reference; unchanged invalid-ballot fraction, unobserved composition of marginal voters',
    not_estimated:'2026 actual turnout, incremental voters political preferences, causal effects',
  };
}
export function turnoutOverview(model,source,deltaPp){
  const hist=historicalTurnout(source);
  return hist.rows.map(x=>{
    const result=turnoutScenario(model,source,{county:x.county,deltaPp});
    return {county:x.county,turnout_2018_pct:result.historical_2018_pct,
      turnout_2022_pct:result.historical_2022_pct,observed_change_pp:x.delta_pp,
      scenario_turnout_pct:result.scenario_turnout_pct,
      hypothetical_ballots_delta:result.scenario_change_ballots,
      robustness_share:result.robustness_share,
      specific_2026_forecast:false,notes:x.special_note};
  });
}
