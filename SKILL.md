---
name: jav-renamer
description: 自动化识别日韩成人影片番号与泛品类资源（AI换脸/国产传媒/里番3D/欧美），多源抓取元数据（JavBus/r18.dev），利用 LLM 精准中译标题、女优名与三标签，批量规范重命名并生成检索清单。
version: 2.1.0
author: r4ain1, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [video, rename, jav, metadata, llm, organizer, media]
---

# JAV Renamer 影片整理与标准化重命名 Skill

自动化识别与整理本地影视资源库，涵盖**标准日韩 JAV** 与 **非标准番号资源（明星AI换脸、国产传媒剧、欧美影片、二次元里番/3D同人、杂项视频）**。通过多源互补（JavBus + r18.dev DMM）抓取官方元数据，结合本地/云端 LLM 完成标题中文翻译、女优名简体汉化、提炼三个代表性中文分类标签，进行无冲突批量规范重命名，外挂字幕协同命名，并生成可全局检索的索引清单。

## 命名规范体系

### 1. 标准日韩 JAV
```text
[番号] 中文翻译标题 [女优姓名] [标签1·标签2·标签3].扩展名
```
- 多分卷/多集自动追加 `第1话`、`第2话` 等分集后缀。
- 超过 3 名女优时折叠为 `[女优A、女优B、女优C等N人]`。
- 标签严格保留 3 个，统一为常见简体中文标签（如 `人妻·凌辱·巨乳`）。

### 2. 泛品类成人影视（方案 B 体系）
- **明星 AI 换脸 / 二创**：`[AI换脸] 明星姓名 剧情简述.扩展名`
  - 示例：`[AI换脸] 迪丽热巴 女教师与校长办公室偷情被学生要挟.mp4`
- **国产传媒品牌（麻豆/果冻/精东等）**：`[厂牌·番号] 剧名 [演员名].扩展名`
  - 示例：`[果冻传媒·GDCM-056] 孤注一掷.mp4`、`[精东影业·JDTY-003] 科学奇迹超敏感体质 [莉娜].mp4`
- **二次元里番 / 3D 同人动画**：`[里番/3D同人] 作品中文名 第X话 [制作社/字幕组].扩展名`
  - 示例：`[里番] 受胎岛 第1话 [ばにぃうぉ～か～].mp4`、`[3D同人] 人妻真理的性事 MOVIE版 [梅麻吕3D·夜樱字幕组].m3u8`
- **欧美与跨国影片**：`[欧美·厂牌] Title [演员].扩展名`
  - 示例：`[欧美·Dorcel] Dorcel Airlines Hotesses Libertines 2019.mp4`
- **待确认与杂项**：`[杂项] 简述.扩展名`

### 3. 视觉识别补充体系（无语义文件）
当文件名无语义（`protected_content_*`、`media_group_*`、`8月X日`、纯哈希等），按视觉识别内容命名：

- **AI换脸**：`[AI换脸] 明星 剧情 [服装·场景·标签]`
  - 示例：`[AI换脸] 赵露思 深夜浴室湿身 [浴室·湿身·诱惑].mp4`
- **JAV（无番号凭水印/场景）**：`[JAV] [厂牌] 服装 场景 [标签]`
  - 示例：`[JAV] [IPPA] 黑丝OL 办公室 [OL·黑丝·办公室].mp4`、`[JAV] [S1] 空姐制服 机舱厕所 [空姐·制服·出轨].mp4`
- **国产传媒**：`[国产] [厂牌] 剧情 [标签]`（沿用方案B规则，厂牌优先取画面水印而非文件名）
  - 示例：`[国产] [麻豆] 新郎醉倒旁白丝新娘被伴郎进入 [新娘·白丝·当面NTR].mp4`
- **欧美**：`[欧美] [厂牌] 场景 [标签]`
- **损坏文件**：`[损坏] 原文件名.扩展名`（保留不删，标记供后续 remux/重下）

---

## 核心工作流

1. **番号智能提取与类型分流**：剥离网站防爬、分享站水印前缀，正则智能提取标准番号；非番号资源自动进入泛品类清洗通道。
2. **多源元数据抓取**：
   - **主源 JavBus**：获取原生日文标题、女优名单、发布日期、官方类型标签。支持年龄验证 Cookie 自动绕过与标题前缀自适应。
   - **补源 r18.dev (DMM)**：处理 JavBus 未收录或防爬拦截的长尾资源。
3. **LLM 批量翻译与结构化抽取**：
   - 标准 JAV：提取女优简体常用译名、精选 3 个代表性中文标签，标题控制在 40 字以内。
   - 非标准资源：剥离营销词、广告后缀，精炼剧情与主角信息。
4. **外挂字幕（.srt/.ass/.vtt）协同匹配**：自动寻找同名前缀字幕文件，实现视频与字幕 100% 同步重命名。
5. **冲突检测与预演**：在重命名前做碰撞排查与路径存在性检查，支持同名防覆盖自增序号。
6. **批量执行与索引表导出**：执行重命名并在目标根目录输出 `_索引_影片清单.csv`（含文件名、分类标签、扩展名、文件体积）。

