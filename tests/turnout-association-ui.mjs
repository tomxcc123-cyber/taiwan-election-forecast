import assert from 'node:assert/strict';
import {associationPanel,verifyAssociation,verifyHoldout} from '../site/turnout-association-ui.mjs';

const fakeCounty=(name,visible)=>{
  const raw={district:'中正區',district_code:'63/000/00/010',delta_turnout_pp:-3.5,
    party_comparison_eligible:visible,delta_KMT_two_party_share_pp:visible?2.25:null,
    years:{
      '2018':{valid_votes:1000,KMT_votes:500,DPP_votes:400,
              KMT_two_party_share_pct:55.555555},
      '2022':{valid_votes:1100,KMT_votes:600,DPP_votes:440,
              KMT_two_party_share_pct:57.692307}
    }};
  return {county:name,status:'audited_historical_town_observation',districts:[raw]};
};
const counties=Array.from({length:22},(_,i)=>fakeCounty(i===0?'台北市':'測試縣'+i,i<20));
const raw={schema_version:1,kind:'historical_ecological_candidate_turnout_association_only',
 no_causal_claim:true,no_2026_prediction:true,official_forecast_unchanged:true,
 matched_towns:22,party_comparable_towns:20,matched_counties:22,counties};
const holdout={schema_version:1,kind:'cec_historical_time_ordered_turnout_holdout',
 training_information_cutoff_election:2018,held_out_election:2022,
 no_2022_training_inputs:true,calibration_claim:false,
 official_2026_forecast_unchanged:true,coverage:{districts:22,counties:22},
 turnout_forecast_score:{
   '2018_persistence':{electorate_weighted_mae_pp:4.4},
   '2014_to_2018_county_drift':{electorate_weighted_mae_pp:8.1}
 },association:{within_county_centered_weighted_pearson:-.03}};
assert.equal(verifyAssociation(raw),raw);
assert.equal(verifyHoldout(holdout),holdout);
let html=associationPanel(raw,holdout,'台北市');
assert.match(html,/4.40 pp/);
assert.match(html,/8.10 pp/);
assert.match(html,/20/);
assert.match(html,/中正區/);
assert.match(html,/因果/);
assert.match(html,/2026/);
assert.match(html,/資訊洩漏/);
const bad=structuredClone(raw);bad.counties[0].districts[0].years['2018'].KMT_votes=100000;
assert.throws(()=>verifyAssociation(bad),/有效票/);
const late=structuredClone(holdout);late.training_information_cutoff_election=2022;
assert.throws(()=>verifyHoldout(late),/時間順序/);
html=associationPanel(null,null);
assert.match(html,/尚未完成核對/);
console.log(JSON.stringify({passed:true,only_aggregate_data:true,time_ordered:true}));
