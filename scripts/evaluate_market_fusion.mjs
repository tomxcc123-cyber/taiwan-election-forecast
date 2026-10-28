"""Score archived forecast variants only against independently supplied final CEC results.

No election results are bundled with this code. Running without a verified
final-results input must fail closed, never invent outcomes or report accuracy.
"""
import {existsSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';

const EPS=1e-8;
const WEIGHTS=[['baseline','probability'],['market','market_aligned'],
               ['fusion_05','fused_05'],['fusion_10','fused_10']];
const MAX_AGE_HOURS=36;
const TAIPEI_POLL_CLOSE_UTC='2026-11-28T08:00:00Z'; // 16:00 Taiwan: evaluation reference, not assertion of certified closing
const DAY_HORIZONS=[1,3,7,14,21,28];

export function scoreDistribution(candidates,winnerId,field){
  const p=candidates.map(c=>c[field]);
  if(!p.every(x=>typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=1))
    throw new Error('Missing or invalid predicted event probabilities: '+field);
  const z=p.reduce((a,b)=>a+b,0);
  if(Math.abs(z-1)>1e-4)throw new Error('Candidate probabilities not normalized: '+field);
  const winner=candidates.findIndex(x=>x.candidate_id===winnerId);
  if(winner<0)throw new Error('Certified winner not present in archived candidate set');
  const brier=p.reduce((sum,x,i)=>sum+(x-(i===winner?1:0))**2,0);
  const logLoss=-Math.log(Math.max(EPS,p[winner]));
  return {brier,log_loss:logLoss,winner_probability:p[winner]};
}

export function validateOfficialResults(outcomes){
  if(outcomes?.schema_version!==1||outcomes.election_date!=='2026-11-28'||
     outcomes.status!=='official_final'||!Array.isArray(outcomes.races)||!outcomes.races.length)
    throw new Error('Only 2026-11-28 official final CEC results are allowed');
  const counties=new Set();
  for(const r of outcomes.races){
    if(!r.county||!r.winner_candidate_id||!r.official_source_url||
       !/^https:\/\/(?:www\.)?(?:cec\.gov\.tw|db\.cec\.gov\.tw)\//.test(r.official_source_url))
      throw new Error('Unverified CEC outcome URL or missing county winner ID');
    if(counties.has(r.county))throw new Error('Duplicate official-result county '+r.county);
    counties.add(r.county);
  }
}

export function evaluate(archive,outcomes){
  validateOfficialResults(outcomes);
  if(archive?.schema_version!==1||!Array.isArray(archive.snapshots)||
     archive.snapshots.some(s=>s.outcome_status!=='awaiting_official_result'||!s.research_only||
     !s.provenance?.market_checked_at||!s.provenance?.model_fingerprint))
     throw new Error('Invalid sealed research provenance');
  const cutoff=Date.parse(TAIPEI_POLL_CLOSE_UTC);
  const official=new Map(outcomes.races.map(r=>[r.county,r]));
  const rows=[],coverage=[];
  for(const days of DAY_HORIZONS){
    const target=cutoff-days*86400000;
    const excluded={missing_official_result:0,missing_archived_date:0,market_gate_failed:0,unknown_winner:0,
      stale_snapshot:0};
    let evaluated=0;
    for(const county of official.keys()){
      const snapshots=archive.snapshots.filter(x=>Date.parse(x.as_of)<=target &&
        Date.parse(x.as_of)<cutoff && x.races.some(r=>r.county===county));
      snapshots.sort((a,b)=>b.as_of.localeCompare(a.as_of));
      if(!snapshots.length){excluded.missing_archived_date++;continue;}
      const snap=snapshots[0],age=(target-Date.parse(snap.as_of))/3600000;
      if(age>MAX_AGE_HOURS){excluded.stale_snapshot++;continue;}
      const race=snap.races.find(r=>r.county===county);
      if(!race.included){excluded.market_gate_failed++;continue;}
      const winner=official.get(county).winner_candidate_id;
      if(!race.candidates.some(c=>c.candidate_id===winner)){
        excluded.unknown_winner++;continue;
      }
      for(const [label,field] of WEIGHTS){
        const scores=scoreDistribution(race.candidates,winner,field);
        rows.push({horizon_days:days,county,method:label,
          ...scores,model_as_of:snap.as_of,market_as_of:race.quote_as_of,
          snapshot_digest:snap.source_digest,
          official_source_url:official.get(county).official_source_url});
      }
      evaluated++;
    }
    coverage.push({horizon_days:days,evaluated_counties:evaluated,official_counties:official.size,
      excluded,score_rule:'multiclass_brier_sum_and_winner_log_loss; one snapshot per county per horizon'});
  }
  const summary=DAY_HORIZONS.map(days=>{
    const candidates=rows.filter(x=>x.horizon_days===days);
    return {horizon_days:days,n:coverage.find(x=>x.horizon_days===days).evaluated_counties,
      scores:Object.fromEntries(WEIGHTS.map(([method])=>{
        const subset=candidates.filter(x=>x.method===method);
        const n=subset.length;
        return [method,n?{brier:subset.reduce((a,x)=>a+x.brier,0)/n,
          log_loss:subset.reduce((a,x)=>a+x.log_loss,0)/n}:null];
      }))};
  });
  return {schema_version:1,scope:'paired_retrospective_research_only',official_status:outcomes.status,
    election_date:outcomes.election_date,certified_counties:official.size,
    no_p_value_claims:true,weights:[0,.05,.10],
    not_independent_across_horizons:true,
    limitation:'Correlated market and poll signals; selected events; no causal proof, no market weight optimization from scored results.',
    coverage,summary,rows};
}

function main(){
  const args=process.argv.slice(2);
  if(args.length!==2)throw new Error('Usage: node scripts/evaluate_market_fusion.mjs <certified-cec-results.json> <research-output.json>');
  const [input,output]=args.map(x=>resolve(x));
  if(!existsSync(input))throw new Error('Official results missing; no evaluation performed');
  const base=resolve(import.meta.dirname,'../data/market-fusion-history.json');
  const archive=JSON.parse(readFileSync(base,'utf8'));
  const outcomes=JSON.parse(readFileSync(input,'utf8'));
  const results=evaluate(archive,outcomes);
  if(!results.coverage.some(x=>x.evaluated_counties>0))
    throw new Error('No matched, fresh and certified forecast pairs; refusing empty performance report');
  writeFileSync(output,JSON.stringify(results,null,2)+'\n');
  console.log(JSON.stringify({qualified:results.coverage.map(c=>[c.horizon_days,c.evaluated_counties])}));
}
if(process.argv[1]&&resolve(process.argv[1])===resolve(import.meta.filename))main();
