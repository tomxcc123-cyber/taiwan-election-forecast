import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  ScaleControl,
  setWorkerUrl,
} from '../vendor/maplibre/maplibre-gl.mjs';
import {COLORS, group} from '../candidate-engine.mjs';

setWorkerUrl(new URL('../vendor/maplibre/maplibre-gl-worker.mjs', import.meta.url).href);

const normalize = value => String(value || '').replaceAll('臺', '台');
const OFFSHORE = ['金門縣', '連江縣', '澎湖縣'];
const NLSC = 'https://wmts.nlsc.gov.tw/wmts';
const TOWN_LEVEL_ZOOM = 6.6;
let activeMap = null;
let activeMarkers = [];
let activeFeatures = [];
let activeSelected = '';
let activeFocused = false;

function nlscSource(layer, maxzoom = 19) {
  return {
    type: 'raster',
    tiles: [`${NLSC}/${layer}/default/GoogleMapsCompatible/{z}/{y}/{x}`],
    tileSize: 256,
    minzoom: 4,
    maxzoom,
    attribution: '內政部國土測繪中心',
  };
}

function mapStyle() {
  return {
    version: 8,
    name: 'Taiwan Election GIS',
    sources: {},
    layers: [{id: 'water', type: 'background', paint: {'background-color': '#dceff3'}}],
  };
}

function addOfficialBasemap(map, basemap) {
  if (basemap === 'simple') return;
  map.addSource('nlsc-terrain', nlscSource('EMAP5'));
  map.addSource('nlsc-administrative', nlscSource('EMAP01'));
  map.addSource('nlsc-hillshade', nlscSource('MOI_HILLSHADE'));
  map.addSource('nlsc-town', nlscSource('TOWN'));
  map.addSource('nlsc-city', nlscSource('CITY'));
  map.addLayer({
    id: 'nlsc-terrain-base',
    type: 'raster',
    source: 'nlsc-terrain',
    layout: {visibility: basemap === 'terrain' ? 'visible' : 'none'},
    paint: {'raster-opacity': 0.96, 'raster-saturation': -0.18, 'raster-contrast': -0.08},
  });
  map.addLayer({
    id: 'nlsc-administrative-base',
    type: 'raster',
    source: 'nlsc-administrative',
    layout: {visibility: basemap === 'administrative' ? 'visible' : 'none'},
    paint: {'raster-opacity': 0.92, 'raster-brightness-max': 0.93},
  });
  map.addLayer({
    id: 'nlsc-relief',
    type: 'raster',
    source: 'nlsc-hillshade',
    layout: {visibility: basemap === 'terrain' ? 'visible' : 'none'},
    paint: {'raster-opacity': 0.17, 'raster-contrast': 0.18},
  });
}

function majorShare(race) {
  const best = key => [...race.candidates]
    .filter(candidate => group(candidate) === key)
    .sort((a, b) => b.mean - a.mean)[0]?.mean || 0;
  const dpp = best('DPP');
  const kmt = best('KMT');
  return dpp > 0 && kmt > 0 ? dpp / (dpp + kmt) : null;
}

function mapMetrics(race, rawRace, baseRace, delta = 0) {
  const leader = race.candidates[race.winner];
  const leaderGroup = group(leader);
  const probability = Number(leader.probability || 0);
  const dpp2 = Number(rawRace?.v5_structural?.r4_dpp_two_party
    ?? rawRace?.v4_structural?.r4_dpp_two_party
    ?? 0.5);
  const baselineMargin = (dpp2 * 2 - 1) * 100;
  const share = majorShare(race);
  const forecastMargin = share === null ? null : (share * 2 - 1) * 100;
  const swing = forecastMargin === null ? null : forecastMargin - baselineMargin;
  const baselineGroup = baselineMargin >= 0 ? 'DPP' : 'KMT';
  const swingGroup = swing === null ? 'IND' : swing >= 0 ? 'DPP' : 'KMT';
  const baseLeader = baseRace?.candidates?.[baseRace.winner];
  return {
    leader,
    leaderGroup,
    probability,
    baselineMargin,
    baselineGroup,
    forecastMargin,
    swing,
    swingGroup,
    uncertainty: 1 - probability,
    flow: delta,
    baseLeader,
  };
}

