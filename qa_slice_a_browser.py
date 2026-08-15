import asyncio, json, os
from pathlib import Path
from playwright.async_api import async_playwright

BASE=Path('/home/raphael/myproject/docs/qa/evidence-slice-a')
BASE.mkdir(parents=True, exist_ok=True)

async def capture(page, path):
  cdp = await page.context.new_cdp_session(page)
  shot = await cdp.send('Page.captureScreenshot', {'format':'png', 'captureBeyondViewport':False})
  Path(path).write_bytes(__import__('base64').b64decode(shot['data']))

async def main():
  async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True, executable_path='/home/raphael/.local/bin/playwright-chromium-userlocal', args=['--no-sandbox'])
    page = await browser.new_page(viewport={'width':1440,'height':1000})
    console=[]; failed=[]; methods=[]
    page.on('console', lambda m: console.append({'type':m.type,'text':m.text}))
    page.on('pageerror', lambda e: console.append({'type':'pageerror','text':str(e)}))
    page.on('requestfailed', lambda r: failed.append({'url':r.url,'failure':r.failure}))
    page.on('request', lambda r: methods.append({'method':r.method,'url':r.url}))
    results=[]
    for w,h,name in [(1440,1000,'desktop'),(1024,1000,'tablet'),(390,844,'compact')]:
      await page.set_viewport_size({'width':w,'height':h})
      await page.goto('http://127.0.0.1:18766/', wait_until='commit', timeout=10000)
      await page.wait_for_timeout(3000)
      await capture(page, BASE/f'{name}.png')
      data=await page.evaluate('''() => ({
        width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        sections:[...document.querySelectorAll('body > .shell > section, body > .shell > details')].map(x=>x.id),
        text: document.body.innerText.slice(0,12000),
        cardCount: document.querySelectorAll('.task-card').length,
        buttons:[...document.querySelectorAll('button')].map(b=>b.innerText.trim()).filter(Boolean),
        forbidden:[...document.querySelectorAll('button,input,textarea,select')].map(x=>x.innerText||x.getAttribute('placeholder')||x.getAttribute('aria-label')||'').filter(t=>/재전송|게이트|live note|라이브|final review|최종 검토|승인/.test(t)),
        focus: document.activeElement?.id || document.activeElement?.innerText?.slice(0,80) || ''
      })''')
      results.append({'viewport':name,'data':data})
    await page.set_viewport_size({'width':390,'height':844})
    # select representative card by task text
    await page.wait_for_selector('.task-card', timeout=15000)
    rep=page.locator('.task-card').filter(has_text='삼성펀드').first
    if await rep.count()==0: rep=page.locator('.task-card').first
    before=await page.evaluate('() => ({dialogs:[...document.querySelectorAll("[role=dialog]")].filter(x=>getComputedStyle(x).display!=="none").length, body:document.body.innerText})')
    action=rep.locator('.task-card-primary-action button:not(.subtle-btn)').first
    action_text=await action.inner_text()
    await action.focus(); focus_before=await page.evaluate('document.activeElement?.innerText')
    await action.click(); await page.wait_for_timeout(150)
    open_state=await page.evaluate('''() => ({dialogs:[...document.querySelectorAll('[role="dialog"]')].filter(x=>getComputedStyle(x).display!=='none').length, title:document.querySelector('#taskDetailTitle')?.innerText, body:document.querySelector('#taskDetailBody')?.innerText, active:document.activeElement?.id || document.activeElement?.innerText})''')
    await page.keyboard.press('Escape'); await page.wait_for_timeout(100)
    close_state=await page.evaluate('''() => ({dialogs:[...document.querySelectorAll('[role="dialog"]')].filter(x=>getComputedStyle(x).display!=='none').length, active:document.activeElement?.innerText, activeId:document.activeElement?.id})''')
    results.append({'interaction':{'action_text':action_text,'focus_before':focus_before,'open':open_state,'close':close_state}})
    # inspect all currently rendered copy and mutating methods
    results.append({'console':console,'failed':failed,'requests':[x for x in methods if x['method']!='GET']})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    await browser.close()

asyncio.run(main())
