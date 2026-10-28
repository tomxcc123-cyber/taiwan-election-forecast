import assert from 'node:assert/strict';
import {validateShadowResearch,shadowResearchPanel} from '../site/turnout-shadow-ui.mjs';

const countyNames=Array.from({length:21},(_,i)=>i===0?'台北市':'研究縣'+i);
const scores={
 persistence:{label:'2018年直接延用',mae_pp:6.2273,rmse_pp:7.4828,
  delta_mae_vs_persistence_pp:0,n_towns:366,county_bootstrap:null},
 county_shrink_75:{label:'收縮至縣市均值75%',mae_pp:6.08,rmse_pp:7.37,
  delta_mae_vs_persistence_pp:-.1473,n_towns:366,
  counties_with_lower_mae:12,county_bootstrap:{
   difference_vs_persistence_mae_pp_90pct_county_bootstrap:[-.4,.2]}},
 county_shrink_50:{label:'收縮50%',mae_pp:6.25,rmse_pp:7.48,
  delta_mae_vs_persistence_pp:.0227,n_towns:366,
  counties_with_lower_mae:11,county_bootstrap:{
   difference_vs_persistence_mae_pp_90pct_county_bootstrap:[-.2,.4]}},
 county_drift_25:{label:'舊趨勢25%',mae_pp:6.5,rmse_pp:7.8,
  delta_mae_vs_persistence_pp:.2727,n_towns:366,
  counties_with_lower_mae:10,county_bootstrap:{
   difference_vs_persistence_mae_pp_90pct_county_bootstrap:[-.1,.6]}},
 national_drift_25:{label:'全台舊趨勢25%',mae_pp:6.52,rmse_pp:7.9,
  delta_mae_vs_persistence_pp:.2927,n_towns:366,
  counties_with_lower_mae:9,county_bootstrap:{
   difference_vs_persistence_mae_pp_90pct_county_bootstrap:[-.1,.7]}},
 shrink_75_drift_25:{label:'收縮加趨勢',mae_pp:6.7,rmse_pp:8.1,
  delta_mae_vs_persistence_pp:.4727,n_towns:366,
  counties_with_lower_mae:9,county_bootstrap:{
   difference_vs_persistence_mae_pp_90pct_county_bootstrap:[.1,.8]}},
 county_drift_100:{label:'舊趨勢100%',mae_pp:6.9655,rmse_pp:9.4523,
  delta_mae_vs_persistence_pp:.7382,n_towns:366,
  counties_with_lower_mae:8,county_bootstrap:{
   difference_vs_persistence_mae_pp_90pct_county_bootstrap:[.2,1.3]}}
};
const r={
 schema_version:1,kind:'turnout_forecast_shadow_ablation_2022_exploratory',
 training_cutoff_election:2018,holdout_election:2022,
 candidate_party_votes_used_in_predictors:false,
 uses_2022_outcomes_only_for_scoring:true,
 coverage:{towns:366,counties:21},scores,
 promotion_gate:{
  status:'blocked',formal_hb_tlef_unchanged:true,
  allow_2026_candidate_win_probability_modification:false
 },
 per_county:countyNames.map(county=>({county,
  metrics:Object.fromEntries(Object.keys(scores).map(k=>[k,{mae_pp:scores[k].mae_pp,rmse_pp:scores[k].rmse_pp}]))}))
};
assert.equal(validateShadowResearch(r),r);
const html=shadowResearchPanel(r,'台北市');
assert.match(html,/2022/);
assert.match(html,/6.23/);
assert.match(html,/6.97/);
assert.match(html,/縣市/);
assert.match(html,/未採納/);
assert.match(html,/不能直接升級為2026/);
assert.match(html,/0.15/);
assert.match(html,/選民/);
const bad=structuredClone(r);bad.promotion_gate.status='approved';
assert.throws(()=>validateShadowResearch(bad),/未通過/);
const future=structuredClone(r);future.training_cutoff_election=2022;
assert.throws(()=>validateShadowResearch(future),/未通過/);
assert.match(shadowResearchPanel(null),/尚未發布/);
console.log(JSON.stringify({passed:true,synthetic:true,formal_forecast_unchanged:true}));
