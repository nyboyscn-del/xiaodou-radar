#!/usr/bin/env python3
"""豆码雷达竞品监控：抓同类站页面指纹 + 码池规模，变化时输出差异摘要。

用法：python3 competitor_watch.py
状态与快照存 ~/workspace/goals/goal-22/hidden_files/competitors/（state.json + snapshots/）。
页面只比对结构与可见文本（码本身每几分钟变，不算功能更新）；码池只记总数/可能可用数。
"""
import hashlib, json, os, re, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))
BASE = os.path.expanduser("~/workspace/goals/goal-22/hidden_files/competitors")
SNAP = os.path.join(BASE, "snapshots")
STATE = os.path.join(BASE, "state.json")
UA = {"User-Agent": "Mozilla/5.0 xiaodou-radar-competitor-watch"}

SITES = [
    {"key": "good1uck", "name": "good1uck（源头站）",
     "page": "https://good1uck.github.io/xiaodou-codes/",
     "codes": "https://raw.githubusercontent.com/good1uck/xiaodou-codes/main/codes.json",
     "repo": "good1uck/xiaodou-codes"},
    {"key": "zou", "name": "Zou-git0324（二创站）",
     "page": "https://zou-git0324.github.io/xiaodou-codes/",
     "codes": "https://raw.githubusercontent.com/Zou-git0324/xiaodou-codes/main/codes.json",
     "repo": "Zou-git0324/xiaodou-codes"},
    {"key": "ccc", "name": "CCC（多平台池，无站点页）",
     "page": None,
     "codes": "https://raw.githubusercontent.com/CCCcccxxxrrr/xiaodou-codes/main/codes.json",
     "repo": "CCCcccxxxrrr/xiaodou-codes"},
    {"key": "betteropc", "name": "BetterOPC（UGC 获客型）",
     "page": "https://betteropc.com/ai-products/invite-codes/xiaodou",
     "codes": None, "repo": None},
]
KEYWORDS = ["关注", "公众号", "微信", "粉丝群", "QQ群", "Telegram", "登录", "注册", "揭晓",
            "订阅", "推送", "提醒", "分享", "广告", "付费", "提交", "投稿", "举报",
            "收藏", "搜索", "筛选", "倒计时", "通知", "X（", "twitter", "follow"]

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def visible_text(html):
    h = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    h = re.sub(r"<style[\s\S]*?</style>", " ", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "\n", h)
    lines = [re.sub(r"\s+", " ", x).strip() for x in h.split("\n")]
    return [x for x in lines if x]

def code_stats(raw):
    try:
        d = json.loads(raw)
    except Exception:
        return None
    codes = d.get("codes") if isinstance(d, dict) else d
    if not isinstance(codes, list):
        return None
    avail = 0
    for c in codes:
        if not isinstance(c, dict):
            continue
        st = str(c.get("status", ""))
        if c.get("replies") == 0 or "avail" in st or "可用" in st:
            avail += 1
    return {"total": len(codes), "available": avail}

def main():
    os.makedirs(SNAP, exist_ok=True)
    state = {}
    if os.path.exists(STATE):
        try:
            state = json.load(open(STATE, encoding="utf-8"))
        except Exception:
            state = {}
    now = datetime.now(BJ).strftime("%Y-%m-%d %H:%M")
    print(f"竞品监控 {now} 北京时间")
    changed = []
    for s in SITES:
        prev = state.get(s["key"], {})
        cur = {}
        line = [f"- {s['name']}："]
        if s["page"]:
            try:
                html = fetch(s["page"])
                vt = visible_text(html)
                fp = hashlib.sha256("\n".join(vt).encode()).hexdigest()[:12]
                cur["fp"] = fp
                cur["features"] = sorted({k for k in KEYWORDS if any(k in t for t in vt)})
                snap_path = os.path.join(SNAP, s["key"] + ".html")
                if prev.get("fp") and prev["fp"] != fp:
                    old = []
                    if os.path.exists(snap_path):
                        old = visible_text(open(snap_path, encoding="utf-8").read())
                    added = [t for t in vt if t not in set(old)][:8]
                    line.append("页面有更新！新增文本：" + ("；".join(added) if added else "（结构变化）"))
                    changed.append(s["key"])
                elif not prev.get("fp"):
                    line.append("已建基线")
                else:
                    line.append("页面无变化")
                open(snap_path, "w", encoding="utf-8").write(html)
                line.append("功能词：" + ("、".join(cur["features"]) if cur["features"] else "无"))
            except Exception as e:
                line.append(f"页面抓取失败 {type(e).__name__}")
        if s["codes"]:
            try:
                cs = code_stats(fetch(s["codes"]))
                if cs:
                    cur["codes"] = cs
                    delta = ""
                    if prev.get("codes"):
                        delta = f"（上次 total {prev['codes']['total']}/可用 {prev['codes']['available']}）"
                    line.append(f"码池 total {cs['total']} / 可能可用 {cs['available']}{delta}")
            except Exception as e:
                line.append(f"码池抓取失败 {type(e).__name__}")
        if s["repo"]:
            try:
                meta = json.loads(fetch(f"https://api.github.com/repos/{s['repo']}"))
                cur["repo_pushed"] = meta.get("pushed_at")
                cur["stars"] = meta.get("stargazers_count")
                line.append(f"仓库 pushed {meta.get('pushed_at')} / star {meta.get('stargazers_count')}")
            except Exception:
                pass
        state[s["key"]] = cur
        print(" ".join(line))
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("变化站点：" + ("、".join(changed) if changed else "无"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
