import assert from 'node:assert/strict';
import {methodLabel,verificationLabel,reviewLabel,ingestionLabel,sourceState,coverageStats,discoveryQueueHTML,observatoryHTML,nonmajorResponseHTML,nonmajorHistoricalHTML,commissionerSensitivityHTML} from '../site/poll-source-v52.mjs';

assert.equal(methodLabel('closed_online_panel'),'封閉式網路樣本');
assert.equal(methodLabel('telephone_cati'),'電話訪問');
assert.equal(methodLabel('online_dmp_panel'),'DMP網路樣本');
assert.equal(verificationLabel('reviewed_multi_source_methodology'),'多來源方法核驗');
assert.equal(verificationLabel('reviewed_multi_source_methodology_partial_response'),'多來源核驗／回應類別部分未公開');
assert.equal(reviewLabel('publisher_reprint_not_new_pollster'),'轉載別家調查／不重複計權');
assert.equal(reviewLabel('publisher_not_pollster'),'刊載媒體／不另建 pollster');
assert.equal(ingestionLabel({ingestion:'reviewed_multi_source_methodology',verification_status:'reviewed_multi_source_methodology'}),'人工核驗後收錄（多來源方法核驗）；不是本輪自動原始報告解析成功。');
assert.equal(ingestionLabel({ingestion:'automatic_original_report'}),'原始報告自動解析並校驗。');
assert.deepEqual(sourceState({validated_reports:2,index_ok:true}),{key:'auto',label:'自動核驗'});
assert.deepEqual(sourceState({status:'reviewed_seed_only',reviewed_reports:1}),{key:'reviewed',label:'人工核驗種子'});
assert.deepEqual(sourceState({auto_discovery_status:'checked',reviewed_reports:2}),{key:'auto',label:'自動發現＋人工核驗'});
assert.deepEqual(sourceState({auto_discovery_status:'degraded',reviewed_reports:2}),{key:'degraded',label:'發現受限／核驗存檔'});
assert.deepEqual(sourceState({index_ok:false}),{key:'degraded',label:'來源受限'});

