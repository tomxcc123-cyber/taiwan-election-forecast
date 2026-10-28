// Public, aggregate historical election research. Never predicts how an
// individual voter or a neighbourhood will vote in 2026.
const esc=x=>String(x??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const fmt=(v,n=2)=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(n):'—';
const signed=v=>typeof v==='number'&&Number.isFinite(v)?(v>0?'+':'')+fmt(v)+' pp':'—';
const readable=n=>Number(n).toLocaleString('zh-TW');

export function verifyAssociation(data){
  if(data?.schema_version!==1||data.kind!=='historical_ecological_candidate_turnout_association_only'||
    !data.no_causal_claim||!data.no_2026_prediction||!data.official_forecast_unchanged||
    !Array.isArray(data.counties)||data.counties.length!==22||
    !Number.isInteger(data.matched_towns)||data.matched_towns<=0)
    throw Error('缺少經中選會逐站對帳的候選人得票來源');
  let districts=0,valid=0;
  for(const county of data.counties){
    if(!Array.isArray(county.districts))throw Error('候選人資料不完整');
    for(const d of county.districts){
      if(!d.district_code||!d.district||!Number.isFinite(d.delta_turnout_pp))
        throw Error('行政區識別與投票率欄位無效');
      for(const year of ['2018','2022']){
        const v=d.years?.[year];
        if(!v||!Number.isInteger(v.valid_votes)||v.valid_votes<1||!Number.isInteger(v.KMT_votes)||!Number.isInteger(v.DPP_votes)||
          v.KMT_votes+v.DPP_votes>v.valid_votes)
          throw Error('候選人得票不能與有效票對帳');
      }
      districts++;
      if(d.party_comparison_eligible){
        if(!Number.isFinite(d.delta_KMT_two_party_share_pp))throw Error('跨屆雙方競爭比率無效');
        valid++;
      }
    }
  }
  if(districts!==data.matched_towns||valid!==data.party_comparable_towns)
    throw Error('行政區與候選人配對數目不守恆');
  return data;
}
export function verifyHoldout(report){
  if(report?.schema_version!==1||report.kind!=='cec_historical_time_ordered_turnout_holdout'||
    report.training_information_cutoff_election!==2018||report.held_out_election!==2022||
    !report.no_2022_training_inputs||report.calibration_claim!==false||
    report.official_2026_forecast_unchanged!==true||
    !Number.isInteger(report.coverage?.districts)||report.coverage.districts<1)
    throw Error('投票率歷史留出測試時間順序或資料不完整');
  return report;
}

export function associationPanel(raw,holdout,county='台北市'){
  let data=null,score=null;
  try{data=verifyAssociation(raw)}catch{}
  try{score=verifyHoldout(holdout)}catch{}
  let s='<section class="turnout-panel" id="turnoutVoteValidation"><header><small>CEC CANDIDATE VOTES · TIME-ORDERED EVALUATION</small><h2>投票率與歷史選舉得票：來源核對與留出測試</h2></header>'
   +'<p>這裡將同一場選舉、同一投開票所的候選人票數逐站加總到鄉鎮市區，再以2018／2022年相同代碼及名稱的行政區做歷史比較。關聯不代表因果，也不代表2026年任何群體或政黨的投票行為。</p>';
  if(score){
    const methods=score.turnout_forecast_score||{};
    const baseline=methods['2018_persistence'];
    const drift=methods['2014_to_2018_county_drift'];
    s+='<div class="turnout-stats">'
       +'<div><small>樣本外測試年份</small><strong>2022</strong></div>'
       +'<div><small>測試行政區</small><strong>'+readable(score.coverage.districts)+'</strong></div>'
       +'<div><small>2018年投票率直接延用 MAE</small><strong>'+fmt(baseline?.electorate_weighted_mae_pp)+' pp</strong></div>'
       +'<div><small>使用2014—2018縣市變化作修正 MAE</small><strong>'+fmt(drift?.electorate_weighted_mae_pp)+' pp</strong></div></div>'
       +'<p class="turnout-note">MAE按2022年各行政區選舉人數加權。兩種2022投票率預測都只使用2018年之前已發生的歷史資料；沒有用2022投票結果估計權重。此處只評估投票率本身，不代表已提高候選人勝率預測。</p>';
  }else{
    s+='<p class="turnout-special">2022時間順序留出評估尚未通過來源或日期驗證，不顯示臆測的準確率。</p>';
  }
  if(data){
    const eligible=data.counties.find(c=>c.county===county);
    const cohorts=data.counties.filter(c=>c.status==='audited_historical_town_observation');
    s+='<div class="turnout-stats">'
      +'<div><small>對帳完成的縣市</small><strong>'+data.matched_counties+' / 22</strong></div>'
      +'<div><small>跨年相同地區的行政區</small><strong>'+readable(data.matched_towns)+'</strong></div>'
      +'<div><small>兩黨均有正式候選人的可比行政區</small><strong>'+readable(data.party_comparable_towns)+'</strong></div>'
      +'<div><small>縣市內去平均的歷史相關係數</small><strong>'+fmt(score?.association?.within_county_centered_weighted_pearson,3)+'</strong></div></div>'
      +'<p class="turnout-note">最後一項是選後、行政區層級的描述性相關係數；僅以有可比兩黨候選人的行政區計算，且按縣市去平均、以2022年選民數加權。它沒有控制候選人更替、地方社經結構或共同政治事件，不可視為投票率的因果係數或選前預測參數。</p>';
    if(eligible?.districts?.length){
      const districts=eligible.districts.filter(d=>d.party_comparison_eligible).slice()
        .sort((a,b)=>a.district.localeCompare(b.district,'zh-TW'));
      s+='<h3>'+esc(county)+'：2018—2022鄉鎮市區觀測比較</h3>'
        +(districts.length?'<div class="turnout-tablewrap"><table class="turnout-table"><thead><tr><th>行政區</th><th>投票率變動</th><th>2018國民黨兩黨票占比</th><th>2022國民黨兩黨票占比</th><th>實際得票占比變化</th></tr></thead><tbody>'
        +districts.map(d=>'<tr><td>'+esc(d.district)+'</td><td>'+signed(d.delta_turnout_pp)+'</td>'
          +'<td>'+fmt(d.years['2018'].KMT_two_party_share_pct)+'%</td>'
          +'<td>'+fmt(d.years['2022'].KMT_two_party_share_pct)+'%</td>'
          +'<td>'+signed(d.delta_KMT_two_party_share_pp)+'</td></tr>').join('')
        +'</tbody></table></div>':
        '<p>該縣市兩屆不具備候選人提名相容的比較資料。</p>');
    }
    s+='<p><a href="cec-town-candidate-association-2018-2022.json" download>下載中選會候選人逐站核對後的行政區統計</a>'
      +(score?' · <a href="turnout-holdout-2018-2022.json" download>下載2022樣本外測試逐區誤差</a>':'')+'</p>';
  }else{
    s+='<p class="turnout-special">逐站候選人票數原始來源尚未完成核對；不以行政區歷史平均代替真實得票。</p>';
  }
  return s+'<p class="turnout-note">方法門檻：2018與2022實際投票率和得票的共同變化是「選後觀察」；將2022實際投票率拿去預測2022候選人結果會造成資訊洩漏，因此不允許。現階段不使用此關聯對2026 HB-TLEF正式模型作任何候選人、政黨或區域修正。</p></section>';
}
