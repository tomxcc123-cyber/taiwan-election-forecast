const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const num=(value,digits=2)=>Number(value).toFixed(digits);
const pct=value=>`${num(Number(value)*100,1)}%`;
const dateLabel=value=>{try{return new Date(value).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false});}catch{return String(value||'');}};

export function validationRows(v5={}){
  const confirm=v5.confirmatory_reference_2022||{};
  const chrono=v5.candidate_offset_chronological_2022||{};
  const dev=v5.end_to_end_development_2022||{};
  return [
    {
      id:'confirmatory',
      label:'確認性參考',
      model:confirm.model||'v4.0 selective RC3',
      mae:confirm.race_balanced_mae_pp,
      winners:confirm.winner_correct,
      total:confirm.winner_total,
      margin:confirm.margin_mae_pp,
      note:'較早凍結、未使用後續 fragmentation 開發結果；作為目前最乾淨的 2022 參考。'
    },
    {
      id:'chronological',
      label:'候選人層時間留出',
      model:'R4 + frozen candidate residual offset',
      mae:chrono.integrated_offset_mae_pp,
      winners:chrono.integrated_winner_correct,
      total:chrono.winner_total,
      margin:null,
      note:'特徵範圍只用 2018 選擇後再評分 2022；但整個專案先前看過 2022，並非 project-wide pristine holdout。'
    },
    {
      id:'development',
      label:'v5 完整開發診斷',
      model:'HB-TLEF v5 end-to-end',
      mae:dev.v5_race_balanced_mae_pp,
      winners:dev.v5_winner_correct,
      total:dev.winner_total,
      margin:dev.v5_margin_mae_pp,
      note:'完整候選人層包含後續 fragmentation 架構，因此只屬 development diagnostic，不能冒充盲測。'
    }
  ];
}

export function competitionBucket(race){
  const grade=race?.quality?.evidence?.grade||'C';
  if(grade==='D')return '暫不評級';
  const ranked=[...(race?.candidates||[])].sort((a,b)=>Number(b.mean)-Number(a.mean));
  if(ranked.length<2)return '單一人選';
  const gap=Number(ranked[0].mean)-Number(ranked[1].mean);
  const p=Number(ranked[0].probability||0);
  if(gap<=4||p<0.62)return '激烈競爭';
  if(gap<=8||p<0.75)return '競爭';
  if(gap<=15||p<0.90)return '傾向領先';
  return '明顯領先';
}

export function evidenceBucket(race){
  const grade=race?.quality?.evidence?.grade||'C';
  return ({A:'A · 近期直接民調',B:'B · 有直接民調',C:'C · 資料有限',D:'D · 模型缺項'})[grade]||`${grade} · 未分類`;
}

export function replayRows(snapshot){
  return (snapshot?.counties||[]).map(race=>{
    const ranked=[...(race.candidates||[])].sort((a,b)=>Number(b.probability??b.mean)-Number(a.probability??a.mean));
    const leader=ranked[0]||{};
    return {county:race.name,leader:leader.name||'—',mean:Number(leader.mean||0),probability:Number(leader.probability||0)};
  });
}

function validationHTML(model,research){
  const v5=model.v5_validation||research?.v5_validation||{};
  const rows=validationRows(v5);
  const current=rows.find(r=>r.id==='development')||{};
  const confirm=rows.find(r=>r.id==='confirmatory')||{};
  return `<section class="gov-validation" id="v5ValidationTruth">
    <div class="gov-kicker">CURRENT MODEL VALIDATION · ${esc(model.model_id)}</div>
    <div class="gov-validation-head"><div><h2>先分清「確認性驗證」與「開發診斷」</h2><p>頁面主驗證改讀 <code>v5_validation</code>。舊版 <code>backtest</code> 不再作為現行 HB-TLEF v5 的首頁成績單。</p></div><span class="gov-chip warn">勝率未完成跨屆校準</span></div>
    <div class="gov-score-grid">
      <article><span>確認性參考 · 2022</span><strong>${confirm.mae==null?'—':num(confirm.mae)}<small> pp race MAE</small></strong><p>${confirm.winners??'—'}/${confirm.total??'—'} 赢家 · margin MAE ${confirm.margin==null?'—':num(confirm.margin)}pp</p></article>
      <article><span>目前 v5 · 2022 開發診斷</span><strong>${current.mae==null?'—':num(current.mae)}<small> pp race MAE</small></strong><p>${current.winners??'—'}/${current.total??'—'} 赢家 · margin MAE ${current.margin==null?'—':num(current.margin)}pp</p></article>
      <article><span>概率狀態</span><strong>Conditional<small> / uncalibrated</small></strong><p>勝率是目前模型與誤差假設下的條件概率，不是已校準的真實事件頻率。</p></article>
    </div>
    <div class="gov-validation-tracks">${rows.map(row=>`<article class="gov-track ${row.id}"><span class="gov-chip">${esc(row.label)}</span><h3>${esc(row.model)}</h3><div class="gov-track-metrics"><b>${row.mae==null?'—':num(row.mae)}pp</b><small>MAE</small><b>${row.winners??'—'}/${row.total??'—'}</b><small>赢家</small></div><p>${esc(row.note)}</p></article>`).join('')}</div>
    <div class="gov-caution"><strong>不確定性仍是 v5 的主要研究缺口。</strong><span>現行產品把歷史模擬分布重定到 R4＋候選人 residual offset＋T3 的新中心；新結構層、候選人層與第三方層的參數估計誤差尚未以完整 bootstrap / posterior 方式傳播到最終勝率。因此 MAE 改善不能被用來證明 85% 等概率已可靠校準。</span></div>
    <details><summary>下一輪統一驗證標準</summary><p>歷史回測與線上預測將使用同一套引擎與同一資料截止規則，採 rolling-origin 時間驗證；同時報告 MAE、margin MAE、區間覆蓋率、平均區間寬度、Brier、log loss 與 reliability diagram。Brier 下降本身不等同於完成校準。</p></details>
  </section>`;
}

