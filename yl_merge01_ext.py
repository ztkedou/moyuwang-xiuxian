# -*- coding: utf-8 -*-
r"""yl_merge01_ext.py — 0.8.13 批次 · 上游 bug 摘取 M-1/M-2（客户端 · merge01）

来源：`报告_上游融合评估.md` §4.1 的 M-1 / M-2（上游仓库 JeasonLoop/react-xiuxian-game）。

=========================================================================== M-1 · 宠物技能文案 `$` 字面量 + 属性为 0 渲染孤立 0
上游 commit `68b1480`（`PetModal.tsx` 8 处 `攻击+${…}` → `攻击+{…}`；`AuctionHouseModal.tsx`
6 处 `x && …` → `!!x && …`）。产物逐字实测：

  (a) `$` 字面量 **8 处**，全部在 PetModal 宠物技能 buff 块（`["攻击+$",P.effect.buff.attack]` 形态），
      渲染成 `攻击+$100` / `攻击+$50%` —— **真 bug，线上可见**。
  (b) 「真值判断 → 孤立 0」共 **35 个守卫**（报告计 32，漏了 3 处 `.effect.exp`）：
        · 4 个物品/装备效果块 × `.effect.{attack,defense,hp,spirit,physique,speed}` = 24
          （w 块 ×2：坊市商店 + 批量选择；m 块 ×1：装备选择；L 块 ×1：交易行）
        · PetModal buff 块 × `.buff.{attack,attackPercent,defense,defensePercent,hp,
          speedPercent,critChance,dodge}` = 8
        · `.effect.exp` ×3（w×2 + m×1；L 块无 exp）
      React 下 `0 && <div/>` 求值为 `0` 并渲染出**孤立数字 0**。修法 = 加 `!!` 前缀（上游同款）。

  ★ **可达性核实（诚实结论）**：**当前数据下 0 不可达**。
    · 产物 228 个 `effect:{}` 字面量**无一个字段为 0**（脚本逐对象扫描）；
    · 装备生成器 `iy()`：`h[N]=Math.min(q,g)` 且 `q>=Math.max(_*M, C*.8)`，
      `C=Math.floor(baseX*x*T*M)`；最低境界 baseDefense/baseSpirit=5、最低稀有度 mid=(.18+.32)/2=.25、
      `ny=[1,...]`、`T>=1` ⇒ `C>=1` ⇒ `q>=0.8>0` ⇒ **装备效果恒 >0**；
    · 消耗品生成器 `ry()`：`T[N]=Math.floor(t[N]*b)`，`b=ny[v]*(1+(l-1)*.08)>=1`，
      仅在模板 `t[N]===0` 时为 0，而模板无 0。
    ⇒ 这 35 个 `!!` 属**潜在/防御性**修复（`0` 之外行为逐字节不变，零风险；防未来数据漂移），
      **不是**线上可达缺陷。若 lead 要求最小 diff，可整段回退 (b)、只保留 (a)。

=========================================================================== M-2 · refreshAccessToken 共享 Promise 卡死
上游 commit `1ec1b63`。我方 `pS()` 与上游**被替换掉的旧版逐字同构**：

    let Pl=null;
    async function pS(){ if(Pl)return Pl; const r=Et.getState().refreshToken;
      return Pl=(async()=>{ try{ if(!r) throw Et.getState().logout(),Je(Hr),new Error(Hr); … }
                            finally{ Pl=null } })(), Pl }

`refreshToken` 为空（falsy）时 IIFE 体在首个 await 前同步抛出 ⇒ `finally` 先执行 `Pl=null`，
**随后外层赋值把 `Pl` 写成那个已 reject 的 Promise**（`Pl` 永不清除）⇒ 此后 `if(Pl)return Pl`
永远返回同一个 reject ⇒ **token 刷新通道永久失效**（连 logout 都不再触发）。

**可达**：外链登录 `?token=…&username=…` 无 refreshToken 时 `h({token:N,refreshToken:""})`
⇒ `Et.getState().refreshToken===""`（falsy）⇒ 一旦 401 走 `Xc → pS()` 即命中。

修法（照搬上游 `1ec1b63` 的机制，去掉其 sessionId 部分——我方无该字段）：
  · 用 `Promise.resolve().then(async()=>{…})` **在 microtask 里启动**，保证 `Pl=tracked` 赋值
    发生在任何同步抛出之前；
  · `const tracked=pending.finally(()=>{ if(Pl===tracked)Pl=null })` —— 只在仍是「当前那一个」时清空；
  · 保留原语义：`!r` → logout+toast+throw；`!a.ok` 且 refreshToken 已变 → 返回 `""`；成功 → setTokens。
Node 对照验证：旧版「无 refreshToken」第 2 次调用拿到同一 reject 且 logout 不再触发（卡死复现）；
新版每次都能清空 `Pl`、通道恢复，且 in-flight 时并发仍复用同一 fetch（不重复刷新）。

=========================================================================== 门禁计数清单（给接线人入 dryrun）
  ① '"攻击+$"' 等 6 个字面量                                 基线 8 → 改后 0
  ② _A_BUF_OLD（含 $ 的旧宠物 buff 块）                      基线 1 → 改后 0
  ③ _A_BUF_NEW（无 $ + !! 的新宠物 buff 块）                 基线 0 → 改后 1
  ④ _A_EFF_W_OLD / NEW                                       基线 2 → 0 / 0 → 2
  ⑤ _A_EFF_M_OLD / NEW                                       基线 1 → 0 / 0 → 1
  ⑥ _A_EFF_L_OLD / NEW                                       基线 1 → 0 / 0 → 1
  ⑦ _A_PS_OLD / NEW                                          基线 1 → 0 / 0 → 1
  ⑧ 对照面：Xc / pS 头部 / dungeon 调用点 / buff 外壳         恒 1（零改动）

=========================================================================== 技术约束遵守
· 本模块**无注入块**（纯字符串替换），不产生任何新函数/新标识符 ⇒ INJECT_JS=''。
· 不改 build_v26n.py / chain_build.py / 其他 yl_*_ext.py；不改 build/assets/ 产物。
· 全仓已 grep：无任何模块把本模块的 5 个锚点当 needle（含 build_v26n.py 自身）。
· 不改网络调用 / 服务端 / 存档结构；M-2 仅重排 `pS` 内部 Promise 收敛方式，语义不变。
"""

