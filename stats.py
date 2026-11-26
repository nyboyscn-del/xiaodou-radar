#!/usr/bin/env python3
"""豆码雷达访问统计回读（Abacus 计数，免注册）。

用法：python3 stats.py [--days N]
指标：pv-total 打开总次数 / uv-total 近似独立访客（同浏览器每天计一次）
      pv-from-x / pv-from-search / pv-direct / pv-from-other 来源分布
      copy-total 复制邀请码总次数；另附最近 N 天 pv-YYYY-MM-DD / copy-YYYY-MM-DD。
计数从 2026-11-26 上线统计起算，上线前无数据。计数接口公开可读，试验期口径，不作精确审计。
"""
import json, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))
BASE = "https://abacus.jasoncameron.dev/get/xiaodou-radar-nyboys4/"

def get(key):
    try:
        req = urllib.request.Request(BASE + key, headers={"User-Agent": "Mozilla/5.0 xiaodou-radar-stats"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8")).get("value", 0)
    except urllib.error.HTTPError as e:
        return 0 if e.code == 404 else None  # 404 = 该键还没被计过数
    except Exception:
        return None

def main():
    days = 7
    if "--days" in sys.argv:
        try:
            days = int(sys.argv[sys.argv.index("--days") + 1])
        except Exception:
            pass
    keys = ["pv-total", "uv-total", "pv-from-x", "pv-from-search", "pv-direct", "pv-from-other", "copy-total"]
    out = {k: get(k) for k in keys}
    print("豆码雷达访问统计（累计，自 2026-11-26 统计上线起）")
    for k in keys:
        print(f"  {k}: {out[k]}")
    print(f"最近 {days} 天（北京时间）：")
    today = datetime.now(BJ).date()
    for i in range(days):
        d = today - timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        print(f"  {ds}: pv={get('pv-' + ds)} copy={get('copy-' + ds)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
