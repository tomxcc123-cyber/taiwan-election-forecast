// Read-only election market research and evidence coverage. No order or trading APIs.
const esc = v => String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const percent = v => Number.isFinite(Number(v)) ? (Number(v)*100).toFixed(1)+'%' : '—';
const compact = v => Number.isFinite(Number(v)) ? new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(Number(v))+' USD' : '未提供';
const dateLabel = v => {if(!v)return '尚未核對';const d=new Date(v);return Number.isFinite(d.getTime())?d.toLocaleString('zh-TW',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit'}):'尚未核對';};
const alias = {
  'Chiang Wan-an':'蔣萬安','Puma Shen':'沈伯洋','Kuo Hsi':'郭璽',
  'Su Chiao-hui':'蘇巧慧','Lee Shu-chuan':'李四川',
  'Chang San-cheng':'張善政','Huang Shih-chieh':'黃世杰',
  'Johnny Chiang':'江啟臣','Ho Hsin-chun':'何欣純',
  'Lai Jui-lung':'賴瑞隆','Ko Chih-en':'柯志恩',
  'Ann Kao':'高虹安','Chuang Ching-cheng':'莊競程',
  'Hsu Hsin-ying':'徐欣瑩','Cheng Chao-fang':'鄭朝方',
  'Chung Tung-chin':'鍾東錦','Chen Pin-an':'陳品安',
  'Hsieh Kuo-liang':'謝國樑','Tung Tzu-wei':'童子瑋',
  'Lin Kuo-chang':'林國漳','Wu Tsung-hsien':'吳宗憲',
  'Chen Su-yueh':'陳素月','Wei Ping-cheng':'魏平政',
  'Wang Mei-hui':'王美惠','Chang Chi-kai':'張啓楷',
  'Chou Chun-mi':'周春米','Su Ching-chuan':'蘇清泉'
};

export function coverageRows(model){
  const audit=model?.poll_audit||[],asof=Date.parse(model?.generated_at||'');
  return (model?.counties||[]).map(r=>{
    const rows=audit.filter(x=>x.included&&x.county===r.name),latest=rows.map(x=>x.date).sort().at(-1)||null;
    const days=latest&&Number.isFinite(asof)?Math.max(0,Math.floor((asof-Date.parse(latest+'T00:00:00Z'))/86400000)):null;
    return {county:r.name,count:rows.length,latest,days};
  });
}
export function coverageOverrides(model){
  return Object.fromEntries(coverageRows(model).map(r=>[r.county,{
    fill:r.count===0?'#9aa8b9':r.days>45?'#b88d4a':r.count>=2?'#176e68':'#4aa89c',
    opacity:r.count===0?0.36:0.82,
    value:r.count?r.count+' 題 / '+r.latest:'無直接民調',
    evidence:r.count?'已配對民調':'未覆蓋',elevation:130+r.count*140
  }]));
}
export function coveragePanel(model){
  const rows=coverageRows(model),covered=rows.filter(x=>x.count).length;
  const body=rows.map(r=>'<tr><td><a href="?view=counties&county='+encodeURIComponent(r.county)+'">'+esc(r.county)+'</a></td><td>'+r.count+'題</td><td>'+esc(r.latest||'—')+'</td><td>'+esc(r.count?(r.days>45?'較舊／'+r.days+'天前':'有直接民調／'+r.days+'天前'):'無直接民調，僅基本面及其他證據')+'</td></tr>').join('');
  return '<section class="market-panel evidence-coverage"><header><div><small>DATA COVERAGE · GIS</small><h2>22 縣市民調資料覆蓋</h2></div></header>'
    +'<div class="market-summary"><div><small>有直接民調</small><strong>'+covered+' / '+rows.length+'</strong></div>'
    +'<div><small>無直接民調</small><strong>'+(rows.length-covered)+'</strong></div>'
    +'<div><small>登記名單版本</small><strong>'+esc(model?.roster_as_of||'未提供')+'</strong></div></div>'
    +'<p class="market-note">僅統計候選人模型審計已納入的觀測。不等於獨立選舉數；未有直接民調不代表沒有模型預測。總覽地圖可切換「覆蓋」圖層。</p>'
    +'<div class="market-tablewrap"><table class="market-data-table"><thead><tr><th>縣市</th><th>模型觀測</th><th>最近訪查結束</th><th>資料條件</th></tr></thead><tbody>'+body+'</tbody></table></div></section>';
}
function sparkline(points){
  if(points.length<2)return '<small class="market-muted">快照累積中</small>';
  const values=points.slice(-30).map(x=>Number(x.probability)).filter(Number.isFinite);
  if(values.length<2)return '<small class="market-muted">快照不足</small>';
  const low=Math.max(0,Math.min(...values)-.03),span=Math.max(.02,Math.min(1,Math.max(...values)+.03)-low);
  const d=values.map((v,i)=>(i?'L':'M')+(8+i*180/(values.length-1)).toFixed(1)+','+(46-(v-low)/span*35).toFixed(1)).join(' ');
  return '<svg class="market-spark" viewBox="0 0 196 54" role="img" aria-label="歷史價格快照"><path d="'+d+'" fill="none" stroke="#198778" stroke-width="2.4"/></svg>';
}
function eventCard(event,model,history){
  const race=(model?.counties||[]).find(x=>x.name===event.county);
  const candidates=new Map((race?.candidates||[]).map(c=>[c.name,c]));
  const rows=[...(event.outcomes||[])].sort((a,b)=>b.probability-a.probability).map(o=>{
    const chinese=alias[o.name],candidate=candidates.get(chinese),p=Number(candidate?.probability),matched=!!candidate&&Number.isFinite(p);
    const spread=o.spread==null?'未知':(o.spread*100).toFixed(1)+'¢';
    const trace=history.filter(x=>x.key===event.slug+'|'+o.market_id);
    return '<tr><td><b>'+esc(chinese||o.name)+'</b><small>'+esc(o.name)+'</small></td>'
     +'<td><strong>'+percent(o.probability)+'</strong><i class="market-bar"><b style="width:'+(100*o.probability).toFixed(2)+'%"></b></i></td>'
     +'<td>'+(matched?percent(p):'未配對')+'</td><td>'+(matched?((o.probability-p)*100>=0?'+':'')+((o.probability-p)*100).toFixed(1)+'pp':'—')+'</td>'
     +'<td>'+spread+'</td><td>'+sparkline(trace)+'</td></tr>';
  }).join('');
  const url=/^https:\/\/polymarket\.com\/event\/[a-z0-9-]+$/.test(event.source_url||'')?event.source_url:'#';
  return '<article class="market-panel market-event" data-market-county="'+esc(event.county)+'"><header><div><small>'+esc(event.county)+' / '+(event.stale?'過往快照':'來源已核驗')+'</small><h2>'+esc(event.title)+'</h2></div><a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">市場來源及結算規則</a></header>'
   +'<div class="market-metadata"><span>總交易量 <b>'+compact(event.volume_usd)+'</b></span><span>流動性 <b>'+compact(event.liquidity_usd)+'</b></span><span>來源更新 <b>'+esc(dateLabel(event.quote_as_of))+'</b></span></div>'
   +(event.stale?'<p class="market-warning">來源暫未成功核驗，以下為最後有效快照，並非即時價格。</p>':'')
   +(event.data_quality==='thin'?'<p class="market-warning">成交量或流動性較低，報價參考價值有限。</p>':'')
   +'<div class="market-tablewrap"><table class="market-data-table"><thead><tr><th>選項</th><th>Yes價格</th><th>模型條件勝率</th><th>差額</th><th>買賣價差</th><th>價格走勢</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
   +'<p class="market-note">Yes合約報價不保證合計100%；市場與模型數值的差額不代表統計誤差。未核實姓名配對的候選人不進行對照。</p></article>';
}
export function marketPage(snapshot,model){
  const d=snapshot?.schema_version===1?snapshot:{status:'unavailable',events:[],history:[],errors:[]};
  const events=d.events||[],fresh=events.filter(x=>!x.stale);
  const option=[...new Set(events.map(x=>x.county))].sort().map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');
  return '<section class="market-observatory"><header class="market-intro"><small>PREDICTION MARKET OBSERVATORY · READ ONLY</small><h1>預測市場觀察</h1><p>查看臺灣地方選舉公開合約價格、交易活躍程度與模型估計的差異。只讀研究資料，無下注、錢包、交易或下單功能；不影響HB-TLEF正式預測。</p></header>'
   +'<div class="market-summary"><div><small>已驗證市場縣市</small><strong>'+new Set(fresh.map(x=>x.county)).size+' / 22</strong></div><div><small>已核驗市場</small><strong>'+fresh.length+'</strong></div><div><small>存檔／來源故障</small><strong>'+(events.length-fresh.length)+' / '+(d.errors||[]).length+'</strong></div><div><small>快照檢查（台北）</small><strong class="market-time">'+esc(dateLabel(d.checked_at))+'</strong></div></div>'
   +'<p class="market-warning">市場價格不是民調支持率，也不是已校準的勝選機率。須注意合約選項、買賣價差、交易深度、交易限制及來源時間。資料只用於觀察與研究，不提供交易建議。</p>'
   +(d.status!=='ok'?'<p class="market-warning">來源狀態：'+esc(d.status||'unavailable')+'。缺值不填入估測價格。</p>':'')
   +(events.length?'':'<section class="market-panel"><h2>市場資料尚未成功核驗</h2><p>等待公開來源同步；未使用模擬行情。</p></section>')
   +'<div class="market-controls"><label for="marketCounty">縣市</label><select id="marketCounty"><option value="all">全部</option>'+option+'</select><small>無市場不代表沒有選舉，歷史快照不代表即時盤口。</small></div>'
   +'<div id="marketEventList">'+events.map(x=>eventCard(x,model,d.history||[])).join('')+'</div>'
   +'<section class="market-panel"><h2>資料與法律說明</h2><p>來源為<a href="https://docs.polymarket.com/" rel="noopener noreferrer" target="_blank">Polymarket Gamma 公開唯讀接口</a>。採排程快照，資料不一定即時，也不是完整訂單簿；失敗時保留舊值並標記。選前全站暫停發布政策同樣適用本頁。</p><p>目前不將市場資料合併進統計模型、不做依價格推測選民群體的分析，也不提供交易功能。不同市場的結算條款應逐一核對。</p></section></section>';
}
