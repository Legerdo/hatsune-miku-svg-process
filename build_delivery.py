"""Package only verified delivery files, sources and actual drawing checkpoints."""
from pathlib import Path
import hashlib
import html
import json
import shutil
import zipfile
from PIL import Image,ImageDraw,ImageFont

root=Path(__file__).resolve().parent
out=root/'output'
required=['hatsune-miku.svg','hatsune-miku.png','miku-drawing-player.html','hatsune-miku-process.mp4','hatsune-miku-process.report.json','validation.json','player-verification.json','video-verification.json']
for name in required:
    if not (out/name).is_file():raise SystemExit(f'Missing required delivery artifact: {name}')
validation=json.loads((out/'validation.json').read_text('utf-8'))
player=json.loads((out/'player-verification.json').read_text('utf-8'))
video=json.loads((out/'hatsune-miku-process.report.json').read_text('utf-8'))
video_pixels=json.loads((out/'video-verification.json').read_text('utf-8'))
if not all(v['status']=='PASS' for v in [validation,player,video,video_pixels]):raise SystemExit('A delivery gate has not passed.')
if video['sample']:raise SystemExit('A video sample is not the complete process.')
if 'video' not in validation:raise SystemExit('Final video has not been independently validated.')

def sha(file):
    with file.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

if player['html_sha256']!=sha(out/'miku-drawing-player.html'):raise SystemExit('Player QA is stale.')
if validation['files']['hatsune-miku-process.mp4']['sha256']!=sha(out/'hatsune-miku-process.mp4'):raise SystemExit('Video QA is stale.')
session=json.loads((root/'recording/session.json').read_text('utf-8'))
if video['session_sha256']!=sha(root/'recording/session.json'):raise SystemExit('Recorded session differs from final session.')

