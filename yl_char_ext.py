# -*- coding: utf-8 -*-
"""
yl_char_ext.py — v28 客户端注入块：人物志 · 道友图鉴（缘契）

需求来源：#7「人物志的玩法需要一个游戏策划师来重新策划」
完整策划案：`人物志重策划案.md`

设计要点
  1. **不新增页签 / 不新增抽屉入口 / 不动 YLXW_TABS / YLXW_COMP / YLXW_ICONS**，
     只在既有「人物志」模态框（bundle 内组件 Nk，@1331247）内部插两块 UI：
       - 模态框 children 数组首位 → YlxwCharDexPanel（图鉴 + 收集奖励 + 寻访）
       - 右侧详情「结识于：」之后 → YlxwCharBondPanel（缘契里程碑 + 小传/秘辛）
  2. 数据全部落在 player 内（socialRelations 原结构不动 + 新增 player.charDex），
     随既有 /api/save 整包落库 → **服务端零改动**。
  3. 永久收益接在既有修炼速度公式的 S 变量上（追加一行，不改任何既有常量）。
  4. 前 8 位图鉴条目沿用既有 npc-random-1..8 的 id 与名字 → 老档自动点亮。

导出符号（构建侧契约）
  INJECT_JS : str   注入 JS 代码块（可含中文，落盘前由 build 侧 zh() 统一转义）
  apply(p, ctx)     p = yl_patch.Patcher；ctx = {'zh': zh, 'base_text': str}
                    返回 gates: list[(name, needle, expected, op, note)]

锚点实测（基线 build/assets/index-v26m-20260927.js，count 全部 == 1）
  EXT_ANCHOR   'function YlxwMeta(k) {'
  EXP_HOOK     'let b=fy(m).expRate||0,S=0;'
  EMPTY_TEXT   'children:"尚未结识任何道友，多在历练中闯荡吧。"'
  MODAL_OPEN   'title:"人物志",titleIcon:e.jsx(um,{size:18}),size:"lg",height:"lg",children:e.jsxs("div",{className:"space-y-4",children:['
  DETAIL_ENC   'children:["结识于：",j.lastEncounterRealm]}),'
"""

import re

# ---------------------------------------------------------------- 注入代码
# 这里可以放心写中文，apply() 里统一走 ctx['zh'] 转义。

