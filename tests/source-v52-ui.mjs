import assert from 'node:assert/strict';
import {methodLabel,verificationLabel,reviewLabel,sourceState,coverageStats,observatoryHTML} from '../site/poll-source-v52.mjs';

assert.equal(methodLabel('closed_online_panel'),'封閉式網路樣本');
assert.equal(methodLabel('telephone_cati'),'電話訪問');
assert.equal(verificationLabel('reviewed_multi_source_methodology'),'多來源方法核驗');
assert.equal(reviewLabel('publisher_not_pollster'),'刊載媒體／不另建 pollster');
assert.deepEqual(sourceState({validated_reports:2,index_ok:true}),{key:'auto',label:'自動核驗'});
assert.deepEqual(sourceState({status:'reviewed_seed_only',reviewed_reports:1}),{key:'reviewed',label:'人工核驗種子'});
assert.deepEqual(sourceState({index_ok:false}),{key:'degraded',label:'來源受限'});

const feed={
  latest_fieldwork_date:'2026-08-30',
  sources:[
    {name:'ETtoday 民調雲',url:'https://example.com/e',reviewed_reports:2,validated_reports:0,index_ok:true,status:'checked',method_class:'closed_online_panel',note:'closed panel'},
    {name:'新台灣國策智庫／趨勢民調',url:'https://example.com/t',reviewed_reports:1,validated_reports:0,status:'reviewed_seed_only',method_class:'telephone_cati'}
  ],
  source_review:[{name:'艾普羅行銷市場研究',status:'reviewed_methodology_incomplete_response_mass',note:'37.7% response mass unresolved',url:'https://example.com/a'}],
  discovery_queue:[],
  records:[
    {id:'p1',source:'ETtoday 民調雲',pollster_id:'ettoday',method_class:'closed_online_panel'},
    {id:'p2',source:'新台灣國策智庫／趨勢民調',pollster_id:'trend-survey',method_class:'telephone_cati'}
  ]
};
const model={poll_audit:[{id:'p1',included:true},{id:'p2',included:true}]};
const stats=coverageStats(feed,model);
assert.equal(stats.sourceCount,2);
assert.equal(stats.methodCount,2);
assert.equal(stats.included,2);
assert.equal(stats.reviewQueue,1);
assert.equal(stats.latest,'2026-08-30');
const html=observatoryHTML(feed,model);
assert.match(html,/民調來源觀測站/);
assert.match(html,/pollster · ettoday/);
assert.match(html,/封閉式網路樣本/);
assert.match(html,/人工核驗種子/);
assert.match(html,/方法已核對／回應類別不完整/);
assert.match(html,/fail-closed/);
assert.ok(!html.includes('未接入</td>'));
console.log('source-v52-ui ok');
