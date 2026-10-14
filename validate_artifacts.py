"""Read-only delivery checks. Never rewrites artwork, thresholds, or recordings."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--video',type=Path)
    args=parser.parse_args()
    svg_path=ROOT/'output/hatsune-miku.svg'
    session=json.loads((ROOT/'recording/session.json').read_text('utf-8'))
    tree=ET.parse(svg_path)
    tags=lambda e:e.tag.rsplit('}',1)[-1]
    drawing_tags={'path','rect','circle','ellipse','line','polyline','polygon','image','use','text'}
    drawings=[e for e in tree.iter() if tags(e) in drawing_tags]
    paths=[e for e in drawings if tags(e)=='path']
    checks={
        'svg_xml_parses':True,
        'drawing_elements_exactly_1600':len(drawings)==1600,
        'all_drawing_elements_are_paths':len(paths)==len(drawings),
        'final_session_count_matches':len(session['paths'])==1600,
        'unique_path_ids':len({p.get('id') for p in paths})==1600,
        'final_ids_match_session':{p.get('id') for p in paths}=={p['id'] for p in session['paths']},
        'no_embedded_or_external_raster':not any(tags(e) in {'image','foreignObject','use'} for e in tree.iter()),
        'no_scripts':not any(tags(e)=='script' for e in tree.iter()),
        'no_external_resource_attributes':not any(k.rsplit('}',1)[-1] in {'href','src'} for e in tree.iter() for k in e.attrib),
        'nonempty_finite_geometry':all(p.get('d') and not re.search(r'NaN|Infinity',p.get('d')) for p in paths),
        'no_hidden_padding_paths':all(p.get('display')!='none' and p.get('visibility')!='hidden' and float(p.get('opacity','1'))>0 for p in paths),
        'underpainting_not_in_final_svg':not any(p.get('id','').startswith(('u','s')) for p in paths),
        'source_sha256_matches_selected_original':sha(ROOT/'reference/miku-kei-original.png')=='24346813e53347219795a1ec515b5ceeffd28329af368c97a4ee556a7b93ba22',
        'all_reviewed_checkpoints_exist':all((ROOT/b['checkpoint']).is_file() and (ROOT/b['vector_file']).is_file() for b in session['batches']),
        'overall_finish_recorded':session.get('finish_underpainting') is True,
    }
    original=Image.open(ROOT/'reference/miku-kei-original.png').convert('RGBA')
    reference=Image.new('RGBA',original.size,'white'); reference.alpha_composite(original)
    final=Image.open(ROOT/'output/hatsune-miku.png').convert('RGB')
    reduced=final.resize(original.size,Image.Resampling.LANCZOS)
    a=np.asarray(reference.convert('RGB'),dtype=float); b=np.asarray(reduced,dtype=float)
    fg=np.asarray(original)[:,:,3]>90
    mse=float(np.mean((a[fg]-b[fg])**2))
    report={
        'checks':checks,
        'source_dimensions':list(original.size),
        'png_dimensions':list(final.size),
        'svg_viewbox':tree.getroot().get('viewBox'),
        'final_drawing_elements':len(drawings),
        'transient_sketch_strokes':len(session['strokes']),
        'transient_underpainting_operations':len(session.get('underpainting',[])),
        'recorded_batches':len(session['batches']),
        'total_replay_drawing_operations':len(session['paths'])+len(session.get('underpainting',[]))+len(session['strokes']),
        'source_color_components_preserved':sum(p.get('component_count',0) for p in session['paths']),
        'render_comparison':{'method':'Chromium-rendered final PNG, downsampled to source resolution; foreground alpha > 90 only. Descriptive comparison, not an acceptance threshold.','mse':mse,'psnr_db':10*math.log10(255**2/max(mse,1e-12)),'mae':float(np.mean(np.abs(a[fg]-b[fg])))},
        'files':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in [svg_path,ROOT/'output/hatsune-miku.png',ROOT/'recording/session.json']},
    }
    if args.video:
        video=args.video if args.video.is_absolute() else ROOT/args.video
        proc=subprocess.run(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=codec_name,width,height,r_frame_rate,nb_frames,nb_read_frames,duration:format=duration,size','-of','json',str(video)],capture_output=True,text=True,check=True)
        probe=json.loads(proc.stdout); stream=probe['streams'][0]
        duration=float(probe['format']['duration'])
        checks['video_h264']=stream['codec_name']=='h264'
        checks['video_full_hd']=stream['width']==1920 and stream['height']==1080
        checks['video_has_decodable_frames']=int(stream.get('nb_read_frames',0))>0
        checks['video_contains_full_length_timeline']=duration>=240
        report['video']=probe
        report['files'][video.name]={'bytes':video.stat().st_size,'sha256':sha(video)}
    report['status']='PASS' if all(checks.values()) else 'FAIL'
    (ROOT/'output/validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))
    raise SystemExit(0 if report['status']=='PASS' else 1)

if __name__=='__main__':main()
