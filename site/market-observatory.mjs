import {marketFusion} from './market-fusion.mjs';
import {jointMarketShadow} from './market-joint-shadow.mjs';
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
function eventCard(event,model,history,weight){
  const fusion=marketFusion(model,event,weight);
  const fused=new Map(fusion.eligible?fusion.probabilities.map(x=>[x.name,x]):[]);
  const race=(model?.counties||[]).find(x=>x.name===event.county);
  const candidates=new Map((race?.candidates||[]).map(c=>[c.name,c]));
  const rows=[...(event.outcomes||[])].sort((a,b)=>b.probability-a.probability).map(o=>{
    const chinese=alias[o.name],candidate=candidates.get(chinese),p=Number(candidate?.probability),matched=!!candidate&&Number.isFinite(p);
    const spread=o.spread==null?'未知':(o.spread*100).toFixed(1)+'¢';
    const shadow=fused.get(chinese);
    const trace=history.filter(x=>x.key===event.slug+'|'+o.market_id);
    return '<tr><td><b>'+esc(chinese||o.name)+'</b><small>'+esc(o.name)+'</small></td>'
     +'<td><strong>'+percent(o.probability)+'</strong><i class="market-bar"><b style="width:'+(100*o.probability).toFixed(2)+'%"></b></i></td>'
     +'<td>'+(matched?percent(p):'未配對')+'</td><td>'+(matched?((o.probability-p)*100>=0?'+':'')+((o.probability-p)*100).toFixed(1)+'pp':'—')+'</td>'
     +'<td>'+spread+'</td><td>'+(shadow?percent(shadow.fused):'—')+'</td><td>'+sparkline(trace)+'</td></tr>';
  }).join('');
  const url=/^https:\/\/polymarket\.com\/event\/[a-z0-9-]+$/.test(event.source_url||'')?event.source_url:'#';
  return '<article class="market-panel market-event" data-market-county="'+esc(event.county)+'"><header><div><small>'+esc(event.county)+' / '+(event.stale?'過往快照':'來源已核驗')+'</small><h2>'+esc(event.title)+'</h2></div><a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">市場來源及結算規則</a></header>'
   +'<div class="market-metadata"><span>總交易量 <b>'+compact(event.volume_usd)+'</b></span><span>流動性 <b>'+compact(event.liquidity_usd)+'</b></span><span>來源更新 <b>'+esc(dateLabel(event.quote_as_of))+'</b></span></div>'
   +(fusion.eligible?'<p class="market-note">融合試驗權重 '+Math.round(weight*100)+'%；不改變正式模型或得票率。</p>':'<p class="market-note">融合試驗不適用：'+esc(fusion.reason)+'。</p>')
   +(event.stale?'<p class="market-warning">來源暫未成功核驗，以下為最後有效快照，並非即時價格。</p>':'')
   +(event.data_quality==='thin'?'<p class="market-warning">成交量或流動性較低，報價參考價值有限。</p>':'')
   +'<div class="market-tablewrap"><table class="market-data-table"><thead><tr><th>選項</th><th>Yes價格</th><th>模型條件勝率</th><th>差額</th><th>買賣價差</th><th>融合試驗勝率</th><th>價格走勢</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
   +'<p class="market-note">Yes合約報價不保證合計100%；市場與模型數值的差額不代表統計誤差。未核實姓名配對的候選人不進行對照。</p></article>';
}
export function fusionEvidencePanel(archive){
  const snapshots=archive?.schema_version===1&&Array.isArray(archive.snapshots)?archive.snapshots:[];
  const recent=snapshots.at(-1);
  const rows=recent?.races||[];
  const reasons=new Map();
  for(const r of rows){
    if(!r.included)reasons.set(r.reason||'未標明原因',(reasons.get(r.reason||'未標明原因')||0)+1);
  }
  const exclusions=[...reasons.entries()].sort((a,b)=>b[1]-a[1]);
  const stat='<div class="market-summary">'
   +'<div><small>真正凍結的台北日曆日</small><strong>'+snapshots.length+'</strong></div>'
   +'<div><small>最近通過訊號核驗的選區</small><strong>'+(recent?.included_races??'—')+' / 22</strong></div>'
   +'<div><small>核驗排除的選區</small><strong>'+(recent?.excluded_races??'—')+'</strong></div>'
   +'<div><small>已發佈的選後評分</small><strong>尚未提供</strong></div></div>';
  const table=recent?'<div class="market-tablewrap"><table class="market-data-table"><thead><tr><th>縣市</th><th>模型凍結時間</th><th>信號資格</th><th>模型領先者</th><th>5% 融合差額</th></tr></thead><tbody>'
   +rows.map(r=>{
      const base=[...(r.candidates||[])].sort((a,b)=>b.probability-a.probability)[0];
      const shifted=base?.fused_05;
      return '<tr><td>'+esc(r.county)+'</td><td>'+esc(dateLabel(recent.as_of))+'</td>'
      +'<td>'+(r.included?'已配對／通過門檻':esc(r.reason||'不適用'))+'</td>'
      +'<td>'+esc(base?.name||'—')+'</td>'
      +'<td>'+(r.included&&Number.isFinite(shifted)?((shifted-base.probability)*100>=0?'+':'')+((shifted-base.probability)*100).toFixed(2)+'pp':'—')+'</td></tr>';
    }).join('')+'</tbody></table></div>':'<p class="market-note">還沒有由同一次網站建構與市場核驗形成的配對歷史記錄；不會用目前的行情推算過去日期。</p>';
  const exceptions=exclusions.length?'<details class="market-evidence-exceptions"><summary>未入選原因（'+exclusions.reduce((a,x)=>a+x[1],0)+'縣市）</summary>'
      +'<div class="market-tablewrap"><table class="market-data-table"><thead><tr><th>原因</th><th>縣市數</th></tr></thead><tbody>'
      +exclusions.map(([reason,count])=>'<tr><td>'+esc(reason)+'</td><td>'+count+'</td></tr>').join('')
      +'</tbody></table></div></details>':'';
  return '<section class="market-panel" id="marketFusionAudit"><header><div><small>FROZEN EVIDENCE · NO LOOK-AHEAD</small><h2>市場融合的歷史證據與研究審計</h2></div></header>'
    +'<p>同一建構時點配對模型條件勝率、原始合約價格和實驗結果。每天僅保留台北時間當日最後一次成功建構，保留來源時間、版本與候選人識別，供選後按相同資訊截止時間比較。</p>'
    +stat
    +(recent?'<p class="market-note">最近紀錄：'+esc(dateLabel(recent.as_of))+' · 來源記錄 SHA256 '+esc(recent.source_digest?.slice(0,14)||'—')+'…</p>':'')
    +exceptions+table
    +'<p class="market-warning">2026年11月28日選舉尚未舉行。現在沒有正式結算結果，不能顯示「Brier改善」或宣稱哪個權重較準。選後只使用當日之前實際已保存、且能匹配中選會正式結果的樣本。</p></section>';
}

