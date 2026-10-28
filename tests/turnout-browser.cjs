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
