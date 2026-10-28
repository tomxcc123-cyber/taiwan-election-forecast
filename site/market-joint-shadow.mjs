// Research-only joint market-signal sensitivity on the canonical correlated
// HB-TLEF draws. Never mutates the official candidate-model, draw cloud or
// published baseline. No calibration or causal claims.
import {marketFusion,MARKET_FUSION_WEIGHTS} from './market-fusion.mjs';
import {GROUPS,NAMES,group} from './candidate-engine.mjs';

const floor=1e-6;
const MIN_ESS_FRAC=0.20;
const MAX_SINGLE_WEIGHT=0.05;
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const fail=(reason,extra={})=>({available:false,reason,official_model_unchanged:true,...extra});

function weightedQuantile(values,weights,q){
  const ordered=values.map((value,i)=>({value,weight:weights[i]})).sort((a,b)=>a.value-b.value);
  const target=q*weights.reduce((s,x)=>s+x,0);
  let acc=0;
  for(const item of ordered){acc+=item.weight;if(acc>=target)return item.value;}
  return ordered.at(-1)?.value??null;
}
function normalize(logWeights){
  const peak=Math.max(...logWeights),w=logWeights.map(x=>Math.exp(x-peak));
  const sum=w.reduce((a,b)=>a+b,0);
  if(!finite(sum)||sum<=0)return null;
  return w.map(x=>x/sum);
}
function winnerOf(row){
  let max=-1,index=-1;
  for(let i=0;i<row.length;i++){if(!finite(row[i])||row[i]<0)return -1;if(row[i]>max){max=row[i];index=i;}}
  return index;
}

/** 
 * Returns a transparent shadow distribution across all 22 county elections.
 * Each original joint Monte Carlo index remains one path; no independence of
 * county outcomes is assumed. The scenario engine is intentionally not used.
 */
