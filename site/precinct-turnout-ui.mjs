// Precinct-level CEC history is directly observed data, not a forecast.
// Station identifiers are not linked across elections.
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=x=>Number.isFinite(x)?(x*100).toFixed(2)+'%':'—';
const num=x=>Number.isFinite(x)?new Intl.NumberFormat('zh-TW').format(x):'—';
const safe=(path)=>/^cec-precincts\/(?:2014|2018|2022)-[\p{Script=Han}]+\.json$/u.test(path);

export function validatePrecinctIndex(index){
  if(index?.schema_version!==1||index.races_expected!==66||
     !Array.isArray(index.entries)||index.entries.length!==66)
    throw new Error('投票所公開資料未達到66場歷史選舉核對標準');
  const matches=new Set();
  for(const r of index.entries){
    if(![2014,2018,2022].includes(r.year)||!r.county||
       matches.has(r.year+'|'+r.county))
      throw new Error('投票所歷史索引包含重複或無效選舉');
    matches.add(r.year+'|'+r.county);
    if(r.status==='official_precinct_aggregate_verified'){
      if(!safe(r.path)||!Number.isInteger(r.precinct_count)||r.precinct_count<1)
        throw new Error('投票所索引沒有合法的來源檔案');
    }else if(r.status!=='district_only_original'){
      throw new Error('未知投票所來源等級');
    }
  }
  return index;
}
export function validatePrecinctRecord(index,record,year,county){
  const entry=validatePrecinctIndex(index).entries.find(r=>r.year===year&&r.county===county);
  if(!entry||entry.status!=='official_precinct_aggregate_verified')
    throw new Error('這場選舉沒有可用的投票所明細');
  if(record?.schema_version!==1||record.year!==year||record.county!==county||
     record.precinct_count!==entry.precinct_count||
     !Array.isArray(record.precincts)||record.precincts.length!==entry.precinct_count)
    throw new Error('投票所明細與官方索引不一致');
  const total={valid_votes:0,invalid_votes:0,ballots_cast:0,electorate:0};
  const seen=new Set();
  for(const p of record.precincts){
    const key=JSON.stringify(p.geo_codes);
    if(seen.has(key))throw new Error('投票所重複代碼');
    seen.add(key);
    if(Object.keys(total).some(k=>!Number.isInteger(p[k])||p[k]<0)||
       p.valid_votes+p.invalid_votes!==p.ballots_cast)
      throw new Error('投票所票數守恆失敗');
    for(const k of Object.keys(total))total[k]+=p[k];
  }
  if(Object.keys(total).some(k=>total[k]!==record.totals[k]||total[k]!==entry.totals[k]))
    throw new Error('投票所與縣市歷史總數不一致');
  return record;
}
export function precinctDistricts(record){
  if(!record)return [];
  const grouped=new Map();
  for(const p of record.precincts){
    const key=p.geo_codes.slice(0,4).join('/');
    let x=grouped.get(key);
    if(!x){
      x={code:key,name:p.district_name||'行政區 '+p.geo_codes[3],
        stations:0,electorate:0,ballots_cast:0,valid_votes:0,invalid_votes:0};
      grouped.set(key,x);
    }
    x.stations++;
    for(const k of ['electorate','ballots_cast','valid_votes','invalid_votes'])
      x[k]+=p[k];
  }
  return [...grouped.values()].sort((a,b)=>a.name.localeCompare(b.name,'zh-TW'));
}
export function precinctPanel(index,record,county='台北市',year=2022,district='all'){
  let source;
  try{source=validatePrecinctIndex(index)}
  catch(e){return '<section class="turnout-panel"><h2>投開票所歷史資料</h2><p>原始明細來源尚未通過建置核驗，未以鄉鎮平均值冒充投票所資料。</p></section>';}
  const entries=source.entries,selected=entries.find(x=>x.year===year&&x.county===county);
  const verified=entries.filter(x=>x.status==='official_precinct_aggregate_verified');
  let effective=null,message='';
  if(selected?.status==='district_only_original')
    message='<p class="turnout-special">本場官方對應歷史資料只有區級合計，尚未取得可逐站核對的縣市長明細，不顯示假投票所。</p>';
  else if(selected?.status==='official_precinct_aggregate_verified'){
    try{effective=validatePrecinctRecord(source,record,year,county)}
    catch(e){message='<p class="turnout-special">已核實原始來源，但所選明細尚未載入或未通過核驗。'+esc(e.message)+'</p>';}
  }else message='<p class="turnout-special">此縣市年份沒有可供核對的投票所檔案。</p>';
  const areas=precinctDistricts(effective),chosen=district==='all'?'all':areas.some(x=>x.code===district)?district:'all';
  const booths=effective?.precincts.filter(p=>chosen==='all'||p.geo_codes.slice(0,4).join('/')===chosen)||[];
  const rows=booths.slice(0,45);
  const yearSelector=[2014,2018,2022].map(v=>'<option value="'+v+'" '+(year===v?'selected':'')+'>'+v+'</option>').join('');
  const countySelector=[...new Set(entries.map(e=>e.county))].sort().map(name=>'<option value="'+esc(name)+'" '+(county===name?'selected':'')+'>'+esc(name)+'</option>').join('');
  return '<section class="turnout-panel" id="precinctTurnoutHistory"><h2>中選會投開票所原始資料 · 2014—2022</h2>'
    +'<p>此區為實際已公布的歷史投票統計，並非2026投票率預測。每一站的票數均和該場縣市長選舉原始縣市總數對帳；對照的是投票數（含無效票）與選舉人數。</p>'
    +'<div class="turnout-stats">'
    +'<div><small>縣市長選舉場數</small><strong>66</strong></div>'
    +'<div><small>可核實投票所的場數</small><strong>'+verified.length+' / 66</strong></div>'
    +'<div><small>歷史投開票所記錄數</small><strong>'+num(source.station_rows)+'</strong></div>'
    +'<div><small>僅區級資料</small><strong>'+entries.filter(x=>x.status==='district_only_original').length+'</strong></div></div>'
    +'<div class="turnout-controls"><label for="precinctCounty">縣市<select id="precinctCounty">'+countySelector+'</select></label>'
    +'<label for="precinctYear">歷史年份<select id="precinctYear">'+yearSelector+'</select></label>'
    +(areas.length?'<label for="precinctDistrict">鄉鎮市區<select id="precinctDistrict"><option value="all">全部行政區</option>'+areas.map(x=>'<option value="'+esc(x.code)+'" '+(chosen===x.code?'selected':'')+'>'+esc(x.name)+'</option>').join('')+'</select></label>':'')+'</div>'
    +message
    +(effective?'<p>目前顯示：'+esc(county)+' '+year+'年，原始檔共'+num(effective.precinct_count)+'個投票所；有效票'+num(effective.totals.valid_votes)+'、無效票'+num(effective.totals.invalid_votes)+'、投票數'+num(effective.totals.ballots_cast)+'、選舉人數'+num(effective.totals.electorate)+'。所有合計已核驗。</p>':'')
    +(areas.length?'<div class="turnout-tablewrap"><table class="turnout-table"><thead><tr><th>鄉鎮市區</th><th>投開票所數</th><th>選舉人數</th><th>投票數</th><th>投票率</th><th>無效票</th></tr></thead><tbody>'
      +areas.map(x=>'<tr><td>'+esc(x.name)+'</td><td>'+num(x.stations)+'</td><td>'+num(x.electorate)+'</td><td>'+num(x.ballots_cast)+'</td><td>'+pct(x.electorate?x.ballots_cast/x.electorate:NaN)+'</td><td>'+num(x.invalid_votes)+'</td></tr>').join('')
      +'</tbody></table></div>':'')
    +(rows.length?'<h3>投開票所明細（目前顯示 '+rows.length+' / '+booths.length+' 站）</h3>'
      +'<div class="turnout-tablewrap"><table class="turnout-table"><thead><tr><th>投開票所編號</th><th>行政區</th><th>村里</th><th>選舉人數</th><th>投票數</th><th>投票率</th><th>無效票</th></tr></thead><tbody>'
      +rows.map(p=>'<tr><td>'+esc(p.precinct_number)+'</td><td>'+esc(p.district_name||p.geo_codes[3])+'</td><td>'+esc(p.village_name||p.geo_codes[4])+'</td><td>'+num(p.electorate)+'</td><td>'+num(p.ballots_cast)+'</td><td>'+pct(p.electorate?p.ballots_cast/p.electorate:NaN)+'</td><td>'+num(p.invalid_votes)+'</td></tr>').join('')
      +'</tbody></table></div>':'')
    +'<p class="turnout-note">投開票所編號及村里行政區界可能跨年改動，不能把同號站點當成同一地點。本站不對投票所居民的政黨偏好或個人投票行為作推斷；所有數據僅供歷史選舉研究。</p>'
    +'<p>官方資料：<a href="'+esc(source.source_url)+'" target="_blank" rel="noopener noreferrer">中央選舉委員會開放資料</a>。<a href="cec-precincts/index.json" download>下載逐年逐縣市覆蓋索引</a>'
    +(selected?.path? ' · <a href="'+esc(selected.path)+'" download>下載目前縣市投開票所明細</a>':'')+'</p></section>';
}
