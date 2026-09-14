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
const NLSC_API = 'https://api.nlsc.gov.tw/other/TownVillagePointQuery';
const MAPTERHORN_TILEJSON = 'https://tiles.mapterhorn.com/tilejson.json';
const TOWN_LEVEL_ZOOM = 7.4;
const VILLAGE_LEVEL_ZOOM = 10.4;
let activeMap = null;
let activeMarkers = [];
let activeLocationMarker = null;
let activeFeatures = [];
let activeSelected = '';
let activeFocused = false;
let activeGeography = null;
let activeOnGeography = null;
let activePerspective = '3d';

const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const cameraDuration = milliseconds => reduceMotion() ? 0 : milliseconds;
const cameraEase = t => 1 - Math.pow(1 - t, 4);
const perspectiveCamera = (zoom = activeMap?.getZoom() || 5.5) => activePerspective === '3d'
  ? {pitch: zoom >= VILLAGE_LEVEL_ZOOM ? 54 : zoom >= TOWN_LEVEL_ZOOM ? 50 : 46, bearing: -18}
  : {pitch: 0, bearing: 0};

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
  map.addSource('nlsc-imagery', nlscSource('PHOTO2'));
  map.addSource('nlsc-hillshade', nlscSource('MOI_HILLSHADE'));
  map.addSource('nlsc-town', nlscSource('TOWN'));
  map.addSource('nlsc-village', nlscSource('Village'));
  map.addSource('nlsc-city', nlscSource('CITY'));
  map.addLayer({
    id: 'nlsc-terrain-base',
    type: 'raster',
    source: 'nlsc-terrain',
    layout: {visibility: basemap === 'terrain' ? 'visible' : 'none'},
    paint: {'raster-opacity': 0, 'raster-opacity-transition': {duration: 260}, 'raster-saturation': -0.18, 'raster-contrast': -0.08},
  });
  map.addLayer({
    id: 'nlsc-administrative-base',
    type: 'raster',
    source: 'nlsc-administrative',
    layout: {visibility: basemap === 'administrative' ? 'visible' : 'none'},
    paint: {'raster-opacity': 0, 'raster-opacity-transition': {duration: 260}, 'raster-brightness-max': 0.93},
  });
  map.addLayer({
    id: 'nlsc-imagery-base',
    type: 'raster',
    source: 'nlsc-imagery',
    layout: {visibility: basemap === 'imagery' ? 'visible' : 'none'},
    paint: {'raster-opacity': 0, 'raster-opacity-transition': {duration: 260}, 'raster-saturation': -0.12, 'raster-contrast': -0.04},
  });
  map.addLayer({
    id: 'nlsc-relief',
    type: 'raster',
    source: 'nlsc-hillshade',
    maxzoom: 11.5,
    layout: {visibility: basemap === 'terrain' ? 'visible' : 'none'},
    paint: {'raster-opacity': 0, 'raster-opacity-transition': {duration: 520}, 'raster-contrast': 0.2, 'raster-saturation': -0.3},
  });
}

function addTerrainModel(map, element) {
  map.addSource('terrain-dem', {
    type: 'raster-dem',
    url: MAPTERHORN_TILEJSON,
    tileSize: 512,
    encoding: 'terrarium',
  });
  map.addSource('terrain-shade', {
    type: 'raster-dem',
    url: MAPTERHORN_TILEJSON,
    tileSize: 512,
    encoding: 'terrarium',
  });
  map.addLayer({
    id: 'terrain-ambient',
    type: 'hillshade',
    source: 'terrain-shade',
    maxzoom: 15,
    layout: {visibility: activePerspective === '3d' ? 'visible' : 'none'},
    paint: {
      'hillshade-illumination-anchor': 'map',
      'hillshade-illumination-direction': 318,
      'hillshade-exaggeration': 0.54,
      'hillshade-shadow-color': 'rgba(19, 48, 58, 0.46)',
      'hillshade-highlight-color': 'rgba(255, 248, 218, 0.34)',
      'hillshade-accent-color': 'rgba(67, 98, 86, 0.28)',
    },
  });
  element.dataset.terrainSource = 'MOI-2024-20m-DTM';
  element.dataset.terrainReady = 'false';
  const markReady = () => {
    if (map.isSourceLoaded('terrain-dem')) element.dataset.terrainReady = 'true';
  };
  map.on('sourcedata', markReady);
  markReady();
}

