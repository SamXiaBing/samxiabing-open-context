# -*- coding: utf-8 -*-
"""扫描 articles/ 与 local/ 下的文章 frontmatter，生成 catalog.jsonl（公开）、
catalog.local.jsonl（全量）、README.md（English primary）与 README.zh-CN.md（中文镜像）。

每篇中文 md 可带同目录同名 .en.md 英文版（frontmatter 含 lang: en 与英文 title），
catalog 行会附 title_en/path_en，README 双语索引。"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["title", "date", "series", "no", "status", "visibility", "wechat_url"]
SERIES = {
    "carpaint": ("Car Paint Materials", "车漆材质系列"),
    "rendering": ("Scene Materials & Effects", "场景材质系列"),
    "perf": ("Performance", "性能优化系列"),
    "stability": ("Stability", "稳定性系列"),
    "framework": ("Dev Framework", "开发框架系列"),
    "localization": ("Localization", "本地化系列"),
    "tools": ("Toolchain", "工具链系列"),
    "sr": ("SR · Surround Rendering", "智驾 SR 系列"),
    "misc": ("Engineering Notes", "工程实践拾遗"),
    "drama": ("Meeting Drama (private)", "会议戮（不公开）"),
}


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
        if md.parent.name == "scripts" or md.name.endswith(".en.md"):
            continue
        meta = parse_frontmatter(md)
        if meta is None:
            continue
        row = {k: meta.get(k, "") for k in FIELDS}
        row["path"] = str(md.relative_to(ROOT)).replace("\\", "/")
        en = md.with_name(md.stem + ".en.md")
        if en.exists():
            en_meta = parse_frontmatter(en)
            if en_meta:
                row["title_en"] = en_meta.get("title", "")
                row["path_en"] = str(en.relative_to(ROOT)).replace("\\", "/")
        rows.append(row)
    return rows


def write_jsonl(rows, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def series_tables(public, lang: int) -> list[str]:
    """lang 0=英文主版, 1=中文镜像"""
    by = defaultdict(list)
    for r in public:
        by[r["series"]].append(r)
    L = []
    for s in [s for s in SERIES if s in by and s != "drama"]:
        rows = sorted(by[s], key=lambda r: (r["date"], r["title"]))
        name = f"{SERIES[s][lang]}（{SERIES[s][0]}）" if lang == 1 else SERIES[s][0]
        L.append(f"### {name} ({len(rows)})" if lang == 0 else f"### {name}（{len(rows)} 篇）")
        L.append("")
        if lang == 0:
            L.append("| Date | Title | 中文 |")
            L.append("|---|---|---|")
        else:
            L.append("| 日期 | 标题 | English |")
            L.append("|---|---|---|")
        for r in rows:
            en_title = r.get("title_en", "")
            en_link = f"[{en_title}]({r['path_en'].replace(chr(92), '/')})" if en_title else ""
            if lang == 0:
                zh_cell = f"[{r['title']}]({r['path']})" if r["wechat_url"] else r["title"]
                L.append(f"| {r['date']} | {en_link or r['title']} | {zh_cell} |")
            else:
                zh_label = f"[{r['title']}]({r['wechat_url']})" if r["wechat_url"] else r["title"]
                L.append(f"| {r['date']} | {zh_label} | {en_link} |")
        L.append("")
    return L


def gen_readme(public):
    n = len(public)
    n_en = sum(1 for r in public if r.get("title_en"))
    en = [
        "# SamXiaBing · Open Context",
        "",
        "Public writing corpus of a **cockpit 3D HMI engineer** working on mass-production",
        "vehicle infotainment: car paint rendering, scene materials, performance, stability,",
        "runtime framework, localization, toolchain, and Surround Rendering (SR) business logic.",
        "",
        "Articles are written in **Chinese** (deep technical dives, published weekly on WeChat);",
        "this repository is the **dated, structured, machine-readable snapshot** of that work —",
        "my open context, in the sense of [lizheng-open-context](https://github.com/sunyuzheng/lizheng-open-context):",
        "not a persona prompt, but a source-grounded corpus you can search, cite, and build on.",
        f"English translations are provided alongside each article (`*.en.md`) — {n_en}/{n} available.",
        "",
        "## How to use this repo",
        "",
        "- **Engineers (Unity / automotive HMI)**: the series index below is a learning path;",
        "  solutions include pitfalls and trade-offs from production code (desensitized).",
        "- **AI agents / retrieval**: `catalog.jsonl` is a machine-readable index, one JSON object",
        "  per article (`title / title_en / date / series / no / status / wechat_url / path`).",
        "  Pair it with full-text search; cite the article path when answering.",
        "- **Writers**: the desensitization discipline (technique over business detail) and",
        "  per-series numbering are reusable practices.",
        "",
        "## Series index",
        "",
        f"{n} published articles. **Title** links to the English translation; **中文** links to",
        "the original Chinese article.",
        "",
    ]
    en += series_tables(public, 0)
    en += [
        "## Data layer",
        "",
        "- Each article lives at `articles/<series>/<title>/` with a frontmatter header",
        "  (`title / date / series / no / status / visibility / wechat_url`) and local images;",
        "  the English translation sits next to it as `<title>.en.md`.",
        "- `scripts/build_catalog.py` regenerates the catalogs and both READMEs;",
        "  `scripts/validate_corpus.py` checks integrity.",
        "",
        "## Boundary & license",
        "",
        "- All code snippets are **desensitized samples**: technique over business detail,",
        "  no mapping to any real project, client, or employer.",
        "- Not included: unpublished drafts, workplace fiction, client or project identifiers.",
        "- Opinions are the author's own, not the employer's.",
        "- A few early figures are lost to the WeChat image-hosting hotlink policy and are",
        "  marked *[see the original WeChat article]*.",
        "",
        "## License",
        "",
        "Content: [CC BY-NC-ND 4.0](LICENSE-CONTENT.md) — attribution required, non-commercial,",
        "no derivatives. Code snippets follow the same terms.",
        "",
        "---",
        "",
        "WeChat official account: first-publication venue · GitHub: [SamXiaBing](https://github.com/SamXiaBing)",
        "",
        "> 中文版说明见 [README.zh-CN.md](README.zh-CN.md)",
    ]

    zh = [
        "# 座舱 3D HMI 写作语料库（SamXiaBing · Open Context）",
        "",
        "车机 3D HMI 一线工程的公开写作语料：车漆渲染、场景材质、性能优化、稳定性保障、",
        "开发框架、本地化、工具链与智驾 SR 业务实现。公众号为首发平台，本仓库是",
        "**带日期、带目录、可机器检索**的开放快照——对标 [lizheng-open-context](https://github.com/sunyuzheng/lizheng-open-context)，",
        "不是人格提示词，而是有出处、有时间、可引用、可继续开发的公共材料。",
        "",
        "## 三类访客怎么用",
        "",
        "- **同行工程师**：下面的系列索引即学习路径；方案含踩坑与 trade-off，可直接对照实践。",
        "- **AI / 检索**：`catalog.jsonl` 为机器可读目录（一行一篇），配合全文检索回答领域问题；",
        "  引用请注明文章路径。",
        "- **写作者**：脱敏规范（讲工艺不讲业务）与逐系列编号实践可参考。",
        "",
        "## 系列索引",
        "",
        f"共 {n} 篇已发表文章，其中 {n_en} 篇提供英文版（*.en.md，与原文同目录）。英文主版索引见 [README.md](README.md)。",
        "",
    ]
    zh += series_tables(public, 1)
    zh += [
        "## 数据层",
        "",
        "- 每篇文章位于 `articles/<系列>/<标题>/`，md 文首带 frontmatter 元数据，图片为本地相对路径，",
        "  英文版为同目录 `<标题>.en.md`",
        "- `scripts/build_catalog.py` 重新生成目录与两个 README；`scripts/validate_corpus.py` 校验完整性",
        "",
        "## 边界与声明",
        "",
        "- 全部代码片段均为**脱敏示意代码**：讲工艺不讲业务，与真实工程无对应关系",
        "- 本仓库不包含：未发表草稿、职场系列、任何客户与项目标识信息",
        "- 文中观点为作者个人观点，与雇主无关",
        "- 部分早期文章配图因公众号图床防盗链遗失，已标注 *[配图见公众号原文]*",
        "",
        "## License",
        "",
        "内容：[CC BY-NC-ND 4.0](LICENSE-CONTENT.md)（署名—非商业—禁止演绎）。转载请署名并附链接。",
        "",
        "---",
        "",
        "公众号：首发平台（名称待补） · GitHub：[SamXiaBing](https://github.com/SamXiaBing)",
    ]
    (ROOT / "README.md").write_text("\n".join(en), encoding="utf-8")
    (ROOT / "README.zh-CN.md").write_text("\n".join(zh), encoding="utf-8")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    public = collect(ROOT / "articles")
    local = collect(ROOT / "local")
    public.sort(key=lambda r: (r["date"], r["path"]))
    local.sort(key=lambda r: (r["date"], r["path"]))
    write_jsonl(public, ROOT / "catalog.jsonl")
    write_jsonl(public + local, ROOT / "catalog.local.jsonl")
    gen_readme(public)
    n_en = sum(1 for r in public if r.get("title_en"))
    print(f"catalog.jsonl: {len(public)} 篇（公开，英文版 {n_en}）; catalog.local.jsonl: {len(public) + len(local)} 篇（全量）; README x2 已更新")


if __name__ == "__main__":
    main()
