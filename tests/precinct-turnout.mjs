import assert from 'node:assert/strict';
import {validatePrecinctIndex,validatePrecinctRecord,precinctDistricts,precinctPanel} from '../site/precinct-turnout-ui.mjs';

const names=Array.from({length:22},(_,i)=>i===0?'台北市':i===1?'嘉義市':'測試'+String.fromCodePoint(0x4e00+i));
const entries=[];
for(const year of [2014,2018,2022]){
  for(const county of names){
    const missing=county==='嘉義市'&&year===2022;
    entries.push({year,county,
      status:missing?'district_only_original':'official_precinct_aggregate_verified',
      path:missing?undefined:'cec-precincts/'+year+'-'+county+'.json',
      precinct_count:missing?0:2,
      totals:missing?undefined:{electorate:200,ballots_cast:160,valid_votes:158,invalid_votes:2}
    });
  }
}
const source={schema_version:1,races_expected:66,entries,station_rows:130,
  source_url:'https://data.cec.gov.tw/選舉資料庫/votedata.zip'};
assert.equal(validatePrecinctIndex(source),source);
const record={schema_version:1,year:2022,county:'台北市',precinct_count:2,
 totals:{electorate:200,ballots_cast:160,valid_votes:158,invalid_votes:2},
 precincts:[
  {geo_codes:['01','000','00','010','0001','0001'],
    precinct_number:'0001',district_name:'中正區',village_name:'建民里',
    electorate:100,ballots_cast:90,valid_votes:89,invalid_votes:1},
  {geo_codes:['01','000','00','010','0002','0002'],
    precinct_number:'0002',district_name:'中正區',village_name:'光明里',
    electorate:100,ballots_cast:70,valid_votes:69,invalid_votes:1}
 ]};
assert.equal(validatePrecinctRecord(source,record,2022,'台北市'),record);
assert.deepEqual(precinctDistricts(record).map(x=>[x.name,x.stations,x.ballots_cast]),[['中正區',2,160]]);
const page=precinctPanel(source,record,'台北市',2022);
assert.match(page,/投開票所原始資料/);
assert.match(page,/65 \/ 66/);
assert.match(page,/中正區/);
assert.match(page,/90.00%/);
assert.match(page,/80.00%/);
assert.match(page,/下載目前縣市投開票所明細/);
const missing=precinctPanel(source,null,'嘉義市',2022);
assert.match(missing,/只有區級合計/);
const broken=structuredClone(record);broken.precincts[0].ballots_cast=91;
assert.throws(()=>validatePrecinctRecord(source,broken,2022,'台北市'),/守恆/);
const badSource=structuredClone(source);badSource.entries.pop();
assert.throws(()=>validatePrecinctIndex(badSource),/66場/);
assert.match(precinctPanel(null,null),/尚未通過建置核驗/);
console.log(JSON.stringify({passed:true,source_years:3,counties:22,verified:65,fixture_only:true}));
