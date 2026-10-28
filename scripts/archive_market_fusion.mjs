"""Historical archive of genuinely computed, paired election-market and model signals.

Archives are produced ONLY from one publish build's candidate-model.json and
already-fetched market-snapshots.json. No retroactive reconstruction of older
market/model values and no ingestion of market data into official forecasts.
"""
import {readFileSync,writeFileSync,existsSync,mkdirSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {marketFusion} from '../site/market-fusion.mjs';

const base = resolve(import.meta.dirname,'..');
const modelFile=resolve(base,'dist/candidate-model.json');
const marketFile=resolve(base,'data/market-snapshots.json');
const historyFile=resolve(base,'data/market-fusion-history.json');
const publishFile=resolve(base,'dist/market-fusion-history.json');

export const ASSUMED_WEIGHTS=Object.freeze([0,0.05,0.10]);
const round = p=>Number(p.toFixed(8));
const id = x=>String(x??'');

export function pairedSnapshot(model, market){
  const asOf=model?.generated_at,modelMs=Date.parse(asOf||'');
  const checked=Date.parse(market?.checked_at||'');
  if(!Number.isFinite(modelMs)||!Number.isFinite(checked)||checked>modelMs)
    throw new Error('Model and market snapshot timestamps are not aligned');
  if(!model?.fingerprint||model.counties?.length!==22||market?.schema_version!==1||
     !Array.isArray(market.events))throw new Error('Incomplete audited prediction source');
  const day=new Date(modelMs+8*3600e3).toISOString().slice(0,10);
  const marketEvents=new Map();
  for(const event of market.events){
    if(marketEvents.has(event.county))throw new Error('Ambiguous duplicate market event for county '+event.county);
    marketEvents.set(event.county,event);
  }
  const races=[];
  for(const county of model.counties){
    const event=marketEvents.get(county.name);
    const baseline=(county.candidates||[]).map(c=>({
      candidate_id:id(c.candidate_id),name:id(c.name),probability:c.probability
    }));
    if(!baseline.length||baseline.some(c=>!Number.isFinite(c.probability)))
      throw new Error('Invalid baseline county '+county.name);
    const signal=event?marketFusion(model,event,0.05,asOf):
      {eligible:false,reason:'尚無對應的公開選舉市場'};
    const signal10=event&&signal.eligible?marketFusion(model,event,0.10,asOf):null;
    if(signal.eligible&&!signal10?.eligible)
      throw new Error('Mismatched sensitivity-gate results');
    const mapped=new Map(signal.eligible?signal.probabilities.map(x=>[x.candidateId,x]):[]);
    const mapped10=new Map(signal10?.eligible?signal10.probabilities.map(x=>[x.candidateId,x]):[]);
    const candidates=baseline.map(c=>{
      const x=mapped.get(c.candidate_id),y=mapped10.get(c.candidate_id);
      if(signal.eligible&&(!x||!y))throw new Error('Incomplete aligned candidate mapping');
      return {
        ...c,
        market_yes:x?.market??null,
        market_aligned:x?round(x.alignedMarket):null,
        fused_05:x?round(x.fused):null,
        fused_10:y?round(y.fused):null
      };
    });
    races.push({
      county:county.name,race_id:id(county.race_id),
      market_slug:event?.slug||null,
      source_url:event?.source_url||null,
      quote_as_of:event?.quote_as_of||null,
      market_retrieved_at:event?.retrieved_at||null,
      market_stale:event?.stale??null,
      liquidity_usd:event?.liquidity_usd??null,
      volume_usd:event?.volume_usd??null,
      included:!!signal.eligible,
      reason:signal.eligible?'matched_and_quality_checked':signal.reason,
      candidates
    });
  }
  const source={
    model_fingerprint:model.fingerprint,
    model_version:model.model_version,
    model_as_of:asOf,
    market_checked_at:market.checked_at,
    market_registry_count:market.registry_count,
    market_status:market.status
  };
  return {
    schema_version:1,
    taipei_day:day,
    as_of:asOf,
    provenance:source,
    source_digest:createHash('sha256').update(JSON.stringify({source,races})).digest('hex'),
    weights:ASSUMED_WEIGHTS,
    included_races:races.filter(r=>r.included).length,
    excluded_races:races.filter(r=>!r.included).length,
    outcome_status:'awaiting_official_result',
    research_only:true,
    official_forecast_unchanged:true,
    races
  };
}

export function upsertHistory(previous, snapshot){
  if(previous&&previous.schema_version!==1)throw new Error('Unknown historical archive schema');
  const items=Array.isArray(previous?.snapshots)?previous.snapshots:[];
  if(items.some(s=>!s.provenance?.model_fingerprint||!s.taipei_day))
    throw new Error('Corrupted archived provenance');
  const key=snapshot.taipei_day+'|'+snapshot.provenance.model_version;
  const keep=items.filter(x=>x.taipei_day+'|'+x.provenance.model_version!==key);
  const prior=items.find(x=>x.taipei_day+'|'+x.provenance.model_version===key);
  // Never replace a later observation with an earlier replay.
  if(prior&&Date.parse(prior.as_of)>Date.parse(snapshot.as_of))return previous;
  if(prior&&Date.parse(prior.as_of)===Date.parse(snapshot.as_of)&&prior.source_digest!==snapshot.source_digest)
    throw new Error('Conflicting same-timestamp immutable market/model snapshot');
  const snapshots=[...keep,snapshot].sort((a,b)=>a.as_of.localeCompare(b.as_of)).slice(-200);
  return {
    schema_version:1,
    publication_status:'research_not_calibrated',
    election_date:'2026-11-28',
    weights:ASSUMED_WEIGHTS,
    created_from:'one matched production model build and already fetched Gamma market snapshot',
    results_available:false,
    scoring_status:'awaiting_official_cec_results',
    note:'Daily last build by Taipei date. No fabricated backfill, no evidence of predictive improvement yet; market/forecast correlated through news and polls.',
    snapshots
  };
}

export function appendArchive(model,market,previous={}){
  return upsertHistory(previous,pairedSnapshot(model,market));
}

function main(){
  if(!existsSync(modelFile)){
    console.log('Market/model aligned archive skipped: publication pause or no model artifact');
    return;
  }
  if(!existsSync(marketFile))throw new Error('Missing market snapshot input');
  const model=JSON.parse(readFileSync(modelFile,'utf8'));
  const market=JSON.parse(readFileSync(marketFile,'utf8'));
  const previous=existsSync(historyFile)?JSON.parse(readFileSync(historyFile,'utf8')):{};
  const output=appendArchive(model,market,previous);
  mkdirSync(dirname(historyFile),{recursive:true});
  const bytes=JSON.stringify(output,null,2)+'\n';
  writeFileSync(historyFile,bytes,'utf8');
  writeFileSync(publishFile,bytes,'utf8');
  const recent=output.snapshots.at(-1);
  console.log(JSON.stringify({archived:output.snapshots.length,date:recent.taipei_day,
    included:recent.included_races,excluded:recent.excluded_races,official_outcomes:'not_yet_available'}));
}
if(process.argv[1]&&resolve(process.argv[1])===resolve(import.meta.filename))main();