# --------------------------------------------------------------------------- M-1 锚点
_A_BUF_OLD = 'P.effect.buff.attack&&e.jsxs("span",{className:"text-orange-300",children:["攻击+$",P.effect.buff.attack]}),P.effect.buff.attackPercent&&e.jsxs("span",{className:"text-orange-400",children:["攻击+$",Math.floor(P.effect.buff.attackPercent*100),"%"]}),P.effect.buff.defense&&e.jsxs("span",{className:"text-blue-300",children:["防御+$",P.effect.buff.defense]}),P.effect.buff.defensePercent&&e.jsxs("span",{className:"text-blue-400",children:["防御+$",Math.floor(P.effect.buff.defensePercent*100),"%"]}),P.effect.buff.speedPercent&&e.jsxs("span",{className:"text-cyan-300",children:["速度+$",Math.floor(P.effect.buff.speedPercent*100),"%"]}),P.effect.buff.critChance&&e.jsxs("span",{className:"text-red-400",children:["暴击+$",Math.floor(P.effect.buff.critChance*100),"%"]}),P.effect.buff.dodge&&e.jsxs("span",{className:"text-emerald-300",children:["闪避+$",Math.floor(P.effect.buff.dodge*100),"%"]}),P.effect.buff.hp&&e.jsxs("span",{className:"text-green-300",children:["气血+$",P.effect.buff.hp]})'  # PetModal 宠物技能 buff 块（8 处 $ 字面量）
_A_BUF_NEW = '!!P.effect.buff.attack&&e.jsxs("span",{className:"text-orange-300",children:["攻击+",P.effect.buff.attack]}),!!P.effect.buff.attackPercent&&e.jsxs("span",{className:"text-orange-400",children:["攻击+",Math.floor(P.effect.buff.attackPercent*100),"%"]}),!!P.effect.buff.defense&&e.jsxs("span",{className:"text-blue-300",children:["防御+",P.effect.buff.defense]}),!!P.effect.buff.defensePercent&&e.jsxs("span",{className:"text-blue-400",children:["防御+",Math.floor(P.effect.buff.defensePercent*100),"%"]}),!!P.effect.buff.speedPercent&&e.jsxs("span",{className:"text-cyan-300",children:["速度+",Math.floor(P.effect.buff.speedPercent*100),"%"]}),!!P.effect.buff.critChance&&e.jsxs("span",{className:"text-red-400",children:["暴击+",Math.floor(P.effect.buff.critChance*100),"%"]}),!!P.effect.buff.dodge&&e.jsxs("span",{className:"text-emerald-300",children:["闪避+",Math.floor(P.effect.buff.dodge*100),"%"]}),!!P.effect.buff.hp&&e.jsxs("span",{className:"text-green-300",children:["气血+",P.effect.buff.hp]})'  # 去 $ + 8 处 !!
_A_EFF_W_OLD = 'w.effect.attack&&e.jsxs("div",{children:["攻击 +",lt(w.effect.attack)]}),w.effect.defense&&e.jsxs("div",{children:["防御 +",lt(w.effect.defense)]}),w.effect.hp&&e.jsxs("div",{children:["气血 +",lt(w.effect.hp)]}),w.effect.exp&&e.jsxs("div",{children:["修为 +",lt(w.effect.exp)]}),w.effect.spirit&&e.jsxs("div",{children:["神识 +",lt(w.effect.spirit)]}),w.effect.physique&&e.jsxs("div",{children:["体魄 +",lt(w.effect.physique)]}),w.effect.speed&&e.jsxs("div",{children:["速度 +",lt(w.effect.speed)]})]})'  # 坊市商店 + 批量选择 效果块（2 处）
_A_EFF_W_NEW = '!!w.effect.attack&&e.jsxs("div",{children:["攻击 +",lt(w.effect.attack)]}),!!w.effect.defense&&e.jsxs("div",{children:["防御 +",lt(w.effect.defense)]}),!!w.effect.hp&&e.jsxs("div",{children:["气血 +",lt(w.effect.hp)]}),!!w.effect.exp&&e.jsxs("div",{children:["修为 +",lt(w.effect.exp)]}),!!w.effect.spirit&&e.jsxs("div",{children:["神识 +",lt(w.effect.spirit)]}),!!w.effect.physique&&e.jsxs("div",{children:["体魄 +",lt(w.effect.physique)]}),!!w.effect.speed&&e.jsxs("div",{children:["速度 +",lt(w.effect.speed)]})]})'  
_A_EFF_M_OLD = 'm.effect.attack&&e.jsxs("div",{children:["攻击 +",m.effect.attack]}),m.effect.defense&&e.jsxs("div",{children:["防御 +",m.effect.defense]}),m.effect.hp&&e.jsxs("div",{children:["气血 +",m.effect.hp]}),m.effect.spirit&&e.jsxs("div",{children:["神识 +",m.effect.spirit]}),m.effect.physique&&e.jsxs("div",{children:["体魄 +",m.effect.physique]}),m.effect.speed&&e.jsxs("div",{children:["速度 +",m.effect.speed]}),m.effect.exp&&e.jsxs("div",{children:["修为 +",m.effect.exp]})]})'  # 装备选择 效果块（1 处）
_A_EFF_M_NEW = '!!m.effect.attack&&e.jsxs("div",{children:["攻击 +",m.effect.attack]}),!!m.effect.defense&&e.jsxs("div",{children:["防御 +",m.effect.defense]}),!!m.effect.hp&&e.jsxs("div",{children:["气血 +",m.effect.hp]}),!!m.effect.spirit&&e.jsxs("div",{children:["神识 +",m.effect.spirit]}),!!m.effect.physique&&e.jsxs("div",{children:["体魄 +",m.effect.physique]}),!!m.effect.speed&&e.jsxs("div",{children:["速度 +",m.effect.speed]}),!!m.effect.exp&&e.jsxs("div",{children:["修为 +",m.effect.exp]})]})'  
_A_EFF_L_OLD = 'L.effect.attack&&e.jsxs("div",{children:["攻击 +",lt(L.effect.attack)]}),L.effect.defense&&e.jsxs("div",{children:["防御 +",lt(L.effect.defense)]}),L.effect.hp&&e.jsxs("div",{children:["气血 +",lt(L.effect.hp)]}),L.effect.spirit&&e.jsxs("div",{children:["神识 +",lt(L.effect.spirit)]}),L.effect.physique&&e.jsxs("div",{children:["体魄 +",lt(L.effect.physique)]}),L.effect.speed&&e.jsxs("div",{children:["速度 +",lt(L.effect.speed)]})]})'  # 交易行 效果块（1 处）
_A_EFF_L_NEW = '!!L.effect.attack&&e.jsxs("div",{children:["攻击 +",lt(L.effect.attack)]}),!!L.effect.defense&&e.jsxs("div",{children:["防御 +",lt(L.effect.defense)]}),!!L.effect.hp&&e.jsxs("div",{children:["气血 +",lt(L.effect.hp)]}),!!L.effect.spirit&&e.jsxs("div",{children:["神识 +",lt(L.effect.spirit)]}),!!L.effect.physique&&e.jsxs("div",{children:["体魄 +",lt(L.effect.physique)]}),!!L.effect.speed&&e.jsxs("div",{children:["速度 +",lt(L.effect.speed)]})]})'  

