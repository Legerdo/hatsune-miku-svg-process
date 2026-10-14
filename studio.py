"""Checkpointed vector painting. Python 3.10+, OpenCV, NumPy, SciPy, Pillow, Playwright.
Each refine command is a separately reviewed batch. SVGs contain no embedded raster.
"""
from __future__ import annotations
import argparse, html, json, math, time, urllib.request
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent
W, H = 519, 791
URL = 'https://piapro.net/intl/images/ch_img_miku.png'
cv2.setNumThreads(1)
cv2.setRNGSeed(28379)
for folder in ['reference', 'checkpoints', 'output', 'recording']:
    (ROOT / folder).mkdir(exist_ok=True)

def load_reference():
    path = ROOT / 'reference/miku-kei-original.png'
    if not path.exists():
        urllib.request.urlretrieve(URL, path)
    im = np.array(Image.open(path).convert('RGBA'))
    alpha = im[:, :, 3].astype(np.float32) / 255
    rgb = np.rint(im[:, :, :3] * alpha[:, :, None] + 255 * (1-alpha[:, :, None])).astype(np.uint8)
    Image.fromarray(rgb).save(ROOT / 'reference/reference-on-white.png')
    return rgb, im[:, :, 3] > 90

TARGET, FG = load_reference()

def load():
    p = ROOT / 'recording/session.json'
    return json.loads(p.read_text('utf-8')) if p.exists() else {'width': W, 'height': H, 'source': URL, 'strokes': [], 'paths': [], 'batches': []}

def save(data):
    (ROOT / 'recording/session.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

def bounds_of(contours):
    pts = np.vstack(contours).reshape(-1, 2)
    return [round(float(pts[:, 0].min()), 2), round(float(pts[:, 1].min()), 2), round(float(pts[:, 0].max()), 2), round(float(pts[:, 1].max()), 2)]

def contour_path(contours, epsilon=.55):
    curves = []; polygons = []
    for c in contours:
        p = cv2.approxPolyDP(c, epsilon, True).reshape(-1, 2).astype(float)
        if len(p) < 3:
            continue
        polygons.append(p.tolist())
        before = []; after = []
        for i, v in enumerate(p):
            a = p[i-1] - v; b = p[(i+1) % len(p)] - v
            la = np.linalg.norm(a); lb = np.linalg.norm(b)
            r = min(.48, la*.22, lb*.22)
            before.append(v+a*(r/max(la, .001))); after.append(v+b*(r/max(lb, .001)))
        s = f'M{after[-1][0]:.2f},{after[-1][1]:.2f}'
        for v, a, b in zip(p, before, after):
            s += f'L{a[0]:.2f},{a[1]:.2f}Q{v[0]:.2f},{v[1]:.2f} {b[0]:.2f},{b[1]:.2f}'
        curves.append(s+'Z')
    return ''.join(curves), polygons

def render_paths(paths, scale=1):
    canvas = np.full((H*scale, W*scale, 3), 255, np.uint8)
    for p in paths:
        polys = [np.rint(np.array(c)*scale).astype(np.int32) for c in p['polygons']]
        cv2.fillPoly(canvas, polys, p['rgb'], lineType=cv2.LINE_AA)
    return canvas

def svg_text(data, sketch=True):
    paints = data['paths']
    if sketch and not data.get('finish_underpainting', False):
        paints = data.get('underpainting', []) + paints
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*4}" height="{H*4}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
        '<title id="title">Hatsune Miku — a vector painting after KEI</title>',
        '<desc id="desc">A staged vector adaptation of the official KEI illustration. Hatsune Miku, © Crypton Future Media, INC. 2007. CC BY-NC 3.0. Source: https://piapro.net/intl/en_character.html. Only vector drawing paths; no embedded raster image.</desc>']
    if sketch and data['strokes']:
        alpha = .75 if not paints else max(0, .28-len(paints)/550)
        parts.append(f'<g id="construction" opacity="{alpha:.3f}" fill="none" stroke="#718b96" stroke-linecap="round" stroke-linejoin="round">')
        for s in data['strokes']:
            parts.append(f'<path d="{s["d"]}" stroke-width="{s.get("width", .8)}"/>')
        parts.append('</g>')
    for b in data['batches']:
        entries = [p for p in paints if p['batch'] == b['id']]
        if not entries:
            continue
        parts.append(f'<g id="batch-{b["id"]:02d}" data-stage="{html.escape(b["title"])}">')
        for p in entries:
            color = '#'+''.join(f'{v:02x}' for v in p['rgb'])
            parts.append(f'<path id="{p["id"]}" d="{p["d"]}" fill="{color}" fill-rule="evenodd" stroke="{color}" stroke-width="{p.get("stroke_width", .16)}" stroke-linejoin="round"/>')
        parts.append('</g>')
    parts.append('</svg>')
    return '\n'.join(parts)

