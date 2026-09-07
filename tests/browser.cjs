const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../dist');
const qa=path.resolve(__dirname,'../qa');fs.mkdirSync(qa,{recursive:true});
const real=JSON.parse(fs.readFileSync(path.join(root,'polls.json'),'utf8'));
let mode='real';
const mock=structuredClone(real);
const candidate=mock.records.find(r=>r.county==='台北市');
assert.ok(candidate,'real source needed for integration test');
const r=structuredClone(candidate);r.id='1234567890abcdef12345678';
r.date='2026-08-26';r.field_start='2026-08-21';r.model_eligible=true;r.exclusion_reason=null;
r.candidates[0].support=44;r.candidates[1].support=45;r.undecided=11;
mock.records.unshift(r);
mock.polls=[{id:r.id,county:r.county,source:r.source,date:r.date,sample_n:r.sample_n,blue:44,dpp:45,third:0,other:0,undecided:11}];
const server=http.createServer((req,res)=>{
 const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
 if(pathname==='/polls.json'){
  if(mode==='failure'){res.writeHead(503);res.end('Unavailable');return;}
  res.setHeader('Content-Type','application/json');
  res.end(JSON.stringify(mode==='mock'?mock:mode==='invalid'?{...mock,polls:[{...mock.polls[0],blue:400}]}:real));return;
 }
 const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
 if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
 const type={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.json':'application/json'}[path.extname(file)]||'application/octet-stream';
 res.setHeader('Content-Type',type);fs.createReadStream(file).pipe(res);
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(`http://127.0.0.1:${server.address().port}/legacy.html`,{waitUntil:'domcontentloaded'});
  await page.waitForSelector('body[data-public-ready="true"]');
  await page.waitForFunction(()=>document.querySelectorAll('#countyMap .county-path').length>=20);
  assert.equal(await page.locator('#apiKey').count(),0,'no public API key input');
  assert.equal(await page.locator('.public-poll-record').count(),real.records.length);
  assert.equal(await page.evaluate(()=>USER_POLLS.filter(p=>p.external).length),0,'old baseline polls not reweighted');
  await page.screenshot({path:path.join(qa,'desktop.png')});
  await page.locator('#publicPolls').evaluate(n=>n.scrollIntoView({block:'start',behavior:'instant'}));
  await page.screenshot({path:path.join(qa,'polls-desktop.png')});
  await page.locator('#publicPollArchiveTitle').click();
  await page.selectOption('#publicPollCounty','連江縣');
  assert.equal(await page.locator('.public-poll-record').count(),0);
  assert.ok((await page.locator('#publicPollRecords').innerText()).includes('尚無'));
  await page.selectOption('#publicPollCounty','all');
  const before=await page.evaluate(()=>APP.counties['台北市'].forecast.blue_exp);
  mode='mock';
  await page.evaluate(()=>PublicPolls.reload());
  const after=await page.evaluate(()=>APP.counties['台北市'].forecast.blue_exp);
  assert.notEqual(before,after,'new validated feed actually reaches forecast model');
  assert.equal(await page.evaluate(()=>USER_POLLS.filter(p=>p.external).length),1);
  await page.evaluate(()=>PublicPolls.reload());
  assert.equal(await page.evaluate(()=>USER_POLLS.filter(p=>p.external).length),1,'no duplicate input on refresh');
  const after2=await page.evaluate(()=>APP.counties['台北市'].forecast.blue_exp);
  assert.equal(after,after2,'unchanged feed is stable');
  mode='failure';await page.evaluate(()=>PublicPolls.reload());
  assert.equal(await page.evaluate(()=>APP.counties['台北市'].forecast.blue_exp),after);
  assert.ok((await page.locator('#publicPollStripStatus').innerText()).includes('連線失敗'));
  mode='invalid';await page.evaluate(()=>PublicPolls.reload());
  assert.equal(await page.evaluate(()=>APP.counties['台北市'].forecast.blue_exp),after,'malformed feed cannot corrupt current model');
  mode='real';await page.evaluate(()=>PublicPolls.reload());
  assert.equal(await page.evaluate(()=>USER_POLLS.filter(p=>p.external).length),0,'restored feed replaces previous external set');
  for(const width of [390,768]){
   await page.setViewportSize({width,height:900});
   await page.evaluate(()=>scrollTo(0,0));
   await page.screenshot({path:path.join(qa,`mobile-${width}.png`)});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'no page overflow '+width);
   await page.locator('#publicPolls').scrollIntoViewIfNeeded();
   await page.screenshot({path:path.join(qa,`polls-${width}.png`)});
  }
  assert.deepEqual(errors,[],'no JS runtime exceptions');
  fs.writeFileSync(path.join(qa,'browser-result.json'),JSON.stringify({passed:true,records:real.records.length,before,after,mobileWidths:[390,768],errors},null,2));
  console.log('PASS: real source display, new-feed model integration, deduplication, failure recovery, invalid-feed rejection, mobile layouts');
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