INJECT_JS = r'''
/* ===== yl-v28 人物志 · 道友图鉴（缘契）策划落地 ===== */

/* ---- 24 位道友图鉴表：前 8 位沿用既有 npc-random-1..8（老档自动点亮） ---- */
var YLXW_CHAR_DEX = [
  { id: "npc-random-1", name: "云游道人", rarity: "凡缘", title: "四海为家",
    hint: "历练途中偶遇", desc: "山道上擦肩而过的云游道人",
    bio: "他背一只旧葫芦，说要走遍九州寻一味能解乡愁的酒。",
    secret: "他原是三百年前失踪的青云宗长老，因误服丹药失了记忆。" },
  { id: "npc-random-2", name: "采药修士", rarity: "凡缘", title: "药庐常客",
    hint: "采药途中偶遇", desc: "在灵田边弯腰采药的修士",
    bio: "他认得山中每一株草，却记不清自己师承何处。",
    secret: "他的药篓夹层里，藏着一页残缺的《百草纲》。" },
  { id: "npc-random-3", name: "散修剑客", rarity: "仙缘", title: "一剑无门",
    hint: "历练途中偶遇", desc: "在酒肆里独饮的散修剑客",
    bio: "他没有门派，剑上刻着十九道缺口，每一道都是一场败仗。",
    secret: "他其实是剑冢的守墓人，剑冢一开，天下剑修皆来朝。" },
  { id: "npc-random-4", name: "隐世前辈", rarity: "天缘", title: "不问世事",
    hint: "顿悟或秘境中感应", desc: "在顿悟中感应到的一缕灵识",
    bio: "他说话极慢，一句要等半炷香，但每句都值得等。",
    secret: "他早已坐化，留在此地的只是一缕不肯散的道念。" },
  { id: "npc-random-5", name: "同门师兄", rarity: "凡缘", title: "引路之人",
    hint: "宗门日常偶遇", desc: "在山门石阶上遇见的同门师兄",
    bio: "他总在你最需要的时候递来一壶温水。",
    secret: "他偷偷替你挡下了三次宗门责罚。" },
  { id: "npc-random-6", name: "路见不平客", rarity: "仙缘", title: "侠骨不冷",
    hint: "危难相助后结识", desc: "曾在危难中得到你的帮助",
    bio: "他出手从不问对方是谁，只问谁在欺负人。",
    secret: "他右臂有一道雷纹，那是替人受天劫留下的。" },
  { id: "npc-random-7", name: "摆摊老者", rarity: "凡缘", title: "识货之人",
    hint: "坊市闲逛偶遇", desc: "在坊市角落摆摊的老者",
    bio: "他的摊上什么都有，又什么都像假的。",
    secret: "他收过的每一件废品，最后都被证明是宝物。" },
  { id: "npc-random-8", name: "落魄书生", rarity: "凡缘", title: "纸上谈仙",
    hint: "坊市或客栈偶遇", desc: "在客栈角落抄书换酒的书生",
    bio: "他考了七次仙门未中，却能把丹方背得一字不差。",
    secret: "他写的那本《丹经辨伪》，被三家宗门列为禁书。" },
  { id: "npc-dex-9", name: "灵泉守护者", rarity: "仙缘", title: "一泓不涸",
    hint: "灵泉旁偶遇", desc: "在灵泉旁结识的道友",
    bio: "她守着一口灵泉，守了不知多少年。",
    secret: "那口灵泉，其实是她的眼泪化成的。" },
  { id: "npc-dex-10", name: "古修残魂", rarity: "天缘", title: "残卷余音",
    hint: "顿悟或古洞府中感应", desc: "在古洞府中惊动的一缕残魂",
    bio: "他只剩半句话没说完，说了三百年。",
    secret: "他等的那个传人，其实早就来过了。" },
  { id: "npc-dex-11", name: "道韵化身", rarity: "仙缘", title: "无形之师",
    hint: "顿悟时偶遇", desc: "在顿悟中化作人形的道韵",
    bio: "他从不回答你的问题，只把你的问题变成另一个问题。",
    secret: "他就是你每次突破时听到的那声轻叹。" },
  { id: "npc-dex-12", name: "灵识投影", rarity: "凡缘", title: "镜中之我",
    hint: "打坐或顿悟偶遇", desc: "在静坐中照见的一道灵识",
    bio: "他与你长得一模一样，只是笑得更自在些。",
    secret: "他记得你忘记的所有事。" },
  { id: "npc-dex-13", name: "丹霞仙子", rarity: "仙缘", title: "一炉春色",
    hint: "炼丹房或丹会偶遇", desc: "在丹会上与你论丹的仙子",
    bio: "她炼的丹总带一点花香，谁也学不来。",
    secret: "她其实是药王谷最后一位传人，谷中早已无人。" },
  { id: "npc-dex-14", name: "铁匠王老", rarity: "凡缘", title: "锤下有灵",
    hint: "炼器坊偶遇", desc: "在炼器坊抡锤的老匠人",
    bio: "他说兵器有脾气，得顺着它来。",
    secret: "他年轻时铸过一把剑，那把剑杀过一位仙人。" },
  { id: "npc-dex-15", name: "藏经阁主", rarity: "仙缘", title: "万卷皆空",
    hint: "宗门藏经阁偶遇", desc: "在藏经阁深处扫尘的老者",
    bio: "他不读书，只擦书，说擦干净了自然就记住了。",
    secret: "藏经阁最里面那排书架，从来没有书。" },
  { id: "npc-dex-16", name: "醉仙楼掌柜", rarity: "凡缘", title: "一醉三年",
    hint: "坊市酒楼偶遇", desc: "在醉仙楼拨算盘的掌柜",
    bio: "他的酒能让修士醉，也能让凡人醒。",
    secret: "他欠着一位仙人的酒钱，已经欠了九百年。" },
  { id: "npc-dex-17", name: "无名剑冢客", rarity: "天缘", title: "剑下无名",
    hint: "剑冢或秘境深处偶遇", desc: "在剑冢中与你对望的剑客",
    bio: "他从不报名，只说剑的名就够了。",
    secret: "他的剑名叫作「无名」，因为天下还没有配得上它的主人。" },
  { id: "npc-dex-18", name: "东海钓叟", rarity: "凡缘", title: "垂钓千年",
    hint: "东海或水边偶遇", desc: "在东海礁石上垂钓的老叟",
    bio: "他钓的不是鱼，是沉在海底的旧事。",
    secret: "他钓上过一柄剑，那柄剑至今还在他的鱼篓里。" },
  { id: "npc-dex-19", name: "太虚幻影", rarity: "天缘", title: "亦真亦幻",
    hint: "太虚秘境中偶遇", desc: "在太虚秘境中一闪而过的身影",
    bio: "你见过他三次，每次他都在做不同的事。",
    secret: "他不存在于任何一条时间线上，除了你记得他。" },
  { id: "npc-dex-20", name: "牧灵少女", rarity: "凡缘", title: "与兽同行",
    hint: "山野或灵兽出没处偶遇", desc: "在山野间牧养灵兽的少女",
    bio: "她能听懂灵兽的话，灵兽却听不懂她的话。",
    secret: "她其实是被灵兽养大的。" },
  { id: "npc-dex-21", name: "断魂崖猎户", rarity: "凡缘", title: "崖上求生",
    hint: "断魂崖或险地偶遇", desc: "在断魂崖打猎的猎户",
    bio: "他从不走回头路，说崖上的路只有一条。",
    secret: "崖底那堆白骨，是他给自己留的。" },
  { id: "npc-dex-22", name: "青云执事", rarity: "凡缘", title: "案牍劳形",
    hint: "宗门事务处偶遇", desc: "在宗门事务处核对名册的执事",
    bio: "他记得每一个弟子的名字，包括已经死了的。",
    secret: "名册最后一页写着他的名字，墨迹还没干。" },
  { id: "npc-dex-23", name: "幽篁琴姬", rarity: "仙缘", title: "一弦惊梦",
    hint: "竹林或宴席偶遇", desc: "在幽篁竹林中抚琴的女子",
    bio: "她的琴声能让修士入梦，也能让人醒不来。",
    secret: "她弹的每一首曲子，都是写给同一个人的。" },
  { id: "npc-dex-24", name: "天机阁算子", rarity: "仙缘", title: "推演天机",
    hint: "天机阁或卦摊偶遇", desc: "在天机阁推演命数的算子",
    bio: "他算得出别人的命，算不出自己的。",
    secret: "他算出过一场大劫，唯一的解法是「不要算」。" }
];

/* 稀有度：配色 / 寻访权重 / 图鉴永久修炼速度系数 */
var YLXW_CHAR_RAR = {
  "凡缘": { c: "text-stone-300", b: "border-stone-600", bg: "bg-stone-800", w: 60, rate: 0.003, total: 12 },
  "仙缘": { c: "text-cyan-300", b: "border-blue-800", bg: "bg-blue-900/20", w: 30, rate: 0.006, total: 8 },
  "天缘": { c: "text-amber-300", b: "border-amber-600", bg: "bg-amber-900/20", w: 10, rate: 0.012, total: 4 }
};

/* 缘契里程碑（对所有关系生效；数值均为新增，可被 T7 数值重规划调整） */
var YLXW_CHAR_BOND_MILE = [
  { at: 25, label: "相知", stones: 60, exp: 0 },
  { at: 50, label: "知己", stones: 0, exp: 120 },
  { at: 75, label: "莫逆", stones: 200, exp: 0 },
  { at: 100, label: "道侣", stones: 300, exp: 400 }
];

/* 图鉴收集奖励档位 */
var YLXW_CHAR_DEX_MILE = [
  { at: 3, label: "三友", stones: 300, exp: 0, item: null },
  { at: 6, label: "六合", stones: 0, exp: 500, item: null },
  { at: 9, label: "九曜", stones: 800, exp: 0, item: null },
  { at: 12, label: "十二楼", stones: 0, exp: 1200, item: { name: "同心结", rarity: "稀有", qty: 1 } },
  { at: 16, label: "十六尊", stones: 1500, exp: 0, item: null },
  { at: 20, label: "二十真", stones: 0, exp: 2000, item: { name: "同心结", rarity: "稀有", qty: 2 } },
  { at: 24, label: "廿四仙", stones: 3000, exp: 3000, item: { name: "道友图谱", rarity: "仙品", qty: 1 } }
];

var YLXW_CHAR_VISIT_COST = 200; /* × YLRF(player) */

/* ---------------- 纯函数层 ---------------- */

function YlxwCharEntry(id) {
  for (var i = 0; i < YLXW_CHAR_DEX.length; i++) { if (YLXW_CHAR_DEX[i].id === id) return YLXW_CHAR_DEX[i]; }
  return null;
}
function YlxwCharEntryByName(nm) {
  if (!nm) return null;
  for (var i = 0; i < YLXW_CHAR_DEX.length; i++) { if (YLXW_CHAR_DEX[i].name === nm) return YLXW_CHAR_DEX[i]; }
  return null;
}
function YlxwCharPS(p) {
  var d = (p && p.charDex) || {};
  return {
    met: d.met || {}, claimed: d.claimed || {}, bond: d.bond || {},
    freeDate: d.freeDate || "", visits: Number(d.visits) || 0
  };
}
/* 已识集合：charDex.met ∪ socialRelations（按 id 与 name 双匹配，兼容老档名字错位） */
function YlxwCharMet(p) {
  var ps = YlxwCharPS(p), rels = (p && p.socialRelations) || [], m = {}, i, k, e;
  for (k in ps.met) { if (Object.prototype.hasOwnProperty.call(ps.met, k)) m[k] = true; }
  for (i = 0; i < rels.length; i++) {
    if (!rels[i]) continue;
    if (rels[i].id) m[rels[i].id] = true;
    e = YlxwCharEntryByName(rels[i].name);
    if (e) m[e.id] = true;
  }
  return m;
}
function YlxwCharMetN(p) {
  var m = YlxwCharMet(p), n = 0, i;
  for (i = 0; i < YLXW_CHAR_DEX.length; i++) { if (m[YLXW_CHAR_DEX[i].id]) n++; }
  return n;
}
function YlxwCharRarStats(p) {
  var m = YlxwCharMet(p), s = { "凡缘": 0, "仙缘": 0, "天缘": 0 }, i, e;
  for (i = 0; i < YLXW_CHAR_DEX.length; i++) {
    e = YLXW_CHAR_DEX[i];
    if (m[e.id]) s[e.rarity] = (s[e.rarity] || 0) + 1;
  }
  return s;
}
function YlxwCharRf(p) { try { return YLRF(p); } catch (ylxwCrE1) { return 1; } }
/* 图鉴永久修炼速度加成（满图鉴 +15.2%） */
function YlxwCharDexRate(p) {
  var m = YlxwCharMet(p), r = 0, n = 0, i, e, rr;
  for (i = 0; i < YLXW_CHAR_DEX.length; i++) {
    e = YLXW_CHAR_DEX[i];
    if (!m[e.id]) continue;
    n++;
    rr = YLXW_CHAR_RAR[e.rarity] || {};
    r += rr.rate || 0;
  }
  if (n >= YLXW_CHAR_DEX.length) r += 0.02;
  return r;
}
function YlxwCharToday() {
  var d = new Date();
  return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
}
/* 寻访目标：未结识池按稀有度权重抽取；全结识则返回 null */
function YlxwCharRollTarget(p) {
  var m = YlxwCharMet(p), pool = [], i, e, w, total = 0, x;
  for (i = 0; i < YLXW_CHAR_DEX.length; i++) {
    e = YLXW_CHAR_DEX[i];
    if (m[e.id]) continue;
    w = (YLXW_CHAR_RAR[e.rarity] || {}).w || 1;
    pool.push([e, w]);
    total += w;
  }
  if (!pool.length) return null;
  x = Math.random() * total;
  for (i = 0; i < pool.length; i++) { x -= pool[i][1]; if (x <= 0) return pool[i][0]; }
  return pool[pool.length - 1][0];
}
function YlxwCharItem(name, rarity, qty) {
  return {
    id: "ylxw-char-" + (typeof St === "function" ? St() : (Date.now() + "-" + Math.floor(Math.random() * 1e9))),
    name: name, type: "Material", description: "道友图鉴纪念之物，可赠予道友以增缘契。",
    quantity: qty, rarity: rarity
  };
}
function YlxwCharPushItems(inv, items) {
  var out = (inv || []).slice(), i, j, it, hit;
  for (i = 0; i < items.length; i++) {
    it = items[i];
    if (!it) continue;
    hit = -1;
    for (j = 0; j < out.length; j++) {
      if (out[j] && out[j].name === it.name && out[j].type === "Material") { hit = j; break; }
    }
    if (hit < 0) out.push(YlxwCharItem(it.name, it.rarity, it.qty));
    else out[hit] = Object.assign({}, out[hit], { quantity: (Number(out[hit].quantity) || 0) + it.qty });
  }
  return out;
}
/* 结算助手：opt = {stones, exp, items, markMet:[id], setFree:bool, visit:bool} */
function YlxwCharApply(prev, opt) {
  if (!prev) return prev;
  var next = Object.assign({}, prev), d, met, i;
  if (opt.stones) next.spiritStones = Math.max(0, (Number(prev.spiritStones) || 0) + opt.stones);
  if (opt.exp) next.exp = Math.max(0, (Number(prev.exp) || 0) + opt.exp);
  if (opt.items && opt.items.length) next.inventory = YlxwCharPushItems(prev.inventory, opt.items);
  d = Object.assign({}, prev.charDex || {});
  met = Object.assign({}, d.met || {});
  if (opt.markMet) { for (i = 0; i < opt.markMet.length; i++) { if (opt.markMet[i]) met[opt.markMet[i]] = true; } }
  d.met = met;
  if (opt.setFree) d.freeDate = YlxwCharToday();
  if (opt.visit) d.visits = (Number(d.visits) || 0) + 1;
  next.charDex = d;
  return next;
}
/* 结识 / 重逢：upsert 关系到 socialRelations 并点亮图鉴 */
function YlxwCharMeet(prev, entry, gain, desc) {
  if (!prev || !entry) return prev;
  var rels = (prev.socialRelations || []).slice(), i, hit = -1, next, d, met;
  for (i = 0; i < rels.length; i++) { if (rels[i] && rels[i].id === entry.id) { hit = i; break; } }
  if (hit < 0) {
    rels.push({
      id: entry.id, name: entry.name,
      favorability: Math.max(-100, Math.min(100, gain)),
      description: desc || entry.desc, lastEncounterRealm: prev.realm
    });
  } else {
    rels[hit] = Object.assign({}, rels[hit], {
      favorability: Math.max(-100, Math.min(100, (Number(rels[hit].favorability) || 0) + gain)),
      lastEncounterRealm: prev.realm
    });
  }
  next = Object.assign({}, prev, { socialRelations: rels });
  d = Object.assign({}, next.charDex || {});
  met = Object.assign({}, d.met || {});
  met[entry.id] = true;
  d.met = met;
  next.charDex = d;
  return next;
}
function YlxwCharBondClaimed(p, relId, at) {
  var ps = YlxwCharPS(p), b = ps.bond[relId] || {};
  return !!b[String(at)];
}

/* ---------------- ① 图鉴面板（插在人物志模态框 children 首位） ---------------- */

/* 兜底错误边界：本区块任何渲染异常只隐藏自己，绝不炸掉整个面板 / 游戏
   （本作没有 app 级 ErrorBoundary，未捕获异常会卸载整棵树） */
class YlxwCharSafe extends O.Component {
  constructor(props) { super(props); this.state = { err: false }; }
  static getDerivedStateFromError() { return { err: true }; }
  componentDidCatch() {}
  render() { return this.state.err ? null : this.props.children; }
}

function YlxwCharDexPanel(props) {
  var p = props.player, setP = props.setPlayer, log = props.addLog || function () {};
  var s1 = O.useState(null), sel = s1[0], setSel = s1[1];
  var s2 = O.useState(""), notice = s2[0], setNotice = s2[1];
  var m = YlxwCharMet(p), n = YlxwCharMetN(p), rs = YlxwCharRarStats(p);
  var ps = YlxwCharPS(p), rf = YlxwCharRf(p);
  var cost = Math.round(YLXW_CHAR_VISIT_COST * rf);
  var freeOk = ps.freeDate !== YlxwCharToday();
  var stones = Number(p && p.spiritStones) || 0;
  var i, j, e2, k;

  function doVisit(useFree) {
    if (!p) return;
    if (!useFree && stones < cost) { setNotice("灵石不足，寻访需 " + cost + " 灵石。"); return; }
    var entry = YlxwCharRollTarget(p);
    var parts = [];
    if (!entry) {
      var cands = [];
      for (k = 0; k < YLXW_CHAR_DEX.length; k++) { if (m[YLXW_CHAR_DEX[k].id]) cands.push(YLXW_CHAR_DEX[k]); }
      if (!cands.length) { setNotice("暂无可寻访的道友。"); return; }
      entry = cands[Math.floor(Math.random() * cands.length)];
      var g0 = 4 + Math.floor(Math.random() * 6);
      setP(function (prev) {
        var nx = YlxwCharMeet(prev, entry, g0, "重逢于一次寻访");
        return YlxwCharApply(nx, { stones: useFree ? 0 : -cost, setFree: useFree, visit: true });
      });
      log("【寻访】你与【" + entry.name + "】重逢，缘契 +" + g0 + "。", "gain");
      setNotice("重逢【" + entry.name + "】，缘契 +" + g0 + (useFree ? "。" : "（-" + cost + " 灵石）"));
      setSel(entry.id);
      return;
    }
    var gain = 15 + Math.floor(Math.random() * 11);
    setP(function (prev) {
      var nx = YlxwCharMeet(prev, entry, gain, entry.desc);
      return YlxwCharApply(nx, { stones: useFree ? 0 : -cost, setFree: useFree, visit: true });
    });
    log("【寻访】你结识了【" + entry.name + "】（" + entry.rarity + "），缘契 +" + gain + "。", "gain");
    setNotice("结识【" + entry.name + "】（" + entry.rarity + "），缘契 +" + gain + (useFree ? "。" : "（-" + cost + " 灵石）"));
    setSel(entry.id);
  }

  function doClaim(mile) {
    if (!p) return;
    if (YlxwCharPS(p).claimed[String(mile.at)]) return;
    if (n < mile.at) return;
    var st = Math.round((mile.stones || 0) * rf), ex = Math.round((mile.exp || 0) * rf);
    var items = mile.item ? [mile.item] : [];
    setP(function (prev) {
      var next = YlxwCharApply(prev, { stones: st, exp: ex, items: items });
      var d = Object.assign({}, next.charDex || {});
      var c = Object.assign({}, d.claimed || {});
      c[String(mile.at)] = true;
      d.claimed = c;
      next.charDex = d;
      return next;
    });
    parts = [];
    if (st) parts.push("灵石 +" + st);
    if (ex) parts.push("修为 +" + ex);
    if (mile.item) parts.push(mile.item.name + " x" + mile.item.qty);
    log("【人物志·" + mile.label + "】收集奖励：" + parts.join("、") + "。", "gain");
    setNotice("已领取【" + mile.label + "】：" + parts.join("、"));
  }

  /* 收集奖励 chip */
  var chips = [];
  for (i = 0; i < YLXW_CHAR_DEX_MILE.length; i++) {
    (function (mile) {
      var done = !!ps.claimed[String(mile.at)];
      var can = n >= mile.at;
      chips.push(e.jsx("button", {
        disabled: done || !can,
        onClick: function () { doClaim(mile); },
        className: "px-2 py-1 rounded border text-[10px] transition-colors " + (
          done ? "bg-emerald-900/20 border-emerald-700/50 text-emerald-300" :
          can ? "bg-amber-600 hover:bg-amber-500 border-amber-500 text-stone-900 font-bold" :
                "bg-stone-800 border-stone-700 text-stone-500"),
        title: done ? "已领取" : (can ? "点击领取" : ("需结识 " + mile.at + " 位道友")),
        children: (done ? "✓ " : "") + mile.label + " " + (done ? "" : (can ? "可领" : n + "/" + mile.at))
      }, "ylxw-charmile-" + mile.at));
    })(YLXW_CHAR_DEX_MILE[i]);
  }

  /* 图鉴网格 */
  var cells = [];
  for (i = 0; i < YLXW_CHAR_DEX.length; i++) {
    (function (en) {
      var got = !!m[en.id];
      var rar = YLXW_CHAR_RAR[en.rarity] || {};
      cells.push(e.jsx("button", {
        onClick: function () { setSel(en.id); },
        className: "rounded border px-1 py-1.5 text-[10px] leading-tight text-center transition-colors " + (
          sel === en.id ? "bg-mystic-gold/20 border-mystic-gold text-amber-100" :
          got ? (rar.bg || "bg-stone-800") + " " + (rar.b || "border-stone-600") + " " + (rar.c || "text-stone-200") :
                "bg-stone-900/60 border-stone-800 text-stone-600"),
        title: got ? (en.name + " · " + en.rarity + " · " + en.title) : ("未结识（" + en.hint + "）"),
        children: e.jsx("span", { children: got ? en.name : "？？" })
      }, "ylxw-charcodex-" + en.id));
    })(YLXW_CHAR_DEX[i]);
  }

  /* 选中详情 */
  var selEntry = sel ? YlxwCharEntry(sel) : null;
  var selRel = null, rels = (p && p.socialRelations) || [];
  if (selEntry) {
    for (j = 0; j < rels.length; j++) { if (rels[j] && rels[j].id === selEntry.id) { selRel = rels[j]; break; } }
  }
  var bond = selRel ? (Number(selRel.favorability) || 0) : 0;
  var rarSel = selEntry ? (YLXW_CHAR_RAR[selEntry.rarity] || {}) : {};
  var selBlock = selEntry ? e.jsxs("div", { className: "bg-ink-900 border border-stone-700 rounded p-2.5 space-y-1", children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsxs("span", { className: "font-serif text-amber-200", children: [
        selEntry.name,
        e.jsx("span", { className: "text-[10px] ml-2 " + (rarSel.c || "text-stone-400"), children: selEntry.rarity + " · " + selEntry.title })
      ] }),
      e.jsx("span", { className: "text-[10px] text-stone-400", children: selRel ? ("缘契 " + bond + " / 100") : "未结识" })
    ] }),
    selRel
      ? e.jsx("p", { className: "text-[11px] text-stone-300", children: selEntry.desc })
      : e.jsx("p", { className: "text-[11px] text-stone-500", children: "邂逅线索：" + selEntry.hint + "（或使用上方【寻访】主动结识）" }),
    e.jsxs("p", { className: "text-[11px] " + (bond >= 50 ? "text-blue-200" : "text-stone-600"), children: [
      e.jsx("span", { className: "text-cyan-400 font-bold", children: "【小传】" }),
      bond >= 50 ? selEntry.bio : "缘契达 50 解锁"
    ] }),
    e.jsxs("p", { className: "text-[11px] " + (bond >= 100 ? "text-amber-200" : "text-stone-600"), children: [
      e.jsx("span", { className: "text-amber-400 font-bold", children: "【秘辛】" }),
      bond >= 100 ? selEntry.secret : "缘契达 100 解锁"
    ] })
  ] }) : null;

  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, {
      extra: e.jsx("span", { className: "text-[10px] text-stone-400", children: "邂逅越多，修炼越快" }),
      children: "道友图鉴 · 缘契"
    }),
    e.jsxs("div", { children: [
      e.jsxs("div", { className: "flex justify-between text-[11px] text-stone-400 mb-1", children: [
        e.jsx("span", { children: "图鉴收集" }),
        e.jsxs("span", { children: [ n + " / " + YLXW_CHAR_DEX.length, e.jsx("span", { className: "text-emerald-300", children: "　修炼速度 +" + (YlxwCharDexRate(p) * 100).toFixed(1) + "%" }) ] })
      ] }),
      e.jsx("div", { className: "w-full bg-stone-800 rounded-full h-2 overflow-hidden", children: e.jsx("div", {
        className: "h-2 bg-gradient-to-r from-amber-600 to-amber-400 transition-all",
        style: { width: Math.round(n / YLXW_CHAR_DEX.length * 100) + "%" }
      }) })
    ] }),
    e.jsx("div", { className: "grid grid-cols-3 gap-1.5", children: [
      e.jsxs("div", { className: "bg-ink-800/60 border border-stone-700 rounded px-2 py-1 text-[11px] text-center", children: [
        e.jsx("span", { className: "text-stone-300", children: "凡缘 " }), rs["凡缘"] + "/" + YLXW_CHAR_RAR["凡缘"].total
      ] }),
      e.jsxs("div", { className: "bg-ink-800/60 border border-blue-800 rounded px-2 py-1 text-[11px] text-center", children: [
        e.jsx("span", { className: "text-cyan-300", children: "仙缘 " }), rs["仙缘"] + "/" + YLXW_CHAR_RAR["仙缘"].total
      ] }),
      e.jsxs("div", { className: "bg-ink-800/60 border border-amber-700 rounded px-2 py-1 text-[11px] text-center", children: [
        e.jsx("span", { className: "text-amber-300", children: "天缘 " }), rs["天缘"] + "/" + YLXW_CHAR_RAR["天缘"].total
      ] })
    ] }),
    e.jsx("div", { className: "text-[10px] text-stone-500", children: "收集奖励（每档仅可领一次）" }),
    e.jsx("div", { className: "flex flex-wrap gap-1.5", children: chips }),
    e.jsxs("div", { className: "flex items-center gap-2 flex-wrap pt-1", children: [
      e.jsx(YlxwBtn, { disabled: !freeOk, onClick: function () { doVisit(true); }, children: freeOk ? "寻访 · 今日免费" : "今日已寻访" }),
      e.jsx(YlxwBtn, { tone: "ghost", disabled: stones < cost, onClick: function () { doVisit(false); }, children: "灵石寻访 " + cost }),
      e.jsx("span", { className: "text-[10px] text-stone-500", children: "已寻访 " + ps.visits + " 次" })
    ] }),
    notice ? e.jsx("div", { className: "text-[11px] text-emerald-300", children: notice }) : null,
    e.jsx("div", { className: "text-[10px] text-stone-500", children: "图鉴（点击格子查看详情 / 小传 / 秘辛）" }),
    e.jsx("div", { className: "grid grid-cols-4 md:grid-cols-5 gap-1.5", children: cells }),
    selBlock
  ] });
}

/* ---------------- ② 缘契里程碑（插在关系详情「结识于：」之后） ---------------- */

function YlxwCharBondPanel(props) {
  var rel = props.rel, p = props.player, setP = props.setPlayer, log = props.addLog || function () {};
  var s1 = O.useState(""), notice = s1[0], setNotice = s1[1];
  if (!rel) return null;
  var bond = Number(rel.favorability) || 0;
  var rf = YlxwCharRf(p);
  var ps = YlxwCharPS(p);
  var claimed = ps.bond[rel.id] || {};
  var entry = YlxwCharEntry(rel.id) || YlxwCharEntryByName(rel.name);
  var i;

  function claim(mile) {
    if (bond < mile.at || claimed[String(mile.at)]) return;
    var st = Math.round((mile.stones || 0) * rf), ex = Math.round((mile.exp || 0) * rf);
    setP(function (prev) {
      var next = YlxwCharApply(prev, { stones: st, exp: ex });
      var d = Object.assign({}, next.charDex || {});
      var b = Object.assign({}, d.bond || {});
      var mine = Object.assign({}, b[rel.id] || {});
      mine[String(mile.at)] = true;
      b[rel.id] = mine;
      d.bond = b;
      next.charDex = d;
      return next;
    });
    var parts = [];
    if (st) parts.push("灵石 +" + st);
    if (ex) parts.push("修为 +" + ex);
    log("【人物志】" + rel.name + " 缘契达 " + mile.at + "（" + mile.label + "）：" + parts.join("、") + "。", "gain");
    setNotice("已领取【" + mile.label + "】：" + parts.join("、"));
  }

  var chips = [];
  for (i = 0; i < YLXW_CHAR_BOND_MILE.length; i++) {
    (function (mile) {
      var done = !!claimed[String(mile.at)];
      var can = bond >= mile.at;
      chips.push(e.jsx("button", {
        disabled: done || !can,
        onClick: function () { claim(mile); },
        className: "px-2 py-1 rounded border text-[10px] transition-colors " + (
          done ? "bg-emerald-900/20 border-emerald-700/50 text-emerald-300" :
          can ? "bg-amber-600 hover:bg-amber-500 border-amber-500 text-stone-900 font-bold" :
                "bg-stone-800 border-stone-700 text-stone-500"),
        title: done ? "已领取" : (can ? "点击领取" : ("缘契达 " + mile.at + " 可领")),
        children: (done ? "✓ " : "") + mile.label + " " + mile.at
      }, "ylxw-charbond-" + rel.id + "-" + mile.at));
    })(YLXW_CHAR_BOND_MILE[i]);
  }

  return e.jsxs("div", { className: "space-y-2 pt-2 border-t border-stone-700", children: [
    e.jsx("div", { className: "text-[11px] text-stone-400 font-bold", children: "缘契里程碑（点击领取）" }),
    e.jsx("div", { className: "flex flex-wrap gap-1.5", children: chips }),
    notice ? e.jsx("div", { className: "text-[11px] text-emerald-300", children: notice }) : null,
    entry ? e.jsxs("div", { className: "space-y-1", children: [
      e.jsxs("p", { className: "text-[11px] " + (bond >= 50 ? "text-blue-200" : "text-stone-600"), children: [
        e.jsx("span", { className: "text-cyan-400 font-bold", children: "【小传】" }),
        bond >= 50 ? entry.bio : "缘契达 50 解锁"
      ] }),
      e.jsxs("p", { className: "text-[11px] " + (bond >= 100 ? "text-amber-200" : "text-stone-600"), children: [
        e.jsx("span", { className: "text-amber-400 font-bold", children: "【秘辛】" }),
        bond >= 100 ? entry.secret : "缘契达 100 解锁"
      ] })
    ] }) : e.jsx("p", { className: "text-[11px] text-stone-600", children: "（无名道友，暂未录入图鉴；缘契里程碑仍可领取）" })
  ] });
}

/* == end yl-v28 人物志·道友图鉴 == */
'''

