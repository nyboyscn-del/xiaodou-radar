#!/usr/bin/env python3
"""豆码雷达统一码池服务（国内版站点 + 多渠道取码 + 公众号动态发码）。

- 码池数据源：GitHub 仓 codes.json（patrol.py 每 15 分钟更新），本服务带 60 秒缓存拉取。
- 已分发标记：本地 state 文件（distributed.json），渠道取走一条即标记，防自家渠道重复发同一码。
- 取码接口：GET /api/claim?channel=wechat|xhs&key=<CLAIM_KEY>
  成功 {"ok": true, "code": "...", ...}；无码 {"ok": false, "reason": "暂无新码"}。
- 公众号：GET /wx 校验（Token 签名），POST /wx 收消息：
  关注事件 -> 服务导航；文本「小豆」-> 取码回复；「教程」-> 上手指南；其他 -> 提示。
- 静态站：SITE_DIR 下文件（国内版 index.html），/codes.json 走上游缓存透传。
只用标准库。配置读同目录 pool_config.json：{port, wx_token, claim_key, site_dir, codes_url}
"""
import hashlib, json, os, re, threading, time, urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "pool_config.json"), encoding="utf-8"))
PORT = int(CFG.get("port", 8730))
WX_TOKEN = CFG["wx_token"]
CLAIM_KEY = CFG["claim_key"]
SITE_DIR = CFG.get("site_dir", os.path.join(HERE, "site"))
CODES_URL = CFG.get("codes_url", "https://raw.githubusercontent.com/nyboyscn-del/xiaodou-radar/main/codes.json")
STATE_FILE = os.path.join(HERE, "distributed.json")
SITE_URL = CFG.get("site_url", "https://nyboyscn-del.github.io/xiaodou-radar/?v=cn")

_lock = threading.Lock()
_cache = {"at": 0, "data": None}

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_state(st):
    tmp = STATE_FILE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, STATE_FILE)

