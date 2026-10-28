// Historical ecological three-cycle audit. No changes to candidate model,
// turnout scenario, market fusion, or 2026 political preference forecasts.
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const percent=n=>Number.isFinite(n)?(n>0?'+':'')+n.toFixed(2):'—';
const number=n=>Number.isInteger(n)?new Intl.NumberFormat('zh-TW').format(n):'—';
const METHODS=['persistence','county_shrink_75','county_shrink_50'];
const COHORTS=[
 ['common_towns','三屆同碼同名共同樣本'],
 ['unchanged_station_count','三屆投開票所數量相同'],
 ['electorate_change_within_8pct','兩周期選舉人數變化均不超過8%'],
 ['both_diagnostic_flags_clear','同時符合上述兩個選後條件']
];

export function validateThreeYearAudit(data){
  if(data?.schema_version!==1||
    data.kind!=='cec_three_year_common_town_ecological_stability_audit'||
    data.geography_status!=='code_and_original_name_or_official_2015_rename_no_historical_boundary_overlay'||
    data.candidate_vote_data_used!==false||
    data.no_individual_voter_inference!==true||
    data.forecast_2026_modified!==false||
    data.promotion_gate?.status!=='blocked'||
    data.promotion_gate?.formal_hb_tlef_unchanged!==true||
    data.promotion_gate?.allow_2026_candidate_win_probability_modification!==false||
    !Number.isInteger(data.matched_towns)||data.matched_towns<1||
    !Array.isArray(data.towns)||data.towns.length!==data.matched_towns||
    !Array.isArray(data.county_diagnostics)||
    data.county_diagnostics.length!==data.matched_counties||
    !Array.isArray(data.unmatched_recent)||!Array.isArray(data.unmatched_prior)||
    data['2018_duplicate_source_counts_disagreements']!==0)
    throw new Error('三屆行政區資料核驗或模型隔離失敗');
  const seen=new Set();
  for(const town of data.towns){
    const k=town.county+'|'+town.town_code+'|'+town.district;
    if((!town.code_and_name_only && !(town.documented_name_change?.spatial_boundary_verified===false && town.documented_name_change?.cec_minutes_url==='https://web.cec.gov.tw/api/file/d97c9325-90b2-44bc-a430-c43197e58ea0.pdf'))||!town['2018_duplicate_source_counts_identical']||seen.has(k))
      throw new Error('三屆行政區跨年對接紀錄不完整');
    seen.add(k);
    for(const year of ['2014','2018','2022'])
      if(!Number.isInteger(town.year_electorates?.[year])||town.year_electorates[year]<=0||
        !Number.isInteger(town.year_station_counts?.[year])||town.year_station_counts[year]<=0)
        throw new Error('行政區年度選民或站點數異常');
  }
  for(const [key] of COHORTS){
    const c=data.cohorts?.[key];
    if(!c)throw new Error('三屆樣本敏感性組缺失');
    for(const period of ['2014_to_2018','2018_to_2022']){
      const sample=c[period];
      if(!Number.isInteger(sample?.n_towns)||sample.n_towns<0||sample.n_towns>data.matched_towns)
        throw new Error('行政區樣本數異常');
      if(sample.n_towns>0&&!METHODS.every(m=>Number.isFinite(sample.scores?.[m])&&sample.scores[m]>=0))
        throw new Error('行政區共同樣本誤差指標異常');
    }
    if(c['2014_to_2018'].n_towns!==c['2018_to_2022'].n_towns)
      throw new Error('跨周期樣本不是同一組行政區');
  }
  if(data.cohorts.common_towns['2014_to_2018'].n_towns!==data.matched_towns)
    throw new Error('共同樣本未完全納入驗證');
  return data;
}

