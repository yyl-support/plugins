---
name: codegraph-setup
description: 为仓库批量建立 codegraph 代码索引，让 codegraph MCP 的工具（explore / callers / impact 等）真正可用，并顺带把索引目录挡在 git 之外。当用户说"帮我给这几个仓建索引""codegraph 怎么用不了""预热一下这些仓库""MCP 报 isn't indexed"，或拿到新仓库想让它支持代码结构查询时使用。Use when the user wants to index repositories for codegraph, when codegraph MCP tools return "isn't indexed", or when onboarding onto new repos that need code-structure queries.
---

# 建立 codegraph 索引

## 什么时候需要

codegraph MCP 的工具**只在已建索引的仓库上可用**。没建索引时，
工具调用不会报"工具不存在"，而是返回一句 `isn't indexed with codegraph`
——**看起来像插件坏了，其实只是没建索引**。

## 执行

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/codegraph-setup/scripts/warmup.py" <仓库路径> [<仓库路径> ...]
```

脚本会：建索引（已建过的走增量 `sync`）、并把 `.codegraph/` 写进
该仓库的 `.git/info/exclude`。

## 跑之前必须先说清楚成本

**建索引要花磁盘和时间，所以必须先问用户，不要自作主张跑。**

实测：104 个文件 → 索引 7.3MB / 1.66 秒。仓库越大越久，
**大仓可能几分钟到几十分钟**。

用户没明确点名仓库时，不要擅自替他挑——列出候选让他选。

## 脚本顺带解决的一个坑

`codegraph init` **不会**把 `.codegraph/` 写进 `.gitignore`。实测 `init --yes`
跑完，`git status` 里是裸的 `?? .codegraph/`——一次 `git add -A`
就把 7MB 的 SQLite 提交进去了。

脚本的处理是写进 `.git/info/exclude`，**不动仓库里受版本控制的 `.gitignore`**：

- 脏是本机跑 init 造成的，就该在本机解决
- 不替团队决定他们的 `.gitignore` 长什么样

### 这一点要主动告诉用户

`info/exclude` 是**每个 clone 各自一份**，不随仓库分发。
同事 clone 下来不会有这条规则——**换台机器就要重跑本脚本**。

## 报告结果时

- 索引成功 ≠ 代码结构问题都能答了。索引覆盖的是**符号与调用关系**，
  不含 YAML / Shell / Dockerfile / Markdown 的结构化查询
- 仓库很大时脚本会跑很久，属正常，不是卡死

## 不要做的事

- ❌ 不要在用户没要求时自动建索引——磁盘和时间是用户的成本
- ❌ 不要改仓库的 `.gitignore` 来达到忽略目的（见上）
- ❌ 不要用 `codegraph uninit` 清理——会删掉索引，用户要重新花时间建
