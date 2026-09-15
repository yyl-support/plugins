# yyl-support/plugins

团队自用的 Claude Code 插件集合（marketplace 仓库）。

## 安装

在 Claude Code 里依次执行：

```
/plugin marketplace add yyl-support/plugins
/plugin install knowledge-plugin@yyl-support-plugins
```

装好后用 `/knowledge-plugin:portal` 和 `/knowledge-plugin:doc-reconcile` 调用。

## 插件列表

| 插件 | 作用 |
|---|---|
| [`knowledge-plugin`](./plugins/knowledge-plugin) | 团队代码知识门户 + 门户文档可信度对账 |

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
