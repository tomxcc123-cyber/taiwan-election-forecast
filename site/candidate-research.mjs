import {escape as esc} from './charts.mjs';

const fixed = (value, digits=1) => Number(value).toFixed(digits);

const reasons = {
  mass_outside_rounding_bound:'名單得票合計超出四捨五入容許範圍',
  damaged_candidate_name:'姓名含異常字元', duplicate_candidate:'候選人重複',
  invalid_shares:'得票資料無效', winner_mismatch:'當選標記與得票不一致'
};

export function registrationPanel(roster, county) {
  const race = roster?.races.find(r=>r.county===county);
  if (!race) return '<section class="history"><h2>登記參選名單</h2><p class="meta">尚無名單快照。</p></section>';
  return `<section class="history" id="registrationPanel"><h2>${esc(county)} · 登記參選人</h2>
    <p class="meta">截至 ${esc(roster.as_of)} · ${race.candidates.length} 人 · 已登記，待資格審查。下列名單與舊版三方情境分開，不套用上方情境勝率。</p>
    <div class="table-wrap"><table><caption>登記順序，非選票號次</caption><thead><tr><th>姓名</th><th>登記政黨／身分</th><th>來源</th></tr></thead>
    <tbody>${race.candidates.map(c=>`<tr><td>${esc(c.name)}</td><td>${esc(c.party_name)}</td><td><a href="${safeURL(c.source_url)}" target="_blank" rel="noopener">報導</a></td></tr>`).join('')}</tbody></table></div>
    <p class="meta">全台 ${roster.county_count} 縣市、${roster.candidate_count} 名。姓名及政黨已與媒體名單核對，最終合格名單仍以選委會公告為準。</p></section>`;
}

function safeURL(value) {
  try { const u=new URL(value); return u.protocol==='https:'?esc(u.href):'#'; }
  catch { return '#'; }
}

export function candidateValidation(artifact) {
  if (!artifact) return '<p class="empty">候選人研究模型尚無驗證產物。</p>';
  const b=artifact.backtest,m=b.metrics,a=artifact.audit;
  const rows=[['候選人 ridge',m],['前屆延續基準',b.baselines.carry_forward],['候選人均分基準',b.baselines.uniform]];
  return `<section id="candidateValidation"><div class="section-heading"><h2>候選人模型 · 歷史留出測試</h2><span class="badge">研究中，未取代線上模型</span></div>
    <p class="meta">${esc(artifact.model_version)} · 2018 訓練，2022 整屆留出。僅 ${m.races} 場通過審計的賽事、${m.candidate_rows} 候選人列，不是 ${m.candidate_rows} 個獨立選舉週期。</p>
    <div class="warning">模型使用事後收錄的候選名單，不是選前快照。90%區間平均寬 ${fixed(m.mean_width_90_pp)} 百分點；覆蓋率高不代表預測精準。只有1個測試週期，尚不能宣稱2026勝率已校準。</div>
    <div class="table-wrap"><table><caption>相同候選人、相同測試賽事；每場賽事等權</caption><thead><tr><th>模型</th><th>MAE（百分點）</th><th>RMSE（百分點）</th></tr></thead><tbody>${rows.map(([name,v])=>`<tr><td>${name}</td><td>${fixed(v.mae_pp,2)}</td><td>${fixed(v.rmse_pp,2)}</td></tr>`).join('')}</tbody></table></div>
    <div class="poll-meta"><div><span class="meta">90%區間覆蓋率</span><strong>${fixed(m.coverage_90*100)}%</strong></div><div><span class="meta">多類別 Brier</span><strong>${fixed(m.multiclass_brier,3)}</strong></div><div><span class="meta">Log loss</span><strong>${fixed(m.log_loss,3)}</strong></div><div><span class="meta">WIS（越低越好）</span><strong>${fixed(m.wis_90_pp,3)}</strong></div></div>
    <details class="history"><summary>資料審計：${a.race_count-a.research_eligible_count} 場未通過數值或姓名檢查</summary><p class="meta">${a.race_count} 場歷史選舉、${a.candidate_count} 列；${a.research_eligible_count} 場通過檢查。通過不等於官方完整名單已核實。2014僅作特徵歷史，不作本次訓練標籤。</p><div class="table-wrap"><table><thead><tr><th>年份</th><th>縣市</th><th>得票合計</th><th>排除原因</th></tr></thead><tbody>${a.races.filter(r=>!r.research_eligible).map(r=>`<tr><td>${r.year}</td><td>${esc(r.county)}</td><td>${fixed(r.observed_share_sum)}%</td><td>${r.errors.map(e=>reasons[e]||esc(e)).join('；')}</td></tr>`).join('')}</tbody></table></div></details>
    <details class="history"><summary>逐候選人測試結果與90%區間</summary><div class="table-wrap"><table><caption>實際比例僅在四捨五入容許範圍內閉合至100%</caption><thead><tr><th>縣市</th><th>候選人</th><th>預測得票率</th><th>實際得票率</th><th>90%區間</th></tr></thead><tbody>${b.details.map(r=>`<tr><td>${esc(r.county)}</td><td>${esc(r.name)}</td><td>${fixed(r.predicted_pct)}%</td><td>${fixed(r.actual_closed_pct)}%</td><td>${fixed(r.p05_pct)}–${fixed(r.p95_pct)}%</td></tr>`).join('')}</tbody></table></div></details>
    <details class="history"><summary>參數敏感性（不據此挑選測試分數最佳者）</summary><div class="table-wrap"><table><thead><tr><th>Ridge懲罰</th><th>全台誤差假設</th><th>MAE</th><th>RMSE</th><th>區間平均寬度</th></tr></thead><tbody>${artifact.sensitivity.map(s=>`<tr><td>${s.alpha}</td><td>${s.national_sd}</td><td>${fixed(s.metrics.mae_pp)}</td><td>${fixed(s.metrics.rmse_pp)}</td><td>${fixed(s.metrics.mean_width_90_pp)}</td></tr>`).join('')}</tbody></table></div></details>
    <p class="meta history">已實作：候選人獨立建模、訓練折內標準化、ridge、縣市群集bootstrap、同批聯合抽樣及歷史留出測試。待完成：官方歷史原檔、最終資格名單、選前快照、跨週期校準及候選人聯合民調模型。登記名單已接入，不等於上述驗證已完成。</p>
    <p class="history"><a href="candidate-research.json" download>下載歷史驗證與模型係數</a></p></section>`;
}
