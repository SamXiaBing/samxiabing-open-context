# -*- coding: utf-8 -*-
"""校验语料库：frontmatter 完整性、series 目录匹配、同系列编号唯一、catalog 双向一致。"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERIES = {"carpaint", "rendering", "perf", "stability", "framework", "localization", "tools", "sr", "misc", "drama"}
REQUIRED = ["title", "date", "series", "status", "visibility"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_frontmatter(md_path: Path):
    text = md_path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None, "缺 frontmatter"
    end = text.find("\n---", 3)
    if end < 0:
        return None, "frontmatter 未闭合"
    meta = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, ""


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    errors, warns = [], []
    nos = {}
    all_rows = []
    for tier in ("articles", "local"):
        base = ROOT / tier
        if not base.exists():
            continue
        for md in sorted(base.rglob("*.md")):
            rel = str(md.relative_to(ROOT)).replace("\\", "/")
            if md.parent.name == "scripts" or md.name.endswith(".en.md"):
                continue
            meta, err = parse_frontmatter(md)
            if meta is None:
                errors.append(f"{rel}: {err}")
                continue
            for f in REQUIRED:
                if not meta.get(f):
                    errors.append(f"{rel}: 缺必填字段 {f}")
            series = meta.get("series", "")
            if series not in SERIES:
                errors.append(f"{rel}: series 非法值 {series!r}")
            elif not rel.replace("\\", "/").startswith(f"{tier}/{series}/") and tier == "articles":
                errors.append(f"{rel}: series={series} 与目录不符")
            if meta.get("date") and not DATE_RE.match(meta["date"]):
                errors.append(f"{rel}: date 格式应为 YYYY-MM-DD，实际 {meta['date']!r}")
            if meta.get("visibility") not in ("public", "local"):
                errors.append(f"{rel}: visibility 应为 public/local，实际 {meta.get('visibility')!r}")
            if tier == "articles" and meta.get("visibility") == "local":
                errors.append(f"{rel}: 公开目录内出现 visibility=local")
            no = meta.get("no", "")
            if no:
                key = (meta.get("series"), no)
                nos.setdefault(key, []).append(meta.get("title", rel))
            all_rows.append(meta)

    for (series, no), titles in nos.items():
        if len(titles) > 1:
            warns.append(f"同系列编号冲突（待用户拍板重命名） series={series} no={no}: {titles}")

    cat_pub = ROOT / "catalog.jsonl"
    if cat_pub.exists():
        on_disk = [json.loads(l) for l in cat_pub.read_text(encoding="utf-8").splitlines() if l.strip()]
        disk_titles = Counter(r["title"] for r in on_disk)
        cur_titles = Counter(r.get("title", "?") for r in all_rows if r.get("visibility") == "public")
        if disk_titles != cur_titles:
            errors.append("catalog.jsonl 与 articles/ 实际内容不一致，请重跑 build_catalog.py")
    else:
        warns.append("catalog.jsonl 不存在，请跑 build_catalog.py")

    for e in errors:
        print(f"[ERROR] {e}")
    for w in warns:
        print(f"[WARN ] {w}")
    n = len(all_rows)
    print(f"\n共 {n} 篇（public {sum(1 for r in all_rows if r.get('visibility')=='public')} / local {sum(1 for r in all_rows if r.get('visibility')=='local')}）")
    print("PASS" if not errors else f"FAIL: {len(errors)} 个错误")
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
