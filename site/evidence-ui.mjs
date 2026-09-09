import {escape as esc} from './charts.mjs';
import {NAMES,cleanState} from './candidate-engine.mjs';

const num=(x,n=1)=>Number(x).toFixed(n);
const probability=x=>`${Math.round(x*100)}%`;
const signed=x=>Math.abs(x)<.05?'0.0':`${x>0?'+':''}${num(x)}`;
const dateLabel=x=>new Date(x).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'});
const day=x=>new Date(x).toLocaleDateString('en-CA',{timeZone:'Asia/Taipei'});
const link=url=>{try{return new URL(url).protocol==='https:'?esc(url):'#';}catch{return '#';}};
export const evidence=r=>r.quality?.evidence||{grade:'C',reason:'資料等級尚未提供'};
export function badge(r){const q=evidence(r);return `<span class="evidence-badge grade-${q.grade}" title="${esc(q.reason)}">${q.grade} · ${q.grade==='D'?'暫不評級':q.grade==='C'?'資料有限':'近期民調'}</span>`;}
export function probabilityLabel(r,c){const g=evidence(r).grade;return g==='D'?'模型缺項 · 暫不評級':g==='C'?`模型傾向 ${probability(c.probability)}`:`約 ${probability(c.probability)}`;}
export function competition(r){
  const q=evidence(r),c=r.candidates[r.winner];
  if(q.grade==='D')return '模型缺項';
  if(q.grade==='C'||c.p95-c.p05>30)return '資料不足／高不確定';
  const ranked=[...r.candidates].sort((a,b)=>b.mean-a.mean);
  if(ranked.length>1&&ranked[0].mean-ranked[1].mean<=5&&c.probability<.75)return '接近競爭';
  return '有資料的領先';
}
export function ratingsBoard(result){return `<section class="ratings"><h2>證據與競爭狀態</h2><p class="meta">先區分資料缺口，再判讀差距；不把高不確定性直接當作五五波。</p><div class="evidence-ratings">${['模型缺項','資料不足／高不確定','接近競爭','有資料的領先'].map(label=>`<section><h3>${label}</h3><div>${result.counties.filter(r=>competition(r)===label).map(r=>`<button class="link" data-county="${esc(r.name)}">${esc(r.name)}<small>${evidence(r).grade==='D'?'跨黨支持效果未估計':esc(r.leaderLabel)+' · '+probabilityLabel(r,r.candidates[r.winner])}</small></button>`).join('')||'<p class="meta">目前無縣市符合</p>'}</div></section>`).join('')}</div></section>`;}
export function nationalSummary(data,result){
  const count=data.poll_counts,risks=result.counties.filter(r=>evidence(r).grade==='D'),recent=result.counties.filter(r=>['A','B'].includes(evidence(r).grade)).length;
  return `<section class="election-brief" aria-label="全台資料摘要"><div><span class="eyebrow">基準資料摘要</span><h2>先看證據，再看機率</h2></div><p>22縣市中，${count.covered_counties}個有直接配對民調，${recent}個有60天內的合格民調。${risks.length?`${risks.map(r=>esc(r.name)).join('、')}存在尚未建模的支持關係，暫不評級。`:''}${data.support_model?.applied_evidence.length||0}項跨黨支持已作研究代理輸入，效果尚未跨期驗證。缺乏近期民調的結果僅代表模型傾向，不能據此判定近期民意移動。</p><a href="?view=updates" data-view="updates">查看變化與證據</a></section>`;
}
export function pollCounts(data){const c=data.poll_counts;return `<div class="poll-meta" id="pollCounts">${[['收錄原始報告',`${c.reports} 份`],['候選組合題',`${c.questions} 題`],['候選人模型納入',`${c.included_questions} 題`],['直接民調覆蓋',`${c.covered_counties}/22 縣市`],['名單不符排除',`${c.roster_exclusions} 題`],['最近有效訪問結束',c.latest_eligible_fieldwork||'無']].map(([k,v])=>`<div><span class="meta">${k}</span><strong>${esc(v)}</strong></div>`).join('')}</div>`;}
export function candidateEvidence(data,r){
  const events=data.evidence.events.filter(e=>e.county===r.name);
  return `<section class="history evidence-panel"><h2>證據與模型解釋</h2><p>${badge(r)} ${esc(evidence(r).reason)}</p><div class="table-wrap"><table><caption>觀測資料與模型缺項分列</caption><thead><tr><th>候選人</th><th>前屆同名得票</th><th>來源履歷</th></tr></thead><tbody>${r.candidates.map(c=>{const old=r.history.candidates.find(p=>p.name===c.name);return `<tr><td>${esc(c.name)}</td><td>${old?num(old.share_pct)+'%'+(old.winner?' · 當選':''):'無同名紀錄（非零支持）'}</td><td>${esc(c.bio||'未提供')}<br><a href="${link(c.source_url)}" target="_blank" rel="noopener">名單來源</a></td></tr>`;}).join('')}</tbody></table></div>
  ${events.map(e=>`<article class="evidence-event"><span class="eyebrow">已核對公開報導 · ${esc(e.date)}</span><h3>${esc(e.title)}</h3><p>${esc(e.note)}</p><a href="${link(e.source_url)}" target="_blank" rel="noopener">${esc(e.source_name)}</a><span class="badge">效果未經跨期驗證</span></article>`).join('')||'<p class="meta">尚無已核對的跨黨支持紀錄，不代表沒有支持關係。</p>'}
  <details><summary>哪些因素已進入模型？</summary><p>前屆同名個人得票、具名政黨得票、前屆勝方與缺值標記已用於基本面。履歷文字不轉成能力分數；公開支持關係借用具名政黨的歷史組織特徵，並加入額外不確定性。這是代理假設，尚未估計背書的因果效果。現任其他職務不等於現任縣市長。尚未估計人口分群、地方派系或投票率效果。</p><p>${esc(data.evidence.grading_rule)}</p><p>${esc(data.evidence.coverage)}</p></details>${supportComparison(data,r)}</section>`;
}

