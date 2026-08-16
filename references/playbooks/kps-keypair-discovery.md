# KPS Keypair Discovery Playbook

## 目标

在 ECS 创建或 SSH 登录场景里，先确认密钥对 discovery 路径。

## 适用场景

- 创建 ECS 前确认 keypair
- 用户要求复用现有 SSH keypair
- 用户想排查实例登录方式

## 当前能力边界

- 查询使用 `ListKeypairs` / `ListKeypairDetail`。
- 导入已有 OpenSSH 公钥使用 `huaweicloud.kps.import_keypair.v1`。
- 删除精确名称的密钥对使用 `huaweicloud.kps.delete_keypair.v1`。
- 当前 capability 不生成、导入、导出或回显私钥；需要 SSH 时，先在工作区生成本地密钥，
  再把 `.pub` 文件交给 import capability。

## 标准步骤

### 1. 上下文确认

```bash
python3 scripts/hcloud_context_inspect.py --pretty
```

### 2. KPS cache discovery

```bash
python3 scripts/hcloud_meta_lookup.py --service=KPS --allow-help-fallback --pretty
```

### 3. 在 ECS readiness 中回答的问题

- 是否已有可复用 keypair
- keypair 是不是在目标 region 内
- 用户是想走密码登录还是密钥登录

## 变更流程

1. 先查询是否已有可复用密钥对。
2. 需要新密钥时，在工作区生成私钥和 OpenSSH 公钥，私钥只留在工作区认证文件中。
3. 调用 import capability，只传 region、可选 project、名称和工作区相对 `.pub` 路径。
4. capability 返回 `verified` 结果后，才把该名称写入 ECS 创建请求。
5. 临时工作流完成后，先确认没有仍依赖该名称的实例，再调用 delete capability。

不要通过 `exec` 拼接 `CreateKeypair` / `NovaCreateKeypair`，也不要使用通用命令 proposal
替代已登记 capability。这样可以避免 hcloud 退出码为 0 但业务失败、同名异钥覆盖和未回读确认。
