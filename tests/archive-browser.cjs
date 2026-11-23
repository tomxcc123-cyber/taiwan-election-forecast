const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../qa/blackout-site');
if(!fs.existsSync(path.join(root,'index.html')))throw new Error('Missing blackout-safe historical build');
const mime={'.html':'text/html;charset=utf-8','.json':'application/json','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css'};
const server=http.createServer((req,res)=>{
  const pathname=new URL(req.url,'http://localhost').pathname;
  const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':decodeURIComponent(pathname)));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){
    res.writeHead(404);res.end('Not found');return;
  }
  res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    const base='http://127.0.0.1:'+server.address().port+'/';
    await page.goto(base,{waitUntil:'networkidle'});
    await page.waitForFunction(()=>document.querySelectorAll('.map-county').length===22,{timeout:12000});
    assert.equal(await page.locator('[data-year]').count(),3);
    assert.equal(await page.locator('.map-county').count(),22);
    assert.equal(await page.locator('#countySelect option').count(),23);
    assert.match(await page.locator('#mapScope').innerText(),/TAIWAN/);
    assert.match(await page.locator('.legal-strip').innerText(),/2026/);
    assert.equal((await page.request.get(base+'candidate-model.json')).status(),404);
    assert.equal((await page.request.get(base+'polls.json')).status(),404);
    assert.equal((await page.request.get(base+'model-data.json')).status(),404);
    await page.locator('#countySelect').selectOption('台北市');
    await page.waitForFunction(()=>document.querySelector('#mapScope')?.textContent?.includes('2022 TOWNSHIP RESULTS'));
    assert.ok(await page.locator('.map-county').count()>10);
    assert.match(await page.locator('#inspectorTitle').innerText(),/台北市/);
    assert.ok(await page.locator('.candidate-item').count()>1);
    assert.ok(await page.locator('#townList button').count()>5);
    await page.locator('#backTaiwan').click();
    assert.equal(await page.locator('.map-county').count(),22);
    await page.locator('button[data-year="2018"]').click();
    assert.equal(await page.locator('button[data-year="2018"]').getAttribute('aria-pressed'),'true');
    assert.match(await page.locator('#resultYear').innerText(),/2018/);
    await page.locator('button[data-metric="turnout"]').click();
    assert.equal(await page.locator('button[data-metric="turnout"]').getAttribute('aria-pressed'),'true');
    assert.match(await page.locator('#mapLegend').innerText(),/歷史實際投票率/);
    await page.setViewportSize({width:390,height:844});
    await page.waitForTimeout(160);
    const dims=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));
    assert.ok(dims.scroll<=dims.viewport+1,'Mobile horizontal overflow: '+JSON.stringify(dims));
    assert.deepEqual(errors,[]);
    console.log('Archive GIS browser passed: 22 counties, 2022 towns, 2018 vote/turnout, 390px mobile; 2026 assets excluded');
  } finally{
    await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
})().catch(error=>{console.error(error);server.close();process.exitCode=1});
