import assert from 'node:assert/strict';
import {validationRows,competitionBucket,evidenceBucket,replayRows} from '../site/governance-v56.mjs';

const v5={
  confirmatory_reference_2022:{model:'frozen confirmatory',race_balanced_mae_pp:5.9807606878,winner_correct:14,winner_total:22,margin_mae_pp:11.276881147},
  candidate_offset_chronological_2022:{integrated_offset_mae_pp:4.8470669371,integrated_winner_correct:16,winner_total:19},
  end_to_end_development_2022:{v5_race_balanced_mae_pp:4.5968949867,v5_winner_correct:17,winner_total:22,v5_margin_mae_pp:9.6368604394}
};
const rows=validationRows(v5);
assert.equal(rows.length,3);
assert.equal(rows[0].id,'confirmatory');
assert.equal(rows[0].mae,v5.confirmatory_reference_2022.race_balanced_mae_pp);
assert.equal(rows[1].id,'chronological');
assert.equal(rows[1].mae,v5.candidate_offset_chronological_2022.integrated_offset_mae_pp);
assert.equal(rows[2].id,'development');
assert.equal(rows[2].mae,v5.end_to_end_development_2022.v5_race_balanced_mae_pp);
assert.match(rows[2].note,/development diagnostic/);

const closeButSparse={quality:{evidence:{grade:'C'}},candidates:[{mean:48,probability:.54},{mean:46,probability:.44},{mean:6,probability:.02}]};
assert.equal(competitionBucket(closeButSparse),'激烈競爭');
assert.equal(evidenceBucket(closeButSparse),'C · 資料有限');
const clearButSparse={quality:{evidence:{grade:'C'}},candidates:[{mean:61,probability:.94},{mean:33,probability:.06},{mean:6,probability:0}]};
assert.equal(competitionBucket(clearButSparse),'明顯領先');
assert.equal(evidenceBucket(clearButSparse),'C · 資料有限');
const missing={quality:{evidence:{grade:'D'}},candidates:[{mean:52,probability:.8},{mean:48,probability:.2}]};
assert.equal(competitionBucket(missing),'暫不評級');
assert.equal(evidenceBucket(missing),'D · 模型缺項');

const snapshot={counties:[
  {name:'台北市',candidates:[{name:'甲',mean:47,probability:.35},{name:'乙',mean:49,probability:.62}]},
  {name:'台中市',candidates:[{name:'丙',mean:51,probability:.55},{name:'丁',mean:46,probability:.43}]}
]};
const replay=replayRows(snapshot);
assert.deepEqual(replay.map(r=>[r.county,r.leader,r.mean,r.probability]),[
  ['台北市','乙',49,.62],['台中市','丙',51,.55]
]);
console.log('governance-v56-ui ok');
