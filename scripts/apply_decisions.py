# -*- coding: utf-8 -*-
"""按用户拍板执行：①车漆（六）天气特效层 →（九）；②黄区 79 篇转公开层（drama 与 URAS 除外）。"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # 1. 天气特效层（六）→（九）
    old = ROOT / "articles/carpaint/座舱3D HMI材质：车漆（六）天气特效层"
    new = ROOT / "articles/carpaint/座舱3D HMI材质：车漆（九）天气特效层"
    if old.exists():
        old.rename(new)
        for md in new.glob("*.md"):
            t = md.read_text(encoding="utf-8")
            t = t.replace('title: "座舱3D HMI材质：车漆（六）天气特效层"',
                          'title: "座舱3D HMI材质：车漆（九）天气特效层"')
            t = re.sub(r"^no: .*$", "no: 9", t, count=1, flags=re.M)
            md.write_text(t, encoding="utf-8")
        print("车漆（九）天气特效层：重命名+frontmatter 完成")

    # 2. 黄区转公开（drama、URAS 除外）
    moved, kept = 0, []
    for series_dir in sorted((ROOT / "local").iterdir()):
        if not series_dir.is_dir() or series_dir.name == "drama":
            continue
        for art in sorted(series_dir.iterdir()):
            if not art.is_dir():
                continue
            if "URAS" in art.name:
                kept.append(art.name)
                continue
            dest = ROOT / "articles" / series_dir.name / art.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(art), str(dest))
            for md in dest.glob("*.md"):
                t = md.read_text(encoding="utf-8")
                t = re.sub(r"^visibility: local$", "visibility: public", t, flags=re.M)
                md.write_text(t, encoding="utf-8")
            moved += 1
    print(f"转公开 {moved} 篇；留本地 {[k for k in kept]}")


if __name__ == "__main__":
    main()
