# CHANGELOG

本文件记录 maibot-plugin-dev 技能本身的校对基线变化（不是 MaiBot 或 SDK 的 changelog）。
每次更新按「日期 + 校对基线」记一条：用户能感知的内容变化、新增/删除的文件、修正的错误。
机器可读基线（三个仓库的基点 SHA 与 Hook/能力名清单）在 `maintenance/baseline.json`。

## 2026-10-24：SDK 2.16.0 + MaiBot Host 1.3.15（基点 MaiBot `062d45cf` / SDK `835e0e9` / docs `5aa7365`）

增量校对，11 个文件定点改写，新增 3 个文件：

- **2.15.0**：新增第 19 个能力代理 `ctx.market`，只读查询插件市场：`search(query, *, category/page/limit/sort_by/compatible_only/include_manifest/include_stats/force_refresh)`、`get_detail(plugin_id)`、`get_readme(plugin_id, *, max_chars=8000/prefer_local/branch/force_refresh)`；三个能力需在 manifest `capabilities` 分别声明。
- **2.16.0**：新增 `ctx.maisaka.reply.generate(stream_id, reference, *, format_instruction="", model_name="", timeout_ms=None)`，生成符合麦麦人格的长文、结果交由插件自行发送；`ctx.maisaka.context.append()` 新增 `replyable` / `user_info` 仅关键字参数，用于保留真实作者与消息编号。
- Host 侧：能力注册表扩到 **81 个能力名**（新增 `market.search` / `market.get_detail` / `market.get_readme` / `maisaka.reply.generate`）；Hook 清单修正为 22 个——删掉了 3 个旧基线条目（`emoji.register.after_build_emotion`、`jargon.query.before_search`、`jargon.query.after_search`，当前源码全仓 grep 零命中，系上一版误收，文档中已改为「不存在、勿订阅」的警示行）；SDK 超出版本区间改为只 warning 放行，不再拒载。
- 收录事实补记：插件中心**收录审核不接受 `999.999.999` 上界**（实测拦截），锁已实测次版本线的写法同时是收录硬门槛。
- 新增 `references/plugin-testing.md`（插件测试流程：离线导入 → 本地实例 → 收录前自检）。
- 新增 `assets/plugin-template/.gitignore`（`config.toml` 运行时自动生成勿上传、`.env` 与密钥防泄漏）。
- `plugin-repo-submission.md` 新增「公开发布前安全检查」一节。
- 变更摘要从 SKILL.md 迁出至本文件，SKILL.md 只保留校对基线行。
- README 与 SKILL.md 的插件目录结构对齐官方「目录结构约定」（`webui.json` / `i18n/` / `assets/`），补记偏差：官方推荐的 `i18n/` 资源目录当前在 Host 无运行时加载点（`locales_path` 仅被插件市场元数据透传），实际生效的插件多语言是配置 UI 的 `__ui_i18n__` 机制。
- 收编官方 vibe-coding 页目录树里的 `tests/`（官方无内容说明、Host 不加载）：SKILL.md 目录结构加条目，plugin-testing.md 明确隔离导入 harness 放 `tests/` 配合 pytest 维护，并补上官方「测试建议」里的停用/卸载清理测试项。
- 模板移除 `config.toml` 示例文件：它是首次运行由 Runner 自动生成的运行时产物（官方目录约定不列、官方要求 `.gitignore` 排除 `/config.toml`），模板自带的 `.gitignore` 也忽略它——保留示例反而诱导作者提交。生成结构见 `references/plugin-config.md` 的对应示例。
- 补齐官方文档三个覆盖缺口（`hooks-and-components.md`，均与 SDK / Host 源码逐行核实）：**LLMProvider** 完整规范（Operation 三类请求/返回字段、`LLMProviderBase` 基类、卸载回退、排错）；**动态 API** 五方法与静态对比（register 后必须 `sync_dynamic_apis()` 才对 Host 生效、WebUI 页面只绑静态 API）；**网关消息归属**规则（顶层 `platform`/`account_id`/`scope` 须与网关声明逐字段一致，旧别名 `self_id` 等下版移除）。
- 吸收主要贡献者（SengokuCola）插件实战：**SDK 测试注入点** `set_plugin_config` / `_set_context(rpc_call=fake)`（官方文档未记载，实测通过）与 tests/ 工程化惯例进 `plugin-testing.md`；**模板自带可跑的测试脚手架**（`tests/conftest.py` 相对导入安全姿势 + 注入示例 + `pyproject.toml` pytest 配置，模板原样 pytest 2/2 通过）；`display.icon` 子字段规范；`locales_path` 空串校验；重依赖 worker 分层附录（标注"作者实践非 Host 机制"）。
- **plugin-testing.md 第 2 层（本地实例实测）六步在 1.3.15 实例全程实测走通**（模板插件当被测件）：放进 `plugins/` 即被扫描加载、配置表单渲染、WebUI 聊天室可直接 `/命令` 触发、启停开关就地翻转写 `[plugin].enabled`；修正一处文档失实——**EventHandler / HookHandler 的注册状态 WebUI 不展示**（详情页组件区只列 Tool / 旧版 Action / Command），Hook 订阅只能靠真实触发或日志验证。

## 2026-10-17：SDK 2.14.0 + MaiBot Host 1.3.9（基点 MaiBot `ac6ed61b` / SDK `e61ca95` / docs `32874ab`）

全量重写基线：14 个文件逐行对照源码复核，约 65 条事实修正，确定性门禁 19/19 通过。

- 确认 18 个能力代理、22→25 个 Hook 的规格（kwargs 逐字）、组件装饰器全集与废弃项。
- WebUI v2 扩展协议（`webui.json`）整页按源码重写，替换掉描述不存在协议的旧内容。
- 陷阱库重建：逐条复核旧陷阱在当前源码是否成立，新增事件类型发射点、配置重建等真实机制类陷阱。
- 仓库补充 LICENSE（CC BY-SA 4.0）与 README。
