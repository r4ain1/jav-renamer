# -*- coding: utf-8 -*-
"""
JAV Renamer - 全品类成人影片与影视资源自动化整理、元数据中译、智能打标与批量重命名工具
支持两大模式：
1. 标准日韩 JAV 模式：通过 JavBus/r18.dev 抓取官方元数据，LLM 精准汉化女优与生成三标签
2. 泛品类综合整理模式（AI换脸/国产自媒体/里番3D/欧美影片/杂项）：利用 LLM 结构化提取清洗
"""

import argparse
import collections
import concurrent.futures
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ----------------- 基础正则与过滤集合 -----------------

JAV_EXCLUDES = {
    'MP', 'MKV', 'AVI', 'WMV', 'M3U', 'ISO', 'VOB', 'SRT', 'FHD', 'WEB',
    'AAC', 'XAV', 'VOL', 'EP', 'PART', 'CD', 'DATE', 'SIZE',
    'POST', 'PAGE', 'HTTP', 'HTTPS', 'WWW', 'COM', 'NET', 'ORG', 'BIG', 'RESTORED',
    'HD', 'FHD', 'UHD', 'SD', 'XAVO', 'PMV', 'HHB', 'DVD', 'MOV', 'M4V', 'TS'
}

CODE_RE = re.compile(r'(?<![A-Za-z])([A-Za-z]{2,6})[-_ ]?0*(\d{2,5})(?![0-9])')

SUBTITLE_EXTS = {'.srt', '.ass', '.vtt', '.sub', '.idx'}
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.wmv', '.m3u8', '.iso', '.vob', '.ts', '.m4v', '.flv', '.rmvb', '.mov', '.nrg', '.md0'}

# ----------------- 步骤 1: 番号提取 -----------------

def extract_code(filename):
    stem = os.path.splitext(filename)[0]
    work = stem
    for p in [
        r'^[a-zA-Z0-9._-]+\.(com|net|tv|tw|xyz|la|me|co|top|org|cc|site|club|us|vip|icu)@',
        r'^[\w\.-]+@',
        r'^\d+_3xplanet_', r'^\d+_', r'^3xplanet_\d+-', r'^3xplanet_',
        r'^IKUJAV\.COM-', r'^JAVZIP\.NET-', r'^avidol\.us-', r'^mimip2p\+', r'^nike\(',
        r'^DivX\+', r'^THMS@', r'^bb\.', r'^FHD-', r'^FHD ', r'^HD\]',
        r'^1www\.98T\.la@', r'^www\.98T\.la@', r'^169bbs1\.com@', r'^489155\.com@',
        r'^hhd800\.com@', r'^sis001\.com@', r'^4k2\.com@', r'^gg5\.co@', r'^kcf9\.com@',
    ]:
        work = re.sub(p, '', work, flags=re.I).strip()
    work = re.sub(r'([A-Za-z]{2,6})\s*[-_ ]\s*(\d{2,5})', r'\1-\2', work)
    work = work.replace('_', '-')
    
    matches = CODE_RE.findall(work)
    for prefix, num in matches:
        p_up = prefix.upper()
        if p_up in JAV_EXCLUDES:
            continue
        if p_up in ('HD', 'FHD', 'UHD') and int(num) in (720, 1080, 2160, 480):
            continue
        if len(num) < 3:
            num = num.zfill(3)
        return f"{p_up}-{num}"
    return None

# ----------------- 步骤 2: 元数据网络抓取 (JavBus + r18.dev) -----------------

