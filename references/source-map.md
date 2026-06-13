# Huawei CLI Skill Source Map

本文件说明 `huaweicloud-skill` 在构建和维护时，应该如何使用 `materials/` 下的原始资料。

## 资料分层

默认使用顺序：

1. `references/`
2. `materials/hcloud-docs-md/`
3. 已安装的 `huaweicloudsdk*` package
4. `reference-projects/huaweicloud-sdk-python-v3` 维护期源码参考

解释：

- `references/`
  - 是清洗后的技能资料。
  - 只保留当前 skill 真的需要的规则、流程、例子和约束。
- `materials/hcloud-docs-md/`
  - 是主要阅读源。
  - 适合 `rg`、摘取命令示例、整理章节内容。
- 已安装的 `huaweicloudsdk*` package
  - 是 SDK 补充能力的运行时来源。
  - 只用于参数、region/endpoint、错误结构和 allowlist 内只读 runner。
- `reference-projects/huaweicloud-sdk-python-v3`
  - 是本仓库维护和测试参考。
  - 用户机器不要求存在该源码目录。

## 当前原始文档用途

### 用户指南

- 主用途：
  - 配置项
  - 选项说明
  - `--cli-jsonInput`
  - `--cli-output`
  - `--cli-query`
  - `--cli-waiter`
- 主要来源：
  - `materials/hcloud-docs-md/华为云命令行工具服务 KooCLI 用户指南_md_dollar/output.md`

### 常见问题

- 主用途：
  - 认证优先级
  - 缓存位置
  - 日志位置
  - 网络超时
  - 不支持的服务或 operation
  - 空响应体判断
  - 区域参数问题
- 主要来源：
  - `materials/hcloud-docs-md/华为云命令行工具服务 KooCLI 常见问题_md_dollar/output.md`

### 快速入门

- 主用途：
  - 安装方式
  - 初始化配置
  - 新用户的最短上手路径
- 主要来源：
  - `materials/hcloud-docs-md/华为云命令行工具服务 KooCLI 快速入门_md_dollar/output.md`

## 原始资料的已知问题

- 目录页噪声较多
- 页码残留
- 命令换行被打断
- `说明` / `注意` 等块可能被转成异常字符
- 图片类示例会变成图片占位，而不是文本

因此：

- skill 运行时优先看 `references/`
- 只有在 `references/` 没覆盖时，才回到 `materials/`
- 回到 `materials/` 时，使用保留的 `hcloud-docs-md/`
- 回到 SDK 时，优先使用已安装 package；源码目录只做维护期 fallback
