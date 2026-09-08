/* Read-only cloud feed. Visitors' simulations remain private to their browser. */
(() => {
  'use strict';
  let feed=null, busy=false, offline=false, failure=false, selected='all';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const sourceURL=value=>{try{const u=new URL(value);return u.protocol==='https:'&&['www.tvbs.com.tw','www-asset.tvbs.com.tw','my-formosa.com.tw','www.my-formosa.com.tw'].includes(u.hostname)?u.href:'#';}catch{return '#';}};
  const displayTime=value=>value?new Date(value).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false}):'尚無成功紀錄';
  const valid=data=>{
    if(data?.schema_version!==1||!Array.isArray(data.records)||!Array.isArray(data.polls)||data.polls.length>100||data.records.length>10000)throw Error('資料格式不符');
    if(!Number.isFinite(Date.parse(data.checked_at)))throw Error('檢查時間無效');
    if(!Array.isArray(data.failures)||!Array.isArray(data.history)||!/^\d{4}-\d{2}-\d{2}$/.test(data.baseline_cutoff))throw Error('來源狀態格式不符');
    const recordIDs=new Set();
    for(const r of data.records){
      if(!/^[a-f0-9]{24}$/.test(r.id)||recordIDs.has(r.id)||!APP.order.includes(r.county)||!Array.isArray(r.candidates)||r.candidates.length<2||r.candidates.length>5||sourceURL(r.source_url)==='#')throw Error('來源紀錄無效');
      recordIDs.add(r.id);
      if(!r.candidates.every(c=>typeof c.name==='string'&&c.name.length<=30&&Number.isFinite(c.support)&&c.support>=0&&c.support<=100))throw Error('候選人資料無效');
      if(!Number.isFinite(r.nonvote??0)||(r.nonvote??0)<0||(r.nonvote??0)>100||!Number.isFinite(r.undecided)||r.undecided<0||r.undecided>100||Math.abs(r.candidates.reduce((s,c)=>s+c.support,r.undecided+(r.nonvote??0))-100)>2)throw Error('來源總和無效');
      if(!Number.isFinite(Date.parse(r.date))||!Number.isFinite(Date.parse(r.field_start)))throw Error('來源日期無效');
    }
    const ids=new Set();
    for(const p of data.polls){
      if(!APP.order.includes(p.county)||!/^[a-f0-9]{24}$/.test(p.id)||ids.has(p.id)||p.source!=='TVBS 民意調查中心')throw Error('民調識別不符');
      ids.add(p.id);
      if(!/^\d{4}-\d{2}-\d{2}$/.test(p.date)||p.date<=data.baseline_cutoff||Date.parse(p.date)>Date.now())throw Error('調查日期無效');
      const values=['blue','dpp','third','other','undecided'].map(k=>p[k]);
      if(values.some(x=>typeof x!=='number'||!Number.isFinite(x)||x<0||x>100)||Math.abs(values.reduce((a,b)=>a+b,0)-100)>2)throw Error('百分比無效');
      if(!Number.isFinite(p.sample_n)||p.sample_n<100||p.sample_n>100000)throw Error('樣本量無效');
      const origin=data.records.find(r=>r.id===p.id);
      if(!origin?.model_eligible||sourceURL(origin.source_url)==='#')throw Error('缺少通過校驗的原始來源');
    }
    return data;
  };
  function embargo(data){
    const now=Date.now();
    return now>=Date.parse(data.publication_pause_start)&&now<Date.parse(data.publication_pause_end);
  }
  function render(){
    if(!feed)return;
    const stale=Date.now()-Date.parse(feed.index_checked_at||feed.checked_at)>(feed.stale_after_hours||18)*3600000;
    const age=feed.latest_fieldwork_date?Math.floor((Date.now()-Date.parse(feed.latest_fieldwork_date))/86400000):null;
    const label=offline?'本機預覽':failure?'連線失敗，沿用已載入資料':stale?'來源檢查逾時':feed.status==='ok'?'自動檢查正常':'部分報告未通過校驗';
    const status=document.getElementById('publicPollStripStatus');
    status.textContent=label;status.dataset.state=(offline||failure||stale||feed.status!=='ok')?'warning':'ok';
    document.getElementById('publicPollStripDate').textContent='最新調查 '+(feed.latest_fieldwork_date||'尚無資料');
    document.getElementById('publicPollMetrics').innerHTML=[['最近來源檢查',feed.index_checked_at?displayTime(feed.index_checked_at):'尚未成功'],['最新調查結束',feed.latest_fieldwork_date||'尚無資料'],['資料庫題組',feed.records.length],['新增模型輸入',feed.polls.length]].map(([a,b])=>`<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join('');
    document.getElementById('publicPollArchiveTitle').textContent=`原始民調資料庫（${feed.records.filter(r=>selected==='all'||r.county===selected).length} 題）`;
    document.getElementById('publicPollHealth').textContent=`${label}。部署後排程每 ${feed.schedule_hours||6} 小時執行，頁面每 10 分鐘同步發布資料。來源沒有新報告時，調查日期不會變動。`;
    const warning=document.getElementById('publicPollWarning');
    warning.hidden=age===null||age<=45;
    warning.textContent=`目前資料庫最新調查距今 ${age} 天，不能視為即時民意；沒有新民調的縣市仍使用原有模型基線。`;
    const records=feed.records.filter(r=>selected==='all'||r.county===selected);
    document.getElementById('publicPollRecords').innerHTML=records.length?records.map(r=>{
      const details=[['調查期間',`${r.field_start} 至 ${r.date}`],['有效樣本',`${r.sample_n}；${r.sample_note}`],['調查母體',r.population],['抽樣方式',r.method],['抽樣誤差',`±${r.margin_of_error} 個百分點（${r.confidence_level}% 信心水準）；不是勝率誤差`],['經費來源',r.funding],['主持人',r.supervisor||'原報告未列，未推定'],['母體人數',r.population_size||'原報告未列，未推定']];
      return `<article class="public-poll-record"><h3>${esc(r.county)} <a href="${esc(sourceURL(r.source_url))}" target="_blank" rel="noopener noreferrer">${esc(r.source)} · ${esc(r.date)}</a></h3><div class="public-poll-values">${r.candidates.map(c=>`<span>${esc(c.name)}<strong>${esc(c.support)}%</strong></span>`).join('')}<span>未決定<strong>${esc(r.undecided)}%</strong></span>${r.nonvote!=null?`<span>不投票／廢票<strong>${esc(r.nonvote)}%</strong></span>`:''}</div><p>${r.model_eligible?'通過模型納入條件；同機構同縣市只採最新一期':esc(r.exclusion_reason)}</p><details><summary>調查方法與來源</summary><dl>${details.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl></details></article>`;
    }).join(''):'<p class="public-poll-empty">此縣市尚無可用的自動來源資料，不以模擬值代替民調。</p>';
    document.getElementById('publicPollAudit').innerHTML=`<summary>更新紀錄與未納入報告（${feed.failures.length}）</summary><p>資料異動：${esc(feed.updated_at?displayTime(feed.updated_at):'尚無')}。完整校驗成功：${esc(displayTime(feed.last_success_at))}。</p>`+
      feed.failures.slice(0,30).map(f=>`<p><a href="${esc(sourceURL(f.url))}" target="_blank" rel="noopener noreferrer">原始報告</a>：未通過解析或連線檢查，保留上一份有效資料。<br><small>${esc(f.message)}</small></p>`).join('')+
      feed.history.slice(0,10).map(h=>`<p>${esc(displayTime(h.date))} · ${esc(h.county)} · ${h.kind==='report_added'?'收錄原始報告':'原始報告異動'}</p>`).join('');
  }
  function apply(data){
    valid(data);
    if(embargo(data)){document.body.replaceChildren(Object.assign(document.createElement('p'),{textContent:'選前暫停發布民調及相關預測。投票結束後恢復。'}));return;}
    // Avoid rewriting model state on an unchanged feed, preserving focused simulation inputs.
    const signature=JSON.stringify(data.polls);
    if(signature!==window.__publicPollSignature){
      importExternalPollPayload({updated_at:data.updated_at,polls:data.polls});
      window.__publicPollSignature=signature;
    }
    feed=data;render();
  }
  async function reload(){
    if(busy)return 0;
    busy=true;
    try{
      if(location.protocol==='file:'){offline=true;render();return feed?.polls.length||0;}
      const response=await fetch('polls.json',{cache:'no-store',signal:AbortSignal.timeout(15000)});
      if(!response.ok)throw Error('HTTP '+response.status);
      const data=await response.json();
      valid(data);
      failure=false;offline=false;apply(data);
      return data.polls.length;
    }catch{
      failure=true;render();return 0;
    }finally{busy=false;}
  }
  function start(){
    const hero=document.getElementById('v12ForecastHero');
    const strip=document.createElement('div');strip.className='public-poll-strip';
    strip.innerHTML='<span class="public-poll-state" id="publicPollStripStatus" role="status">讀取民調來源</span><span id="publicPollStripDate"></span><a href="#publicPolls">自動民調與來源</a>';
    hero.before(strip);
    const section=document.createElement('section');section.id='publicPolls';section.setAttribute('aria-labelledby','publicPollTitle');
    section.innerHTML=`<header><div><h2 id="publicPollTitle">自動民調</h2><p>原始報告、調查日期與模型納入狀態</p></div><label>縣市 <select id="publicPollCounty"><option value="all">全部縣市</option>${APP.order.map(c=>`<option>${esc(c)}</option>`).join('')}</select></label></header><dl id="publicPollMetrics" class="public-poll-metrics"></dl><p id="publicPollHealth" role="status"></p><p id="publicPollWarning" class="public-poll-warning" hidden></p><p>目前自動來源：TVBS。原始百分比保留四捨五入差異；${esc(JSON.parse(document.getElementById('publicPollBootstrap').textContent).baseline_cutoff)} 以前的資料不重複加權。你的情境調整只保存在本機，不會改寫網站公用資料。</p><div id="publicPollRecords"></div><details id="publicPollAudit" class="public-poll-audit"></details>`;
    document.querySelector('#v12V14FeatureDeck').before(section);
    const archive=document.createElement('details');archive.className='public-poll-archive';
    const summary=Object.assign(document.createElement('summary'),{id:'publicPollArchiveTitle',textContent:'原始民調資料庫'});
    const records=document.getElementById('publicPollRecords');records.before(archive);archive.append(summary,records);
    document.getElementById('publicPollCounty').addEventListener('change',e=>{selected=e.target.value;archive.open=true;render();});
    document.querySelector('.v12-nav').append(Object.assign(document.createElement('a'),{href:'#publicPolls',textContent:'民調'}));
    document.getElementById('apiKey')?.closest('details')?.remove();
    const oldLoader=document.getElementById('reloadExternalPollsBtn');
    if(oldLoader){oldLoader.textContent='同步已發布民調';oldLoader.title='讀取網站後台已更新的資料';}
    for(const id of ['clearExternalPollsBtn']){const n=document.getElementById(id);if(n)n.hidden=true;}
    window.PublicPolls={reload};
    try{apply(JSON.parse(document.getElementById('publicPollBootstrap').textContent));}catch{failure=true;}
    reload();
    setInterval(()=>{if(!document.hidden)reload();},600000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)reload();});
    document.body.dataset.publicReady='true';
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
