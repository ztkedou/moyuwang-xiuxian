#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 CHANGELOG.md 自动生成 README.md 里的「更新日志」段。

为什么需要它
------------
README 的「相比上游改了什么」段过去是手写的，发版时很容易忘记同步，
于是出现「README 写的版本号 / 日期 / 内容和 CHANGELOG.md 对不上」。
本脚本把这一段变成**从 CHANGELOG.md 派生**的生成物：只要 CHANGELOG.md 是对的，
README 就不会再漂移。

权威源
------
`CHANGELOG.md`（仓库根目录）是**唯一权威**。本脚本只读它、绝不改写它。
要改更新日志内容，请改 CHANGELOG.md，然后重跑本脚本。

生成区
------
README.md 里由下面两行标记包住的内容是**自动生成**的：

    <!-- BEGIN:CHANGELOG -->
    ...
    <!-- END:CHANGELOG -->

标记之外的内容一个字都不会动。第一次使用时请先手工把这两行标记放进 README。

用法
----
    python scripts/gen-readme-changelog.py                  # 就地更新 README.md
    python scripts/gen-readme-changelog.py --check          # 只校验，不一致退出码 1
    python scripts/gen-readme-changelog.py --limit 16       # 详细列最近 16 版
    python scripts/gen-readme-changelog.py --max-bullets 5  # 每版最多 5 条要点
    python scripts/gen-readme-changelog.py --changelog /path/to/CHANGELOG.md

