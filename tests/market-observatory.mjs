import assert from 'node:assert/strict';
import {coverageRows, coverageOverrides, coveragePanel, marketPage, fusionEvidencePanel} from '../site/market-observatory.mjs';

const model = {
  generated_at: '2026-10-28T08:00:00Z', roster_as_of: '2026-09-07',
  poll_audit: [{county:'台北市',date:'2026-10-20',included:true},
               {county:'台北市',date:'2026-08-01',included:false}],
  counties: [
    {name:'台北市',candidates:[{name:'蔣萬安',probability:0.61},{name:'沈伯洋',probability:0.39}]},
    {name:'桃園市',candidates:[{name:'張善政',probability:0.9}]}
  ]
};
const rows=coverageRows(model);
assert.equal(rows.length,2);
assert.equal(rows[0].count,1);
assert.equal(rows[1].count,0);
assert.equal(coverageOverrides(model)['桃園市'].value,'無直接民調');
assert.match(coveragePanel(model), /1 \/ 2/);
assert.match(coveragePanel(model), /台北市/);

const snapshot={
  schema_version:1,status:'ok',checked_at:'2026-10-28T08:00:00Z',
  errors:[],history:[],
  events:[{county:'台北市',slug:'taipei-mayor-election-winner-20260813125857100',
    source_url:'https://polymarket.com/event/taipei-mayor-election-winner-20260813125857100',
    title:'Taipei Mayor Election Winner',stale:false,
    quote_as_of:'2026-10-28T07:55:00Z',
    volume_usd:15000,liquidity_usd:15000,
    outcomes:[{market_id:'200',name:'Chiang Wan-an',probability:0.65,spread:0.03},
              {market_id:'201',name:'Unmapped Candidate',probability:0.25,spread:0.08}]}]
};
const output=marketPage(snapshot,model);
assert.match(output,/預測市場觀察/);
assert.match(output,/蔣萬安/);
assert.match(output,/65.0%/);
assert.match(output,/\+4.0pp/);
assert.match(output,/未配對/);
assert.doesNotMatch(output,/<button[^>]*(?:buy|trade|order)|data-action=["']trade|wallet-connect/i);
const missing=marketPage(null,model);
assert.match(missing,/尚未成功核驗/);
console.log(JSON.stringify({passed:true,coverage_rows:rows.length,markets:1}));

const emptyEvidence=fusionEvidencePanel(null);
assert.match(emptyEvidence,/沒有由同一次網站建構/);
const archivedEvidence=fusionEvidencePanel({schema_version:1,snapshots:[{
  as_of:'2026-10-28T05:00:00Z',source_digest:'a'.repeat(64),
  included_races:1,excluded_races:1,races:[
    {county:'台北市',included:true,reason:'matched_and_quality_checked',candidates:[
      {name:'蔣萬安',probability:.6,fused_05:.62},{name:'沈伯洋',probability:.4,fused_05:.38}]},
    {county:'桃園市',included:false,reason:'來源不存在',candidates:[{name:'張善政',probability:1,fused_05:null}]}
  ]}]});
assert.match(archivedEvidence,/市場融合的歷史證據與研究審計/);
assert.match(archivedEvidence,/來源不存在/);
assert.match(archivedEvidence,/\+2.00pp/);
assert.match(archivedEvidence,/尚未提供/);
