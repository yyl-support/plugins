#!/usr/bin/env python3
"""门户文档对账：检出文档的悬空引用、覆盖缺口与失效的 skill 引用。

用法：
    python3 reconcile.py <repo_dir>

输入是一个已克隆到本地的仓库目录，输出对账报告。

检测四类问题：
  A. 悬空引用   —— 文档提到的文件/目录在仓库里不存在
  B. 覆盖缺口   —— 仓库顶层条目文档从未提及
  C. Skill 引用 —— 文档声称的 skill 不存在，或存在的 skill 未被收录
  D. Skill 文档 —— 每个 .claude/skills/*/SKILL.md 自身的悬空引用

只验证"对不对得上"，不验证"说得对不对"：文件存在但内容过时、
描述与实现行为不符，均检不出。检出 0 问题 ≠ 文档没问题，只是自洽。
"""

import re
import sys
from pathlib import Path

# ---- 配置 ----------------------------------------------------------------

# 门户文档的扫描优先级（与插件分层一致：先"怎么做"，再"是什么"）
PORTAL_DOCS = ["CLAUDE.md", "AGENTS.md", "README.md"]

# 覆盖缺口统计时忽略：版本控制、CI 配置、skill 目录（由 C/D 类单独覆盖）
IGNORE_ENTRIES = {".git", ".github", ".claude", ".gitignore"}

# 文件扩展名白名单——用于把 token 判为"文件引用"
HAS_EXT = re.compile(
    r"\.(py|sh|bash|yaml|yml|md|json|txt|toml|cfg|ini|env|"
    r"js|jsx|ts|tsx|go|java|rs|rb|php|cs|kt|swift|scala|"
    r"tpl|conf|lock|xml|sql|proto|gradle|cmake)$"
)

# 外部域名（无 scheme 的 URL 写法）
EXTERNAL = re.compile(r"[\w-]+\.(com|cn|org|io|net|dev|ai)/")
# 跨仓库引用：`other-repo/docs :: path/to/file` —— 本地没有那个仓，必然误报
CROSS_REPO = re.compile(r"\s+::\s+|\s+->\s+")
# IP/CIDR：10.106.0.0/16
IP_CIDR = re.compile(r"^\d{1,3}(\.\d{1,3}){3}/\d+$")
# CJK 字符
CJK = re.compile(r"[一-鿿]")
# skill 上下文信号——用于区分 `/arc-deploy`（skill）与 `/health`（HTTP 端点）
SKILL_CTX = re.compile(r"skill|技能|slash|斜杠|触发|invoke|命令", re.I)

BACKTICK = re.compile(r"`([^`\n]+)`")
FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
SKILL_MENTION = re.compile(r"`/([a-z][a-z0-9-]{2,})`")


# ---- 仓库索引 -------------------------------------------------------------
# 一次性建立索引，避免对每个 token 重复 rglob（大仓上这是主要耗时）。
# 全部用 Path.parts 比较而非字符串拼接——目标环境含 Windows，
# 字符串里的 "/" 与 Windows 的 "\\" 不匹配，会让整个 exists() 静默失效。


def build_index(repo: Path):
    """返回 (全部相对路径的元组集合, basename -> [路径元组])。"""
    rels = set()
    by_base = {}
    for p in repo.rglob("*"):
        try:
            rp = p.relative_to(repo).parts
        except ValueError:
            continue
        if ".git" in rp:
            continue
        rels.add(rp)
        by_base.setdefault(rp[-1], []).append(rp)
    return rels, by_base


def exists(idx, tok: str) -> bool:
    """该 token 在仓库中是否存在（容忍文档省略中间层级）。"""
    rels, by_base = idx
    cand = tok.strip("./").rstrip("/")
    if not cand:
        return False
    parts = tuple(cand.split("/"))
    if parts in rels:
        return True
    if len(parts) == 1:
        return parts[0] in by_base
    # 文档可能省略了中间层级（如 org/repo 目录），按尾部匹配
    for rp in by_base.get(parts[-1], ()):
        if rp[-len(parts):] == parts:      # 全路径后缀命中
            return True
        if rp[-2:] == parts[-2:]:          # 末两段命中
            return True
    return False


# ---- 引用提取 -------------------------------------------------------------


def is_dirish(tok: str) -> bool:
    """判断 token 是否像仓库内目录路径——用于压掉正文里的自然语言噪声。

    早期的做法是"两侧都是短词就拒"，但那会误杀 `argocd/clusters`、
    `other/Ascend` 这类真实目录。改为按"是否像散文"来判：
    含中文、或任一段含大写字母的，基本是 `Pod/Service`、`podCIDR` 这类术语。
    """
    if "/" not in tok or not re.fullmatch(r"[\w.\-/]+", tok):
        return False
    if IP_CIDR.match(tok):
        return False
    if CJK.search(tok):            # 卡数/SFS、Server/网段/NPU
        return False
    segs = tok.split("/")
    if any(re.search(r"[A-Z]", s) for s in segs):   # Pod/Service、podCIDR
        return False
    # 首段含点 → k8s 注解键（scheduling.volcano.sh/queue-name），非仓库路径
    if "." in segs[0]:
        return False
    return True


