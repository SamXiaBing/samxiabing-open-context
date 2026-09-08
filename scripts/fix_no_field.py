# -*- coding: utf-8 -*-
"""一次性修正语料库 frontmatter 的 no 字段：中文数字（一）→1，case-08 → case-08。"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_RE = re.compile(r"[（(]([一二三四五六七八九十]{1,2})[）)]")
CASE_RE = re.compile(r"[（(]case-(\d+)[）)]")


def no_of(title: str) -> str:
    m = CASE_RE.search(title)
    if m:
        return f"case-{int(m.group(1)):02d}"
    m = CN_RE.search(title)
    if m:
        s = m.group(1)
        if s == "十":
            return "10"
        if s.startswith("十"):
            return str(10 + CN[s[1]])
        if s.endswith("十"):
            return str(CN[s[0]] * 10)
        if "十" in s:
            a, b = s.split("十")
            return str(CN[a] * 10 + CN[b])
        return str(CN[s])
    return ""


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    n = 0
    for tier in ("articles", "local"):
        for md in (ROOT / tier).rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            head = text[:end]
            title_m = re.search(r'title: "(.*)"', head)
            if not title_m:
                continue
            new_no = no_of(title_m.group(1))
            if re.search(r"^no: .*$", head, re.M):
                head2 = re.sub(r"^no: .*$", f"no: {new_no}", head, flags=re.M)
            else:
                head2 = head + f"\nno: {new_no}"
            if head2 != head:
                md.write_text(head2 + text[end:], encoding="utf-8")
                n += 1
    print(f"更新 no 字段 {n} 篇")


if __name__ == "__main__":
    main()
