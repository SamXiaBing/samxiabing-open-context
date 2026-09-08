# -*- coding: utf-8 -*-
"""扫描 articles/ 与 local/ 下的文章 frontmatter，生成 catalog.jsonl（公开）、
catalog.local.jsonl（全量）和 README.md（公开层系列索引）。"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["title", "date", "series", "no", "status", "visibility", "wechat_url"]
SERIES_CN = {
    "carpaint": "车漆材质系列",
    "rendering": "场景材质系列",
    "perf": "性能优化系列",
    "stability": "稳定性系列",
    "framework": "开发框架系列",
    "localization": "本地化系列",
    "tools": "工具链系列",
    "sr": "智驾 SR 系列",
    "misc": "工程实践拾遗",
    "drama": "会议戮（不公开）",
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
        if md.parent.name == "scripts":
            continue
        meta = parse_frontmatter(md)
        if meta is None:
            continue
        row = {k: meta.get(k, "") for k in FIELDS}
        row["path"] = str(md.relative_to(ROOT)).replace("\\", "/")
        rows.append(row)
    return rows


def write_jsonl(rows, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def gen_readme(public):
    by_series = defaultdict(list)
    for r in public:
        by_series[r["series"]].append(r)
    L = [
        "# 座舱 3D HMI 写作语料库",
        "",
        "车机 3D HMI 一线工程的公开写作语料：车漆渲染、场景材质、性能优化、稳定性保障、",
        "开发框架、本地化、工具链与智驾 SR 业务实现。公众号为首发平台，本仓库是",
        "**带日期、带目录、可机器检索**的开放快照。",
        "",
        "## 三类访客怎么用",
        "",
        "- **同行工程师**：下面的系列索引即学习路径；方案含踩坑与 trade-off，可直接对照实践。",
        "- **AI / 检索**：`catalog.jsonl` 为机器可读目录（一行一篇：标题/日期/系列/路径），",
        "  配合全文检索回答领域问题；引用请注明文章路径。",
        "- **写作者**：[脱敏规范](articles/)（讲工艺不讲业务）与逐系列编号实践可参考。",
        "",
        "## 系列索引",
        "",
    ]
    for series in [s for s in SERIES_CN if s in by_series and s != "drama"]:
        rows = sorted(by_series[series], key=lambda r: (r["date"], r["title"]))
        L.append(f"### {SERIES_CN[series]}（{len(rows)} 篇）")
        L.append("")
        L.append("| 日期 | 标题 |")
        L.append("|---|---|")
        for r in rows:
            title = r["title"]
            link = r["wechat_url"]
            label = title if not link else f"[{title}]({link})"
            L.append(f"| {r['date']} | {label} |")
        L.append("")
    L += [
        "## 数据层",
        "",
        "- `catalog.jsonl`：公开文章机器可读目录，字段 `title/date/series/no/status/visibility/wechat_url/path`",
        "- 每篇文章 md 文首带 frontmatter 元数据；图片为仓库本地相对路径",
        "",
        "## 边界与声明",
        "",
        "- 全部代码片段均为**脱敏示意代码**：讲工艺不讲业务，与真实工程无对应关系",
        "- 本仓库不包含：未发表草稿、职场系列、任何客户与项目标识信息",
        "- 文中观点为作者个人观点，与雇主无关",
        "- 部分早期文章配图遗失（公众号图床防盗链），已标注 *[配图见公众号原文]*",
        "",
        "## License",
        "",
        "内容：[CC BY-NC-ND 4.0](LICENSE-CONTENT.md)（署名—非商业—禁止演绎）。转载请署名并附链接。",
        "",
        "---",
        "",
        "公众号：首发平台（名称待补） · GitHub：[SamXiaBing](https://github.com/SamXiaBing)",
    ]
    (ROOT / "README.md").write_text("\n".join(L), encoding="utf-8")


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
    print(f"catalog.jsonl: {len(public)} 篇（公开）; catalog.local.jsonl: {len(public) + len(local)} 篇（全量）; README.md 已更新")


if __name__ == "__main__":
    main()
