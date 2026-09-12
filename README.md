# JAV Renamer Skill

自动化提取影片番号，聚合 JavBus + r18.dev 多源官方元数据，结合 LLM 智能中译日文标题、汉化女优名，并精准提炼 3 个分类标签，进行批量规范重命名并输出索引清单。

## 适用场景
- 各种网盘、本地磁盘中杂乱命名的番号视频文件整理。
- 去除各种发布组/论坛杂质前缀（如 `[Thz.la]`、`hhd800.com@`、`3xplanet_` 等）。
- 统一重命名为标准化格式：`[番号] 中文标题 [女优] [标签1·标签2·标签3].ext`。

## 文件结构
- `SKILL.md`: 技能定义与执行规范说明
- `scripts/jav_rename.py`: 核心自动化流水线 Python 脚本

## 使用方法

```bash
# 预览模式（仅展示前后对照，不改动文件）
python scripts/jav_rename.py --dir "D:\Videos"

# 确认无误后执行
python scripts/jav_rename.py --dir "D:\Videos" --apply
```
