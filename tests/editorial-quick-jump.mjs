import assert from 'node:assert/strict';
import {makeIndex,matchItems,buildDestination,formatFeedStatus} from '../site/editorial-quick-jump.mjs';

const data={counties:[
  {name:'台中市',candidates:[{name:'何欣純'},{name:'江啟臣'},{name:'洪麗華'}]},
  {name:'台北市',candidates:[{name:'蔣萬安'},{name:'沈伯洋'}]},
  {name:'臺南市',candidates:[{name:'測試候選人'}]}
]};
const index=makeIndex(data);
assert.equal(index.filter(x=>x.kind==='section').length,9);
assert.equal(index.filter(x=>x.kind==='county').length,3);
assert.deepEqual(matchItems(index,'何欣純').map(x=>x.county),['台中市']);
assert.deepEqual(matchItems(index,'臺中').map(x=>x.county),['台中市']);
assert.deepEqual(matchItems(index,'台南').map(x=>x.county),['臺南市']);
assert.ok(matchItems(index,'民調').some(x=>x.view==='polls'));
assert.ok(matchItems(index,'   ').length>0);
assert.equal(matchItems(index,'不可能的查詢字串').length,0);
assert.ok(matchItems(index,'台',2).length<=2);

const current='https://example.com/elections/?view=polls&county=台北市&level=town&town=大安區&s=KEEP#section';
const dest= new URL(buildDestination(current,matchItems(index,'何欣純')[0]));
assert.equal(dest.searchParams.get('view'),'counties');
assert.equal(dest.searchParams.get('county'),'台中市');
assert.equal(dest.searchParams.get('level'),'county');
assert.equal(dest.searchParams.get('election'),'2026-local');
assert.equal(dest.searchParams.get('s'),'KEEP');
assert.equal(dest.searchParams.has('town'),false);
assert.equal(dest.hash,'');
const other=new URL(buildDestination(current,matchItems(index,'模型驗證')[0]));
assert.equal(other.searchParams.get('view'),'validation');
assert.throws(()=>buildDestination(current,{view:'evil',kind:'section'}),/Invalid/);

const model={feed_checked_at:'2026-11-05T11:38:20+00:00'};
const live={checked_at:model.feed_checked_at,status:'degraded'};
assert.deepEqual(formatFeedStatus(live,{feed_checked_at:'old'}),{quality:'unknown',text:'資料版本核對中'});
assert.equal(formatFeedStatus(live,model).quality,'degraded');
assert.match(formatFeedStatus(live,model).text,/部分來源受限/);
assert.equal(formatFeedStatus({...live,status:'checked'},model).quality,'verified');
assert.match(formatFeedStatus({...live,status:'checked'},model).text,/資料已同步/);
assert.equal(formatFeedStatus({...live,checked_at:'invalid'},{feed_checked_at:'invalid'}).quality,'unknown');

console.log('editorial-quick-jump tests passed');
