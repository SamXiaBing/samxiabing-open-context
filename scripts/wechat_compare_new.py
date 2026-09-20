# -*- coding: utf-8 -*-
"""比对微信已发表清单与语料库，定位 media/final 中的新文章文件夹。"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\AIWorkSpace\articles-corpus")
SRC = Path(r"D:\AIWorkSpace\media\final")

WECHAT = [
    ("座舱3D HMI 开发框架：Command 机制的设计与用途", "2026-09-18"),
    ("智驾 SR 开发：行人动画选 Animator 还是 VAT？", "2026-09-17"),
    ("【318位座舱专家已报名】比亚迪、小米、蔚来、理想、小鹏、吉利、奇瑞、长安、赛力斯邀您面对面聊座舱场景解题新思路", "2026-09-16"),
    ("座舱3D HMI材质：轮毂——从通用 Lit 到 MatCap", "2026-09-16"),
    ("会议“戮”：谁杀了我的进程？", "2026-09-15"),
    ("座舱3D HMI性能：对象池接入与回收的对称性", "2026-09-14"),
    ("座舱3D HMI 开发框架：MVC架构的工程化落地", "2026-09-11"),
    ("智驾 SR 开发：车位点选的几何检测方案", "2026-09-10"),
    ("座舱3D HMI材质：透明车壳材质的光效拆解", "2026-09-09"),
    ("会议“戮”：按键音，谁来播？", "2026-09-08"),
    ("座舱3D HMI性能：内存泄漏？关于“回收”的陷阱", "2026-09-07"),
]


def norm(s: str) -> str:
    s = s.lower().replace("some/ip", "someip")
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", s)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    known = set()
    for line in (ROOT / "catalog.local.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            known.add(norm(json.loads(line)["title"]))
    for t, d in WECHAT:
        n = norm(t)
        if n in known:
            print(f"[已在库] {t[:42]} {d}")
            continue
        hits = [f.name for f in SRC.iterdir() if f.is_dir() and norm(f.name) == n]
        if hits:
            print(f"[找到文件夹] {hits[0]}  微信日期 {d}")
        else:
            fuzzy = [f.name for f in SRC.iterdir() if f.is_dir() and (n in norm(f.name) or norm(f.name) in n)]
            print(f"[未找到] {t[:42]} {d}  模糊候选: {fuzzy[:2]}")


if __name__ == "__main__":
    main()