def fetch_javbus(code, proxy="http://127.0.0.1:7890"):
    handlers = {}
    if proxy:
        handlers = {'http': proxy, 'https': proxy}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(handlers))
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9,ja;q=0.8',
        'Cookie': 'existmag=all; age=checked; over18=1'
    }
    
    # 1. 直接请求
    url = f"https://www.javbus.com/{code}"
    try:
        req = urllib.request.Request(url, headers=headers)
        html = opener.open(req, timeout=15).read().decode('utf-8', 'ignore')
        if "<title>" in html and "Age Verification" not in html and "404 Not Found" not in html:
            t = re.search(r'<title>(.*?)</title>', html, re.S)
            title_full = t.group(1).replace(' - JavBus', '').strip() if t else ''
            title_clean = re.sub(rf'^{code}\s*', '', title_full, flags=re.I).strip()
            stars = list(dict.fromkeys(re.findall(r'/star/[a-z0-9_]+\"[^>]*>([^<]+)</a>', html)))
            genres = [g for g in dict.fromkeys(re.findall(r'/genre/[a-z0-9]+\"[^>]*>([^<]+)</a>', html)) if g not in ('高清', '字幕', '高畫質', '4K')]
            return {
                'code': code,
                'title_jp': title_clean or title_full,
                'stars': stars,
                'genres': genres,
                'source': 'javbus'
            }
    except Exception:
        pass

    # 2. 搜索回退
    search_url = f"https://www.javbus.com/search/{code}"
    try:
        req = urllib.request.Request(search_url, headers=headers)
        html = opener.open(req, timeout=15).read().decode('utf-8', 'ignore')
        boxes = re.findall(r'<a class=\"movie-box\" href=\"(https://www.javbus.com/[^\"]+)\"', html)
        prefix_part = code.split('-')[0].upper()
        num_part = code.split('-')[1]
        for box_url in boxes:
            box_slug = box_url.split('/')[-1].upper()
            if prefix_part in box_slug and num_part in box_slug:
                sub_html = opener.open(urllib.request.Request(box_url, headers=headers), timeout=15).read().decode('utf-8', 'ignore')
                t = re.search(r'<title>(.*?)</title>', sub_html, re.S)
                title_full = t.group(1).replace(' - JavBus', '').strip() if t else ''
                title_clean = re.sub(rf'^{code}\s*', '', title_full, flags=re.I).strip()
                stars = list(dict.fromkeys(re.findall(r'/star/[a-z0-9_]+\"[^>]*>([^<]+)</a>', sub_html)))
                genres = [g for g in dict.fromkeys(re.findall(r'/genre/[a-z0-9]+\"[^>]*>([^<]+)</a>', sub_html)) if g not in ('高清', '字幕', '高畫質', '4K')]
                return {
                    'code': code,
                    'title_jp': title_clean or title_full,
                    'stars': stars,
                    'genres': genres,
                    'source': 'javbus_search'
                }
    except Exception:
        pass

    return None

def fetch_r18dev(code, proxy="http://127.0.0.1:7890"):
    handlers = {}
    if proxy:
        handlers = {'http': proxy, 'https': proxy}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(handlers))
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*'
    }
    variations = [code.lower(), code.lower().replace('-', '')]
    for v in variations:
        url = f"https://r18.dev/videos/vod/movies/detail/-/dvd_id={v}/json"
        req = urllib.request.Request(url, headers=headers)
        try:
            res = opener.open(req, timeout=15).read().decode('utf-8')
            data = json.loads(res)
            stars = [a.get('name', '') for a in data.get('actresses', []) if a.get('name')]
            genres = [c.get('name', '') for c in data.get('categories', []) if c.get('name')]
            title = data.get('title', '')
            if title:
                return {
                    'code': code,
                    'title_jp': title,
                    'stars': stars,
                    'genres': genres,
                    'source': 'r18.dev'
                }
        except Exception:
            continue
    return None

def fetch_metadata_single(code, proxy):
    m = fetch_javbus(code, proxy=proxy)
    if not m:
        m = fetch_r18dev(code, proxy=proxy)
    return code, m

# ----------------- 步骤 3: LLM 翻译打标 -----------------

SYS_PROMPT_JAV = '''你是日本成人影片元数据整理助手。输入为若干条作品信息（编号/日文或英文标题/女优名/官方分类）。
任务：为每条输出中文整理结果：
1) zh_title：标题的中文翻译。忠实原意、通顺自然、不省略关键剧情要素、不超过38个汉字；去掉「※」「」等符号；保留系列名；若原标题包含女优名字则移除。
2) actress_cn：女优名的简体中文常用译名（中国大陆常见译法，如 三上悠亜→三上悠亚、吉沢明歩→吉泽明步、野々浦暖→野野浦暖、涼森れむ→凉森玲梦、神木麗→神木丽）。
3) tags：正好3个中文分类标签，从官方分类中挑选最能代表作品的3个，统一为简体中文常用词（如 人妻/女教师/痴汉/NTR/中出/巨乳/制服/凌辱/单体作品/口交/搜查官/美乳 等）。
只输出JSON数组，元素形如 {"i":0,"zh_title":"...","actress_cn":["..."],"tags":["..","..",".."]}，不要任何解释文字，不要markdown。'''