def _classify(raw: str, files: set, dirs: set, self_name: str):
    """从一段文本里挑出路径样 token。按空白切分以覆盖命令行形式。"""
    if CROSS_REPO.search(raw):  # 跨仓库引用，本地无从校验
        return
    for tok in raw.split():
        tok = tok.strip().strip("\"'").rstrip(".,;:()[]")
        if not tok or tok.startswith("-"):
            continue
        if "://" in tok or EXTERNAL.search(tok):      # 外部 URL
            continue
        if tok.startswith("/"):                        # 容器内绝对路径
            continue
        if tok.startswith(("$", "{")) or "{" in tok or "<" in tok:
            continue                                   # 占位符 / 变量
        if "*" in tok or "?" in tok:                   # glob 模式
            continue
        if "..." in tok or "…" in tok:                 # 散文省略号
            continue
        if tok == self_name:                           # 文档引用了自己
            continue
        if HAS_EXT.search(tok):
            files.add(tok)
        elif is_dirish(tok):
            dirs.add(tok)


def extract_refs(text: str, self_name: str):
    """提取文档中所有像"仓库内文件"的引用，分文件/目录两档。

    扫两处：行内反引号，以及 ``` 围栏代码块。
    后者很关键——可运行命令（如 `python3 foo.py`）通常写在代码块里，
    而这类引用恰恰最容易过期失效。
    """
    files, dirs = set(), set()
    for raw in BACKTICK.findall(text):
        _classify(raw, files, dirs, self_name)
    for block in FENCE.findall(text):
        for ln in block.splitlines():
            ln = ln.lstrip("#").strip()  # 去掉 shell 注释
            if not ln or ln.startswith("<!--"):
                continue
            _classify(ln, files, dirs, self_name)
    return files, dirs


def line_of(text: str, tok: str) -> int:
    for i, l in enumerate(text.splitlines(), 1):
        if tok in l:
            return i
    return 0


# ---- C. Skill 引用 --------------------------------------------------------


def check_skills(repo: Path, text: str):
    """检出文档提到但仓库中不存在的 skill。

    动机：skill 名不带扩展名也不带斜杠（如 `/arc-deploy`），会被 A 类的
    路径规则漏掉，但它是最"可执行"的引用——用户照着敲 `/app-argocd-onboarding`，
    得到的是 command not found。

    难点：`` `/health` `` 这类 HTTP 端点写法与 skill 名完全同形。
    判据是"带连字符"或"所在行附近有 skill 语境"，避免把接口当 skill 报。
    """
    lines = text.splitlines()
    claimed = set()
    for m in SKILL_MENTION.finditer(text):
        name = m.group(1)
        ln = text[: m.start()].count("\n")
        ctx = "\n".join(lines[max(0, ln - 5): ln + 1])
        if "-" in name or SKILL_CTX.search(ctx):
            claimed.add(name)
    if not claimed:
        return None

    actual = set()
    for base in (repo / ".claude" / "skills", repo / "skills"):
        if base.is_dir():
            actual |= {d.name for d in base.iterdir() if d.is_dir()}
    return claimed, actual


def skill_docs(repo: Path):
    """收集仓库内所有 SKILL.md。

    动机：根目录门户文档只是"门牌"，团队真正花心思写的知识在 .claude/skills/ 里。
    skill 正文引用的模板/脚本路径与根文档一样会腐烂，且腐烂后没有任何提示。
    """
    out = []
    for base in (repo / ".claude" / "skills", repo / "skills"):
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            sk = d / "SKILL.md"
            if sk.is_file():
                out.append((d.name, sk))
    return out


def scan_doc(repo: Path, idx, text: str, self_name: str):
    """对单份文档跑 A 类悬空引用检查。"""
    files, dirs = extract_refs(text, self_name)
    bad_f = sorted(t for t in files if not exists(idx, t))
    bad_d = sorted(t for t in dirs if not exists(idx, t))
    return bad_f, bad_d, len(files)


# ---- 主流程 ---------------------------------------------------------------


def read_portal(repo: Path):
    """收集**全部**存在的门户文档，而非只取第一个。

    动机：`CLAUDE.md` 与 `AGENTS.md` 可能同时存在且内容不同步
    （实测 `backlog` 两个都有）。只查其中一个会漏掉另一份的问题，
    而 B 类覆盖缺口的判定也需要"全部文档合起来"才算数——
    某个条目只被 README 提到，就不该报成缺口。
    """
    out = []
    for name in PORTAL_DOCS:
        p = repo / name
        if p.is_file():
            out.append((p, p.read_text(encoding="utf-8", errors="replace")))
    return out


