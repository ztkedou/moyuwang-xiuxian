# -*- coding: utf-8 -*-
r"""sync-from-prod.py — 把线上生产环境的 yl 定版产物同步进本发布仓库。

为什么需要它：
  线上 /opt/yl 是「开发工作树」（169 跟踪文件 / 75MB，含大量 *.bak-* 与 diag 脚本），
  **不适合**直接推 GitHub。本发布仓库才是对外唯一源码包。
  本脚本负责把「生产实际在跑的那一版」抽出来，覆盖进 build/ 与 srv/，保持二者一致。

用法：
  python scripts/sync-from-prod.py            # 拉取 + 覆盖 + 报告
  python scripts/sync-from-prod.py --check    # 只比对 md5，不写文件

依赖：paramiko（WorkBuddy python env 已装）
"""
import argparse
import hashlib
import os
import re
import sys

def _default_key():
    """本机私钥文件名含已退役旧机 IP（历史遗留，勿改名），故不写死字面量：
    优先环境变量，其次扫 ~/.ssh 下匹配 ali-hk-*.key 的第一个。"""
    env = os.environ.get("YL_PROD_KEY")
    if env:
        return os.path.expanduser(env)
    sshd = os.path.expanduser("~/.ssh")
    if os.path.isdir(sshd):
        for f in sorted(os.listdir(sshd)):
            if f.startswith("ali-hk") and f.endswith(".key"):
                return os.path.join(sshd, f)
    return os.path.expanduser("~/.ssh/yl_prod.key")


HOST = os.environ.get("YL_PROD_HOST", "104.208.x.x")
USER = os.environ.get("YL_PROD_USER", "root")
KEY = _default_key()
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 生产路径 → 仓库路径
MAP = [
    ("/opt/yl/server/index.ts", "srv/index_v28.ts"),
    ("/opt/yl/server/game-dicts.json", "srv/game-dicts.json"),
    ("/opt/yl/www/CHANGELOG.md", "CHANGELOG.md"),
    ("/opt/yl/www/CHANGELOG_PLAYER.md", "CHANGELOG_PLAYER.md"),
]

# ★ 预期差异（不是漂移，别去"修"）：
#   build/index.html —— 生产用 /myxxz/ 绝对路径 + 平台注入块
#   （h5game/unified-stats.js、mw-reward），仓库用 ./ 相对路径以保证可移植。
#   因此 index.html **不参与自动同步**，只在报告里提示。
EXPECTED_DIFF = {
    "build/index.html": "生产用 /myxxz/ 绝对路径 + 平台注入块（unified-stats / mw-reward）；"
                        "仓库保持 ./ 相对路径 + 无注入，属预期差异。",
}


def connect():
    import paramiko
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, key_filename=KEY, timeout=30,
              allow_agent=False, look_for_keys=False)
    return c


def md5(b):
    return hashlib.md5(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只比对，不写")
    args = ap.parse_args()

    c = connect()
    sftp = c.open_sftp()

    # 1) 找出生产 index.html 实际引用的 bundle 名
    with sftp.open("/opt/yl/www/index.html", "rb") as f:
        html = f.read().decode("utf-8", "replace")
    m = re.search(r"assets/(index-v[\w\-]+\.js)", html)
    if not m:
        raise SystemExit("找不到 index.html 引用的 bundle")
    cur = m.group(1)
    print("生产当前定版 bundle:", cur)

    rows = []
    for prod, repo in MAP:
        p = prod
        try:
            with sftp.open(p, "rb") as f:
                pdata = f.read()
        except Exception as ex:
            print("  跳过 %s (%s)" % (p, ex)); continue
        rp = os.path.join(REPO, repo)
        rdata = open(rp, "rb").read() if os.path.exists(rp) else None
        same = (rdata is not None and md5(rdata) == md5(pdata))
        rows.append((p, repo, md5(pdata), md5(rdata) if rdata else "-", same))
        if not args.check and not same:
            os.makedirs(os.path.dirname(rp), exist_ok=True)
            open(rp, "wb").write(pdata)
    # bundle 单独处理（路径含 {CUR}）
    pb = "/opt/yl/www/assets/" + cur
    rb = os.path.join(REPO, "build/assets", cur)
    try:
        with sftp.open(pb, "rb") as f:
            pdata = f.read()
        rdata = open(rb, "rb").read() if os.path.exists(rb) else None
        same = (rdata is not None and md5(rdata) == md5(pdata))
        rows.insert(0, (pb, "build/assets/" + cur, md5(pdata),
                        md5(rdata) if rdata else "-", same))
        if not args.check and not same:
            os.makedirs(os.path.dirname(rb), exist_ok=True)
            open(rb, "wb").write(pdata)
    except Exception as ex:
        print("  bundle 拉取失败", ex)

    print()
    print("%-46s %-34s %s" % ("生产", "仓库", "一致"))
    for p, r, pm, rm, same in rows:
        mark = "OK" if same else "★不一致"
        if not same and r in EXPECTED_DIFF:
            mark = "预期差异"
        print("%-46s %-34s %s" % (p, r, mark))
    bad = [r for _, r, _, _, s in rows if not s and r not in EXPECTED_DIFF]
    for r in EXPECTED_DIFF:
        print()
        print("提示 %s：%s" % (r, EXPECTED_DIFF[r]))
    if bad:
        print()
        print("不一致（%d）：" % len(bad))
        for b in bad:
            print("  " + b)
        if args.check:
            return 1
        print("已按生产覆盖。")
    else:
        print()
        print("全部一致 ✅")
    sftp.close()
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
