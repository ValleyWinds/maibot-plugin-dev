---
name: maibot-plugin-dev
description: MaiBot 插件开发技能。在开发、调试、重构 MaiBot Plugin SDK 2.14.x 插件时使用此技能。涵盖 SDK 能力代理签名（18 种，已逐行核对源码）、组件装饰器规范、Hook 系统与真实 Hook 清单、配置模型、常见陷阱（Command 返回值解包、llm.generate 的 system_prompt/task_name、send 返回值与 return_details、Hook kwargs 结构、extra_prompt 归属、SDK 能力领先 Host 实现等），以及插件模板。适用于 ZCode 环境。
agent_created: true
---

# MaiBot 插件开发技能

## 概述

本技能提供 MaiBot Plugin SDK 插件开发的核心知识与最佳实践，基于真实插件开发中踩过的坑提炼而成。涵盖 SDK 能力代理签名、组件装饰器、Hook 系统、配置模型、常见陷阱和插件模板。入口文件只放规范要点与陷阱索引，细节一律在 `references/` 下展开。

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）
> 逐版本变更摘要（相对本文件上一版基线）：
> - **2.10.0**：新增 `@ReplyExtension` 回复扩展装饰器与 `ComponentType.REPLY_EXTENSION`，模型侧 `reply` 工具多出 `plugin_options` 参数。
> - **2.11.0**：新增第 18 个能力代理 `ctx.webui`，唯一方法 `claim_upload(upload_id)`。
> - **2.12.0**：新增 `ctx.maisaka.context.resolve_image(stream_id, source_id, index=0)`。
> - **2.13.0**：`@Tool` 新增仅关键字参数 `platforms`（平台作用域）。
> - **2.14.0**：`@ReplyExtension` 同样新增 `platforms`，Tool 与 ReplyExtension 共用平台名校验；Host 按当前聊天平台过滤回复扩展。
> - Host 侧：能力注册表扩到 **76 个能力名**；`chat.get_avatar` 已实现（不再触发「未注册的能力」）；旧的 manifest 页面扩展协议（v2 之前）已由 `webui.json` 声明式页面协议取代。
> 环境版本不同时，先核对 `maibot-plugin-sdk/pyproject.toml` 的 `version` 与主程序 `pyproject.toml`。

## 何时使用

- 开发新的 MaiBot 插件
- 调试或重构现有 MaiBot 插件
- 需要查阅 SDK 能力代理签名或组件规范
- 遇到 Command/Hook/Tool/LLM 相关问题时排查陷阱

## 官方文档

官方文档：https://docs.mai-mai.org/plugin/

> ⚠️ **文档不等于真相**。当前已知偏差（均为逐行核对源码时确认）：
> - **官方文档内部自相矛盾**：能力代理数量三处口径不一——官方文档 `index.md`（中英同错）与 SDK `README.md` / `docs/guide.md` 都写 17 种（漏 `ctx.webui`），只有 `api-reference.md` 写 18 种。装饰器数量同样矛盾：`index.md`（中英）写 9 种，SDK `docs/guide.md` 写 8 种并自称「对外推荐」、SDK `README.md` 写「7 种正式 + 1 种兼容」；而 `index.md` 的 9 种里其实含已废弃的 `@Action`。源码事实是 **18 个能力代理、9 个可用组件装饰器**（另有已废弃的 `Action` 与已移除的 `WorkflowStep`）。
> - **SDK `docs/guide.md` 落后于版本**：其能力代理清单与装饰器清单未跟上 2.10.0 的 `ReplyExtension` 与 2.11.0 的 `ctx.webui`。
> - **官方文档写错返回值语义**：`commands.md` 说 Command 三元组第三项是「命令优先级权重，数值越高优先级越高」——实际是拦截等级 `intercept_message_level`，非 0 即拦截消息（`result[0]` 反而被 Host 忽略）。`event-handlers.md` 教返回 `{"intercepted": True}` 拦截消息，该 key 运行时根本不认识，拦截不会生效；且 `ON_MESSAGE` 在主程序里已无发射点。
> - **官方文档指向不存在的页面**：`index.md` 的「插件接入」指向 `/develop/plugin`，仓库里没有该路径。
> - **遇到行为疑问，以 SDK / 主程序源码为准**，本技能已标注所有已知偏差。

