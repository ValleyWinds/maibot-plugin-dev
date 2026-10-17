---
name: plugin-repo-submission
description: MaiBot 插件发布与收录参考：plugin-repo 收录流程、Release/Tag 规则、版本区间策略、README 写法、多版本安装与更新替换机制
---

# 插件发布与收录（plugin-repo）

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）
> 收录规则来源：官方社区插件索引仓库 [Mai-with-u/plugin-repo](https://github.com/Mai-with-u/plugin-repo)（`README.md` / `CONTRIBUTING.md` / `VERSIONING.md`，2026-10-17 核对）
> 与官方文档 `docs/zh/plugin/submission.md`；manifest 校验行为以 Host `src/plugin_runtime/runner/manifest_validator.py` 为准

插件本体留在各自的公开 GitHub 仓库，plugin-repo 维护三份索引：

| 索引文件 | 生成方式 | 作用 |
|----------|----------|------|
| `plugins.json` | 人工登记 | 插件身份与公开仓库地址的核心登记表 |
| `plugin_versions.json` | 同步工作流生成 | 逐版本索引（`schema_version: 1`），供客户端选兼容版本、固定 commit 安装与锁定更新（Release 安装的依据） |
| `plugin_details.json` | 同步工作流生成 | 各插件默认分支的**当前 manifest 与展示资源**，是**分支安装**的依据；WebUI 插件市场列表经 `catalog.py` 的 fetch-raw 接口读取它，Host 升级后的兼容性提醒（`update_compatibility_notice.py` 的 `_fetch_marketplace_plugins`）也用它当「插件市场清单」 |

插件展示页：https://plugins.maibot.chat/ 。提交完全免费、无需邀请。

## 1. 收录流程（Issue 驱动）

### 1.1 插件仓库必需文件（CI 校验前置）

| 文件 | 要求 |
|------|------|
| `_manifest.json` | 位于**仓库根目录**，`manifest_version` 为 `2`；只从 main / master / dev / develop 分支的根目录读取（注意：上游没有正面规定分支集合，这是从 `CONTRIBUTING.md` FAQ「无法获取 `_manifest.json`」列出的错误原因反推的） |
| `plugin.py` | 插件入口，含 `create_plugin()` 工厂函数 |
| `LICENSE` | 许可证类型必须与 manifest `license` 字段一致 |
| `README.md` | 建议含功能介绍、安装方式、配置说明、使用示例 |

`_manifest.json` 通过 `urls.repository` 字段定位，该字段必须是公开 HTTPS GitHub 地址、**不带 `.git` 后缀**；
仓库必须公开，私有仓库 CI 直接报「无法获取 _manifest.json」。

### 1.2 公开发布的硬门槛

- 新增或修改插件前，仓库必须有**至少一个已发布的 GitHub Release**：草稿不算、仅创建 Tag 不算，
  **预发布（Prerelease）可以**，GitHub 自动生成的源码包即可，无需上传附件。
- 历史上已登记但无可识别 Release 的老插件继续走分支安装；**新增 / 修改请求必须满足 Release 要求**。
- 移除请求不受 Release 要求限制。

### 1.3 提交步骤

1. 打开 plugin-repo 的 New Issue 页面，选 **「Add Plugin / 添加插件」** 模板，无需 Fork、无需本地 Git 操作。
2. 填写**插件 ID**（与 manifest `id` 一致）+ 完整公开 HTTPS 仓库地址（不带 `.git`）。
3. CI 自动读取仓库根目录 `_manifest.json` 校验，结果评论在 Issue 里。
4. 通过后维护者 `/approve` 批准，插件进入插件中心，WebUI 插件市场可搜到。

### 1.4 状态标签

| 标签 | 含义 |
|------|------|
| `pending-validation` | 等待自动验证 |
| `validated` | 验证通过，等待维护者批准 |
| `validation-failed` | 验证失败，按提示修复后评论 `/recheck` |
| `approved` | 已批准并加入插件中心 |
| `auto-approved` | **本批次**通过：每个插件新发现的合规版本组成一个 `plugin-release` 审核批次，整批全部通过 AI 审核后自动收录、标记本标签并关闭该 Issue（不是「历史所有 Release」） |
| `reviewing` | AI 审核中，完成后自动移除 |
| `needs-manual-review` | 有风险/不确定的 Release，等维护者人工裁决 |
| `plugin-release` | 已收录插件的发布版本审核 |
| `rejected` | 被维护者拒绝 |

### 1.5 Issue 命令

| 命令 | 权限 | 作用 |
|------|------|------|
| `/recheck` | 作者或维护者 | 重新验证并触发 AI 审核（**单独一条新评论**，内容仅命令） |
| `/mai_review`（`/mr`） | 仅维护者 | 重跑 AI 审核 |
| `/approve`（`/ap`） | 仅维护者 | 批准请求或待审 Release |
| `/ap 1.0.1 1.0.2` | 仅维护者 | 在 Release Issue 里批准指定版本 |
| `/reject <reason>` | 仅维护者 | 在 Release Issue 里**永久**拒绝剩余未收录版本（已收录的保留） |

> ⚠️ **AI 审核每个 Issue 上限 8 次**：初次、重审、已开始但失败的都计入（Issue 显示 `已审核：x次 / 8次`）。
> 达上限后 manifest 仍可验证，但不再 AI 审核。**提交前先在本地把 manifest / Release 对齐跑一遍，别浪费次数。**

## 2. Tag / version / id 一致性

### 2.1 逐版本对齐规则

| 项 | 规则 |
|----|------|
| Git Tag | 与 manifest `version` 完全一致，Tag 写 `1.4.2` 或 `v1.4.2` 均可，manifest 里必须是纯三段式 `1.4.2` |
| `version` | 严格三段式 `x.y.z`，正则 `^\d+\.\d+\.\d+$`（`manifest_validator.py` 的版本校验），**不带** `-rc1` / `+build` 后缀 |
| 预发布 | 用 GitHub 的 **Prerelease 标记**，不要改版本号格式 |
| 插件 `id` | 发布版本里不能变；改 ID 的版本判定「发布版本改变了插件 ID」直接驳回 |
| `manifest_version` | 固定 `2`（`SUPPORTED_MANIFEST_VERSIONS`） |
| Tag 指向的 commit | 必须能读到 `_manifest.json`；改写历史、删过 manifest 的 Tag 会被驳回 |

任何一条对不上，该版本进 `rejected_releases`，用户只能看到「有 N 个发布版本未通过校验」，装不了。

### 2.2 固定发布流程

改代码 → 更新 `_manifest.json` 的 `version` → 提交推送 → **同版本号打 Tag 推送** → 基于 Tag 建 Release
（需要时勾选 Prerelease）。三者版本号一致，索引一次同步即可收录。

### 2.3 Tag 一经收录不可变

同一版本**首次收录后，Tag 和 commit 不允许改动**；修复代码请发布**新版本号**，不要删除并重打同版本 Tag。

### 2.4 撤回（yanked）语义

- 删除已收录的 Release（或转回草稿）→ 该版本在索引里标记 **yanked**，**历史记录保留**，
  不参与 `recommended_version` 推荐，但版本记录仍可查。
- 维护者 `/reject <reason>` 会把剩余未收录版本按「插件 ID + 仓库 + 版本」写进 `blocked_release_versions.json`
  **永久拒绝**；新版本号不受影响，已收录版本保留。

## 3. 版本号策略

### 3.1 区间上下界怎么写

`host_application` 与 `sdk` 各为一个版本区间对象，`min_version` / `max_version` 均必填、都必须是严格三段式，
且 `min_version` 不能大于 `max_version`（`manifest_validator.py` 的 `ManifestVersionRange` 校验）。

- **两条线要分开写**：
  - `host_application.max_version` 写 `999.999.999`，只认真约束 `min_version`；不想约束下界就写 `0.0.0`。
    Host 侧有「同主次版本更高版本仅 warning」的容忍规则（见 §3.2），写高上界不会造成误放行后的静默故障。
  - `sdk` 区间锁在 2.x 线：`min_version` 按实际依赖的 SDK 写、**上界按 `2.99.99`**。
    官方内置插件 `src/plugins/built_in/plugin_management/_manifest.json` 实测即 `sdk.min_version: 2.0.0` /
    `sdk.max_version: 2.99.99`（上游 `CONTRIBUTING.md` 示例同为 `2.99.99`），其 `host_application.min_version`
    是 `1.0.0` 而非 `0.0.0`。原因：SDK 超区间**一律 error 拒载、没有容忍档**（见 §3.2），
    SDK 与 Host 独立发版、大版本换代意味着破坏性变更，上界必须锁在当前主版本线内；
    Host 有同主次版本容忍规则，因此上界可以放心写 `999.999.999`，SDK 不行。
- **为什么不要锁死小版本**：上界写成具体小版本（如 `1.1.99`）时，MaiBot 一升级（如到 `1.3.9`）插件就被版本校验挡住，
  用户看到的是「插件突然加载不了」。把「新版本还能不能跑」交给实际测试，不要交给版本号。
- `sdk.min_version` 要覆盖**目标环境实际运行的 SDK 版本**——SDK 与主程序独立发版，SDK 侧新能力可能领先 Host 实现，
  写新调用前先确认 Host 注册表里有该能力名（搜 `src/plugin_runtime/capabilities/registry.py`）。

### 3.2 区间校验的容忍规则（Host 侧）

- Host **高于** `max_version` 但**主次版本相同**（仅补丁号超出）→ warning，照常加载（`is_same_major_minor_higher_version`）。
- Host 其余情况超区间 → error，阻止加载。
- SDK 超区间 → **一律 error**，无容忍档。

> 排查用临时手段：`[debug] force_plugin_compatibility`（WebUI 调试配置里也有开关）跳过区间校验，超范围只 warning 不拒载；
> 需重启生效，只跳版本区间，能力白名单、依赖解析、`llm_providers` 一致性等校验照旧。别长期开。

### 3.3 预发布怎么标

manifest 的 `version` 保持纯三段式；预发布语义只由 GitHub Release 的 Prerelease 标记承载。
客户端推荐 `recommended_version` 时只取**兼容、未撤回、非预发布**中版本号最高者（数字比较，不看发布时间）；
显式安装请求可以选择兼容的预发布版本。

## 4. README 编写要求

README 面向**用户**写，不面向开发者写（AI 生成 README 最常犯的错就是写成开发文档）：

- **不写内部版本策略**：如「版本线接续上游避免混淆」这类只有维护者需要知道的信息。
- **不写 `config_version` 字段说明**：这是 schema 版本号，用户不该动也不需要懂。
- **不写 manifest 已承载的元信息**：分类、图标、能力声明、manifest 字段表——这些在 `_manifest.json` 里，
  README 里重复一遍只会和 manifest 漂移。
- **不写 SDK 安装步骤**：插件 SDK 由主程序自动提供给插件 Runner，用户装 SDK 毫无意义。
  **安装指引的正确主路径是「WebUI 插件市场一键安装」**，手动克隆到 `plugins/` 只作备选。
- 功能用用户视角描述（什么场景、有什么效果），**不要罗列 Tool / Command 组件名**。
- 文中指向仓库内文件的 Markdown 相对链接（如 `[GPL-3.0-or-later](LICENSE)`）在部分查看器里会被屏蔽渲染成
  `[blocked]`，关键信息（版本、协议）直接写纯文本，附件名用反引号。
- fork 插件的致谢节：上游仓库名可只写仓库部分（如 `self_identity_plugin`），但原作者署名和感谢必须保留。

## 5. 多版本安装机制与更新替换行为

`plugin_versions.json` 里每个插件条目带 `id`、`manifest_id`、`repositoryUrl`、`mode`（`releases` / `branch`）、`versions`，
以及决定用户可见状态的顶层字段 `sync_error`、`rejected_releases`，还有 `ignored_tags`——记录不符合版本规范的 Tag
（上游 `VERSIONING.md` 将三者并列；Host 侧解析结构 `releases.py` 的 `PluginReleaseEntry` **不解析** `ignored_tags`，字段声明里没有它）；
每条版本记录含 `version`、`tag`、解析后的 40 位 `commit` SHA（支持注解 Tag）、完整 manifest 快照、
`prerelease`、`published_at`、`release_url`、`release_notes`、`yanked`。

- **`sync_error`**：字符串，非空表示该插件整体同步失败（如仓库不可达、manifest 读不出）。客户端会把它的**所有**版本追加
  「版本同步失败」原因判为不兼容（`describe_entry`），安装请求直接 409 拒绝（`resolve_release`）；且带 `sync_error`
  的条目不参与 ID 别名登记。
- **`rejected_releases`**：记录各版本格式校验的失败原因（即 §2.1 所说的被驳回版本），用户在插件市场只会看到
  「有 N 个发布版本未通过校验」。
- Host 校验一致性：`versions` 或 `rejected_releases` 任一非空的条目，`mode` 必须是 `releases`，否则整个索引被判
  「版本索引安装模式不匹配」而加载失败（`load_release_index` / `parse_market_release_entry`）。

- **安装请求**：`plugin_id` + `repository_url` + `version` + `pinned`（上游语义，实现状态见下条）。
  `version: "latest"` 选最新的兼容稳定版；显式版本号可选旧版或兼容的预发布版；省略 `version` 走分支安装，
  装的是 `plugin_details.json` 登记的默认分支当前版本（索引 `mode: "branch"` 的插件只支持这条路径，
  指定版本号会被 `resolve_release` 拒绝：「该插件尚未发布 Release，只支持分支安装」）。
- **已通过 Release 安装的插件不能再走分支拉取更新**（安装记录在插件目录 `.maibot-release.json`，
  上游口径含实际版本、commit、仓库与锁定状态）。
- **`pinned` 锁定**（⚠️ 以下均为上游 `VERSIONING.md` 与官方 `plugin-lifecycle-api.md` 的口径，
  **Host 1.3.9 本地源码副本尚未实现**，不要拿它排查 1.3.9 的实际行为）：锁定版本不会被自动更新覆盖，
  也不会被降级或重装同版本；手动选择版本可在安装后改变锁定状态。
  源码实证缺口：`schemas.py` 的 `InstallPluginRequest` / `UpdatePluginRequest` 均无 `pinned` 参数；
  `release_install.py` 的 `replace_files` 写入的 `receipt_data` 只有 `plugin_id` / `version` / `tag` /
  `commit` / `repository_url` 五个字段、无锁定状态；全 `src/` 无 pinned 判断，
  `_install_release` 里唯一的自动更新拒绝是降级检查（目标版本 ≤ 当前版本时拒绝）。
- **更新替换流程**：客户端克隆指定 Tag 到临时目录 → 对候选目录跑安装校验 → 停插件 → 保留用户文件
  （`_preserve_user_files`：固定保留 `config.toml` / `config_back` / `data`，且对 Git 插件**还会把未跟踪与被忽略的文件一并复制进新版本**
  ——`git ls-files --others` 枚举，跳过 `.venv` / `venv` / `__pycache__` / `.pytest_cache` 等运行缓存与虚拟环境；
  上游 `VERSIONING.md` 同口径「Git 插件同时保留未跟踪及被忽略的文件，跳过虚拟环境和运行缓存」）
  → 旧目录备份到插件根目录 `.update_backups` → 换代码 → 恢复运行。目录替换失败会还原原目录；恢复运行失败报错
  （`release_install.py` 的 `_install_release` / `replace_and_reload`）。
- **安装硬失败校验**（任一不通过即中止安装、不改动现有目录，`release_install.py` 的 `_validate_candidate`）：
  1. 克隆目录 `git rev-parse HEAD` 与版本索引记录的 40 位 `commit` 不一致（Tag 被移动过）；
  2. 下载的 `_manifest.json` 与索引中的 manifest 快照**深度不相等**（不是只比版本字符串）；
  3. `ManifestValidator` 完整校验失败：manifest 字段合法性、入口 `plugin.py` 存在、Host / SDK 运行时版本区间、依赖声明；
  4. manifest 的 `id` 与索引条目的 `manifest_id` 不一致；
  5. **待安装插件（候选）自己声明的依赖不满足**：它要求的其他插件未安装、或已安装版本不符合声明的
     `version_spec`（`_validate_candidate` 把**候选 manifest** 与「扫描本地插件目录得到的 id→version 映射」传给
     `get_unsatisfied_plugin_dependencies`，遍历的是候选的 `plugin_dependencies`；Python 包侧的候选依赖校验由
     第 3 条的 `ManifestValidator` 全量校验承担，官方 `plugin-lifecycle-api.md` 同口径：「400 插件依赖不满足——该版本要求的其他插件或 Python 包缺失」）；
  6. 目录任意层级含符号链接 / 目录联接（`_check_tree`）；
  7. 本地改动过已跟踪代码、或新版本文件与保留的本地数据路径冲突（`_preserve_user_files`，`config.toml` 例外、保留本地）；
  8. 自动更新时目标版本 ≤ 当前版本，拒绝降级 / 重装同版本；安装记录 `.maibot-release.json` 损坏时在动文件前即报错（`read_release_receipt`）。
- **仅告警不阻断**：与上面第 5 条**方向相反**——第 5 条查「待安装插件依赖别人」，本条查「已安装插件依赖待安装插件」：
  其他已安装插件声明依赖本插件、而本次安装的版本不满足其约束时，只在安装成功的 `warnings` 里提醒
  「该插件可能无法运行」，不阻止切换（`_validate_candidate` 的 warnings 分支，逐条比对已安装插件 manifest 的
  `dependencies` 中指向本插件的 `type: plugin` 声明）。
- **降级只切代码、不回滚数据迁移**：数据格式兼容由插件作者自行保证。SDK 持久数据在主程序 `data/plugins`，代码替换不迁移。

## 6. 收录后的维护与归档

- 默认分支**至少 365 天无提交**、且仍在使用 Manifest v1 或 `0.1` 版本的活跃插件会被归档。
- 源仓库返回 404/410（无凭证重复两次）或转为私有 → 从活跃登记中移除，存档进 `archived_plugins.json`；
  超时、限流、权限错误、5xx、仅缺分支/manifest 只告警不摘除。
- 重新收录需要：恢复维护、升级到 Manifest v2、按贡献指南重新申请。

## 7. manifest v2 禁写旧字段

`categories`、`keywords`、`repository_url`、`homepage_url` 以及旧 manifest 的页面扩展字段等**不属于 manifest v2**。
Host 侧基类是 `extra="forbid"`，任何未声明字段都会让校验失败并报「存在未声明字段」。需要 WebUI 展示时用
`@HomeCard` 声明式卡片，或按当前版本的 `webui.json` 声明式页面协议（见 `references/webui-pages.md`）。

其余 manifest 字段级规则（`id` 正则、`author` / `urls` 必填项、`capabilities` 必填但可为空数组、
`plugin_type` / `dependencies` / `llm_providers` / `display.icon` / `changelog`）见 `references/sdk-api-reference.md`
与 `references/common-pitfalls.md`。

## 8. 收录前自检清单

- [ ] 公开 GitHub 仓库，根目录有 `_manifest.json`（`manifest_version: 2`）、`plugin.py`、`LICENSE`（类型与 `license` 一致）、`README.md`
- [ ] 至少一个已发布 Release（非草稿、非仅 Tag；预发布可），且其 Tag 与 manifest `version` 一致
- [ ] `id` 稳定唯一（形如 `github.username.my-plugin`），无空格、无路径字符；后续不再改
- [ ] 所有版本号三段式；`host_application` / `sdk` 上界未锁死小版本
- [ ] `author` 是 `{ name, url }`；`urls.repository` 是公开 HTTPS 地址、无 `.git` 后缀
- [ ] `capabilities` 只声明实际需要的能力，无能力时写空数组
- [ ] 未在真实 MaiBot 里验证过加载运行前，不要提 Issue（AI 审核次数有限）
- [ ] 若含 `webui.json`，已在本地 MaiBot 重载插件并打开页面验证

本地自检命令（仓库根目录）：

```bash
git describe --tags --abbrev=0
python -c "import json; print(json.load(open('_manifest.json'))['version'])"
```