export function jointMarketShadow(model,market,lambda=0.05,asOf=model?.generated_at){
  if(!MARKET_FUSION_WEIGHTS.includes(lambda))return fail('非預先指定的實驗權重');
  const races=model?.counties;
  const draws=model?.simulations;
  if(!Array.isArray(races)||races.length!==22||!Number.isInteger(draws)||draws<100)
    return fail('基準模型沒有完整22縣市的聯合模擬');
  const asOfMs=Date.parse(asOf||''),modelMs=Date.parse(model?.generated_at||''),
        marketMs=Date.parse(market?.checked_at||'');
  if(!finite(asOfMs)||!finite(modelMs)||!finite(marketMs)||marketMs>asOfMs||modelMs>asOfMs||
     modelMs<marketMs-60000)
    return fail('市場、模型擷取時間不可對齊，拒絕前瞻資訊');
  if(market?.schema_version!==1||!Array.isArray(market.events))
    return fail('來源市場檔案格式無效');
  if(races.some(r=>!Array.isArray(r.candidates)||r.candidates.length<2||
     !Array.isArray(r.draws)||r.draws.length!==draws||
     r.draws.some(a=>!Array.isArray(a)||a.length!==r.candidates.length)))
    return fail('候選人模擬矩陣不完整');

  const byCounty=new Map();
  for(const event of market.events){
    if(byCounty.has(event.county))return fail('同一縣市出現多筆衝突的市場事件');
    byCounty.set(event.county,event);
  }
  const checks=races.map(r=>{
    const event=byCounty.get(r.name);
    const result=event?marketFusion(model,event,lambda,asOf):
      {eligible:false,reason:'沒有對應的公開選舉市場'};
    const p=result.eligible?new Map(result.probabilities.map(x=>[x.candidateId,x])):null;
    return {county:r.name,eligible:!!result.eligible,
            reason:result.eligible?'已通過原有合約與流動性核驗':result.reason,
            quote_as_of:event?.quote_as_of||null,probabilities:p};
  });
  const eligible=checks.filter(c=>c.eligible);
  if(eligible.length===0)return fail('沒有同時通過時效、合約對應與流動性條件的市場', {checks,eligible_count:0});

  const logWeights=Array(draws).fill(0);
  const rawWinners=new Map();
  for(let k=0;k<races.length;k++){
    const r=races[k],check=checks[k];
    const winners=r.draws.map(winnerOf);
    if(winners.some(j=>j<0))return fail('模型模擬的候選人得票數值無效');
    rawWinners.set(r.race_id,winners);
    if(!check.eligible||lambda===0)continue;
    for(let s=0;s<draws;s++){
      const candidate=r.candidates[winners[s]];
      const x=check.probabilities.get(candidate.candidate_id);
      if(!x)return fail('市場來源與模擬的候選人識別不一致');
      // Likelihood ratio of the observed winner event, not a vote-share prior.
      // Tempered by fixed 5% or 10% sensitivity only.
      logWeights[s]+=lambda*(Math.log(Math.max(floor,x.alignedMarket))-
                             Math.log(Math.max(floor,x.model)));
    }
  }
  const weights=normalize(logWeights);
  if(!weights)return fail('聯合權重不可歸一化');
  const ess=1/weights.reduce((s,w)=>s+w*w,0);
  const largest=Math.max(...weights);
  // Don't present a dramatic shift produced by a handful of Monte Carlo paths.
  const diagnostics={
    simulations:draws,
    eligible_count:eligible.length,
    excluded_count:checks.length-eligible.length,
    effective_sample_size:Number(ess.toFixed(1)),
    effective_sample_fraction:Number((ess/draws).toFixed(4)),
    max_path_weight:Number(largest.toFixed(5)),
    joint_gate_passed:ess>=draws*MIN_ESS_FRAC&&largest<=MAX_SINGLE_WEIGHT,
    market_checked_at:market.checked_at,
    model_as_of:model.generated_at,
    experiment_weight:lambda,
    no_independent_signal_assumption:true
  };
  if(!diagnostics.joint_gate_passed)
    return fail('重要性重加權有效樣本數不足，聯合模擬結果被拒絕',{diagnostics,checks,eligible_count:eligible.length});

  const seats=Object.fromEntries(GROUPS.map(g=>[g,Array(draws).fill(0)]));
  const counties=races.map((r,k)=>{
    const win=rawWinners.get(r.race_id);
    const probs=Array(r.candidates.length).fill(0);
    const plain=Array(r.candidates.length).fill(0);
    for(let s=0;s<draws;s++){
      const j=win[s];
      probs[j]+=weights[s];plain[j]+=1/draws;
      seats[group(r.candidates[j])][s]++;
    }
    const check=checks[k];
    const candidates=r.candidates.map((c,j)=>({
      candidate_id:c.candidate_id,name:c.name,party:group(c),
      baseline:Number(plain[j].toFixed(6)),
      experimental:Number(probs[j].toFixed(6)),
      delta_pp:Number(((probs[j]-plain[j])*100).toFixed(2))
    }));
    const winner=candidates.reduce((best,c)=>c.experimental>best.experimental?c:best,candidates[0]);
    return {
      county:r.name,race_id:r.race_id,
      eligible_market:check.eligible,
      candidates,leader:winner.name,leader_probability:winner.experimental
    };
  });
  const national=GROUPS.map(g=>{
    const samples=seats[g];
    const hist=Array.from({length:23},(_,n)=>samples.reduce((acc,value,i)=>acc+(value===n?weights[i]:0),0));
    const mean=samples.reduce((acc,v,i)=>acc+v*weights[i],0);
    const baseline=samples.reduce((acc,v)=>acc+v,0)/draws;
    return {party:g,name:NAMES[g],
      mean:Number(mean.toFixed(4)),
      baseline_mean:Number(baseline.toFixed(4)),
      delta_mean:Number((mean-baseline).toFixed(4)),
      p05:weightedQuantile(samples,weights,.05),
      p95:weightedQuantile(samples,weights,.95),
      majority_probability:Number(hist.slice(12).reduce((a,b)=>a+b,0).toFixed(5)),
      histogram:hist.map(v=>Number(v.toFixed(6)))
    };
  });
  const nationalMean=national.reduce((acc,x)=>acc+x.mean,0);
  if(Math.abs(nationalMean-22)>0.003)return fail('聯合席次守恆失敗',{diagnostics});
  return {
    available:true,kind:'uncalibrated_joint_importance_weight_shadow',
    official_model_unchanged:true,not_training:true,
    diagnostics,checks,counties,national,
    warning:'僅是相關模擬路徑的敏感度重新加權，無法代表已校準的聯合後驗；市場與民調可能含有相同資訊。'
  };
}