function fillFor(metrics, mode) {
  if (mode === 'baseline') return COLORS[metrics.baselineGroup];
  if (mode === 'swing') return metrics.swing === null ? '#9aa5ae' : COLORS[metrics.swingGroup];
  if (mode === 'uncertainty') return '#c98232';
  if (mode === 'flow') return metrics.flow >= 0 ? COLORS.KMT : COLORS.DPP;
  return COLORS[metrics.leaderGroup] || COLORS.IND;
}

function opacityFor(metrics, mode) {
  if (mode === 'probability') return 0.32 + Math.max(0, metrics.probability - 0.45) * 1.18;
  if (mode === 'baseline') return 0.34 + Math.min(0.48, Math.abs(metrics.baselineMargin) / 34);
  if (mode === 'swing') return metrics.swing === null ? 0.22 : 0.28 + Math.min(0.58, Math.abs(metrics.swing) / 16);
  if (mode === 'uncertainty') return 0.24 + Math.min(0.62, metrics.uncertainty * 0.9);
  if (mode === 'flow') return 0.26 + Math.min(0.62, Math.abs(metrics.flow) / 8);
  return metrics.leader ? 0.7 : 0.25;
}

function valueFor(metrics, mode) {
  if (mode === 'probability') return `${Math.round(metrics.probability * 100)}%`;
  if (mode === 'baseline') return `${metrics.baselineMargin >= 0 ? 'DPP' : 'KMT'} +${Math.abs(metrics.baselineMargin).toFixed(1)}`;
  if (mode === 'swing') return metrics.swing === null ? '主要政黨配對不完整' : `${metrics.swing >= 0 ? 'DPP' : 'KMT'} ${metrics.swing >= 0 ? '+' : '−'}${Math.abs(metrics.swing).toFixed(1)}`;
  if (mode === 'uncertainty') return `${Math.round(metrics.uncertainty * 100)}% 不確定`;
  if (mode === 'flow') return `${metrics.flow >= 0 ? '+' : '−'}${Math.abs(metrics.flow).toFixed(1)} pp`;
  return `${metrics.leader?.name || '無資料'} 領先`;
}

function toFeatureCollection(topology, results, rawCounties, baselineResults, mode, deltas) {
  const collection = window.topojson.feature(topology, topology.objects.map);
  const resultByName = new Map(results.map(race => [normalize(race.name), race]));
  const rawByName = new Map(rawCounties.map(race => [normalize(race.name), race]));
  const baseByName = new Map(baselineResults.map(race => [normalize(race.name), race]));
  const features = collection.features.map((feature, index) => {
    const name = normalize(feature.properties?.name);
    const race = resultByName.get(name);
    if (!race) return {...feature, id: feature.properties?.id || index};
    const metrics = mapMetrics(race, rawByName.get(name), baseByName.get(name), Number(deltas?.[name] || 0));
    return {
      ...feature,
      id: feature.properties?.id || index,
      properties: {
        ...feature.properties,
        name,
        fill: fillFor(metrics, mode),
        opacity: Math.min(0.92, opacityFor(metrics, mode)),
        party: metrics.leaderGroup,
        leader: metrics.leader?.name || '無資料',
        value: valueFor(metrics, mode),
        evidence: race.quality?.evidence?.grade || '—',
      },
    };
  });
  return {type: 'FeatureCollection', features};
}

function coordinates(geometry) {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return geometry.coordinates.flat();
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat(2);
  return [];
}

function boundsFor(feature) {
  const points = coordinates(feature.geometry);
  return points.reduce((bounds, point) => {
    const [lng, lat] = point;
    if (!bounds) return [[lng, lat], [lng, lat]];
    bounds[0][0] = Math.min(bounds[0][0], lng);
    bounds[0][1] = Math.min(bounds[0][1], lat);
    bounds[1][0] = Math.max(bounds[1][0], lng);
    bounds[1][1] = Math.max(bounds[1][1], lat);
    return bounds;
  }, null);
}

function tooltipNode(properties) {
  const node = document.createElement('div');
  node.className = 'gis-tooltip';
  const title = document.createElement('strong');
  title.textContent = properties.name;
  const value = document.createElement('span');
  value.textContent = properties.value;
  const meta = document.createElement('small');
  meta.textContent = `Evidence ${properties.evidence} · 點擊進入地區檔案`;
  node.append(title, value, meta);
  return node;
}

