# -*- coding: utf-8 -*-
"""生成 RISK-ASSESSMENT.md：逐篇分级清单，供用户确认公开范围。"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def parse_fm(md: Path):
    text = md.read_text(encoding="utf-8", errors="replace")
    end = text.find("\n---", 3)
    meta = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"')
    return meta, text[end + 4:]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    rows = []
    for tier in ("articles", "local"):
        for md in sorted((ROOT / tier).rglob("*.md")):
            meta, body = parse_fm(md)
            imgs = sorted(f.name for f in md.parent.iterdir() if f.suffix.lower() in IMG_EXT)
            ext_links = len(re.findall(r"!\[[^\]]*\]\(https?://", body))
            rows.append({"tier": tier, "series": meta.get("series", "?"), "title": meta.get("title", md.stem),
                         "date": meta.get("date", ""), "imgs": imgs, "ext": ext_links})
    g = [r for r in rows if r["tier"] == "articles"]
    drama = [r for r in rows if r["series"] == "drama"]
    yellow = [r for r in rows if r["tier"] == "local" and r["series"] != "drama"]

    L = ["# 风险分级清单（逐篇确认用）", "",
         "> 公众号发表时已经过你的脱敏审查，本清单评估的是 GitHub 的**增量风险**：",
         "> 搜索引擎/AI 可批量抓取、多篇聚合可拼出项目全貌、图片可被单独下载。",
         "> 全库扫描结果：faw/metis/一汽/解放/红旗/车型代号/内部IP **零命中**；",
         "> 唯一标识词命中为公开引擎名 Tuanjie（团结引擎）版本号，属低敏感。",
         ""]
    L.append(f"## 🟢 绿：建议直接公开（{len(g)} 篇，当前已在 articles/ 公开层）\n")
    L.append("| 文章 | 日期 | 本地图数 | 备注 |")
    L.append("|---|---|---|---|")
    for r in sorted(g, key=lambda x: (x["series"], x["date"])):
        note = "9 张位置映射图建议推送前对照公众号原文抽查" if any(
            k in r["title"] for k in ["车漆（一）", "车漆（二）", "车漆（三）", "Dual Kawase 模糊的工程思维", "充电特效", "车灯光柱"]) else ""
        L.append(f"| {r['title']} | {r['date']} | {len(r['imgs'])} | {note} |")
    L.append("\n> 🟢 注意：图片内容（Unity 编辑器截图等）建议推送前人工过目一遍；文字层面已扫描干净。")

    L.append(f"\n## 🟡 黄：工程系列，逐篇勾选（{len(yellow)} 篇，当前在 local/ 本地层）\n")
    L.append("已发表且脱敏过；决定是否公开时主要看：图片截图是否露内部界面、指标数值是否愿被聚合检索。\n")
    L.append("| 勾选? | 文章 | 系列 | 日期 | 图数 | 残留外链(失效图) | 特别标记 |")
    L.append("|---|---|---|---|---|---|---|")
    for r in sorted(yellow, key=lambda x: (x["series"], x["date"])):
        mark = "⚠️ URAS 命名是否内部系统名？" if "URAS" in r["title"] else ""
        L.append(f"| ☐ | {r['title']} | {r['series']} | {r['date']} | {len(r['imgs'])} | {r['ext']} | {mark} |")

    L.append(f"\n## 🔴 红：默认不公开（{len(drama)} 篇会议戮 + 说明）\n")
    L.append("| 文章 | 日期 |")
    L.append("|---|---|")
    for r in sorted(drama, key=lambda x: x["date"]):
        L.append(f"| {r['title']} | {r['date']} |")
    L.append("""
## 附：与公开无关的存量问题

1. **3 篇源文件夹无正文 md**（只有图片/脚本，未迁移）：车模环视、Unity编辑器小工具、ReferencePool
2. **车漆（八）水体平面反射文件夹已不存在**（疑似改名为"座舱3D HMI场景：水面效果"，语料库按现状收录）
3. **local/ 层失效图片**：约 100 条过期 OSS 签名链接 + 4 条相对路径缺文件（bug_candle_chart.png、gantt.png、profiler-mesh-hotpath.png、profiler-mesh-before-after.png）——不影响公开层，只影响本地检索时的图示完整性
4. **车漆双（六）编号冲突**：需拍板（（六）天气特效层 mtime 08-25 晚于（七）08-05，但 mtime 是最后编辑时间非发表时间，无法定序，建议按你记忆中的发表顺序定）
""")
    (ROOT / "RISK-ASSESSMENT.md").write_text("\n".join(L), encoding="utf-8")
    print(f"RISK-ASSESSMENT.md: 🟢{len(g)} 🟡{len(yellow)} 🔴{len(drama)}")


if __name__ == "__main__":
    main()
