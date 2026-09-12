# -*- coding: utf-8 -*-
"""
JAV Renamer - 自动化成人影片元数据抓取、中译、打标与批量重命名工具
"""

import argparse
import collections
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

PREFIX_PATTERNS = [
    r'^\[[^\]]*\]\s*', r'^【[^】]*】\s*', r'^\d+_3xplanet_', r'^\d+_',
    r'^3xplanet_\d+-', r'^3xplanet_', r'^hhd800\.com@', r'^IKUJAV\.COM-',
    r'^JAVZIP\.NET-', r'^avidol\.us-', r'^mimip2p\+', r'^nike\(',
    r'^DivX\+', r'^THMS@', r'^bb\.', r'^FHD-', r'^FHD ', r'^HD\]',
]

CODE_RE = re.compile(r'(?<![A-Za-z0-9])([A-Za-z]{2,6})[-_ ]?(\d{2,5})(?![\d])')

def extract_code(filename):
    stem = re.sub(r'\.[A-Za-z0-9]{2,4}$', '', filename)
    work = stem
    for p in PREFIX_PATTERNS:
        work = re.sub(p, '', work, flags=re.I)
    work = work.replace('_', '-')
    m = CODE_RE.search(work)
    if not m:
        return None
    return f"{m.group(1).upper()}-{m.group(2)}"

def fetch_javbus(code, proxy="http://127.0.0.1:7890"):
    handlers = {}
    if proxy:
        handlers = {'http': proxy, 'https': proxy}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(handlers))
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    url = f"https://www.javbus.com/{code}"
    req = urllib.request.Request(url, headers=headers)
    try:
        html = opener.open(req, timeout=20).read().decode('utf-8', 'ignore')
        if "<title>" not in html or "Age Verification" in html:
            return None
        
        t = re.search(r'<title>(.*?)</title>', html, re.S)
        title_full = t.group(1).replace(' - JavBus', '').strip() if t else ''
        
        stars = list(dict.fromkeys(re.findall(r'/star/[a-z0-9_]+\"[^>]*>([^<]+)</a>', html)))
        genres = [g for g in dict.fromkeys(re.findall(r'/genre/[a-z0-9]+\"[^>]*>([^<]+)</a>', html)) if g not in ('高清', '字幕', '高畫質')]
        
        return {
            'code': code,
            'title_jp': title_full,
            'stars': stars,
            'genres': genres,
            'source': 'javbus'
        }
    except Exception:
        return None

def fetch_r18dev(code):
    url = f"https://r18.dev/videos/vod/movies/detail/-/dvd_id={code}/json"
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode('utf-8'))
        stars = [a.get('name', '') for a in data.get('actresses', [])]
        genres = [c.get('name', '') for c in data.get('categories', [])]
        return {
            'code': code,
            'title_jp': data.get('title', ''),
            'stars': stars,
            'genres': genres,
            'source': 'r18.dev'
        }
    except Exception:
        return None

SYS_PROMPT = '''你是日本成人影片元数据整理助手。输入为若干条作品信息（编号/日文或英文标题/女优名/官方分类）。
任务：为每条输出中文整理结果：
1) zh_title：标题的中文翻译。忠实原意、不省略关键剧情要素、不超过38个汉字；去掉「※」「」等符号；保留系列名。
2) actress_cn：女优名的简体中文常用译名（中国大陆常见译法，如 三上悠亜→三上悠亚、吉沢明歩→吉泽明步、野々浦暖→野野浦暖）。
3) tags：正好3个中文分类标签，从官方分类中挑选最能代表作品的3个，统一为简体中文常用词（如 人妻/女教师/痴汉/NTR/中出/巨乳/制服/凌辱/单体作品/口交 等）。
只输出JSON数组，元素形如 {"i":0,"zh_title":"...","actress_cn":["..."],"tags":["..","..",".."]}，不要任何解释文字，不要markdown。'''

def call_llm(batch, api_base, api_key, model="claude-sonnet-4-6"):
    items = []
    for j, m in enumerate(batch):
        items.append({
            'i': j,
            'code': m.get('code'),
            'title': m.get('title_jp', '')[:120],
            'stars': m.get('stars', []),
            'genres': m.get('genres', [])[:8]
        })
    body = json.dumps({
        'model': model,
        'messages': [
            {'role': 'system', 'content': SYS_PROMPT},
            {'role': 'user', 'content': json.dumps(items, ensure_ascii=False)}
        ],
        'temperature': 0.2,
        'max_tokens': 3000
    }, ensure_ascii=False).encode('utf-8')
    
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=body,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
    )
    res = urllib.request.urlopen(req, timeout=120).read().decode('utf-8')
    d = json.loads(res)
    content = d['choices'][0]['message']['content'].strip()
    content = re.sub(r'^```(json)?', '', content).strip()
    content = re.sub(r'```$', '', content).strip()
    m = re.search(r'\[.*\]', content, re.S)
    if m:
        content = m.group(0)
    return json.loads(content)

