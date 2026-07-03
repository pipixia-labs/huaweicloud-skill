# OBS Static Website Hosting Readiness

## 目标

面向官网、落地页、文档站、下载页和低成本静态站，把 OBS 静态网站托管从“桶存在”推进到“用户域名可访问、错误路径可解释、后续 CDN/DNS/证书可接入”的验收状态。

本 playbook 不把 OBS 默认域名访问当作完整上线。面向正式外部访问时，应优先使用自定义域名，并确认 DNS、备案、匿名访问和 HTTP 行为。

## 适用场景

- 用户要用 OBS 托管静态网站。
- 用户要把自定义域名绑定到 OBS 静态网站 endpoint。
- 用户遇到 OBS 网站访问 403、404、CNAME 或 endpoint 混用问题。
- 用户在 OBS 静态站、CDN、DNS、SCM 之间需要一条低成本上线链路。

## 必须先确认

| 项 | 说明 |
| --- | --- |
| region | OBS 桶创建后 region 不可变，必须提前确认。 |
| bucket name | 全局唯一；3-63 字符；小写字母、数字、`-`、`.`；不能像 IP；不能首尾为 `-` 或 `.`。 |
| custom domain | 正式上线建议必填；国内访问还要提醒备案状态。 |
| index document | 默认 `index.html`，必须确认对象已上传到正确路径。 |
| error document | 可选；没有时缺失路径通常表现为 404。 |
| public read boundary | 静态站需要匿名访问网站对象，但不能把管理权限或写权限公开。 |
| DNS ownership | 确认域名 DNS 是否在华为云 DNS，还是外部 DNS。 |

## hcloud / obsutil 边界

OBS 不走普通 OpenAPI-style `hcloud OBS <Operation>` 命令。默认按 `obs-boundary.md`：

- 只读：`scripts/hcloud_obs_readonly.py`
- 写类规划：`scripts/hcloud_obs_change_plan.py`
- 真实对象上传、桶属性、网站托管和自定义域名能力优先通过 `hcloud obs` / obsutil / 已验证 SDK 补充路径实现。

不要在未确认 obsutil 配置和 endpoint 前直接生成写命令。

## 推荐流程

1. 环境体检：

```bash
python3 scripts/hcloud_environment_doctor.py \
  --need hcloud \
  --need obsutil \
  --pretty
```

2. 查询 OBS 当前状态：

```bash
python3 scripts/hcloud_obs_readonly.py \
  --operation ListBuckets \
  --limit=20 \
  --pretty
```

3. 如果桶已存在，查询桶属性：

```bash
python3 scripts/hcloud_obs_readonly.py \
  --operation StatBucket \
  --bucket "<bucket_name>" \
  --pretty
```

4. 如果需要新建桶，只生成 planner：

```bash
python3 scripts/hcloud_obs_change_plan.py \
  CreateBucket \
  --bucket "<bucket_name>" \
  --region "<region>" \
  --pretty
```

5. 明确静态网站配置：
   - index document，例如 `index.html`
   - error document，例如 `error.html`
   - bucket website endpoint，而不是普通 OBS API endpoint
   - 自定义域名的 CNAME target

6. DNS 接入：
   - 如果 DNS 在华为云，按 `dns-zone-record-readiness.md` 规划 CNAME。
   - 如果 DNS 在外部，给用户输出 record type、host/name、target/value、TTL 和验证命令。
   - 不把“已提供 CNAME 值”说成“DNS 已生效”。

7. 验收：
   - 自定义域名解析到 OBS website endpoint。
   - 首页返回 HTTP 200 或合理的 3xx。
   - 缺失路径返回 404 或配置的 error document。
   - 关键 CSS/JS/图片路径不返回 403/404。
   - 如接入 CDN，分别验证源站直连和 CDN 域名。

## 403 / 404 排障

| 现象 | 常见原因 | 下一步 |
| --- | --- | --- |
| 403 | 对象未公开读、bucket policy 不允许匿名访问、访问了 API endpoint、AK/SK 权限不足 | 先确认是否匿名访问网站对象，再区分网站 endpoint 和 API endpoint。 |
| 404 | index document 名称不对、对象路径不对、上传目录多了一层、error document 未配置 | 查询对象路径，确认首页实际 key。 |
| CNAME 生效但打不开 | CNAME target 指向普通 OBS 域名或 DNS 未传播 | 用 `dig` / `nslookup` 查解析结果，确认 target 是 website endpoint。 |
| 默认域名可访问，自定义域名不可访问 | DNS 未配置、未在 OBS 绑定自定义域名、备案/证书边界未满足 | 分开验证 OBS 绑定和 DNS 解析。 |

## 安全和成本提示

- 不要建议 `public-read-write`。
- 不要把 AK/SK、token、`.obsutilconfig` 内容贴到对话中。
- 上传目录前先排除 `.env`、私钥、真实 `terraform.tfvars`、数据库 dump、证书私钥。
- 成本主要来自存储、请求、外网流量、CDN 流量和域名/证书相关费用。
- 静态站不需要 ECS、ELB、RDS，除非用户明确需要后端服务。

## 输出给用户时

至少说明：

- 为什么推荐 OBS 静态站，或为什么不适合。
- 还缺哪些事实：region、bucket、domain、DNS 归属、备案、index document。
- 下一步只读命令或 planner。
- 验收证据：DNS 解析、HTTP 状态、首页和缺失路径行为。
