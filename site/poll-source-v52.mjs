const METHOD_LABELS={closed_online_panel:'封閉式網路樣本',telephone_cati:'電話訪問',landline_cati:'市話訪問',dual_frame_cati:'市話＋手機雙架構',online_panel:'網路樣本',online_dmp_panel:'DMP網路樣本'};
const VERIFY_LABELS={reviewed_multi_source_methodology_partial_response:'多來源核驗／回應類別部分未公開',reviewed_multi_source_methodology:'多來源方法核驗',reviewed_original_page_facts:'原始頁面核驗',reviewed_pollster_facts:'調查機構事實核驗',automatic_original_report:'原始報告自動校驗',automatic_original_html:'原始頁面自動校驗'};
const REVIEW_LABELS={reviewed_methodology_incomplete_response_mass:'方法已核對／回應類別不完整',publisher_not_pollster:'刊載媒體／不另建 pollster',publisher_reprint_not_new_pollster:'轉載別家調查／不重複計權',access_limited:'來源受限／暫不入模',reviewed_not_integrated:'已核對／暫未整合',pending_original_verification:'待原始資料核驗'};
const esc=value=>String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const safe=value=>{try{const u=new URL(value);return u.protocol==='https:'?esc(u.href):'#';}catch{return '#';}};
export const methodLabel=value=>METHOD_LABELS[value]||value||'方法未分類';
export const verificationLabel=value=>VERIFY_LABELS[value]||value||'一般資料校驗';
export const reviewLabel=value=>REVIEW_LABELS[value]||value||'待處理';
export const ingestionLabel=record=>String(record?.ingestion||'').startsWith('reviewed_')?`人工核驗後收錄（${verificationLabel(record.verification_status||record.ingestion)}）；不是本輪自動原始報告解析成功。`:'原始報告自動解析並校驗。';
export function sourceState(source){
  if(source.auto_discovery_status==='degraded'&&Number(source.reviewed_reports)>0)return {key:'degraded',label:'發現受限／核驗存檔'};
  if(source.auto_discovery_status==='checked'&&Number(source.reviewed_reports)>0)return {key:'auto',label:'自動發現＋人工核驗'};
  if(source.auto_discovery_status==='checked')return {key:'checked',label:'自動發現'};
  if(source.status==='reviewed_seed_only')return {key:'reviewed',label:'人工核驗種子'};
  if(source.index_ok===false||source.status==='unavailable')return {key:'degraded',label:'來源受限'};
  if(Number(source.validated_reports)>0)return {key:'auto',label:'自動核驗'};
  if(Number(source.reviewed_reports)>0)return {key:'reviewed',label:'已核驗存檔'};
  return {key:'checked',label:'已檢查'};
}
export function coverageStats(feed,model){
  const audit=new Map((model?.poll_audit||[]).map(x=>[x.id,x]));
  const records=feed?.records||[];
  return {
    sourceCount:new Set(records.map(r=>r.pollster_id||r.source)).size,
    registryCount:Number(feed?.pollster_registry?.registered_pollsters||0),
    methodCount:new Set(records.map(r=>r.method_class).filter(Boolean)).size,
    included:records.filter(r=>audit.get(r.id)?.included).length,
    reviewQueue:(feed?.source_review||[]).length+(feed?.discovery_queue||[]).length,
    discoveryQueue:(feed?.discovery_queue||[]).length,
    latest:feed?.latest_fieldwork_date||'無'
  };
}
function statusChip(key,label){return `<span class="source-chip source-${esc(key)}">${esc(label)}</span>`;}
function acquisitionLabel(source){
  if(source.auto_discovery)return `${Number(source.auto_discovered||0)} 發現 / ${Number(source.validated_reports||0)} 解析 / ${Number(source.reviewed_reports||0)} 核驗`;
  return `${Number(source.validated_reports||0)} 自動 / ${Number(source.reviewed_reports||0)} 核驗`;
}
function recordSourceRow(source,feed,model){
  const records=(feed.records||[]).filter(r=>r.source===source.name),first=records[0],audit=new Map((model?.poll_audit||[]).map(x=>[x.id,x])),included=records.filter(r=>audit.get(r.id)?.included).length,state=sourceState(source);
  return `<tr><td><a href="${safe(source.url)}" target="_blank" rel="noopener">${esc(source.name)}</a><small>${first?.pollster_id?`pollster_id · ${esc(first.pollster_id)}`:source.registry_pollster_id?`pollster_id · ${esc(source.registry_pollster_id)}`:'來源層級'}</small></td><td>${statusChip(state.key,state.label)}</td><td>${esc(methodLabel(source.method_class||first?.method_class))}</td><td>${esc(acquisitionLabel(source))}</td><td>${included} 題</td><td>${esc(source.note||'通過解析與資料校驗後存檔。')}</td></tr>`;
}
function reviewSourceRow(source){
  const blocked=/incomplete|limited|pending|not_integrated/.test(source.status||''),publisher=['publisher_not_pollster','publisher_reprint_not_new_pollster'].includes(source.status);
  return `<tr><td>${source.url?`<a href="${safe(source.url)}" target="_blank" rel="noopener">${esc(source.name)}</a>`:esc(source.name)}<small>${publisher?'verification / publisher':'review queue'}</small></td><td>${statusChip(publisher?'publisher':blocked?'blocked':'review',reviewLabel(source.status))}</td><td>—</td><td>人工核對</td><td>0 題</td><td>${esc(source.note||'')}</td></tr>`;
}
export function discoveryQueueHTML(feed){
  const queue=feed?.discovery_queue||[];
  if(!queue.length)return `<section class="discovery-queue discovery-empty"><div class="source-observatory-head"><div><span class="eyebrow">Discovery Queue</span><h3>待核驗發現</h3><p>目前沒有新的「已發現但未核驗」民調頁面。</p></div>${statusChip('included','佇列為空')}</div></section>`;
  const rows=queue.map(row=>`<tr><td>${statusChip('review','待核驗')}</td><td><a href="${safe(row.url)}" target="_blank" rel="noopener">${esc(row.title||row.source||'未命名頁面')}</a><small>${esc(row.pollster_id?`pollster_id · ${row.pollster_id}`:row.source||'')}</small></td><td>${esc(row.county||'待辨識')}</td><td>${esc(row.reason||'尚未通過完整資料品質校驗。')}</td><td>${esc((row.discovered_at||'').slice(0,10)||'—')}</td></tr>`).join('');
  return `<section class="discovery-queue"><div class="source-observatory-head"><div><span class="eyebrow">Discovery Queue</span><h3>待核驗發現</h3><p>系統已在一方來源找到這些頁面，但它們尚未通過訪期、樣本、方法、完整回應品質與候選人題目校驗，因此<strong>不影響目前預測</strong>。</p></div>${statusChip('review',`${queue.length} 筆待核驗`)}</div><div class="table-wrap source-table"><table><thead><tr><th>狀態</th><th>發現頁面</th><th>縣市</th><th>為何尚未入模</th><th>首次發現</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
}
export function nonmajorResponseHTML(model){
  const audit=model?.nonmajor_poll_response_audit;
  if(!audit)return '';
  if(audit.schema_version!==1||audit.kind!=='nonmajor_survey_response_comparison_not_ballot_forecast_constraint'
     ||audit.formal_forecast_modified!==false||audit.metrics_not_interchangeable!==true
     ||!Array.isArray(audit.rows)||audit.rows.length!==audit.source_rows)return '';
  if(!audit.rows.length)return '';
  const fmt=v=>Number(v).toFixed(1);
  const rows=audit.rows.map(r=>{
    const valid=r.is_ballot_prediction_constraint===false&&r.reweighted_or_redistributed_undecided===false
      &&Number.isFinite(r.model_nonmajor_mean_ballot_pct)
      &&Number.isFinite(r.poll_nonmajor_support_upper_pct)
      &&Number.isFinite(r.poll_undecided_reported_pct)
      &&Number.isFinite(r.model_nonmajor_p05_ballot_pct)
      &&Number.isFinite(r.model_nonmajor_p95_ballot_pct)
      &&r.poll_nonmajor_support_upper_pct>=0&&r.poll_nonmajor_support_upper_pct<=100
      &&r.model_nonmajor_p05_ballot_pct<=r.model_nonmajor_p95_ballot_pct
      &&r.provenance==='first_party_reported_survey_responses_vs_uncalibrated_election_day_ballot_draws';
    if(!valid)return '';
    return `<tr><td>${esc(r.county)}<small>${esc(r.date)}</small></td><td><a href="${safe(r.source_url)}" target="_blank" rel="noopener">${esc(r.source)}</a><small>${esc(r.pollster_id)}</small></td><td>&lt;${fmt(r.poll_nonmajor_support_upper_pct)}%</td><td>${fmt(r.poll_undecided_reported_pct)}%</td><td>${fmt(r.model_nonmajor_mean_ballot_pct)}%<small>90%模擬範圍 ${fmt(r.model_nonmajor_p05_ballot_pct)}–${fmt(r.model_nonmajor_p95_ballot_pct)}%</small></td></tr>`;
  }).filter(Boolean);
  if(!rows.length)return '';
  return `<section class="source-observatory" id="nonmajorResponseAudit"><div class="source-observatory-head"><div><span class="eyebrow">Nonmajor Evidence · Research Only</span><h3>非藍綠候選人：原始民調回應與模型票池對照</h3><p>只列原始調查<strong>明確交代其他候選人支持上限</strong>的波次。模型數值是選舉日模擬得票，調查數值是訪問當下的回答比例；分母、時間及未表態轉化都不同，<strong>兩者的差距不是預測誤差，更不是模型必須遵守的得票上限</strong>。</p></div></div><div class="table-wrap source-table"><table><thead><tr><th>縣市／訪期結束</th><th>原始調查</th><th>調查其他人選回應</th><th>調查未表態</th><th>模型非藍綠得票池</th></tr></thead><tbody>${rows.join('')}</tbody></table></div><p class="meta">為避免自行將未表態者分票給小黨／無黨籍，本研究僅顯示原始回應比例與模型不確定範圍；正式候選人得票及勝選機率維持既有模型，尚待多期資料與回測確認是否應調整。</p></section>`;
}
export function observatoryHTML(feed,model){
  const s=coverageStats(feed,model),rows=[...(feed.sources||[]).map(x=>recordSourceRow(x,feed,model)),...(feed.source_review||[]).map(reviewSourceRow)];
  const registryText=s.registryCount?`Pollster Registry 已登錄 ${s.registryCount} 個調查機構／狀態。`:'來源登錄正在建立中。';
  return `<section class="source-observatory" id="pollSourceObservatory"><div class="source-observatory-head"><div><span class="eyebrow">Poll Ingestion 2.0 · Source Coverage v5.3</span><h2>民調來源觀測站</h2><p>把「自動發現」「資料核驗」「正式入模」拆成三個狀態；刊載媒體不冒充調查機構，資訊不完整時維持 fail-closed。${esc(registryText)}</p></div><span class="source-chip source-policy">發現 ≠ 入模</span></div><div class="source-metrics"><div><small>已識別調查機構</small><strong>${s.sourceCount}</strong></div><div><small>調查方法類型</small><strong>${s.methodCount}</strong></div><div><small>候選人模型納入</small><strong>${s.included}</strong></div><div><small>待核驗／受限來源</small><strong>${s.reviewQueue}</strong></div><div><small>最近訪期結束</small><strong>${esc(s.latest)}</strong></div></div><div class="table-wrap source-table"><table><thead><tr><th>來源／pollster</th><th>狀態</th><th>方法類型</th><th>取得方式</th><th>已入模</th><th>限制與說明</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>${nonmajorResponseHTML(model)}<p class="meta">同一調查的媒體轉載不建立新的 pollster_id；reviewed seed 只在方法、訪期、樣本與題目口徑足以核驗時收錄，且會被日後同調查的自動原始紀錄取代。</p>${discoveryQueueHTML(feed)}</section>`;
}
function recordTags(record,audit){
  const accepted=audit?.included;
  return `<div class="poll-provenance">${statusChip(accepted?'included':'excluded',accepted?'v5 已納入':'v5 未納入')}${record.pollster_id?statusChip('neutral',`pollster · ${record.pollster_id}`):''}${record.method_class?statusChip('neutral',methodLabel(record.method_class)):''}${statusChip('verify',verificationLabel(record.verification_status||record.ingestion))}</div>`;
}
function matchRecord(card,feed,used){
  const title=card.querySelector('h3')?.textContent||'',meta=card.querySelector('.meta')?.textContent||'';
  return (feed.records||[]).find(r=>!used.has(r.id)&&title.includes(r.county)&&title.includes(r.source)&&meta.includes(r.field_start)&&meta.includes(r.date));
}
function enhanceCards(feed,model){
  const audit=new Map((model?.poll_audit||[]).map(x=>[x.id,x])),used=new Set();
  document.querySelectorAll('.poll-row').forEach(card=>{
    const old=card.querySelector('.poll-provenance');if(old)old.remove();
    const r=matchRecord(card,feed,used);if(!r)return;used.add(r.id);
    const meta=card.querySelector('.meta');if(meta)meta.insertAdjacentHTML('afterend',recordTags(r,audit.get(r.id)));
    const details=card.querySelector('details');if(details){
      const paragraphs=details.querySelectorAll(':scope > p');
      if(paragraphs[1])paragraphs[1].textContent=ingestionLabel(r);
      if(!details.dataset.sourceV52){
        details.dataset.sourceV52='1';
        details.insertAdjacentHTML('beforeend',`<dl class="provenance-dl"><dt>調查機構 ID</dt><dd>${esc(r.pollster_id||'未建立')}</dd><dt>方法類型</dt><dd>${esc(methodLabel(r.method_class))}</dd><dt>核驗狀態</dt><dd>${esc(verificationLabel(r.verification_status||r.ingestion))}</dd><dt>發布日期</dt><dd>${esc(r.published_at||'未提供')}</dd></dl>`);
      }
    }
  });
}
let cache=null,lastLoad=0,scheduled=false;
async function load(force=false){
  if(cache&&!force&&Date.now()-lastLoad<60000)return cache;
  const [fr,mr]=await Promise.all([fetch('polls.json',{cache:'no-store'}),fetch('candidate-model.json',{cache:'no-store'})]);
  if(!fr.ok||!mr.ok)throw Error('來源觀測資料讀取失敗');
  cache={feed:await fr.json(),model:await mr.json()};lastLoad=Date.now();return cache;
}
async function apply(force=false){
  if(typeof document==='undefined')return;
  const params=new URL(location.href).searchParams,view=params.get('view')||'overview';
  if(!['polls','methods'].includes(view))return;
  try{
    const {feed,model}=await load(force);
    if(view==='polls'){
      const anchor=document.querySelector('#sourceStatus');if(!anchor)return;
      document.querySelector('#pollSourceObservatory')?.remove();anchor.insertAdjacentHTML('beforebegin',observatoryHTML(feed,model));anchor.hidden=true;enhanceCards(feed,model);
    }else{
      const prose=document.querySelector('.prose');if(!prose||document.querySelector('#sourceGovernanceV52'))return;
      const s=coverageStats(feed,model);prose.insertAdjacentHTML('beforeend',`<section id="sourceGovernanceV52"><h2>民調來源治理 · Poll Ingestion 2.0</h2><p>目前資料庫識別 ${s.sourceCount} 個已出現 pollster、${s.registryCount||'—'} 個 Registry 狀態、${s.methodCount} 類調查方法，候選人 likelihood 實際納入 ${s.included} 題。來源流程分成自動發現、方法／回應品質核驗與候選人模型納入；資料不足時不以剩餘百分比自行推定未表態，也不把「已發現」等同「已入模」。</p><p>目前有 ${s.discoveryQueue} 筆自動發現頁面仍在待核驗佇列。<a href="?view=polls">查看來源觀測站、待核驗發現與每題 provenance</a></p></section>`);
    }
  }catch(error){console.warn('[source-v5.3]',error);}
}
function schedule(force=false){if(scheduled)return;scheduled=true;setTimeout(()=>{scheduled=false;apply(force);},0);}
if(typeof document!=='undefined'){
  const page=document.querySelector('#page');if(page)new MutationObserver(()=>schedule()).observe(page,{childList:true,subtree:false});
  document.addEventListener('click',e=>{if(e.target?.id==='reloadPolls')setTimeout(()=>apply(true),900);});
  window.addEventListener('popstate',()=>schedule());
  schedule();
}
