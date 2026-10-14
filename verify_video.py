"""Decode the delivered MP4 independently and compare its final art with the player."""
from pathlib import Path
import hashlib,json,subprocess
import cv2
import numpy as np
from PIL import Image

root=Path(__file__).resolve().parent
video=root/'output/hatsune-miku-process.mp4'
qa=root/'recording/prime-qa'
if not video.is_file():raise SystemExit('The complete MP4 does not exist yet.')
decode=subprocess.run(['ffmpeg','-hide_banner','-v','error','-i',str(video),'-f','null','-'],capture_output=True,text=True)
cap=cv2.VideoCapture(str(video))
if not cap.isOpened():raise SystemExit('OpenCV could not decode the MP4.')
count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS)
width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
duration=count/fps
samples=[]
try:
    for t in [0,7,22,55,100,160,220,270,duration-1/fps]:
        index=min(count-1,max(0,round(t*fps)))
        cap.set(cv2.CAP_PROP_POS_FRAMES,index)
        ok,bgr=cap.read()
        if not ok:raise RuntimeError(f'Unable to decode frame {index}')
        rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
        file=qa/f'video-frame-{index:05d}.png'
        Image.fromarray(rgb).save(file)
        samples.append({'frame':index,'seconds':index/fps,'file':str(file.relative_to(root)),'art_mean_rgb':rgb[127:934,233:764].mean(axis=(0,1)).round(4).tolist()})
        if index==count-1:final=rgb
        if index==0:first=rgb
finally:
    cap.release()
expected=np.array(Image.open(qa/'player-292.png').convert('RGB'),dtype=float)
actual=final.astype(float)
error=np.abs(actual[127:934,233:764]-expected[127:934,233:764])
mae=float(error.mean())
with video.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
checks={
    'full_stream_decodes_without_error':decode.returncode==0 and not decode.stderr.strip(),
    'full_hd_1920x1080':(width,height)==(1920,1080),
    'frame_rate_24':abs(fps-24)<.001,
    'full_292_second_timeline':abs(duration-292)<.65,
    'all_requested_sample_frames_decode':len(samples)==9,
    'final_art_matches_separate_player_render':mae<3.0,
    'final_frame_is_not_initial_blank':float(np.mean(np.abs(final[127:934,233:764].astype(float)-first[127:934,233:764])))>15,
}
report={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'video_sha256':sha,'dimensions':[width,height],'fps':fps,'decoded_frame_count':count,'duration_seconds':duration,'full_stream_decoder_exit':decode.returncode,'full_stream_decoder_errors':decode.stderr,'final_art_comparison':{'reference':'Independently rendered completed HTML player, recording/prime-qa/player-292.png','mean_absolute_error':mae,'acceptance_mean_absolute_error_below':3.0,'pixel_range':[0,255]},'sample_frames':samples}
(root/'output/video-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