# ---------------------------------------------------------------- 锚点

A_EXT_BLOCK = 'function YlxwMeta(k) {'
A_EXP_HOOK = 'let b=fy(m).expRate||0,S=0;'
A_EMPTY_TEXT = 'children:"\u5c1a\u672a\u7ed3\u8bc6\u4efb\u4f55\u9053\u53cb\uff0c\u591a\u5728\u5386\u7ec3\u4e2d\u95ef\u8361\u5427\u3002"'
A_MODAL_OPEN = ('title:"\u4eba\u7269\u5fd7",titleIcon:e.jsx(um,{size:18}),size:"lg",height:"lg",'
                'children:e.jsxs("div",{className:"space-y-4",children:[')
A_DETAIL_ENC = 'children:["\u7ed3\u8bc6\u4e8e\uff1a",j.lastEncounterRealm]}),'

R_EMPTY_TEXT = ('children:"\u5c1a\u672a\u7ed3\u8bc6\u4efb\u4f55\u9053\u53cb\u3002'
                '\u70b9\u51fb\u4e0b\u65b9\u3010\u5bfb\u8bbf\u3011\u4e3b\u52a8\u7ed3\u8bc6\uff0c'
                '\u6216\u591a\u5728\u5386\u7ec3\u4e2d\u95ef\u8361\u5076\u9047\u3002"')