def mentioned(name: str, text: str, is_dir: bool) -> bool:
    """文档是否"作为路径"提及了该条目。

    早先用裸子串匹配，会把英文单词误当路径——目录 `bin` 会被
    "binary" 命中，`other` 会被正文里的 "other" 命中。
    目录要求出现 `name/`（路径写法），文件因带扩展名歧义小，放宽为子串。
    """
    if is_dir:
        return f"{name}/" in text or f"`{name}`" in text
    return name in text


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    repo = Path(sys.argv[1]).resolve()
    if not repo.is_dir():
        print(f"不是目录：{repo}")
        sys.exit(1)

    docs_in = read_portal(repo)
    print("=" * 74)
    print(f"仓库：{repo.name}")
    if not docs_in:
        print("门户文档：无")
        print("=" * 74)
        return
    sizes = "  ".join(f"{p.name} {len(t.encode())}B" for p, t in docs_in)
    print(f"门户文档：{sizes}")
    print("=" * 74)

    idx = build_index(repo)
    # 只有一份文档时保持原有的扁平输出；多份时按文档分段，便于定位
    multi = len(docs_in) > 1

    # ---- A. 悬空引用 ----
    print("\n【A. 悬空引用】\n")
    total_bad = 0
    total_refs = 0
    for dpath, text in docs_in:
        files, dirs = extract_refs(text, dpath.name)
        bad_files = sorted(t for t in files if not exists(idx, t))
        bad_dirs = sorted(t for t in dirs if not exists(idx, t))
        total_bad += len(bad_files)
        total_refs += len(files)
        if multi:
            print(f"  ── {dpath.name} ──")
        if bad_files:
            for t in bad_files:
                label = f"{dpath.name}:{line_of(text, t)}" if multi else f"第 {line_of(text, t):>3} 行"
                print(f"    ✗ {label:<12} {t}")
        elif not multi:
            print("  ✓ 无悬空的文件引用")
        if bad_dirs:
            for t in bad_dirs:
                label = f"{dpath.name}:{line_of(text, t)}" if multi else f"第 {line_of(text, t):>3} 行"
                print(f"    ? {label:<12} {t}  （目录，可能是运行时生成）")
        if multi:
            print()

    print(f"  合计：文件类 {total_bad} 悬空 / {total_refs} 引用")

    # ---- C. Skill 引用 ----
    # 跨文档合并：一份声称、另一份收录，就不该报
    claimed_all, actual_all = set(), set()
    for dpath, text in docs_in:
        sk = check_skills(repo, text)
        if sk:
            claimed_all |= sk[0]
            actual_all |= sk[1]
    if claimed_all or actual_all:
        print("\n【C. Skill 引用】\n")
        for s in sorted(claimed_all - actual_all):
            where = next((d.name for d, t in docs_in if f"`/{s}`" in t), "?")
            print(f"    ✗ {where:<14} /{s}  —— 不存在")
        for s in sorted(actual_all - claimed_all):
            print(f"    ○ {'(全部文档)':<14} /{s}  —— 存在但文档未收录")
        if claimed_all == actual_all:
            print("  ✓ 文档与仓库一致")
        print(f"\n  合计：声称 {len(claimed_all)} 个 / 实际 {len(actual_all)} 个")

    # ---- B. 覆盖缺口 ----
    # 判据用"全部文档合起来"——某条目只被 README 提到，就不算缺口
    joined = "\n".join(t for _, t in docs_in)
    print("\n【B. 覆盖缺口】仓库顶层条目未被文档提及\n")
    gap = []
    for p in sorted(repo.iterdir()):
        if p.name in IGNORE_ENTRIES or p.name in PORTAL_DOCS:
            continue
        if mentioned(p.name, joined, p.is_dir()):
            continue
        if p.is_dir():
            fs = [f for f in p.rglob("*") if f.is_file()]
            size = sum(f.stat().st_size for f in fs)
            gap.append((size, p.name, f"{len(fs)} 文件 / {size/1024:.0f}KB"))
        else:
            size = p.stat().st_size
            gap.append((size, p.name, f"{size}B"))
    if gap:
        for _, name, desc in sorted(gap, reverse=True):  # 体积降序：越大越可能是主体
            print(f"    ✗ {name:<34} {desc}")
        print(f"\n  合计 {len(gap)} 个顶层条目未被文档提及")
    else:
        print("  ✓ 无覆盖缺口")

    # ---- D. Skill 文档 ----
    docs = skill_docs(repo)
    if docs:
        print("\n【D. Skill 文档对账】\n")
        skill_bad = 0
        for sname, spath in docs:
            stext = spath.read_text(encoding="utf-8", errors="replace")
            bf, bd, nf = scan_doc(repo, idx, stext, spath.name)
            rel = spath.relative_to(repo)
            for t in bf:
                print(f"    ✗ {rel}:{line_of(stext, t)}   {t}")
            for t in bd:
                print(f"    ? {rel}:{line_of(stext, t)}   {t}  （目录，可能是运行时生成）")
            if not bf and not bd:
                print(f"    ✓ {sname:<28} {nf} 个引用，全部有效")
            skill_bad += len(bf)
        if skill_bad:
            print(f"\n  合计 {skill_bad} 个悬空文件引用")
        else:
            print(f"\n  合计 {len(docs)} 个 skill，无悬空文件引用")
    print()


if __name__ == "__main__":
    main()