export function threeYearAuditPanel(raw){
  if(!raw)return '<section class="turnout-panel" id="turnoutThreeYearAudit"><h2>2014—2022三屆共同樣本核驗</h2><p>原始資料尚未完成來源交叉稽核，沒有顯示推算成果。</p></section>';
  let d;
  try{d=validateThreeYearAudit(raw)}
  catch(e){return '<section class="turnout-panel" id="turnoutThreeYearAudit"><h2>2014—2022三屆共同樣本核驗</h2><p>'+esc(e.message)+'；未使用未驗證資料。</p></section>';}
  const metric=(c,period,k)=>{
    const n=c[period].scores?.[k];
    return Number.isFinite(n)?n.toFixed(3):'—';
  };
  const rows=COHORTS.map(([key,label])=>{
    const c=d.cohorts[key];
    return '<tr><td>'+esc(label)+'</td><td>'+number(c['2014_to_2018'].n_towns)+'</td>'+
      '<td>'+metric(c,'2014_to_2018','persistence')+'</td>'+
      '<td>'+metric(c,'2014_to_2018','county_shrink_75')+'</td>'+
      '<td>'+metric(c,'2018_to_2022','persistence')+'</td>'+
      '<td>'+metric(c,'2018_to_2022','county_shrink_75')+'</td></tr>';
  }).join('');
  const countyRows=d.county_diagnostics.map(c=>
    '<tr><td>'+esc(c.county)+'</td><td>'+number(c.matched_towns)+'</td>'+
    '<td>'+number(c.station_count_changed)+'</td><td>'+number(c.electorate_change_gt_8pct)+'</td></tr>'
  ).join('');
  const excluded=arr=>arr.length?arr.map(x=>esc(x.county+' '+x.district)).join('、'):'無';
  return '<section class="turnout-panel" id="turnoutThreeYearAudit">'+
    '<header><small>OFFICIAL CEC · COMMON THREE-YEAR COHORT · HISTORICAL AUDIT ONLY</small><h2>2014—2022 三屆行政區共同樣本與地理可比性審計</h2></header>'+
    '<p>將2014—2018與2018—2022兩套已對帳的中選會行政區面板，以<strong>相同縣市、同一鄉鎮代碼及原始名稱</strong>連結；2015年官方確認的員林鎮→員林市、頭份鎮→頭份市設有嚴格名稱改制例外。再逐項核對兩個來源2018年的選舉人數、投票數、有效票、無效票及投開票所數。這是統計口徑的連續匹配，<strong>不是歷史行政邊界GIS重疊比對</strong>。</p>'+
    '<div class="turnout-stats">'+
      '<div><small>三屆共同行政區</small><strong>'+number(d.matched_towns)+'</strong></div>'+
      '<div><small>共同樣本縣市</small><strong>'+number(d.matched_counties)+' / 22</strong></div>'+
      '<div><small>投開票所數三屆不變</small><strong>'+number(d.unchanged_station_count_towns)+'</strong></div>'+
      '<div><small>至少一周期選民數變化超過8%</small><strong>'+number(d.electorate_change_gt_8pct_towns)+'</strong></div></div>'+
    '<p>具有中選會2015年正式名稱改制佐證而恢復對接的地區：<strong>'+number(d.documented_2015_name_changes_count||0)+'</strong>。名稱改制、站點總數核對與空間邊界完全一致是不同層次的驗證，不得混同。</p>'+ 
    '<h3>同一批行政區的兩周期歷史留出對照</h3>'+
    '<div class="turnout-tablewrap"><table class="turnout-table"><thead><tr><th>選後診斷分組</th><th>鄉鎮數</th><th>2018直接延用MAE</th><th>2018收縮25%MAE</th><th>2022直接延用MAE</th><th>2022收縮25%MAE</th></tr></thead><tbody>'+
    rows+'</tbody></table></div>'+
    '<p class="turnout-note">誤差單位是百分點（pp）；2018及2022兩次留出各自使用當屆實際選舉人數加權，同一年份內各方法在同一鄉鎮集合評分。8%為探索性品質標記，並非已驗證最優門檻。投開票所數量相等不證明地點、村里界或選民組成相同。</p>'+
    '<p class="turnout-special"><strong>不可作選前準確率證據：</strong>投開票所數量是否維持、選舉人數變動是否小於8%，都依賴留出年份的選後資料。按這些條件篩選的誤差改善可能是選樣偏差；所有分組均為事後穩健性診斷，不得因此修改2026正式候選人勝選機率或聲稱投票率對選票選擇存在因果影響。</p>'+
    '<h3>各縣市共同樣本的資料警示</h3><div class="turnout-tablewrap"><table class="turnout-table"><thead><tr><th>縣市</th><th>三屆配對鄉鎮</th><th>站點數變動地區</th><th>選民數變動超過8%地區</th></tr></thead><tbody>'+
    countyRows+'</tbody></table></div>'+
    '<p class="turnout-note">僅在前兩屆配對面板出現：'+excluded(d.unmatched_prior)+'；僅在後兩屆面板出現：'+excluded(d.unmatched_recent)+'。未符合三屆連續對接的地區不予拼接，且2022嘉義市另期選舉的來源缺口仍保留。</p>'+
    '<p>下一步需要取得<strong>選舉當期版本</strong>的國土測繪中心歷史行政區界，實施多邊形交集、面積差、跨屆代碼變動稽核，才可判定空間邊界是否等同。'+
    '<a href="'+esc(d.historical_boundary_reference)+'" target="_blank" rel="noopener noreferrer">國土測繪中心歷史鄉鎮界圖層</a> · '+
    '<a href="turnout-three-year-compatibility.json" download>下載三屆共同樣本及逐區品質標記</a>。</p></section>';
}