DEX_MOUNT = ('e.jsx(YlxwCharSafe,{children:e.jsx(YlxwCharDexPanel,'
             '{player:a,setPlayer:l,addLog:c})}),')
BOND_MOUNT = ('e.jsx(YlxwCharSafe,{children:e.jsx(YlxwCharBondPanel,'
              '{rel:j,player:a,setPlayer:l,addLog:c})},j.id),')
# 人物志加成挂在主界面「修炼效率」算式里，而这个算式在**主渲染路径**上、
# 不在 YlxwCharSafe 边界内（那个边界只包了人物志面板子树）。本作没有 app 级
# ErrorBoundary，所以这里一旦抛错就会卸载整棵树 → 整站白屏。
# 与库内同类钩子（YLSettledExp / YLRealmOk）保持一致：抛错即降级为 0 加成，绝不让它炸掉游戏。
EXP_ADD = 'try{S+=(typeof YlxwCharDexRate==="function"?YlxwCharDexRate(t):0);}catch(ylCde){}'

# ---------------------------------------------------------------- 注入块门禁

BAN_PATTERNS = ['fetch(', 'localStorage', 'sessionStorage', 'auth_token',
                '/yl/api', 'iframe', 'postMessage', 'X-YL-', 'XMLHttpRequest',
                'Be.getState().setPlayer']