---

## 运行方式

脚本位于 `scripts/` 目录：

```bash
# 全品类完整流水线（预览模式，不修改磁盘）
python scripts/jav_rename.py --dir "W:/H11A/100"

# 全品类完整流水线（直接应用执行重命名）
python scripts/jav_rename.py --dir "W:/H11A/100" --apply

# 仅处理日韩标准番号
python scripts/jav_rename.py --dir "W:/H11A/100" --mode jav --apply

# 仅处理非标准番号资源（AI换脸/国产/欧美/里番）
python scripts/jav_rename.py --dir "W:/H11A/100" --mode non-jav --apply

# 递归处理所有子目录（大批量整库整理）
python scripts/recursive_rename.py --root "W:/H11A" --apply

# 无语义文件视觉识别（protected_content_*/日期命名/纯哈希）
python scripts/vision_rename.py --dir "C:/Users/Nero/Downloads"
python scripts/vision_rename.py --dir "C:/Users/Nero/Downloads" --apply --frames 8
```

### 无语义文件视觉识别流程（vision_rename.py）

针对 Telegram/网盘抓取的 `protected_content_1790629947_3d3b1f60.mp4`、`8月9日.mp4` 类无语义文件：

1. **抽帧**：ffmpeg 均匀抽 N 帧（默认 8 帧，避开片头尾 5%）
2. **拼图**：PIL 把多帧拼成 4×2 网格图（降低视觉 LLM 调用成本）
3. **识别**：视觉 LLM 提取厂牌水印/服装/场景/剧情/标签
4. **命名**：按内容类型走对应命名模板（见命名规范 §3）
5. **缓存**：识别结果写入 `_vision_cache.json`，重复运行秒回

**关键参数**：
- `--frames 8`：抽帧数（剧情片建议 8-12，短片 4 够用）
- `--concurrency 3`：并发抽帧+识别（太高易超时）
- `--model`：视觉模型（默认 `gemini-3.8-flash-high`，备选 `gpt-4o`/`claude-sonnet-4-6`）

**无语义判定规则**（`needs_vision`）：未匹配标准番号 + 无中文 + 命中 `protected_content_*`/`media_group_*`/`X月X日`/纯哈希前缀 → 视为无语义。

### 损坏文件处理

- ffmpeg 抽帧失败 / `moov atom not found` / HEVC NAL 错误 → 视为损坏
- 默认策略：**标记 `[损坏]` 保留**，不删不覆盖，供后续 remux/重下
- 0 字节文件 + `PermissionError`（杀软/同步锁占用）→ 跳过，记录待处理

### 关键参数说明
- `--dir`：影视资源所在目录（默认当前目录）。
- `--mode`：执行模式，`all`（默认全品类）、`jav`（仅日韩标准番号）、`non-jav`（仅非标准资源）。
- `--apply`：实际执行重命名（缺省时仅生成计划和预览）。
- `--proxy`：网络代理地址（默认 `http://127.0.0.1:7890`）。
- `--api-base`：OpenAI 兼容接口（默认 `http://127.0.0.1:8317/v1`）。
- `--jav-model`：日韩元数据处理模型（默认 `gemini-3.8-flash-high`）。
- `--b-model`：泛品类处理模型（默认 `claude-sonnet-4-6`）。

---

## 依赖要求

- Python 3.8+
- **ffmpeg / ffprobe** 在 PATH 中（视觉识别抽帧必需）
- **Pillow**（`pip install pillow`，视觉识别拼图必需）
- 网络代理（访问 JavBus / r18.dev，如本地 Clash 代理端口 7890）
- OpenAI 兼容的 LLM 接口（本地 Gateway `http://127.0.0.1:8317/v1` 或各类云端 API）
- 视觉识别需支持 image_url 的多模态模型（gemini-3.8-flash-high / gpt-4o / claude-sonnet-4-6）

## 踩坑与降级经验

- **内置视觉服务超时**：若 Agent 内置 `vision_analyze` 工具持续超时，降级为直连 OpenAI 兼容网关 + base64 图传（`vision_rename.py` 即此实现）。
- **视觉识别 prompt 必须声明"不识别真实人脸身份"**：合规要求，且响应更稳定；AI换脸场景可识别"换脸目标明星"公众形象标签。
- **串行优于并发**：视觉 LLM 并发 >3 易超时；抽帧本身可并发，但识别调用建议串行或 ≤3 并发。
- **Windows 路径**：ffmpeg/PIL 等原生工具用 `C:\` 原生路径，勿用 MSYS `/c/` 路径。
- **全角符号文件名**：`os.rename` 替代 shell `mv` 处理带全角逗号/括号的长文件名。
- **JavBus 防爬**：直接命中页返回 200 但无标题 → 已内置 search 回退 + `existmag=all` Cookie 绕过年龄验证。