// Original Monte Carlo paths are reweighted jointly, preserving their
// across-county dependency rather than summing disconnected local estimates.
export function jointShadowPanel(model,market,weight){
  const shadow=jointMarketShadow(model,market,weight);
  const header='<section class="market-panel market-joint-shadow" id="marketJointSensitivity">'
      +'<header><div><small>JOINT MONTE CARLO · RESEARCH SHADOW</small><h2>市場訊號下的22縣市聯合席次敏感度</h2></div></header>'
      +'<p>不是立法院席次：此表計算的是22個縣市長選舉中，各政黨／無黨籍候選人勝選的縣市數。保留 HB-TLEF 原始模擬路徑之間的相關性，只用合約核驗通過的選區進行小幅重要性重加權。</p>';
  if(!shadow.available)return header+'<p class="market-warning">聯合敏感度不可顯示：'+esc(shadow.reason)+'。原始模型數據仍保持有效且不受影響。</p></section>';
  const stats=shadow.diagnostics;
  const make=(v,dp=2)=>Number(v).toFixed(dp);
  const delta=v=>(v>=0?'+':'')+make(v);
  const table=shadow.national.map(x=>'<tr><td><b>'+esc(x.name)+'</b></td>'
    +'<td>'+make(x.baseline_mean)+'</td><td><strong>'+make(x.mean)+'</strong></td>'
    +'<td>'+delta(x.delta_mean)+'</td><td>'+x.p05+'—'+x.p95+'</td>'
    +'<td>'+make(x.majority_probability*100,1)+'%</td></tr>').join('');
  const exclusions=shadow.checks.filter(x=>!x.eligible);
  return header
    +'<div class="market-summary">'
    +'<div><small>核驗通過的縣市</small><strong>'+stats.eligible_count+' / 22</strong></div>'
    +'<div><small>研究加權強度</small><strong>'+make(weight*100,0)+'%</strong></div>'
    +'<div><small>有效模擬數（ESS）</small><strong>'+make(stats.effective_sample_size,0)+' / '+stats.simulations+'</strong></div>'
    +'<div><small>最大單一路徑權重</small><strong>'+make(stats.max_path_weight*100,2)+'%</strong></div></div>'
    +'<div class="market-tablewrap"><table class="market-data-table"><thead><tr><th>政治分類</th><th>原模型預期縣市數</th><th>聯合試驗預期縣市數</th><th>差異</th><th>5%—95%席次區間</th><th>至少12縣市機率</th></tr></thead><tbody>'+table+'</tbody></table></div>'
    +(exclusions.length?'<details class="market-evidence-exceptions"><summary>檢視未納入聯合重加權的 '+exclusions.length+' 個縣市</summary><div class="market-tablewrap"><table class="market-data-table"><thead><tr><th>縣市</th><th>排除原因</th></tr></thead><tbody>'+exclusions.map(x=>'<tr><td>'+esc(x.county)+'</td><td>'+esc(x.reason)+'</td></tr>').join('')+'</tbody></table></div></details>':'')
    +'<p class="market-warning">重要性重加權並非已訓練或經校準的聯合後驗。市場可能轉述民調與新聞，兩者並非獨立訊息。此結果不改寫正式網站地圖、候選人得票率、席次或發布版勝率；有效樣本數低於20%或單一路徑權重高於5%即拒絕發布試驗結果。</p></section>';
}

