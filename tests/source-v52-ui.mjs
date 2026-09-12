import assert from 'node:assert/strict';
import {methodLabel,verificationLabel,reviewLabel,ingestionLabel,sourceState,coverageStats,discoveryQueueHTML,observatoryHTML} from '../site/poll-source-v52.mjs';

assert.equal(methodLabel('closed_online_panel'),'封閉式網路樣本');
assert.equal(methodLabel('telephone_cati'),'電話訪問');
assert.equal(methodLabel('online_dmp_panel'),'DMP網路樣本');
assert.equal(verificationLabel('reviewed_multi_source_methodology'),'多來源方法核驗');
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
    {id:'p1',source:'ETtoday 民調雲',pollster_id:'ettoday',method_class:'closed_online_panel'},
    {id:'p2',source:'新台灣國策智庫／趨勢民調',pollster_id:'trend-survey',method_class:'telephone_cati'},
    {id:'p3',source:'鉅聞天下／皮爾森數據',pollster_id:'pearson-data',method_class:'online_dmp_panel'}
  ]
};
const model={poll_audit:[{id:'p1',included:true},{id:'p2',included:true},{id:'p3',included:true}]};
const stats=coverageStats(feed,model);
assert.equal(stats.sourceCount,3);
assert.equal(stats.registryCount,7);
assert.equal(stats.methodCount,3);
assert.equal(stats.included,3);
assert.equal(stats.discoveryQueue,1);
assert.equal(stats.reviewQueue,2);
assert.equal(stats.latest,'2026-08-30');
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
assert.ok(!html.includes('未接入</td>'));
const empty=discoveryQueueHTML({...feed,discovery_queue:[]});
assert.match(empty,/目前沒有新的/);
assert.match(empty,/佇列為空/);
console.log('source-v53-ui ok');