关键页面：插件开发指南、Manifest 系统（`_manifest.json`）、生命周期、Hook 系统、组件（tools / commands / event-handlers / reply-extensions / home-cards / message-gateway / llmprovider）、配置管理。

## 核心开发规范

### 1. 插件基本结构

```
my-plugin/
├── _manifest.json       # 必需：插件清单
├── plugin.py            # 必需：插件入口，含 create_plugin()
├── config.py            # 可选：配置模型
├── config.toml          # 可选：用户配置
└── ...
```

`plugin.py` 必须包含：
- 继承 `MaiBotPlugin` 的插件类
- 声明 `config_model`（如使用配置）
- 实现三个生命周期方法——**缺一个 Runner 会拒绝加载**：
  - `async def on_load(self) -> None`
  - `async def on_unload(self) -> None`
  - `async def on_config_update(self, scope: str, config_data: dict, version: str) -> None`（**三个参数**）
- `create_plugin()` 工厂函数

`_manifest.json` 必填字段（缺任一都会注册失败）：
`manifest_version`(只支持 2) / `id`（须匹配 `^[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)+$`，至少两段） / `version`（严格三段式 X.Y.Z） / `name` / `description` / `license` / `author{name,url}` / `urls.repository` / `host_application{min_version,max_version}` / `sdk{min_version,max_version}` / **`capabilities`**（数组，无默认值，缺失即 Pydantic missing；可为空数组，不允许空字符串项） / `i18n{default_locale, supported_locales}`。

常用可选字段：
- `plugin_type`：缺省 `"extension"`，接受别名 `type`；唯一有语义的特殊值是 `"adapter"`（决定归 builtin 还是 third_party Supervisor）。
- `dependencies`：`{"type":"plugin", "id", "version_spec"}` 或 `{"type":"python_package", "name", "version_spec"}` 两种形态；不允许自依赖与重复依赖。
- `llm_providers`：每项必填 `client_type`；manifest 声明与代码 `@LLMProvider` 注册必须**双向一致**，不一致直接注册失败；两个插件声明同一 `client_type` 时**双方都被阻止加载**。
- `display.icon`（lucide / emoji / local）、`changelog`（URL 或插件目录内 `.md` 相对路径）。
- ⚠️ 基类是 `extra="forbid"`：任何未声明字段（`extensions`、`categories`、`keywords`、`repository_url` 等）都会让校验失败报「存在未声明字段」。

版本区间最佳实践（详见陷阱 16）：
- **`max_version` 写 `999.999.999`，只认真约束 `min_version`**——锁死小版本会导致 MaiBot 一升级插件就被挡。
- 容忍规则：Host 超上界但主次版本相同 → warning 照常加载；其余超范围 / SDK 超范围 → 拒载。
- 排查用临时手段：`[debug] force_plugin_compatibility` 开关跳过版本校验（需重启，其他校验照旧）。
- **发布 Release 时 Tag 必须与 manifest `version` 一致**，`id` 不能变，否则该版本被插件中心拒收。

### 2. 组件装饰器（从 maibot_sdk 导入）

| 装饰器 | 用途 | 关键参数 |
|--------|------|---------|
| `@Tool` | LLM 可调用的工具（**推荐**） | name, description, brief_description, detailed_description, parameters, platforms |
| `@Command` | 用户正则命令 | name（**不带斜杠**）, pattern, aliases |
| `@HookHandler` | 订阅命名 Hook | hook（必填）, name, mode, order, timeout_ms, error_policy |
| `@ReplyExtension` | 回复扩展（两阶段，SDK 2.10.0+） | name, parameters, platforms, priority, timeout_ms, chat_scope, allowed_session, enabled |
| `@API` | 插件间 API | name, description, version, public（**仅 public=True 可被跨插件调用**） |
| `@EventHandler` | 事件监听 | name, event_type, intercept_message, weight |
| `@HomeCard` | WebUI 首页卡片（2.7.0+） | name, title, content, width, order |
| `@MessageGateway` | 平台适配器 | route_type（send/receive/duplex 及别名 recv/recive）, name, platform, protocol |
| `@LLMProvider` | 自定义 LLM | client_type |
| ~~`@Action`~~ | **已废弃**，调用即发 `DeprecationWarning`，内部转 `@Tool` 注册 | 新插件别用 |
| ~~`@WorkflowStep`~~ | **已移除**，调用直接抛 `RuntimeError` | 改用 `@HookHandler` |

