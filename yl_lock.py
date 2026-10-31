# -*- coding: utf-8 -*-
r"""
yl_lock.py — 跨进程独占文件锁（最小实现，供 build_v26n / dryrun_087 / chain_build 用）

背景（2026-10-31 实测踩到）
--------------------------------------------------------------------------
  两个 `build_v26n.py` 进程同时跑时，两者都写同一个 `OUT`
  （`build/assets/index-v102-20261022.js`），且 `apply_standalone()` 会对该文件
  按序做「读 → 改 → 原子写回」。并发下后启动者可能读到被前者截断/半写的中间态，
  于是 standalone 环 rc=1/rc=2 级联报错：

      实测：10:05:04 那次 build 报 3 个 ABORT（r250 rc=1 → r252/r254 rc=2），
            中断现场 2,206,391 chars，正常 2,212,704 chars，**差 6313**。
      随后连跑 3 次全部干净 ⇒ 是并发竞争，不是代码缺陷。

设计取舍
--------------------------------------------------------------------------
  · **平台原生文件锁**（Windows `msvcrt.locking` / POSIX `fcntl.flock`），
    不用 `O_CREAT|O_EXCL` 标记文件 —— 后者在进程崩溃时会留下**陈旧锁**，
    需要人工删文件才能恢复；原生锁随进程退出/句柄关闭**自动释放**。
  · 拿不到锁 → 轮询等待（默认 300s），超时抛 `LockTimeout`（带明确错误）。
  · 用法（with 语句，异常路径也保证释放）：
        from yl_lock import build_lock
        with build_lock(os.path.join(HERE, 'build', '.yl_client_build.lock')):
            ...原有流程...
  · **零侵入**：不改任何现有函数签名/流程，只在入口处包一层。

注意：这是「同一台机器上多个进程」的互斥，不是跨机器锁。
"""

import errno
import os
import sys
import time

DEFAULT_TIMEOUT = 300.0     # 秒（lead 裁定：最多 300 秒）
POLL_INTERVAL = 0.25        # 秒


class LockTimeout(RuntimeError):
    """拿锁超时。"""


def _try_lock(fd):
    """非阻塞尝试加锁；成功返回 True，被占用返回 False。"""
    if sys.platform == 'win32':
        import msvcrt
        try:
            # LK_NBLCK：非阻塞独占；锁 1 字节（内容无关，只为互斥）
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    else:
        import fcntl
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise


def _unlock(fd):
    if sys.platform == 'win32':
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


class FileLock(object):
    """独占文件锁（上下文管理器）。"""

    def __init__(self, path, timeout=DEFAULT_TIMEOUT, label=None, verbose=True):
        self.path = path
        self.timeout = float(timeout)
        self.label = label or os.path.basename(path)
        self.verbose = verbose
        self._fd = None
        self.waited = 0.0

    # --- 获取 ---------------------------------------------------------
    def acquire(self):
        d = os.path.dirname(os.path.abspath(self.path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        # 文件必须存在才能加锁；O_CREAT 不截断（不破坏别人的锁）
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        t0 = time.time()
        warned = False
        while True:
            if _try_lock(fd):
                self._fd = fd
                self.waited = time.time() - t0
                if self.verbose and self.waited > 0.5:
                    print('  [lock] 已获得 %s（等待 %.1fs）' % (self.label, self.waited))
                return self
            waited = time.time() - t0
            if waited >= self.timeout:
                os.close(fd)
                raise LockTimeout(
                    '[lock] 等待 %s 超时（%.0fs）：另一个构建进程仍持有锁。\n'
                    '       锁文件: %s\n'
                    '       ⇒ 等它跑完再试；若确认无进程在跑，可直接删除该锁文件。'
                    % (self.label, self.timeout, self.path))
            if self.verbose and not warned and waited > 2.0:
                warned = True
                print('  [lock] 等待 %s 释放中（另一个构建进程在跑）…' % self.label)
            time.sleep(POLL_INTERVAL)

    # --- 释放 ---------------------------------------------------------
    def release(self):
        if self._fd is not None:
            _unlock(self._fd)
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


def build_lock(path, timeout=DEFAULT_TIMEOUT, label=None, verbose=True):
    """便捷构造（不自动获取，供 with 使用）。"""
    return FileLock(path, timeout=timeout, label=label, verbose=verbose)