def get_pool():
    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < 60:
        return _cache["data"]
    req = urllib.request.Request(CODES_URL, headers={"User-Agent": "xiaodou-pool-service"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    _cache.update(at=now, data=data)
    return data

def claim(channel):
    """取最新一条可能可用且未被自家渠道分发过的码，标记后返回；无码返回 None。"""
    with _lock:
        pool = get_pool()
        st = load_state()
        for c in pool.get("codes", []):
            if c.get("status") != "maybe_available":
                continue
            code = c.get("code")
            if not code or code in st:
                continue
            st[code] = {"channel": channel, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            save_state(st)
            return c
        return None

def pool_status():
    pool = get_pool()
    st = load_state()
    codes = pool.get("codes", [])
    avail = [c for c in codes if c.get("status") == "maybe_available"]
    fresh = [c for c in avail if c.get("code") not in st]
    return {"total": len(codes), "available": len(avail),
            "undistributed_available": len(fresh), "distributed": len(st)}

TXT_SUBSCRIBE = "欢迎关注破局笔记。\n回复「小豆」查最新邀请码\n回复「教程」看小豆上手指南"
TXT_GUIDE = ("小豆上手指南：\n1. 应用商店搜「小豆」下载（认准：豆包旗下 AI 个人助理）；\n"
             "2. 登录后停在「你已加入等候名单」页，点「我有邀请码，马上去体验」；\n"
             "3. 填入邀请码，验证通过即进入。\n没有码？回复「小豆」领一条最新码。")
TXT_DEFAULT = "回复「小豆」查最新邀请码，回复「教程」看上手指南。"

def txt_claim_ok(code):
    return (f"你的小豆邀请码：{code}\n"
            "来自公开渠道聚合，一码只能用一次，请尽快在小豆 App 里使用；"
            "如果已被抢先，回复「小豆」再领下一条。")

TXT_CLAIM_EMPTY = "现在暂时没有新码，巡检还在继续，过几分钟再回复「小豆」试试。"

def wx_reply_xml(to_user, from_user, content):
    return (f"<xml><ToUserName><![CDATA[{to_user}]]></ToUserName>"
            f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
            f"<CreateTime>{int(time.time())}</CreateTime>"
            f"<MsgType><![CDATA[text]]></MsgType>"
            f"<Content><![CDATA[{content}]]></Content></xml>")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/claim":
            if q.get("key", [""])[0] != CLAIM_KEY:
                return self._send(403, json.dumps({"ok": False, "reason": "forbidden"}))
            channel = q.get("channel", ["manual"])[0][:20]
            c = claim(channel)
            if c is None:
                return self._send(200, json.dumps({"ok": False, "reason": "暂无新码"}, ensure_ascii=False))
            return self._send(200, json.dumps({"ok": True, "code": c["code"], "platform": c.get("platform"),
                                               "author": c.get("author"), "postedAt": c.get("postedAt")}, ensure_ascii=False))
        if u.path == "/api/status":
            try:
                return self._send(200, json.dumps(pool_status(), ensure_ascii=False))
            except Exception as e:
                return self._send(502, json.dumps({"ok": False, "reason": str(e)}))
        if u.path == "/wx":
            sig = q.get("signature", [""])[0]
            ts = q.get("timestamp", [""])[0]
            nonce = q.get("nonce", [""])[0]
            echostr = q.get("echostr", [""])[0]
            check = hashlib.sha1("".join(sorted([WX_TOKEN, ts, nonce])).encode()).hexdigest()
            if check == sig:
                return self._send(200, echostr, "text/plain")
            return self._send(403, "signature mismatch", "text/plain")
        if u.path == "/codes.json":
            try:
                pool = get_pool()
                return self._send(200, json.dumps(pool, ensure_ascii=False))
            except Exception:
                p = os.path.join(SITE_DIR, "codes.json")
                if os.path.exists(p):
                    return self._send(200, open(p, "rb").read())
                return self._send(502, "pool unavailable", "text/plain")
        # static
        rel = u.path.lstrip("/") or "index.html"
        if ".." in rel:
            return self._send(400, "bad path", "text/plain")
        p = os.path.join(SITE_DIR, rel)
        if os.path.isfile(p):
            ctype = "text/html; charset=utf-8" if p.endswith(".html") else "application/octet-stream"
            return self._send(200, open(p, "rb").read(), ctype)
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/wx":
            return self._send(404, "not found", "text/plain")
        q = parse_qs(u.query)
        sig = q.get("signature", [""])[0]
        ts = q.get("timestamp", [""])[0]
        nonce = q.get("nonce", [""])[0]
        check = hashlib.sha1("".join(sorted([WX_TOKEN, ts, nonce])).encode()).hexdigest()
        if check != sig:
            return self._send(403, "signature mismatch", "text/plain")
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            root = ET.fromstring(body.decode("utf-8"))
        except Exception:
            return self._send(200, "success", "text/plain")
        def tag(name):
            el = root.find(name)
            return el.text.strip() if el is not None and el.text else ""
        from_user, to_user = tag("FromUserName"), tag("ToUserName")
        msg_type, event, content = tag("MsgType"), tag("Event"), tag("Content")
        reply = None
        if msg_type == "event" and event == "subscribe":
            reply = TXT_SUBSCRIBE
        elif msg_type == "text":
            if content == "小豆":
                c = claim("wechat")
                reply = txt_claim_ok(c["code"]) if c else TXT_CLAIM_EMPTY
            elif content == "教程":
                reply = TXT_GUIDE
            else:
                reply = TXT_DEFAULT
        if reply is None:
            return self._send(200, "success", "text/plain")
        return self._send(200, wx_reply_xml(from_user, to_user, reply), "text/xml; charset=utf-8")

if __name__ == "__main__":
    os.makedirs(SITE_DIR, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
