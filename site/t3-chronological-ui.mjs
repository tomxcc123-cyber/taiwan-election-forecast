const esc=x=>String(x??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const f=n=>Number(n).toFixed(2);
export function validateT3Audit(report){
  if(!report||report.schema_version!==1||
      report.kind!=='t3_chronological_nonmajor_bias_development_diagnostic'||
      report.model_id!=='HB-TLEF-v5.0-public-beta.1'||
      report.governance?.official_forecast_modified!==false||
      report.governance?.independent_blind_holdout!==false||
      report.governance?.release_gate!=='blocked_until_independent_roster_and_probability_validation'||
      report.governance?.strict_historical_candidate_ballot_roster_vintage_proven!==false||
      Math.abs(report.frozen_t3?.alpha-.3)>1e-10||
      Math.abs(report.frozen_t3?.model_weight-.7)>1e-10||
      Math.abs(report.frozen_t3?.carry_weight-.3)>1e-10||
      !Array.isArray(report.frozen_t3?.features)||
      !report.cycles?.['2018']||!report.cycles?.['2022'])throw Error('T3歷史驗證來源或預測隔離標記不一致');
  for(const [year,cycle] of Object.entries(report.cycles)){
    if(!['2018','2022'].includes(year)||cycle.target_year!==Number(year)||
        cycle.target_rows!==22||cycle.rows?.length!==22||
        cycle.training_years?.some(y=>y>=Number(year))||
        cycle.training_years?.join(',')!==(year==='2018'?'2014':'2014,2018'))throw Error('T3時間順序或樣本不符');
    const m=cycle.metrics;
    for(const name of ['deployed_t3_70_30_roster_aware','prior_cycle_carry_roster_aware','fitted_t3_raw_roster_aware']){
      const v=m?.[name];
      if(v?.rows!==22||!['mae_pp','rmse_pp','signed_bias_pp'].every(k=>Number.isFinite(v[k])))throw Error('T3統計指標無法核對');
    }
    if(!Array.isArray(cycle.bootstrap?.t3_signed_bias_pp_90pct_interval)||
       cycle.bootstrap.t3_signed_bias_pp_90pct_interval.length!==2||
       cycle.bootstrap.resample_unit!=='county')throw Error('T3縣市重抽樣資訊遺失');
    for(const row of cycle.rows){
      if(!row.county||row.target_year!==Number(year)||!['target_nonmajor_pct','prior_cycle_nonmajor_pct','t3_blend_nonmajor_pct','t3_blend_signed_error_pp'].every(k=>Number.isFinite(row[k])))throw Error('T3縣市觀測資料不完整');
    }
  }
  return report;
}
export function t3AuditHTML(value){
  if(!value)return '<section class="history"><h2>T3非藍綠票池跨屆檢驗</h2><p class="warning">歷史驗證報告暫時無法讀取，不以既有候選人勝率代替缺失的檢驗。</p></section>';
  let audit;
  try{audit=validateT3Audit(value);}catch(error){
    return '<section class="history"><h2>T3非藍綠票池跨屆檢驗</h2><p class="warning">歷史資料驗證失敗，禁止展示未核驗結果。</p></section>';
  }
  const titles={'2018':'2018 · 2014資料訓練','2022':'2022 · 2014＋2018資料訓練'};
  const summary=['2018','2022'].map(year=>{
    const c=audit.cycles[year],m=c.metrics;
    const a=m.deployed_t3_70_30_roster_aware,b=m.prior_cycle_carry_roster_aware;
    return `<tr><td>${esc(titles[year])}</td><td>${c.target_rows}縣市</td><td>${f(a.mae_pp)}</td><td>${f(a.signed_bias_pp)}</td><td>${f(b.mae_pp)}</td><td>${f(a.mae_pp-b.mae_pp)}</td><td>${a.overestimated_count}/22</td></tr>`;
  }).join('');
  const c=audit.cycles['2022'],boots=c.bootstrap;
  const subset=[
    ['沒有非藍綠參選者','no_nonmajor_on_ballot'],
    ['僅一名非藍綠參選者','one_nonmajor_on_ballot'],
    ['至少兩名非藍綠參選者','two_or_more_nonmajor_on_ballot'],
    ['實際非藍綠得票不到5%','observed_nonmajor_below_5pct'],
    ['實際非藍綠得票至少20%','observed_nonmajor_at_least_20pct']
  ].map(([label,k])=>{const m=c.cohort_metrics[k];return `<tr><td>${esc(label)}</td><td>${m?.rows??'—'}</td><td>${m?f(m.mae_pp):'—'}</td><td>${m?f(m.signed_bias_pp):'—'}</td></tr>`;}).join('');
  const county=c.rows.slice().sort((a,b)=>Math.abs(b.t3_blend_signed_error_pp)-Math.abs(a.t3_blend_signed_error_pp)).slice(0,8).map(row=>
    `<tr><td>${esc(row.county)}</td><td>${row.nonmajor_candidate_count}</td><td>${f(row.target_nonmajor_pct)}%</td><td>${f(row.t3_blend_nonmajor_pct)}%</td><td>${row.t3_blend_signed_error_pp>0?'+':''}${f(row.t3_blend_signed_error_pp)}pp</td></tr>`
  ).join('');
  const bias=boots.t3_signed_bias_pp_90pct_interval,relative=boots.t3_minus_carry_mae_pp_90pct_interval;
  return `<section class="history" id="t3ChronologicalAudit"><h2>T3第三勢力／無黨籍票池：跨屆偏差檢驗</h2>
  <p class="warning">僅為回顧式開發診斷。2018曾用於選擇T3規格，2022結果也已在專案開發中查看；當屆參選名單與地方組織特徵的選前可得時點尚未逐筆獨立核證，因此<strong>不是獨立盲測、不是2026勝率校準</strong>。</p>
  <p>固定現行T3特徵與正則化（alpha=0.3），使用2014→2018及2014＋2018→2022兩段時間順序，精確按現行70% T3＋30%前屆票池混合，並對沒有非藍綠參選者的縣市依名單設零。同條件對比前屆延續基準。每縣市等權，單位為百分點（pp）。</p>
  <div class="table-wrap"><table><caption>候選人名單條件下的非藍綠總得票份額誤差（非勝選概率）</caption><thead><tr><th>測試屆次</th><th>樣本</th><th>T3 MAE</th><th>T3有號偏差</th><th>前屆延續MAE</th><th>T3減前屆MAE</th><th>T3高估縣市</th></tr></thead><tbody>${summary}</tbody></table></div>
  <p>2022以縣市作為重抽樣單位，T3平均有號偏差的90%描述性區間：${f(bias[0])} 至 ${f(bias[1])}pp；相對前屆延續的MAE差異區間：${f(relative[0])} 至 ${f(relative[1])}pp。這些區間只反映單一週期22縣市的抽樣變動，不涵蓋歷屆環境或模型規格不確定性。</p>
  <h3>2022高估／低估發生在哪些類型？</h3><div class="table-wrap"><table><thead><tr><th>子群</th><th>縣市</th><th>T3 MAE</th><th>有號偏差</th></tr></thead><tbody>${subset}</tbody></table></div>
  <h3>2022絕對誤差較大的縣市</h3><div class="table-wrap"><table><thead><tr><th>縣市</th><th>其他人選數</th><th>實際得票</th><th>T3票池預測</th><th>有號誤差</th></tr></thead><tbody>${county}</tbody></table></div>
  <p class="meta">正值為高估，負值為低估。子群按實際得票率分組的統計只能用於事後分析，不可用作2026先驗特徵。所有候選人得票預測、2000次聯合模擬與勝率均未由本報告修改。模型升級閘門仍為阻擋，直到取得獨立時間／名單與機率驗證。</p>
  <p><a href="t3-chronological-bias-audit.json" download>下載完整T3 2018／2022核驗報告（含22縣市逐筆誤差）</a></p></section>`;
}
