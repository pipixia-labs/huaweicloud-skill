# Versioning Policy

版本事实只放在版本文档里，避免 `SKILL.md`、脚本说明和评审文档各自记录不同版本口径。

## 真相源

- `CHANGELOG.md`：对外版本历史和已发布版本摘要。
- `RELEASE_NOTES.md`：当前未发布变更、发布说明草稿和验证摘要。

## 写作规则

- `SKILL.md` 只描述当前行为、入口和安全边界，不写“从某版本开始支持某能力”。
- `references/` 可以描述能力边界，但不要把它当版本发布记录。
- 新增脚本、reference、playbook 或测试时，把用户可见变化同步到 `RELEASE_NOTES.md` 的 `Unreleased`。
- 发布时再把 `Unreleased` 摘要迁入 `CHANGELOG.md` 或对应发布段落。

## 校验口径

- 维护评审时，优先看 `RELEASE_NOTES.md` 的 `Unreleased` 判断当前待发布内容。
- 用户任务中不要加载历史 release 说明，除非用户明确询问版本差异或升级历史。

## 兼容入口退役节奏

统一入口先于物理合并发布，避免破坏既有工作流；但兼容入口不能永久扩大维护面。退役节奏如下：

- v0.8：把兼容入口标记为 deprecated，只在 `references/scripts.md` 保留兼容说明；新文档、场景路由和示例只指向统一入口。
- v0.9：把主路径测试迁移到统一入口；旧入口只保留轻量兼容 smoke，确保仍能转发或保持结果结构。
- v1.0：若连续两个小版本没有兼容入口专属需求，移除或内部化旧入口；保留用户可见统一入口和必要 library API。

当前受影响的兼容入口包括 acceptance 子工具、P0/P1/P2 分层 closure planner，以及 MaaS 旧命名 shim。删除前必须先确认 `references/script-audience-manifest.json`、`references/scripts.md`、测试和 release notes 都不再把它们当首选入口。