export function comparisonSnapshot(data,period='version'){
  const list=[...data.tracking.snapshots].sort((a,b)=>Date.parse(b.generated_at)-Date.parse(a.generated_at));
  if(period==='version')return list.find(s=>s.model_version!==data.model_version)||null;
  if(period==='poll')return list.find(s=>JSON.stringify(s.poll_ids)!==JSON.stringify(data.poll_audit.filter(a=>a.included).map(a=>a.id).sort()))||null;
  const target=new Date(Date.parse(data.generated_at)-Number(period)*86400000),wanted=day(target);
  return list.find(s=>day(s.generated_at)===wanted)||null;
}
export function changeReasons(data,previous){
  if(!previous)return [];
  const names={feed_hash:'民調資料',candidate_set_version:'候選名單',training_data_hash:'歷史選舉資料',historical_poll_hash:'歷史民調資料',context_hash:'證據標註'};
  const changed=Object.entries(names).filter(([k])=>data[k]!==previous.inputs[k]).map(([,label])=>label);
  if(data.model_version!==previous.model_version)changed.push('產品版本');
  if(data.generated_at!==previous.generated_at)changed.push('計算時點');
  return changed;
}
export function snapshotDownload(data){return JSON.stringify({schema_version:1,scope:'stored baseline summaries only; not full simulation draws',snapshots:data.tracking.snapshots},null,2);}
export function versionPanel(data,r){const s=comparisonSnapshot(data),old=s?.counties.find(x=>x.race_id===r.race_id);return `<section class="history"><h2>版本對比</h2><p class="meta">目前 ${esc(data.model_version)}</p>${old?`<p class="meta">前版 ${esc(s.model_version)} · ${dateLabel(s.generated_at)}</p><div class="table-wrap"><table><thead><tr><th>候選人</th><th>前版得票</th><th>目前基準得票</th><th>差值</th></tr></thead><tbody>${data.counties.find(x=>x.race_id===r.race_id).candidates.map(c=>{const p=old.candidates.find(x=>x.candidate_id===c.candidate_id);return `<tr><td>${esc(c.name)}</td><td>${p?num(p.mean)+'%':'新增人選'}</td><td>${num(c.mean)}%</td><td>${p?signed(c.mean-p.mean)+'百分點':'不比較'}</td></tr>`;}).join('')}</tbody></table></div><p class="meta">變動輸入：${changeReasons(data,s).join('、')}。不包含目前使用者情境；不是因素貢獻分解。</p>`:'<p class="empty">尚無前一產品版本存檔。</p>'}<a href="?view=updates" data-view="updates">完整變化紀錄</a></section>`;}
export function updatesPage(data,period){
  const previous=comparisonSnapshot(data,period),old=new Map(previous?.counties.map(r=>[r.race_id,r])||[]);
  const rows=data.counties.map(r=>{const leader=[...r.candidates].sort((a,b)=>b.probability-a.probability)[0],p=old.get(r.race_id)?.candidates.find(c=>c.candidate_id===leader.candidate_id);return {r,c:leader,p,delta:p?leader.mean-p.mean:null};}).sort((a,b)=>Math.abs(b.delta||0)-Math.abs(a.delta||0));
  const added=previous?data.poll_audit.filter(a=>a.included&&!previous.poll_ids.includes(a.id)):[];
  return `<section class="election-brief"><div><span class="eyebrow">真實快照 · 基準模型</span><h2>每日選情觀測</h2></div><p>${esc(data.tracking.notice)}</p></section>
  <div class="filterbar"><label>比較基準<select id="historyCompare">${[['version','上一產品版本'],['1','前一日'],['7','七日前'],['poll','上一組納入民調']].map(([v,n])=>`<option value="${v}" ${period===v?'selected':''}>${n}</option>`).join('')}</select></label><button id="downloadHistory">下載已存摘要</button></div>
  ${previous?`<p class="meta">${dateLabel(previous.generated_at)} → ${dateLabel(data.generated_at)}；變動輸入：${changeReasons(data,previous).join('、')}。</p><p class="warning">以下是兩次建置的差值，不代表新增民意觀測或事件的因果影響。尚未進行逐因素固定條件重跑，不提供虛構的貢獻百分點。</p>`:'<p class="empty" role="status">尚無這個比較時點的存檔。從實際建置日起累積，不補造昨日或七日前的預測。</p>'}
  <div class="table-wrap"><table id="changesTable"><caption>22縣市基準變化 · 勝率差為百分點，不是百分比增幅</caption><thead><tr><th>縣市</th><th>資料等級</th><th>模型首位人選</th><th>得票差</th><th>勝率差</th></tr></thead><tbody>${rows.map(({r,c,p,delta})=>`<tr><td><button class="link" data-county="${esc(r.name)}">${esc(r.name)}</button></td><td>${badge(r)}</td><td>${esc(c.name)}${evidence(r).grade==='D'?'<small> · 不評級</small>':''}</td><td>${delta===null?'無可比資料':signed(delta)}</td><td>${p?signed((c.probability-p.probability)*100):'無可比資料'}</td></tr>`).join('')}</tbody></table></div>
  <section class="history"><h2>新增納入題目</h2><p>${previous?`${added.length} 題；按題目識別碼比較，不把重抓報告當新增。`:'尚無比較基準。'}</p>${added.length?`<ul>${added.map(a=>`<li>${esc(a.id)}</li>`).join('')}</ul>`:''}<a href="?view=polls" data-view="polls">查看原始報告與排除原因</a></section>
  <section class="history"><h2>已核對事件</h2><p class="meta">人工核對來源的事實目錄，並非全網即時事件或情緒監測；核對至 ${esc(data.evidence.reviewed_at)}。</p>${[...data.evidence.events].sort((a,b)=>b.date.localeCompare(a.date)).map(e=>`<article class="evidence-event"><span class="eyebrow">${esc(e.date)} · ${esc(e.county)}</span><h3>${esc(e.title)}</h3><p>${esc(e.note)}</p><a href="${link(e.source_url)}" target="_blank" rel="noopener">來源</a></article>`).join('')}</section>`;
}

