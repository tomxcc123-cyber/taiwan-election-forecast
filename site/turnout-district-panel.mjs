import {validateTwoCycleHistory} from './turnout-two-cycle-ui.mjs';
// Observed, matched administrative-town panel from CEC booths; NOT a causal
// turnout→candidate model or a new estimate of 2026 political preferences.
const esc=x=>String(x??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const norm=x=>String(x||'').replaceAll('臺','台').trim();
const pct=x=>Number.isFinite(x)?Number(x).toFixed(2)+'%':'—';
const pp=x=>Number.isFinite(x)?(x>0?'+':'')+Number(x).toFixed(2)+' pp':'—';
const nf=n=>new Intl.NumberFormat('zh-TW').format(n);
const colorDelta=v=>{
  if(!Number.isFinite(v))return '#cad5dc';
  const a=Math.abs(v);
  if(a<1)return '#e1e7eb';
  if(v<0) return a>=10?'#945823':a>=6?'#bc7b44':a>=3?'#d9a879':'#ead5be';
  return a>=10?'#6b5097':a>=6?'#9373b9':a>=3?'#b8a4cf':'#d9cfe6';
};
export function validateTownPanel(source){
  if(source?.schema_version!==1||source.kind!=='observed_turnout_district_panel_not_an_individual_turnout_model'||
    !source.official_forecast_unchanged||!Array.isArray(source.counties)||source.counties.length!==22)
    throw new Error('跨年鄉鎮市區原始資料格式不完整');
  if(!Number.isInteger(source.matched_districts)||source.matched_districts<=0)
    throw new Error('缺少經來源確認的比較單位');
  const seen=new Set();
  let n=0;
  for(const c of source.counties){
    if(!c.county||seen.has(c.county))throw new Error('縣市比較索引重複');
    seen.add(c.county);
    if(!Array.isArray(c.districts))throw new Error('縣市行政區原始統計缺失');
    const ids=new Set();
    for(const d of c.districts){
      if(!d.district||!d.district_code||ids.has(d.district_code))
        throw new Error('行政區跨年鍵重複');
      ids.add(d.district_code);
      const a=d.years?.['2018'],b=d.years?.['2022'];
      for(const v of [a,b]){
        if(!v||!Number.isInteger(v.electorate)||v.electorate<1||
            !Number.isInteger(v.ballots_cast)||v.ballots_cast<0||v.ballots_cast>v.electorate)
          throw new Error('歷史投票率原值無效');
      }
      if(Math.abs(d.delta_turnout_pp-100*(b.ballots_cast/b.electorate-a.ballots_cast/a.electorate))>0.00015)
        throw new Error('跨年行政區差額與原始整數不一致');
      n++;
    }
  }
  if(n!==source.matched_districts)throw new Error('配對行政區數目不守恆');
  return source;
}
export function districtPanelView(source,county='台北市'){
  if(!source) return '<section class="turnout-panel" id="turnoutDistrictPanel"><h2>跨年行政區投票率比較</h2><p>已核驗的2018—2022跨年資料尚未發佈，暫不展示推算數據。</p></section>';
  let data;
  try{data=validateTownPanel(source)}catch(e){return '<section class="turnout-panel" id="turnoutDistrictPanel"><h2>跨年行政區投票率比較</h2><p>資料檢驗未通過：'+esc(e.message)+'</p></section>';}
  const c=data.counties.find(x=>x.county===county)||data.counties[0];
  const districts=[...c.districts].sort((a,b)=>a.delta_turnout_pp-b.delta_turnout_pp);
  const matched=c.matched_districts;
  const base=c.county_observed_turnout_pp;
  const mean=base?base['2022']-base['2018']:null;
  const coverage=c['2022_matched_electorate_coverage'];
  const summary='<div class="turnout-stats">'
    +'<div><small>可比較縣市</small><strong>'+data.matched_counties+' / 22</strong></div>'
    +'<div><small>符合代碼＋名稱雙重匹配的行政區</small><strong>'+nf(data.matched_districts)+'</strong></div>'
    +'<div><small>本縣市觀測投票率變動</small><strong>'+pp(mean)+'</strong></div>'
    +'<div><small>本縣市2022選民涵蓋率</small><strong>'+pct(coverage*100)+'</strong></div></div>';
  const text=matched?
    '<p>本縣市共'+matched+'個鄉鎮市區符合2018／2022相同代碼、相同行政區名稱的篩選。地圖以當年該行政區實際投票數除以選舉人數，顯示變化百分點；不使用2026模型推算。</p>':
    '<p class="turnout-special">目前這個縣市不具備經雙重核對的可比較行政區。'+esc(c.exclusion_reasons.join('、'))+'。不製造變化值。</p>';
  const reasons=c.unmatched_2018.length||c.unmatched_2022.length?
     '<p class="turnout-note">未能逐區雙重匹配：2018年'+c.unmatched_2018.length+'個、2022年'+c.unmatched_2022.length+'個。其餘單位才進入比較。</p>':'';
  const rows=districts.map(d=>{
    const left=d.years['2018'],right=d.years['2022'];
    return '<tr><td>'+esc(d.district)+'</td>'
      +'<td>'+pct(left.ballots_cast/left.electorate*100)+'</td>'
      +'<td>'+pct(right.ballots_cast/right.electorate*100)+'</td>'
      +'<td><span class="turnout-delta-chip" style="--town-color:'+colorDelta(d.delta_turnout_pp)+'">'+pp(d.delta_turnout_pp)+'</span></td>'
      +'<td>'+nf(right.electorate)+'</td>'
      +'<td>'+nf(left.stations)+' → '+nf(right.stations)+'</td></tr>';
  }).join('');
  return '<section class="turnout-panel" id="turnoutDistrictPanel"><header><small>OFFICIAL CEC · MATCHED DISTRICT PANEL</small><h2>2018—2022 鄉鎮市區投票率變化與GIS</h2></header>'
    +'<p>以原始投開票所的票數及選民數重新聚合；僅對行政區代碼與名稱在兩屆均一致的單位做算術比較。變化只代表歷史觀測，並非2018投票所與2022投票所一對一配對。</p>'
    +summary+text
    +(districts.length?'<div class="turnout-map-layout"><div class="turnout-map-shell"><svg id="townTurnoutMap" role="img" aria-label="'+esc(c.county)+'2018至2022投票率變化，行政區著色圖" viewBox="0 0 680 500" preserveAspectRatio="xMidYMid meet"><text x="20" y="40">行政區GIS地圖載入中…</text></svg>'
    +'<p class="turnout-map-key">投票率變動（百分點）：<span style="background:#bc7b44"></span>下降　<span style="background:#e1e7eb"></span>±1pp內　<span style="background:#9373b9"></span>上升　<span style="background:#cad5dc"></span>無法匹配</p></div>'
    +'<div class="turnout-map-detail" id="turnoutMapInspector">在地圖中選取行政區查看兩屆票數與投票率。</div></div>':'')
    +(reasons||'')
    +(districts.length?'<div class="turnout-tablewrap"><table class="turnout-table"><thead><tr><th>鄉鎮市區</th><th>2018投票率</th><th>2022投票率</th><th>變動</th><th>2022選舉人</th><th>投票所數（2018→2022）</th></tr></thead><tbody>'+rows+'</tbody></table></div>':'')
    +'<p class="turnout-note">重要限制：行政區代碼和名稱一致不等於邊界與人口組成完全不變。此模組未使用候選人票數或選民個體參與資料，不呈現投票率造成政黨得票增減的因果估計。2014原始行政區名稱有缺失，暫不混入雙年度面板；2022嘉義市單獨選期亦不強行配對。</p>'
    +'<p><a href="turnout-district-panel-2018-2022.json" download>下載經對帳的歷史行政區面板</a> · <a href="'+esc(data.source_url)+'" target="_blank" rel="noopener noreferrer">中選會原始開放資料</a></p></section>';
}

// Each historical cycle has its own request token. A second map must not
// invalidate the first map's in-flight topology request.
const requestVersions=new Map();
export async function drawTurnoutDistrictMap(panel,county,topologyUrl,options={}){
  const prior=options.period==='2014_to_2018';
  const mapId=prior?'priorTownTurnoutMap':'townTurnoutMap';
  const inspectorId=prior?'priorTurnoutMapInspector':'turnoutMapInspector';
  const from=prior?'2014':'2018',to=prior?'2018':'2022';
  const element=document.getElementById(mapId);
  if(!element)return;
  const id=(requestVersions.get(mapId)||0)+1;
  requestVersions.set(mapId,id);
  const obsolete=()=>id!==requestVersions.get(mapId)||!element.isConnected;
  const message=text=>{if(obsolete())return;while(element.firstChild)element.removeChild(element.firstChild);const t=document.createElementNS('http://www.w3.org/2000/svg','text');t.setAttribute('x','20');t.setAttribute('y','35');t.textContent=text;element.append(t);};
  let source;
  try{source=prior?validateTwoCycleHistory(panel,options.report).panel:validateTownPanel(panel)}catch{message('尚無經核驗的行政區面板');return;}
  const c=source.counties.find(x=>x.county===county);
  if(!c?.districts.length||!topologyUrl){message('本場沒有可比較的行政區幾何圖層');return;}
  try{
    const r=await fetch(topologyUrl,{cache:'force-cache'});
    if(!r.ok)throw Error('行政區圖資不可讀取');
    const topo=await r.json();
    if(obsolete())return;
    if(!globalThis.d3||!globalThis.topojson||!topo.objects?.map)throw Error('圖資解碼器缺失');
    const d3=globalThis.d3,topojson=globalThis.topojson;
    const feature=topojson.feature(topo,topo.objects.map);
    const projection=d3.geoMercator().fitExtent([[22,22],[658,474]],feature);
    const path=d3.geoPath(projection);
    const names=new Map(c.districts.map(x=>[norm(x.district),x]));
    const root=d3.select(element);
    root.selectAll('*').remove();
    const linked=new Set();
    root.selectAll('path').data(feature.features).enter().append('path')
      .attr('d',path)
      .attr('fill',d=>{
        const row=names.get(norm(d.properties?.name));
        if(row)linked.add(row.district);
        return colorDelta(row?.delta_turnout_pp);
      })
      .attr('stroke','#fff').attr('stroke-width',1.4)
      .attr('tabindex',0)
      .attr('role','button')
      .attr('aria-label',d=>{
         const row=names.get(norm(d.properties?.name));
         return row?row.district+' 投票率變化 '+pp(row.delta_turnout_pp):norm(d.properties?.name)+' 尚無可比數據';
      })
      .on('click',(_,feature)=>select(feature))
      .on('keydown',(event,feature)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select(feature);}});
    function select(f){
      const row=names.get(norm(f.properties?.name));
      const target=document.getElementById(inspectorId);
      if(!target||!row)return;
      const a=row.years[from],b=row.years[to];
      target.textContent=row.district+'：'+from+'投票率 '+pct(a.ballots_cast/a.electorate*100)+'，'+to+'為 '+pct(b.ballots_cast/b.electorate*100)+'，變動 '+pp(row.delta_turnout_pp)+'；兩屆投開票所數 '+a.stations+' → '+b.stations+'。';
    }
    const unmatched=c.districts.filter(x=>!linked.has(x.district));
    if(unmatched.length) {
      const target=document.getElementById(inspectorId);
      if(target)target.textContent='GIS圖層與官方統計的行政區名稱有 '+unmatched.length+' 處無法匹配；表格數據仍有效，但未匹配單位不著色。';
    }
  }catch(e){message('GIS行政區圖層暫不可用：'+String(e.message||e));}
}
