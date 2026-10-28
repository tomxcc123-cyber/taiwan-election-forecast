import {turnoutScenario,turnoutOverview,TURNOUT_DELTA_OPTIONS} from './turnout-sensitivity.mjs';
import {precinctPanel} from './precinct-turnout-ui.mjs';
import {districtPanelView} from './turnout-district-panel.mjs';
const esc=x=>String(x??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const pct=x=>Number(x).toFixed(2)+'%';
const fmt=x=>new Intl.NumberFormat('zh-TW',{maximumFractionDigits:0}).format(Math.abs(x));
const signed=(x,n=2)=>((x>0?'+':'')+Number(x).toFixed(n));
const boundsBar=(candidate)=>{
  const lo=100*candidate.lower,hi=100*candidate.upper,mid=100*candidate.model_valid_vote_share;
  return '<div class="turnout-range" aria-label="數學界限 '+pct(lo)+' 至 '+pct(hi)+'">'
    +'<span class="turnout-range-possible" style="left:'+lo.toFixed(3)+'%;width:'+(hi-lo).toFixed(3)+'%"></span>'
    +'<span class="turnout-range-center" style="left:'+mid.toFixed(3)+'%"></span></div>';
};
export function turnoutPage(model,source,county='台北市',deltaPp=0,precinctIndex=null,precinctRecord=null,precinctCounty='台北市',precinctYear=2022,precinctDistrict='all',districtPanel=null){
  if(!source) return '<section class="turnout-page"><h1>投票率影響與敏感度</h1><p>無法核驗中選會歷史投票率資料。未用推算數字代替。</p></section>';
  try{
    const rows=turnoutOverview(model,source,deltaPp);
    const active=rows.some(x=>x.county===county)?county:rows[0].county;
    const selected=turnoutScenario(model,source,{county:active,deltaPp});
    const ordered=[...selected.candidates].sort((a,b)=>b.model_valid_vote_share-a.model_valid_vote_share);
    const hist='<table class="turnout-table"><thead><tr><th>縣市</th><th>2018投票率</th><th>2022投票率</th><th>歷史變化（pp）</th><th>假設投票率</th><th>領先優勢仍具穩健性的模擬比例</th></tr></thead><tbody>'
      +rows.map(r=>'<tr '+(r.county===active?'class="turnout-selected"':'')+'><td>'+esc(r.county)+'</td>'
        +'<td>'+pct(r.turnout_2018_pct)+'</td><td>'+pct(r.turnout_2022_pct)+'</td>'
        +'<td>'+signed(r.observed_change_pp)+' pp</td><td>'+pct(r.scenario_turnout_pct)+'</td>'
        +'<td>'+pct(r.robustness_share*100)+'</td></tr>').join('')
      +'</tbody></table>';
    const ranges='<div class="turnout-tablewrap"><table class="turnout-table"><thead><tr><th>候選人</th><th>原模擬平均有效票占比</th><th>未知新增／流失選民組成下的數學範圍</th><th>上下界</th></tr></thead><tbody>'
      +ordered.map(x=>'<tr><td>'+esc(x.name)+'</td><td>'+pct(100*x.model_valid_vote_share)+'</td>'
      +'<td>'+boundsBar(x)+'</td><td>'+pct(100*x.lower)+'—'+pct(100*x.upper)+'</td></tr>').join('')
      +'</tbody></table></div>';
    return '<section class="turnout-page">'
      +'<header class="turnout-intro"><small>VOTER PARTICIPATION · SOURCE-VERIFIED SENSITIVITY</small><h1>投票率與結果敏感度</h1>'
      +'<p>依中選會委託研究彙整2018、2022年22縣市長選舉之選舉人數與投票數。透過假設投票率變化，量化額外／減少投票數及候選人得票占比的可行數學區間；不推定新增選民的政治偏好，不改動正式HB-TLEF預測。</p></header>'
      +'<div class="turnout-stats"><div><small>2018全台投票率</small><strong>66.96%</strong></div>'
      +'<div><small>2022全台投票率</small><strong>60.97%</strong></div>'
      +'<div><small>全台歷史變化</small><strong>−5.99 pp</strong></div>'
      +'<div><small>資料覆蓋</small><strong>22／22縣市</strong></div></div>'
      +'<section class="turnout-panel"><h2>投票參與情境</h2><div class="turnout-controls">'
      +'<label for="turnoutCounty">縣市 <select id="turnoutCounty">'+rows.map(r=>'<option value="'+esc(r.county)+'" '+(r.county===active?'selected':'')+'>'+esc(r.county)+'</option>').join('')+'</select></label>'
      +'<label for="turnoutDelta">相對2022年投票率假設 <select id="turnoutDelta">'+TURNOUT_DELTA_OPTIONS.map(d=>'<option value="'+d+'" '+(d===deltaPp?'selected':'')+'>'+signed(d,0)+' 個百分點'+(d===0?'（對照組）':'')+'</option>').join('')+'</select></label></div>'
      +'<div class="turnout-stats turnout-county-stats"><div><small>'+esc(active)+' 2022實際投票率</small><strong>'+pct(selected.historical_2022_pct)+'</strong></div>'
      +'<div><small>本情境假設投票率</small><strong>'+pct(selected.scenario_turnout_pct)+'</strong></div>'
      +'<div><small>相對2022年選舉人數的票數差額</small><strong>'+(selected.scenario_change_ballots>=0?'+':'−')+fmt(selected.scenario_change_ballots)+'</strong></div>'
      +'<div><small>模擬領先差距在任意票源下仍穩健</small><strong>'+pct(selected.robustness_share*100)+'</strong></div></div>'
      +'<p class="turnout-note">上述票數差額以2022年該縣市選舉人數作分母，非2026年預估投票數；「穩健」代表該模擬路徑的前兩名差距即使新增投票全流向第二名、或減少票全從第一名扣除，仍不能翻轉次序。其餘情況只是存在數學上的改變可能，不代表勝選機率。</p>'
      +(selected.notes?'<p class="turnout-special">資料比較註記：'+esc(selected.notes)+'</p>':'')
      +'</section>'
      +'<section class="turnout-panel"><h2>'+esc(active)+' 候選人有效票占比的條件範圍</h2>'
      +'<p>淺色區間是「投票率固定變動'+signed(deltaPp,0)+'個百分點，受影響選民的選票可任意分配」的邏輯上下界，不是機率區間；深色刻線為未改變原模型支持組成時的平均值。各候選人個別上下界不會同時取到。</p>'
      +ranges+'</section>'
      +districtPanelView(districtPanel,precinctCounty)
      +precinctPanel(precinctIndex,precinctRecord,precinctCounty,precinctYear,precinctDistrict)
      +'<section class="turnout-panel"><h2>各縣市歷史參與與情境診斷</h2>'
      +'<p>每列均用該縣市2022年的實際投票率做參照；紅／綠等政治分類不參與推算。由於2022年嘉義市長投票另期舉行，其跨年比較需特別審慎。</p>'
      +'<div class="turnout-tablewrap">'+hist+'</div></section>'
      +'<section class="turnout-panel"><h2>方法與資料限制</h2>'
      +'<p>投票率＝投票數／選舉人數，投票數含無效票；模型的候選人得票占比是有效票比例。為展示數學界限，暫假定無效票占比不隨投票率改變。若無分群投票偏好資料，不能單憑地方投票率變化判斷哪位候選人受益，也不能推定投票率與候選人支持之間的因果關係。</p>'
      +'<p>2018年六都與其他縣市長選舉總投票率66.96%，2022年60.97%；本頁沒有提供2026年投票率的統計預測，也沒有把假設作為正式模型輸入。逐投開票所數據現已可依2014、2018、2022年官方檔案逐年核對；但它只能觀察總體投票行為，仍需要選民調查中的投票參與與候選人意向聯合測量、行政邊界對接及跨屆留出測試，才可能判定投票率能否成為正式模型因素。</p>'
      +'<p>來源：<a href="'+esc(source.source.url)+'" target="_blank" rel="noopener noreferrer">'+esc(source.source.report)+'</a>，表1-4（2018）及表1-7（2022）。<a href="turnout-history-2018-2022.json" download>下載22縣市原始投票率資料</a>。</p>'
      +'</section></section>';
  }catch(e){
    return '<section class="turnout-page"><h1>投票率影響與敏感度</h1><p>資料未通過核驗：'+esc(e.message)+'。已停止產生情境結果。</p></section>';
  }
}