export const PRESETS=[
  {id:'gain',label:'正向事件敏感度',boost:2,flow:0,tactical:0,description:'選定人選 +2 百分點；由其他人選按比例移轉。'},
  {id:'loss',label:'負向事件敏感度',boost:-2,flow:0,tactical:0,description:'選定人選 −2 百分點；回流其他人選。'},
  {id:'strong-loss',label:'較強衝擊敏感度',boost:-5,flow:0,tactical:0,description:'選定人選 −5 百分點；不是任何司法或危機事件的估計效果。'},
  {id:'flow-low',label:'部分票流整合',boost:0,flow:10,tactical:0,description:'來源人選當次支持的10%移至去向人選。'},
  {id:'flow-high',label:'較高票流整合',boost:0,flow:30,tactical:0,description:'來源人選當次支持的30%移至去向人選；不代表政黨支持者必然轉移。'},
  {id:'tactical',label:'第三人選票流',boost:0,flow:0,tactical:15,description:'基準排名第三名以後，各移轉15%支持至第二名。'}
];
export function presetState(data,county,presetId,selection){
  const p=PRESETS.find(p=>p.id===presetId),r=data.counties.find(r=>r.name===county);
  if(!p||!r)throw Error('未知的情境');
  const ids=r.candidates.map(c=>c.candidate_id);
  if(['boostId','from','to'].some(k=>!ids.includes(selection[k])))throw Error('人選與名單不一致');
  if(p.flow&&selection.from===selection.to)throw Error('票流來源與去向不能相同');
  if(p.tactical&&ids.length<3)throw Error('本縣市不足三名人選，無法套用第三人選票流');
  return cleanState({county,edits:{[r.race_id]:{boostId:selection.boostId,from:selection.from,to:selection.to,boost:p.boost,flow:p.flow,tactical:p.tactical,matrix:[],strategy:p.tactical?'legacy':'close',cutoff:15,topSplit:50}},constraints:{}},data);
}
export function presetPanel(){return `<section class="quick-lab"><div class="section-heading"><div><span class="eyebrow">假設實驗，不是事件預測</span><h2>快速情境</h2></div><span class="badge">規則運算 · 非AI選民</span></div><p class="meta">使用下方專業參數的人選選擇。先預覽，再從全台原始基準套用；將清除其他情境與指定席次。</p><div class="preset-grid">${PRESETS.map(p=>`<button data-preset="${p.id}"><strong>${p.label}</strong><small>${p.description}</small></button>`).join('')}</div><p class="meta">±2、−5百分點與10%、30%、15%均為公開的示例假設，未經歷史事件訓練；不模擬正式退選或特定人口群的政治態度。</p></section>`;}
export function scenarioComparison(result,baseline,county){const r=result.counties.find(r=>r.name===county),b=baseline.counties.find(r=>r.name===county);return `<section id="scenarioComparison" class="history"><h2>基準與目前情境</h2><p class="meta">固定 ${result.originalSimulations.toLocaleString()} 次原始抽樣；目前保留 ${result.simulations.toLocaleString()} 次。所有差值相對未調整基準，非事件效果估計。</p><div class="table-wrap"><table><thead><tr><th>人選</th><th>基準得票</th><th>情境得票</th><th>得票差</th><th>勝率差</th></tr></thead><tbody>${r.candidates.map(c=>{const p=b.candidates.find(x=>x.candidate_id===c.candidate_id);return `<tr><td>${esc(c.name)}</td><td>${num(p.mean)}%</td><td>${num(c.mean)}%</td><td>${signed(c.mean-p.mean)} pp</td><td>${signed((c.probability-p.probability)*100)} pp</td></tr>`;}).join('')}</tbody></table></div><div class="seat-labels">${result.summary.map(s=>`<span>${NAMES[s.group]}預期席次 ${signed(s.mean-baseline.summary.find(b=>b.group===s.group).mean)}</span>`).join('')}</div></section>`;}

