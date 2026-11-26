// 豆码雷达统一码池 Worker（Cloudflare）：公众号动态发码 + 多渠道取码 + 已分发标记（KV）
// 路由：GET/POST /wx（公众号回调）、GET /api/claim、GET /api/status、GET /codes.json（码池透传）
// 绑定：KV namespace 绑名 POOL_KV；环境变量（Secret）：WX_TOKEN、CLAIM_KEY
const CODES_URL = "https://raw.githubusercontent.com/nyboyscn-del/xiaodou-radar/main/codes.json";
const CORS = { "Access-Control-Allow-Origin": "*" };

const TXT_SUBSCRIBE = "欢迎关注破局笔记。\n回复「小豆」查最新邀请码\n回复「教程」看小豆上手指南";
const TXT_GUIDE = "小豆上手指南：\n1. 应用商店搜「小豆」下载（认准：豆包旗下 AI 个人助理）；\n2. 登录后停在「你已加入等候名单」页，点「我有邀请码，马上去体验」；\n3. 填入邀请码，验证通过即进入。\n没有码？回复「小豆」领一条最新码。";
const TXT_DEFAULT = "回复「小豆」查最新邀请码，回复「教程」看上手指南。";
const TXT_EMPTY = "现在暂时没有新码，巡检还在继续，过几分钟再回复「小豆」试试。";
const txtOk = (code) => `你的小豆邀请码：${code}\n来自公开渠道聚合，一码只能用一次，请尽快在小豆 App 里使用；如果已被抢先，回复「小豆」再领下一条。`;

async function sha1hex(s) {
  const b = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function getPool() {
  const r = await fetch(CODES_URL, { cf: { cacheTtl: 60, cacheEverything: true } });
  if (!r.ok) throw new Error("pool fetch " + r.status);
  return r.json();
}

async function getDist(env) {
  const raw = await env.POOL_KV.get("distributed");
  return raw ? JSON.parse(raw) : {};
}

async function claim(env, channel) {
  const pool = await getPool();
  const dist = await getDist(env);
  for (const c of pool.codes || []) {
    if (c.status !== "maybe_available" || !c.code || dist[c.code]) continue;
    dist[c.code] = { channel, at: new Date().toISOString() };
    await env.POOL_KV.put("distributed", JSON.stringify(dist));
    return c;
  }
  return null;
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });
}

function tag(xml, name) {
  const m = xml.match(new RegExp(`<${name}>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${name}>`));
  return m ? m[1].trim() : "";
}

function wxReply(toUser, fromUser, content) {
  const xml = `<xml><ToUserName><![CDATA[${toUser}]]></ToUserName><FromUserName><![CDATA[${fromUser}]]></FromUserName><CreateTime>${Math.floor(Date.now() / 1000)}</CreateTime><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[${content}]]></Content></xml>`;
  return new Response(xml, { headers: { "Content-Type": "text/xml; charset=utf-8" } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === "/api/claim") {
      if (url.searchParams.get("key") !== env.CLAIM_KEY) return json({ ok: false, reason: "forbidden" }, 403);
      const channel = (url.searchParams.get("channel") || "manual").slice(0, 20);
      try {
        const c = await claim(env, channel);
        if (!c) return json({ ok: false, reason: "暂无新码" });
        return json({ ok: true, code: c.code, platform: c.platform, author: c.author, postedAt: c.postedAt });
      } catch (e) {
        return json({ ok: false, reason: String(e) }, 502);
      }
    }

    if (path === "/api/status") {
      try {
        const pool = await getPool();
        const dist = await getDist(env);
        const avail = (pool.codes || []).filter((c) => c.status === "maybe_available");
        return json({
          total: (pool.codes || []).length,
          available: avail.length,
          undistributed_available: avail.filter((c) => !dist[c.code]).length,
          distributed: Object.keys(dist).length,
        });
      } catch (e) {
        return json({ ok: false, reason: String(e) }, 502);
      }
    }

    if (path === "/codes.json") {
      try {
        const pool = await getPool();
        return json(pool);
      } catch (e) {
        return json({ ok: false, reason: String(e) }, 502);
      }
    }

    if (path === "/wx") {
      const sig = url.searchParams.get("signature") || "";
      const ts = url.searchParams.get("timestamp") || "";
      const nonce = url.searchParams.get("nonce") || "";
      const check = await sha1hex([env.WX_TOKEN, ts, nonce].sort().join(""));
      if (check !== sig) return new Response("signature mismatch", { status: 403 });
      if (request.method === "GET") {
        return new Response(url.searchParams.get("echostr") || "", { headers: { "Content-Type": "text/plain" } });
      }
      const xml = await request.text();
      const fromUser = tag(xml, "FromUserName");
      const toUser = tag(xml, "ToUserName");
      const msgType = tag(xml, "MsgType");
      const event = tag(xml, "Event");
      const content = tag(xml, "Content");
      let reply = null;
      if (msgType === "event" && event === "subscribe") reply = TXT_SUBSCRIBE;
      else if (msgType === "text") {
        if (content === "小豆") {
          try {
            const c = await claim(env, "wechat");
            reply = c ? txtOk(c.code) : TXT_EMPTY;
          } catch (e) {
            reply = TXT_EMPTY;
          }
        } else if (content === "教程") reply = TXT_GUIDE;
        else reply = TXT_DEFAULT;
      }
      if (reply === null) return new Response("success", { headers: { "Content-Type": "text/plain" } });
      return wxReply(fromUser, toUser, reply);
    }

    return new Response("not found", { status: 404 });
  },
};
