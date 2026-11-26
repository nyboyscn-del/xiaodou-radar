# 豆码雷达 · 小豆邀请码实时抓码站

社区收集的豆包「小豆」邀请码，来自 X / 微博 / LINUX DO 等平台的公开分享帖。**这不是豆包或字节跳动的官方网站。**

- 站点：https://nyboyscn-del.github.io/xiaodou-radar/
- 数据：根目录的 `codes.json`，巡检脚本 `patrol.py` 多源聚合写入（上游公开码池 + 自有 X 搜索增量）
- 页面每 30 秒重新拉取 `codes.json`；状态按原帖回复数推断（0 回复＝可能可用），不保证当前仍可用
- 「试过了」标记只保存在访客浏览器 localStorage，不回写数据

字段：`code` 6 位字母数字 / `postUrl` 原帖 / `postedAt` 北京时间 / `expires` 有效期（如原帖标注）/ `status` maybe_available｜maybe_used