function plot(points,title,xLabel,yLabel){
  return `<figure class="validation-plot"><figcaption><h3>${title}</h3></figcaption><svg viewBox="0 0 400 340" role="img" aria-label="${title}；橫軸${xLabel}，縱軸${yLabel}">${[0,25,50,75,100].map(t=>`<line x1="50" y1="${285-t*2.4}" x2="350" y2="${285-t*2.4}" stroke="#dce1e7"/><text x="42" y="${289-t*2.4}" text-anchor="end" font-size="11">${t}</text><text x="${50+t*3}" y="304" text-anchor="middle" font-size="11">${t}</text>`).join('')}<line x1="50" y1="285" x2="350" y2="45" stroke="#616b77" stroke-dasharray="4 4"/>${points.map(p=>`<circle cx="${50+p.x*3}" cy="${285-p.y*2.4}" r="${p.r||4}" fill="#2864c8" fill-opacity=".65"><title>${esc(p.label)}</title></circle>`).join('')}<text x="200" y="328" text-anchor="middle" font-size="12">${xLabel}（%）</text><text x="50" y="24" font-size="12">${yLabel}（%）</text></svg></figure>`;
}
export function validationCard(research){const b=research.backtest,m=b.metrics;return `<section class="validation-report" id="validationReport"><span class="eyebrow">2022留出 · 基本面模型</span><h2>模型成績單</h2><div class="report-grid"><div><span>候選人得票 MAE</span><strong>${num(m.mae_pp,2)}<small> 百分點</small></strong></div><div><span>前屆延續基準 MAE</span><strong>${num(b.baselines.carry_forward.mae_pp,2)}</strong></div><div><span>90%區間覆蓋</span><strong>${num(m.coverage_90*100,1)}%</strong></div><div><span>勝率校準</span><strong>未完成</strong></div></div><p>${m.mae_pp<b.baselines.carry_forward.mae_pp?'單一留出週期優於前屆延續基準，不能外推跨期優勢。':'目前尚未優於前屆延續基準。'}僅${m.races}場、1個測試週期；以下民調回測另依預測時距列出，不能混為同一成績。</p></section>`;}
export function validationPlots(research){const b=research.backtest;return `<section class="history"><h2>預測與實際</h2><div class="validation-charts">${plot(b.details.map(d=>({x:d.predicted_pct,y:d.actual_closed_pct,label:`${d.county} ${d.name}：預測${num(d.predicted_pct)}%，實際${num(d.actual_closed_pct)}%`})),'得票率對照','預測得票','實際得票')}${plot(b.reliability_bins.filter(d=>d.candidate_rows).map(d=>({x:d.mean_probability*100,y:d.observed_fraction*100,r:6,label:`${d.candidate_rows}筆候選人；預測${probability(d.mean_probability)}，實際當選${probability(d.observed_fraction)}`})),'勝率可靠度診斷','平均預測機率','實際當選比例')}</div><p class="meta">虛線為理想一致線。可靠度圖只有一個測試週期，候選人彼此相依；不是已完成校準的證明。</p><details><summary>圖表數值與逐候選人檢驗</summary><div class="table-wrap"><table><thead><tr><th>縣市／候選人</th><th>預測</th><th>實際</th><th>90%區間</th></tr></thead><tbody>${b.details.map(d=>`<tr><td>${esc(d.county)}／${esc(d.name)}</td><td>${num(d.predicted_pct)}%</td><td>${num(d.actual_closed_pct)}%</td><td>${num(d.p05_pct)}–${num(d.p95_pct)}%</td></tr>`).join('')}</tbody></table></div><div class="table-wrap"><table><caption>勝率分箱（候選人相依）</caption><thead><tr><th>機率區間</th><th>筆數</th><th>預測平均</th><th>實際當選</th></tr></thead><tbody>${b.reliability_bins.map(d=>`<tr><td>${probability(d.lower)}–${probability(d.upper)}</td><td>${d.candidate_rows}</td><td>${d.candidate_rows?probability(d.mean_probability):'無資料'}</td><td>${d.candidate_rows?probability(d.observed_fraction):'無資料'}</td></tr>`).join('')}</tbody></table></div></details></section>`;}

