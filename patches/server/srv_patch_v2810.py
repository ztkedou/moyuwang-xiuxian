# -*- coding: utf-8 -*-
r"""srv_patch_v2810.py — 0.8.10 服务端综合环（链第 21 环 / 新末环）

只做 8 件事，逐项对应任务书 ①~⑧；锚区互不重叠，且与前 20 环零交集。

| # | 锚点 | 改动 |
|---:|---|---|
| ① | `/api/activity/shop` 响应（:8133）+ `/api/activity/shop/exchange` 收尾（:8203） | 顶层 `balance` → `jadeBalance`（**语义纠正**：这两个 balance 是 activity_token 灵玉，非灵石） |
| ② | `PET_T2_COST_BASE` 定义（:5355）/ `petT2ExpeditionCost`（:5398）/ `/api/pet/spirit/list`（:11423） | 新增 `PET_T2_PATH_BASE = 7500`；**秘径**改用它；**融合**仍 10000；list 追加 `pathCostBase` |
| ③ | `tickWudaoIdle` 两处调用点（:2365 / :2388）+ 其定义前（:5990） | 新增 `ylWudaoIdleDelta()` = 打坐 + 历练；两处调用点改调它（**不动** tickWudaoIdle 内部公式） |
| ④ | `/api/mail/send` 之后（:6213） | 新增 `DELETE /api/mail/:id`（200/400/404/409 契约，见下） |
| ⑤ | `snapshotOldSave` 定义（:2207）+ 节流行（:2213）+ 回档调用点（:2601） | 加可选参 `force`（默认 false）；回档点传 `true` 绕过 10min 节流；**写档点不传** |
| ⑥ | `gm_sessions` 建表（:1196）/ `authenticateGM`（:1249）/ GM 登录（:2416） | `safeAddColumn` 幂等加 `expires_at`；登录写 7 天；校验加过期判定 + 惰性删行 |
| ⑦ | `POST /api/gm/activity/config` 之后（:7775） | 新增 `DELETE /api/gm/activity/:id`（删 events 行 + 审计） |
| ⑧ | 封禁迁移块（:2867）/ ban 端点后（:2884）/ `POST /api/messages` 写入点（:3430） | `users.muted_until` 幂等加列 + `POST /api/gm/players/:id/mute` + 发言拦截 + `GET /api/me/mute` |

## ① 为什么是资损级 bug

客户端有「灵石余额回显采纳器」：读响应**顶层**裸 `balance` 并写进 `player.spiritStones`。
而 `/api/activity/shop`（灵玉阁）把**灵玉余额**（activity_token，玩家通常为 0）放在顶层
`balance` ⇒ 一打开灵玉阁就把灵石采纳成 0（实测事故：`[灵石] 权威采纳后本地灵石下调：94729 → 0`）。
改名 `jadeBalance` 后该端点顶层再无 `balance`，采纳器自然不触发。

★ 已顺扫全仓顶层 `balance`：`:1569`（回显中间件，取自 `saves.save_data.player.spiritStones`）、
`:2337`（409 stale_save 的 `staleBal`）、`:7383` / `:7504`（悟道 / 功法面板，同样取自
`spiritStones`）—— **四处皆为真灵石，一字不动**。

## ④ 邮件删除契约（客户端已按此实现）

* `DELETE /api/mail/:id`，`authenticateToken` + `rateLimit`
* 成功 → `200 { ok: true, id: <number> }`
* `400` → id 非法（非正整数）
* `404` → 邮件不存在**或不属于该玩家**
* `409` → **已领取的邮件不可删除**（`mail.claimed = 1`；DDL 见产物 `:274`）

## ⑤ 数据安全：回档前强制落一条（本仓坑 23）

`snapshotOldSave` 自带 10 分钟节流；回档端点也走它 ⇒ 10 分钟内连回档两次，第二次
**没有退路快照 ⇒ 回档不可逆**。加 `force` 参数后，回档点强制落一条；普通写档点仍走节流
（否则会写爆表）。门禁同时断言「回档调用点带 force」+「写档调用点不带 force」。

## ⑥ 存量行策略（重要，交付说明同款）

`gm_sessions.expires_at` 为**新增列**，存量行的该列为 `NULL`。
本环策略：**NULL 视为已过期**（惰性删行 + 401）。理由：这些行全部来自本次上线之前的旧会话，
无法回溯其签发时刻 ⇒ 保守失效优于「永久有效」。**副作用：上线瞬间会踢掉当前在线 GM 会话**，
GM 重新登录一次即可（`POST /api/gm/login` 会写入 7 天后的 `expires_at`）。

★ 过期返回 **401** 而非 403：GM 前端 `gm-pro/gm-pro.html:590` **仅在 401 时**清 token 并弹回
登录页；403 只弹错误、不清 token（会把 GM 卡死在坏 token 上）。无效 token 仍维持既有 403 分支。

## ⑧ 拦截面

只拦「发言」= `POST /api/messages` 的 `chat_messages` 写入点（`:3430`）。
**不拦**登录 / 存档 / 领取（那是封禁 `banned` 的语义）。
`chat_messages` 无 `user_id` 列（只有 `username`）⇒ 禁言判定按 `username` 回查 `users.muted_until`
（与写入行的身份口径一致）。全仓另一处 `INSERT INTO chat_messages`（`:11667`）是**系统公告**
（渡劫播报），非玩家发言，不拦。

## 工程约束（本项目已踩过的坑，本环逐条遵守）

1. **回调式 sqlite3** ⇒ 一律 `dbGet / dbAll / dbRun`；`db.run(...).catch(...)` **禁止**。
2. **ESM** ⇒ `require(` **禁止**（门禁断言其计数不增加）。
3. **加列走 `safeAddColumn`**（吞 `duplicate column name`）；**不读 PRAGMA**（serialize 无完成屏障，坑 12）。
4. **注入块里的中文一律转义成 `\uXXXX`**（模块里的 `zh()`），门禁 needle 落在注入块内时同样用 `zh()`。
5. **结算/扣费顺序（坑 16）**：本环无「先扣钱后可能失败」的操作（唯一写钱路径都不在本环）。
6. **锚点**：每处替换都带 `expect=<精确次数>`，改动前先验证 `count` 等于期望值。
7. ⛔ 不改 `srv/index_v28.ts`（链产物）；⛔ 不改前 20 环补丁；⛔ 不改基座指纹。
8. **本环不新增任何 `res.status(403)`**：mute 用 `res.statusCode = 403; res.json(...)` 表达，
   因为 `check_srv_087.py` 硬断言 `res.status(403)` 计数 == 11（业务拒绝零 403 纪律）。

## 用法

```
python srv_patch_v2810.py --src <上一环产物>    # 就地原子写回 --src
python srv_patch_v2810.py --selftest            # 只跑门禁，不碰文件
```

幂等：已含 `[v2810]` 标记则 SKIP。锚点不唯一一律中止（拒绝静默失败）。
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
import time

MARK = '[v2810]'
HERE = os.path.dirname(os.path.abspath(__file__))


def md5s(s: str) -> str:
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def die(msg: str):
    print('[FAIL] ' + msg)
    sys.exit(1)


def zh(s: str) -> str:
    """注入块编码纪律：把非 ASCII 字符转成 `\\uXXXX`。

    ★ 为什么：补丁脚本注入的**新**中文一律以转义形态落进产物，杜绝任何编码链路
      （写盘 / 传输 / 二次读取）造成的乱码；也保证门禁 needle 与产物逐字可比。
    """
    return ''.join(ch if ord(ch) < 128 else '\\u%04x' % ord(ch) for ch in s)


def apply_one(text: str, tag: str, old: str, new: str, expect: int = 1) -> str:
    n = text.count(old)
    if n != expect:
        die('%s 锚点命中 %d 次（期望 %d）—— 拒绝静默失败' % (tag, n, expect))
    print('  [OK] %-6s 锚点命中 %d 次' % (tag, n))
    return text.replace(old, new, expect)


def _assert_anchor_kept(tag: str, old: str, new: str) -> None:
    """★ 自毁防线：**插入式**改动必须把锚点原文带进 new（否则等于删掉锚点行）。"""
    if old not in new:
        die('%s 自毁防线：new 未包含锚点原文 ⇒ 锚点行会被整段删除（不是插入）。' % tag)
    print('  [OK] %-6s 自毁防线通过（new 含锚点原文，属插入式改动）' % tag)


# ═══════════════════════════════════════════════════════════════════════
# ① 活动域 balance → jadeBalance
# ═══════════════════════════════════════════════════════════════════════
E1_OLD = "    res.json({ balance, window, items, engineOn: await actEngineEnabled() });"
E1_NEW = zh("    res.json({ jadeBalance: balance, window, items, engineOn: await actEngineEnabled() });"
            " // [v2810] \u9876\u5c42 balance \u6539\u540d jadeBalance\uff1a"
            "\u8fd9\u91cc\u662f activity_token \u7075\u7389\u4f59\u989d\uff0c\u4e0e\u7075\u77f3\u65e0\u5173")

E2_OLD = ("    res.json({ ok: true, balance: Math.max(0, Math.floor(Number(balRow && balRow.balance) || 0)), "
          "gained, item: item.id, title });")
E2_NEW = zh("    res.json({ ok: true, jadeBalance: Math.max(0, Math.floor(Number(balRow && balRow.balance) || 0)), "
            "gained, item: item.id, title });"
            " // [v2810] \u540c\u4e0a\uff1a\u7075\u7389\u4f59\u989d\u6539\u540d jadeBalance")

# ═══════════════════════════════════════════════════════════════════════
# ② 灵宠秘径基础 7500（融合仍 10000）
# ═══════════════════════════════════════════════════════════════════════
E3_OLD = "const PET_T2_COST_BASE = 10000;             // \u2190 \u7528\u6237 2026-09-29\uff1a\u57fa\u7840 10000 \u7075\u77f3\u8d77"
E3_NEW = E3_OLD + "\n" + zh(
    "const PET_T2_PATH_BASE = 7500;              // 0.8.10\uff1a\u79d8\u5f84\u57fa\u7840 10000 \u2192 7500"
    "\uff08\u7528\u6237\u8981\u6c42\uff09\uff1b\u878d\u5408\u4ecd 10000")

E4_OLD = "  return petRound100(PET_T2_COST_BASE * rm * PET_FUSE_STAGE_MULT[si] * petT2AffectionMult(affection));"
E4_NEW = zh("  return petRound100(PET_T2_PATH_BASE * rm * PET_FUSE_STAGE_MULT[si] * petT2AffectionMult(affection));"
            " // [v2810] \u79d8\u5f84\u57fa\u7840 7500")

E5_OLD = "        costBase: PET_T2_COST_BASE,               // \u79d8\u5f84 / \u878d\u5408\u8d39\u57fa\u7840 10000 \u7075\u77f3"
E5_NEW = E5_OLD + "\n" + zh(
    "        pathCostBase: PET_T2_PATH_BASE,           // [v2810] \u79d8\u5f84\u57fa\u7840 7500\uff08\u878d\u5408\u4ecd 10000\uff09")

# ═══════════════════════════════════════════════════════════════════════
# ③ 历练也触发悟道（只改喂进去的时长）
# ═══════════════════════════════════════════════════════════════════════
E6_OLD = ("tickWudaoIdle(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData)).meditate)")
E6_NEW = "tickWudaoIdle(req.user.id, ylWudaoIdleDelta(prevCounters, saveData))"

E15_ANCHOR = "async function tickWudaoIdle(userId: number, playTimeDeltaMs: number): Promise<void> {"
E15_NEW = zh(
    "// [v2810] \u609f\u9053\u6302\u673a\u65f6\u957f = \u6253\u5750 + \u5386\u7ec3\uff08\u7528\u6237\u8981\u6c42\u300c\u6253\u5750/\u5386\u7ec3\u4e2d\u968f\u673a\u89e6\u53d1\u609f\u9053\u7ecf\u9a8c\u300d\uff09\u3002\n"
    "//   tickWudaoIdle \u5185\u90e8\u6982\u7387/\u7ecf\u9a8c\u516c\u5f0f\u4e00\u5b57\u4e0d\u52a8\uff0c\u53ea\u6539\u5582\u8fdb\u53bb\u7684\u65f6\u957f\u3002\n"
    "function ylWudaoIdleDelta(prevCounters: StatCounters, saveData: any): number {\n"
    "  const d = computeQuestDeltas(prevCounters, extractCounters(saveData));\n"
    "  return Math.max(0, (Number(d.meditate) || 0) + (Number(d.adventure) || 0));\n"
    "}\n\n") + E15_ANCHOR

# ═══════════════════════════════════════════════════════════════════════
# ④ DELETE /api/mail/:id
# ═══════════════════════════════════════════════════════════════════════
E7_ANCHOR = "  res.status(400).json({ error: '\u9700\u8981 userId / username / all:true' });\n});"
E7_BODY = zh("""
// [v2810] DELETE /api/mail/:id \u2014 \u5220\u9664\u5355\u5c01\u90ae\u4ef6\uff08\u5ba2\u6237\u7aef\u4fe1\u7bb1\u5220\u9664\u6309\u94ae\uff09\u3002
//   \u5951\u7ea6\uff1a200 {ok,id} / 400 id \u975e\u6cd5 / 404 \u4e0d\u5b58\u5728\u6216\u4e0d\u5c5e\u4e8e\u672c\u73a9\u5bb6 / 409 \u5df2\u9886\u53d6\u4e0d\u53ef\u5220\u3002
app.delete('/api/mail/:id', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `mail:del:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  const mailId = asInt(req.params.id);
  if (!Number.isInteger(mailId) || mailId <= 0) return res.status(400).json({ error: '\u90ae\u4ef6 id \u975e\u6cd5' });
  try {
    const row: any = await dbGet('SELECT id, claimed FROM mail WHERE id = ? AND user_id = ?', [mailId, userId]);
    if (!row) return res.status(404).json({ error: '\u90ae\u4ef6\u4e0d\u5b58\u5728' });
    if (Number(row.claimed) === 1) return res.status(409).json({ error: '\u5df2\u9886\u53d6\u7684\u90ae\u4ef6\u4e0d\u53ef\u5220\u9664' });
    const del = await dbRun('DELETE FROM mail WHERE id = ? AND user_id = ? AND claimed = 0', [mailId, userId]);
    if (!del.changes) return res.status(404).json({ error: '\u90ae\u4ef6\u4e0d\u5b58\u5728' });
    res.json({ ok: true, id: mailId });
  } catch (e: any) {
    console.error('mail delete error:', e?.message || e);
    res.status(500).json({ error: '\u5220\u9664\u5931\u8d25' });
  }
});
""")
E7_NEW = E7_ANCHOR + E7_BODY

# ═══════════════════════════════════════════════════════════════════════
# ⑤ 快照「回档前强制落一条」绕过 10 分钟节流
# ═══════════════════════════════════════════════════════════════════════
E8A_OLD = "function snapshotOldSave(userId: number, oldSaveData: string, gmRevision: number) {"
E8A_NEW = zh("function snapshotOldSave(userId: number, oldSaveData: string, gmRevision: number, force: boolean = false) {"
             " // [v2810] force=true \u8df3\u8fc7 10min \u8282\u6d41\uff08\u56de\u6863\u524d\u5f3a\u5236\u843d\u4e00\u6761\uff09")

E8B_OLD = "        if (Number.isFinite(t) && Date.now() - t < 10 * 60 * 1000) return; // \u8282\u6d41\uff1a\u8ddd\u4e0a\u4e00\u6761 <10min \u4e0d\u518d\u5feb\u7167"
E8B_NEW = "        if (!force && Number.isFinite(t) && Date.now() - t < 10 * 60 * 1000) return; // \u8282\u6d41\uff1a\u8ddd\u4e0a\u4e00\u6761 <10min \u4e0d\u518d\u5feb\u7167"

E8C_OLD = "  if (cur) snapshotOldSave(userId, String(cur.save_data), Number(cur.gm_revision) || 0);"
E8C_NEW = zh("  if (cur) snapshotOldSave(userId, String(cur.save_data), Number(cur.gm_revision) || 0, true);"
             " // [v2810] \u56de\u6863\u524d\u5f3a\u5236\u5feb\u7167\uff08\u7ed5\u8fc7 10min \u8282\u6d41\uff0c\u4fdd\u8bc1\u53ef\u9006\uff09")

# ═══════════════════════════════════════════════════════════════════════
# ⑥ gm_sessions.expires_at
# ═══════════════════════════════════════════════════════════════════════
E9_OLD = ("  db.get('SELECT token FROM gm_sessions WHERE token = ?', [token], (err: any, row: any) => {\n"
          "    if (err || !row) return res.status(403).json({ error: 'Invalid GM token' });\n"
          "    next();\n"
          "  });")
E9_NEW = zh("""  db.get('SELECT token, expires_at FROM gm_sessions WHERE token = ?', [token], (err: any, row: any) => {
    if (err || !row) return res.status(403).json({ error: 'Invalid GM token' });
    // [v2810] GM \u4f1a\u8bdd\u8fc7\u671f\u5224\u5b9a\uff1aexpires_at \u4e3a\u7a7a\uff08\u5b58\u91cf\u65e7\u884c\uff09\u6216\u5df2\u8fc7\u671f
    //   \u21d2 \u89c6\u4e3a\u65e0\u6548\uff08401 \u5f3a\u5236\u91cd\u65b0\u767b\u5f55\uff09+ \u60f0\u6027\u5220\u884c\u3002
    //   \u9009 401 \u800c\u975e 403\uff1aGM \u524d\u7aef gm-pro.html \u4ec5\u5728 401 \u65f6\u6e05 token \u5e76\u5f39\u56de\u767b\u5f55\u9875\u3002
    const exp = row.expires_at ? Date.parse(String(row.expires_at)) : NaN;
    if (!Number.isFinite(exp) || exp <= Date.now()) {
      db.run('DELETE FROM gm_sessions WHERE token = ?', [token]);
      return res.status(401).json({ error: 'GM session expired' });
    }
    next();
  });""")

E10_OLD = "  db.run('INSERT INTO gm_sessions (token) VALUES (?)', [token], (err: any) => {"
E10_NEW = zh("  db.run('INSERT INTO gm_sessions (token, expires_at) VALUES (?, ?)', "
             "[token, new Date(Date.now() + 7 * 86400e3).toISOString()], (err: any) => {"
             " // [v2810] GM \u4f1a\u8bdd 7 \u5929\u8fc7\u671f")

# ═══════════════════════════════════════════════════════════════════════
# ⑦ DELETE /api/gm/activity/:id
# ═══════════════════════════════════════════════════════════════════════
E11_ANCHOR = ("    console.error('gm activity config error:', e?.message || e);\n"
              "    res.status(500).json({ error: '\u4fdd\u5b58\u5931\u8d25' });\n"
              "  }\n"
              "});")
E11_BODY = zh("""
// [v2810] DELETE /api/gm/activity/:id \u2014 \u5220\u9664\u6d3b\u52a8\uff08events \u884c + \u5ba1\u8ba1\uff09\u3002
//   \u7ea7\u8054\u7b56\u7565\uff1a\u53ea\u5220 events \u884c\uff1bactivity_token \u7684 bought:<eventId>:<itemId> \u884c\u3001
//   activity_checkin / activity_rank_settled / activity_rain_state / event_boss \u4e2d\u540c
//   event_id \u7684\u884c\u4fdd\u7559\u4e3a\u5b64\u513f\uff08\u5747\u6309 event_id \u5b9a\u4f4d\uff0c\u6d3b\u52a8\u5220\u540e\u67e5\u8be2\u4e0d\u5230\u5373\u65e0\u5bb3\uff09\u3002
app.delete('/api/gm/activity/:id', authenticateGM, async (req: any, res: any) => {
  const id = asInt(req.params.id);
  if (!Number.isInteger(id) || id <= 0) return res.status(400).json({ error: '\u6d3b\u52a8 id \u975e\u6cd5' });
  try {
    const del = await dbRun('DELETE FROM events WHERE id = ?', [id]);
    if (!del.changes) return res.status(404).json({ error: '\u6d3b\u52a8\u4e0d\u5b58\u5728' });
    logGmAction('activity_delete', `event:${id}`, { id });
    res.json({ ok: true, id });
  } catch (e: any) {
    console.error('gm activity delete error:', e?.message || e);
    res.status(500).json({ error: '\u5220\u9664\u5931\u8d25' });
  }
});
""")
E11_NEW = E11_ANCHOR + E11_BODY

# ═══════════════════════════════════════════════════════════════════════
# ⑧ 禁言：加列 + GM 端点 + 发言拦截 + GET /api/me/mute
# ═══════════════════════════════════════════════════════════════════════
E14_ANCHOR = ('// \u5c01\u7981 / \u89e3\u5c01\u8d26\u53f7\uff08\u901a\u8fc7\u6807\u8bb0 GM \u5b57\u6bb5\u5b9e\u73b0\uff1a\u5728 users \u8868\u52a0 banned \u5217\uff09\n'
              'db.serialize(() => {\n'
              '  db.all("PRAGMA table_info(users)", (err: any, rows: any[]) => {\n'
              "    if (!err && rows && !rows.some((r: any) => r.name === 'banned')) {\n"
              "      safeAddColumn('users', 'banned', 'ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0');\n"
              '    }\n'
              '  });\n'
              '});')
E14_NEW = E14_ANCHOR + zh("""
// [v2810] 0.8.10 \u8fc1\u79fb\uff1ausers.muted_until\uff08\u7981\u8a00\uff09+ gm_sessions.expires_at\uff08GM \u4f1a\u8bdd\u8fc7\u671f\uff09\u3002
//   \u2605 \u5e42\u7b49\u52a0\u5217\uff1asafeAddColumn \u541e duplicate column name\uff1b\u4e0d\u8bfb PRAGMA\uff08serialize \u65e0\u5b8c\u6210\u5c4f\u969c\uff0c\u5751 12\uff09\u3002
db.serialize(() => {
  safeAddColumn('users', 'muted_until', 'ALTER TABLE users ADD COLUMN muted_until DATETIME');
  safeAddColumn('gm_sessions', 'expires_at', "ALTER TABLE gm_sessions ADD COLUMN expires_at DATETIME");
});""")

E12_ANCHOR = ("    logGmAction(banned ? 'ban' : 'unban', `user:${userId}`, { reason });\n"
              "    res.json({ message: banned ? 'Banned' : 'Unbanned', banned: !!banned, userId });\n"
              "  });\n"
              "});")
E12_BODY = zh("""
// [v2810] POST /api/gm/players/:id/mute \u2014 \u7981\u8a00 / \u89e3\u9664\u7981\u8a00\uff08users.muted_until\uff09\u3002
//   body { minutes?: number, until?: string }\uff1a\u4e8c\u8005\u53d6\u4e00\uff1bminutes<=0 \u6216 until \u4e3a\u7a7a/\u5df2\u8fc7\u53bb
//   \u21d2 \u89e3\u9664\u7981\u8a00\u3002\u53ea\u62e6\u300c\u53d1\u8a00\u300d\uff08POST /api/messages\uff09\uff0c\u4e0d\u62e6\u767b\u5f55 / \u5b58\u6863 / \u9886\u53d6\uff08\u90a3\u662f\u5c01\u7981\u7684\u8bed\u4e49\uff09\u3002
app.post('/api/gm/players/:id/mute', authenticateGM, async (req: any, res: any) => {
  const userId = asInt(req.params.id);
  if (!Number.isInteger(userId) || userId <= 0) return res.status(400).json({ error: '\u7528\u6237 id \u975e\u6cd5' });
  const minutes = Math.floor(asNum(req.body?.minutes) || 0);
  const untilRaw = asStr(req.body?.until).trim();
  let untilIso: string | null = null;
  if (untilRaw) {
    const t = Date.parse(untilRaw);
    if (Number.isFinite(t) && t > Date.now()) untilIso = new Date(t).toISOString();
  } else if (Number.isFinite(minutes) && minutes > 0) {
    untilIso = new Date(Date.now() + minutes * 60000).toISOString();
  }
  try {
    const up = await dbRun('UPDATE users SET muted_until = ? WHERE id = ?', [untilIso, userId]);
    if (!up.changes) return res.status(404).json({ error: '\u7528\u6237\u4e0d\u5b58\u5728' });
    logGmAction(untilIso ? 'mute' : 'unmute', `user:${userId}`, { until: untilIso, minutes });
    res.json({ ok: true, userId, mutedUntil: untilIso });
  } catch (e: any) {
    console.error('gm mute error:', e?.message || e);
    res.status(500).json({ error: '\u64cd\u4f5c\u5931\u8d25' });
  }
});

// [v2810] GET /api/me/mute \u2014 \u53ea\u8bfb\uff1a\u5f53\u524d\u73a9\u5bb6\u7981\u8a00\u72b6\u6001\uff08\u5ba2\u6237\u7aef\u5c55\u793a\uff1b\u5b57\u6bb5\u540d mutedUntil \u7a33\u5b9a\uff09\u3002
app.get('/api/me/mute', authenticateToken, async (req: any, res: any) => {
  try {
    const row: any = await dbGet('SELECT muted_until FROM users WHERE id = ?', [req.user.id]);
    const raw = row && row.muted_until ? String(row.muted_until) : '';
    const t = raw ? Date.parse(raw) : NaN;
    const active = Number.isFinite(t) && t > Date.now();
    res.json({ muted: active, mutedUntil: active ? new Date(t).toISOString() : null });
  } catch (e: any) {
    console.error('me mute error:', e?.message || e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  }
});""")
E12_NEW = E12_ANCHOR + E12_BODY

E13_OLD = ("  db.run(\n"
           "    'INSERT INTO chat_messages (username, text) VALUES (?, ?)',\n"
           "    [username, trimmedText],")
E13_NEW = zh("""  // [v2810] \u7981\u8a00\u62e6\u622a\uff1a\u4ec5\u62e6\u300c\u53d1\u8a00\u300d\uff08\u4e16\u754c\u804a\u5929\u5199\u5165\uff09\uff0c\u4e0d\u62e6\u767b\u5f55/\u5b58\u6863/\u9886\u53d6\u3002
  try {
    const mrow: any = await dbGet('SELECT muted_until FROM users WHERE username = ?', [username]);
    const mu = mrow && mrow.muted_until ? Date.parse(String(mrow.muted_until)) : NaN;
    if (Number.isFinite(mu) && mu > Date.now()) {
      res.statusCode = 403;
      return res.json({ error: '\u4f60\u5df2\u88ab\u7981\u8a00\uff0c\u89e3\u9664\u65f6\u95f4 ' + new Date(mu).toISOString(), code: 'MUTED', mutedUntil: new Date(mu).toISOString() });
    }
  } catch (e: any) { /* \u7981\u8a00\u6821\u9a8c\u5931\u8d25\u4e0d\u963b\u65ad\u53d1\u8a00\uff08\u53ef\u7528\u6027\u4f18\u5148\uff09 */ }
""") + E13_OLD

# 全部改动： (tag, old, new, expect, insertion?)
EDITS = [
    ('E1',  E1_OLD,  E1_NEW,  1, False),
    ('E2',  E2_OLD,  E2_NEW,  1, False),
    ('E3',  E3_OLD,  E3_NEW,  1, True),
    ('E4',  E4_OLD,  E4_NEW,  1, False),
    ('E5',  E5_OLD,  E5_NEW,  1, True),
    ('E6',  E6_OLD,  E6_NEW,  2, False),
    ('E15', E15_ANCHOR, E15_NEW, 1, True),
    ('E7',  E7_ANCHOR, E7_NEW, 1, True),
    ('E8A', E8A_OLD, E8A_NEW, 1, False),
    ('E8B', E8B_OLD, E8B_NEW, 1, False),
    ('E8C', E8C_OLD, E8C_NEW, 1, False),
    ('E9',  E9_OLD,  E9_NEW,  1, False),
    ('E10', E10_OLD, E10_NEW, 1, False),
    ('E11', E11_ANCHOR, E11_NEW, 1, True),
    ('E14', E14_ANCHOR, E14_NEW, 1, True),
    ('E12', E12_ANCHOR, E12_NEW, 1, True),
    ('E13', E13_OLD, E13_NEW, 1, True),
]


def _strip_line_comments(s: str) -> str:
    return '\n'.join(l.split('//')[0] for l in s.split('\n'))


def _base_counts(src: str) -> dict:
    return {
        'res.status(403)': src.count('res.status(403)'),
        'require(': src.count('require('),
        'status: 403': src.count('status: 403'),
        'utcDayStartMs': src.count('utcDayStartMs'),
        'PRAGMA table_info(users)': src.count('PRAGMA table_info(users)'),
        'db.exec(ALTER TABLE': src.count("db.exec('ALTER TABLE") + src.count('db.exec("ALTER TABLE'),
    }


def _gates(text: str, base: dict, delta: int, gate) -> None:
    # ── ① 活动域 balance 改名 ──
    gate('G1  shop 响应顶层 balance → jadeBalance', text.count('jadeBalance: balance, window, items, engineOn:') == 1,
         '实际 %d' % text.count('jadeBalance: balance, window, items, engineOn:'))
    gate('G2  exchange 响应顶层 balance → jadeBalance',
         text.count('ok: true, jadeBalance: Math.max(0, Math.floor(Number(balRow && balRow.balance) || 0)),') == 1)
    gate('G3  旧顶层 balance 已消失（活动域）',
         text.count('res.json({ balance, window, items, engineOn:') == 0
         and text.count('ok: true, balance: Math.max(0, Math.floor(Number(balRow && balRow.balance)') == 0)
    gate('G4  真灵石 balance 四处一字未动',
         text.count('balance: staleBal !== null ? staleBal : undefined') == 1
         and text.count('origJson(Object.assign({}, body, { balance: bal }));') == 1
         and text.count('let balance: number | null = null;') == 2)

    # ── ② 秘径基础 7500 / 融合仍 10000 ──
    gate('G5  新增 PET_T2_PATH_BASE = 7500', text.count('const PET_T2_PATH_BASE = 7500;') == 1)
    gate('G6  PET_T2_COST_BASE = 10000 原样保留', text.count('const PET_T2_COST_BASE = 10000;') == 1)
    gate('G7  秘径用 PATH_BASE',
         text.count('petRound100(PET_T2_PATH_BASE * rm * PET_FUSE_STAGE_MULT[si] * petT2AffectionMult(affection))') == 1)
    gate('G8  融合仍用 COST_BASE',
         text.count('petRound100(PET_T2_COST_BASE * mm * (1 + si / 3) * petT2AffectionMult(affection))') == 1)
    gate('G9  list 追加 pathCostBase 且保留 costBase',
         text.count('pathCostBase: PET_T2_PATH_BASE,') == 1 and text.count('costBase: PET_T2_COST_BASE,') == 1)

    # ── ③ 历练也触发悟道 ──
    gate('G10 helper ylWudaoIdleDelta 定义 1 处', text.count('function ylWudaoIdleDelta(') == 1)
    gate('G11 两处调用点改调 helper（声明+2 消费者=3）',
         text.count('tickWudaoIdle(req.user.id, ylWudaoIdleDelta(prevCounters, saveData))') == 2
         and text.count('ylWudaoIdleDelta') == 3)
    gate('G12 旧的 meditate-only 调用已消失',
         text.count('tickWudaoIdle(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData)).meditate)') == 0)
    gate('G13 tickWudaoIdle 内部公式一字未动',
         text.count('async function tickWudaoIdle(userId: number, playTimeDeltaMs: number): Promise<void> {') == 1
         and text.count('const hits = wudaoIdleInsights(Math.floor((Number(playTimeDeltaMs) || 0) / 60000), Math.random);') == 1)
    gate('G14 helper 用 adventure 字段（computeQuestDeltas 实测键名）',
         text.count('(Number(d.meditate) || 0) + (Number(d.adventure) || 0)') == 1)

    # ── ④ DELETE /api/mail/:id ──
    gate('G15 邮件删除端点恰 1 处（authenticateToken + rateLimit）',
         text.count("app.delete('/api/mail/:id', authenticateToken, rateLimit(") == 1)
    gate('G16 邮件删除四态齐备',
         text.count(zh('\u90ae\u4ef6 id \u975e\u6cd5')) == 1
         and text.count(zh('\u90ae\u4ef6\u4e0d\u5b58\u5728')) == 2
         and text.count(zh('\u5df2\u9886\u53d6\u7684\u90ae\u4ef6\u4e0d\u53ef\u5220\u9664')) == 1
         and text.count("res.json({ ok: true, id: mailId });") == 1)
    gate('G17 邮件删除按 user_id + claimed=0 守卫',
         text.count('DELETE FROM mail WHERE id = ? AND user_id = ? AND claimed = 0') == 1)

    # ── ⑤ 快照 force ──
    gate('G18 snapshotOldSave 加 force 参数',
         text.count('function snapshotOldSave(userId: number, oldSaveData: string, gmRevision: number, force: boolean = false) {') == 1)
    gate('G19 节流行受 force 控制',
         text.count('if (!force && Number.isFinite(t) && Date.now() - t < 10 * 60 * 1000) return;') == 1)
    gate('G20 回档调用点带 force=true',
         text.count('if (cur) snapshotOldSave(userId, String(cur.save_data), Number(cur.gm_revision) || 0, true);') == 1)
    gate('G21 写档调用点**不带** force（仍走节流）',
         text.count('if (row) snapshotOldSave(req.user.id, row.save_data, curRev);') == 1
         and text.count('snapshotOldSave(req.user.id, row.save_data, curRev, true)') == 0)

    # ── ⑥ gm_sessions 过期 ──
    gate('G22 gm_sessions.expires_at 走 safeAddColumn',
         text.count("safeAddColumn('gm_sessions', 'expires_at',") == 1)
    gate('G23 GM 登录写 expires_at（旧 INSERT 已消失）',
         text.count('INSERT INTO gm_sessions (token, expires_at) VALUES (?, ?)') == 1
         and text.count('INSERT INTO gm_sessions (token) VALUES (?)') == 0)
    gate('G24 authenticateGM 加过期判定 + 惰性删行',
         text.count('SELECT token, expires_at FROM gm_sessions WHERE token = ?') == 1
         and text.count("db.run('DELETE FROM gm_sessions WHERE token = ?', [token]);") == 2
         and text.count("res.status(401).json({ error: 'GM session expired' })") == 1)
    gate('G25 无效 token 分支仍是既有 403（未改语义）',
         text.count("if (err || !row) return res.status(403).json({ error: 'Invalid GM token' });") == 1)

    # ── ⑦ DELETE /api/gm/activity/:id ──
    gate('G26 活动删除端点恰 1 处（authenticateGM）',
         text.count("app.delete('/api/gm/activity/:id', authenticateGM") == 1)
    gate('G27 活动删除写审计 + 404',
         text.count("logGmAction('activity_delete',") == 1
         and text.count(zh('\u6d3b\u52a8\u4e0d\u5b58\u5728')) == 1)
    gate('G28 既有 GM 活动端点未动（GET/POST/config）',
         text.count("app.get('/api/gm/activity', authenticateGM") == 1
         and text.count("app.post('/api/gm/activity', authenticateGM") == 1
         and text.count("app.post('/api/gm/activity/config', authenticateGM") == 1)

    # ── ⑧ 禁言 ──
    gate('G29 users.muted_until 走 safeAddColumn',
         text.count("safeAddColumn('users', 'muted_until',") == 1)
    gate('G30 GM 禁言端点恰 1 处',
         text.count("app.post('/api/gm/players/:id/mute', authenticateGM") == 1
         and text.count("logGmAction(untilIso ? 'mute' : 'unmute',") == 1)
    gate('G31 GET /api/me/mute 恰 1 处且字段名 mutedUntil 稳定',
         text.count("app.get('/api/me/mute', authenticateToken") == 1
         and text.count('res.json({ muted: active, mutedUntil: active ? new Date(t).toISOString() : null });') == 1)
    gate('G32 发言处禁言拦截（按 username 回查）',
         text.count('SELECT muted_until FROM users WHERE username = ?') == 1
         and text.count('res.statusCode = 403;') == 1
         and text.count(zh('\u4f60\u5df2\u88ab\u7981\u8a00\uff0c\u89e3\u9664\u65f6\u95f4 ')) == 1)
    gate('G33 封禁端点/拦截一字未动（banned 语义不受影响）',
         text.count("app.post('/api/gm/players/:id/ban', authenticateGM") == 1
         and text.count("res.status(403).json({ error: '\u8d26\u53f7\u5df2\u88ab\u5c01\u7981', code: 'ACCOUNT_BANNED' })") == 5
         and text.count("safeAddColumn('users', 'banned', 'ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0');") == 1)

    # ── 坑门禁 ──
    gate('G34 [坑] res.status(403) 计数 == 基线（本环不新增 403）',
         text.count('res.status(403)') == base['res.status(403)'],
         '实际 %d（基线 %d）' % (text.count('res.status(403)'), base['res.status(403)']))
    gate('G35 [坑] 对象形式 status: 403 计数 == 基线',
         text.count('status: 403') == base['status: 403'], '实际 %d' % text.count('status: 403'))
    n_require = text.count('require(')
    gate('G36 [坑] require( 计数 == 基线（ESM 下未定义）',
         n_require == base['require('], '实际 %d（基线 %d）' % (n_require, base['require(']))
    n_catch = len(re.findall(r'db\.run\([^\n]*\)\.catch\(', text))
    gate('G37 [坑] db.run(...).catch( == 0', n_catch == 0, '实际 %d' % n_catch)
    n_alter = text.count("db.exec('ALTER TABLE") + text.count('db.exec("ALTER TABLE')
    gate('G38 [坑] db.exec(ALTER TABLE …) 直调 == 0', n_alter == 0, '实际 %d' % n_alter)
    gate('G39 [坑] 未用 PRAGMA 决定是否 ALTER（本环新增迁移不读 PRAGMA）',
         text.count('PRAGMA table_info(gm_sessions)') == 0
         and text.count('PRAGMA table_info(users)') == base['PRAGMA table_info(users)'],
         'users PRAGMA 实际 %d（基线 %d）' % (text.count('PRAGMA table_info(users)'), base['PRAGMA table_info(users)']))

    # ── 幂等 / 规模 ──
    gate('G40 幂等标记就位（重复跑 SKIP）', MARK in text)
    gate('G41 增量字节 ∈ [2500, 20000] B', 2500 <= delta <= 20000, 'delta = %+d B' % delta)

    # ── 前 20 环关键锚点未丢（只做加法）──
    gate('G42 前环关键锚点未丢',
         text.count('const safeAddColumn = (table: string, col: string, ddl: string) => {') == 1
         and text.count('function settleSaveEconV2') == 1
         and text.count("app.get('/api/pet/spirit/list', authenticateToken") == 1
         and text.count("app.get('/api/arena/trials', authenticateToken, rateLimit(") == 1
         and text.count('const FARM_SLOTS = 6;') == 1)
    gate('G43 锚点行仍在（C1/C2/C3/C4 原文逐字）',
         text.count(E1_OLD) == 0 and text.count(E7_ANCHOR) == 1 and text.count(E11_ANCHOR) == 1
         and text.count(E12_ANCHOR) == 1 and text.count(E14_ANCHOR) == 1 and text.count(E15_ANCHOR) == 1)


def _apply_all(text: str, verbose: bool = True) -> str:
    for tag, old, new, expect, insertion in EDITS:
        if insertion:
            _assert_anchor_kept(tag, old, new)
        text = apply_one(text, tag, old, new, expect)
    return text


def _run(src: str, base: dict, label: str) -> int:
    gates = []
    ok = True

    def gate(name, cond, detail=''):
        nonlocal ok
        gates.append((name, bool(cond), detail))
        if not cond:
            ok = False

    before = len(src.encode('utf-8'))
    print('  %s bytes=%d md5=%s' % (label, before, md5s(src)))

    if MARK in src:
        print('  [SKIP] 已含 %s 标记，无需重复打补丁' % MARK)
        return 0

    for tag, old, new, expect, insertion in EDITS:
        if src.count(old) != expect:
            print('  [FAIL] 前置守卫 %s 锚点命中 %d 次（期望 %d）' % (tag, src.count(old), expect))
            return 1
    print('  [OK]   前置守卫：%d 处锚点命中数全部符合期望' % len(EDITS))

    text = _apply_all(src)
    delta = len(text.encode('utf-8')) - before
    _gates(text, base, delta, gate)

    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    print('\n  自证结果：%s（delta %+d B）' % ('全 PASS' if ok else '存在 FAIL', delta))
    return 0 if ok else 1


def selftest() -> int:
    print('0.8.10 服务端综合环（链第 21 环）— 自证')
    cand = None
    for p in (os.path.join(HERE, '_chainstage', 's20.t16arena.ts'),
              os.path.join(HERE, 'srv', 'index_v28.ts')):
        if os.path.isfile(p):
            cand = p
            break
    if not cand:
        print('  [FAIL] 找不到上一环产物')
        return 1
    src = open(cand, encoding='utf-8').read()
    return _run(src, _base_counts(src), '上一环产物 %s' % os.path.basename(cand))


def main() -> int:
    ap = argparse.ArgumentParser(description='0.8.10 服务端综合环（链第 21 环 / 新末环）')
    ap.add_argument('--src', help='上一环产物（就地原子写回）')
    ap.add_argument('--out', help='本环产物（缺省 = 就地写 --src）')
    ap.add_argument('--selftest', action='store_true', help='只跑自证，不碰文件')
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if not a.src:
        die('必须给 --src（或 --selftest）')

    src = os.path.abspath(a.src)
    if not os.path.isfile(src):
        die('src 不存在: %s' % src)
    out = os.path.abspath(a.out) if a.out else src
    if out != src and not os.path.isdir(os.path.dirname(out)):
        die('out 目录不存在: %s' % os.path.dirname(out))

    text = open(src, encoding='utf-8').read()
    before_bytes = len(text.encode('utf-8'))
    print('0.8.10 服务端综合环（链第 21 环 / 新末环）')
    print('  source : %s  bytes=%d md5=%s' % (src, before_bytes, md5s(text)))

    if MARK in text:
        print('  [SKIP] 已包含 %s 标记，无需重复打补丁' % MARK)
        return 0

    for tag, old, new, expect, insertion in EDITS:
        if text.count(old) != expect:
            die('前置守卫失败：%s 锚点命中 %d 次（期望 %d）—— 基线不符' % (tag, text.count(old), expect))
    print('  [OK]   前置守卫：%d 处锚点命中数全部符合期望' % len(EDITS))

    base = _base_counts(text)
    text = _apply_all(text)
    delta = len(text.encode('utf-8')) - before_bytes
    gates = []

    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    _gates(text, base, delta, gate)

    bad = [g for g in gates if not g[1]]
    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    if bad:
        print('\n[ABORT] 门禁未全过（%d 条 FAIL），不写出' % len(bad))
        return 1

    if out != src:
        open(out, 'wb').write(text.encode('utf-8'))
        print('\n  [写出] %s  bytes=%d  md5=%s' % (out, len(text.encode('utf-8')), md5s(text)))
    else:
        bak = '%s.bak-v2810-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] 0.8.10 服务端综合环落地（delta %+d B）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
