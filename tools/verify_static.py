"""Verify committed public assets without regenerating the reviewed artwork.

Uses Python's standard library only, on Windows or a GitHub-hosted Linux runner.
The deep local rendering/decoding evidence is supplied with the immutable assets.
"""
from __future__ import annotations
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote,urlsplit
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'output'

def require(condition:bool,message:str)->None:
    if not condition:raise SystemExit('FAIL: '+message)

def digest(path:Path)->str:
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

class AssetLinks(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in {'href','src','poster'} and value:self.links.append(value)

def main()->None:
    required=['index.html','hatsune-miku.svg','hatsune-miku.png','miku-drawing-player.html','hatsune-miku-process.mp4','hatsune-miku-complete.zip','manifest.json','validation.json','player-verification.json','video-verification.json','hatsune-miku-process.report.json']
    for name in required:require((SITE/name).is_file(),'Missing '+name)
    manifest=json.loads((SITE/'manifest.json').read_text('utf-8'))
    for name,record in manifest.items():
        path=(SITE/name).resolve()
        require(path.is_relative_to(SITE.resolve()),'Manifest path leaves output: '+name)
        require(path.is_file(),'Missing manifest asset: '+name)
        require(path.stat().st_size==record['bytes'],'Size mismatch: '+name)
        require(digest(path)==record['sha256'],'SHA-256 mismatch: '+name)
    tree=ET.parse(SITE/'hatsune-miku.svg')
    tag=lambda node:node.tag.rsplit('}',1)[-1]
    drawable={'path','rect','circle','ellipse','line','polyline','polygon','image','use','text'}
    paths=[node for node in tree.iter() if tag(node) in drawable]
    require(len(paths)==1600 and all(tag(p)=='path' for p in paths),'Expected exactly 1600 drawable paths')
    require(len({p.get('id') for p in paths})==1600,'Path IDs are not unique')
    for node in tree.iter():
        require(tag(node) not in {'image','use','foreignObject','script','style'},'Unexpected embedded content')
        require(not any(k.rsplit('}',1)[-1] in {'href','src'} for k in node.attrib),'External SVG resource')
        require(node.get('display')!='none' and node.get('visibility')!='hidden','Hidden SVG content')
        require(float(node.get('opacity','1'))>0,'Invisible SVG content')
    require(all(p.get('d') and not re.search('NaN|Infinity',p.get('d')) for p in paths),'Invalid path geometry')
    session=ROOT/'recording/session.json'
    data=json.loads(session.read_text('utf-8'))
    require((len(data['paths']),len(data['strokes']),len(data['underpainting']))==(1600,71,722),'Unexpected recording element counts')
    source=ROOT/'reference/miku-kei-original.png'
    require(digest(source)=='24346813e53347219795a1ec515b5ceeffd28329af368c97a4ee556a7b93ba22','Selected reference changed')
    player=json.loads((SITE/'player-verification.json').read_text('utf-8'))
    video=json.loads((SITE/'video-verification.json').read_text('utf-8'))
    record=json.loads((SITE/'hatsune-miku-process.report.json').read_text('utf-8'))
    validate=json.loads((SITE/'validation.json').read_text('utf-8'))
    require(all(r['status']=='PASS' for r in [player,video,record,validate]),'A recorded verification failed')
    require(player['html_sha256']==digest(SITE/'miku-drawing-player.html'),'Player verification is stale')
    require(video['video_sha256']==digest(SITE/'hatsune-miku-process.mp4'),'Video verification is stale')
    require(record['session_sha256']==digest(session),'Recording uses another session')
    require(not record['sample'] and record['final_state']['completedFinalPaths']==1600,'Incomplete recording')
    require(record['final_state']['underpaintingAlpha']==0,'Underpainting remains at finish')
    require(video['decoded_frame_count']==7008 and video['duration_seconds']==292,'Incorrect recorded duration')
    for name in ['index.html','miku-drawing-player.html']:
        parser=AssetLinks();parser.feed((SITE/name).read_text('utf-8'))
        for link in parser.links:
            parts=urlsplit(link)
            if parts.scheme or parts.netloc or not parts.path:continue
            asset=(SITE/unquote(parts.path)).resolve()
            require(asset.is_relative_to(SITE.resolve()) and asset.is_file(),'Broken local link: '+link)
    with zipfile.ZipFile(SITE/'hatsune-miku-complete.zip') as archive:
        require(archive.testzip() is None,'Archive CRC failure')
        require('output/hatsune-miku.svg' in archive.namelist(),'Archive lacks SVG')
        require('output/hatsune-miku-process.mp4' in archive.namelist(),'Archive lacks complete MP4')
    # Only task-owned source and reports are published. Catch common credentials
    # accidentally added later; never print matching secret text.
    secret=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    for path in ROOT.rglob('*'):
        if not path.is_file() or '.git' in path.parts:continue
        require(path.stat().st_size<100*1024*1024,'File exceeds GitHub limit: '+str(path.relative_to(ROOT)))
        require(path.name not in {'.env','.env.local','id_rsa','id_ed25519'},'Unexpected private file name')
        if path.suffix in {'.py','.md','.json','.html','.yml','.yaml','.toml'}:
            require(not secret.search(path.read_bytes()),'Credential pattern in '+str(path.relative_to(ROOT)))
    print(json.dumps({'status':'PASS','svg_paths':1600,'sketch_strokes':71,'underpainting_paths':722,'recorded_frames':7008,'video_seconds':292,'manifest_assets':len(manifest),'local_links':'PASS','archive_crc':'PASS'},indent=2))

if __name__=='__main__':main()