### 3. ctx 能力代理（18 种）

通过 `self.ctx.*` 访问，所有调用通过 RPC 转发到 Host：

`send` / `llm` / `config` / `db` / `message` / `person` / `emoji` / `frequency` / `component` /
`chat` / `knowledge` / `tool` / `api` / `gateway` / `render` / `maisaka` / `statistics` / **`webui`**

另有非能力代理对象：`ctx.paths`（`data_dir` / `runtime_dir`，SDK 2.6.0+）、`ctx.logger`（stdlib Logger）。

> **⚠️ 方法名易错**：这些代理的方法名以 SDK 源码为准，常见笔误是凭直觉猜名字。
> 例如 `ctx.render.html2png`（不是 `html_to_image`）、`ctx.knowledge.search(query, limit=...)`（不是 `top_k`）、
> `ctx.tool.get_definitions()`（不是 `list()`）、`ctx.emoji.get_random(count)`（不是 `random(stream_id)`）、
> `ctx.db.save(...)`（没有 `ctx.db.create/update`）、`ctx.maisaka.proactive.trigger(...)`（不是 `_trigger`）。
> **完整核对过的签名见 `references/sdk-api-reference.md`**。

日志统一走 `ctx.logger` 或 stdlib `logging`（自动转发到主进程）；旧版 `await ctx.logging.info()` 已移除。

> **⚠️ EventHandler 的现实**：SDK 的 `EventType` 枚举有 11 个值，但主程序源码里真正有发射点的只有
> `ON_START` 与 `ON_STOP`；`ON_MESSAGE` 的分发在主程序消息接收处已被整段注释（入站消息改由 Hook 承载），
> 其余 8 个值无发射点——注册了也不会被调用。插件要拦消息请用 `@HookHandler`。

### 4. 配置系统

```python
from maibot_sdk import PluginConfigBase, Field

class MyConfig(PluginConfigBase):
    __ui_label__ = "设置"          # WebUI 分组标题
    __ui_icon__ = "settings"       # Material Icons 图标名
    __ui_order__ = 0               # 分组顺序，越小越靠前
    enabled: bool = Field(default=True, description="开关")
```

- `self.config` 返回强类型实例（需声明 `config_model`）
- `self.get_plugin_config_data()` 返回原始 dict（始终可用）
- 配置来源为插件目录下的 `config.toml`
- **所有字段必须有默认值**（`default` 或 `default_factory`），否则默认配置生成/Schema 导出会失败；`list` / `dict` / 嵌套模型等可变类型用 `default_factory`
- **⚠️ 不要把配置字段放模型根级**：SDK 会把根级字段归入 WebUI 的 `general` 虚拟节，而前端按 `config[节名][字段名]` 取值，根级字段在配置表单里永远显示为空。**所有字段都放进命名 `PluginConfigBase` 子类节**（如 `infos_section: InfosSectionConfig`），对应 TOML 结构 `[infos_section]` / `[[infos_section.infos]]`
- **字段默认在 WebUI 显示英文字段名**：`label` 缺省取字段名，中文名要逐字段传 `json_schema_extra={"label": "启用插件"}`；嵌套列表项的字段 label 缺省取 `description`；纯技术字段（如 `config_version`）加 `"hidden": True`
- **配置类的 docstring 会作为节描述渲染给用户**：docstring 只写用户能懂的一句话，开发者的技术注释用 `#` 注释放字段上方
- 嵌套用嵌套 `PluginConfigBase` 类，每层可各自带 `__ui_label__` / `__ui_icon__` / `__ui_order__`
- `json_schema_extra` 传 UI 元数据：`label` / `hint` / `order` / `placeholder` / `group` / `disabled` / `hidden` / `i18n`
- 配置节多语言：`__ui_i18n__ = {"en_US": {"title": "Settings"}}`（结构是 `{locale: {key: text}}`）
- 支持 `list[Literal["a","b"]]` 生成多选配置
- **`[plugin]` 节必须含 `config_version`**，缺失时插件只加载配置管理、业务被暂停（见陷阱 12）

