# yyl-support/plugins

团队自用的 Claude Code 插件集合（marketplace 仓库）。

## 安装

在 Claude Code 里依次执行：

```
/plugin marketplace add yyl-support/plugins
/plugin install knowledge-plugin@yyl-support-plugins
```

装好后不用记命令——直接描述你的问题，agent 会自己挑合适的 skill。

## 插件列表

| 插件 | 作用 |
|---|---|
| [`knowledge-plugin`](./plugins/knowledge-plugin) | 团队代码知识门户 + 门户文档可信度对账 |

## knowledge-plugin 用它来干什么

| 你想问 | agent 会调用 |
|---|---|
| 这个项目是干嘛的 / 怎么上手 / 怎么参与 | `portal` |
| 团队一共有哪些仓库 / 我该看哪个仓 | `portal`（内含 gitcode 脚本） |
| 这份文档准不准 / 新人能不能照着做 / 是不是过期了 | `doc-reconcile` |
| 这个函数被谁调用 / 改了会影响什么 | codegraph MCP |
| GitCode 上那个 issue / PR 是什么情况 | gitcode MCP |

**测试环境 / 部署上线不在范围内**——那部分由独立模块承载，被问到时会如实说答不了。

## 两个 MCP 的故障排查

两个 MCP 的失败方式**完全不同**，遇到问题先看这里：

### gitcode：需要 `GITCODE_TOKEN` 环境变量

**症状**：工具**根本不在**工具列表里（注意：不是调用失败，是压根没有）。

**原因**：该 server 在**启动时**校验 token，token 无效则整个 server 不启动。

**处理**：设置环境变量后**重启会话**：

```bash
export GITCODE_TOKEN=<你自己的 token>
```

token 向团队申请，**不要提交到任何仓库**。

同一个 token 也用于 `portal` 里的"团队有哪些仓库"脚本。该接口**只返回
token 有权看到的仓库**——实测同一组织匿名请求返回 1 个、带 token 返回 8 个
（7 个私有），**不报错，只是少给**。所以列表为空不代表组织下没有仓库。

### codegraph：需要先建索引

**症状**：工具能调用，但返回 "isn't indexed with codegraph"。

**原因**：该仓库没有 `.codegraph/` 目录。

**处理**：在项目里跑 `codegraph init`。建索引耗时且占磁盘，所以由**你**决定，
agent 不会自动跑。

### 排查工具是否存在时，用全名

MCP 工具名带命名空间，例如：

```
mcp__plugin_knowledge-plugin_codegraph__codegraph_explore
```

用短名 `codegraph_explore` 去问会得到"不存在"的答复——那是名字不对，
不是工具没装上。

## 新增插件

在 `plugins/` 下新建目录，放 `.claude-plugin/plugin.json` 与 `skills/`，
然后在本仓库的 `.claude-plugin/marketplace.json` 的 `plugins` 数组里追加一条：

```json
{
  "name": "your-plugin",
  "source": "./plugins/your-plugin",
  "description": "...",
  "version": "0.1.0"
}
```

## 更新

改完推 `main` 之后，**必须** bump `version`，而且**要 bump 两处**：

- `.claude-plugin/marketplace.json` 里该插件条目的 `version`
- `plugins/<插件名>/.claude-plugin/plugin.json` 里的 `version`

### 两个坑

1. **两处 `version` 必须一致。** `claude plugin tag` 会校验 `plugin.json`
   与外层 marketplace 条目是否相符，不一致直接报错。
2. **不 bump `version`，用户就收不到更新。** 推了 `main` 但没改 version，
   同事那边 `/plugin update` 是空的——插件被钉在旧版本号上，内容更新推不下去。

### 发布前自查

```bash
claude plugin validate ./plugins/<插件名>   # 插件清单
claude plugin validate .                    # 市场清单
```

两条都过再推。