def call_llm_jav(batch, api_base, api_key, model="claude-sonnet-4-6"):
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
            {'role': 'system', 'content': SYS_PROMPT_JAV},
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

SYS_PROMPT_SCHEME_B = '''你是中文影视资源整理与规范命名专家。输入为一组未经整理的非标准番号成人影视/短片文件名列表。
任务：请根据文件命名特征，将其归纳为以下 5 种分类并按照严格规范输出重命名结果：

1. 【明星AI换脸/二创类】（以 #明星名 开头，或含 AI换脸、AI明星、明星名剧情演义、PMV、911爆料、每日大赛等）：
   - 提取主角明星（如 刘亦菲、杨幂、迪丽热巴、宋轶、IU李知恩、赵露思、古力娜扎 等，多位明星用顿号连接）
   - 去除所有营销无用词（如 #、911吃瓜、每日大赛、久久视频、第一人称视角、本人原声配音、高清PMV、无水印等）
   - 提炼简明通顺的剧情/场景主题（中文，控制在22字以内）
   - 命名格式：[AI换脸] 明星姓名 剧情简述

2. 【国产传媒品牌类】（麻豆、果冻、精东、91制片厂、兔子先生、起点、蜜桃、SWAG、GDCM、MDX、MD、JDTY、JDYL、KCM、TZ、MSD等）：
   - 提取品牌名与官方编号（如 果冻传媒·GDCM-056、麻豆传媒·MD-0336、精东影业·JDTY-003、91制片厂·KCM-137）
   - 提取剧名，若有明确演员名则提取演员名
   - 命名格式：[厂牌·番号] 剧名 [演员名] （若无演员名则省略演员名方括号）

3. 【二次元里番与3D同人类】（含 OVA、対魔忍、梅麻呂3D、夜桜字幕組、H動畫、Animan、PoRO、SFM、同人动画等）：
   - 提取作品规范中文名，标注分集（如 第1话、第2话），保留制作组/社团
   - 命名格式：[里番] 作品中文名 第X话 [制作社/字幕组] 或 [3D同人] 作品中文名 [社团/制作]

4. 【欧美与跨国影片】（含 Dorcel、Brazzers/N1C、Pornhub、Mina Asahi跨国篇、欧美老牌等）：
   - 提取厂牌/系列名（如 Dorcel、Brazzers、Pornhub），保留英文标题与主演
   - 命名格式：[欧美·厂牌] Title [演员] 或 [欧美] Title [演员]

5. 【待确认与杂项】（无语义哈希、临时命名如 8月1日、非成人工作视频如 Codex教学等）：
   - 规范格式：[杂项] 简明描述 或 [其他] 描述

注意：
- 只输出 JSON 数组，格式为：[{"i": 0, "category": "AI换脸/国产传媒/里番同人/欧美/杂项", "new_name": "规范后名称"}]
- new_name 绝对不要包含扩展名（如 .mp4/.m3u8）！不要包含 Windows 非法字符 (/ \\ : * ? " < > |)
- 严禁任何额外解释文字，只输出纯 JSON。'''