# --------------------------------------------------------------------------- M-2 锚点
_A_PS_OLD = 'let Pl=null;async function pS(){if(Pl)return Pl;const r=Et.getState().refreshToken;return Pl=(async()=>{try{if(!r)throw Et.getState().logout(),Je(Hr),new Error(Hr);const a=await fetch(`${ln}/auth/refresh`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refreshToken:r})}),l=await a.json().catch(()=>({}));if(!a.ok){if(Et.getState().refreshToken!==r)return"";throw Et.getState().logout(),Je(l.error||Hr),new Error(Hr)}return Et.getState().setTokens(l.token,l.refreshToken),l.token}finally{Pl=null}})(),Pl}'  # 旧 pS（Pl 永不清除）
_A_PS_NEW = 'let Pl=null;async function pS(){if(Pl)return Pl;const r=Et.getState().refreshToken;const pending=Promise.resolve().then(async()=>{if(!r)throw Et.getState().logout(),Je(Hr),new Error(Hr);const a=await fetch(`${ln}/auth/refresh`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refreshToken:r})}),l=await a.json().catch(()=>({}));if(!a.ok){if(Et.getState().refreshToken!==r)return"";throw Et.getState().logout(),Je(l.error||Hr),new Error(Hr)}return Et.getState().setTokens(l.token,l.refreshToken),l.token});const tracked=pending.finally(()=>{if(Pl===tracked)Pl=null});Pl=tracked;return tracked}'  # 新 pS（microtask 启动 + tracked 收敛）