function ratingsHTML(result){
  const races=result?.counties||[];
  const comp=['激烈競爭','競爭','傾向領先','明顯領先','暫不評級','單一人選'];
  const grades=['A · 近期直接民調','B · 有直接民調','C · 資料有限','D · 模型缺項'];
  const list=(labels,fn)=>labels.map(label=>`<section><h3>${esc(label)}</h3><div>${races.filter(r=>fn(r)===label).map(r=>{const leader=[...(r.candidates||[])].sort((a,b)=>Number(b.mean)-Number(a.mean))[0]||{};return `<button class="link" data-county="${esc(r.name)}">${esc(r.name)}<small>${esc(leader.name||'—')} · ${num(leader.mean||0,1)}%</small></button>`;}).join('')||'<p class="meta">目前無縣市</p>'}</div></section>`).join('');
  return `<div class="gov-ratings-split"><div><div class="section-heading"><h2>競爭程度</h2><small>只看差距與模型條件機率</small></div><p class="meta">不再把「資料不足」直接等同於五五波。</p><div class="gov-rating-grid">${list(comp,competitionBucket)}</div></div><div><div class="section-heading"><h2>證據品質</h2><small>與競爭程度分開評級</small></div><p class="meta">A/B/C/D 只描述可用證據，不代表藍綠優勢。</p><div class="gov-rating-grid evidence">${list(grades,evidenceBucket)}</div></div></div>`;
}

