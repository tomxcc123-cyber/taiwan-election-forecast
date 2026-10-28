import assert from 'node:assert/strict';
import {validateTwoCycleHistory,twoCycleHistoryPanel} from '../site/turnout-two-cycle-ui.mjs';

const counties=Array.from({length:22},(_,i)=>({
 county:i===0?'台北市':'測試縣'+i,
 status:'matched_original_code_name',matched_towns:1,
 districts:[{district:'北投區',town_code:'120',delta_turnout_pp:4,
 years:{
   '2014':{electorate:100,ballots_cast:70,valid_votes:68,invalid_votes:2,stations:2},
   '2018':{electorate:100,ballots_cast:74,valid_votes:72,invalid_votes:2,stations:3}
 }}]
}));
const panel={schema_version:1,kind:'observed_cec_2014_to_2018_town_turnout_holdout_input',
 no_cross_year_precinct_join:true,join_screen_not_boundary_proof:true,
 official_2026_forecast_unchanged:true,matched_counties:22,matched_towns:22,counties};
const score=mae=>({n_towns:22,electorate_weighted_mae_pp:mae,
 delta_mae_vs_persistence_pp:mae-3.5});
const previous={training_election:2014,held_out_election:2018,matched_towns:22,
 matched_counties:22,
 towns:Array.from({length:22},(_,i)=>({county:'測試縣'+i})),
 scores:{persistence:score(3.5),county_shrink_75:score(3.4),county_shrink_50:score(3.6)}};
const latest={training_election:2018,held_out_election:2022,matched_towns:22,
 matched_counties:21,towns:Array.from({length:22},(_,i)=>({county:'測試縣'+i})),
 scores:{persistence:score(6.2),county_shrink_75:score(6.1),county_shrink_50:score(6.3)}};
const report={
 schema_version:1,kind:'cec_two_independent_town_turnout_cycles_2014_2022',
 no_future_outcome_predictors:true,candidate_vote_data_used:false,
 promotion_gate:{status:'blocked',formal_hb_tlef_unchanged:true,
  allow_2026_candidate_win_probability_modification:false},
 cycles:{'2014_to_2018':previous,'2018_to_2022':latest},
 improved_both_cycles:['county_shrink_75']
};
report.cycles['2018_to_2022'].scores.persistence.delta_mae_vs_persistence_pp=0;
assert.equal(validateTwoCycleHistory(panel,report).panel,panel);
const text=twoCycleHistoryPanel(panel,report,'台北市');
assert.match(text,/2014—2018/);
assert.match(text,/2018—2022/);
assert.match(text,/北投區/);
assert.match(text,/70.00%/);
assert.match(text,/74.00%/);
assert.match(text,/沒有在2018年預測時使用2018結果/);
assert.match(text,/不得作為2026年正式勝選機率修正依據/);
const wrong=structuredClone(report);wrong.promotion_gate.status='approved';
assert.throws(()=>validateTwoCycleHistory(panel,wrong),/不符合/);
const missing=structuredClone(panel);missing.counties[0].districts=[];
assert.throws(()=>validateTwoCycleHistory(missing,report),/不一致/);
assert.match(twoCycleHistoryPanel(null,null),/尚未經核驗/);
console.log(JSON.stringify({passed:true,cycles:2,station_ids_never_joined:true}));
