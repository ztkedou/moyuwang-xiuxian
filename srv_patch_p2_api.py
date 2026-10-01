# -*- coding: utf-8 -*-
"""
srv_patch_p2_api.py -- P2-(9) 接口 id/入参健壮性补丁（服务端生成器）

Reads : srv/index_v28.ts   (in-place atomic rewrite)
Writes: srv/index_v28.ts

背景
----
`String(x)` / `Number(x)` / `parseInt(x)` 在 x 是「非原始类型且 toString / Symbol.toPrimitive
不可调用」的对象时会**抛 TypeError: Cannot convert object to primitive value**。客户端只要发
`{"gongfa":{"toString":1}}` 这类 JSON 就能让服务端在**任何**「拿输入当串/数用」的端点上 500。

本机沙盒 s21（idx=21，API :3121）实测（localtest/t_api_idrobust.py，修复前）：
  * 51 个 player 端点变体在 `{"toString":1}` 下回 500（期望 4xx）；
  * 4 个 market 端点**完全不带 body**（Express 5 下 req.body === undefined）也回 500，
    根因是 `const { listingId } = req.body;` 直接解构 undefined。

修法（按任务要求：入口类型收窄，不是到处 try/catch）
----
引入三个「永不抛」的原始类型收窄助手 asStr / asNum / asInt：
  * 只接受 string / number / boolean / null（与旧 `String(x ?? '')`、`Number(x)`、`parseInt(x)`
    在这些原始类型上的语义**逐一对齐**）；
  * 其余（object / array / symbol / undefined）一律降级为 '' / NaN，从而**落到既有的 400 守卫**上；
  * 再把「把用户输入当原始类型用」的调用点全部换成助手，并对 `const {..} = req.body` 补 `|| {}`。

设计要点
  * 助手是**纯函数**，对合法请求零行为差异；只把「原来 500」变成「原来就该有的 400」。
  * 只动「入参转换」这一层，不碰任何业务/数值/事务逻辑。

Engineering guarantees (any failure => sys.exit(1), no write):
  1. every anchor occurs EXACTLY the expected number of times in the source;
  2. round-trip: replacing each new fragment back with its old fragment (reverse order) yields
     the source byte-for-byte;
  3. every newly introduced identifier occurs 0 times in the source;
  4. every INJECTED fragment is pure ASCII;
  5. the source is not already patched;
  6. no anchor is a substring of another anchor / of an injected fragment (keeps global
     replacement unambiguous); no injected fragment is a substring of another one.

NOTE（可复现性）：本补丁打在链式产物的末端（`index_v28.ts`），in-place。
      若有人从 `index_v27b.ts` 重跑整条链，必须在最后再跑一次本脚本。

Run (cwd = yl-deploy/):
  python srv_patch_p2_api.py                 # 就地打补丁（原子写）
  python srv_patch_p2_api.py --check         # 只体检，不写
"""
import argparse
import hashlib
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

HELPERS_ANCHOR = "function logGmAction(action: string, target?: string, detail?: any) {"

HELPERS = (
    "// v28.2 (P2-9): safe primitive coercion for untrusted request values.\n"
    "// `String(x)` / `Number(x)` / `parseInt(x)` THROW a TypeError (\"Cannot convert object to\n"
    "// primitive value\") when `x` is a non-primitive whose `toString` / `Symbol.toPrimitive` is\n"
    "// not callable -- e.g. body {\"id\":{\"toString\":1}} or {\"gongfa\":{\"toString\":1}}. That\n"
    "// surfaced as HTTP 500 for plain client junk. These helpers accept only real primitives and\n"
    "// never throw: anything else degrades to '' / NaN so the pre-existing guard answers 4xx.\n"
    "function asStr(x: unknown): string {\n"
    "  if (typeof x === 'string') return x;\n"
    "  if (typeof x === 'number' && Number.isFinite(x)) return String(x);\n"
    "  if (typeof x === 'boolean') return x ? 'true' : 'false';\n"
    "  return '';\n"
    "}\n"
    "function asNum(x: unknown): number {\n"
    "  if (typeof x === 'number') return x;\n"
    "  if (typeof x === 'string') return Number(x);\n"
    "  if (typeof x === 'boolean') return x ? 1 : 0;\n"
    "  if (x === null) return 0;\n"
    "  return NaN;\n"
    "}\n"
    "function asInt(x: unknown): number {\n"
    "  if (typeof x === 'number') return Number.isFinite(x) ? Math.trunc(x) : NaN;\n"
    "  if (typeof x === 'string') { const n = parseInt(x, 10); return Number.isFinite(n) ? n : NaN; }\n"
    "  return NaN;\n"
    "}\n"
)