# --------------------------------------------------------------------------- 注入块（本模块无）
INJECT_JS = ''

# --------------------------------------------------------------------------- 主入口


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    # ---- M-1 (a) 宠物技能 buff 文案：去 8 处字面量 $ ；(b) buff 守卫加 !!
    p.replace('merge01-pet-buff', _A_BUF_OLD, _A_BUF_NEW, expect=1,
              note='M-1 宠物技能 buff：去 $ 字面量 + 8 处 !! 真值判断')
    # ---- M-1 (b) 4 个物品/装备效果块：24（+3 exp）处守卫加 !!
    p.replace('merge01-eff-w', _A_EFF_W_OLD, _A_EFF_W_NEW, expect=2,
              note='M-1 坊市/批量 效果块：7 守卫 ×2 加 !!')
    p.replace('merge01-eff-m', _A_EFF_M_OLD, _A_EFF_M_NEW, expect=1,
              note='M-1 装备选择 效果块：7 守卫加 !!')
    p.replace('merge01-eff-l', _A_EFF_L_OLD, _A_EFF_L_NEW, expect=1,
              note='M-1 交易行 效果块：6 守卫加 !!')
    # ---- M-2 refreshAccessToken 共享 Promise 卡死
    p.replace('merge01-pS', _A_PS_OLD, _A_PS_NEW, expect=1,
              note='M-2 pS：microtask 启动 + tracked 收敛（Pl 不再永久卡死）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- M-1 (a) $ 字面量 ----
        ('M1a·旧宠物buff块（含$）已清除', _A_BUF_OLD,                        0, '==', ''),
        ('M1a·新宠物buff块已就位',        _A_BUF_NEW,                        1, '==', ''),
        ('M1a·字面量$ 全站清零',          '+$"',                             0, '==', '基线=8（6 种标签）'),
        ('M1a·攻击+ 无$',                 'children:["攻击+",P.effect.buff.attack]', 1, '==', ''),
        ('M1a·气血+ 无$',                 'children:["气血+",P.effect.buff.hp]',    1, '==', ''),
        ('M1a·暴击+ 无$',                 'children:["暴击+",Math.floor(P.effect.buff.critChance*100),"%"]', 1, '==', ''),

        # ---- M-1 (b) 孤立 0 守卫（!! 前缀）----
        ('M1b·buff 守卫已加!!',           '!!P.effect.buff.attack&&e.jsxs', 1, '==', ''),
        ('M1b·旧 w 效果块已清除',         _A_EFF_W_OLD,                      0, '==', ''),
        ('M1b·新 w 效果块已就位',         _A_EFF_W_NEW,                      2, '==', ''),
        ('M1b·w.effect 守卫已加!!',       '!!w.effect.attack&&e.jsxs',       2, '==', ''),
        ('M1b·w.effect.exp 守卫已加!!',   '!!w.effect.exp&&e.jsxs',          2, '==', ''),
        ('M1b·旧 m 效果块已清除',         _A_EFF_M_OLD,                      0, '==', ''),
        ('M1b·新 m 效果块已就位',         _A_EFF_M_NEW,                      1, '==', ''),
        ('M1b·m.effect 守卫已加!!',       '!!m.effect.attack&&e.jsxs',       1, '==', ''),
        ('M1b·旧 L 效果块已清除',         _A_EFF_L_OLD,                      0, '==', ''),
        ('M1b·新 L 效果块已就位',         _A_EFF_L_NEW,                      1, '==', ''),
        ('M1b·L.effect 守卫已加!!',       '!!L.effect.attack&&e.jsxs',       1, '==', ''),

        # ---- M-2 ----
        ('M2·旧 pS（finally 内清 Pl）已清除', _A_PS_OLD,                       0, '==', ''),
        ('M2·新 pS 已就位',                   _A_PS_NEW,                       1, '==', ''),
        ('M2·microtask 启动',                 'const pending=Promise.resolve().then(async()=>{', 1, '==', ''),
        ('M2·tracked 收敛清空',               'const tracked=pending.finally(()=>{if(Pl===tracked)Pl=null});', 1, '==', ''),
        ('M2·旧 finally{Pl=null} 已清除',     'finally{Pl=null}})(),Pl}',      0, '==', ''),

        # ---- 对照面（零改动）----
        ('基线·pS 头部未动',              'if(Pl)return Pl',                  1, '==', ''),
        ('基线·Xc 定义未动',              'async function Xc(t,r={})',        1, '==', ''),
        ('基线·401 续期重试未动',         'if(v.status===401&&!c)return await pS(),Xc(t,{...r,_retry:!0})', 1, '==', ''),
        ('基线·dungeon 调用点未动',       'try { await pS(); res = await YlxwDungeonEntryPost(); } catch (eR) {}', 1, '==', ''),
        ('基线·宠物buff 外壳未动',        'P.effect.buff&&e.jsxs("div",{className:"flex flex-wrap gap-x-2 gap-y-0.5 mt-0.5"', 1, '==', ''),
        ('基线·交易行卖家行未动',         'children:["卖家: ",L.sellerName||"匿名修士"]', 1, '==', ''),
    ]
    return gates


if __name__ == '__main__':
    # 自检：在冻结产物上预演（只读，不落盘）
    import yl_patch
    base = yl_patch.load_text('build/assets/index-v2811-20260930.js')
    pp = yl_patch.Patcher(base)
    _g = apply(pp, {'zh': yl_patch.zh, 'base_text': base})
    gg = yl_patch.Gates(pp.text)
    for _t in _g:
        gg.check(*_t[:5])
    print(gg.report())
    print('self-check:', 'PASS' if gg.passed() else 'FAIL')
