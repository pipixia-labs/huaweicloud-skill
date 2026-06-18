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