### 5. 配置热重载订阅

```python
from typing import ClassVar, Iterable

class MyPlugin(MaiBotPlugin):
    config_reload_subscriptions: ClassVar[Iterable[str]] = ("bot", "model")
```

- `("bot",)` — 订阅主程序 bot 配置变更（如人格配置）
- `("model",)` — 订阅模型配置变更
- **不声明则收不到对应 scope 的 on_config_update 回调**

## 关键陷阱速查（必读）

以下陷阱均来自真实开发，一行摘要 + 指向 `references/common-pitfalls.md`：

### P0 — 致命陷阱

1. **Command 必须返回三元组** `(success, response, intercept_message_level)`：`intercept` 非 0 才拦截消息（任意 truthy 都算），**`result[0]` 被 Host 彻底忽略**；返回单字符串/2 元组会掉进 else 分支且 intercept 恒为 0。Command 必须自己调 `ctx.send.text()` 发送回复。
2. **llm.generate 的 system_prompt 被 Host 忽略**：SDK 签名里没有该参数，会被 `**kwargs` 吞掉；system prompt 走消息列表 `[{"role":"system",...}]`，指定任务/模型用 `task_name=` / `model_name=`。
3. **send.* 返回 bool**（不是 dict）：7 个 `send.*` 方法全在 `_BOOLEAN_SUCCESS_CAPABILITIES` 中；需要平台消息 ID 时传 `return_details=True` 得 `{"success","sent","message_id"}`。
4. **Hook kwargs 是嵌套结构**：`chat.receive.before_process` 的 kwargs 只有 `message`（SessionMessage 序列化字典），user_id 嵌套在 `message_info.user_info.user_id`，不要从顶层取。
5. **`maisaka.planner.*` 两个 Hook 只认 `items` / `output_items`**：写 `messages` / `response` 不报错但被忽略，插件「能加载但功能静默失效」；回带时 `item_schema_version` 必须原样不动。

### P1 — 严重陷阱

6. **Hook 返回值规范**：BLOCKING 模式返回 `{"action":"continue","modified_kwargs":kwargs}` 或 `{"action":"abort"}`，只认 continue/abort；OBSERVE 模式返回值被忽略；`modified_kwargs` 是**整体替换**不是逐键合并。
7. **自建 data 目录改用 `ctx.paths`**：`str(self.ctx.paths.data_dir)` / `str(self.ctx.paths.runtime_dir)`（SDK 2.6.0+）；模板文件等源码资源仍用 `__file__` 定位。
8. **manifest capabilities 必须逐条声明**：`capabilities` 是必填字段且逐字面授权，漏声明 = 运行时该调用被拒；HookHandler 不需要声明；`ctx.gateway` 无法声明（走裸方法白名单）；写未知能力名不会拒载但调用必失败。
9. **`extra_prompt` 只在 `maisaka.replyer.before_request`**：planner 链没有该字段；多插件共存应追加而非覆盖；该 Hook 的 kwargs 现为 12 个键（session_id、request_type、task_name、model_name、extra_prompt、attempt、retry_count、max_retries、reply_message_id、reply_reason、selected_expression_ids、reply_tool_args）。
10. **EventHandler 想拦截必须返回规范 dict**：`return True, True, "...", None, None` 与 `{"intercepted": True}` 都不会拦截；生效写法是 `{"continue_processing": False, "modified_message": ...}` 或 `{"blocked": True}`；但注意只有 ON_START / ON_STOP 真会被触发。

