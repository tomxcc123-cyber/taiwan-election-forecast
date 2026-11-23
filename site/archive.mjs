/* Historical data viewer: public during the November 2026 opinion-poll blackout.
   Never imports 2026 forecasts, polling feeds, candidate models, or market data. */
const YEARS = [2014, 2018, 2022];
const PALETTE = Object.freeze({KMT:'#366c9b', DPP:'#268369', TPP:'#439a98', IND:'#888d95', OTHER:'#98839f'});
const PARTY_NAME = Object.freeze({KMT:'國民黨',DPP:'民進黨',TPP:'民眾黨',IND:'無黨籍',OTHER:'其他政黨'});
const $ = selector => document.querySelector(selector);
const nameKey = value => String(value ?? '').normalize('NFKC').replaceAll('臺','台');
const safeNumber = n => Number.isFinite(Number(n)) ? Number(n) : 0;
const pct = n => safeNumber(n).toFixed(1)+'%';
const numeric = n => Math.round(safeNumber(n)).toLocaleString('zh-TW');
const el = (tag, className, content) => {
  const n = document.createElement(tag);
  if (className) n.className=className;
  if(content!=null)n.textContent=String(content);
  return n;
};
function party(candidate) {
  const v=candidate?.legacy_bloc || candidate?.party;
  return Object.hasOwn(PALETTE,v)?v:'OTHER';
}
const state={year:2022,metric:'winner',county:null,scope:'taiwan',town:null,zoom:null,topology:null,towns:null,townResults:null,historical:null,turnout:null,zoomBehavior:null,drawToken:0};
const races=new Map();
const countyNames=new Map();
function turnoutRate(county,year){
  const p=state.turnout?.records?.find(x=>nameKey(x.county)===nameKey(county));
  const y=p?.years?.[year];
  return y?.eligible>0 ?100*y.cast/y.eligible : null;
}
function record(county,year=state.year){
  return races.get(nameKey(county)+':'+year);
}
function candidatesSorted(race){
  return [...(race?.candidates||[])].sort((a,b)=>safeNumber(b.votes)-safeNumber(a.votes));
}
function winner(race){return candidatesSorted(race)[0]||null;}
function townRecord(name){
  const data=state.townResults?.counties||{};
  const key=Object.keys(data).find(x=>nameKey(x)===nameKey(state.county));
  const rows=key?data[key]?.local_2022||{}:{};
  return Object.entries(rows).find(([k])=>nameKey(k)===nameKey(name))?.[1]||null;
}
const labelColors = color => {const n=el('span','legend-swatch');n.style.background=color;return n;};
function updateLegend(){
  const root=$('#mapLegend');
  root.replaceChildren();
  if(state.metric==='turnout'){
    for(const [value,color] of [['50%', '#d5e4df'],['60%','#8ab9c4'],['70%','#347b9d'],['80%','#1b496b']]){
      const part=el('span','legend-item');
      part.append(labelColors(color),document.createTextNode(value));root.append(part);
    }
    root.append(el('span','legend-note','歷史實際投票率'));
  }else{
    for(const [partyId,label] of [['KMT','國民黨'],['DPP','民進黨'],['TPP','民眾黨'],['IND','無黨籍'],['OTHER','其他政黨']]){
      const part=el('span','legend-item');part.append(labelColors(PALETTE[partyId]),document.createTextNode(label));root.append(part);
    }
    root.append(el('span','legend-note',state.scope==='town'?'2022 各區領先政黨':'縣市長當選政黨'));
  }
}
function turnoutColor(value){
  if(value===null)return '#d9e4e8';
  return d3.scaleLinear().domain([45,58,70,83]).range(['#d5e4df','#8ab9c4','#347b9d','#1b496b']).clamp(true)(value);
}
function mapFill(feature){
  if(state.scope==='town'){
    const r=townRecord(feature.properties.name);
    if(!r)return '#ccd8dd';
    return PALETTE[r.winner]||PALETTE.OTHER;
  }
  const c=feature.properties.name;
  if(state.metric==='turnout')return turnoutColor(turnoutRate(c,state.year));
  return PALETTE[party(winner(record(c)))]||'#cbd8dd';
}
function mapTitle(feature){
  const name=feature.properties.name;
  if(state.scope==='town'){
    const r=townRecord(name);
    return r ? name+' · 2022 '+(PARTY_NAME[r.winner]||'其他')+'領先 · 差距 '+pct(r.margin):name+' · 未匹配2022年歷史分區資料';
  }
  const r=record(name);
  const w=winner(r);
  return state.metric==='turnout'
    ?name+' · '+state.year+'投票率 '+(turnoutRate(name,state.year)===null?'無此項資料':pct(turnoutRate(name,state.year)))
    :name+' · '+state.year+' '+(w?.name||'無資料')+' '+pct(w?.share_pct);
}
function status(message){$('#mapState').textContent=message;}
function showTooltip(event,feature){
  const t=$('#mapTooltip'),box=$('#mapSurface').getBoundingClientRect();
  const x=Math.max(5,Math.min(box.width-260,event.clientX-box.left+12));
  const y=Math.max(6,Math.min(box.height-55,event.clientY-box.top+10));
  t.textContent=mapTitle(feature);t.style.left=x+'px';t.style.top=y+'px';t.hidden=false;
}
function clearTooltip(){$('#mapTooltip').hidden=true;}
function makeSelection(select,values){
  select.replaceChildren();
  select.append(el('option',null,'選擇縣市'));
  select.firstChild.value='';
  for(const name of values){
    const o=el('option',null,name);o.value=name;select.append(o);
  }
}
function updateControls(){
  for(const b of document.querySelectorAll('[data-year]'))b.setAttribute('aria-pressed',String(Number(b.dataset.year)===state.year));
  for(const b of document.querySelectorAll('[data-metric]'))b.setAttribute('aria-pressed',String(b.dataset.metric===state.metric));
  $('#countySelect').value=state.county||'';
  $('#backTaiwan').hidden=state.scope!=='town';
  $('#mapScope').textContent=state.scope==='town'?state.county+' · 2022 TOWNSHIP RESULTS':'TAIWAN · 22 COUNTIES';
  const hint=state.scope==='town'?'鄉鎮市區歷史結果':'點選縣市查看歷屆計票';
  status(state.year+'年 · '+(state.metric==='turnout'?'歷史投票率':hint));
}
function renderProfile(){
  const r=state.county?record(state.county):null;
  $('#resultYear').textContent=state.year+' / LOCAL EXECUTIVE · HISTORICAL';
  $('#inspectorTitle').textContent=state.county||'選取一個縣市';
  const hint=$('#profileHint'),summary=$('#profileSummary'),list=$('#candidateList'),townPane=$('#townPane');
  summary.replaceChildren();list.replaceChildren();townPane.hidden=true;
  if(!r){hint.textContent='點選地圖上的縣市，查看該次歷史選舉之候選人得票與投票率。';return;}
  const ranked=candidatesSorted(r),w=ranked[0],second=ranked[1];
  hint.textContent=(r.source_note||'研究專案歷史選舉資料')+' · 已發生的選舉結果，不是2026預測';
  const stats=[
    ['當選人',w?.name||'無資料',''],
    ['當選得票率',pct(w?.share_pct),''],
    ['領先幅度',second?pct(safeNumber(w.share_pct)-safeNumber(second.share_pct)):'—',''],
    ['投票率',pct(r.turnout_pct),'']
  ];
  for(const [caption,value,unit] of stats){
    const box=el('div','profile-stat');
    box.append(el('span',null,caption));
    const strong=el('strong',null,value);if(unit)strong.append(el('small',null,unit));
    box.append(strong);summary.append(box);
  }
  for(const item of ranked){
    const row=el('div','candidate-item'),head=el('div','candidate-head'),group=party(item),share=safeNumber(item.share_pct);
    const dot=el('span','candidate-dot');dot.style.background=PALETTE[group];
    head.append(dot,el('span','candidate-name',item.name+(item.winner?' · 當選':'')),el('span','candidate-party',item.party_name||PARTY_NAME[group]),el('span','candidate-share',pct(share)));
    const bar=el('div','candidate-track'),value=el('span');value.style.width=Math.min(100,Math.max(0,share))+'%';value.style.background=PALETTE[group];bar.append(value);
    row.append(head,bar,el('span','candidate-votes','得票 '+numeric(item.votes)+' 票'));
    list.append(row);
  }
  if(state.year===2022){
    townPane.hidden=false;
    $('#townDescription').textContent='此為2022年已發生的各鄉鎮市區選舉結果，不代表2026年選情。點選區域可在地圖中定位。';
    const container=$('#townList');container.replaceChildren();
    const source=state.townResults?.counties||{};
    const key=Object.keys(source).find(n=>nameKey(n)===nameKey(state.county));
    for(const [town,result] of Object.entries(key?source[key]?.local_2022||{}:{}).sort((a,b)=>a[0].localeCompare(b[0],'zh-Hant'))){
      const b=el('button',null,town),chip=el('span',null,(PARTY_NAME[result.winner]||result.winner)+' '+pct(result.margin));
      b.type='button';b.setAttribute('aria-pressed',String(town===state.town));b.append(chip);
      b.addEventListener('click',async()=>{
        state.town=town;
        if(state.metric!=='winner'){state.metric='winner';updateControls();}
        await enterCounty(state.county);
        renderProfile();
        drawMap();
      });
      container.append(b);
    }
  }
}
function getCountyFeatures(){
  return topojson.feature(state.topology,state.topology.objects.map).features;
}
function getTownFeatures(){
  return state.towns?topojson.feature(state.towns,state.towns.objects.map).features:[];
}
function drawMap(){
  clearTooltip();
  const features=state.scope==='town'&&state.towns?getTownFeatures():getCountyFeatures();
  if(!features.length){status('無可用的歷史地理資料');return;}
  const svg=d3.select('#atlasMap');
  svg.selectAll('*').remove();
  const layer=svg.append('g').attr('class','map-geo-layer');
  const collection={type:'FeatureCollection',features};
  const projection=d3.geoMercator().fitExtent([[32,72],[868,664]],collection);
  const path=d3.geoPath(projection);
  const entries=layer.selectAll('path.map-county').data(features).join('path')
    .attr('class','map-county').attr('d',path).attr('fill',mapFill)
    .attr('tabindex','0').attr('role','button')
    .attr('aria-label',f=>mapTitle(f))
    .classed('is-selected',f=>(state.scope==='town'?nameKey(f.properties.name)===nameKey(state.town):nameKey(f.properties.name)===nameKey(state.county)));
  entries.append('title').text(f=>mapTitle(f));
  entries.on('mouseenter',function(event,f){showTooltip(event,f)})
    .on('mousemove',function(event,f){showTooltip(event,f)})
    .on('mouseleave',clearTooltip)
    .on('focus',function(event,f){$('#mapState').textContent=mapTitle(f)})
    .on('click',async function(event,f){
      if(state.scope==='town'){state.town=f.properties.name;renderProfile();drawMap();return;}
      await selectCounty(f.properties.name,true);
    })
    .on('keydown',function(event,f){if(event.key==='Enter'||event.key===' '){event.preventDefault();this.dispatchEvent(new MouseEvent('click',{bubbles:true}))}});
  if(features.length<=45){
    layer.selectAll('text.map-label').data(features).join('text').attr('class','map-label')
      .attr('text-anchor','middle')
      .attr('transform',f=>'translate('+path.centroid(f).map(x=>Math.round(x)).join(',')+')')
      .style('font-size',state.scope==='town'?'10px':'12px')
      .text(f=>f.properties.name);
  }
  const zoom=d3.zoom().scaleExtent([.76,14]).on('zoom',event=>layer.attr('transform',event.transform));
  svg.call(zoom).on('dblclick.zoom',null);
  state.zoom=zoom;
  svg.call(zoom.transform,d3.zoomIdentity);
  updateLegend();updateControls();
}
async function enterCounty(county){
  if(state.year!==2022||state.metric!=='winner'){
    state.scope='taiwan';state.towns=null;state.town=null;return;
  }
  const all=getCountyFeatures();
  const target=all.find(f=>nameKey(f.properties.name)===nameKey(county));
  if(!target){state.scope='taiwan';return;}
  const code=target.properties.id;
  const key=String(code||'');
  // Fixed numeric county IDs come exclusively from the checked-in GeoJSON,
  // not user input or dynamic URL fragments.
  if(!/^\d{5}$/.test(key)){state.scope='taiwan';return;}
  const token=++state.drawToken;
  status('載入 '+county+' 2022 鄉鎮市區歷史地理...');
  try{
    const response=await fetch('vendor/towns/towns-'+key+'.json');
    if(!response.ok)throw Error('district geometry unavailable');
    const topo=await response.json();
    if(token!==state.drawToken)return;
    if(topo.type!=='Topology'||!topo.objects?.map||topo.objects.map.geometries.length<1)throw Error('invalid district geometry');
    state.towns=topo;state.scope='town';
  }catch{
    if(token!==state.drawToken)return;
    state.scope='taiwan';state.towns=null;state.town=null;
    status('當前縣市鄉鎮圖層無法載入，仍可查看歷史縣市資料');
  }
}
async function selectCounty(county,drill){
  const normalized=nameKey(county);
  const known=countyNames.get(normalized);
  if(!known)return;
  state.county=known;
  state.town=null;state.drawToken++;
  state.scope='taiwan';state.towns=null;
  if(drill)await enterCounty(known);
  drawMap();renderProfile();
}
function setYear(year){
  if(!YEARS.includes(year))return;
  state.year=year;state.drawToken++;state.towns=null;state.scope='taiwan';state.town=null;
  drawMap();renderProfile();
}
function setMetric(metric){
  if(!['winner','turnout'].includes(metric))return;
  state.metric=metric;state.drawToken++;state.towns=null;state.scope='taiwan';state.town=null;
  drawMap();renderProfile();
}
function wire(){
  document.querySelectorAll('[data-year]').forEach(b=>b.addEventListener('click',()=>setYear(Number(b.dataset.year))));
  document.querySelectorAll('[data-metric]').forEach(b=>b.addEventListener('click',()=>setMetric(b.dataset.metric)));
  $('#countySelect').addEventListener('change',e=>{if(e.target.value)selectCounty(e.target.value,true);else{state.county=null;state.scope='taiwan';state.town=null;state.towns=null;state.drawToken++;drawMap();renderProfile();}});
  $('#backTaiwan').addEventListener('click',()=>{state.scope='taiwan';state.towns=null;state.town=null;state.drawToken++;drawMap();renderProfile()});
  $('#zoomIn').addEventListener('click',()=>d3.select('#atlasMap').transition().duration(160).call(state.zoom.scaleBy,1.42));
  $('#zoomOut').addEventListener('click',()=>d3.select('#atlasMap').transition().duration(160).call(state.zoom.scaleBy,1/1.42));
  $('#resetMap').addEventListener('click',()=>d3.select('#atlasMap').transition().duration(160).call(state.zoom.transform,d3.zoomIdentity));
}
async function load(){
  try {
    if(!window.d3||!window.topojson)throw Error('GIS libraries are unavailable');
    const urls=['archive-results.json','archive-turnout.json','vendor/counties.json','vendor/town-results.json'];
    const responses=await Promise.all(urls.map(path=>fetch(path,{cache:'no-store'})));
    if(responses.some(r=>!r.ok))throw Error('historical datasets failed to load');
    const [history,turnout,topology,townResults]=await Promise.all(responses.map(r=>r.json()));
    if(history.kind!=='historical_elections_only_no_current_opinion_polls'
       ||history.races.length!==66
       ||topology.type!=='Topology'
       ||topology.objects?.map?.geometries?.length!==22
       ||turnout.records?.length!==22)throw Error('source archive failed integrity checks');
    for(const race of history.races){
      if(!YEARS.includes(race.year)||!race.county||!Array.isArray(race.candidates))throw Error('malformed historical race');
      const key=nameKey(race.county)+':'+race.year;
      if(races.has(key))throw Error('duplicate historical race');
      races.set(key,race);
      countyNames.set(nameKey(race.county),race.county);
    }
    if(races.size!==66||countyNames.size!==22)throw Error('historical map incomplete');
    state.historical=history;state.turnout=turnout;state.topology=topology;state.townResults=townResults;
    makeSelection($('#countySelect'),[...countyNames.values()].sort((a,b)=>a.localeCompare(b,'zh-Hant')));
    wire();drawMap();renderProfile();
  } catch (error) {
    status('地圖暫時無法載入：'+error.message);
    $('#mapScope').textContent='歷史地圖資源暫時不可用';
    $('#inspectorTitle').textContent='資料載入失敗';
    $('#profileHint').textContent='此公開頁沒有2026民調或預測資料。請檢查網路後重新整理頁面。';
  }
}
load();