const feed={
  latest_fieldwork_date:'2026-08-30',
  checked_at:'2026-09-12T10:35:00+00:00',status:'degraded',failures:[{source:'synthetic',message:'offline'}],stale_after_hours:18,
  pollster_registry:{schema_version:1,registered_pollsters:7,updated_at:'2026-09-12T10:25:00+00:00'},
  sources:[
    {name:'ETtoday 民調雲',url:'https://example.com/e',reviewed_reports:2,validated_reports:0,index_ok:true,status:'checked',method_class:'closed_online_panel',note:'closed panel'},
    {name:'新台灣國策智庫／趨勢民調',url:'https://example.com/t',reviewed_reports:1,validated_reports:0,status:'reviewed_seed_only',method_class:'telephone_cati'},
    {name:'鉅聞天下／皮爾森數據',url:'https://example.com/p',reviewed_reports:2,validated_reports:0,status:'reviewed_seed_only',method_class:'online_dmp_panel',auto_discovery:true,auto_discovery_status:'checked',auto_discovered:4,auto_known:2,auto_pending:2,registry_pollster_id:'pearson-data'}
  ],
  source_review:[{name:'艾普羅行銷市場研究',status:'reviewed_methodology_incomplete_response_mass',note:'37.7% response mass unresolved',url:'https://example.com/a'}],
  discovery_queue:[
    {pollster_id:'pearson-data',source:'鉅聞天下／皮爾森數據',title:'2026《鉅聞民調》台北市長選舉／蔣萬安52%對沈伯洋39%',county:'台北市',url:'https://example.com/new',status:'discovered_unverified',reason:'一方站點自動發現；尚未通過完整資料品質校驗，因此不入模。',discovered_at:'2026-09-12T10:30:00+00:00'}
  ],
  records:[
    {id:'p1',source:'ETtoday 民調雲',pollster_id:'ettoday',method_class:'closed_online_panel',published_at:'2026-09-11'},
    {id:'p2',source:'新台灣國策智庫／趨勢民調',pollster_id:'trend-survey',method_class:'telephone_cati',commissioning_type:'external_commissioned',commissioner_id:'ketagalan-foundation'},
    {id:'p3',source:'鉅聞天下／皮爾森數據',pollster_id:'pearson-data',method_class:'online_dmp_panel'}
  ]
};
const model={poll_audit:[{id:'p1',included:true},{id:'p2',included:true},{id:'p3',included:true}],settings:{commissioned_house_sd:.20}};
const stats=coverageStats(feed,model);
assert.equal(stats.sourceCount,3);
assert.equal(stats.registryCount,7);
assert.equal(stats.methodCount,3);
assert.equal(stats.included,3);
assert.equal(stats.discoveryQueue,1);
assert.equal(stats.reviewQueue,2);
assert.equal(stats.latest,'2026-08-30');
assert.equal(stats.lastPublished,'2026-09-11');
assert.equal(stats.checkedAt,'2026-09-12T10:35:00+00:00');
assert.equal(stats.failures,1);
const queue=discoveryQueueHTML(feed);
assert.match(queue,/待核驗發現/);
assert.match(queue,/不影響目前預測/);
assert.match(queue,/台北市長選舉/);
assert.match(queue,/pollster_id · pearson-data/);
const html=observatoryHTML(feed,model);
assert.match(html,/Poll Ingestion 2\.0 · Source Coverage v5\.3/);
assert.match(html,/發現 ≠ 入模/);
assert.match(html,/Pollster Registry 已登錄 7 個/);
assert.match(html,/pollster_id · ettoday/);
assert.match(html,/封閉式網路樣本/);
assert.match(html,/DMP網路樣本/);
assert.match(html,/自動發現＋人工核驗/);
assert.match(html,/4 發現 \/ 0 解析 \/ 2 核驗/);
assert.match(html,/方法已核對／回應類別不完整/);
assert.match(html,/fail-closed/);
assert.match(html,/待核驗發現/);
assert.match(html,/最近檢查/);
assert.match(html,/最近發布/);
assert.match(html,/2026-09-11/);
assert.match(html,/抓取／解析失敗/);
assert.match(html,/不代表新資料已入模/);
assert.match(html,/委託方不確定性/);
assert.match(html,/已標識 1 筆外部委託調查/);
assert.match(html,/0\.20/);
assert.match(html,/不是單筆調查固定乘以80%權重/);
assert.match(html,/原始民調數字不變/);

