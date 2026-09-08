# -*- coding: utf-8 -*-
"""按公众号 91 篇清单校准语料库：
①回填真实发表日期；②车漆（九）天气特效层恢复为（六）；③20 篇未发表草稿降级 local/draft。
标题变体映射：清单标题 ↔ 语料库文件夹标题。"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPARE = json.loads((ROOT / "wechat_compare.json").read_text(encoding="utf-8"))

VARIANT = {  # 清单标题 -> 语料库标题
    "座舱3D HMI材质：车漆（六）天气特效层": "座舱3D HMI材质：车漆（九）天气特效层",
    "智驾 SR 开发：场景元素的 Layer 化分层管理": "智驾 SR 开发：基于 Layer 的场景分层管理",
    "智驾 SR 开发：PDC 环绕波纹的单材质工程实践": "智驾 SR 开发：PDC 环绕波纹的单材质实现",
}

DEMOTE = [  # 不在 91 清单内的未发表草稿
    "座舱3D HMI场景：高性能模糊算法DualKawaseBlur",
    "座舱3D HMI开发框架：FrameworkLinkedList，节点池化的链表",
    "座舱3D HMI性能：Mesh每帧全量重建",
    "座舱3D HMI材质：车漆（六）车衣遮罩与样式复用",
    "智驾 SR 开发：减速带的模块化拼装 三维物体不自拉伸而自动延长",
    "座舱3D HMI性能：AVP车位框DrawCall合批优化（case-06）",
    "座舱3D HMI性能：MapRender网格构建内存优化（case-15）",
    "座舱3D HMI性能：后台渲染控制与CPU优化（case-12）",
    "座舱3D HMI性能：对象池设计陷阱——回收也要讲度（case-02）",
    "座舱3D HMI性能：感知数据插帧与防抖优化（case-13）",
    "座舱3D HMI性能：数字车衣Addressable动态加载（case-07）",
    "座舱3D HMI性能：高频消息GC优化——零分配热路径（case-08）",
    "座舱3D HMI稳定性：JNI跨线程通信的稳定性演化（case-05）",
    "座舱3D HMI稳定性：离屏渲染黑屏诊断与启动时序（case-03）",
    "座舱3D HMI稳定性：语音形象稳定性保障——从ANR到自愈（case-10）",
    "座舱3D HMI稳定性：长时间Monkey测试ANR防护（case-11）",
    "车机端 3D HMI 冷启动性能优化：从1427ms到达标（case-09）",
    "三个月，三款AI编程工具，我把车机生成式UI渲染器开源了",
    "会议戮：3D组内VP节点攻坚计划 (活人感版)",
    "会议“戮”：按键音，谁来播？",
]


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
    # ① 回填发表日期
    n = 0
    for item in COMPARE["matched"]:
        d = find_dir(item["wechat"])
        if d:
            patch_fm(d, date=item["date"])
            n += 1
    # ② 天气特效层恢复（六）
    old = ROOT / "articles/carpaint/座舱3D HMI材质：车漆（九）天气特效层"
    new = ROOT / "articles/carpaint/座舱3D HMI材质：车漆（六）天气特效层"
    if old.exists():
        old.rename(new)
        patch_fm(new, title="座舱3D HMI材质：车漆（六）天气特效层", no=6, date="2026-08-26")
        print("天气特效层恢复为（六），日期 2026-08-26")
    # 变体标题日期
    for wechat_title, corpus_title in VARIANT.items():
        if "天气特效层" in wechat_title:
            continue
        d = find_dir(corpus_title)
        date = next(x["date"] for x in COMPARE["missing"] if x["title"] == wechat_title)
        if d:
            patch_fm(d, date=date)
            n += 1
    print(f"回填真实发表日期 {n} 篇")

    # ③ 草稿降级
    moved = 0
    for title in DEMOTE:
        d = find_dir(title)
        if d is None:
            print(f"  [未找到] {title}")
            continue
        meta, _ = None, None
        md = next(d.glob("*.md"))
        m = re.search(r"^series: (.*)$", md.read_text(encoding="utf-8"), re.M)
        series = m.group(1).strip()
        dest = ROOT / "local" / series / title
        dest.parent.mkdir(parents=True, exist_ok=True)
        if d.exists():
            shutil.move(str(d), str(dest))
        patch_fm(dest, status="draft", visibility="local")
        moved += 1
    print(f"降级草稿 {moved} 篇 → local/ (status: draft)")


if __name__ == "__main__":
    main()
