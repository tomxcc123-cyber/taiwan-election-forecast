import assert from 'node:assert/strict';
import fs from 'node:fs';
import {validateThreeYearAudit,threeYearAuditPanel} from '../site/turnout-three-year-ui.mjs';

const s={schema_version:1,kind:'cec_three_year_common_town_ecological_stability_audit',
 geography_status:'code_and_original_name_continuity_only_no_historical_boundary_overlay',
 candidate_vote_data_used:false,no_individual_voter_inference:true,
 forecast_2026_modified:false,
 promotion_gate:{status:'blocked',formal_hb_tlef_unchanged:true,
  allow_2026_candidate_win_probability_modification:false},
 matched_towns:1,matched_counties:1,'2018_duplicate_source_counts_disagreements':0,
 towns:[{county:'台北市',town_code:'010',district:'松山區',code_and_name_only:true,
  '2018_duplicate_source_counts_identical':true,
  year_electorates:{'2014':100,'2018':102,'2022':101},
  year_station_counts:{'2014':2,'2018':2,'2022':2}}],
 county_diagnostics:[{county:'台北市',matched_towns:1,
  station_count_changed:0,electorate_change_gt_8pct:0}],
 unmatched_prior:[],unmatched_recent:[],
 historical_boundary_reference:'https://maps.nlsc.gov.tw/pro/013_41_layer.html',
 unchanged_station_count_towns:1,electorate_change_gt_8pct_towns:0,
 cohorts:Object.fromEntries(['common_towns','unchanged_station_count',
   'electorate_change_within_8pct','both_diagnostic_flags_clear'].map(k=>
   [k,Object.fromEntries(['2014_to_2018','2018_to_2022'].map(c=>
      [c,{n_towns:1,scores:{persistence:3.2,county_shrink_75:3.1,county_shrink_50:3.3}}]))]))};
assert.equal(validateThreeYearAudit(s),s);
const html=threeYearAuditPanel(s);
assert.match(html,/2014—2022 三屆行政區共同樣本/);
assert.match(html,/2018直接延用MAE/);
assert.match(html,/同一鄉鎮集合評分/);
assert.match(html,/行政邊界GIS重疊比對/);
assert.match(html,/不可作選前準確率證據/);
const invalid=structuredClone(s);invalid.promotion_gate.status='approved';
assert.throws(()=>validateThreeYearAudit(invalid),/資料核驗/);
assert.doesNotMatch(threeYearAuditPanel(invalid),/2018直接延用MAE/);
const wrong=structuredClone(s);wrong.towns[0].year_electorates['2022']=0;
assert.throws(()=>validateThreeYearAudit(wrong),/年度選民/);
const duplicate=structuredClone(s);duplicate.towns.push(duplicate.towns[0]);duplicate.matched_towns=2;
assert.throws(()=>validateThreeYearAudit(duplicate),/對接紀錄/);
assert.match(threeYearAuditPanel(null),/尚未完成來源交叉稽核/);
if(fs.existsSync(new URL('../dist/turnout-three-year-compatibility.json',import.meta.url))){
 const real=JSON.parse(fs.readFileSync(new URL('../dist/turnout-three-year-compatibility.json',import.meta.url),'utf8'));
 assert.equal(validateThreeYearAudit(real),real);
 assert.equal(real.matched_towns,364);
 assert.match(threeYearAuditPanel(real),/員林市/);
}
console.log(JSON.stringify({passed:true,historical_only:true,no_2026_model_mutation:true}));
