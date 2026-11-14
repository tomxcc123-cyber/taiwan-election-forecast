import assert from 'node:assert/strict';
import {validateT3Audit,t3AuditHTML} from '../site/t3-chronological-ui.mjs';

const row=(year,county='台北市')=>({
  target_year:year,county,nonmajor_candidate_count:2,
  target_nonmajor_pct:5,prior_cycle_nonmajor_pct:8,
  t3_blend_nonmajor_pct:7,t3_blend_signed_error_pp:2,
});
const m={rows:22,mae_pp:4.4,rmse_pp:8.1,signed_bias_pp:1.2,overestimated_count:12,underestimated_count:10};
function cycle(year,years){
 return {target_year:year,training_years:years,target_rows:22,rows:Array.from({length:22},(_,i)=>row(year,'縣市'+i)),metrics:{
  deployed_t3_70_30_roster_aware:{...m},
  prior_cycle_carry_roster_aware:{...m,mae_pp:5.3},
  fitted_t3_raw_roster_aware:{...m,mae_pp:6.8},
 },bootstrap:{resample_unit:'county',t3_signed_bias_pp_90pct_interval:[-.2,2.5],
   t3_minus_carry_mae_pp_90pct_interval:[-1.3,.4]},
 cohort_metrics:{no_nonmajor_on_ballot:null,one_nonmajor_on_ballot:null,
  two_or_more_nonmajor_on_ballot:{...m,rows:22},observed_nonmajor_below_5pct:null,
  observed_nonmajor_at_least_20pct:null}};
}
const fixture={schema_version:1,kind:'t3_chronological_nonmajor_bias_development_diagnostic',
 model_id:'HB-TLEF-v5.0-public-beta.1',
 frozen_t3:{alpha:.3,model_weight:.7,carry_weight:.3,features:['previous_nonmajor_share']},
 governance:{official_forecast_modified:false,independent_blind_holdout:false,
  release_gate:'blocked_until_independent_roster_and_probability_validation',
  strict_historical_candidate_ballot_roster_vintage_proven:false},
 cycles:{'2018':cycle(2018,[2014]),'2022':cycle(2022,[2014,2018])}};
assert.equal(validateT3Audit(fixture),fixture);
const html=t3AuditHTML(fixture);
assert.match(html,/T3第三勢力/);
assert.match(html,/2014＋2018/);
assert.match(html,/不是獨立盲測/);
assert.match(html,/t3-chronological-bias-audit.json/);
assert.match(html,/4.40/);
assert.match(html,/縣市0/);
assert.match(t3AuditHTML(null),/無法讀取/);
for(const fail of [
  {governance:{...fixture.governance,official_forecast_modified:true}},
  {governance:{...fixture.governance,independent_blind_holdout:true}},
  {cycles:{...fixture.cycles,2018:cycle(2018,[2018])}},
  {frozen_t3:{...fixture.frozen_t3,alpha:0}},
]){
 const bad={...fixture,...fail};
 assert.throws(()=>validateT3Audit(bad));
 assert.match(t3AuditHTML(bad),/驗證失敗/);
}
console.log('t3-chronological-ui ok');