export function supportComparison(data,r){
 if(!r.quality.evidence.support_proxy_evidence?.length)return '';
 return `<details class="history" id="supportProxyComparison"><summary>有／無支持代理的基準對照</summary><p class="meta">${esc(data.support_model.note)}額外CLR標準差 ${data.support_model.extra_clr_sd} 為明示假設，並非估計值。</p><div class="table-wrap"><table><thead><tr><th>候選人</th><th>不採代理得票</th><th>採代理得票</th><th>採代理勝率</th></tr></thead><tbody>${r.support_comparison.map(p=>`<tr><td>${esc(r.candidates.find(c=>c.candidate_id===p.candidate_id).name)}</td><td>${num(p.without_proxy_mean)}%</td><td>${num(p.with_proxy_mean)}%</td><td>${probability(p.with_proxy_probability)}</td></tr>`).join('')}</tbody></table></div><p class="meta">這是兩個模型假設的比較，並非背書造成的真實選票增減；不包含使用者兵推。</p></details>`;
}
export function refinementDiagnostics(data){
 const s=data.validation.selection,p=data.validation.tuning_proposal_metrics,kept=data.validation.fundamentals.metrics;
 return `<section class="history" id="refinementDiagnostics"><h2>參數搜索與發布門檻</h2><p>只在2018訓練資料中按22個縣市分組搜索；2022留出結果另列。推薦的正則化係數 ${s.proposed_alpha}，實際採用 ${s.selected_alpha}。</p><div class="table-wrap"><table><thead><tr><th>2022開發留出對照</th><th>得票MAE</th><th>處理</th></tr></thead><tbody><tr><td>原始搜索候選</td><td>${num(p.mae_pp,2)} 百分點</td><td>${s.proposal_adopted?'通過訓練內門檻':'未通過訓練內門檻，不替換原參數'}</td></tr><tr><td>實際採用</td><td>${num(kept.mae_pp,2)} 百分點</td><td>維持公開誤差與未校準標示</td></tr></tbody></table></div><details><summary>訓練內分組檢查</summary><p>只有當配對縣市損失改善超過兩個描述性標準誤、且得票MAE沒有變差，才替換0.1。這是保守發布門檻，不是相依交叉驗證折的正式顯著性檢定。</p><div class="table-wrap"><table><thead><tr><th>係數</th><th>份額交叉熵</th><th>得票MAE</th></tr></thead><tbody>${s.grid.map(x=>`<tr><td>${x.alpha}</td><td>${num(x.cross_entropy,3)}</td><td>${num(x.mae_pp,2)}</td></tr>`).join('')}</tbody></table></div></details><p class="warning">2022已在開發中多次查看，不是新盲測。支持代理沒有完整跨屆背書資料可供驗證，不能把本表當成背書效果通過回測。</p></section>`;
}
