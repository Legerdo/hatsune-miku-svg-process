"""Precision color-boundary passes, applied only after reviewing the preceding screen.

The source is an indexed-color original. All its foreground color components are
converted into curves. Nearby same-color components share a brush path; spatial
partitioning controls the final SVG element budget without discarding small marks.
The earlier underpainting stays in the replay, but is not counted in the final SVG.
"""
from __future__ import annotations
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import studio

ROOT = studio.ROOT
W, H = studio.W, studio.H
REGIONS = ['head', 'body', 'left-hair', 'right-hair', 'legs']

def region_map():
    yy, xx = np.mgrid[:H, :W]
    regions = np.where(xx < 260, 2, 3).astype(np.uint8)
    body = np.array([(205,140),(309,140),(322,280),(350,444),(280,447),(219,422),(184,425),(122,439),(84,421),(81,375),(129,286),(167,220),(188,172)], np.int32)
    cv2.fillPoly(regions, [body], 1)
    legs = [np.array([(119,415),(181,421),(168,556),(153,614),(154,790),(96,790),(103,675),(116,557)],np.int32),
            np.array([(215,417),(277,414),(307,565),(360,698),(371,790),(301,790),(307,715),(255,597)],np.int32)]
    cv2.fillPoly(regions, legs, 4)
    regions[(yy < 150) & (xx > 178) & (xx < 330)] = 0
    return regions

