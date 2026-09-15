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

`version` 是更新开关——不 bump，用户就收不到更新。
