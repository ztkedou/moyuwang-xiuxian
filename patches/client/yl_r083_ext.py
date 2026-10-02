# -*- coding: utf-8 -*-
r"""
yl_r083_ext.py — 0.9.3 客户端小修（R-083 云端刷新弹窗 + 仓库链接指向本仓库）

本模块只做**两处原地替换**，不注入任何 helper（INJECT_JS 有意留空 ⇒ build 侧
`zh('')` 合法、不插入，dryrun 会打一条 `无 INJECT_JS` 的 WARN，属预期非失败）。

=========================================================================== ① R-083 云端数据刷新弹窗反复弹
--------------------------------------------------------------------------
用户报障（2026-10-01）：「页面经常弹出这个，好像是我浏览器切换到别的页面，
过一会再切回来就会弹出。」截图 = 一个**阻塞式弹窗**：
    提示 / 检测到云端数据已更新，已为你实时刷新角色数据。 / [确定]

基线代码（`jS()` 组件里的轮询，实测 count==1）：
    const yS=6e3, vS=30*1e3; let qg=0;                       ← 轮询 6s / 提示节流 30s
    const c=setInterval(async()=>{ ... 
      if(d.gm_revision>Math.max(a.current,Be.getState().appliedGmRevision)){
        if(YLSync.isBusy())return;
        const u=await Pn.fetchSave(); if(!u)return;
        Be.getState().applyRemoteSave(u,d.gm_revision), a.current=d.gm_revision;
        const v=Date.now();
        v-qg>=vS&&(qg=v,Ui("检测到云端数据已更新，已为你实时刷新角色数据。"))   ← 本模块改这里
      } ... }, yS);

根因（为什么「切走再切回」必弹）：
  · 轮询 6s 一次，但**后台标签页的定时器被浏览器节流**（约 1 次/分钟）⇒ 切回前台时
    那个被压住的定时器**立刻补跑一次**，于是「切回来就弹」。
  · 判据是 `服务端 gm_revision > 本地记录`。而**本机自己的自动存档也会把服务端
    revision 顶上去**（`yl-xw-dirty` → `YLSync.push` → 服务端刷新 revision），
    本地那两个记录点（`a.current` / `appliedGmRevision`）在 push 路径上并不一定同步
    ⇒ 轮询把**自己的存档**误判成「别处改的」，于是刷新 + 弹窗。
  · 结果：这条提示在本机单开的情况下也会周期性出现，且是**阻塞式弹窗**（要点确定），
    对挂机游戏是纯打扰。

修法（最小、只动「打扰」不动「同步」）：
  · **保留**静默刷新逻辑（`applyRemoteSave` 一字不动 —— 跨设备同步仍然生效）；
  · **去掉** `Ui(...)` 那个阻塞式弹窗，换一行 `console.info` 留痕（纯 ASCII，便于排查）。
  · 节流记账 `v-qg>=vS&&(qg=v)` 一并去掉（去掉 UI 后它没有意义）。
  ⚠ 没有改 `yS`/`vS` 常量、没有改 `Math.max(a.current,...)` 判据、没有动 `YLSync`。
    若以后想「只在真的跨设备变更时才提示」，正确做法是让 push 路径把服务端返回的
    revision 回写进 `appliedGmRevision`（属服务端/存档链改动，不在本模块范围）。

=========================================================================== ② 游戏内 GitHub 链接指向本仓库
--------------------------------------------------------------------------
基线里有 **2 处** `<a href="https://github.com/JeasonLoop/react-xiuxian-game">`：
    ① 版本信息面板的「前往仓库」按钮（大按钮，`rounded-lg px-4 py-3`）
    ② 设置页「关于」区块的 GitHub 按钮（`rounded px-4 py-2`）
它们指向**上游仓库**。本仓库是这个游戏的改版发布仓库，玩家点「前往仓库」应当到本仓库。

修法：把 `href:` 的值整体换成 `https://github.com/ztkedou/moyuwang-xiuxian`（expect=2 一次替换两处）。

⚠ 注意：基线里还有第三处 `JeasonLoop/react-xiuxian-game`，是**上游 release 检查的 API 地址**
   `Fw="https://api.github.com/repos/.../releases/latest"` —— 那处**不归本模块管**，
   它早在 0.8.1 就被 `yl_version_ext.py` 摘掉外联了（见该模块 #3b），本模块**不得**碰它。
   本模块的锚点写成 `href:"..."` 形态，天然只命中那 2 个 <a>，不会碰到 `Fw=` 那处。

锚点纪律：两处锚点实测 count 见 PATCHES 的 expect；GATES 里同时断言新形态存在与旧形态清零。
"""

# 两处均为原地替换，无需注入任何 helper（build 侧 zh('') 合法且不插入）。
INJECT_JS = ''

# --------------------------------------------------------------------------- 锚点

# ① 仓库链接（基线 count == 2：版本面板 + 设置页关于）
GH_OLD = 'href:"https://github.com/JeasonLoop/react-xiuxian-game"'
GH_NEW = 'href:"https://github.com/ztkedou/moyuwang-xiuxian"'

# ② R-083 云端刷新弹窗（基线 count == 1）
CLOUD_OLD = 'v-qg>=vS&&(qg=v,Ui("检测到云端数据已更新，已为你实时刷新角色数据。"))'
CLOUD_NEW = 'console.info("[YL] cloud save applied silently (R-083: no more blocking dialog)")'


def apply(p, ctx):
    p.replace('r083-gh-link', GH_OLD, GH_NEW, expect=2,
              note='游戏内 2 处 GitHub 按钮改指本仓库 ztkedou/moyuwang-xiuxian（不碰 Fw= 的 API 地址）')
    p.replace('r083-cloud-toast', CLOUD_OLD, CLOUD_NEW, expect=1,
              note='R-083：去掉「检测到云端数据已更新」阻塞式弹窗，保留静默刷新')

    return [
        # ---- ② 链接：新形态存在 / 旧形态清零 ----
        ('R083·本仓库链接 x2',      GH_NEW, 2, '==', '2 处 <a href> 已改指本仓库'),
        ('R083·上游链接清零',        GH_OLD, 0, '==', '旧 href 形态必须为 0'),
        # ---- ② 冻结：上游 release API 地址不得被本模块「复活」----
        #   注：基线里那处 `Fw="https://api.github.com/repos/.../releases/latest"` 早在 0.8.1
        #   就被 yl_version_ext 摘掉外联了 ⇒ 在**终稿**里应为 0。本模块的 href 锚点也天然碰不到它。
        ('冻结·上游 release API 仍为 0',
         'https://api.github.com/repos/JeasonLoop/react-xiuxian-game/releases/latest', 0, '==',
         '终稿里应为 0（version 模块已摘外联）；若变 1 说明有人把它放回来了'),
        # ---- ① R-083 ----
        ('R083·弹窗表达式清零',      CLOUD_OLD, 0, '==', '旧阻塞弹窗形态必须为 0'),
        ('R083·静默留痕已写入',      'cloud save applied silently', 1, '==', 'console.info 留痕'),
        # ---- ① 冻结：同步逻辑与常量不得被误改 ----
        ('冻结·applyRemoteSave 仍在', 'applyRemoteSave(u,d.gm_revision)', 1, '==', '静默刷新逻辑保留'),
        ('冻结·轮询常量未动',        'const yS=6e3,vS=30*1e3;', 1, '==', '轮询 6s / 节流 30s 设计值未动'),
        ('冻结·revision 判据未动',   'd.gm_revision>Math.max(a.current,Be.getState().appliedGmRevision)', 1, '==', ''),
    ]