def to_curves(mask, origin):
    # Upsampling traces pixel cells, not merely their centers. The small same-color
    # edge stroke closes the subpixel gap between adjacent palette regions.
    factor = 3
    enlarged = cv2.resize(mask, None, fx=factor, fy=factor, interpolation=cv2.INTER_NEAREST)
    contours, _ = cv2.findContours(enlarged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    paths = []; polygons = []
    for c in contours:
        p = (cv2.approxPolyDP(c, .35, True).reshape(-1,2).astype(float)+.5)/factor + origin
        if len(p) < 3: continue
        polygons.append(p.round(4).tolist())
        before = []; after = []
        for i,v in enumerate(p):
            a=p[i-1]-v; b=p[(i+1)%len(p)]-v
            la=np.linalg.norm(a); lb=np.linalg.norm(b)
            r=min(.10,la*.19,lb*.19)
            before.append(v+a*(r/max(la,.001)))
            after.append(v+b*(r/max(lb,.001)))
        d=f'M{after[-1][0]:.3f},{after[-1][1]:.3f}'
        for v,a,b in zip(p,before,after):
            d+=f'L{a[0]:.3f},{a[1]:.3f}Q{v[0]:.3f},{v[1]:.3f} {b[0]:.3f},{b[1]:.3f}'
        paths.append(d+'Z')
    return ''.join(paths),polygons

def split_spatial(components, target):
    buckets=[components]
    while len(buckets)<target:
        eligible=[(i,b) for i,b in enumerate(buckets) if len(b)>1]
        if not eligible: break
        def score(ib):
            b=ib[1]; pts=np.array([c['center'] for c in b])
            spread=np.ptp(pts,axis=0)
            return float((spread.max()+2)*math.sqrt(len(b)))
        index, chosen=max(eligible,key=score)
        pts=np.array([c['center'] for c in chosen])
        axis=int(np.argmax(np.ptp(pts,axis=0)))
        chosen=sorted(chosen,key=lambda c:(c['center'][axis],-c['area']))
        split=max(1,min(len(chosen)-1,len(chosen)//2))
        buckets[index]=chosen[:split]
        buckets.append(chosen[split:])
    return buckets

def prepare(args):
    inv_path=ROOT/'recording/palette-inventory.json'
    if inv_path.exists(): raise SystemExit('Inventory already exists; do not overwrite reviewed geometry.')
    im=Image.open(ROOT/'reference/miku-kei-original.png')
    if im.mode != 'P': raise SystemExit('This precision pass expects the selected indexed-color source.')
    labels=np.array(im)
    rgba=np.array(im.convert('RGBA'))
    regions=region_map()
    groups=defaultdict(list)
    for region_index, region in enumerate(REGIONS):
        for palette_index in np.unique(labels[studio.FG]):
            mask=((labels==palette_index)&(regions==region_index)&studio.FG).astype(np.uint8)
            if not mask.any(): continue
            n, cc, stats, centers=cv2.connectedComponentsWithStats(mask,8)
            for ci in range(1,n):
                x,y,w,h,area=map(int,stats[ci])
                if area<1: continue
                crop=(cc[y:y+h,x:x+w]==ci).astype(np.uint8)
                d, polygons=to_curves(crop,np.array([x,y]))
                if not d: continue
                iy,ix=np.argwhere(crop)[0]
                color=studio.TARGET[y+iy,x+ix].tolist()
                groups[(region,int(palette_index))].append({'d':d,'polygons':polygons,'area':area,'center':centers[ci].tolist(),'rgb':color})
        print(f'Prepared region: {region}',flush=True)
    if len(groups)>args.count: raise SystemExit(f'{len(groups)} color-region groups exceed budget {args.count}.')
    keys=sorted(groups)
    allocation={k:1 for k in keys}
    weights={k:sum(math.sqrt(c['area']) for c in groups[k])*(1.25 if k[0]=='head' else 1) for k in keys}
    remaining=args.count-len(keys)
    while remaining:
        possible=[k for k in keys if allocation[k]<len(groups[k])]
        if not possible: raise SystemExit('Fewer real components than requested drawing elements.')
        chosen=max(possible,key=lambda k:weights[k]/(allocation[k]+.6))
        allocation[chosen]+=1; remaining-=1
    inventory=[]
    for key in keys:
        for cluster in split_spatial(groups[key],allocation[key]):
            polygons=[p for c in cluster for p in c['polygons']]
            inventory.append({'d':''.join(c['d'] for c in cluster),'polygons':polygons,'rgb':cluster[0]['rgb'],
                'area':sum(c['area'] for c in cluster),'bounds':studio.bounds_of([np.array(p) for p in polygons]),
                'region':key[0],'palette_index':key[1],'component_count':len(cluster),'stroke_width':.36,
                'precision':True})
    assert len(inventory)==args.count
    inventory.sort(key=lambda p:(REGIONS.index(p['region']), np.mean(p['rgb'])<82, -p['area'], p['bounds'][1],p['bounds'][0]))
    for i,p in enumerate(inventory):p['inventory_id']=i
    inv_path.write_text(json.dumps(inventory,separators=(',',':')),encoding='utf-8')
    data=studio.load()
    if data.get('underpainting'): raise SystemExit('Underpainting was already separated.')
    data['underpainting']=data['paths']
    for i,p in enumerate(data['underpainting']):
        p['id']=f'u{i+1:04d}'; p['transient']=True
    data['paths']=[]
    data['final_target_count']=args.count
    data['precision_method']='Original indexed colors; spatially grouped curved component boundaries, no raster embedding.'
    studio.save(data)
    counts={r:sum(p['region']==r for p in inventory) for r in REGIONS}
    print(json.dumps({'final_inventory_paths':len(inventory),'palette_region_groups':len(groups),'source_components':sum(len(v) for v in groups.values()),'counts':counts,'underpainting_operations':len(data['underpainting'])}))

def paint(args):
    data=studio.load()
    inventory=json.loads((ROOT/'recording/palette-inventory.json').read_text('utf-8'))
    used={p['inventory_id'] for p in data['paths']}
    eligible=[p for p in inventory if p['inventory_id'] not in used and p['region']==args.region]
    if args.n: eligible=eligible[:args.n]
    if not eligible: raise SystemExit('No unpainted elements in the requested region.')
    if len(data['paths'])+len(eligible)>1700: raise SystemExit('Final path count would exceed 1700.')
    bid=studio.batch(data,args.title,args.note)
    data['batches'][-1]['region']=args.region
    for p in eligible:
        p['id']=f'p{len(data["paths"])+1:04d}'; p['batch']=bid
        data['paths'].append(p)
    studio.checkpoint(data,args.title,args.note)
    print(f'Precision paths added: {len(eligible)}; final paths so far: {len(data["paths"])}')

def finish(args):
    data=studio.load()
    if len(data['paths'])!=data.get('final_target_count',1600): raise SystemExit('Final path inventory is not complete.')
    studio.batch(data,'overall-check-and-finish',args.note)
    data['finish_underpainting']=True
    studio.checkpoint(data,'overall-check-and-finish',args.note)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','paint','finish'])
    parser.add_argument('--count',type=int,default=1600)
    parser.add_argument('--region',choices=REGIONS)
    parser.add_argument('--n',type=int,default=0)
    parser.add_argument('--title',default='precision-pass')
    parser.add_argument('--note',default='')
    args=parser.parse_args()
    if args.action=='prepare':prepare(args)
    elif args.action=='paint':paint(args)
    else:finish(args)