幂等：同一份 CHANGELOG.md 重复运行，产物逐字节一致。
"""

import argparse
import re
import sys
from pathlib import Path

BEGIN = "<!-- BEGIN:CHANGELOG -->"
END = "<!-- END:CHANGELOG -->"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANGELOG = REPO_ROOT / "CHANGELOG.md"
DEFAULT_README = REPO_ROOT / "README.md"

# 版本头：## [0.8.11.9] - 2026-10-01 09:32（★ 语法事故热修）
VER_RE = re.compile(
    r"^##\s*\[(?P<ver>[^\]]+)\]\s*-\s*(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:\s+(?P<time>\d{1,2}:\d{2}))?"
)

# 只讲「哪一类改动」的空标题，对读者没信息量，整版都是这类标题时就不显示
GENERIC_TITLES = {
    "问题修复", "新增", "平衡调整", "体验优化", "说明", "其它", "其他",
    "名称调整", "新玩法", "后台与运维", "上游同步", "活动", "上游复刻",
}

# 只讲「这一段在说什么」的空要点，遇到时改取冒号后的正文
GENERIC_LEADS = {
    "用户目标", "用户要求", "改动", "效果", "验证", "根因", "现象", "修复",
    "过程", "教训", "说明", "结论", "实测", "端点实测", "附", "代价说明",
    "问题", "目标", "背景", "方案", "做法", "变化", "影响", "原因",
}


def clean(text: str) -> str:
    """把技术性噪音从一行文本里去掉，只留玩家看得懂的部分。"""
    s = text
    s = re.sub(r"`([^`]*)`", r"\1", s)                       # 去反引号
    s = re.sub(r"\*\*", "", s)                               # 去加粗标记
    s = re.sub(r"[（(][^（）()]*R-\d[^（）()]*[）)]", "", s)     # 去含 R 编号的括号
    s = re.sub(r"R-\d+(?:\.\d+)*", "", s)                     # 去 R-076 这类编号
    s = re.sub(r"[（(]\s*复刻上游[^（）()]*[）)]", "", s)        # 去「（复刻上游 …）」
    s = re.sub(r"[（(]\s*[）)]", "", s)                        # 去空括号
    s = s.replace("⚠️", "").replace("★", "").replace("☆", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip("：:，,。.、·—　 ")


# 含文件名 / 模块名 / md5 这类技术标识的要点，对玩家读者没意义，直接丢弃
TECH_RE = re.compile(
    r"(?:\w+\.(?:py|js|ts|json|sql|md|html|css)\b|_ext\b|srv_patch|md5|node\s+--check)",
    re.IGNORECASE,
)


def is_technical(text: str) -> bool:
    return bool(TECH_RE.search(text))


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def lead_of(bullet: str) -> str:
    """从一条要点里提取「一句话要点」。"""
    s = bullet.strip()
    s = re.sub(r"^[⚠️★☆\s]+", "", s)

    m = re.match(r"^\*\*(.+?)\*\*", s)
    if m:
        cand = clean(m.group(1))
        if cand and len(cand) >= 4 and cand not in GENERIC_LEADS:
            return truncate(cand, 60)
        # 空要点 → 取冒号后面的正文（到第一个句号为止）
        rest = re.sub(r"^[：:，,\s]+", "", s[m.end():])
        rest = re.split(r"[。]", rest, maxsplit=1)[0]
        rest = clean(rest)
        if rest:
            return truncate(rest, 60)
        return truncate(cand or clean(s), 60)

    m2 = re.match(r"^([^：。（(]{2,60})", s)
    if m2:
        return truncate(clean(m2.group(1)), 60)
    return truncate(clean(s), 60)


def parse_changelog(text: str):
    """把 CHANGELOG.md 解析成 [{ver, date, time, titles, bullets}, ...]（新→旧）。"""
    entries = []
    cur = None
    for line in text.split("\n"):
        m = VER_RE.match(line)
        if m:
            cur = {
                "ver": m.group("ver").strip(),
                "date": m.group("date"),
                "time": m.group("time") or "",
                "titles": [],
                "bullets": [],
            }
            entries.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("### "):
            cur["titles"].append(line[4:].strip())
            continue
        if line.startswith("- "):
            cur["bullets"].append(line[2:].strip())
            continue
        if line.startswith(("  - ", "\t- ")):
            continue  # 子条目忽略
        if cur["bullets"] and line.startswith(("  ", "\t")) and line.strip():
            cur["bullets"][-1] += " " + line.strip()
    return entries


def ver_key(ver: str):
    parts = []
    for p in re.split(r"[.\-]", ver):
        parts.append(int(p) if p.isdigit() else -1)
    return tuple(parts)


def title_of(entry) -> str:
    cleaned = [clean(t) for t in entry["titles"]]
    cleaned = [t for t in cleaned if t]
    if not cleaned:
        return ""
    if all(t in GENERIC_TITLES for t in cleaned):
        return ""
    return " / ".join(cleaned)


def render(entries, limit: int, max_bullets: int) -> str:
    recent = entries[:limit]
    older = entries[limit:]
    out = [BEGIN]
    out.append(
        "> 本段由 `scripts/gen-readme-changelog.py` 依据 [CHANGELOG.md](./CHANGELOG.md) **自动生成**，请勿手改；"
    )
    out.append(
        "> 要改内容请改 `CHANGELOG.md`（唯一权威源），再运行 `python scripts/gen-readme-changelog.py`。"
    )
    out.append("")

    for e in recent:
        stamp = f"{e['date']} {e['time']}".strip()
        out.append(f"### {e['ver']}（{stamp}）")
        title = title_of(e)
        if title:
            out.append(f"**{title}**")
        seen = []
        for b in e["bullets"]:
            lead = lead_of(b)
            if lead and not is_technical(lead) and lead not in seen:
                seen.append(lead)
            if len(seen) >= max_bullets:
                break
        for lead in seen:
            out.append(f"- {lead}")
        out.append("")

    if older:
        span = f"{older[-1]['ver']} ~ {older[0]['ver']}"
        out.append(f"### 更早的版本（{span}，共 {len(older)} 版）")
        for e in older:
            head = ""
            for b in e["bullets"]:
                cand = lead_of(b)
                if cand and not is_technical(cand):
                    head = cand
                    break
            if not head:
                head = clean(e["titles"][0]) if e["titles"] else ""
            line = f"- **{e['ver']}**（{e['date']}）"
            if head:
                line += f"：{truncate(head, 40)}"
            out.append(line)
        out.append("")

    out.append("> 以上为要点汇总，完整逐版条目见 [CHANGELOG.md](./CHANGELOG.md)。")
    out.append(END)
    return "\n".join(out)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    eol = "\r\n" if b"\r\n" in path.read_bytes() else "\n"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.replace("\n", eol))


def splice(readme: str, region: str) -> str:
    i = readme.find(BEGIN)
    j = readme.find(END)
    if i == -1 or j == -1 or j < i:
        sys.exit(
            f"[FATAL] README 里找不到 {BEGIN} / {END} 标记。\n"
            f"        请先手工把这两行标记放进 README 的「更新日志」段首尾，再运行本脚本。"
        )
    return readme[:i] + region + readme[j + len(END):]


def newest_ver_in_region(region: str) -> str:
    m = re.search(r"^###\s+([0-9][^\s（(]*)", region, re.M)
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description="从 CHANGELOG.md 生成 README 的更新日志段")
    ap.add_argument("--changelog", default=str(DEFAULT_CHANGELOG), help="权威源路径（默认 ./CHANGELOG.md）")
    ap.add_argument("--readme", default=str(DEFAULT_README), help="目标 README 路径（默认 ./README.md）")
    ap.add_argument("--limit", type=int, default=14, help="详细列出的最近版本数（默认 14）")
    ap.add_argument("--max-bullets", type=int, default=6, help="每版最多列几条要点（默认 6）")
    ap.add_argument("--check", action="store_true", help="只校验 README 是否已最新，不一致则退出码 1")
    ap.add_argument("--force", action="store_true", help="即使权威源比 README 还旧（疑似没同步）也照写")
    args = ap.parse_args()

    cl_path = Path(args.changelog)
    rd_path = Path(args.readme)
    if not cl_path.is_file():
        sys.exit(f"[FATAL] 找不到权威源：{cl_path}")
    if not rd_path.is_file():
        sys.exit(f"[FATAL] 找不到 README：{rd_path}")

    entries = parse_changelog(read_text(cl_path))
    if not entries:
        sys.exit(f"[FATAL] 没能从 {cl_path} 解析出任何版本头（期望形如 `## [0.9.2] - 2026-10-01 16:45`）。")

    region = render(entries, args.limit, args.max_bullets)
    readme = read_text(rd_path)
    new_readme = splice(readme, region)

    old_region_start = readme.find(BEGIN)
    old_region_end = readme.find(END)
    old_region = readme[old_region_start:old_region_end + len(END)] if old_region_start != -1 else ""

    latest = entries[0]["ver"]
    old_latest = newest_ver_in_region(old_region)
    if old_latest and ver_key(latest) < ver_key(old_latest):
        msg = (
            f"权威源最新版 {latest} 比 README 里现有的 {old_latest} 还旧 —— "
            f"CHANGELOG.md 很可能没同步到位，继续跑会把 README 往回退。"
            f"请先把最新的 CHANGELOG.md 同步过来；确实要回退请加 --force。"
        )
        if not args.force:
            print(f"[FATAL] {msg}", file=sys.stderr)
            return 2
        print(f"[WARN] {msg}", file=sys.stderr)

    if args.check:
        if old_region == region:
            print(f"[OK] README 已与 CHANGELOG.md 一致（最新 {latest}）。")
            return 0
        print(f"[DIFF] README 的更新日志段与 CHANGELOG.md 不一致（最新 {latest}），请运行脚本重新生成。", file=sys.stderr)
        return 1

    if old_region == region:
        print(f"[OK] 无需改动，README 已与 CHANGELOG.md 一致（最新 {latest}）。")
        return 0

    write_text(rd_path, new_readme)
    print(f"[DONE] 已用 {cl_path} 重新生成 {rd_path} 的更新日志段（最新 {latest}）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
