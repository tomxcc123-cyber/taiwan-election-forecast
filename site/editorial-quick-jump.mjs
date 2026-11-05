/* Editorial navigation enhancement. No changes to forecasts or GIS state. */
const SECTION_INDEX = Object.freeze([
  {view:'overview', label:'預測總覽', detail:'全台 GIS 與五個關鍵戰場', symbol:'◎'},
  {view:'counties', label:'競賽中心', detail:'縣市候選人與選區詳情', symbol:'▦'},
  {view:'updates', label:'歷史選舉 GIS', detail:'2014、2018、2022 與 2026', symbol:'◷'},
  {view:'polls', label:'民調中心', detail:'原始數據與入模狀態', symbol:'≋'},
  {view:'turnout', label:'投票率', detail:'歷屆投票率與區域研究', symbol:'▥'},
  {view:'markets', label:'市場觀察', detail:'市場訊號與研究限制', symbol:'◈'},
  {view:'scenario', label:'情境推演', detail:'測試選情假設與反事實情境', symbol:'⌁'},
  {view:'validation', label:'模型驗證', detail:'歷史留出與可重現檢查', symbol:'✓'},
  {view:'methods', label:'研究方法', detail:'資料來源、模型與限制', symbol:'i'}
]);

const norm = text => String(text??'').normalize('NFKC').replaceAll('臺','台').trim().toLowerCase();

export function makeIndex(data) {
  const sections = SECTION_INDEX.map(item=>({...item, id:'view:'+item.view,kind:'section'}));
  const counties = (data?.counties||[]).map(r=>({
    id:'county:'+r.name,kind:'county',view:'counties',county:r.name,
    label:r.name,detail:(r.candidates||[]).map(c=>c.name).join(' · ')||'縣市選情詳情',
    symbol:'⌖',
  }));
  const unique = new Map();
  for (const item of counties) if(!unique.has(norm(item.county)))unique.set(norm(item.county),item);
  return [...sections,...unique.values()];
}

export function matchItems(items,query,limit=14) {
  const text=norm(query);
  if(!text)return items.slice(0,9);
  const matched=items.map(item=>{
    const label=norm(item.label), county=norm(item.county), desc=norm(item.detail);
    const score=label===text?100:label.startsWith(text)?80:county.includes(text)?75:
      label.includes(text)?65:desc.includes(text)?40:0;
    return {item,score};
  }).filter(x=>x.score>0).sort((a,b)=>b.score-a.score||a.item.label.localeCompare(b.item.label,'zh-Hant'));
  return matched.slice(0,limit).map(x=>x.item);
}

export function buildDestination(current,item) {
  const url=new URL(current);
  if(!item || !SECTION_INDEX.some(s=>s.view===item.view))throw new Error('Invalid search destination');
  url.searchParams.set('view',item.view==='overview'?'map':item.view);
  if(item.kind==='county'){
    url.searchParams.set('county',item.county);
    // The candidate app restores state from the compact "s" payload before
    // reading the county query parameter. Change BOTH, or county jump would
    // silently reopen the previously saved county instead of the searched one.
    const encoded=url.searchParams.get('s');
    if(encoded){
      try{
        if(encoded.length>48000)throw Error('oversized scenario');
        const saved=JSON.parse(decodeURIComponent(escape(atob(encoded))));
        if(![2,3].includes(saved.v)||!saved.state||typeof saved.state!=='object')
          throw Error('invalid scenario');
        saved.state.county=item.county;
        url.searchParams.set('s',btoa(unescape(encodeURIComponent(JSON.stringify(saved)))));
      }catch{url.searchParams.delete('s');}
    }
    url.searchParams.set('election','2026-local');
    url.searchParams.set('level','county');
    url.searchParams.delete('town');
    url.searchParams.delete('village');
    url.searchParams.delete('district');
  }
  url.hash='';
  return url.toString();
}

export function formatFeedStatus(feed,model){
  if (!feed || !model || feed.checked_at!==model.feed_checked_at) {
    return {quality:'unknown',text:'資料版本核對中'};
  }
  const updated=Date.parse(feed.checked_at);
  if(!Number.isFinite(updated))return {quality:'unknown',text:'更新時間未核實'};
  const time=new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(updated));
  return {quality:feed.status==='degraded'?'degraded':'verified',
    text:feed.status==='degraded'?('部分來源受限 · '+time):('資料已同步 · '+time)};
}

function tag(tagName,className,text){
  const el=document.createElement(tagName);
  if(className)el.className=className;
  if(text!==undefined)el.textContent=text;
  return el;
}

