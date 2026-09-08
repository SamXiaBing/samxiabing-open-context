# -*- coding: utf-8 -*-
"""扫描 articles/ 与 local/ 下的文章 frontmatter，生成 catalog.jsonl（公开）与 catalog.local.jsonl（全量）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["title", "date", "series", "no", "status", "visibility", "wechat_url"]


def parse_frontmatter(md_path: Path):
    text = md_path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    meta = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta


def collect(base: Path):
    rows = []
    if not base.exists():
        return rows
    for md in sorted(base.rglob("*.md")):
        if md.parent.name == "scripts":
            continue
        meta = parse_frontmatter(md)
        if meta is None:
            continue
        row = {k: meta.get(k, "") for k in FIELDS}
        row["path"] = str(md.relative_to(ROOT)).replace("\\", "/")
        rows.append(row)
    return rows


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    public = collect(ROOT / "articles")
    local = collect(ROOT / "local")
    public.sort(key=lambda r: (r["date"], r["path"]))
    local.sort(key=lambda r: (r["date"], r["path"]))

    with open(ROOT / "catalog.jsonl", "w", encoding="utf-8") as f:
        for r in public:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(ROOT / "catalog.local.jsonl", "w", encoding="utf-8") as f:
        for r in local:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"catalog.jsonl: {len(public)} 篇（公开）; catalog.local.jsonl: {len(public) + len(local)} 篇（全量）")


if __name__ == "__main__":
    main()
