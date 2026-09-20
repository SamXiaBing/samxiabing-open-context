# -*- coding: utf-8 -*-
"""增量入库：按微信已发表清单迁移 8 篇新文章 + 转正按键音草稿。"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_from_final import SRC, ROOT, IMG_EXT, find_article_md, rewrite_images  # noqa: E402

# (文件夹名, 微信日期, series, tier) —— tier: articles=公开层 / local=本地层
NEW = [
    ("座舱3D HMI 开发框架：Command 机制的设计与用途", "2026-09-18", "framework", "articles"),
    ("智驾 SR 开发：行人动画选 Animator 还是 VAT？", "2026-09-17", "sr", "articles"),
    ("座舱3D HMI材质：轮毂——从通用 Lit 到 MatCap", "2026-09-16", "rendering", "articles"),
    ("座舱3D HMI性能：对象池接入与回收的对称性", "2026-09-14", "perf", "articles"),
    ("座舱3D HMI 开发框架：MVC架构的工程化落地", "2026-09-11", "framework", "articles"),
    ("智驾 SR 开发：车位点选的几何检测方案", "2026-09-10", "sr", "articles"),
    ("座舱3D HMI材质：透明车壳材质的光效拆解", "2026-09-09", "rendering", "articles"),
    ("会议“戮”：谁杀了我的进程？", "2026-09-15", "drama", "local"),
]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for title, date, series, tier in NEW:
        src_dir = SRC / title
        if not src_dir.exists():
            print(f"[跳过] 源文件夹不存在: {title}")
            continue
        md, note = find_article_md(src_dir)
        if md is None:
            print(f"[跳过] {title}: {note}")
            continue
        dest_dir = ROOT / tier / series / title
        dest_dir.mkdir(parents=True, exist_ok=True)
        report = {"img_matched": 0, "img_downloaded": 0, "img_local": 0, "broken": []}
        budget = {"left": 10}
        text = md.read_text(encoding="utf-8", errors="replace")
        text = rewrite_images(text, src_dir, dest_dir, report, budget)
        no_m = re.search(r"[（(](\d+)[）)]", title)
        cn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        no = str(cn[no_m.group(1)]) if no_m else ""
        visibility = "public" if tier == "articles" else "local"
        fm = (f"---\ntitle: \"{title}\"\ndate: {date}\nseries: {series}\nno: {no}\n"
              f"status: published\nvisibility: {visibility}\nwechat_url: \"\"\n---\n\n")
        (dest_dir / md.name).write_text(fm + text, encoding="utf-8")
        print(f"[入库] {tier}/{series}/{title[:36]}  broken={len(report['broken'])}")

    # 转正按键音草稿：draft → published，日期 2026-09-08
    keyin = ROOT / "local/drama/会议“戮”：按键音，谁来播？"
    if keyin.exists():
        for md in keyin.glob("*.md"):
            t = md.read_text(encoding="utf-8")
            t = re.sub(r"^status: draft$", "status: published", t, flags=re.M)
            t = re.sub(r"^date: .*$", "date: 2026-09-08", t, count=1, flags=re.M)
            md.write_text(t, encoding="utf-8")
        print("[转正] 按键音：草稿 → 已发表，日期 2026-09-08")


if __name__ == "__main__":
    main()
