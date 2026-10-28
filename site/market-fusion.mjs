// Experimental event-level market signal. Intentionally isolated from the
// canonical HB-TLEF posterior, candidate vote shares, and national seat draws.
// All weights are uncalibrated sensitivity assumptions, NOT trained estimates.
export const MARKET_FUSION_WEIGHTS = Object.freeze([0, 0.05, 0.10]);

const NAMES = Object.freeze({
  '台北市': {'Chiang Wan-an':'蔣萬安','Puma Shen':'沈伯洋','Kuo Hsi':'郭璽'},
  '新北市': {'Su Chiao-hui':'蘇巧慧','Lee Shu-chuan':'李四川'},
  '桃園市': {'Chang San-cheng':'張善政','Huang Shih-chieh':'黃世杰'},
  '台中市': {'Johnny Chiang':'江啟臣','Ho Hsin-chun':'何欣純'},
  '高雄市': {'Lai Jui-lung':'賴瑞隆','Ko Chih-en':'柯志恩','Chang Ching':'張靜'},
  '基隆市': {'Hsieh Kuo-liang':'謝國樑','Tung Tzu-wei':'童子瑋'},
  '新竹市': {'Ann Kao':'高虹安','Chuang Ching-cheng':'莊競程','Ho Chih-yung':'何志勇'},
  '新竹縣': {'Cheng Chao-fang':'鄭朝方','Hsu Hsin-ying':'徐欣瑩'},
  '苗栗縣': {'Chung Tung-chin':'鍾東錦','Chen Pin-an':'陳品安'},
  '彰化縣': {'Chen Su-yueh':'陳素月','Wei Ping-cheng':'魏平政','Chiu Chien-fu':'邱建富'},
  '嘉義縣': {'Tsai Yi-yu':'蔡易餘','Wu Pin-jui':'吳品叡'},
  '嘉義市': {'Wang Mei-hui':'王美惠','Chang Chi-kai':'張啓楷','Huang Hung-cheng':'黃宏成台灣阿成世界偉人財神總統','Chen Kai-huang':'陳愷璜'},
  '屏東縣': {'Chou Chun-mi':'周春米','Su Ching-chuan':'蘇清泉'},
  '宜蘭縣': {'Lin Kuo-chang':'林國漳','Wu Tsung-hsien':'吳宗憲'},
  '台東縣': {'Wu Hsiu-hua':'吳秀華','Chen Ying':'陳瑩','Li Wu Ying-chih':'李吳穎智'},
  '花蓮縣': {'Yu Shu-chen':'游淑貞','Wei Chia-hsien':'魏嘉賢','Chang Chun':'張峻','Lo Pei-chin':'羅佩秦'},
  '澎湖縣': {'Chen Chen-chung':'陳振中','Wu Shu-chin':'吳淑瑾','Yeh Chu-lin':'葉竹林','Chou Ni-an':'周倪安','Chen Chin-chuan':'陳盡川','Hsu Chih-fu':'許智富'},
  '金門縣': {'Chen Yu-jen':'陳玉珍','Liang Wen-tao':'梁文韜','Li Wen-liang':'李文良'},
  '連江縣': {'Wang Chung-ming':'王忠銘','Tsao Erh-yuan':'曹爾元'}
});

const error = reason => ({eligible:false,reason,weight:0,probabilities:[]});
function validProbability(value) {return typeof value==='number' && Number.isFinite(value)&&value>=0&&value<=1;}

