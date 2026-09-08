# -*- coding: utf-8 -*-
"""从 D:\\AIWorkSpace\\media\\final 迁移文章到语料库（只复制不移动）。

- 每篇文章: <系列>/<原标题>/ 目录，含同名 md（注入 frontmatter）+ 图片
- OSS 签名/公众号图片链接优先匹配本地同名图改写为相对路径，失败则尝试下载，再失败标记 broken
- visibility 初判: carpaint/rendering = public，其余 = local（Phase 3 复核后调整）
- 产出 MIGRATION-REPORT.md
"""
import datetime
import re
import shutil
import sys
import urllib.request
from pathlib import Path

SRC = Path(r"D:\AIWorkSpace\media\final")
ROOT = Path(__file__).resolve().parent.parent
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
SKIP_DIRS = {".codely", ".codely-cli", ".cursor-history", "demo_headlights", "diagrams",
             "getnote_import", "render_cover_scripts", "video_production", "浮生散记"}
IMG_RE = re.compile(r"(!\[[^\]]*\])\(([^)]+)\)")


def classify(name: str):
    """返回 (series, visibility)。"""
    if name.startswith("会议"):
        return "drama", "local"
    if re.search(r"[（(]case-\d+[）)]", name):
        return "perf", "local"
    if "车漆" in name:
        return "carpaint", "public"
    if name.startswith("座舱3D HMI场景") or name.startswith("座舱3D HMI材质"):
        return "rendering", "public"
    if name.startswith("座舱3D HMI性能"):
        return "perf", "local"
    if name.startswith("座舱3D HMI稳定性"):
        return "stability", "local"
    if "本地化" in name:
        return "localization", "local"
    if "框架" in name:
        return "framework", "local"
    if "工具链" in name or name.startswith("Unity编辑器小工具") or "数据回放" in name:
        return "tools", "local"
    if name.startswith(("智驾 SR", "智驾SR", "车机智驾", "车载智驾")):
        return "sr", "local"
    return "misc", "local"


def find_article_md(src_dir: Path):
    exact = src_dir / f"{src_dir.name}.md"
    if exact.exists():
        return exact, ""
    mds = [p for p in src_dir.glob("*.md") if not p.name.startswith("~")]
    if len(mds) == 1:
        return mds[0], f"md 文件名与文件夹不一致: {mds[0].name}"
    if not mds:
        return None, "无 md 文件"
    return None, f"多个 md 候选: {[p.name for p in mds]}"


def match_local_image(src_dir: Path, alt: str):
    alt = urllib.request.unquote(alt).strip()
    stem = Path(alt).stem
    for f in src_dir.iterdir():
        if f.suffix.lower() in IMG_EXT and f.stem == stem:
            return f
    return None


def try_download(url: str, alt: str, dest_dir: Path, budget: dict):
    """已知过期的签名链接直接放弃；其余限速限时限量尝试。"""
    if "Expires=" in url or "umiwi.com" in url or budget["left"] <= 0:
        return None
    budget["left"] -= 1
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
            out = dest_dir / f"{stem}{ext}"
            out.write_bytes(resp.read())
            return out
    except Exception:
        return None


def rewrite_images(md_text: str, src_dir: Path, dest_dir: Path, report: dict, budget: dict):
    def repl(m):
        alt_part, url = m.group(1), m.group(2).strip()
        alt = alt_part[2:-1]
        if url.startswith(("http://", "https://")):
            local = match_local_image(src_dir, alt)
            if local:
                shutil.copy2(local, dest_dir / local.name)
                report["img_matched"] += 1
                return f"{alt_part}(./{local.name})"
            dl = try_download(url, alt, dest_dir, budget)
            if dl:
                report["img_downloaded"] += 1
                return f"{alt_part}(./{dl.name})"
            report["broken"].append(url[:120])
            return m.group(0)
        rel = (src_dir / url).resolve()
        if rel.exists() and rel.suffix.lower() in IMG_EXT:
            shutil.copy2(rel, dest_dir / rel.name)
            report["img_local"] += 1
            return f"{alt_part}(./{rel.name})"
        report["broken"].append(url[:120])
        return m.group(0)
    return IMG_RE.sub(repl, md_text)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    rows, skipped, broken_total = [], [], []
    budget = {"left": 40}
    for src_dir in sorted(SRC.iterdir()):
        if not src_dir.is_dir() or src_dir.name in SKIP_DIRS or src_dir.name.startswith("."):
            continue
        if "未发表" in src_dir.name:
            skipped.append((src_dir.name, "未发表"))
            continue
        md, note = find_article_md(src_dir)
        if md is None:
            skipped.append((src_dir.name, note))
            continue
        series, visibility = classify(src_dir.name)
        tier = "articles" if visibility == "public" else "local"
        dest_dir = ROOT / tier / series / src_dir.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        report = {"img_matched": 0, "img_downloaded": 0, "img_local": 0, "broken": []}
        text = md.read_text(encoding="utf-8", errors="replace")
        text = rewrite_images(text, src_dir, dest_dir, report, budget)
        no_m = re.search(r"[（(](\d+)[）)]", src_dir.name)
        no = no_m.group(1) if no_m else ""
        date = datetime.datetime.fromtimestamp(md.stat().st_mtime).strftime("%Y-%m-%d")
        fm = (f"---\ntitle: \"{src_dir.name}\"\ndate: {date}\nseries: {series}\nno: {no}\n"
              f"status: published\nvisibility: {visibility}\nwechat_url: \"\"\n---\n\n")
        (dest_dir / md.name).write_text(fm + text, encoding="utf-8")
        n_imgs = sum(1 for f in dest_dir.iterdir() if f.suffix.lower() in IMG_EXT)
        rows.append({"title": src_dir.name, "series": series, "tier": tier, "date": date,
                     "no": no, "note": note, **report, "imgs_in_dest": n_imgs})
        broken_total += report["broken"]
        print(f"[{len(rows):3d}] {series:12s} {src_dir.name[:36]}  图:{report['img_matched']}匹/{report['img_downloaded']}载/{len(report['broken'])}损", flush=True)

    lines = ["# 迁移报告", f"\n迁移 {len(rows)} 篇；跳过 {len(skipped)} 项\n"]
    lines.append("\n## 跳过清单\n")
    for name, why in skipped:
        lines.append(f"- {name}（{why}）")
    lines.append("\n## 迁移明细\n")
    lines.append("| 标题 | 系列 | 层 | 日期 | no | 图片(匹配/下载/本地) | 破损链 | 备注 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(f"| {r['title'][:40]} | {r['series']} | {r['tier']} | {r['date']} | {r['no']} "
                     f"| {r['img_matched']}/{r['img_downloaded']}/{r['img_local']} | {len(r['broken'])} | {r['note']} |")
    if broken_total:
        lines.append("\n## 破损图片链接（需人工处理）\n")
        for b in broken_total:
            lines.append(f"- {b}")
    rep = ROOT / "MIGRATION-REPORT.md"
    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"迁移 {len(rows)} 篇 → 报告 {rep}")
    print(f"破损链接 {len(broken_total)} 个；跳过 {len(skipped)} 项")


if __name__ == "__main__":
    main()