# (label, old, new, expected_count)  -- 全部纯 ASCII
EDITS = [
    # ---- 0) 助手注入 ----
    ("helpers", HELPERS_ANCHOR, HELPERS + HELPERS_ANCHOR, 1),

    # ---- 1) 纯逻辑核心：把 String(key)/Number(raw) 换成收窄助手 ----
    ("core-alchemyRecipe",
     "  return key != null && Object.prototype.hasOwnProperty.call(ALCHEMY_RECIPES, String(key))"
     " ? ALCHEMY_RECIPES[String(key)] : null;",
     "  return key != null && Object.prototype.hasOwnProperty.call(ALCHEMY_RECIPES, asStr(key))"
     " ? ALCHEMY_RECIPES[asStr(key)] : null;", 1),
    ("core-alchemyRecipeByName",
     "  const n = String(name ?? '');",
     "  const n = asStr(name);", 1),
    ("core-gongfaOk",
     "  return key != null && Object.prototype.hasOwnProperty.call(GONGFA_LIST, String(key));",
     "  return key != null && Object.prototype.hasOwnProperty.call(GONGFA_LIST, asStr(key));", 1),
    ("core-wudaoDaoOk",
     "  return key != null && Object.prototype.hasOwnProperty.call(WUDAO_DAOS, String(key));",
     "  return key != null && Object.prototype.hasOwnProperty.call(WUDAO_DAOS, asStr(key));", 1),
    ("core-farmCrop",
     "  return key != null && Object.prototype.hasOwnProperty.call(FARM_CROPS, String(key))"
     " ? FARM_CROPS[String(key)] : null;",
     "  return key != null && Object.prototype.hasOwnProperty.call(FARM_CROPS, asStr(key))"
     " ? FARM_CROPS[asStr(key)] : null;", 1),
    ("core-slotOk",
     "  const s = Number(raw);",
     "  const s = asNum(raw);", 2),
    ("core-clampPage",
     "  const p = Math.floor(Number(raw) || 1);",
     "  const p = Math.floor(asNum(raw) || 1);", 1),
    ("core-clampChronicleText",
     "function clampChronicleText(t: unknown): string { return String(t ?? '')"
     ".slice(0, CHRONICLE_MAX_TEXT); }",
     "function clampChronicleText(t: unknown): string { return asStr(t)"
     ".slice(0, CHRONICLE_MAX_TEXT); }", 1),
    ("core-bountyTitleClamp",
     "function bountyTitleClamp(t: unknown): string { return String(t ?? '')"
     ".trim().slice(0, BOUNTY_TITLE_MAX); }",
     "function bountyTitleClamp(t: unknown): string { return asStr(t)"
     ".trim().slice(0, BOUNTY_TITLE_MAX); }", 1),
    ("core-bountyDescClamp",
     "function bountyDescClamp(t: unknown): string { return String(t ?? '')"
     ".trim().slice(0, BOUNTY_DESC_MAX); }",
     "function bountyDescClamp(t: unknown): string { return asStr(t)"
     ".trim().slice(0, BOUNTY_DESC_MAX); }", 1),
    ("core-clampPetDetail",
     "function clampPetDetail(t: unknown): string { return String(t ?? '').slice(0, 60); }",
     "function clampPetDetail(t: unknown): string { return asStr(t).slice(0, 60); }", 1),
    ("core-bountyRewardOk",
     "  const n = Number(raw);",
     "  const n = asNum(raw);", 1),
    ("core-achPickClaimable",
     "  const id = String(requestedId);",
     "  const id = asStr(requestedId);", 1),
    ("core-findUserByName",
     "  const name = String(nameRaw ?? '').trim().slice(0, 32);",
     "  const name = asStr(nameRaw).trim().slice(0, 32);", 1),
    ("core-sectGfAdvance",
     "  const id = String(idRaw || '');",
     "  const id = asStr(idRaw);", 1),

    # ---- 2) 路由层：number 型入参 ----
    ("slot", "Math.floor(Number(req.body?.slot))", "Math.floor(asNum(req.body?.slot))", 5),
    ("uid", "Math.floor(Number(req.body?.userId))", "Math.floor(asNum(req.body?.userId))", 4),
    ("apprenticeId", "Math.floor(Number(req.body?.apprenticeId))",
     "Math.floor(asNum(req.body?.apprenticeId))", 3),
    ("friendId", "Math.floor(Number(req.body?.friendId))",
     "Math.floor(asNum(req.body?.friendId))", 2),
    ("battleId", "Math.floor(Number(req.body?.battleId))",
     "Math.floor(asNum(req.body?.battleId))", 2),
    ("enemyId", "Math.floor(Number(req.body?.enemyId))",
     "Math.floor(asNum(req.body?.enemyId))", 1),
    ("peerId", "Math.floor(Number(req.body?.peerId))", "Math.floor(asNum(req.body?.peerId))", 1),
    ("side", "Math.floor(Number(req.body?.side))", "Math.floor(asNum(req.body?.side))", 1),
    ("betStones", "Math.floor(Number(req.body?.stones))",
     "Math.floor(asNum(req.body?.stones))", 1),
    ("weekDay", "Math.floor(Number(req.body?.day))", "Math.floor(asNum(req.body?.day))", 1),
    ("bountyId", "Math.floor(Number(req.body?.id))", "Math.floor(asNum(req.body?.id))", 3),
    ("sectJoinId", "Math.floor(Number(req.body?.sectId))",
     "Math.floor(asNum(req.body?.sectId))", 1),
    ("gmEngineOn", "Number(req.body?.engineOn)", "asNum(req.body?.engineOn)", 1),
    ("rebirthCount", "Number(req.body?.count)", "asNum(req.body?.count)", 1),
    ("sectAmount", "Number(req.body?.amount)", "asNum(req.body?.amount)", 1),

    # ---- 3) 路由层：parseInt 入参 ----
    ("mailClaimId", "parseInt(req.body?.id)", "asInt(req.body?.id)", 2),
    ("questTier", "parseInt(req.body?.tier)", "asInt(req.body?.tier)", 1),
    ("feastCoupleId", "parseInt(req.body?.coupleId)", "asInt(req.body?.coupleId)", 1),
    ("mailReadId", "  const mailId = parseInt(id);", "  const mailId = asInt(id);", 1),
    ("titleEquipTid", "  const tid = parseInt(raw);", "  const tid = asInt(raw);", 1),

    # ---- 4) 路由层：string 型入参 ----
    ("wudaoDao", "String(req.body?.dao ?? '')", "asStr(req.body?.dao)", 1),
    ("gongfaKey", "String(req.body?.gongfa ?? '')", "asStr(req.body?.gongfa)", 1),
    ("farmCropKey", "String(req.body.crop)", "asStr(req.body.crop)", 1),
    ("swornName", "const name = String(req.body?.name || '').trim().slice(0, 12);",
     "const name = asStr(req.body?.name).trim().slice(0, 12);", 1),
    ("sectName", "const name = String(req.body?.name ?? '').trim();",
     "const name = asStr(req.body?.name).trim();", 1),
    ("sectRole", "String(req.body?.role || '')", "asStr(req.body?.role)", 1),
    ("guideStep", "String(req.body?.stepId || '')", "asStr(req.body?.stepId)", 1),
    ("sectTaskKey", "String(req.body?.taskKey || '')", "asStr(req.body?.taskKey)", 1),
    ("sectWelfareKind", "String(req.body?.kind || '')", "asStr(req.body?.kind)", 1),
    ("sectNotice", "String(req.body?.notice ?? '')", "asStr(req.body?.notice)", 1),
    ("gmBanReason", "String(req.body?.reason || '')", "asStr(req.body?.reason)", 1),

    # ---- 5) market/list 与 GM 入参 ----
    ("mktPrice", "  const priceNum = Math.floor(Number(price));",
     "  const priceNum = Math.floor(asNum(price));", 1),
    ("mktCleanId",
     "  const cleanId = (listingId || '').toString().replace(/^(?:market-)+/, '');",
     "  const cleanId = asStr(listingId).replace(/^(?:market-)+/, '');", 3),
    ("mktItemType", "  const safeItemType = String(itemType || '\u6750\u6599').slice(0, 50);",
     "  const safeItemType = (asStr(itemType) || '\\u6750\\u6599').slice(0, 50);", 1),
    ("mktDesc", "  const safeDescription = String(description || '').slice(0, 500);",
     "  const safeDescription = asStr(description).slice(0, 500);", 1),
    ("mktRarity", "  const safeRarity = String(rarity || '\u666e\u901a').slice(0, 50);",
     "  const safeRarity = (asStr(rarity) || '\\u666e\\u901a').slice(0, 50);", 1),
    ("mktSlot", "  const safeSlot = equipmentSlot ? String(equipmentSlot).slice(0, 50) : null;",
     "  const safeSlot = equipmentSlot ? asStr(equipmentSlot).slice(0, 50) : null;", 1),
    ("mktQuantity", "  const listingQuantity = Math.max(1, Math.floor(Number(quantity)) || 1);",
     "  const listingQuantity = Math.max(1, Math.floor(asNum(quantity)) || 1);", 1),
    ("gmMktQuantity",
     "  if (quantity != null && Number(quantity) >= 1) { sets.push('quantity = ?');"
     " params.push(Math.floor(Number(quantity))); }",
     "  if (quantity != null && asNum(quantity) >= 1) { sets.push('quantity = ?');"
     " params.push(Math.floor(asNum(quantity))); }", 1),
    ("gmMailTitle", "  const safeTitle = String(title || '').trim().slice(0, 100);",
     "  const safeTitle = asStr(title).trim().slice(0, 100);", 1),
    ("gmMailContent", "  const safeContent = String(content || '').slice(0, 2000);",
     "  const safeContent = asStr(content).slice(0, 2000);", 1),
    ("gmMailSender", "  const safeSender = String(sender || 'system').slice(0, 32);",
     "  const safeSender = (asStr(sender) || 'system').slice(0, 32);", 1),
    ("gmMailUserId", "  if (userId) return sendTo(parseInt(userId));",
     "  if (userId) return sendTo(asInt(userId));", 1),
    ("gmMailUsername", "String(username).slice(0, 32)", "asStr(username).slice(0, 32)", 2),
    ("gmTitleTid", "  const tid = parseInt(titleId);", "  const tid = asInt(titleId);", 1),
    ("gmTitleUid", "    if (userId) uid = parseInt(userId);",
     "    if (userId) uid = asInt(userId);", 1),

    # ---- 6) 缺失 body：Express 5 下 req.body 可为 undefined，直接解构会抛 ----
    ("body-register", "  const { username, password } = req.body;",
     "  const { username, password } = req.body || {};", 2),
    ("body-refresh",
     "app.post('/api/auth/refresh', async (req: any, res: any) => {\n"
     "  const { refreshToken } = req.body;",
     "app.post('/api/auth/refresh', async (req: any, res: any) => {\n"
     "  const { refreshToken } = req.body || {};", 1),
    ("body-ai", "  const { messages, temperature = 0.8, max_tokens = 500 } = req.body;",
     "  const { messages, temperature = 0.8, max_tokens = 500 } = req.body || {};", 1),
    ("body-mktlist",
     "  const { itemName, itemType, description, rarity, price, quantity, effect, isEquippable,"
     " equipmentSlot, itemSourceJson } = req.body;",
     "  const { itemName, itemType, description, rarity, price, quantity, effect, isEquippable,"
     " equipmentSlot, itemSourceJson } = req.body || {};", 1),
    ("body-listingId", "  const { listingId } = req.body;",
     "  const { listingId } = req.body || {};", 3),
]