def call_llm_scheme_b(batch, api_base, api_key, model="claude-sonnet-4-6"):
    items = [{'i': j, 'filename': item} for j, item in enumerate(batch)]
    body = json.dumps({
        'model': model,
        'messages': [
            {'role': 'system', 'content': SYS_PROMPT_SCHEME_B},
            {'role': 'user', 'content': json.dumps(items, ensure_ascii=False)}
        ],
        'temperature': 0.1,
        'max_tokens': 3500
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

def detect_part_number(filename):
    stem = os.path.splitext(filename)[0]
    m = re.search(r'[-_ ](cd|part|ep|disc|话|集)?0*([1-9]\d?)(?=[-_ \]]|$)', stem, re.I)
    if m:
        try:
            return int(m.group(2))
        except ValueError:
            return None
    return None

def sanitize_name(name):
    name = re.sub(r'[/\\:*?"<>|]', ' ', name).strip()
    name = re.sub(r'\s+', ' ', name).strip()
    return name

# ----------------- 主程序 -----------------

def main():
    parser = argparse.ArgumentParser(description="JAV & 全品类成人影视规范重命名工具")
    parser.add_argument("--dir", default=".", help="视频所在目标目录")
    parser.add_argument("--mode", default="all", choices=["jav", "non-jav", "all"], help="执行模式: jav(仅标准番号), non-jav(仅AI/国产/欧美等), all(全品类完整流水线)")
    parser.add_argument("--proxy", default="http://127.0.0.1:7890", help="网络代理地址")
    parser.add_argument("--api-base", default="http://127.0.0.1:8317/v1", help="LLM API Base URL")
    parser.add_argument("--api-key", default=os.getenv("LOCAL_8317_API_KEY", "123456"), help="LLM API Key")
    parser.add_argument("--jav-model", default="gemini-3.8-flash-high", help="标准番号元数据处理 LLM 模型")
    parser.add_argument("--b-model", default="claude-sonnet-4-6", help="非标准番号资源处理 LLM 模型")
    parser.add_argument("--apply", action="store_true", help="直接应用重命名，默认仅预览")
    parser.add_argument("--concurrency", type=int, default=4, help="网络抓取并发数")
    args = parser.parse_args()

    target_dir = os.path.abspath(args.dir)
    if not os.path.exists(target_dir):
        print(f"[!] 目标目录不存在: {target_dir}")
        sys.exit(1)

    all_entries = [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f)) and not f.startswith('_')]
    print(f"[*] 扫描到 {len(all_entries)} 个文件 (目标目录: {target_dir})...")

    # 分离视频文件与字幕文件
    video_files = [f for f in all_entries if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
    sub_files = [f for f in all_entries if os.path.splitext(f)[1].lower() in SUBTITLE_EXTS]
    print(f"[*] 媒体文件: {len(video_files)} 个, 外挂字幕文件: {len(sub_files)} 个")

    # ================== 阶段 1: 标准日韩 JAV 处理 ==================
    if args.mode in ("jav", "all"):
        print("\n" + "="*50 + "\n【阶段 1】标准日韩 JAV 番号提取与规范重命名\n" + "="*50)
        file_map = {}
        for f in video_files:
            if re.match(r'^\[[A-Za-z0-9]+-\d+\]\s+', f):
                continue  # 已经规范命名
            code = extract_code(f)
            if code:
                file_map[f] = code

        unique_codes = sorted({c for c in file_map.values() if c})
        print(f"[*] 提取到 {len(file_map)} 个待处理含番号文件，涵盖 {len(unique_codes)} 个独立番号")

        meta_cache_path = os.path.join(target_dir, "_jav_meta_cache.json")
        meta_cache = {}
        if os.path.exists(meta_cache_path):
            try:
                with open(meta_cache_path, "r", encoding="utf-8") as f:
                    meta_cache = json.load(f)
            except Exception:
                pass

        missing_codes = [c for c in unique_codes if c not in meta_cache]
        if missing_codes:
            print(f"[*] 并发抓取 {len(missing_codes)} 个番号的元数据...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                future_to_code = {executor.submit(fetch_metadata_single, c, args.proxy): c for c in missing_codes}
                for i, future in enumerate(concurrent.futures.as_completed(future_to_code), 1):
                    code, m = future.result()
                    if m:
                        meta_cache[code] = m
                        print(f"  [{i}/{len(missing_codes)}] {code} OK ({m.get('title_jp')[:25]}...)")
                    else:
                        print(f"  [{i}/{len(missing_codes)}] {code} FAIL")
            try:
                with open(meta_cache_path, "w", encoding="utf-8") as f:
                    json.dump(meta_cache, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        llm_cache_path = os.path.join(target_dir, "_jav_llm_cache.json")
        llm_results = {}
        if os.path.exists(llm_cache_path):
            try:
                with open(llm_cache_path, "r", encoding="utf-8") as f:
                    llm_results = json.load(f)
            except Exception:
                pass

        codes_to_translate = [c for c in unique_codes if c in meta_cache and c not in llm_results]
        if codes_to_translate:
            print(f"[*] 开始 JAV 批量中译与打标 ({len(codes_to_translate)} 个, 模型: {args.jav_model})...")
            batch_size = 15
            for i in range(0, len(codes_to_translate), batch_size):
                chunk = [meta_cache[c] for c in codes_to_translate[i:i+batch_size]]
                try:
                    res_arr = call_llm_jav(chunk, args.api_base, args.api_key, model=args.jav_model)
                    for r in res_arr:
                        orig_code = chunk[r['i']]['code']
                        llm_results[orig_code] = r
                    with open(llm_cache_path, "w", encoding="utf-8") as f:
                        json.dump(llm_results, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[!] JAV 翻译错误: {e}")
                time.sleep(0.3)

        # 构建 JAV 重命名计划
        code_videos = collections.defaultdict(list)
        for f in video_files:
            c = file_map.get(f)
            if c and c in llm_results:
                code_videos[c].append(f)

        jav_rename_dict = {}
        for c, files in code_videos.items():
            info = llm_results[c]
            title = re.sub(r'\s+', ' ', re.sub(r'[/\\:*?"<>|]', ' ', info.get('zh_title', '').strip()))[:40].strip()
            stars = info.get('actress_cn', []) or meta_cache.get(c, {}).get('stars', [])
            stars_clean = [re.sub(r'[/\\:*?"<>|]', '', s).strip() for s in stars if s.strip()]
            stars_str = ('、'.join(stars_clean[:3]) + (f'等{len(stars_clean)}人' if len(stars_clean) > 3 else '')) if stars_clean else ''
            tags_clean = [re.sub(r'[/\\:*?"<>|]', '', t).strip() for t in info.get('tags', []) if t.strip()][:3]
            tags_str = '·'.join(tags_clean)

            parts = [f"[{c}]"]
            if title: parts.append(title)
            if stars_str: parts.append(f"[{stars_str}]")
            if tags_str: parts.append(f"[{tags_str}]")
            core_base = ' '.join(parts)

            if len(files) == 1:
                vf = files[0]
                jav_rename_dict[vf] = f"{core_base}{os.path.splitext(vf)[1]}"
            else:
                files_with_parts = [(vf, detect_part_number(vf)) for vf in files]
                has_parts = all(p is not None for _, p in files_with_parts) and len({p for _, p in files_with_parts}) == len(files)
                files_with_parts.sort(key=lambda x: x[1] if has_parts else x[0])
                for idx, (vf, p_num) in enumerate(files_with_parts, 1):
                    ep = p_num if (has_parts and p_num) else idx
                    jav_rename_dict[vf] = f"{core_base} 第{ep}话{os.path.splitext(vf)[1]}"

        # 外挂字幕协同
        for sf in sub_files:
            s_stem, s_ext = os.path.splitext(sf)
            for vf, new_vn in list(jav_rename_dict.items()):
                if os.path.splitext(vf)[0] == s_stem:
                    jav_rename_dict[sf] = f"{os.path.splitext(new_vn)[0]}{s_ext}"
                    break

        print(f"[*] 阶段 1 生成 JAV 规范重命名计划: {len(jav_rename_dict)} 个文件")
        if args.apply:
            s_cnt = 0
            for old_f, new_f in jav_rename_dict.items():
                if old_f != new_f:
                    s_path = os.path.join(target_dir, old_f)
                    d_path = os.path.join(target_dir, new_f)
                    if os.path.exists(s_path) and not os.path.exists(d_path):
                        os.rename(s_path, d_path)
                        s_cnt += 1
            print(f"[✓] 阶段 1 执行完成，成功重命名 {s_cnt} 个文件")

    # ================== 阶段 2: 泛品类综合处理 (AI/国产/里番/欧美) ==================
    if args.mode in ("non-jav", "all"):
        print("\n" + "="*50 + "\n【阶段 2】非标准番号全品类（AI换脸/国产/里番3D/欧美/杂项）规范重命名\n" + "="*50)
        current_entries = [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f)) and not f.startswith('_')]
        
        scheme_b_files = []
        for f in current_entries:
            if re.match(r'^\[[A-Za-z0-9]+-\d+\]\s+', f):
                continue
            if re.match(r'^\[(AI换脸|果冻传媒|麻豆传媒|精东影业|91制片厂|兔子先生|国产传媒|国产中字|国产剧|蜜桃影像|FCD|槟榔传媒|里番|3D同人|欧美|杂项|其他)\]', f):
                continue
            scheme_b_files.append(f)

        sub_b_files = [f for f in scheme_b_files if os.path.splitext(f)[1].lower() in SUBTITLE_EXTS]
        main_b_files = [f for f in scheme_b_files if f not in sub_b_files]
        print(f"[*] 待处理非标准番号媒体: {len(main_b_files)} 个, 字幕: {len(sub_b_files)} 个")

        b_cache_path = os.path.join(target_dir, "_scheme_b_cache.json")
        b_cache = {}
        if os.path.exists(b_cache_path):
            try:
                with open(b_cache_path, "r", encoding="utf-8") as f:
                    b_cache = json.load(f)
            except Exception:
                pass

        needed_b = [f for f in main_b_files if f not in b_cache]
        if needed_b:
            print(f"[*] 调用 LLM 处理 {len(needed_b)} 个非标准番号文件 (模型: {args.b_model})...")
            batch_size = 12
            for idx in range(0, len(needed_b), batch_size):
                chunk = needed_b[idx:idx+batch_size]
                try:
                    res_list = call_llm_scheme_b(chunk, args.api_base, args.api_key, model=args.b_model)
                    for r in res_list:
                        orig = chunk[r['i']]
                        b_cache[orig] = {
                            'category': r.get('category', '杂项'),
                            'new_name': sanitize_name(r.get('new_name', ''))
                        }
                    with open(b_cache_path, "w", encoding="utf-8") as f:
                        json.dump(b_cache, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[!] 批次解析错误: {e}")
                time.sleep(0.3)

        b_plan = []
        b_stem_map = {}
        for f in main_b_files:
            ext = os.path.splitext(f)[1]
            stem = os.path.splitext(f)[0]
            rec = b_cache.get(f)
            if rec and rec.get('new_name'):
                new_f = f"{rec['new_name']}{ext}"
                b_plan.append((f, new_f, rec.get('category', '杂项')))
                b_stem_map[stem] = rec['new_name']
            else:
                b_plan.append((f, f, "跳过"))

        for sf in sub_b_files:
            s_stem, s_ext = os.path.splitext(sf)
            if s_stem in b_stem_map:
                b_plan.append((sf, f"{b_stem_map[s_stem]}{s_ext}", "外挂字幕"))
            else:
                b_plan.append((sf, sf, "外挂字幕"))

        # 排重
        name_counts = collections.defaultdict(int)
        final_b_plan = []
        for old_f, new_f, cat in b_plan:
            if new_f != old_f and cat != "外挂字幕":
                name_counts[new_f] += 1
                if name_counts[new_f] > 1:
                    stem, ext = os.path.splitext(new_f)
                    new_f = f"{stem} ({name_counts[new_f]}){ext}"
            final_b_plan.append((old_f, new_f, cat))

        print(f"[*] 阶段 2 生成规范重命名计划: {len(final_b_plan)} 个文件")
        if args.apply:
            s_cnt = 0
            for old_f, new_f, cat in final_b_plan:
                if old_f != new_f:
                    s_path = os.path.join(target_dir, old_f)
                    d_path = os.path.join(target_dir, new_f)
                    if os.path.exists(s_path) and not os.path.exists(d_path):
                        os.rename(s_path, d_path)
                        s_cnt += 1
            print(f"[✓] 阶段 2 执行完成，成功重命名 {s_cnt} 个文件")

    # ================== 阶段 3: 输出/刷新全局 CSV 检索清单 ==================
    csv_path = os.path.join(target_dir, "_索引_影片清单.csv")
    final_files = sorted([f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f)) and not f.startswith('_')])
    try:
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["文件名", "分类标签", "扩展名", "文件大小(MB)"])
            for fname in final_files:
                fpath = os.path.join(target_dir, fname)
                fsize = round(os.path.getsize(fpath) / (1024*1024), 2)
                ext = os.path.splitext(fname)[1]
                m_tag = re.search(r'^\[([^\]]+)\]', fname)
                tag = m_tag.group(1) if m_tag else "未分类"
                writer.writerow([fname, tag, ext, fsize])
        print(f"\n[✓] 全局影片清单已刷新至: {csv_path} (共收录 {len(final_files)} 部资源)")
    except Exception as e:
        print(f"[!] 写入索引表失败: {e}")

if __name__ == "__main__":
    main()
