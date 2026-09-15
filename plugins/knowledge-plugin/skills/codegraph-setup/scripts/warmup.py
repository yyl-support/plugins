#!/usr/bin/env python3
"""为一组仓库批量建 codegraph 索引，并把 .codegraph/ 挡在 git 之外。

用法：
    python3 warmup.py <仓库路径> [<仓库路径> ...]

为什么需要它：codegraph MCP 的工具只在"已建索引"的仓库上可用，
而建索引必须由人决定（耗磁盘），agent 不会自动跑。这个脚本把这件事
变成一条命令，同时处理一个很容易忘的副作用——见下。

**它顺带解决的坑**：`codegraph init` 不会把 `.codegraph/` 写进 `.gitignore`。
实测：`init --yes` 跑完，`git status` 里是 `?? .codegraph/`，那个目录
有 7MB 的 SQLite——一次 `git add -A` 就提交进去了。

处理方式是写进 `.git/info/exclude`（**本地**忽略），不动仓库里受版本
控制的 `.gitignore`。理由：脏是本机跑 init 造成的，就该在本机解决，
不该为此改动别人的仓库、更不该替团队决定他们的 .gitignore 长什么样。

注意 `info/exclude` 是**每个 clone 各自一份**，换台机器要重跑本脚本。

只读代码、只写索引与本地忽略规则，不碰任何受版本控制的文件。
"""

import subprocess
import sys
from pathlib import Path

CODEGRAPH = ["npx", "-y", "@colbymchenry/codegraph"]
EXCLUDE_LINE = ".codegraph/"
# 排除行后面必须是换行结尾，否则会粘在上一行末尾
TRAILING_NEWLINE = "\n"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def find_exclude_file(repo):
    """用 git 自己算 info/exclude 的位置。

    不手拼 ".git/info/exclude"——worktree / submodule 下 `.git` 是个文件
    （内容是 `gitdir: ...`），手拼会写到一个不存在的地方，然后静默失效。
    """
    r = run(["git", "-C", str(repo), "rev-parse", "--git-path", "info/exclude"])
    if r.returncode != 0:
        return None, r.stderr.strip()
    p = Path(r.stdout.strip())
    return (p if p.is_absolute() else Path(repo) / p), None


def ensure_excluded(repo):
    """确保 .codegraph/ 被本地忽略。返回 (状态, 说明)。"""
    exc, err = find_exclude_file(repo)
    if exc is None:
        return "skip", f"不是 git 仓库（{err}）——索引照建，但无忽略规则可写"

    try:
        old = exc.read_text(encoding="utf-8") if exc.exists() else ""
    except OSError as e:
        return "fail", f"读不到 {exc}：{e}"

    if EXCLUDE_LINE in {ln.strip() for ln in old.splitlines()}:
        return "ok", "已在 info/exclude 中"

    try:
        exc.parent.mkdir(parents=True, exist_ok=True)
        # 文件没以换行结尾时先补一个，否则新行会粘到上一行末尾
        sep = "" if (not old or old.endswith(TRAILING_NEWLINE)) else TRAILING_NEWLINE
        exc.write_text(old + sep + EXCLUDE_LINE + TRAILING_NEWLINE, encoding="utf-8")
    except OSError as e:
        return "fail", f"写不了 {exc}：{e}"
    return "ok", "已写入 info/exclude（本地忽略）"


def index(repo):
    """建索引。已建过则增量同步，避免留下一个静默过期的索引。"""
    already = (Path(repo) / ".codegraph").is_dir()
    cmd = CODEGRAPH + (["sync", str(repo)] if already else ["init", str(repo), "--yes"])
    r = run(cmd, timeout=1800)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()
        return False, (tail[-1] if tail else f"退出码 {r.returncode}")

    lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    stat = next((ln for ln in lines if "nodes" in ln and "edges" in ln), "")
    return True, ("已同步" if already else "已建索引") + (f"：{stat.lstrip('● ').strip()}" if stat else "")


def main():
    repos = sys.argv[1:]
    if not repos:
        print(__doc__)
        sys.exit(1)

    failed = []
    for raw in repos:
        repo = Path(raw).expanduser()
        print(f"\n■ {repo}")
        if not repo.is_dir():
            print("  ✗ 路径不存在或不是目录")
            failed.append(raw)
            continue

        status, msg = ensure_excluded(repo)
        print(f"  {'✓' if status == 'ok' else '·' if status == 'skip' else '✗'} 忽略规则：{msg}")
        if status == "fail":
            failed.append(raw)

        ok, msg = index(repo)
        print(f"  {'✓' if ok else '✗'} 索引：{msg}")
        if not ok:
            failed.append(raw)

    print()
    if failed:
        print(f"✗ {len(failed)} 个仓库未成功：{'、'.join(failed)}")
        sys.exit(1)
    print("✓ 全部完成。索引已就绪，codegraph MCP 的工具现在可用于这些仓库。")


if __name__ == "__main__":
    main()