function replayHTML(history,selected){
  const snapshots=[...(history?.snapshots||[])].sort((a,b)=>Date.parse(b.generated_at)-Date.parse(a.generated_at));
  if(!snapshots.length)return '<section class="gov-replay"><h2>歷史快照</h2><p class="empty">尚無已存預測快照。</p></section>';
  const index=Math.max(0,Math.min(Number(selected)||0,snapshots.length-1));
  const snap=snapshots[index];
  const rows=replayRows(snap);
  return `<section class="gov-replay" id="historicalReplay"><div class="section-heading"><div><span class="gov-kicker">STORED SNAPSHOT REPLAY</span><h2>歷史 22 縣市快照</h2></div><label>快照<select id="govReplaySelect">${snapshots.map((s,i)=>`<option value="${i}" ${i===index?'selected':''}>${esc(dateLabel(s.generated_at))} · ${esc(s.model_version)}</option>`).join('')}</select></label></div><p class="meta">這裡直接讀取當時保存的 22 縣市摘要，不再沿用目前地圖顏色或目前匯總數字。存檔未保存完整 Monte Carlo draws，因此稱為「快照回放」，不是事後重跑的完整歷史 forecast。</p><div class="gov-replay-meta"><span>${esc(snap.model_version)}</span><span>${rows.length} 縣市</span><span>${(snap.poll_ids||[]).length} 個當時納入 poll IDs</span></div><div class="table-wrap"><table><thead><tr><th>縣市</th><th>當時模型首位</th><th>當時均值得票</th><th>當時條件勝率</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.county)}</td><td>${esc(r.leader)}</td><td>${num(r.mean,1)}%</td><td>${pct(r.probability)}</td></tr>`).join('')}</tbody></table></div></section>`;
}

function methodsHTML(model){
  const bridge=model?.structural_model?.current_features?.organization_bridge||{};
  const vintage=bridge.organization_feature_vintage ?? model?.counties?.find(r=>r.v5_structural?.organization_feature_vintage)?.v5_structural?.organization_feature_vintage ?? 2018;
  const gate=model?.fragmentation_gate||{};
  return `<section class="gov-method-audit" id="governanceMethodAudit"><span class="gov-kicker">DATA / RULE GOVERNANCE</span><h2>兩個容易被誤讀的口徑</h2><div class="gov-method-grid"><article><span>地方組織變數</span><strong>${esc(vintage)} vintage</strong><p>2026 結構層目前承接的是 2018 年地方議員／鄉鎮組織快照。檔名中的「2022」描述後續特徵檔，不代表已使用 2022 議員或鄉鎮市長資料。</p></article><article><span>TVBS 40% fragmentation 規則</span><strong>${gate.status==='shadow_only'?'Shadow only':'Public Beta rule'}</strong><p>${gate.status==='shadow_only'?'只做影子診斷，不再二次改寫公開 posterior；另設 60 天新鮮度門檻。':'目前仍可能重定 posterior，屬 Public Beta 研究規則。'}</p></article><article><span>勝率不確定性</span><strong>尚未完整重建</strong><p>目前尚未把 R4、候選人 residual offset 與 T3 的參數估計誤差完整傳到勝率；因此網站只稱「模型條件機率」。</p></article></div></section>`;
}

let model=null,research=null,history=null,replayIndex=0,applying=false,queued=false;
function view(){return new URL(location.href).searchParams.get('view')||'overview';}
function compactRelease(){
  const strip=document.querySelector('.release-strip');
  if(!strip||strip.dataset.gov56)return;
  strip.dataset.gov56='1';
  strip.innerHTML='<strong>HB-TLEF v5.0 Public Beta 1</strong><span class="gov-chip">現行模型</span><span class="gov-chip warn">概率未校準</span><span class="gov-chip neutral">fragmentation hard gate：shadow</span><a href="MODEL_CARD_V5_PUBLIC_BETA.md" target="_blank" rel="noopener">模型卡</a>';
}
function patchValidation(page){
  if(page.querySelector('#v5ValidationTruth'))return;
  const head=page.querySelector('.page-head');
  if(head)head.insertAdjacentHTML('afterend',validationHTML(model,research));
  const legacyCard=page.querySelector('.validation-report');if(legacyCard)legacyCard.hidden=true;
  const old=page.querySelector('#candidateValidation');if(old)old.hidden=true;
  [...page.querySelectorAll('section.history')].forEach(section=>{const h2=section.querySelector(':scope > h2');if(h2?.textContent.trim()==='預測與實際')section.hidden=true;});
}
function patchOverview(page){
  const head=page.querySelector('.page-head');
  if(head&&!page.querySelector('#govOverviewStatus'))head.insertAdjacentHTML('afterend',`<div class="gov-overview-status" id="govOverviewStatus"><span>${esc(model.model_id)}</span><b>Public Beta</b><span>勝率：未跨屆校準</span><span>組織資料：2018 vintage</span></div>`);
  const summary=page.querySelector('.summary-band'),warning=page.querySelector('.warning'),map=page.querySelector('.map-desk'),brief=page.querySelector('.election-brief');
  if(summary&&head){const status=page.querySelector('#govOverviewStatus');status?.after(summary);if(warning)summary.after(warning);if(map&&warning)warning.after(map);if(brief&&map)map.after(brief);}
  const ratings=page.querySelector('.ratings');if(ratings&&!ratings.dataset.gov56){ratings.dataset.gov56='1';ratings.innerHTML=ratingsHTML(window.CandidateApp?.result);}
}
function patchUpdates(page){
  if(page.querySelector('#historicalReplay'))return;
  const head=page.querySelector('.page-head');if(head)head.insertAdjacentHTML('afterend',replayHTML(history,replayIndex));
}
function patchMethods(page){
  if(page.querySelector('#governanceMethodAudit'))return;
  const head=page.querySelector('.page-head');if(head)head.insertAdjacentHTML('afterend',methodsHTML(model));
}
function apply(){
  if(applying||!model)return;applying=true;
  try{compactRelease();const page=document.querySelector('#page');if(!page)return;const v=view();if(v==='validation')patchValidation(page);else if(v==='overview')patchOverview(page);else if(v==='updates')patchUpdates(page);else if(v==='methods')patchMethods(page);}finally{applying=false;}
}
function schedule(){if(queued)return;queued=true;queueMicrotask(()=>{queued=false;apply();});}
async function get(path){const response=await fetch(path,{cache:'no-store'});if(!response.ok)throw new Error(`${path} unavailable`);return response.json();}
async function boot(){
  try{
    [model,research,history]=await Promise.all([get('candidate-model.json'),get('candidate-validation.json'),get('forecast-history.json')]);
    const page=document.querySelector('#page');if(page)new MutationObserver(schedule).observe(page,{childList:true});
    document.addEventListener('change',event=>{if(event.target?.id==='govReplaySelect'){replayIndex=Number(event.target.value)||0;const old=document.querySelector('#historicalReplay');if(old)old.outerHTML=replayHTML(history,replayIndex);}});
    const ready=()=>{if(document.body.dataset.ready==='true')apply();else setTimeout(ready,50);};ready();
  }catch(error){console.error('governance-v56',error);}
}
if(typeof window!=='undefined'&&typeof document!=='undefined')boot();