def browser_exe():
    for p in [r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe']:
        if Path(p).exists():
            return p
    return None

def render_svg(svg, target, scale=2):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_exe())
        page = browser.new_page(viewport={'width': W*scale, 'height': H*scale}, device_scale_factor=1)
        page.set_content('<style>html,body{margin:0;width:100%;height:100%;background:white}svg{width:100%;height:100%;display:block}</style>'+svg)
        page.screenshot(path=str(target))
        browser.close()

def checkpoint(data, title, note):
    idx = len(data['batches']); name = f'{idx:02d}-{title}'
    svg = svg_text(data)
    (ROOT / f'checkpoints/{name}.svg').write_text(svg, encoding='utf-8')
    render_svg(svg, ROOT / f'checkpoints/{name}.png')
    paints = data['paths'] if data.get('finish_underpainting', False) else data.get('underpainting', []) + data['paths']
    canvas = render_paths(paints)
    mse = float(np.mean((TARGET[FG].astype(float)-canvas[FG])**2))
    data['batches'][-1]['checkpoint'] = f'checkpoints/{name}.png'
    data['batches'][-1]['vector_file'] = f'checkpoints/{name}.svg'
    data['batches'][-1]['mse_foreground'] = round(mse, 4)
    data['batches'][-1]['total_paths'] = len(data['paths'])
    save(data)
    print(json.dumps({'checkpoint': name, 'paths': len(data['paths']), 'sketch_strokes': len(data['strokes']), 'foreground_mse': round(mse, 2), 'note': note}, ensure_ascii=True))