function syncTerrain(map = activeMap) {
  if (!map?.getSource('terrain-dem')) return;
  const enabled = activePerspective === '3d';
  map.setTerrain(enabled ? {source: 'terrain-dem', exaggeration: 1.38} : null);
  map.getContainer().dataset.terrainEnabled = String(enabled);
  if (map.getLayer('terrain-ambient')) {
    map.setLayoutProperty('terrain-ambient', 'visibility', enabled ? 'visible' : 'none');
  }
}

function revealLoadedOfficialLayers(map, element, basemap) {
  if (basemap === 'simple') {
    element.dataset.basemapReady = 'true';
    return;
  }
  const activeSource = basemap === 'terrain' ? 'nlsc-terrain' : basemap === 'imagery' ? 'nlsc-imagery' : 'nlsc-administrative';
  const baseOpacity = basemap === 'terrain' ? 0.96 : basemap === 'imagery' ? 0.88 : 0.92;
  const layers = [
    [activeSource, basemap === 'terrain' ? 'nlsc-terrain-base' : basemap === 'imagery' ? 'nlsc-imagery-base' : 'nlsc-administrative-base',
      ['interpolate', ['linear'], ['zoom'], 5.45, 0, 7.25, 0, 7.85, baseOpacity]],
    ...(basemap === 'terrain' ? [['nlsc-hillshade', 'nlsc-relief',
      ['interpolate', ['linear'], ['zoom'], 6.8, 0, 7.4, 0, 8, activePerspective === '3d' ? 0.16 : 0.09]]] : []),
  ];
  const reveal = () => {
    for (const [source, layer, opacity] of layers) {
      if (map.getLayer(layer) && map.isSourceLoaded(source)) map.setPaintProperty(layer, 'raster-opacity', opacity);
    }
    if (map.isSourceLoaded(activeSource)) element.dataset.basemapReady = 'true';
  };
  map.on('sourcedata', reveal);
  reveal();
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
        elevation: 150 + Math.round(metrics.probability * 950),
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
  activeLocationMarker?.remove();
  activeLocationMarker = null;
  if (activeMap) activeMap.remove();
  activeMap = null;
}

function xmlText(xml, tag) {
  return xml.querySelector(tag)?.textContent?.trim() || '';
}

async function lookupAdministrativePoint(lng, lat) {
  const response = await fetch(`${NLSC_API}/${lng.toFixed(6)}/${lat.toFixed(6)}/4326`);
  if (!response.ok) throw new Error('官方行政區定位暫時無法使用');
  const xml = new DOMParser().parseFromString(await response.text(), 'application/xml');
  if (xml.querySelector('parsererror')) throw new Error('官方行政區資料格式錯誤');
  const result = {
    county: normalize(xmlText(xml, 'ctyName')),
    countyCode: xmlText(xml, 'ctyCode'),
    town: xmlText(xml, 'townName'),
    townCode: xmlText(xml, 'townCode'),
    village: xmlText(xml, 'villageName'),
    villageCode: xmlText(xml, 'villageCode'),
    section: xmlText(xml, 'sectName'),
    lng,
    lat,
  };
  if (!result.county || !result.town) throw new Error('此位置沒有可用的行政區資料');
  return result;
}

function locationMarker(detail) {
  activeLocationMarker?.remove();
  const element = document.createElement('div');
  element.className = `gis-location-marker${detail.village ? ' is-village' : ''}`;
  element.setAttribute('aria-label', detail.village ? `${detail.village}定位點` : `${detail.town}定位點`);
  activeLocationMarker = new Marker({element, anchor: 'center'})
    .setLngLat([detail.lng, detail.lat])
    .addTo(activeMap);
}

function publishGeography(detail) {
  activeGeography = detail;
  if (detail) locationMarker(detail);
  else {
    activeLocationMarker?.remove();
    activeLocationMarker = null;
  }
  activeOnGeography?.(detail);
  if (activeMap) syncGeographicLevel(activeMap);
}

