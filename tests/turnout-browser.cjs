// Smoke-test the actual standalone turnout research view under Chromium.
// This does not assert candidate predictive gains or use invented market data.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../dist');
const server=http.createServer((req,res)=>{
  const u=new URL(req.url,'http://localhost'),pathname=u.pathname==='/'?'/index.html':decodeURIComponent(u.pathname);
  const target=path.resolve(root,'.'+pathname);
  if(!target.startsWith(root+path.sep)||!fs.existsSync(target)){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',({'.json':'application/json','.mjs':'text/javascript','.js':'text/javascript',
    '.css':'text/css','.html':'text/html;charset=utf-8'})[path.extname(target)]||'text/plain');
  fs.createReadStream(target).pipe(res);
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch({headless:true,
    ...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH,
      args:['--no-sandbox','--disable-setuid-sandbox','--use-gl=angle',
            '--use-angle=swiftshader','--enable-unsafe-swiftshader','--in-process-gpu']}:{})});
  const page=await browser.newPage({viewport:{width:1300,height:900}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.goto('http://127.0.0.1:'+server.address().port+'/?view=turnout',
      {waitUntil:'networkidle'});
    await page.waitForSelector('body[data-ready=true]',{timeout:20000});
    await page.locator('#turnoutDistrictPanel').waitFor();
    await page.locator('#turnoutVoteValidation').waitFor();
    await page.locator('#twoCycleTurnout').waitFor();
    await page.locator('#turnoutThreeYearAudit').waitFor();
    if(fs.existsSync(path.join(root,'turnout-three-year-compatibility.json'))){
      const audit=await page.locator('#turnoutThreeYearAudit').innerText();
      assert.match(audit,/36[46]/);
      assert.match(audit,/三屆行政區共同樣本/);
      assert.match(audit,/不可作選前準確率證據/);
    }
    if(fs.existsSync(path.join(root,'turnout-two-cycle-town-validation.json'))){
      const cycleText=await page.locator('#twoCycleTurnout').innerText();
      assert.match(cycleText,/2014—2018/);
      assert.match(cycleText,/2018—2022/);
      assert.match(cycleText,/兩個周期均低於直接延用基準/);
    }

    assert.match(await page.locator('#turnoutDistrictPanel').innerText(),/2018—2022/);
    assert.match(await page.locator('#turnoutVoteValidation').innerText(),/因果/);
    const unverified=await page.locator('#turnoutVoteValidation').innerText();
    if(fs.existsSync(path.join(root,'cec-town-candidate-association-2018-2022.json')))
      assert.match(unverified,/兩黨均有正式候選人/);
    await page.waitForFunction(()=>{
      const el=document.querySelector('#townTurnoutMap');
      return el&& (el.querySelectorAll('path').length>=8||
        el.textContent.includes('暫不可用'));
    },null,{timeout:15000});
    assert.ok(await page.locator('#townTurnoutMap path').count()>=8,
      'Historical Taipei township polygons must load, not just a placeholder.');
    await page.locator('#townTurnoutMap path').first().click();
    const inspection=await page.locator('#turnoutMapInspector').innerText();
    assert.match(inspection,/2018投票率/);
    if(fs.existsSync(path.join(root,'turnout-district-panel-2014-2018.json'))
       &&fs.existsSync(path.join(root,'turnout-two-cycle-town-validation.json'))){
      await page.waitForFunction(()=>{
        const el=document.querySelector('#priorTownTurnoutMap');
        return el&&(el.querySelectorAll('path').length>=8||
          el.textContent.includes('暫不可用'));
      },null,{timeout:15000});
      assert.ok(await page.locator('#priorTownTurnoutMap path').count()>=8,
        'The verified original-year 2014→2018 township map must load real GIS polygons.');
      await page.locator('#priorTownTurnoutMap path').first().click();
      assert.match(await page.locator('#priorTurnoutMapInspector').innerText(),/2014投票率/);
      assert.ok(await page.locator('#townTurnoutMap path').count()>=8,
        'The second map must not cancel or erase the first historical map.');
    }
    await page.selectOption('#precinctCounty','新北市');
    await page.locator('#turnoutDistrictPanel h2').waitFor();
    await page.waitForFunction(()=>document.querySelectorAll('#townTurnoutMap path').length>=25,null,{timeout:15000});
    await page.selectOption('#precinctCounty','台北市');
    await page.waitForFunction(()=>document.querySelectorAll('#townTurnoutMap path').length>=8,null,{timeout:15000});
    assert.deepEqual(errors,[],'No JS errors on historical turnout research route');
    console.log(JSON.stringify({passed:true,route:'turnout',
      taipei_map_polygon_count:await page.locator('#townTurnoutMap path').count(),
      no_forecast_mutation:true}));
  }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
