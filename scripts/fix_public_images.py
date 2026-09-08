# -*- coding: utf-8 -*-
"""一次性修复公开层文章的破损 OSS 图片链接：按出现顺序映射到本地图。"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(r"D:\AIWorkSpace\media\final")

# 文章文件夹名 -> 按出现顺序映射的本地图片名
FIXES = {
    "座舱3D HMI材质：车漆（一）分层结构与整体构成": ["图1 效果图.png"],
    "座舱3D HMI材质：车漆（二）Base 层：主色、边缘色与过渡": ["图1.png", "图2.png"],
    "座舱3D HMI材质：车漆（三）Flake 层：金属颗粒与珠光": ["图1.png", "图2.png", "图3.png"],
    "座舱3D HMI场景：Dual Kawase 模糊的工程思维": ["图1.png", "图2.png"],
    "座舱3D HMI场景：充电特效": ["flow-charge-dissolve.png"],
    "座舱3D HMI场景：车灯光柱的体积光效果": ["图1.png", "图2.png"],
}

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    oss = re.compile(r"(!\[[^\]]*\])\(https?://[^)]+\)")
    for title, images in FIXES.items():
        md = next((ROOT / "articles").rglob(f"{title}/*.md"))
        src_dir = SRC / title
        idx = 0
        def repl(m):
            nonlocal idx
            if idx >= len(images):
                return m.group(0)
            name = images[idx]
            idx += 1
            shutil.copy2(src_dir / name, md.parent / name)
            return f"{m.group(1)}(./{name})"
        text = md.read_text(encoding="utf-8")
        text = oss.sub(repl, text)
        md.write_text(text, encoding="utf-8")
        print(f"{title[:30]}: 替换 {idx}/{len(images)} 条", flush=True)
        if idx < len(images):
            print(f"  警告: 映射列表比实际破损链接多 {len(images)-idx} 条，未用完: {images[idx:]}", flush=True)

if __name__ == "__main__":
    main()
