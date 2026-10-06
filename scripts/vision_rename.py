# -*- coding: utf-8 -*-
"""
无语义文件视觉识别重命名器 (vision_rename.py)
================================================================
针对 Telegram 下载/网盘抓取的 `protected_content_*` / `media_group_*` /
`8月X日` 类无语义文件，按 ffmpeg 多帧截图 + 视觉 LLM 识别内容
（厂牌水印 / 服装 / 场景 / 剧情），生成符合命名规范的新文件名。

用法:
    python vision_rename.py --dir "C:/Users/Nero/Downloads"
    python vision_rename.py --dir "C:/Users/Nero/Downloads" --apply
    python vision_rename.py --dir "C:/..." --frames 8 --model gemini-3.8-flash-high

依赖:
    - ffmpeg / ffprobe 在 PATH 中
    - Pillow (pip install pillow)
    - OpenAI 兼容视觉接口 (默认 http://127.0.0.1:8317/v1)
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.wmv', '.m4v', '.flv', '.rmvb', '.mov', '.ts'}

# ---------- 1. 抽帧 ----------

def probe_duration(path):
    try:
        out = subprocess.check_output([
            'ffprobe','-v','quiet','-show_entries','format=duration',
            '-of','csv=p=0', path
        ], timeout=15).decode().strip()
        return float(out)
    except Exception:
        return None

def extract_frames(video_path, out_dir, n_frames=8):
    """抽取 n 个均匀分布帧到 out_dir, 返回帧路径列表"""
    dur = probe_duration(video_path)
    if not dur or dur < 5:
        return []
    stem = os.path.splitext(os.path.basename(video_path))[0]
    safe = re.sub(r'[^\w\-]', '_', stem)[:40]
    os.makedirs(out_dir, exist_ok=True)
    frames = []
    # 避开片头 5% 片尾 5%
    lo, hi = dur*0.05, dur*0.95
    step = (hi-lo)/max(n_frames-1,1)
    for i in range(n_frames):
        t = lo + i*step
        fp = os.path.join(out_dir, f"{safe}_f{i+1:02d}.jpg")
        subprocess.run([
            'ffmpeg','-y','-ss',f'{t:.1f}','-i',video_path,
            '-vframes','1','-vf','scale=1280:-1','-q:v','3', fp
        ], capture_output=True, timeout=30)
        if os.path.exists(fp) and os.path.getsize(fp) > 5000:
            frames.append(fp)
    return frames

def make_grid(frames, out_path, cols=4):
    """把多帧拼成一张网格图（降低视觉LLM调用次数）"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    if not frames:
        return None
    imgs = [Image.open(f).convert('RGB') for f in frames]
    w, h = imgs[0].size
    tw, th = w//2, h//2  # 半分辨率节省token
    thumbs = [im.resize((tw,th)) for im in imgs]
    rows = (len(thumbs)+cols-1)//cols
    canvas = Image.new('RGB', (tw*cols, th*rows), (20,20,20))
    draw = ImageDraw.Draw(canvas)
    for i,im in enumerate(thumbs):
        x,y = (i%cols)*tw, (i//cols)*th
        canvas.paste(im,(x,y))
        draw.rectangle([x,y,x+60,y+18],fill=(0,0,0))
        draw.text((x+3,y+2), f"#{i+1}", fill=(255,220,0))
    canvas.save(out_path, 'JPEG', quality=85)
    return out_path

# ---------- 2. 视觉 LLM ----------

SYS_PROMPT = '''你是成人影片内容识别与文件命名助手。输入为一段视频抽帧拼图（多帧按时间顺序 #1..#N）。
请仔细观察所有帧，识别并输出 JSON（纯JSON无markdown）：
{
 "category": "AI换脸|JAV|国产传媒|欧美|里番|3D同人|杂项 之一",
 "studio": "厂牌/水印，如 IPPA/FALENO/S1/麻豆/果冻/天美/SA国际/Dorcel/Brazzers/OnlyFans 等，无则null",
 "actress": "演员或明星名（若明确可辨，AI换脸场景取原明星），否则null",
 "scene": "场景简述（卧室/办公室/教室/浴室等，中文4-10字）",
 "costume": "服装特征（黑丝/OL制服/空姐制服/新娘白丝等，无则null）",
 "plot": "剧情一句话（中文10-25字，如'空姐下班后被上司胁迫出轨'）",
 "tags": ["3-5个中文标签，如['人妻','黑丝','中出','OL']"]
}
硬性规则：
- 严禁识别真实人脸身份；若是AI换脸可识别「换脸目标明星」的公众形象标签
- 优先提取画面上的厂牌Logo/水印（Jable/SODSTAR/FALENO/IPPA/麻豆/天美等）
- 若画面纯黑或无法识别，category 返回 "杂项"
- 若疑似损坏文件（首帧黑/绿屏/马赛克大块）返回 {"category":"损坏"}
'''

def call_vision(img_path, api_base, api_key, model, timeout=120):
    with open(img_path,'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    body = json.dumps({
        "model": model,
        "messages":[
            {"role":"system","content":SYS_PROMPT},
            {"role":"user","content":[
                {"type":"text","text":"识别该视频内容并输出JSON"},
                {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}
            ]}
        ],
        "temperature":0.2,"max_tokens":1500
    }).encode()
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions", data=body,
        headers={'Content-Type':'application/json','Authorization':f'Bearer {api_key}'})
    res = urllib.request.urlopen(req,timeout=timeout).read().decode()
    content = json.loads(res)['choices'][0]['message']['content'].strip()
    content = re.sub(r'^```(json)?|```$','',content).strip()
    m = re.search(r'\{.*\}', content, re.S)
    return json.loads(m.group(0)) if m else None