function clearMap() {
  activeMarkers.forEach(marker => marker.remove());
  activeMarkers = [];
  if (activeMap) activeMap.remove();
  activeMap = null;
}

function renderOffshoreInsets(features, onSelect) {
  const host = document.getElementById('gisInsets');
  if (!host || !window.d3?.geoMercator || !window.d3?.geoPath) return;
  host.replaceChildren();
  for (const name of OFFSHORE) {
    const feature = features.find(item => item.properties.name === name);
    if (!feature) continue;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `gis-inset${name === activeSelected ? ' is-selected' : ''}`;
    button.dataset.county = name;
    button.setAttribute('aria-label', `定位並查看${name}預測`);
    const label = document.createElement('span');
    label.textContent = name;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 112 58');
    svg.setAttribute('aria-hidden', 'true');
    const projection = window.d3.geoMercator().fitExtent([[8, 8], [104, 52]], feature);
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', window.d3.geoPath(projection)(feature));
    svg.append(path);
    button.append(label, svg);
    button.addEventListener('click', event => {
      event.stopPropagation();
      focusElectionCounty(name);
      onSelect(name);
    });
    host.append(button);
  }
}

function syncGeographicLevel(map) {
  const detailed = map.getZoom() >= TOWN_LEVEL_ZOOM;
  const indicator = document.getElementById('gisLevelIndicator');
  if (indicator) {
    const strong = indicator.querySelector('strong');
    const small = indicator.querySelector('small');
    if (strong) strong.textContent = detailed ? '鄉鎮市區' : '縣市';
    if (small) small.textContent = detailed ? '官方鄉鎮界已顯示' : '放大顯示鄉鎮市區界';
    indicator.classList.toggle('is-detailed', detailed);
  }
  activeMarkers.forEach(marker => {
    const button = marker.getElement();
    button.classList.toggle('is-scale-hidden', detailed && !button.classList.contains('is-selected'));
  });
}

function addLabels(map, features, onSelect) {
  if (!window.d3?.geoCentroid) return;
  for (const feature of features) {
    const name = feature.properties.name;
    const element = document.createElement('button');
    element.type = 'button';
    element.className = `gis-map-label county-path${name === activeSelected ? ' is-selected' : ''}`;
    element.dataset.county = name;
    element.textContent = name.replace(/[縣市]$/, '');
    element.setAttribute('aria-label', `查看${name}預測`);
    element.addEventListener('click', event => {
      event.stopPropagation();
      focusElectionCounty(name);
      onSelect(name);
    });
    const marker = new Marker({element, anchor: 'center'})
      .setLngLat(window.d3.geoCentroid(feature))
      .addTo(map);
    activeMarkers.push(marker);
  }
}

function selectFilter(name) {
  if (!activeMap?.getLayer('county-selected')) return;
  activeMap.setFilter('county-selected', ['==', ['get', 'name'], name || '']);
  activeMarkers.forEach(marker => {
    const button = marker.getElement();
    button.classList.toggle('is-selected', button.getAttribute('aria-label') === `查看${name}預測`);
  });
  document.querySelectorAll('.gis-inset').forEach(button => {
    button.classList.toggle('is-selected', button.dataset.county === name);
  });
  if (activeMap) syncGeographicLevel(activeMap);
}

export function focusElectionCounty(name, animate = true) {
  activeSelected = normalize(name);
  activeFocused = true;
  selectFilter(activeSelected);
  const feature = activeFeatures.find(item => item.properties.name === activeSelected);
  const bounds = feature && boundsFor(feature);
  if (activeMap && bounds) activeMap.fitBounds(bounds, {
    padding: {top: 86, right: 72, bottom: 86, left: 72},
    maxZoom: 8.2,
    duration: animate && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 850 : 0,
  });
}

export function resetElectionMap() {
  activeFocused = false;
  const compact = matchMedia('(max-width: 980px)').matches;
  activeMap?.fitBounds(compact ? [[119.65, 21.65], [122.35, 25.55]] : [[118.0, 21.55], [122.25, 26.3]], {
    padding: compact ? 24 : 38,
    duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 700,
  });
}