def batch(data, title, note):
    b = {'id': len(data['batches'])+1, 'title': title, 'decision': note, 'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'start_path': len(data['paths'])}
    data['batches'].append(b)
    return b['id']

def init(args):
    if (ROOT / 'recording/session.json').exists():
        raise SystemExit('Session already exists; initialization never overwrites it.')
    data = load(); bid = batch(data, 'gesture-and-proportion', args.note)
    paths = [
        ('M247 133 Q224 221 219 270 Q202 308 207 352', 1.2),
        ('M191 170 Q244 135 302 162', 1),
        ('M161 344 Q204 367 259 355', 1),
        ('M203 174 Q191 216 165 269 Q137 327 109 394', 1.2),
        ('M298 168 Q288 224 301 297 Q308 350 312 423', 1.2),
        ('M161 358 Q146 449 141 559 Q115 651 123 735', 1.2),
        ('M239 365 Q268 459 282 559 Q322 649 340 735', 1.2),
        ('M197 34 Q167 163 98 331 Q19 504 39 584 Q44 663 91 688', 1.25),
        ('M303 18 Q358 173 402 340 Q462 511 405 603 Q383 642 393 687', 1.25),
        ('M197 34 Q207 8 258 10 Q288 12 289 52 Q287 100 261 129 Q248 145 231 134 Q200 122 197 77 Q193 50 197 34Z', .8),
        ('M201 76 Q240 86 279 69', .8),
        ('M226 31 Q239 76 251 134', .65),
        ('M205 107 Q240 121 277 103', .55),
        ('M204 171 L194 212 L211 257 L184 331 L218 374 L277 345 L249 267 L279 217 L300 163', .8),
        ('M124 400 Q149 417 177 420', .75),
        ('M217 415 Q244 433 274 417', .75),
        ('M119 554 Q140 574 157 552', .6),
        ('M260 550 Q281 578 299 557', .6),
        ('M112 713 Q130 728 141 715', .6),
        ('M325 712 Q342 728 355 716', .6),
        ('M107 728 Q102 749 112 771 Q130 784 151 763 L138 732', .85),
        ('M331 729 Q317 744 313 767 Q335 789 360 765 L356 729', .85),
        ('M293 8 L282 31 L304 50 L318 26Z', .8),
        ('M199 23 L208 23 L202 42', .7),
        ('M219 151 L245 144 L260 174 L278 146', .65),
        ('M130 336 Q195 396 276 344', .8),
        ('M116 382 Q129 409 176 427', .65),
        ('M207 393 Q235 424 271 431', .65),
    ]
    for d, w in paths:
        data['strokes'].append({'id': f's{len(data["strokes"])+1:04d}', 'd': d, 'width': w, 'batch': bid, 'type': 'gesture'})
    checkpoint(data, 'gesture-and-proportion', args.note)

def outlines(args):
    data = load(); bid = batch(data, 'contour-construction', args.note)
    contours, _ = cv2.findContours(FG.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:1]:
        p = cv2.approxPolyDP(c, 1.05, True).reshape(-1, 2)
        for i in range(0, len(p), 10):
            seg = p[i:min(i+11, len(p))]
            if len(seg) < 2:
                continue
            d = 'M'+' L'.join(f'{x:.1f},{y:.1f}' for x, y in seg)
            data['strokes'].append({'id': f's{len(data["strokes"])+1:04d}', 'd': d, 'width': .7, 'batch': bid, 'type': 'contour'})
    internals = [
        'M216 42 Q215 72 236 85', 'M225 44 Q248 66 281 98',
        'M210 72 Q207 115 221 139', 'M279 91 Q273 125 280 132',
        'M212 88 Q222 82 232 96', 'M250 80 Q260 72 270 87',
        'M235 116 Q243 120 250 114', 'M268 125 L279 128 L272 147',
        'M240 153 Q217 211 190 269 L164 291 L150 328 L157 346 L186 327 L224 199 L248 162Z',
        'M124 309 L162 286', 'M184 331 L217 376 L276 349',
        'M282 207 L308 210 L312 272 L328 338 L344 417 Q312 440 274 416 L284 326 L281 262Z',
        'M292 317 L316 316 L332 415 L298 421Z',
        'M126 424 L175 435 Q164 502 158 552 Q147 606 136 700',
        'M225 431 L274 425 Q287 511 300 565 Q329 645 350 704',
        'M109 333 Q88 355 88 383 L119 410',
        'M130 349 L112 371', 'M151 363 L137 396', 'M178 376 L171 405',
        'M213 378 L219 402', 'M240 367 L254 391',
        'M168 383 Q161 464 178 547 Q183 578 200 605',
        'M306 38 Q341 202 373 355 Q412 505 371 580 Q345 629 378 661',
        'M184 96 Q153 261 95 407 Q41 508 54 569 Q68 622 52 645',
    ]
    for d in internals:
        data['strokes'].append({'id': f's{len(data["strokes"])+1:04d}', 'd': d, 'width': .62, 'batch': bid, 'type': 'structure'})
    checkpoint(data, 'contour-construction', args.note)

def region_mask(name):
    yy, xx = np.mgrid[:H, :W]
    hsv = cv2.cvtColor(TARGET, cv2.COLOR_RGB2HSV)
    cyan = (hsv[:, :, 0] > 69) & (hsv[:, :, 0] < 109) & (hsv[:, :, 1] > 34)
    hair = FG & (((xx < 188) & (yy > 47)) | ((xx > 321) & (yy > 25)) | (yy < 142)) & (cyan | ((xx < 188) & (yy > 440)) | ((xx > 352) & (yy > 110)))
    face = FG & (((xx > 200) & (xx < 308) & (yy > 49) & (yy < 215)) | ((yy > 379) & (yy < 447) & (xx > 85) & (xx < 348)))
    clothes = FG & (xx > 83) & (xx < 367) & (yy > 138)
    if name == 'hair': return hair
    if name == 'face': return face
    if name == 'clothes': return clothes
    if name == 'head': return FG & (yy < 150)
    return FG

def candidates(k, sigma, epsilon, minarea, region):
    smooth = cv2.GaussianBlur(TARGET, (0, 0), sigma) if sigma > 0 else cv2.bilateralFilter(TARGET, 5, 16, 2)
    lab = cv2.cvtColor(smooth, cv2.COLOR_RGB2LAB)
    pixels = lab[FG]
    rng = np.random.default_rng(28379+k)
    sample = pixels[rng.choice(len(pixels), min(32000, len(pixels)), replace=False)].astype(np.float32)
    cv2.setRNGSeed(28379+k)
    _, _, centers = cv2.kmeans(sample, k, None, (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER, 55, .08), 2, cv2.KMEANS_PP_CENTERS)
    _, nearest = cKDTree(centers).query(lab.reshape(-1, 3), workers=1)
    labels = nearest.reshape(H, W).astype(np.int16)
    labels[~FG] = -1
    interest = region_mask(region)
    result = []
    for ci in range(k):
        contours, hierarchy = cv2.findContours((labels == ci).astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None: continue
        for j, c in enumerate(contours):
            if hierarchy[0, j, 3] != -1 or cv2.contourArea(c) < minarea: continue
            group = [c]; child = hierarchy[0, j, 2]
            while child != -1:
                if cv2.contourArea(contours[child]) > .9: group.append(contours[child])
                child = hierarchy[0, child, 0]
            d, polygons = contour_path(group, epsilon)
            if not d: continue
            bx, by, bw, bh = cv2.boundingRect(c)
            maskroi = np.zeros((bh, bw), np.uint8)
            rel = [np.rint(np.array(p)-[bx, by]).astype(np.int32) for p in polygons]
            cv2.fillPoly(maskroi, rel, 1)
            ys, xs = np.nonzero(maskroi)
            ys += by; xs += bx
            valid = FG[ys, xs]; ys = ys[valid]; xs = xs[valid]
            if len(xs) < minarea or float(interest[ys, xs].mean()) < .52: continue
            rgb = np.rint(TARGET[ys, xs].mean(axis=0)).astype(np.uint8)
            result.append({'d': d, 'polygons': polygons, 'rgb': rgb.tolist(), 'bounds': bounds_of([np.array(p) for p in polygons]), '_idx': ys*W+xs, 'area': len(xs), 'region': region})
    return result

def refine(args):
    data = load()
    if not data['batches']: raise SystemExit('Initialize a session first.')
    if len(data['paths'])+args.n > 1700: raise SystemExit('Requested batch would exceed the hard 1700-path limit.')
    existing = {p['d'] for p in data['paths']}
    canvas = render_paths(data['paths']).reshape(-1, 3).astype(np.float32)
    target = TARGET.reshape(-1, 3).astype(np.float32)
    pool = candidates(args.k, args.sigma, args.epsilon, args.minarea, args.region)
    ranked = []
    for p in pool:
        if p['d'] in existing: continue
        idx = p['_idx']; col = np.array(p['rgb'], np.float32)
        gain = float(np.sum((canvas[idx]-target[idx])**2-(col-target[idx])**2))
        if gain > 0: ranked.append((gain, p))
    ranked.sort(key=lambda x: x[0], reverse=True)
    selected = []
    for _, p in ranked:
        if len(selected) >= args.n: break
        idx = p['_idx']; col = np.array(p['rgb'], np.float32)
        gain = float(np.sum((canvas[idx]-target[idx])**2-(col-target[idx])**2))
        if gain <= max(3, len(idx)*args.mingain): continue
        p['gain'] = round(gain, 2)
        p['stroke_width'] = args.overlap
        canvas[idx] = col
        del p['_idx']
        selected.append(p)
    if not selected: raise SystemExit('No improving shapes found; review the image and adjust candidate scale/region.')
    bid = batch(data, args.title, args.note)
    data['batches'][-1]['parameters'] = {k: getattr(args, k) for k in ['k', 'sigma', 'epsilon', 'minarea', 'n', 'region', 'mingain', 'overlap']}
    selected.sort(key=lambda p: (-int(math.log2(max(p['area'], 1))), int(p['bounds'][1]/110), p['bounds'][0]))
    for p in selected:
        p['id'] = f'p{len(data["paths"])+1:04d}'; p['batch'] = bid
        data['paths'].append(p)
    checkpoint(data, args.title, args.note)
    print(f'Accepted {len(selected)} / {args.n} requested, from {len(pool)} candidates.')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'outlines', 'refine', 'final'])
    parser.add_argument('--note', default='')
    parser.add_argument('--title', default='refinement')
    parser.add_argument('--k', type=int, default=16)
    parser.add_argument('--sigma', type=float, default=1)
    parser.add_argument('--epsilon', type=float, default=.55)
    parser.add_argument('--minarea', type=float, default=3)
    parser.add_argument('--n', type=int, default=100)
    parser.add_argument('--mingain', type=float, default=1)
    parser.add_argument('--overlap', type=float, default=.8)
    parser.add_argument('--region', choices=['all', 'hair', 'face', 'clothes', 'head'], default='all')
    args = parser.parse_args()
    if args.action == 'init': init(args)
    elif args.action == 'outlines': outlines(args)
    elif args.action == 'refine': refine(args)
    else:
        data = load()
        if not 1500 <= len(data['paths']) <= 1700: raise SystemExit(f'Final element gate failed: {len(data["paths"])}')
        svg = svg_text(data, False)
        (ROOT / 'output/hatsune-miku.svg').write_text(svg, encoding='utf-8')
        render_svg(svg, ROOT / 'output/hatsune-miku.png', 4)
        print(f'Final SVG: {len(data["paths"])} paths')

if __name__ == '__main__': main()