// A normalized log-opinion pool of the model's *event* probabilities and
// a source-verified, exhaustively mapped market event. This does not infer
// candidate vote shares and must not be treated as a calibrated posterior.
export function marketFusion(model, event, weight=0.05, asOf=new Date().toISOString()) {
  if(!MARKET_FUSION_WEIGHTS.includes(weight))return error('非預先聲明的研究權重');
  if(!event||event.stale)return error('來源不存在或只有過期快照');
  const race=(model?.counties||[]).find(x=>x.name===event.county);
  if(!race||race.candidates?.length<2)return error('目前名單無法對應選區');
  const quoteTime=Date.parse(event.quote_as_of||'');
  const checkTime=Date.parse(asOf||'');
  if(!Number.isFinite(quoteTime)||!Number.isFinite(checkTime)||quoteTime>checkTime||
      checkTime-quoteTime>12*3600000)return error('交易報價超過12小時或時間異常');
  if(!Number.isFinite(event.volume_usd)||event.volume_usd<10000||
      !Number.isFinite(event.liquidity_usd)||event.liquidity_usd<10000)return error('交易量或流動性不足');
  const raw=event.outcomes||[];
  if(raw.length<2||raw.some(x=>!validProbability(x.probability)))return error('合約結果資料不完整');
  const total=raw.reduce((sum,x)=>sum+x.probability,0);
  if(total<0.93||total>1.07)return error('合約價格總和偏離100%過多');
  const alias=NAMES[event.county]||{},registered=new Map(race.candidates.map(c=>[c.name,c]));
  const mapped=new Map(),unknown=[];
  for(const outcome of raw){
    const name=alias[outcome.name];
    if(!name||!registered.has(name)){unknown.push(outcome);continue;}
    if(mapped.has(name))return error('合約多重對應同一候選人');
    mapped.set(name,outcome);
  }
  if(mapped.size<2)return error('少於兩位已核驗的市場候選人');
  if(unknown.reduce((sum,x)=>sum+x.probability,0)>0.02)return error('市場包含重要但無法對應的選項');
  const matched=[...mapped.values()].sort((a,b)=>b.probability-a.probability);
  if(matched.slice(0,2).some(x=>x.spread==null||!Number.isFinite(x.spread)||x.spread>0.10))
    return error('主要選項買賣價差缺漏或過大');
  const qKnown=[...mapped.values()].reduce((sum,x)=>sum+x.probability,0);
  if(qKnown<0.90)return error('市場有效對應不足90%');
  const p=modelProbabilities(race);
  if(!p)return error('模型勝率無效');
  const unused=race.candidates.filter(c=>!mapped.has(c.name));
  const remaining=Math.max(0,1-qKnown),available=unused.reduce((sum,c)=>sum+p.get(c.name),0);
  const q=new Map();
  for(const c of race.candidates){
    const known=mapped.get(c.name);
    const rawPrice=known?.probability;
    q.set(c.name,known?rawPrice:unused.length?remaining*(available>0?p.get(c.name)/available:1/unused.length):0);
  }
  const qTotal=[...q.values()].reduce((a,b)=>a+b,0);
  if(qTotal<=0)return error('市場候選人合約未形成有效分布');
  const scores=race.candidates.map(c=>{
    const p0=Math.max(0.0005,p.get(c.name)),q0=Math.max(0.0005,q.get(c.name)/qTotal);
    return weight===0?p.get(c.name):Math.exp((1-weight)*Math.log(p0)+weight*Math.log(q0));
  });
  const z=scores.reduce((sum,x)=>sum+x,0);
  if(!z||!Number.isFinite(z))return error('融合分布無法歸一化');
  return {
    eligible:true,weight,
    source:'Polymarket',method:'uncalibrated_logarithmic_opinion_pool',
    modelVersion:model.model_version||null,marketSlug:event.slug,quoteAsOf:event.quote_as_of,
    probabilities:race.candidates.map((c,i)=>({
      candidateId:c.candidate_id,name:c.name,model:p.get(c.name),
      market:mapped.has(c.name)?mapped.get(c.name).probability:null,
      alignedMarket:q.get(c.name)/qTotal,
      fused:scores[i]/z,delta:scores[i]/z-p.get(c.name),
      mapped:mapped.has(c.name)
    }))
  };
}
function modelProbabilities(race){
  const p=new Map(),arr=race.candidates;
  if(!arr.every(c=>validProbability(c.probability)))return null;
  const total=arr.reduce((x,c)=>x+c.probability,0);
  if(Math.abs(total-1)>0.03)return null;
  for(const c of arr)p.set(c.name,c.probability/total);
  return p;
}
