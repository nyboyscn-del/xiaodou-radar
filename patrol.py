#!/usr/bin/env python3
"""豆码雷达巡检：多源聚合小豆邀请码 -> codes.json

数据源（全部公开）：
  A. good1uck/xiaodou-codes 的 codes.json（上游巡检站，约 5 分钟更新）
  B. CCCcccxxxrrr/xiaodou-codes 的 codes.json（多平台补充，字段不同，做映射）
  C. 自有 X 搜索（twitterapi 连接器，可选；失败/限额时跳过，不阻断 A/B）

规则（对齐社区站通行口径）：
  - 码必须是 6 位字母数字、字母与数字都要有；全字母英文词（OPENAI/PRINTF 等）剔除
  - 状态按原帖回复数推断：0 回复 = maybe_available，否则 maybe_used
  - 同码去重，保留信息更全/更新的一条；新码在前（按发帖时间倒序）
  - 已过期（expires 已过）的不收录；confirmed_used 不收录
"""
import json, re, subprocess, sys, urllib.request
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))
HERE = "/home/hatch/workspace/xiaodou-radar"
OUT = HERE + "/codes.json"
DENY = {"OPENAI", "CLOUDX", "GOOGLE", "GEMINI", "CURSOR", "CLAUDE", "GROKAI",
        "PRINTF", "OUTPUT", "STRING", "RETURN", "IMPORT", "SELECT", "INSERT"}

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 xiaodou-radar"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def valid_code(c):
    if not re.fullmatch(r"[A-Z0-9]{6}", c or ""):
        return False
    if not (re.search(r"[A-Z]", c) and re.search(r"[0-9]", c)):
        return False
    if c in DENY:
        return False
    return True

def parse_expires(s):
    if not s:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})", s)
    if not m:
        return None
    y, mo, d, h, mi = map(int, m.groups())
    return datetime(y, mo, d, h, mi, tzinfo=BJ)

def norm_good(x):
    return {
        "code": x.get("code", "").upper(),
        "postId": x.get("postId", ""),
        "author": x.get("author", ""),
        "postUrl": x.get("postUrl", ""),
        "postedAt": x.get("postedAt", ""),
        "postedAtUtc": x.get("postedAtUtc", ""),
        "replyCount": x.get("replyCount", 0),
        "status": x.get("status", "maybe_used"),
        "expires": x.get("expires", ""),
        "platform": x.get("platform", "X"),
        "source": "good1uck",
    }

def norm_ccc(x):
    pub = x.get("publishedAt", "")
    posted = ""
    try:
        dt = datetime.fromisoformat(pub)
        posted = dt.astimezone(BJ).strftime("%Y-%m-%d %H:%M:%S") + " 北京时间"
    except Exception:
        posted = pub
    rep = x.get("replies", 0) or 0
    return {
        "code": (x.get("code") or "").upper(),
        "postId": "",
        "author": (x.get("author") or "").lstrip("@"),
        "postUrl": x.get("url", ""),
        "postedAt": posted,
        "postedAtUtc": "",
        "replyCount": rep,
        "status": "maybe_available" if rep == 0 else "maybe_used",
        "expires": "",
        "platform": x.get("platform", "X"),
        "source": "ccc",
    }

CODE_RE = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{6})(?![A-Z0-9])")

def own_search(existing):
    """自有 X 搜索增量。失败返回 []，不抛。"""
    out = []
    try:
        p = subprocess.run(
            ["python3", "/home/hatch/workspace/custom-connectors/custom.twitterapi/bin/twitterapi.py",
             "search", "小豆邀请码", "--type", "Latest"],
            capture_output=True, text=True, timeout=60)
        data = json.loads(p.stdout)
        tweets = data.get("tweets", data if isinstance(data, list) else [])
        for t in tweets:
            text = (t.get("text") or "")
            if "小豆" not in text:
                continue
            author = ((t.get("author") or {}).get("userName") or "")
            tid = str(t.get("id") or "")
            created = t.get("createdAt") or ""
            posted, posted_utc = "", ""
            try:
                dt = datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y")
                posted = dt.astimezone(BJ).strftime("%Y-%m-%d %H:%M:%S") + " 北京时间"
                posted_utc = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            except Exception:
                pass
            exp = ""
            m = re.search(r"有效期至[：:\s]*(\d{4}-\d{2}-\d{2}[ ]?\d{0,2}:?\d{0,2})", text)
            if m:
                exp = m.group(1).strip()
            rep = t.get("replyCount", 0) or 0
            for cand in CODE_RE.findall(text.upper()):
                if not valid_code(cand) or cand in existing:
                    continue
                out.append({
                    "code": cand, "postId": tid, "author": author,
                    "postUrl": f"https://x.com/{author}/status/{tid}" if author and tid else "",
                    "postedAt": posted, "postedAtUtc": posted_utc,
                    "replyCount": rep,
                    "status": "maybe_available" if rep == 0 else "maybe_used",
                    "expires": exp, "platform": "X", "source": "own-search",
                })
    except Exception as e:
        print(f"[patrol] own-search skipped: {e}", file=sys.stderr)
    return out

def main():
    merged = {}
    # A
    try:
        a = fetch_json("https://raw.githubusercontent.com/good1uck/xiaodou-codes/main/codes.json")
        for x in a.get("codes", []):
            n = norm_good(x)
            if valid_code(n["code"]) and n["status"] != "confirmed_used":
                merged[n["code"]] = n
        since = a.get("lastSinceId", "")
    except Exception as e:
        print(f"[patrol] source A failed: {e}", file=sys.stderr)
        since = ""
    # B
    try:
        b = fetch_json("https://raw.githubusercontent.com/CCCcccxxxrrr/xiaodou-codes/main/codes.json")
        items = b if isinstance(b, list) else b.get("codes", [])
        for x in items:
            n = norm_ccc(x)
            if valid_code(n["code"]) and n["code"] not in merged:
                merged[n["code"]] = n
    except Exception as e:
        print(f"[patrol] source B failed: {e}", file=sys.stderr)
    # C
    for n in own_search(set(merged)):
        merged[n["code"]] = n

    now = datetime.now(BJ)
    codes = []
    for n in merged.values():
        exp_dt = parse_expires(n.get("expires"))
        if exp_dt and exp_dt < now:
            continue
        codes.append(n)
    def sortkey(n):
        return n.get("postedAtUtc") or n.get("postedAt") or ""
    codes.sort(key=sortkey, reverse=True)
    codes = codes[:120]
    doc = {
        "lastUpdated": now.strftime("%Y-%m-%d %H:%M") + " 北京时间",
        "lastSinceId": since,
        "total": len(codes),
        "available": sum(1 for c in codes if c["status"] == "maybe_available"),
        "codes": codes,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"[patrol] wrote {len(codes)} codes, available={doc['available']}, at {doc['lastUpdated']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
