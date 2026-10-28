import assert from 'node:assert/strict';
import {validateTownPanel,districtPanelView} from '../site/turnout-district-panel.mjs';

const row={
 district:'松山區',district_code:'63/000/00/010',boundary_screen:'code_and_name_match_only',
 years:{
  '2018':{ballots_cast:650,electorate:1000,valid_votes:640,invalid_votes:10,stations:2,turnout_pct:65,invalid_pct:1.5385},
  '2022':{ballots_cast:570,electorate:1000,valid_votes:560,invalid_votes:10,stations:3,turnout_pct:57,invalid_pct:1.7544}
 },delta_turnout_pp:-8,delta_invalid_pp:.2159,delta_electorate:0,delta_cast:-80
};
const counties=Array.from({length:22},(_,i)=>({
 county:i===0?'台北市':i===1?'嘉義市':'模擬縣市'+i,
 status:i===1?'excluded':'matched_code_name_only',
 exclusion_reasons:i===1?['2022逐站來源缺失或非同場投票']:[],
 matched_districts:i===1?0:1,
 '2022_matched_electorate_coverage':i===1?0:1,
 county_observed_turnout_pp:i===1?null:{'2018':65,'2022':57},
 total_districts_2018:1,total_districts_2022:i===1?0:1,
 unmatched_2018:[],unmatched_2022:[],
 districts:i===1?[]:[structuredClone({...row,district:i===0?'松山區':'模擬區'+i})]
}));
const source={
 schema_version:1,kind:'observed_turnout_district_panel_not_an_individual_turnout_model',
 official_forecast_unchanged:true,counties,
 matched_districts:21,matched_counties:21,source_url:'https://data.cec.gov.tw/選舉資料庫/votedata.zip'
};
assert.equal(validateTownPanel(source),source);
const html=districtPanelView(source,'台北市');
assert.match(html,/2018—2022 鄉鎮市區投票率變化與GIS/);
assert.match(html,/松山區/);
assert.match(html,/65.00%/);
assert.match(html,/57.00%/);
assert.match(html,/-8.00 pp/);
assert.match(html,/townTurnoutMap/);
assert.match(html,/21 \/ 22/);
assert.match(html,/不等於邊界與人口組成完全不變/);
const chiayi=districtPanelView(source,'嘉義市');
assert.match(chiayi,/不具備經雙重核對/);
assert.doesNotMatch(chiayi,/townTurnoutMap/);
const invalid=structuredClone(source);
invalid.counties[0].districts[0].delta_turnout_pp=5;
assert.throws(()=>validateTownPanel(invalid),/差額/);
assert.match(districtPanelView(null,'台北市'),/尚未發佈/);
assert.equal(row.years['2018'].ballots_cast,650);
console.log(JSON.stringify({passed:true,comparison_unit:'code-and-name-matched-town',no_causal_claims:true}));