export function resizeElectionMap() {
  activeMap?.resize();
  if (activeFocused) focusElectionCounty(activeSelected, false);
  else resetElectionMap();
}

export function drawElectionMap(element, topology, results, rawCounties, baselineResults, selected, mode, basemap, onSelect, deltas = {}) {
  clearMap();
  activeSelected = normalize(selected);
  const geojson = toFeatureCollection(topology, results, rawCounties, baselineResults, mode, deltas);
  activeFeatures = geojson.features;
  const map = activeMap = new MapLibreMap({
    container: element,
    style: mapStyle(),
    center: [120.85, 23.65],
    zoom: 5.55,
    minZoom: 4.4,
    maxZoom: 10,
    attributionControl: false,
    dragRotate: false,
    pitchWithRotate: false,
    cooperativeGestures: false,
  });
  map.addControl(new NavigationControl({showCompass: false, visualizePitch: false}), 'top-right');
  map.addControl(new ScaleControl({maxWidth: 110, unit: 'metric'}), 'bottom-left');
  map.on('error', () => {});
  map.once('load', () => {
    addOfficialBasemap(map, basemap);
    map.addSource('counties', {type: 'geojson', data: geojson, promoteId: 'id'});
    map.addLayer({
      id: 'county-shadow',
      type: 'line',
      source: 'counties',
      paint: {'line-color': '#18364b', 'line-width': 5, 'line-opacity': 0.09, 'line-blur': 4},
    });
    map.addLayer({
      id: 'county-fill',
      type: 'fill',
      source: 'counties',
      paint: {
        'fill-color': ['get', 'fill'],
        'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], basemap === 'simple' ? 0.96 : 0.82, ['*', ['get', 'opacity'], basemap === 'simple' ? 1 : 0.72]],
      },
    });
    map.addLayer({
      id: 'county-boundary',
      type: 'line',
      source: 'counties',
      paint: {'line-color': '#ffffff', 'line-width': 1.25, 'line-opacity': 0.92},
    });
    map.addLayer({
      id: 'county-selected',
      type: 'line',
      source: 'counties',
      filter: ['==', ['get', 'name'], activeSelected],
      paint: {'line-color': '#152c40', 'line-width': 4, 'line-opacity': 1},
    });
    if (basemap !== 'simple') {
      map.addLayer({
        id: 'official-town-boundaries',
        type: 'raster',
        source: 'nlsc-town',
        minzoom: TOWN_LEVEL_ZOOM,
        paint: {'raster-opacity': 0.64, 'raster-fade-duration': 140},
      });
      map.addLayer({
        id: 'official-county-boundaries',
        type: 'raster',
        source: 'nlsc-city',
        paint: {'raster-opacity': 0.68, 'raster-fade-duration': 140},
      });
    }
    addLabels(map, activeFeatures, onSelect);
    renderOffshoreInsets(activeFeatures, onSelect);
    resetElectionMap();
    syncGeographicLevel(map);
  });
  map.on('zoom', () => syncGeographicLevel(map));
  let hoveredId = null;
  const popup = new Popup({closeButton: false, closeOnClick: false, offset: 10, maxWidth: '240px'});
  map.on('mousemove', 'county-fill', event => {
    const feature = event.features?.[0];
    if (!feature) return;
    if (hoveredId !== null) map.setFeatureState({source: 'counties', id: hoveredId}, {hover: false});
    hoveredId = feature.id;
    map.setFeatureState({source: 'counties', id: hoveredId}, {hover: true});
    map.getCanvas().style.cursor = 'pointer';
    popup.setLngLat(event.lngLat).setDOMContent(tooltipNode(feature.properties)).addTo(map);
  });
  map.on('mouseleave', 'county-fill', () => {
    if (hoveredId !== null) map.setFeatureState({source: 'counties', id: hoveredId}, {hover: false});
    hoveredId = null;
    map.getCanvas().style.cursor = '';
    popup.remove();
  });
  map.on('click', 'county-fill', event => {
    const name = normalize(event.features?.[0]?.properties?.name);
    if (!name) return;
    focusElectionCounty(name);
    onSelect(name);
  });
  return map;
}
