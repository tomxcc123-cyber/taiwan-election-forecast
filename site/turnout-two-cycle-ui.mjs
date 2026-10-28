// Official, retrospective historical turnout holdouts. Never change HB-TLEF.
// 2014 station electoral-area code differs from same-year elbase admin area;
// labels are drawn ONLY from 2014 original source, with sha256 provenance.
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fixed=x=>Number.isFinite(x)?x.toFixed(2):'—';
const pp=x=>Number.isFinite(x)?(x>0?'+':'')+fixed(x)+' pp':'—';
const num=x=>Number.isFinite(x)?new Intl.NumberFormat('zh-TW').format(x):'—';
const methods=[['persistence','前屆鄉鎮投票率直接延用'],
['county_shrink_75','向縣市均值收縮25%'],
['county_shrink_50','向縣市均值收縮50%']];

export function validateTwoCycleHistory(panel,check){
  if(panel?.schema_version!==1||panel.kind!=='observed_cec_2014_to_2018_town_turnout_holdout_input'||
    !panel.no_cross_year_precinct_join||!panel.join_screen_not_boundary_proof||
    panel.official_2026_forecast_unchanged!==true||
    !Array.isArray(panel.counties)||panel.counties.length!==22||
    !Number.isInteger(panel.matched_towns)||panel.matched_towns<1)
    throw new Error('2014原始行政區來源尚未通過雙年份核驗');
  if(check?.schema_version!==1||check.kind!=='cec_two_independent_town_turnout_cycles_2014_2022'||
    check.no_future_outcome_predictors!==true||check.candidate_vote_data_used!==false||
    check.promotion_gate?.status!=='blocked'||
    check.promotion_gate?.allow_2026_candidate_win_probability_modification!==false||
    check.promotion_gate?.formal_hb_tlef_unchanged!==true)
    throw new Error('兩屆投票率驗證不符合選前資料或模型隔離要求');
  const before=check.cycles?.['2014_to_2018'];
  const after=check.cycles?.['2018_to_2022'];
  if(!before||!after||before.training_election!==2014||
    before.held_out_election!==2018||after.training_election!==2018||
    after.held_out_election!==2022||before.matched_towns!==panel.matched_towns||
    !Array.isArray(before.towns)||before.towns.length!==before.matched_towns)
    throw new Error('兩屆驗證樣本與2014原始來源不一致');
  const sample=panel.counties.reduce((n,c)=>n+c.districts.length,0);
  if(sample!==panel.matched_towns||panel.matched_counties!==panel.counties.filter(x=>x.matched_towns>0).length)
    throw new Error('前屆行政區配對數與來源索引不一致');
  for(const key of methods.map(x=>x[0])){
    for(const cycle of [before,after]){
      const s=cycle.scores?.[key];
      if(!s||!Number.isFinite(s.electorate_weighted_mae_pp)||s.electorate_weighted_mae_pp<0||
         !Number.isFinite(s.delta_mae_vs_persistence_pp)||
         s.n_towns!==undefined&&s.n_towns!==cycle.matched_towns&&s.n_towns!==null)
        throw new Error('歷史留出指標不完整');
    }
  }
  return {panel,check};
}
export function twoCycleHistoryPanel(raw,report,county='台北市'){
  let x;
  try{x=validateTwoCycleHistory(raw,report)}catch{
    return '<section class="turnout-panel" id="twoCycleTurnout"><h2>2014—2022獨立選舉周期驗證</h2><p>2014年原始行政區資料或雙周期回測尚未經核驗，不顯示估計結果。</p></section>';
  }
  const {panel,check}=x;
  const a=check.cycles['2014_to_2018'],b=check.cycles['2018_to_2022'];
  const district=panel.counties.find(c=>c.county===county);
  const historyRows=district?.districts.slice().sort((x,y)=>x.district.localeCompare(y.district,'zh-TW'))||[];
  const rows=methods.map(([key,label])=>{
    const before=a.scores[key],after=b.scores[key];
    return '<tr><td>'+esc(label)+'</td><td>'+fixed(before.electorate_weighted_mae_pp)+'</td>'
      +'<td>'+pp(before.delta_mae_vs_persistence_pp)+'</td><td>'+fixed(after.electorate_weighted_mae_pp)+'</td>'
      +'<td>'+pp(after.delta_mae_vs_persistence_pp)+'</td></tr>';
  }).join('');
  const townRows=historyRows.map(t=>{
    const a=t.years['2014'],b=t.years['2018'];
    return '<tr><td>'+esc(t.district)+'</td>'
      +'<td>'+fixed(100*a.ballots_cast/a.electorate)+'%</td>'
      +'<td>'+fixed(100*b.ballots_cast/b.electorate)+'%</td>'
      +'<td>'+pp(t.delta_turnout_pp)+'</td><td>'+num(a.stations)+' → '+num(b.stations)+'</td></tr>';
  }).join('');
  return '<section class="turnout-panel" id="twoCycleTurnout">'
   +'<header><small>CEC ORIGINAL 2014 ADMINISTRATIVE NAMES · TWO SEPARATE HOLDOUT CYCLES</small><h2>2014—2018 與 2018—2022：獨立周期投票率驗證</h2></header>'
   +'<p>2014年投開票所選區欄位與行政區基礎表不同，已利用<strong>2014年同屆中選會原始elbase行政區名稱</strong>重新識別；各站與縣市票數須完全對帳。跨年只比對同縣市、同碼同名鄉鎮市區，不直接拼接投票所編號。</p>'
   +'<div class="turnout-stats"><div><small>2014→2018年匹配縣市</small><strong>'+num(a.matched_counties)+' / 22</strong></div>'
   +'<div><small>2014→2018年匹配行政區</small><strong>'+num(a.matched_towns)+'</strong></div>'
   +'<div><small>2018→2022年匹配縣市</small><strong>'+num(b.matched_counties)+' / 22</strong></div>'
   +'<div><small>2018→2022年匹配行政區</small><strong>'+num(b.matched_towns)+'</strong></div></div>'
   +'<div class="turnout-tablewrap"><table class="turnout-table"><thead><tr><th>固定公式</th>'
   +'<th>預測2018年 MAE (pp)</th><th>2018相對基準</th>'
   +'<th>預測2022年 MAE (pp)</th><th>2022相對基準</th></tr></thead><tbody>'
   +rows+'</tbody></table></div>'
   +'<p class="turnout-note">比較公式只使用各測試年份上一屆已知投票率，沒有在2018年預測時使用2018結果、也沒有在2022年預測時使用2022結果。兩個周期可比的是方法，不是完全相同的行政區樣本；不合併兩屆MAE。表內負的相對基準差額表示誤差改善。</p>'
   +'<p>兩個周期均低於直接延用基準的方法：'
   +(check.improved_both_cycles.length?check.improved_both_cycles.map(k=>esc(methods.find(x=>x[0]===k)?.[1]||k)).join('、'):'無')
   +'。</p>'
   +(historyRows.length?'<h3>'+esc(county)+'：2014—2018年行政區實際投票率</h3>'
    +'<div class="turnout-tablewrap"><table class="turnout-table"><thead><tr><th>行政區</th>'
    +'<th>2014年</th><th>2018年</th><th>變動</th><th>站點數</th></tr></thead><tbody>'
    +townRows+'</tbody></table></div>':
    '<p>這個縣市沒有通過2014—2018年同碼同名的配對，不填造缺失資料。</p>')
   +'<p class="turnout-special"><strong>驗證限制：</strong>2014與2018同碼同名不等於行政邊界及人口構成不變；兩期回測仍是已知歷史結果的回溯檢驗。2022年最好的「全台舊趨勢25%」方案缺少跨2010→2014同邊界的訓練資訊，不能冒充已由2018年度再次驗證。這些試驗沒有候選人投票選擇聯合數據，不得作為2026年正式勝選機率修正依據。</p>'
   +'<p><a href="turnout-district-panel-2014-2018.json" download>下載2014—2018核對面板</a>'
   +' · <a href="turnout-two-cycle-town-validation.json" download>下載雙周期逐區誤差</a>'
   +' · <a href="turnout-county-two-cycle-2014-2022.json" download>下載獨立縣市層級驗證</a></p>'
   +'</section>';
}
