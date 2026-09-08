# -*- coding: utf-8 -*-
"""①充放电溶解降级 draft；②PDC/Layer 两篇标题对齐公众号原题（文件夹+frontmatter）。"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_dir(title: str) -> Path | None:
    for tier in ("articles", "local"):
        for series in (ROOT / tier).iterdir():
            if series.is_dir():
                d = series / title
                if d.exists():
                    return d
    return None


def patch_fm(d: Path, **kv):
    for md in d.glob("*.md"):
        t = md.read_text(encoding="utf-8")
        for k, v in kv.items():
            t = re.sub(rf"^{k}: .*$", f"{k}: {v}", t, count=1, flags=re.M)
        md.write_text(t, encoding="utf-8")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # ① 充放电溶解降级
    d = find_dir("座舱3D HMI材质：车漆（七）充放电溶解")
    dest = ROOT / "local/carpaint/座舱3D HMI材质：车漆（七）充放电溶解"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(d), str(dest))
    patch_fm(dest, status="draft", visibility="local", no="")
    print("车漆（七）充放电溶解 → local/draft")

    # ② 标题对齐
    for old_t, new_t in [
        ("智驾 SR 开发：PDC 环绕波纹的单材质实现", "智驾 SR 开发：PDC 环绕波纹的单材质工程实践"),
        ("智驾 SR 开发：基于 Layer 的场景分层管理", "智驾 SR 开发：场景元素的 Layer 化分层管理"),
    ]:
        d = find_dir(old_t)
        nd = d.parent / new_t
        d.rename(nd)
        patch_fm(nd, title=f'"{new_t}"' if False else new_t)
        # patch_fm 用 {k}: {v} 模板，title 需要带引号
        for md in nd.glob("*.md"):
            t = md.read_text(encoding="utf-8")
            t = re.sub(r'^title: .*$', f'title: "{new_t}"', t, count=1, flags=re.M)
            md.write_text(t, encoding="utf-8")
        print(f"标题对齐: {new_t}")


if __name__ == "__main__":
    main()
