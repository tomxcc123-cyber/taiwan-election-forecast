// Descriptive, historical forecast diagnostics. The 2022 labels were already
// observed when exploratory formulas were designed; never promote models here.
const enc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(2):'—';
const signed=x=>x>0?'+'+fmt(x):fmt(x);
const nm=x=>Number(x).toLocaleString('zh-TW');
export function validateShadowResearch(r){
  if(r?.schema_version!==1||r.kind!=='turnout_forecast_shadow_ablation_2022_exploratory'||
    r.training_cutoff_election!==2018||r.holdout_election!==2022||
    r.candidate_party_votes_used_in_predictors!==false||
    r.uses_2022_outcomes_only_for_scoring!==true||
    r.promotion_gate?.status!=='blocked'||r.promotion_gate?.formal_hb_tlef_unchanged!==true||
    r.promotion_gate?.allow_2026_candidate_win_probability_modification!==false||
    !Number.isInteger(r.coverage?.towns)||r.coverage.towns<1||
    !Array.isArray(r.per_county)||r.per_county.length!==r.coverage.counties||
    !r.scores?.persistence||typeof r.scores.persistence.mae_pp!=='number')
    throw Error('投票率實驗回測資料或防洩漏條件未通過驗證');
  if(r.scores.persistence.delta_mae_vs_persistence_pp!==0)
    throw Error('歷史基準錯位');
  for(const score of Object.values(r.scores)){
    if(typeof score.mae_pp!=='number'||score.mae_pp<0||score.n_towns!==r.coverage.towns||
       typeof score.delta_mae_vs_persistence_pp!=='number')
      throw Error('回測分母／評分欄位失效');
  }
  return r;
}
export function shadowResearchPanel(raw,county='台北市'){
  let r;
  try{r=validateShadowResearch(raw)}catch(e){
    return '<section class="turnout-panel" id="turnoutShadowResearch"><h2>投票率預測：影子模型回測</h2><p>經核驗的時間順序比較尚未發布；不展示未經計算的2026投票率預測。</p></section>';
  }
  const ordered=['persistence','county_shrink_75','county_shrink_50',
   'county_drift_25','national_drift_25','shrink_75_drift_25','county_drift_100'];
  const rows=ordered.map(key=>{
    const s=r.scores[key];
    if(!s)return '';
    const ci=s.county_bootstrap?.difference_vs_persistence_mae_pp_90pct_county_bootstrap;
    return '<tr><td>'+enc(s.label)+'</td><td>'+fmt(s.mae_pp)+'</td><td>'+fmt(s.rmse_pp)+'</td>'
      +'<td>'+signed(s.delta_mae_vs_persistence_pp)+'</td>'
      +'<td>'+(ci?fmt(ci[0])+' 至 '+fmt(ci[1]):'基準')+'</td>'
      +'<td>'+(Number.isInteger(s.counties_with_lower_mae)?s.counties_with_lower_mae+' / '+r.coverage.counties:'—')+'</td></tr>';
  }).join('');
  const c=r.per_county.find(x=>x.county===county);
  const countyRows=c?ordered.map(key=>{
    const s=c.metrics[key];
    return '<tr><td>'+enc(r.scores[key].label)+'</td><td>'+fmt(s.mae_pp)+' pp</td>'
      +'<td>'+fmt(s.rmse_pp)+' pp</td></tr>';
  }).join(''):'';
  return '<section class="turnout-panel" id="turnoutShadowResearch">'
    +'<header><small>PRE-2022 INPUTS · EXPLORATORY SHADOW MODELS</small>'
    +'<h2>投票率預測：固定公式的樣本外比較</h2></header>'
    +'<p>在不使用2022年結果作為模型輸入的前提下，比較上一屆投票率、向縣市均值收縮和歷史趨勢修正等固定公式。測試年是2022年；所有誤差按該年選舉人數加權，以百分點表示（越小越好）。</p>'
    +'<div class="turnout-stats"><div><small>預測資料截止</small><strong>2018年</strong></div>'
    +'<div><small>留出年份</small><strong>2022年</strong></div>'
    +'<div><small>核驗行政區</small><strong>'+nm(r.coverage.towns)+'</strong></div>'
    +'<div><small>正式模型採納情況</small><strong>未採納</strong></div></div>'
    +'<div class="turnout-tablewrap"><table class="turnout-table"><thead><tr>'
    +'<th>影子模型</th><th>加權 MAE (pp)</th><th>加權 RMSE (pp)</th>'
    +'<th>相對基準 MAE 差額 (pp)</th><th>縣市群集重抽樣差額區間 (pp)</th>'
    +'<th>優於基準縣市數</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
    +'<p class="turnout-note">區間只透過對21個縣市重抽樣估計同一屆2022年內的差異，並不是跨不同選舉年份的可信度界限或統計顯著性檢定。數值為負代表在此歷史樣本中誤差較小，並不證明將來仍會較好。</p>'
    +(c?'<h3>'+enc(county)+'：各固定公式的2022年誤差</h3><div class="turnout-tablewrap">'
      +'<table class="turnout-table"><thead><tr><th>方法</th><th>MAE</th><th>RMSE</th></tr></thead><tbody>'
      +countyRows+'</tbody></table></div>':'')
    +'<p class="turnout-special"><strong>不能直接升級為2026正式預測。</strong>這些公式是在研究者已看過2022基準結果後進行的探索性回測；即使有方法在這一屆表現更好，也可能是重複利用同一留出集選型。缺乏另一屆獨立驗證與選民參與—投票選擇聯合證據，不能據此更改候選人勝選機率。</p>'
    +'<p><a href="turnout-shadow-ablation-2022.json" download>下載影子模型回測、逐縣市比較與公式資料</a></p></section>';
}