NEW_IDENTIFIERS = ["asStr(", "asNum(", "asInt("]


def fail(msg: str) -> None:
    print("FAIL: " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 5) already patched?
    for label, old, new, cnt in EDITS:
        if src.count(new) > 0 and src.count(old) == 0:
            fail("source looks already patched at %s" % label)

    # 3) identifier collision
    for ident in NEW_IDENTIFIERS:
        if src.count(ident) != 0:
            fail("new identifier already present (%d): %r" % (src.count(ident), ident))

    # 4) injected text ASCII
    for label, old, new, cnt in EDITS:
        try:
            new.encode("ascii")
        except UnicodeEncodeError as e:
            fail("injected text for %s is not ASCII: %s" % (label, e))

    # 1) anchor count
    for label, old, new, cnt in EDITS:
        n = src.count(old)
        if n != cnt:
            fail("anchor %s occurs %d times (want %d): %r" % (label, n, cnt, old[:90]))

    # 1b) the injected fragment must not already exist in the source (else reverse is ambiguous)
    for label, old, new, cnt in EDITS:
        if src.count(new) != 0:
            fail("injected fragment for %s already present x%d in source: %r"
                 % (label, src.count(new), new[:90]))

    # 6a) no old is a substring of another old
    for i, (li, oi, ni, ci) in enumerate(EDITS):
        for j, (lj, oj, nj, cj) in enumerate(EDITS):
            if i != j and oi in oj:
                fail("anchor %s is a substring of anchor %s: %r" % (li, lj, oi[:60]))
    # 6b) no old appears inside an injected fragment; no new inside another new
    for i, (li, oi, ni, ci) in enumerate(EDITS):
        for j, (lj, oj, nj, cj) in enumerate(EDITS):
            if oi in nj and not (i == j and oi == oj):
                # 允许同一 edit 自身的 old==new 情形；其余一律拒绝
                fail("anchor %s appears inside injected %s" % (li, lj))
            if i != j and ni in nj:
                fail("injected %s is a substring of injected %s" % (li, lj))

    out = src
    for label, old, new, cnt in EDITS:
        before = out.count(new)
        out = out.replace(old, new)
        after = out.count(new)
        if after - before != cnt:
            fail("edit %s: replaced %d occurrences (want %d)" % (label, after - before, cnt))

    # 2) round-trip (reverse order, global) must reproduce the source exactly
    rt = out
    for label, old, new, cnt in reversed(EDITS):
        rt = rt.replace(new, old)
    if rt != src:
        fail("round-trip mismatch: product is not an exact superset of source")

    # ---- 语义断言 ----
    # 硬断言：只针对本补丁**必然消除**的字符串（与具体 edit 一一对应），
    # 这样即使本补丁在链式装配里被排在别的补丁之后，也不会被他人新增代码误伤。
    if out.count("function asStr(x: unknown): string {") != 1:
        fail("asStr helper not injected exactly once")
    if out.count("function asNum(x: unknown): number {") != 1:
        fail("asNum helper not injected exactly once")
    if out.count("function asInt(x: unknown): number {") != 1:
        fail("asInt helper not injected exactly once")
    for gone in ("String(idRaw", "String(requestedId)", "String(nameRaw",
                 "String(key)", "String(t ?? '')", "String(name ?? '')",
                 "const s = Number(raw);", "const n = Number(raw);",
                 "(listingId || '').toString()",
                 "Math.floor(Number(price))", "Math.floor(Number(quantity))",
                 "Number(req.body?.count)", "Number(req.body?.amount)",
                 "Number(req.body?.engineOn)"):
        if out.count(gone) != 0:
            fail("residual unsafe coercion %r x%d (should be gone)" % (gone, out.count(gone)))
    if "  const saveData = req.body;" not in out:
        fail("/api/save saveData assignment was disturbed")
    if out.count("asStr(") < 20 or out.count("asNum(") < 20 or out.count("asInt(") < 4:
        fail("coercion helper call sites look too few")

    # 软提示（不阻断）：链式装配中若别的补丁又引入了裸 `X(req.body...)`，这里只告警，
    # 由 ver-a/ver-b 的独立复测去抓；不因他人代码把本补丁卡死。
    for p in ("String(req.body", "Number(req.body", "parseInt(req.body"):
        if out.count(p):
            print("WARN: residual %r x%d remains in product (not introduced by this patch)"
                  % (p, out.count(p)))

    if a.check:
        print("CHECK OK: %d edits, anchors unique/counted, round-trip byte-exact, ASCII, gates pass"
              % len(EDITS))
        return

    # 原子写（in-place）
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".p2api_", suffix=".ts")
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    def md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    print("OK  source : %s  chars=%d bytes=%d md5=%s"
          % (src_path, len(src), len(src.encode("utf-8")), md5(src)))
    print("OK  product: %s  chars=%d bytes=%d md5=%s"
          % (src_path, len(out), len(out.encode("utf-8")), md5(out)))
    print("OK  delta  : chars=+%d bytes=+%d"
          % (len(out) - len(src), len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    print("OK  edits  : %d  asStr=%d asNum=%d asInt=%d"
          % (len(EDITS), out.count("asStr("), out.count("asNum("), out.count("asInt(")))
    print("OK  all anchors counted, identifiers collision-free, round-trip byte-exact, ASCII")


if __name__ == "__main__":
    main()
