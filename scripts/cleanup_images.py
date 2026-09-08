# -*- coding: utf-8 -*-
"""公开层失效图片清理：外部链接先重试下载，失败替换为说明文字；缺失相对路径同样处理。"""
import re
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
IMG_RE = re.compile(r"(!\[[^\]]*\])\(([^)]+)\)")
NOTE = "*[配图见公众号原文]*"


def dl(url: str, alt: str, dest: Path):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            ctype = resp.headers.get("Content-Type", "")
            ext = ".png"
            for e, ct in [(".png", "png"), (".jpg", "jpeg"), (".jpg", "jpg"), (".gif", "gif"), (".webp", "webp")]:
                if ct in ctype:
                    ext = e
                    break
            stem = re.sub(r'[\\/:*?"<>|\s]+', "_", urllib.request.unquote(alt).strip() or "image")[:40] or "image"
            out = dest / f"img_{stem}{ext}"
            out.write_bytes(resp.read())
            return out.name
    except Exception:
        return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    fixed = noted = 0
    for md in sorted((ROOT / "articles").rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        changed = False

        def repl(m):
            nonlocal fixed, noted, changed
            alt_part, url = m.group(1), m.group(2).strip()
            alt = alt_part[2:-1]
            if url.startswith(("http://", "https://")):
                name = dl(url, alt, md.parent)
                if name:
                    fixed += 1
                    changed = True
                    return f"{alt_part}(./{name})"
                noted += 1
                changed = True
                return NOTE
            if not (md.parent / url).exists():
                noted += 1
                changed = True
                return NOTE
            return m.group(0)

        new = IMG_RE.sub(repl, text)
        if changed:
            md.write_text(new, encoding="utf-8")
            print(f"[fix] {md.parent.name[:40]}", flush=True)
    print(f"\n完成：补图 {fixed} 张，替换说明 {noted} 处")


if __name__ == "__main__":
    main()
