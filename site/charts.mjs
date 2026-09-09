import {COLORS, LABELS} from './forecast.mjs';
export const escape = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
export const pct = v => (v * 100).toFixed(0) + '%';
export const fixed = v => Number(v).toFixed(1);
export function intervalRows(c) {
  return c.shares.map((s,i)=>`<div class="interval-row"><span><i class="dot" style="background:${COLORS[i]}"></i>${LABELS[i].replace('情境','').replace('整合','')}</span><strong>${fixed(s.mean)}%</strong><svg viewBox="0 0 230 44" role="img" aria-label="${LABELS[i]}，90%推估區間${fixed(s.p05)}至${fixed(s.p95)}%"><line x1="12" y1="17" x2="218" y2="17" stroke="#e2e6eb"/><line x1="${12+s.p05*2.06}" y1="17" x2="${12+s.p95*2.06}" y2="17" stroke="${COLORS[i]}" stroke-width="3"/><circle cx="${12+s.mean*2.06}" cy="17" r="4" fill="${COLORS[i]}"/><text x="12" y="39" font-size="11" fill="#616b77">${fixed(s.p05)}%</text><text x="218" y="39" text-anchor="end" font-size="11" fill="#616b77">${fixed(s.p95)}%</text></svg></div>`).join('');
}
export function histogram(summary, party=0) {
  const h=summary[party].histogram, max=Math.max(...h,.01), width=440, base=145;
  return `<svg class="chart" viewBox="0 0 440 184" role="img" aria-label="${LABELS[party]}的0至22席機率分布"><text x="8" y="12" fill="#616b77" font-size="11">${pct(max)}</text><line x1="28" y1="${base}" x2="435" y2="${base}" stroke="#bfc7d1"/>${h.map((v,i)=>`<rect x="${30+i*17.3}" y="${base-v/max*118}" width="13" height="${v/max*118}" fill="${COLORS[party]}" opacity="${i>=12?1:.48}"><title>${i}席：${(v*100).toFixed(1)}%</title></rect>${i%2===0?`<text x="${36+i*17.3}" y="164" text-anchor="middle" font-size="10" fill="#616b77">${i}</text>`:''}`).join('')}<line x1="235" y1="22" x2="235" y2="148" stroke="#35404e" stroke-dasharray="3 3"/><text x="242" y="24" font-size="11" fill="#35404e">12席門檻</text><text x="425" y="181" font-size="10" fill="#616b77">席次</text></svg>`;
}
export function rating(c) {
  if(c.winner===2) return 7;
  const p=c.probability[c.winner];
  if(p<.6) return 3;
  const level=p>=.9?0:p>=.75?1:2;
  return c.winner===0?level:6-level;
}
export const RATINGS=['藍白強勢','藍白領先','藍白傾向','競爭激烈','綠營傾向','綠營領先','綠營強勢','其他領先'];
export const RATING_COLORS=['#2864c8','#6c94d8','#c3d4f0','#d0d5dd','#bde0d4','#68b097','#14805e','#737b89'];
export function drawMap(element, geo, results, selected, mode, onSelect, deltas) {
  const d3=window.d3, topojson=window.topojson;
  const svg=d3.select(element).attr('viewBox','0 0 640 490');svg.selectAll('*').remove();
  const riskPattern=svg.append('defs').append('pattern').attr('id','evidence-risk').attr('width',8).attr('height',8).attr('patternUnits','userSpaceOnUse');riskPattern.append('rect').attr('width',8).attr('height',8).attr('fill','#edf0f4');riskPattern.append('path').attr('d','M-2,2L2,-2M0,8L8,0M6,10L10,6').attr('stroke','#8993a2').attr('stroke-width',2);
  const features=topojson.feature(geo,geo.objects.map).features;
  const name=f=>f.properties.name.replaceAll('臺','台');
  const offshore=['金門縣','澎湖縣','連江縣'];
  const mainland=features.filter(f=>!offshore.includes(name(f)));
  const projection=d3.geoMercator().fitExtent([[120,12],[565,472]],{type:'FeatureCollection',features:mainland});
  const add=(features,projection)=>{
    const path=d3.geoPath(projection);
    const paths=svg.append('g').selectAll('path').data(features).join('path').attr('d',path).attr('class',f=>'county-path'+(name(f)===selected?' selected':''))
      .attr('data-county',name).attr('tabindex',0).attr('role','button')
      .attr('aria-label',f=>{const c=results.find(c=>c.name===name(f));return c.quality?.evidence?.grade==='D'?`${name(f)}，已知模型缺項，暫不評級`:`${name(f)}，${c.leaderLabel||LABELS[c.winner]}模型傾向，勝率${pct(c.leaderProbability??c.probability[c.winner])}`;})
      .attr('aria-pressed',f=>String(name(f)===selected))
      .attr('fill',f=>{const c=results.find(c=>c.name===name(f));if(mode==='flow'){const v=deltas?.[c.name]||0;return d3.interpolateRgb('#edf0f4',v>=0?COLORS[0]:COLORS[1])(Math.min(1,Math.abs(v)/12));}if(c.quality?.evidence?.grade==='D')return 'url(#evidence-risk)';if(c.leaderLabel)return mode==='probability'?d3.interpolateRgb('#edf0f4',c.leaderColor)(.2+.8*c.leaderProbability):c.leaderColor;return mode==='probability'?d3.interpolateRgb('#edf0f4',COLORS[c.winner])(.2+.8*c.probability[c.winner]):RATING_COLORS[rating(c)];})
      .on('click',(e,f)=>onSelect(name(f))).on('keydown',(e,f)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(name(f));}});
    paths.append('title').text(f=>{const c=results.find(c=>c.name===name(f));return c.quality?.evidence?`${name(f)} · ${c.quality.evidence.grade}級：${c.quality.evidence.reason}`:name(f);});return path;
  };
  const path=add(mainland,projection);
  const labels=['新北市','桃園市','苗栗縣','台中市','南投縣','雲林縣','嘉義縣','台南市','高雄市','屏東縣','宜蘭縣','花蓮縣','台東縣'];
  svg.append('g').selectAll('text').data(mainland.filter(f=>labels.includes(name(f)))).join('text').attr('x',f=>path.centroid(f)[0]).attr('y',f=>path.centroid(f)[1]).attr('text-anchor','middle').attr('class','map-label').text(name);
  offshore.forEach((n,i)=>{
    const f=features.filter(f=>name(f)===n), y=48+i*126;
    svg.append('rect').attr('x',12).attr('y',y).attr('width',104).attr('height',112).attr('rx',4).attr('fill','#fafbfc').attr('stroke','#dce1e7');
    svg.append('text').attr('x',22).attr('y',y+21).attr('class','island-label').text(n);
    // Remote islets can span hundreds of kilometres. Show the largest land polygon
    // in each inset, explicitly labelled as a main-island detail rather than a full boundary.
    const detail=f.map(feature=>{
      if(feature.geometry.type!=='MultiPolygon')return feature;
      const polygons=feature.geometry.coordinates.map(coordinates=>({type:'Polygon',coordinates}));
      const largest=polygons.sort((a,b)=>d3.geoArea(b)-d3.geoArea(a))[0];
      return {...feature,geometry:largest};
    });
    const pr=d3.geoMercator().fitExtent([[24,y+34],[104,y+94]],{type:'FeatureCollection',features:detail});add(detail,pr);
    svg.append('text').attr('x',22).attr('y',y+106).attr('class','inset-note').attr('font-size',9).attr('fill','#616b77').text('主島詳圖・非等比例');
  });
  // Dense northern cities get separate callouts instead of overlapping map labels.
  ['台北市','基隆市','新竹縣','新竹市','彰化縣','嘉義市'].forEach((n,i)=>{
    const f=mainland.find(f=>name(f)===n);if(!f)return;const [x,y]=path.centroid(f), tx=548, ty=28+i*30;
    svg.append('path').attr('d',`M${x},${y}L${tx-7},${ty-4}`).attr('fill','none').attr('stroke','#8993a2').attr('stroke-width',.7);
    svg.append('text').attr('x',tx).attr('y',ty).attr('text-anchor','start').attr('class','map-label callout').text(n);
  });
}