async function drillAtPoint(map, event) {
  const canvas = map.getCanvas();
  if (canvas.dataset.lookupBusy === 'true') return;
  canvas.dataset.lookupBusy = 'true';
  canvas.classList.add('is-locating');
  try {
    const found = await lookupAdministrativePoint(event.lngLat.lng, event.lngLat.lat);
    if (found.county !== activeSelected) {
      activeSelected = found.county;
      activeFocused = true;
      selectFilter(activeSelected);
    }
    const enterVillage = activeGeography?.town === found.town || map.getZoom() >= VILLAGE_LEVEL_ZOOM;
    const detail = enterVillage ? found : {...found, village: '', villageCode: ''};
    publishGeography(detail);
    map.flyTo({
      center: event.lngLat,
      zoom: enterVillage ? Math.max(map.getZoom(), 13.2) : Math.max(map.getZoom(), 10.7),
      ...perspectiveCamera(enterVillage ? 13.2 : 10.7),
      duration: cameraDuration(1050),
      curve: 1.24,
      essential: false,
    });
  } catch (error) {
    activeOnGeography?.({error: error.message});
  } finally {
    canvas.dataset.lookupBusy = 'false';
    canvas.classList.remove('is-locating');
  }
}

export async function drillElectionCoordinates(lng, lat) {
  if (!activeMap) throw new Error('地图尚未载入');
  await drillAtPoint(activeMap, {lngLat: {lng: Number(lng), lat: Number(lat)}});
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
  const zoom = map.getZoom();
  map.getContainer().dataset.mapZoom = zoom.toFixed(2);
  const detailed = zoom >= TOWN_LEVEL_ZOOM;
  const villageVisible = zoom >= VILLAGE_LEVEL_ZOOM;
  const level = activeGeography?.village ? '村里' : activeGeography?.town ? '鄉鎮市區' : detailed ? '鄉鎮市區' : '縣市';
  const indicator = document.getElementById('gisLevelIndicator');
  if (indicator) {
    const strong = indicator.querySelector('strong');
    const small = indicator.querySelector('small');
    if (strong) strong.textContent = level;
    if (small) small.textContent = activeGeography?.village
      ? '地理瀏覽層 · 非預測層'
      : activeGeography?.town
        ? '再點一次選取村里'
        : villageVisible
          ? '點擊地圖選取村里'
          : detailed
            ? '點擊地圖選取鄉鎮市區'
            : '點擊縣市後向下探索';
    indicator.classList.toggle('is-detailed', detailed);
    indicator.classList.toggle('is-village', Boolean(activeGeography?.village));
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
  ['county-selected-halo', 'county-selected-casing', 'county-selected'].forEach(id => {
    if (activeMap.getLayer(id)) activeMap.setFilter(id, ['==', ['get', 'name'], name || '']);
  });
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
  if (activeGeography?.county !== activeSelected) publishGeography(null);
  selectFilter(activeSelected);
  const feature = activeFeatures.find(item => item.properties.name === activeSelected);
  const bounds = feature && boundsFor(feature);
  if (activeMap && bounds) activeMap.fitBounds(bounds, {
    padding: {top: 86, right: 72, bottom: 86, left: 72},
    maxZoom: 8.2,
    ...perspectiveCamera(8.2),
    duration: animate ? cameraDuration(1120) : 0,
    easing: cameraEase,
  });
}

export function setElectionPerspective(mode, animate = true) {
  activePerspective = mode === '2d' ? '2d' : '3d';
  if (!activeMap) return;
  const element = activeMap.getContainer();
  element.dataset.perspective = activePerspective;
  const camera = perspectiveCamera();
  activeMap.easeTo({...camera, duration: animate ? cameraDuration(1050) : 0, easing: cameraEase});
  syncTerrain(activeMap);
  if (activeMap.getLayer('county-extrusion')) {
    activeMap.setPaintProperty('county-extrusion', 'fill-extrusion-opacity', activePerspective === '3d' ? 0.46 : 0);
  }
  if (activeMap.getLayer('nlsc-relief')) {
    activeMap.setPaintProperty('nlsc-relief', 'raster-opacity',
      ['interpolate', ['linear'], ['zoom'], 6.8, 0, 7.4, 0, 8, activePerspective === '3d' ? 0.16 : 0.09]);
  }
  if (activePerspective === '3d') {
    activeMap.dragRotate.enable();
    activeMap.touchZoomRotate.enableRotation();
  } else {
    activeMap.dragRotate.disable();
    activeMap.touchZoomRotate.disableRotation();
  }
}

export function resetElectionMap() {
  activeFocused = false;
  publishGeography(null);
  const compact = matchMedia('(max-width: 980px)').matches;
  if (activePerspective === '3d') {
    activeMap?.flyTo({
      center: [120.94, 23.72],
      zoom: compact ? 6.36 : 7.02,
      ...perspectiveCamera(compact ? 6.36 : 7.02),
      duration: cameraDuration(1080),
      curve: 1.16,
      essential: false,
    });
    return;
  }
  activeMap?.fitBounds(compact ? [[119.65, 21.65], [122.35, 25.55]] : [[118.0, 21.55], [122.25, 26.3]], {
    padding: compact ? 24 : 38,
    ...perspectiveCamera(5.55),
    duration: cameraDuration(1080),
    easing: cameraEase,
  });
}

export function stepBackElectionMap() {
  if (activeGeography?.village) {
    const town = {...activeGeography, village: '', villageCode: ''};
    publishGeography(town);
    activeMap?.flyTo({center: [town.lng, town.lat], zoom: 10.7, ...perspectiveCamera(10.7), duration: cameraDuration(900), curve: 1.18, essential: false});
    return;
  }
  if (activeGeography?.town) {
    publishGeography(null);
    focusElectionCounty(activeSelected);
    return;
  }
  resetElectionMap();
}

export function resizeElectionMap() {
  activeMap?.resize();
  if (activeGeography) return;
  if (activeFocused) focusElectionCounty(activeSelected, false);
  else resetElectionMap();
}

export function drawElectionMap(element, topology, results, rawCounties, baselineResults, selected, mode, basemap, perspective, onSelect, onGeography, deltas = {}) {
  clearMap();
  element.dataset.basemapReady = basemap === 'simple' ? 'true' : 'false';
  activeSelected = normalize(selected);
  activePerspective = perspective === '2d' ? '2d' : '3d';
  element.dataset.perspective = activePerspective;
  activeGeography = null;
  activeOnGeography = onGeography;
  const geojson = toFeatureCollection(topology, results, rawCounties, baselineResults, mode, deltas);
  activeFeatures = geojson.features;
  const map = activeMap = new MapLibreMap({
    container: element,
    style: mapStyle(),
    center: [120.85, 23.65],
    zoom: 5.55,
    ...perspectiveCamera(5.55),
    minZoom: 4.4,
    maxZoom: 18,
    attributionControl: false,
    maxPitch: 65,
    dragRotate: activePerspective === '3d',
    pitchWithRotate: activePerspective === '3d',
    cooperativeGestures: false,
  });
  map.addControl(new NavigationControl({showCompass: true, visualizePitch: true}), 'top-right');
  map.addControl(new ScaleControl({maxWidth: 110, unit: 'metric'}), 'bottom-left');
  map.on('error', () => {});
  map.once('load', () => {
    addOfficialBasemap(map, basemap);
    addTerrainModel(map, element);
    map.addSource('counties', {type: 'geojson', data: geojson, promoteId: 'id'});
    map.addLayer({
      id: 'county-shadow',
      type: 'line',
      source: 'counties',
      paint: {
        'line-color': '#0f2d44',
        'line-width': ['interpolate', ['linear'], ['zoom'], 4.5, 4.8, 8.5, 2.6, 11, 1.2],
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 4.5, 0.14, 8.5, 0.08, 11, 0.02],
        'line-blur': ['interpolate', ['linear'], ['zoom'], 4.5, 3.4, 9, 1.4],
      },
    });
    map.addLayer({
      id: 'county-fill',
      type: 'fill',
      source: 'counties',
      paint: {
        'fill-color': ['get', 'fill'],
        'fill-opacity': ['interpolate', ['linear'], ['zoom'],
          5.5, ['case', ['boolean', ['feature-state', 'hover'], false], basemap === 'simple' ? 0.96 : 0.82, ['*', ['get', 'opacity'], basemap === 'simple' ? 1 : 0.72]],
          9, basemap === 'simple' ? 0.48 : 0.28,
          11, basemap === 'simple' ? 0.24 : 0.08,
        ],
      },
    });
    map.addLayer({
      id: 'county-extrusion',
      type: 'fill-extrusion',
      source: 'counties',
      maxzoom: 9.4,
      paint: {
        'fill-extrusion-color': ['get', 'fill'],
        'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'],
          4.5, ['get', 'elevation'],
          7.8, ['*', ['get', 'elevation'], 0.25],
          9.2, 0,
        ],
        'fill-extrusion-base': 0,
        'fill-extrusion-opacity': activePerspective === '3d' ? 0.46 : 0,
        'fill-extrusion-opacity-transition': {duration: 620, delay: 0},
        'fill-extrusion-vertical-gradient': true,
      },
    });
    map.addLayer({
      id: 'county-boundary-casing',
      type: 'line',
      source: 'counties',
      paint: {
        'line-color': '#17344b',
        'line-width': ['interpolate', ['linear'], ['zoom'], 4.5, 2.2, 7.5, 1.8, 10, 1],
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 4.5, 0.78, 8, 0.56, 10.5, 0.12],
      },
    });
    map.addLayer({
      id: 'county-boundary',
      type: 'line',
      source: 'counties',
      paint: {
        'line-color': '#fffdf5',
        'line-width': ['interpolate', ['linear'], ['zoom'], 4.5, 0.86, 7.5, 0.68, 10, 0.42],
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 4.5, 0.9, 8, 0.72, 10.5, 0.16],
      },
    });
    map.addLayer({
      id: 'county-selected-halo',
      type: 'line',
      source: 'counties',
      filter: ['==', ['get', 'name'], activeSelected],
      paint: {
        'line-color': '#f3a51e',
        'line-width': ['interpolate', ['linear'], ['zoom'], 4.5, 9, 9, 6],
        'line-opacity': 0.24,
        'line-blur': 4,
      },
    });
    map.addLayer({
      id: 'county-selected-casing',
      type: 'line',
      source: 'counties',
      filter: ['==', ['get', 'name'], activeSelected],
      paint: {'line-color': '#6e4b16', 'line-width': ['interpolate', ['linear'], ['zoom'], 4.5, 4.2, 9, 2.8], 'line-opacity': 0.92},
    });
    map.addLayer({
      id: 'county-selected',
      type: 'line',
      source: 'counties',
      filter: ['==', ['get', 'name'], activeSelected],
      paint: {'line-color': '#ffd979', 'line-width': ['interpolate', ['linear'], ['zoom'], 4.5, 1.7, 9, 1.1], 'line-opacity': 1},
    });
    if (basemap !== 'simple') {
      map.addLayer({
        id: 'official-town-boundaries',
        type: 'raster',
        source: 'nlsc-town',
        minzoom: TOWN_LEVEL_ZOOM - 0.4,
        paint: {
          'raster-opacity': ['interpolate', ['linear'], ['zoom'], TOWN_LEVEL_ZOOM - 0.4, 0, 7.3, 0.26, 9.6, 0.2, 11, 0.07],
          'raster-opacity-transition': {duration: 540},
          'raster-fade-duration': 360,
          'raster-saturation': -0.72,
          'raster-contrast': -0.16,
        },
      });
      map.addLayer({
        id: 'official-village-boundaries',
        type: 'raster',
        source: 'nlsc-village',
        minzoom: VILLAGE_LEVEL_ZOOM - 0.5,
        paint: {
          'raster-opacity': ['interpolate', ['linear'], ['zoom'], VILLAGE_LEVEL_ZOOM - 0.5, 0, 11, 0.16, 12.5, 0.3, 16, 0.26],
          'raster-opacity-transition': {duration: 620},
          'raster-fade-duration': 420,
          'raster-hue-rotate': 18,
          'raster-saturation': -0.74,
          'raster-contrast': -0.18,
        },
      });
      map.addLayer({
        id: 'official-county-boundaries',
        type: 'raster',
        source: 'nlsc-city',
        maxzoom: 10.5,
        paint: {
          'raster-opacity': ['interpolate', ['linear'], ['zoom'], 4.5, 0.24, 7.5, 0.12, 10, 0],
          'raster-opacity-transition': {duration: 520},
          'raster-fade-duration': 380,
          'raster-saturation': -0.7,
          'raster-contrast': -0.18,
        },
      });
    }
    addLabels(map, activeFeatures, onSelect);
    renderOffshoreInsets(activeFeatures, onSelect);
    resetElectionMap();
    syncGeographicLevel(map);
    revealLoadedOfficialLayers(map, element, basemap);
    setElectionPerspective(activePerspective, false);
  });
  map.on('zoom', () => syncGeographicLevel(map));
  map.on('movestart', () => {
    element.dataset.cameraMoving = 'true';
    element.dataset.renderReady = 'false';
  });
  let settleTimer = null;
  map.on('moveend', () => {
    element.dataset.cameraMoving = 'false';
    clearTimeout(settleTimer);
    settleTimer = setTimeout(() => {
      if (element.dataset.cameraMoving !== 'true') element.dataset.renderReady = 'true';
    }, cameraDuration(420));
  });
  map.on('idle', () => { element.dataset.renderReady = 'true'; });
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
    if (name !== activeSelected || map.getZoom() < TOWN_LEVEL_ZOOM) {
      focusElectionCounty(name);
      onSelect(name);
      return;
    }
    drillAtPoint(map, event);
  });
  return map;
}
