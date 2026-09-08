# -*- coding: utf-8 -*-
"""风险扫描：在语料库全部文章中查找公司/项目标识词与内部地址，统计本地图片数。

公众号发表时已经过用户脱敏审查，GitHub 的增量风险是"可聚合性"——
多篇串联能拼出项目全貌、内部系统名、截图。本脚本输出逐篇命中清单供人工分级。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
# 脱敏规范中点名的公司/项目标识 + 通用内部特征
TOKENS = {
    "faw": re.compile(r"faw", re.I),
    "metis": re.compile(r"metis", re.I),
    "一汽/解放/红旗": re.compile(r"一汽|解放|红旗|hongqi", re.I),
    "车型代号J6/J7": re.compile(r"\bJ6\b|\bJ7\b"),
    "内部IP": re.compile(r"\b10\.\d+\.\d+\.\d+\b"),
    "内部域名": re.compile(r"[a-z0-9.-]+\.(corp|intra|local)\b", re.I),
    "Tuanjie/团结引擎版本": re.compile(r"[Tt]uanjie"),
}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    out = []
    for tier in ("articles", "local"):
        for md in sorted((ROOT / tier).rglob("*.md")):
            text = md.read_text(encoding="utf-8", errors="replace")
            hits = {}
            for name, rx in TOKENS.items():
                n = len(rx.findall(text))
                if n:
                    hits[name] = n
            imgs = sum(1 for f in md.parent.iterdir() if f.suffix.lower() in IMG_EXT)
            out.append({"path": str(md.relative_to(ROOT)).replace("\\", "/"), "hits": hits, "imgs": imgs})
    (ROOT / "risk_scan.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    flagged = [r for r in out if r["hits"]]
    print(f"扫描 {len(out)} 篇；命中标识词 {len(flagged)} 篇，明细 risk_scan.json")
    for r in flagged:
        print(f"  {r['path'][:70]} -> {r['hits']}")


if __name__ == "__main__":
    main()