def main():
    parser = argparse.ArgumentParser(description="批量重命名影片并打标")
    parser.add_argument("--dir", default=".", help="视频所在目录")
    parser.add_argument("--proxy", default="http://127.0.0.1:7890", help="代理地址")
    parser.add_argument("--api-base", default="http://127.0.0.1:8317/v1", help="LLM API Base URL")
    parser.add_argument("--api-key", default=os.getenv("LOCAL_8317_API_KEY", "123456"), help="LLM API Key")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="LLM 模型名称")
    parser.add_argument("--apply", action="store_true", help="直接应用重命名，默认仅预览")
    args = parser.parse_args()

    target_dir = os.path.abspath(args.dir)
    files = [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f)) and not f.startswith('_')]
    print(f"[*] 扫描到 {len(files)} 个文件...")

    # 1. 番号提取
    file_map = {}
    for f in files:
        code = extract_code(f)
        file_map[f] = code

    # 2. 抓取元数据
    unique_codes = sorted({c for c in file_map.values() if c})
    meta_cache = {}
    print(f"[*] 共提取到 {len(unique_codes)} 个独立番号，开始获取元数据...")
    for i, code in enumerate(unique_codes, 1):
        m = fetch_javbus(code, proxy=args.proxy)
        if not m:
            m = fetch_r18dev(code)
        if m:
            meta_cache[code] = m
            print(f"[{i}/{len(unique_codes)}] {code} OK")
        else:
            print(f"[{i}/{len(unique_codes)}] {code} FAIL")
        time.sleep(0.5)

    # 3. LLM 结构化中译与打标
    llm_results = {}
    codes_to_translate = [c for c in unique_codes if c in meta_cache]
    print(f"[*] 开始 LLM 批量中译与打标 ({len(codes_to_translate)} 个)...")
    batch_size = 10
    for i in range(0, len(codes_to_translate), batch_size):
        chunk = [meta_cache[c] for c in codes_to_translate[i:i+batch_size]]
        try:
            res_arr = call_llm(chunk, args.api_base, args.api_key, model=args.model)
            for r in res_arr:
                orig_code = chunk[r['i']]['code']
                llm_results[orig_code] = r
        except Exception as e:
            print(f"[!] 批次翻译错误: {e}")
        time.sleep(1)

    # 4. 生成新文件名
    plan = []
    groups = collections.defaultdict(list)
    for f in files:
        c = file_map.get(f)
        groups[c].append(f)

    for f in files:
        ext = os.path.splitext(f)[1]
        c = file_map.get(f)
        if not c or c not in llm_results:
            plan.append((f, None))
            continue
        info = llm_results[c]
        title = info.get('zh_title', '').strip()
        title = re.sub(r'[/\\:*?"<>|]', ' ', title)[:45]
        stars = info.get('actress_cn', [])
        stars_str = '、'.join(stars[:3]) + (f'等{len(stars)}人' if len(stars) > 3 else '')
        tags = '·'.join(info.get('tags', [])[:3])
        
        parts = [f"[{c}]"]
        if title: parts.append(title)
        if stars_str: parts.append(f"[{stars_str}]")
        if tags: parts.append(f"[{tags}]")
        core = ' '.join(parts)
        if len(groups[c]) > 1:
            part_idx = groups[c].index(f) + 1
            core += f" 第{part_idx}话"
        new_name = core + ext
        plan.append((f, new_name))

    # 5. 执行或预览
    print("\n" + "="*50)
    print("重命名计划预览 (前 10 条):")
    for old, new in plan[:10]:
        print(f"  {old}  ==>  {new or '[跳过/未识别]'}")
    print("="*50)

    if args.apply:
        count = 0
        for old, new in plan:
            if new and new != old:
                os.rename(os.path.join(target_dir, old), os.path.join(target_dir, new))
                count += 1
        print(f"\n[✓] 成功重命名 {count} 个文件！")
    else:
        print("\n[!] 当前为预览模式。添加 --apply 参数以实际执行重命名。")

if __name__ == "__main__":
    main()
