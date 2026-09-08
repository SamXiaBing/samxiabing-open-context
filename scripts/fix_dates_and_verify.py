# -*- coding: utf-8 -*-
"""修正：①按路径回填 91 篇日期；②draft 清空 no；③终验公开层 ⊆ 91 清单。"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPARE = json.loads((ROOT / "wechat_compare.json").read_text(encoding="utf-8"))


def norm(s: str) -> str:
    s = s.lower().replace("some/ip", "someip")
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", s)


def patch_fm(md: Path, **kv):
    t = md.read_text(encoding="utf-8")
    for k, v in kv.items():
        t = re.sub(rf"^{k}: .*$", f"{k}: {v}", t, count=1, flags=re.M)
    md.write_text(t, encoding="utf-8")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # ① 按路径回填日期
    n = 0
    for item in COMPARE["matched"]:
        md = ROOT / item["path"]
        if md.exists():
            patch_fm(md, date=item["date"])
            n += 1
    print(f"按路径回填日期 {n} 篇")

    # ② draft 清空 no
    for tier in ("articles", "local"):
        for md in (ROOT / tier).rglob("*.md"):
            t = md.read_text(encoding="utf-8")
            if re.search(r"^status: draft$", t, re.M) and re.search(r"^no: \d", t, re.M):
                patch_fm(md, no="")
                print(f"  draft 清空 no: {md.parent.name[:40]}")

    # ③ 终验
    wechat_norm = set()
    for line in (ROOT / "scripts" / "wechat_compare.py").read_text(encoding="utf-8").splitlines():
        m = re.match(r'\s*\("(.+)",\s*"(2026-\d\d-\d\d)"\),', line)
        if m:
            wechat_norm.add(norm(m.group(1)))
    leak = []
    for md in (ROOT / "articles").rglob("*.md"):
        t = md.read_text(encoding="utf-8")
        m = re.search(r'^title: "(.*)"$', t, re.M)
        if m and norm(m.group(1)) not in wechat_norm:
            leak.append(m.group(1))
    print(f"\n终验：公开层 {len(leak)} 篇不在 91 清单内")
    for t in leak:
        print(f"  [泄漏] {t}")


if __name__ == "__main__":
    main()