# ---------- 3. 命名生成 ----------

def build_name(meta, ext):
    """根据识别结果生成规范文件名"""
    if not meta:
        return None
    cat = meta.get('category','杂项')
    if cat == '损坏':
        return f"[损坏]{ext}"
    studio = meta.get('studio') or ''
    actress = meta.get('actress') or ''
    scene = meta.get('scene') or ''
    costume = meta.get('costume') or ''
    plot = meta.get('plot') or ''
    tags = meta.get('tags') or []

    if cat == 'AI换脸':
        parts = ['[AI换脸]', actress or '未知', plot or scene]
    elif cat == '国产传媒':
        code = f"·{studio}" if studio else ''
        parts = [f'[{studio or "国产"}]', plot or scene]
        if actress: parts.append(f'[{actress}]')
    elif cat == 'JAV':
        parts = ['[JAV]']
        if studio: parts.append(f'[{studio}]')
        if costume: parts.append(costume)
        parts.append(plot or scene)
        if actress: parts.append(f'[{actress}]')
    elif cat == '欧美':
        parts = [f'[欧美·{studio}]' if studio else '[欧美]', plot or scene]
        if actress: parts.append(f'[{actress}]')
    elif cat in ('里番','3D同人'):
        parts = [f'[{cat}]', plot or scene or '作品']
        if studio: parts.append(f'[{studio}]')
    else:
        parts = ['[杂项]', plot or scene or '待分类']

    # 附标签
    if tags and cat != '杂项':
        t = '·'.join(t for t in tags[:4] if t)
        if t: parts.append(f'[{t}]')

    name = ' '.join(p for p in parts if p).strip()
    name = re.sub(r'[/\\:*?"<>|]',' ',name)
    name = re.sub(r'\s+',' ',name).strip()
    return f"{name}{ext}"

def needs_vision(fname):
    """判断是否无语义命名（需要视觉识别）"""
    stem = os.path.splitext(fname)[0]
    if re.match(r'^\[', stem): return False  # 已规范
    if re.match(r'^[A-Za-z]{2,6}-\d{2,5}', stem): return False  # 标准番号
    if re.search(r'[\u4e00-\u9fff]', stem): return False  # 含中文有语义
    # protected_content_*/media_group_*/日期/数字hash/纯英文随机
    if re.match(r'^(protected_content|media_group|video|VID_|IMG_|MOV_|download|\d+月\d+日|\d{4}-\d{2}-\d{2}|[a-f0-9]{16,})', stem, re.I):
        return True
    # 全英文但无单词意义 > 无语义
    words = re.findall(r'[a-z]{3,}', stem.lower())
    if len(words) <= 1 and len(stem) > 10:
        return True
    return False