function setup(){
  const opener=document.querySelector('#quickJump');
  const modal=document.querySelector('#quickPalette');
  const input=document.querySelector('#paletteInput');
  const output=document.querySelector('#paletteResults');
  const feedback=document.querySelector('#designStatus');
  if(!opener || !modal || !input || !output)return;
  let items=makeIndex(null),visible=[],selected=0,loading=null;
  let lastOpener=null;

  const paint=()=>{
    visible=matchItems(items,input.value);
    selected=Math.min(selected,Math.max(0,visible.length-1));
    output.replaceChildren();
    if(!visible.length){
      output.append(tag('p','palette-empty','沒有符合的縣市或功能。請試試候選人姓名或縣市。'));
      return;
    }
    let lastType;
    visible.forEach((item,i)=>{
      if(item.kind!==lastType)output.append(tag('div','palette-group',item.kind==='county'?'縣市與候選人':'網站功能'));
      lastType=item.kind;
      const button=tag('button','palette-result');
      button.type='button';
      button.dataset.searchResult=item.id;
      button.setAttribute('role','option');
      button.setAttribute('aria-selected',String(i===selected));
      if(i===selected)button.classList.add('is-active');
      button.append(tag('span','palette-result-icon',item.symbol));
      const content=tag('span');
      content.append(tag('strong',null,item.label),tag('small',null,item.detail));
      button.append(content,tag('span','palette-result-arrow','↵'));
      button.addEventListener('click',()=>window.location.assign(buildDestination(window.location.href,item)));
      output.append(button);
    });
  };

  const choose=(n)=>{
    if(n<0||n>=visible.length)return;
    selected=n;
    output.querySelectorAll('.palette-result').forEach((el,i)=>{
      el.classList.toggle('is-active',i===selected);
      el.setAttribute('aria-selected',String(i===selected));
    });
    output.querySelectorAll('.palette-result')[selected]?.scrollIntoView({block:'nearest'});
  };

  const updateIndex=()=>{
    if(window.CandidateApp?.data){items=makeIndex(window.CandidateApp.data);paint();return Promise.resolve();}
    if(loading)return loading;
    loading=fetch('candidate-model.json',{cache:'no-store'}).then(r=>{
      if(!r.ok)throw Error('model unavailable');
      return r.json();
    }).then(d=>{items=makeIndex(d);paint();}).catch(()=>{items=makeIndex(null);paint();}).finally(()=>{loading=null;});
    return loading;
  };

  const open=()=>{
    if(modal.open)return;
    lastOpener=document.activeElement;
    input.value='';selected=0;paint();
    modal.showModal();opener.setAttribute('aria-expanded','true');
    input.focus();
    updateIndex();
  };
  const dismiss=()=>{
    // Native dialog close event is asynchronous; update ARIA state now.
    opener.setAttribute('aria-expanded','false');
    if(modal.open)modal.close();
  };
  opener.addEventListener('click',open);
  modal.addEventListener('cancel',()=>opener.setAttribute('aria-expanded','false'));
  modal.addEventListener('close',()=>{
    // Ignore a stale close event if the command palette was already reopened.
    if(modal.open)return;
    opener.setAttribute('aria-expanded','false');
    (lastOpener?.isConnected?lastOpener:opener)?.focus();
  });
  input.addEventListener('input',()=>{selected=0;paint()});
  input.addEventListener('keydown',event=>{
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();dismiss();return;}
    if(event.key==='ArrowDown'){event.preventDefault();choose((selected+1)%Math.max(visible.length,1));}
    if(event.key==='ArrowUp'){event.preventDefault();choose((selected-1+visible.length)%Math.max(visible.length,1));}
    if(event.key==='Enter'&&visible.length){event.preventDefault();window.location.assign(buildDestination(window.location.href,visible[selected]));}
  });
  document.addEventListener('keydown',event=>{
    const target=event.target;
    const typing=target?.matches?.('input,textarea,select,[contenteditable=true]');
    if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){
      event.preventDefault();if(modal.open)dismiss();else open();
    }else if(event.key==='/'&&!typing&&!modal.open&&!event.ctrlKey&&!event.metaKey&&!event.altKey){
      event.preventDefault();open();
    }
  });
  if(feedback){
    // The election application has already verified and loaded both snapshots.
    // Reuse those in-memory objects instead of downloading two large JSON
    // bundles again solely to paint a small status label.
    const repaint=()=>{
      if(!window.CandidateApp?.data||!window.CandidateApp?.feed)return false;
      const state=formatFeedStatus(window.CandidateApp.feed,window.CandidateApp.data);
      feedback.textContent=state.text;
      feedback.dataset.quality=state.quality;
      feedback.title='調查來源檢查狀態；不代表選舉結果已校準';
      return true;
    };
    if(!repaint()){
      const observer=new MutationObserver(()=>{
        if(repaint())observer.disconnect();
      });
      observer.observe(document.body,{attributes:true,attributeFilter:['data-ready']});
    }
    window.addEventListener('candidate-forecast-refreshed',repaint);
  }
}

if(typeof document!=='undefined'){
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup,{once:true});
  else setup();
}