### P2 — 注意事项

11. **proactive.trigger 调用方式**：`await ctx.maisaka.proactive.trigger(stream_id, intent, reason="")` 或快捷方法 `ctx.maisaka.trigger_proactive(...)`。
12. **config.get 读取主程序配置**：`await ctx.config.get("personality.personality", "")`，异步，key 支持点分割路径。
13. **manifest 版本上界写 `999.999.999`；Release Tag = manifest version**：锁死小版本上界会被版本校验挡住；Tag 与 version 不一致 / id 变动 → Release 被插件中心拒收。
14. **SDK 新能力可能领先 Host 实现**：`chat.get_avatar` 现已由 Host 实现（1.3.9 注册表在册），但机理仍成立——SDK 与 Host 独立发版，能力名不在注册表时调用才失败；怀疑时 grep 主程序 `src/plugin_runtime/` 确认。
15. **Host 侧硬限制**：`component.update_plugin_config` 仅内置插件管理可用、`component.unload_plugin` 恒失败（改用 reload）、`component.enable/disable` 仅支持全局 scope、`database.query` 只支持 5 种 query_type、`api.call` 禁跨插件调未公开 API、未注册的 Hook 名会让组件注册直接失败。

## 参考文件

- `references/sdk-api-reference.md` — **18 种能力代理 + paths/logger 的完整方法签名（逐行核对 SDK 2.14.0）**
- `references/common-pitfalls.md` — 常见陷阱的详解和修复方案；另附附录：planner items/output_items 协议、`@Command` 的 aliases 匹配语义、删除配置字段与 config_version 重建语义、插件发布与收录规则
- `references/hooks-and-components.md` — Hook 系统清单（22 个 Hook 的真实 kwargs）+ 全部组件装饰器
- `references/reply-extensions.md` — `@ReplyExtension` 回复扩展：两阶段协议、消息组格式、失败语义、平台作用域
- `references/webui-pages.md` — `webui.json` 声明式 WebUI 页面协议（当前版本的一等公民，已按 Host 1.3.9 重写）
- `references/isolated-import-testing.md` — 脱离宿主导入 plugin.py 做纯函数验证的 stub harness 套路（review / 排障陌生插件时用）
- `assets/plugin-template/` — 插件模板文件（plugin.py / config.py / _manifest.json / config.toml）

## 语言环境

本技能在 **ZCode** 中使用：技能文件位于 `~/.zcode/skills/maibot-plugin-dev/`，被 ZCode 的技能机制自动发现。`references/` 下所有文件均为纯 Markdown，可直接作为上下文提供给会话；`assets/plugin-template/` 可直接复制到新插件项目作为起点。本地核对源码时 SDK 仓库在 `maibot-plugin-sdk/`、主程序源码在 `src/plugin_runtime/`。

## 开发流程建议

1. **查阅官方文档** — https://docs.mai-mai.org/plugin/
2. **对照 SDK 源码验证签名** — SDK 通常在 `maibot-plugin-sdk/maibot_sdk/` 目录
3. **对照主程序源码验证行为** — Host 端能力实现在 `src/plugin_runtime/capabilities/`
4. **先写 _manifest.json** — 确定能力声明和版本兼容
5. **实现生命周期方法** — on_load/on_unload/on_config_update
6. **添加组件** — Tool/Command/HookHandler/API/ReplyExtension
7. **配置模型** — PluginConfigBase + Field + WebUI i18n
8. **测试** — mock ctx 对象做单元测试，不依赖真实 Host
9. **审查第三方插件 / 复现纯函数 bug** — 用 stub harness 单独导入 `plugin.py`，见 `references/isolated-import-testing.md`
10. **热加载**：插件支持热加载，代码更新后在 WebUI「插件管理」重新加载即可，**一般无需重启 MaiBot**；写安装/调试指引时不要让用户重启（`[debug] force_plugin_compatibility` 等少数开关除外）
