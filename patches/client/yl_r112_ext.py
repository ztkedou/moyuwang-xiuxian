# -*- coding: utf-8 -*-
r"""
yl_r112_ext.py（墓碑）— R-112 打坐/历练产出灵玉：客户端半边【已废弃，禁止接线】

2026-10-02 主控口径改判
--------------------------------------------------------------------------
R-112 唯一实现 = 服务端环 patches/server/srv_patch_r112.py：
  POST /api/save 的 UPDATE 分支按 Δmeditate/Δadventure（本次存档 vs 上次存档）
  roll 掉落（打坐 0.4%/跳 < 历练 0.9%/次，命中 1 玉），经 actDropTokens 发放
  （日上限 300 / activity_token_daily 钳制 / 活跃 token_shop 场次门槛全复用）。

为什么客户端半边必须为零
--------------------------------------------------------------------------
灵玉真值在服务端 activity_token；打坐/历练是客户端权威结算、无独立服务端端点。
本文件原方案（2026-10-02 00:42 版，已备份 yl_r112_ext.py.bak-client-20261002）
在客户端打坐/历练结算口写 player.jadeBalance —— 该字段会被存档采纳器覆盖
（资损风险），且不进灵玉阁余额/日上限，属半成品死路，已按主控指令废弃。
客户端对 R-112 的正确姿势 = 零改动：灵玉余额经既有 /api/activity/shop 的
jadeBalance 字段下发（v2810 改名后的安全口径），灵玉阁面板照常显示。

接线拦截
--------------------------------------------------------------------------
任何装配层（build_v26n V28_MODULES / STANDALONE_CLIENT）引用本模块都会在
apply() 处直接 AssertionError 拒绝——防止历史半成品被误接回客户端。
"""

DEPRECATED = "R-112 已改走服务端环 patches/server/srv_patch_r112.py（2026-10-02）"


def apply(p, ctx):  # pragma: no cover — 墓碑：任何接线尝试必须响亮失败
    raise AssertionError(
        "yl_r112_ext.py 已废弃（客户端写 jadeBalance=资损风险）。"
        "R-112 唯一实现 = patches/server/srv_patch_r112.py（SRV_CHAIN 环）。"
        "如误把本模块接进 build_v26n/STANDALONE_CLIENT，请移除该接线。"
    )