# A contact sheet uses the actual reviewed checkpoints, not regenerated stages.
labels={1:'비례 스케치',3:'큰 색면',6:'명암과 구조',8:'얼굴과 의상',10:'머리카락',12:'전체 점검·완성'}
font=ImageFont.truetype(r'C:\Windows\Fonts\malgun.ttf',26)
small=ImageFont.truetype(r'C:\Windows\Fonts\malgun.ttf',18)
sheet=Image.new('RGB',(1440,1570),'#f5f5f2')
draw=ImageDraw.Draw(sheet)
for i,(bid,label) in enumerate(labels.items()):
    batch=next(b for b in session['batches'] if b['id']==bid)
    im=Image.open(root/batch['checkpoint']).convert('RGB')
    im.thumbnail((416,660),Image.Resampling.LANCZOS)
    x=(i%3)*480;y=(i//3)*760
    draw.rounded_rectangle((x+16,y+16,x+464,y+744),radius=14,fill='white')
    sheet.paste(im,(x+(480-im.width)//2,y+63+(660-im.height)//2))
    draw.text((x+36,y+27),f'{bid:02d}  {label}',font=font,fill='#264f55')
draw.text((30,1534),'KEI · Hatsune Miku © Crypton Future Media, INC. 2007 · CC BY-NC 3.0',font=small,fill='#627779')
sheet.save(out/'process-overview.jpg',quality=93,subsampling=0)
shutil.copyfile(root/'recording/prime-qa/player-292.png',out/'process-poster.png')
shutil.copyfile(root/'README.md',out/'README.md')
seconds=float(validation['video']['format']['duration'])
minute,second=divmod(round(seconds),60)
duration=f'{minute}분 {second:02d}초'

landing='''<!doctype html>
<html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>하츠네 미쿠 · SVG와 제작 과정</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f4ef;color:#243e44;font:16px/1.75 "Malgun Gothic","Segoe UI",sans-serif}main{max-width:1200px;margin:50px auto;padding:0 28px}header{letter-spacing:.15em;font-size:12px;color:#5c817f}h1{font-size:42px;line-height:1.3;letter-spacing:-.04em;margin:22px 0}h2{font-size:24px}p{max-width:760px}.hero{display:grid;grid-template-columns:400px 1fr;gap:60px;align-items:center;margin:36px 0 64px}.art{background:white;border-radius:16px;padding:18px;text-align:center}.art img{height:640px;max-width:100%;object-fit:contain}.meta{color:#53747b}.links{display:flex;flex-wrap:wrap;gap:12px;margin:26px 0}.links a{background:#245d62;color:white;padding:13px 20px;border-radius:7px;text-decoration:none}.links a.secondary{background:#e1eae6;color:#24545a}.small{font-size:14px;color:#687e81}video{display:block;width:100%;border-radius:12px;background:white}.overview{width:100%;display:block;border-radius:12px}section{margin:58px 0}footer{padding:28px 0;border-top:1px solid #d2deda;font-size:13px;color:#62797d}a{color:#216f74}code{font-family:Consolas,monospace}details{margin:24px 0}summary{cursor:pointer}@media(max-width:820px){.hero{grid-template-columns:1fr;gap:24px}.art img{height:500px}main{margin-top:28px}h1{font-size:32px}}
</style><main>
<header>VECTOR STUDY / KEI · HATSUNE MIKU</header>
<div class="hero"><div class="art"><img src="hatsune-miku.png" alt="완성한 하츠네 미쿠 전신 SVG의 미리보기"></div><div>
<h1>하츠네 미쿠<br>SVG와 전체 제작 과정</h1>
<p class="meta">1,600개 벡터 패스 · 12개 제작 배치 · __DURATION__ 전체 영상</p>
<p>비례 스케치에서 시작해 큰 색면, 명암, 구조와 세부 묘사를 거쳐 완성하는 과정을 담았습니다. 각 배치의 렌더링 화면을 확인한 후 다음 작업을 결정했습니다.</p>
<div class="links"><a href="miku-drawing-player.html">제작 과정 재생기 열기</a><a class="secondary" href="hatsune-miku-complete.zip" download>전체 파일 ZIP</a></div>
<div class="links"><a class="secondary" href="hatsune-miku.svg" download>SVG 원본</a><a class="secondary" href="hatsune-miku-process.mp4" download>MP4 영상</a><a class="secondary" href="hatsune-miku.png" download>PNG 미리보기</a></div>
<p class="small">HTML 재생기는 파일 하나로 오프라인 실행됩니다. 구간 탐색, 속도 조절, 단계 선택, 얼굴·소매 확대를 지원합니다.</p>
</div></div>
<section><h2>전체 과정 영상</h2><p class="small">1920×1080 · H.264 · 24fps · __DURATION__ · 무음</p><video controls preload="metadata" poster="process-poster.png"><source src="hatsune-miku-process.mp4" type="video/mp4"></video></section>
<section><h2>실제로 확인한 제작 단계</h2><img class="overview" src="process-overview.jpg" alt="비례 스케치, 큰 색면, 명암과 구조, 얼굴과 의상, 머리카락, 전체 점검과 완성의 실제 체크포인트"></section>
<details><summary>요소 수와 검증 기록</summary><p>최종 SVG에는 정확히 1,600개의 실제 <code>&lt;path&gt;</code>가 있습니다. 스케치 71획과 밑칠 722개는 제작 과정에만 포함됩니다. 전체 재생 동작은 2,393개입니다. 같은 색의 가까운 하위 윤곽을 하나의 복합 패스로 묶었으며, 비트맵을 삽입하거나 숨긴 요소로 수량을 채우지 않았습니다.</p><p>이 영상은 작업 중 보존한 SVG 배치를 바탕으로 만든 드로잉 시뮬레이션을 실제 브라우저에서 녹화한 것입니다.</p><p><a href="validation.json">SVG·영상 검증</a> · <a href="player-verification.json">재생기 검증</a> · <a href="hatsune-miku-process.report.json">녹화 기록</a> · <a href="README.md">제작·재현 문서</a> · <a href="manifest.json">파일 해시</a></p></details>
<footer>Original illustration: KEI · Hatsune Miku © Crypton Future Media, INC. 2007<br>Vector adaptation and recorded process simulation · <a href="https://piapro.net/intl/en_character.html">Piapro 공식 원본</a> · <a href="https://creativecommons.org/licenses/by-nc/3.0/">CC BY-NC 3.0</a></footer>
</main></html>'''.replace('__DURATION__',html.escape(duration))
(out/'index.html').write_text(landing,encoding='utf-8')
manifest={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.iterdir()) if p.is_file() and p.suffix not in {'.zip'} and p.name not in {'manifest.json','delivery-receipt.json'}}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
sources=['README.md','studio.py','palette_paint.py','build_player.py','player-template.html','record_video.py','validate_artifacts.py','verify_player.py','verify_video.py','build_delivery.py']
include=[root/p for p in sources]
include += [p for p in out.iterdir() if p.is_file() and p.suffix!='.zip' and p.name!='delivery-receipt.json']
include += [root/'reference/miku-kei-original.png',root/'reference/source.json',root/'recording/session.json']
include += [root/b[k] for b in session['batches'] for k in ['checkpoint','vector_file']]
include += list((root/'recording/prime-qa').glob('player-*.png'))+[root/'recording/prime-qa/player-verification.json']
archive=out/'hatsune-miku-complete.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for file in sorted(set(include)):
        z.write(file,file.relative_to(root).as_posix())
with zipfile.ZipFile(archive) as z:
    bad=z.testzip()
    if bad:raise SystemExit(f'Archive CRC failure: {bad}')
    count=len(z.infolist())
receipt={'status':'PASS','workspace':str(root),'index':'http://127.0.0.1:8789/','archive':str(archive),'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'archive_files':count,'video_seconds':seconds,'final_svg_paths':1600,'drawing_operations':2393}
(out/'delivery-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=True,indent=2))
