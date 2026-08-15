import asyncio,json
from pathlib import Path
import base64
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True, executable_path='/home/raphael/.local/bin/playwright-chromium-userlocal', args=['--no-sandbox'])
  page=await b.new_page(viewport={'width':390,'height':844})
  out={'console':[],'failed':[]}
  page.on('console',lambda m:out['console'].append([m.type,m.text]))
  page.on('pageerror',lambda e:out['console'].append(['pageerror',str(e)]))
  page.on('requestfailed',lambda r:out['failed'].append([r.url,r.failure]))
  try: await page.goto('http://127.0.0.1:18766/',wait_until='commit',timeout=5000)
  except Exception as e: out['goto_error']=type(e).__name__+': '+str(e)
  await page.wait_for_timeout(15000)
  out['before']=await page.evaluate('''()=>({url:location.href,cards:document.querySelectorAll('.task-card').length,body:document.body.innerText.slice(0,5000),width:innerWidth,scrollWidth:document.documentElement.scrollWidth,script:typeof loadDashboard,resources:[...performance.getEntriesByType('resource')].map(x=>x.name).slice(-20)})''')
  try:
   rep=page.locator('.task-card').filter(has_text='삼성펀드').first
   out['rep_text']=await rep.inner_text(timeout=3000)
   act=rep.locator('.task-card-primary-action button:not(.subtle-btn)').first
   out['action']=await act.inner_text(timeout=3000)
   await act.focus(); out['focus_before']=await page.evaluate('document.activeElement?.innerText')
   await act.click(timeout=3000); await page.wait_for_timeout(300)
   cdp=await page.context.new_cdp_session(page)
   shot=await cdp.send('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})
   Path('/home/raphael/myproject/docs/qa/evidence-slice-a/interaction.png').write_bytes(base64.b64decode(shot['data']))
   out['open']=await page.evaluate('''()=>({dialogs:[...document.querySelectorAll('[role=dialog]')].filter(x=>getComputedStyle(x).display!=='none').length,title:document.querySelector('#taskDetailTitle')?.innerText,body:document.querySelector('#taskDetailBody')?.innerText.slice(0,3000),active:document.activeElement?.innerText})''')
   await page.keyboard.press('Escape'); await page.wait_for_timeout(200)
   out['close']=await page.evaluate('''()=>({dialogs:[...document.querySelectorAll('[role=dialog]')].filter(x=>getComputedStyle(x).display!=='none').length,active:document.activeElement?.innerText,activeId:document.activeElement?.id})''')
  except Exception as e: out['interaction_error']=type(e).__name__+': '+str(e)
  print(json.dumps(out,ensure_ascii=False,indent=2))
  await b.close()
asyncio.run(main())
