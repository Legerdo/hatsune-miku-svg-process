"""Independent offline browser controls and vector-frame checks for delivery."""
from pathlib import Path
import base64
import hashlib
import json
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from studio import browser_exe

root=Path(__file__).resolve().parent
destination=root/'recording/prime-qa'
destination.mkdir(exist_ok=True)
source=root/'output/miku-drawing-player.html'
session=json.loads((root/'recording/session.json').read_text('utf-8'))
errors=[]; external=[]; checks={}; frames=[]

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=browser_exe())
    try:
        page=browser.new_page(viewport={'width':1920,'height':1200},device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:external.append(request.url) if request.url.startswith(('https:','http:')) else None)
        page.goto(source.as_uri(),wait_until='load',timeout=120000)
        page.wait_for_function('window.__mikuStudio?.ready===true',timeout=120000)
        initial=page.evaluate('window.__mikuStudio.getState()')
        checks['session_sha_matches_source']=initial['sessionSha256']==hashlib.sha256((root/'recording/session.json').read_bytes()).hexdigest()
        checks['all_final_paths_loaded']=initial['paths']==len(session['paths'])==1600
        checks['all_underpainting_loaded']=initial['underpainting']==len(session['underpainting'])==722
        checks['all_sketch_strokes_loaded']=initial['strokes']==len(session['strokes'])==71
        page.get_by_role('button',name='재생 또는 일시정지',exact=True).click()
        page.wait_for_timeout(350)
        running=page.evaluate('window.__mikuStudio.getState()')
        checks['real_play_button_advances_time']=running['playing'] and running['time']>0
        page.get_by_role('button',name='재생 또는 일시정지',exact=True).click()
        paused=page.evaluate('window.__mikuStudio.getState()')
        page.wait_for_timeout(180)
        later=page.evaluate('window.__mikuStudio.getState()')
        checks['real_pause_button_stops_time']=not later['playing'] and abs(later['time']-paused['time'])<.01
        page.get_by_role('combobox',name='재생 속도',exact=True).select_option('2')
        checks['speed_control']=page.evaluate('window.__mikuStudio.getState().speed')==2
        page.get_by_role('combobox',name='제작 단계 선택',exact=True).select_option('10')
        chosen=page.evaluate('window.__mikuStudio.getState()')
        checks['stage_selection_seeks_to_boots']=chosen['stageIndex']==10 and chosen['completedFinalPaths']>=1287
        checks['stage_title_is_korean']='부츠' in chosen['currentStage']
        page.get_by_role('button',name='얼굴',exact=True).click()
        checks['face_zoom_button']=page.evaluate('window.__mikuStudio.getState().focus')=='face'
        page.get_by_role('button',name='소매',exact=True).click()
        checks['sleeve_zoom_button']=page.evaluate('window.__mikuStudio.getState().focus')=='sleeve'
        page.get_by_role('button',name='전체',exact=True).click()
        slider=page.get_by_role('slider',name='제작 과정 탐색',exact=True)
        slider.focus();slider.press('End')
        end=page.evaluate('window.__mikuStudio.getState()')
        checks['keyboard_scrub_reaches_end']=abs(end['time']-end['duration'])<.01
        checks['all_2393_drawing_operations_complete']=end['completedSketch']+end['completedUnderpainting']+end['completedFinalPaths']==2393
        checks['underpainting_removed_at_finish']=end['underpaintingAlpha']==0
        chapters=page.evaluate('window.__mikuPlayer.chapters')
        checks['all_12_batches_and_final_hold']=len(chapters)==13
        checks['cleanup_lasts_two_seconds']=any(c['kind']=='clean' and abs(c['end']-c['start']-2)<.001 for c in chapters)
        for t in [0,7,22,55,100,160,220,270,292]:
            state=page.evaluate('(t)=>{window.__mikuStudio.seek(t);return window.__mikuStudio.getState()}',t)
            encoded=page.evaluate('window.__mikuStudio.dataURL()').split(',',1)[1]
            file=destination/f'player-{t:03d}.png'
            file.write_bytes(base64.b64decode(encoded))
            frames.append({'time':t,'file':str(file.relative_to(root)),'state':state})
        page.screenshot(path=str(destination/'player-controls-final.png'),full_page=True)
        checks['no_browser_exceptions']=not errors
        checks['offline_without_network_requests']=not external
    finally:
        browser.close()

final=np.array(Image.open(destination/'player-292.png').convert('RGB'))
blank=np.array(Image.open(destination/'player-000.png').convert('RGB'))
checks['drawing_is_not_blank']=float(np.mean(np.abs(final[127:934,233:764].astype(float)-blank[127:934,233:764])))>15
reference=Image.open(root/'output/hatsune-miku.png').convert('RGB')
expected=np.array(reference.resize((531,807),Image.Resampling.LANCZOS),dtype=float)
actual=final[127:934,233:764].astype(float)
mae=float(np.mean(np.abs(expected-actual)))
report={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'html_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'duration_seconds':initial['duration'],'canvas_size':[1920,1080],'render_comparison':{'method':'Completed player art crop against separately Chromium-rendered final SVG PNG at matched dimensions; subpixel registration and Canvas antialiasing may differ. Descriptive comparison.','mean_absolute_error':mae},'browser_errors':errors,'external_requests':external,'chapters':chapters,'frames':frames}
(destination/'player-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'output/player-verification.json').write_text(json.dumps({k:v for k,v in report.items() if k!='frames'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in {'frames','chapters'}},ensure_ascii=True,indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