# ---------- 4. 主流程 ----------

def process_one(f, target_dir, frames_dir, args):
    """处理单个文件：抽帧 -> 拼图 -> 识别 -> 返回新文件名"""
    video_path = os.path.join(target_dir, f)
    stem, ext = os.path.splitext(f)
    try:
        frames = extract_frames(video_path, frames_dir, n_frames=args.frames)
        if not frames:
            return f, None, 'no_frames'
        grid_path = os.path.join(frames_dir, re.sub(r'[^\w\-]','_',stem)[:40] + '_grid.jpg')
        if not make_grid(frames, grid_path, cols=min(4,args.frames)):
            return f, None, 'grid_fail'
        meta = call_vision(grid_path, args.api_base, args.api_key, args.model)
        if not meta:
            return f, None, 'vision_fail'
        new_name = build_name(meta, ext)
        return f, new_name, meta
    except Exception as e:
        return f, None, f'error: {e}'

def main():
    ap = argparse.ArgumentParser(description='无语义视频文件视觉识别重命名')
    ap.add_argument('--dir', required=True)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--frames', type=int, default=8, help='每部抽帧数(默认8)')
    ap.add_argument('--api-base', default='http://127.0.0.1:8317/v1')
    ap.add_argument('--api-key', default=os.getenv('LOCAL_8317_API_KEY','123456'))
    ap.add_argument('--model', default='gemini-3.8-flash-high')
    ap.add_argument('--concurrency', type=int, default=3)
    ap.add_argument('--cache', default=None, help='识别结果缓存json路径')
    args = ap.parse_args()

    target = os.path.abspath(args.dir)
    frames_dir = os.path.join(target, '_vision_frames')
    os.makedirs(frames_dir, exist_ok=True)
    cache_path = args.cache or os.path.join(target, '_vision_cache.json')

    cache = {}
    if os.path.exists(cache_path):
        try: cache = json.load(open(cache_path,encoding='utf-8'))
        except Exception: pass

    files = [f for f in os.listdir(target)
             if os.path.isfile(os.path.join(target,f))
             and os.path.splitext(f)[1].lower() in VIDEO_EXTS
             and needs_vision(f)]
    print(f'[*] 待识别文件: {len(files)} 个')

    plan = {}
    pending = [f for f in files if f not in cache]
    if pending:
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = {ex.submit(process_one,f,target,frames_dir,args):f for f in pending}
            for i,fut in enumerate(as_completed(futs),1):
                f,new_name,meta = fut.result()
                if isinstance(meta,dict):
                    cache[f] = {'meta':meta,'new_name':new_name}
                    print(f'  [{i}/{len(pending)}] {f[:40]:<42} -> {new_name[:50] if new_name else "?"}')
                else:
                    print(f'  [{i}/{len(pending)}] {f[:40]:<42} -> SKIP ({meta})')
                if i%5==0:
                    json.dump(cache,open(cache_path,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
        json.dump(cache,open(cache_path,'w',encoding='utf-8'),ensure_ascii=False,indent=1)

    # 应用
    applied=0
    for f,rec in cache.items():
        new = rec.get('new_name')
        if not new or new==f: continue
        src,dst = os.path.join(target,f), os.path.join(target,new)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                if args.apply:
                    os.rename(src,dst); applied+=1
                else:
                    plan[f]=new
            except PermissionError:
                print(f'  [!] 锁定: {f}')
    if args.apply:
        print(f'\n[✓] 已重命名 {applied} 个')
    else:
        print(f'\n[*] 预览计划 {len(plan)} 条（加 --apply 执行）')
        for old,new in list(plan.items())[:20]:
            print(f'  {old[:50]} -> {new[:60]}')

if __name__=='__main__':
    main()