assert.ok(!html.includes('未接入</td>'));
const empty=discoveryQueueHTML({...feed,discovery_queue:[]});
assert.match(empty,/目前沒有新的/);
assert.match(empty,/佇列為空/);
const proofModel={nonmajor_poll_response_audit:{schema_version:1,
  kind:'nonmajor_survey_response_comparison_not_ballot_forecast_constraint',
  formal_forecast_modified:false,metrics_not_interchangeable:true,source_rows:1,rows:[{
  county:'台北市',date:'2026-10-25',source:'聯合報系民意調查中心',
  pollster_id:'udn-poll-center',source_url:'https://udn.com/news/story/124652/9840910',
  poll_nonmajor_support_upper_pct:1,poll_undecided_reported_pct:13,
  model_nonmajor_mean_ballot_pct:19.7,model_nonmajor_p05_ballot_pct:1,model_nonmajor_p95_ballot_pct:58,
  is_ballot_prediction_constraint:false,reweighted_or_redistributed_undecided:false,
  provenance:'first_party_reported_survey_responses_vs_uncalibrated_election_day_ballot_draws'
}]}};
const difference=nonmajorResponseHTML(proofModel);
assert.match(difference,/非藍綠候選人/);
assert.match(difference,/調查未表態/);
assert.match(difference,/&lt;1\.0%/);
assert.match(difference,/19\.7%/);
assert.match(difference,/差距不是預測誤差/);
assert.ok(!difference.includes('<script>'));
assert.match(observatoryHTML(feed,{...model,...proofModel}),/nonmajorResponseAudit/);
assert.equal(nonmajorResponseHTML({nonmajor_poll_response_audit:{...proofModel.nonmajor_poll_response_audit,formal_forecast_modified:true}}),'');
const noPromotion={
  schema_version:1,
  kind:'historical_t3_rolling_origin_research_no_2026_forecast_promotion',
  promotion_gate:{promote_to_formal_forecast:false,'2026_forecast_t3_parameters_changed':false},
  folds:[{target_year:2018},{target_year:2022}],
  scores:{
    '2018':{nonmajor_present_unique_pair:{models:{
      t3_blend_pct:{n:14,mae_pp:7.5,bias_pp:2,over_5pp:6,under_5pp:4},
      t3_raw_pct:{n:14,mae_pp:8},carry_pct:{n:14,mae_pp:9}}}},
    '2022':{nonmajor_present_unique_pair:{models:{
      t3_blend_pct:{n:13,mae_pp:6.9,bias_pp:1.5,over_5pp:4,under_5pp:2},
      t3_raw_pct:{n:13,mae_pp:6.1},carry_pct:{n:13,mae_pp:7.7}}}}
  },
  bootstrap:{cluster_combined:{ci95_low_pp:-1.2,ci95_high_pp:3.7}},
  largest_2022_overestimates:[{county:'台北市',actual_pct:1.8,t3_blend_pct:20,nonmajor_candidate_count:3}]
};
const holdoutHTML=nonmajorHistoricalHTML({nonmajor_historical_holdout:noPromotion});
assert.match(holdoutHTML,/歷史時間留出檢驗/);
assert.match(holdoutHTML,/2018/);
assert.match(holdoutHTML,/2022/);
assert.match(holdoutHTML,/9\.00pp/);
assert.match(holdoutHTML,/7\.50pp/);
assert.match(holdoutHTML,/非全案盲測/);
assert.match(holdoutHTML,/台北市/);
assert.match(holdoutHTML,/研究觀察 · 不調正式預測/);
assert.match(observatoryHTML(feed,{...model,nonmajor_historical_holdout:noPromotion}),/nonmajorHistoricalValidation/);
assert.equal(nonmajorHistoricalHTML({nonmajor_historical_holdout:{...noPromotion,promotion_gate:{promote_to_formal_forecast:true}}}),'');
const commissionAudit={kind:'commissioner_uncertainty_leave_one_group_out_read_only',
  read_only:true,affects_formal_forecast:false,not_partisan_bias_estimate:true,
  leave_one_commissioner_out:[{
    commissioner_id:'xinmin-association',source_labels:['信民協會／畢肯'],report_count:1,
    counties:[{county:'台中市',max_abs_shift_pp:3.45,candidates:[
      {name:'何欣純',with_all_pct:42.12,comparison_pct:38.67,difference_pp:3.45},
      {name:'江啟臣',with_all_pct:46.31,comparison_pct:47.66,difference_pp:-1.35}]}]
  }]
};
const commissionHTML=commissionerSensitivityHTML({commissioner_sensitivity:commissionAudit});
assert.match(commissionHTML,/委託方敏感度檢查/);
assert.match(commissionHTML,/台中市/);
assert.match(commissionHTML,/信民協會／畢肯/);
assert.match(commissionHTML,/何欣純 42.12% → 38.67%/);
assert.match(commissionHTML,/3.45 pp/);
assert.match(commissionHTML,/不是民調偏差估計/);
assert.match(observatoryHTML(feed,{...model,commissioner_sensitivity:commissionAudit}),/commissionerSensitivityAudit/);
assert.equal(commissionerSensitivityHTML({commissioner_sensitivity:{...commissionAudit,affects_formal_forecast:true}}),'');
assert.equal(commissionerSensitivityHTML({}),'');
console.log('source-v53-ui ok');
