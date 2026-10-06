# -*- coding: utf-8 -*-
"""
递归全目录成人影视规范化重命名工具 (健壮增强版)
遍历所有包含尚未规范命名的子目录，对每一个子目录执行阶段1(JAV标准番号)与阶段2(泛品类资源)重命名。
"""

import argparse
import os
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description="递归处理目录下所有子目录的影视规范重命名")
    parser.add_argument("--root", default="W:/H11A", help="根目录路径")
    parser.add_argument("--proxy", default="http://127.0.0.1:7890", help="代理")
    parser.add_argument("--api-base", default="http://127.0.0.1:8317/v1", help="LLM API Base")
    parser.add_argument("--api-key", default=os.getenv("LOCAL_8317_API_KEY", "123456"), help="LLM Key")
    parser.add_argument("--jav-model", default="gemini-3.8-flash-high", help="JAV 模型")
    parser.add_argument("--b-model", default="claude-sonnet-4-6", help="泛品类模型")
    parser.add_argument("--apply", action="store_true", help="直接应用重命名")
    parser.add_argument("--concurrency", type=int, default=8, help="网络抓取并发数")
    args = parser.parse_args()

    root_dir = os.path.abspath(args.root)
    if not os.path.exists(root_dir):
        print(f"[!] 根目录不存在: {root_dir}")
        sys.exit(1)

    video_exts = {'.mp4', '.mkv', '.avi', '.wmv', '.m3u8', '.iso', '.vob', '.ts', '.m4v', '.flv', '.rmvb', '.mov'}
    target_dirs = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "javTunes" in dirpath:
            continue
        # 统计含有未规范命名文件的子目录
        raw_files = [f for f in filenames if os.path.splitext(f)[1].lower() in video_exts and not f.startswith('_') and not f.startswith('[')]
        if raw_files:
            target_dirs.append((dirpath, len(raw_files), len(filenames)))

    print("="*70)
    print(f"【深度扫描完成】发现 {len(target_dirs)} 个包含未规范命名文件的目录：")
    total_raw = sum(cnt for _, cnt, _ in target_dirs)
    for d, raw_cnt, tot_cnt in target_dirs[:15]:
        print(f"  - {d} (待规范: {raw_cnt} / 总计: {tot_cnt})")
    if len(target_dirs) > 15:
        print(f"  ... 还有 {len(target_dirs) - 15} 个目录")
    print(f"  待处理文件总计: {total_raw} 个")
    print("="*70)

    script_path = os.path.abspath("C:/Users/Nero/AppData/Local/hermes/skills/jav-renamer/scripts/jav_rename.py")

    for idx, (d, raw_cnt, tot_cnt) in enumerate(target_dirs, 1):
        print(f"\n\n>>>>>>>>>>> [{idx}/{len(target_dirs)}] 正在处理目录: {d} (待改名: {raw_cnt}) <<<<<<<<<<<")
        cmd = [
            sys.executable, script_path,
            "--dir", d,
            "--mode", "all",
            "--proxy", args.proxy,
            "--api-base", args.api_base,
            "--api-key", args.api_key,
            "--jav-model", args.jav_model,
            "--b-model", args.b_model,
            "--concurrency", str(args.concurrency)
        ]
        if args.apply:
            cmd.append("--apply")

        try:
            res = subprocess.run(cmd, timeout=600)
            if res.returncode != 0:
                print(f"[!] 目录处理异常退出 (退出码: {res.returncode}): {d}")
        except subprocess.TimeoutExpired:
            print(f"[!] 目录处理超时 (600s): {d}")
        except Exception as e:
            print(f"[!] 目录处理发生错误: {d}, 错误: {e}")

    print("\n" + "="*70)
    print(f"[✓] 全部 {len(target_dirs)} 个子目录处理完毕！")
    print("="*70)

if __name__ == "__main__":
    main()
