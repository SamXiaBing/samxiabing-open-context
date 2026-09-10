# -*- coding: utf-8 -*-
"""GitHub 收尾 v2（修正顺序）：①改名 cockpit-hmi-notes → samxiabing-open-context（remote 已指向新名，必须先改）
②推送 ③验证。"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(r"D:\AIWorkSpace\articles-corpus")
TOK = Path(r"D:\AIWorkSpace\.githubtoken").read_text(encoding="utf-8").strip()
OLD = "SamXiaBing/cockpit-hmi-notes"
NEW = "samxiabing-open-context"
DESC = ("SamXiaBing's open context - public writing corpus of a cockpit 3D HMI engineer: "
        "car paint rendering, scene materials, performance, stability, framework, localization, SR. "
        "Chinese deep-dives, CC BY-NC-ND 4.0.")


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def run_git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def api(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {TOK}", "Accept": "application/vnd.github+json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or "{}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # ① 改名（remote 已指向新名，必须先改）
    renamed = False
    # 若已被上次部分执行改过名则跳过
    try:
        r = api("GET", f"repos/SamXiaBing/{NEW}")
        renamed = True
        log(f"新名仓库已存在（可能之前已改名成功）: {r['html_url']}")
    except Exception:
        pass
    if not renamed:
        for i in range(30):
            try:
                r = api("PATCH", f"repos/{OLD}", {"name": NEW, "description": DESC})
                renamed = True
                log(f"改名成功: {r['html_url']}")
                break
            except Exception as e:
                log(f"改名失败（{i+1}/30）: {e}")
                time.sleep(120)
        if not renamed:
            log("FATAL: 改名失败")
            sys.exit(1)

    # ② 推送
    for i in range(40):
        p = run_git("push", "-u", "origin", "main")
        if p.returncode == 0:
            log(f"push OK (第 {i+1} 次)")
            break
        log(f"push 失败（{i+1}/40）: {(p.stderr or p.stdout).strip()[-90:]}")
        time.sleep(120)
    else:
        log("FATAL: push 全部重试失败")
        sys.exit(1)

    # ③ 验证
    run_git("fetch", "origin")
    tip = run_git("log", "origin/main", "-1", "--format=%h %ad %s", "--date=iso")
    log(f"FINAL remote=SamXiaBing/{NEW} tip={tip.stdout.strip()}")


if __name__ == "__main__":
    main()