export function marketPage(snapshot,model,weight=0.05,archive=null){
  const d=snapshot?.schema_version===1?snapshot:{status:'unavailable',events:[],history:[],errors:[]};
  const events=d.events||[],fresh=events.filter(x=>!x.stale);
  const option=[...new Set(events.map(x=>x.county))].sort().map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');
  return '<section class="market-observatory"><header class="market-intro"><small>PREDICTION MARKET OBSERVATORY · READ ONLY</small><h1>預測市場觀察</h1><p>查看臺灣地方選舉公開合約價格、交易活躍程度與模型估計的差異。只讀研究資料，無下注、錢包、交易或下單功能；不影響HB-TLEF正式預測。</p></header>'
   +'<div class="market-summary"><div><small>已驗證市場縣市</small><strong>'+new Set(fresh.map(x=>x.county)).size+' / 22</strong></div><div><small>已核驗市場</small><strong>'+fresh.length+'</strong></div><div><small>存檔／來源故障</small><strong>'+(events.length-fresh.length)+' / '+(d.errors||[]).length+'</strong></div><div><small>快照檢查（台北）</small><strong class="market-time">'+esc(dateLabel(d.checked_at))+'</strong></div></div>'
   +'<p class="market-warning">市場價格不是民調支持率，也不是已校準的勝選機率。須注意合約選項、買賣價差、交易深度、交易限制及來源時間。資料只用於觀察與研究，不提供交易建議。</p>'
   +(d.status!=='ok'?'<p class="market-warning">來源狀態：'+esc(d.status||'unavailable')+'。缺值不填入估測價格。</p>':'')
   +(events.length?'':'<section class="market-panel"><h2>市場資料尚未成功核驗</h2><p>等待公開來源同步；未使用模擬行情。</p></section>')
   +'<div class="market-controls"><label for="marketCounty">縣市</label><select id="marketCounty"><option value="all">全部</option>'+option+'</select><small>無市場不代表沒有選舉，歷史快照不代表即時盤口。</small></div>'
   +'<section class="market-panel market-fusion-control"><h2>市場信號融合 · 試驗版本</h2><p>以模型勝率及候選人市場 Yes 合約價格進行對數機率融合；並非把市場價格當作候選人得票率。研究權重尚未經獨立週期校準，融合數字不改動正式 HB-TLEF 模型、得票率或全國席次分布。</p><label for="marketWeight">市場試驗權重</label> <select id="marketWeight">'+[0,0.05,0.10].map(w=>'<option value="'+w+'" '+(w===weight?'selected':'')+'>'+Math.round(w*100)+'%'+(w===0?'（不融合）':'')+'</option>').join('')+'</select><p class="market-note">僅對候選人名單高度匹配、近期報價、流動性及買賣價差均通過門檻的選區產生融合勝率。</p></section>'
   +jointShadowPanel(model,d,weight)
   +fusionEvidencePanel(archive)
   +'<div id="marketEventList">'+events.map(x=>eventCard(x,model,d.history||[],weight)).join('')+'</div>'
   +'<section class="market-panel"><h2>資料與法律說明</h2><p>來源為<a href="https://docs.polymarket.com/" rel="noopener noreferrer" target="_blank">Polymarket Gamma 公開唯讀接口</a>。採排程快照，資料不一定即時，也不是完整訂單簿；失敗時保留舊值並標記。選前全站暫停發布政策同樣適用本頁。</p><p>目前不將市場資料合併進統計模型、不做依價格推測選民群體的分析，也不提供交易功能。不同市場的結算條款應逐一核對。</p></section></section>';
}