def _assert_block_clean(block):
    """注入块硬断言：zh() 之后必须纯 ASCII，且不含禁用模式。"""
    bad = re.findall(r'[^\x00-\x7f]', block)
    if bad:
        raise ValueError('yl_char_ext: 注入块 zh() 后仍含非 ASCII: %r' % (bad[:10],))
    for pat in BAN_PATTERNS:
        if pat in block:
            raise ValueError('yl_char_ext: 注入块含禁用模式 %r' % pat)


# ---------------------------------------------------------------- 应用

def apply(p, ctx):
    """把人物志重策划落到 Patcher 上；返回 gates 列表。"""
    zh = ctx['zh']
    block = zh(INJECT_JS)
    _assert_block_clean(block)

    # 1) 主注入块：放在 YlxwMeta 之前（YlxwPanel/YlxwBtn/… 均为函数声明，作用域内可见；
    #    本块不引用任何模块级 var，故与 build_v26n 的 core-block 先后顺序无关）
    p.insert_before(
        'char-ext-block', A_EXT_BLOCK, block + '\n',
        note='v28 人物志·道友图鉴：24 位道友 / 缘契里程碑 / 收集奖励 / 寻访 / 小传秘辛'
    )

    # 2) 修炼速度公式追加图鉴收集加成（只追加一行，不改既有常量）
    p.replace(
        'char-exp-rate-hook', A_EXP_HOOK, A_EXP_HOOK + EXP_ADD,
        note='图鉴收集度 → 修炼速度永久加成（接在既有 S 变量之后）'
    )

    # 3) 空态文案：从「一行灰字死局」改为带出口的引导
    p.replace(
        'char-empty-text', A_EMPTY_TEXT, R_EMPTY_TEXT,
        note='人物志空态引导（指向寻访）'
    )

    # 4) 模态框 children 首位插入图鉴面板
    p.replace(
        'char-dex-mount', A_MODAL_OPEN, A_MODAL_OPEN + DEX_MOUNT,
        note='人物志模态框顶部挂载 道友图鉴·缘契 面板'
    )

    # 5) 关系详情「结识于：」之后插入缘契里程碑 + 小传/秘辛
    p.replace(
        'char-bond-mount', A_DETAIL_ENC, A_DETAIL_ENC + BOND_MOUNT,
        note='关系详情挂载 缘契里程碑 / 小传 / 秘辛'
    )

    gates = [
        # ---- 注入块本体 ----
        ('图鉴面板定义',            'function YlxwCharDexPanel(', 1, '==', ''),
        ('缘契面板定义',            'function YlxwCharBondPanel(', 1, '==', ''),
        ('兜底错误边界定义',         'class YlxwCharSafe extends O.Component', 1, '==', ''),
        ('图鉴加成函数定义',        'function YlxwCharDexRate(', 1, '==', ''),
        ('寻访抽签函数定义',        'function YlxwCharRollTarget(', 1, '==', ''),
        ('结识 upsert 函数定义',    'function YlxwCharMeet(', 1, '==', ''),
        ('结算助手定义',            'function YlxwCharApply(', 1, '==', ''),
        ('已识集合定义',            'function YlxwCharMet(', 1, '==', ''),
        ('图鉴表 24 位',            '"npc-dex-24"', 1, '==', ''),
        ('图鉴表首位沿用老 id',      '"npc-random-1"', 1, '==', ''),
        ('图鉴表条目数',            'id: "npc-', 24, '==', '基线 0 命中，全部来自本模块'),
        ('稀有度表',                'var YLXW_CHAR_RAR = {', 1, '==', ''),
        ('缘契里程碑表',            'var YLXW_CHAR_BOND_MILE = [', 1, '==', ''),
        ('收集奖励表',              'var YLXW_CHAR_DEX_MILE = [', 1, '==', ''),
        ('寻访单价常量',            'var YLXW_CHAR_VISIT_COST = 200;', 1, '==', ''),
        ('注入块结束标记',          '/* == end yl-v28 ', 1, '==', ''),
        # ---- 挂载点 ----
        # ★ 0.8.7 T6（yl_t6chardex_ext.py）合法改写了下列 5 条门禁的字面锚：
        #   · 图鉴/缘契面板挂载改名 YlxwCharDexPanelT6 / YlxwCharBondPanelT6，并包进内容区左列
        #   · Nk 内容区改 grid 两列 ⇒ 图鉴不再落在 children 首位
        #   · 缘契挂载改名 ⇒ 不再紧跟「结识于」之后
        #   · 空态引导文案追加「多读需求、多交付，缘契上得快。」
        #   ⇒ 本模块 5 条退为「旧字面形态 == 0」，最终形态断言归 T6 模块
        #     （T6·左列开包 / T6·两列布局 / T6·旧空态文案已清零）。
        #   T6 侧登记表：yl_t6chardex_ext.py 文首「门禁计数变更清单」+ OLD_GATES_NEW_EXPECT。
        ('图鉴面板挂载（旧字面已清零）', DEX_MOUNT, 0, '==', '0.8.7 T6 改名 YlxwCharDexPanelT6'),
        ('缘契面板挂载（旧字面已清零）', BOND_MOUNT, 0, '==', '0.8.7 T6 改名 YlxwCharBondPanelT6'),
        ('图鉴落在 children 首位（旧形态已清零）', A_MODAL_OPEN + DEX_MOUNT, 0, '==', '0.8.7 T6 内容区改 grid 两列'),
        ('缘契落在结识于之后（旧形态已清零）', A_DETAIL_ENC + BOND_MOUNT, 0, '==', '0.8.7 T6 挂载改名'),
        # 改名而非删除：两处 YlxwCharSafe 挂载仍在（T6 模块同串断言 2）
        ('图鉴/缘契安全边界挂载仍在', 'e.jsx(YlxwCharSafe,{', 2, '==', '改名未删挂载'),
        ('修炼速度钩子已注入',       EXP_ADD, 1, '==', ''),
        ('修炼速度钩子挂到 t',       'YlxwCharDexRate(t):0)', 1, '==', ''),
        # 主渲染路径上的钩子必须自带兜底：本作无 app 级 ErrorBoundary，
        # 该算式一抛错就会卸载整棵树（整站白屏）。回归门禁。
        ('图鉴加成钩子有 try/catch 兜底', 'try{S+=(typeof YlxwCharDexRate', 1, '==', '缺失则整站白屏风险'),
        ('空态引导文案（旧字面已清零）', R_EMPTY_TEXT, 0, '==', '0.8.7 T6 追加「多读需求、多交付，缘契上得快。」'),
        # ---- 基线完整性 ----
        ('YlxwMeta 未被破坏',       'function YlxwMeta(k) {', 1, '==', ''),
        ('YlxwPanelModal 未被破坏', 'function YlxwPanelModal(p) {', 1, '==', ''),
        ('xt 总属性函数仍在',       'const xt=t=>{', 1, '==', ''),
        ('St uid 生成器仍在',       'const St=()=>(pg++', 1, '==', ''),
        ('YLRF 缩放函数仍在',       'function YLRF(j) {', 1, '==', ''),
        ('人物志模态框仍在',        'title:"\u4eba\u7269\u5fd7",titleIcon:e.jsx(um,{size:18})', 1, '==', ''),
        ('既有 8 名字池仍在',       '"\\u4e91\\u6e38\\u9053\\u4eba","\\u91c7\\u836f\\u4fee\\u58eb"', 3, '==', '历练/抉择/战斗三处触发点'),
        ('既有好感度 buff 未被改',   'T.favorability>=80?S+=.1:T.favorability>=50&&(S+=.05);', 1, '==', ''),
        ('既有空态原文已替换',       A_EMPTY_TEXT, 0, '==', '必须为 0'),
        ('未新增 YLXW_TABS 项',      'YLXW_TABS.push({ key: "charcodex"', 0, '==', '必须为 0'),
        ('未新增 YLXW_COMP 项',      'YLXW_COMP.charcodex', 0, '==', '必须为 0'),
        ('未新增 YLXW_ICONS 项',     'YLXW_ICONS.charcodex', 0, '==', '必须为 0'),
        ('物品工厂定义',            'function YlxwCharItem(', 1, '==', ''),
        ('物品叠加助手定义',        'function YlxwCharPushItems(', 1, '==', ''),
        ('每日免费寻访日期函数',     'function YlxwCharToday(', 1, '==', ''),
        ('已领里程碑判定函数',       'function YlxwCharBondClaimed(', 1, '==', ''),
    ]
    return gates
