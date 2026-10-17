# MaiBot 插件开发常见陷阱

> 基于本地源码（MaiBot 主程序 + maibot-plugin-sdk）逐行核对，只收录「看起来能跑但静默失效」的坑
> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）

---

## P0 — 致命陷阱（功能完全不工作）

### 陷阱 1：Command 返回值不是三元组，且 `result[0]` 被 Host 彻底忽略

**现象**：Command 执行了但消息继续走 AI（Maisaka），AI 自己又处理了一遍；返回的字符串没有发给用户。

**根因**（`src/plugin_runtime/component_query.py` `_build_command_executor`）：
- 返回值是 `list`/`tuple` 且 `len >= 3`：`response_text = str(result[1])`、`intercept = bool(result[2])`
- 否则走 else 分支：`response_text = str(整个 result)`，`intercept` 保持 metadata 默认 `0`
- `success` 取自 RPC 回包 `payload["success"]`（Runner 侧固定 `True`，只表示"调用没抛异常"），**`result[0]` 从未被读取**
- 消费方 `src/chat/message_receive/bot.py` `_process_commands`：`continue_process = not bool(intercept_message_level)`

**两条易踩语义**：
- **别把业务成败放在第一位**。`return (False, "参数错误", 1)` 会被当成**成功 + 拦截**——第一位被忽略，第二位进日志，第二位才是用户可见文本的载体（发送要靠 `ctx.send.*`）。
- **非 3 元组掉进 else 分支**：`return "你好"` → 日志记 `你好`；`return (True, "x")` → 日志记 `(True, 'x')`，且 intercept 恒为默认 0（消息继续走 AI）。

**错误写法**：
```python
@Command(name="hello", pattern=r"^/hello\b")
async def handle_hello(self, **kwargs):
    return "你好！"  # ❌ intercept=0，消息继续走 AI；用户收不到
```

**正确写法**：
```python
@Command(name="hello", pattern=r"^/hello\b")
async def handle_hello(self, **kwargs):
    stream_id = kwargs["stream_id"]
    await self.ctx.send.text(text="你好！", stream_id=stream_id)  # ✅ 主动发送
    return True, "已发送", 2  # ✅ 三元组，intercept=2 拦截 AI
```

> **Command 的 `name` 不带前导斜杠**（`@Command("hello", pattern=r"^/hello")`，SDK `components.py` `Command` 装饰器 docstring 即此写法），`pattern` 和 `aliases` 才带 `/`。两处真实代价（均已实测）：① `name="/hello"` 会被「配置 → 命令权限」页**再加一次** `/` 前缀显示成 `//hello`——前端 `dashboard/src/routes/config/bot/CommandPermissions.tsx` 用 `/{command.name}` 渲染，斜杠是 JSX 裸文本，grep `'/'` 字符串字面量搜不到；② `name` 会拼进权限路径 `plugin_id.command_name`（`bot.py` 的 `has_command_permission(f"{plugin_name}.{command_name}", ...)`），带斜杠得到 `plugin_id./hello` 这种带 `./` 的键，命令注册表里的 `id` 同样如此（实测 `probe.slash-name./probe_slash`）。注意 Host 的**匹配**只看 `pattern`/`aliases`，带斜杠照样能触发——坏的是标识符与界面呈现，不是触发。

**验证来源**：SDK `maibot_sdk/components.py` `Command`；主程序 `src/plugin_runtime/component_query.py` `_build_command_executor`；`src/chat/message_receive/bot.py` `_process_commands`

---

### 陷阱 2：llm.generate 的 `system_prompt` 被 Host 完全忽略

**现象**：传了 `system_prompt="你是温柔恋人"` 但 LLM 回复完全不带恋人语气。

**根因**（`src/plugin_runtime/capabilities/core.py` `_cap_llm_generate`）：只从 args 读
`prompt` / `task_name` / `model` / `model_name` / `temperature` / `max_tokens` 构造 `LLMServiceRequest`，
**全文没有 `system_prompt`**。SDK `context.py` 也没有为该能力注入 system prompt——透传的额外参数在 Host 侧被静默丢弃。

**错误写法**：
```python
result = await ctx.llm.generate(
    prompt="你好",
    system_prompt="你是温柔恋人",  # ❌ Host 端不读这个参数
)
```

**正确写法**：
```python
result = await ctx.llm.generate(
    prompt=[
        {"role": "system", "content": "你是温柔恋人"},  # ✅ 消息列表格式
        {"role": "user", "content": "你好"},
    ],
)
```

**验证来源**：主程序 `src/plugin_runtime/capabilities/core.py` `_cap_llm_generate` / `_normalize_prompt_arg`

---

### 陷阱 3：`send.*` 返回 `bool`，不是 dict

**现象**：`if result.get("success"):` 直接 `AttributeError`，或写成 `if isinstance(result, dict) and ...` 后永远走失败分支。

**根因**：
- SDK `context.py` 的 `_BOOLEAN_SUCCESS_CAPABILITIES` 含 `frequency.set_adjust` + 7 个 `send.*`
  （`send.text` / `emoji` / `image` / `forward` / `hybrid` / `command` / `custom`），命中时 SDK 返回 `bool(result["success"])`
- Host 侧 `src/plugin_runtime/capabilities/core.py` `_build_send_result` 默认只回 `{"success": sent}`，
  仅当 `args["return_details"]` 为真时才补 `sent` / `message_id`

**错误写法**：
```python
result = await ctx.send.text(text="你好", stream_id=sid)
if isinstance(result, dict) and result.get("success"):  # ❌ result 是 bool
    ...
```

**正确写法**：
```python
result = await ctx.send.text(text="你好", stream_id=sid)
if result:  # ✅ result 是 True/False
    ...
```

**需要平台消息 ID 时用 `return_details=True`**（7 个 send 方法都支持）：
```python
result = await ctx.send.text("你好", stream_id, return_details=True)
# {"sent": bool, "message_id": str | None}
if result["sent"] and result["message_id"]:
    platform_msg_id = result["message_id"]   # 适配器回传的 platform_message_id
```

**验证来源**：SDK `maibot_sdk/context.py`（`_BOOLEAN_SUCCESS_CAPABILITIES` / `_DETAILED_SEND_CAPABILITIES`）；
主程序 `src/plugin_runtime/capabilities/core.py` `_build_send_result`

---

### 陷阱 4：Hook kwargs 是嵌套结构，顶层没有 user_id

**现象**：`chat.receive.before_process` Hook 中从 kwargs 顶层取 `user_id` / `raw_message`，取不到值，拦截逻辑完全失效。

**根因**（`src/chat/message_receive/bot.py` `_invoke_message_hook`）：调用的是
`invoke_hook(hook_name, message=serialize_session_message(message), **kwargs)`。
该 Hook 的 HookSpec `required` 只有 `["message"]`，`user_id` 嵌套在序列化 message 的
`message_info.user_info.user_id` 里。命令链的 `chat.command.before_execute` 才会在顶层多带
`command_name` / `plugin_id` / `matched_groups`。

**错误写法**：
```python
@HookHandler("chat.receive.before_process", mode=HookMode.BLOCKING)
async def on_message(self, **kwargs):
    user_id = kwargs.get("user_id", "")        # ❌ 顶层没有 user_id
    raw_message = kwargs.get("raw_message", "")  # ❌ 顶层没有 raw_message
```

**正确写法**：
```python
@HookHandler("chat.receive.before_process", mode=HookMode.BLOCKING)
async def on_message(self, **kwargs):
    msg = kwargs.get("message", {})           # ✅ 从 message 字典取
    msg_info = msg.get("message_info") or {}
    user_info = msg_info.get("user_info") or {}
    user_id = str(user_info.get("user_id") or msg.get("user_id") or "")

    raw_text = msg.get("processed_plain_text") or ""
    if not raw_text:
        raw_msg = msg.get("raw_message")
        if isinstance(raw_msg, list):
            parts = [seg.get("data", "") for seg in raw_msg
                     if isinstance(seg, dict) and seg.get("type") == "text"]
            raw_text = "".join(parts)
```

> `raw_message` 是组件 dict 列表（`[{"type": "text", "data": "..."}]`，见 `src/plugin_runtime/host/message_utils.py`
> `_component_to_dict`），**不是**带 `components` 键的字典；TextComponent 的文本字段是 `data`，不是 `text`。
> 必须按 `type == "text"` 过滤——image/emoji 的 `data` 是资源地址、file/at/reply/forward 的 `data` 是结构化数据，
> 不过滤会把图片 URL 当正文参与匹配（见附录 1）。

**验证来源**：主程序 `src/chat/message_receive/bot.py` `_invoke_message_hook` / `register_chat_hook_specs`；
`src/plugin_runtime/host/message_utils.py` `_component_to_dict`

---

## P1 — 严重陷阱

### 陷阱 5：Hook 返回值只认 `continue` / `abort`，未知 action 静默回落

**现象**：返回 `{"handled": True}` 后行为未定义，Hook 没拦截，也没有任何报错。

**Host 侧真实判定**（`src/plugin_runtime/host/hook_dispatcher.py` `_normalize_action`）：
`str(raw).strip().lower()` 后不在 `{"continue", "abort"}` 就打 warning 并**回落成 `continue`**。
Runner 侧 `runner_main.py` 的 `_handle_hook_invoke` 做同样的归一化。

**正确规范**：
- BLOCKING 模式：
  - 放行：返回 `None` 或 `{"action": "continue"}`
  - 放行并改参：返回 `{"action": "continue", "modified_kwargs": kwargs}`
  - 中止调用链：返回 `{"action": "abort"}`
- OBSERVE 模式：返回值被忽略
- BLOCKING handler 返回值还可携带 `custom_result` 与 `error_message`；同时返回 `abort` 时以 abort 为准

**`modified_kwargs` 是整体替换不是逐键 merge**（`dispatch_result.kwargs = dict(execution_result.modified_kwargs)`）：
多插件链式修改时，必须把其余键原样带回，否则会丢参数。`modified_kwargs` 不是 dict 时打 warning 后忽略
（`_extract_modified_kwargs`）。

**三种"注册时不报错、调用时静默失效"的组合**（`_merge_blocking_result`）：
- `HookSpec.allow_blocking=False` 时 BLOCKING handler 被跳过并记 error
- `allow_kwargs_mutation=False` 时 `modified_kwargs` 被忽略并记 error
- `allow_abort=False` 时 abort 请求被忽略并记 error

> 反过来，注册阶段是**硬失败**：Hook 名未注册、或 HookSpec 不允许却声明了 blocking / observe /
> `error_policy=abort`，都会抛 `ComponentRegistrationError` 导致插件注册失败（`host/component_registry.py`）。
> 所以「Hook 名拼错」是显式报错，「mode / 返回值写错」才是静默失效。

**验证来源**：主程序 `src/plugin_runtime/host/hook_dispatcher.py` `_normalize_action` / `_merge_blocking_result` /
`_extract_modified_kwargs`；`src/plugin_runtime/host/component_registry.py` HookSpec 注册校验

---

### 陷阱 6：自建 data 目录存放运行时数据

**现象**：插件在源码目录下自建 `data/` 子目录存放运行时数据，框架不认，热更新/迁移时数据丢失。

**根因**：SDK 早期版本没有目录属性，插件只能用 `os.path.dirname(os.path.abspath(__file__))` 自建目录。
SDK 现在提供 `PluginPaths` dataclass（`data_dir` / `runtime_dir`），由 Runner 按插件 ID 分配。

**正确写法**：
```python
# 持久化数据目录（data/plugins/<plugin_id>/）
data_dir = str(self.ctx.paths.data_dir)

# 临时数据目录（temp/plugins/<plugin_id>/）
runtime_dir = str(self.ctx.paths.runtime_dir)
```

**注意**：
- `ctx.paths.data_dir` 返回 `pathlib.Path`，需 `str()` 转换传给期望 `str` 的代码
- 模板文件等源码自带资源仍用 `os.path.dirname(os.path.abspath(__file__))` 定位（它们在插件源码目录，不在 data_dir）
- 迁移旧数据时从旧 `<plugin>/data/` 复制到新 `ctx.paths.data_dir`

**验证来源**：SDK `maibot_sdk/context.py` `PluginPaths` / `PluginContext.paths`

---

### 陷阱 7：capabilities 漏声明 = 静默失能；写未知名 = 不拒载但调用必失败

**现象 A**：插件"加载成功但功能是摆设"——`send.text` 发送失败、`llm.generate` 报"生成失败"、
`get_available_models` 静默跳过。

**根因**（`src/plugin_runtime/host/authorization.py` `check_capability`）：能力授权是**逐字面比对**，
未声明即返回「插件 {id} 未获授权能力: {capability}」。调用链先过授权再过注册表，所以漏声明死在授权。

**规则**：
- **`capabilities` 是 manifest 必填字段**（`manifest_validator.py` 中 `capabilities: List[str]` 无默认值）
- **能力名与代码调用必须一一对应**：调 `ctx.send.text` 就声明 `send.text`，调 `ctx.llm.get_available_models` 就声明 `llm.get_available_models`
- HookHandler 不需要在 capabilities 声明；`ctx.gateway` 走裸方法白名单，无对应能力名
- 唯一例外：`api.replace_dynamic` 在 `_ALWAYS_ALLOWED_CAPABILITIES` 白名单里，未声明也放行

**现象 B — manifest 写了不存在的能力名**：**不会拒载**。
`manifest_validator.py` 的 `_validate_capabilities` 只校验非空与去重，**不校验名字是否真实注册**。
授权能过，死在运行时调用：`host/capability_service.py` 查注册表失败即返回
`E_METHOD_NOT_ALLOWED`「未注册的能力: {capability}」。

> 能力名是逐项点号分层的（`send.text` / `llm.generate` 等），**没有 `send_message` 这种聚合名**。
> 官方文档 `docs/zh/plugin/manifest.md` 的示例现已改为具体能力名（`send.text` / `send.emoji` / `config.get`）。

**能力名以主程序源码为准**（`src/plugin_runtime/capabilities/registry.py`，当前 76 项）：
- `send.text` / `send.emoji` / `send.image` / `send.forward` / `send.hybrid` / `send.command` / `send.custom`
- `llm.generate` / `llm.generate_with_tools` / `llm.embed` / `llm.transcribe_audio` / `llm.get_available_models`
- `config.get` / `config.get_plugin` / `config.get_all`
- `database.query` / `database.save` / `database.get` / `database.delete` / `database.count`
- `chat.get_all_streams` / `chat.get_avatar` / `chat.get_group_streams` / `chat.get_private_streams` /
  `chat.open_session` / `chat.get_stream_by_group_id` / `chat.get_stream_by_user_id`
- `message.get_by_time` / `message.get_by_time_in_chat` / `message.get_by_id` / `message.get_recent` /
  `message.count_new` / `message.build_readable`
- `maisaka.context.append` / `maisaka.context.resolve_image` / `maisaka.proactive.trigger`
- `person.get_id` / `person.get_value` / `person.get_id_by_name`
- `emoji.get_random` / `emoji.get_by_description` / `emoji.register` / `emoji.delete` / `emoji.get_info` /
  `emoji.get_emotions` / `emoji.get_all` / `emoji.get_count`
- `frequency.get_current_talk_value` / `frequency.set_adjust` / `frequency.get_adjust`
- `component.*`（11 个）/ `api.call` / `api.get` / `api.list` / `api.replace_dynamic` /
  `knowledge.search` / `render.html2png` / `tool.get_definitions`
- `statistics.local.*`（7 个方法，见 `references/sdk-api-reference.md`）
- `webui.claim_upload`（唯一单独注册的 webui 能力，需 manifest 显式声明）

**验证来源**：主程序 `src/plugin_runtime/host/authorization.py`、`host/capability_service.py`、
`src/plugin_runtime/runner/manifest_validator.py` `_validate_capabilities`、
`src/plugin_runtime/capabilities/registry.py`

---

### 陷阱 8：`extra_prompt` 只在 replyer 链；`modified_kwargs` 是整体替换

**现象 A — Hook 选错**：在 `maisaka.planner.before_request` 里给 `kwargs["extra_prompt"]` 赋值，毫无效果。

**根因**：`extra_prompt` **不存在于 planner 链**。planner 的 `before_request` required 只有 7 个键：
`items` / `item_schema_version` / `tool_definitions` / `selected_history_count` /
`built_message_count` / `selection_reason` / `session_id`。
`extra_prompt` 只存在于 **`maisaka.replyer.before_request`**（12 个 required 键），Host 会把它包成
`【额外回复要求】\n{...}` 附加到回复请求里（`src/chat/replyer/maisaka_generator_base.py` `_build_reply_requirements`）。

`maisaka.replyer.before_request` 的 12 个 required 键：
`session_id` / `request_type` / `task_name` / `model_name` / `extra_prompt` / `attempt` /
`retry_count` / `max_retries` / `reply_message_id` / `reply_reason` / `selected_expression_ids` /
`reply_tool_args`。

```python
# ✅ 要影响回复内容，用 replyer 链
@HookHandler("maisaka.replyer.before_request", mode=HookMode.BLOCKING)
async def inject(self, **kwargs):
    kwargs["extra_prompt"] = (kwargs.get("extra_prompt") or "") + " 麦麦正在晒太阳"
    return {"action": "continue", "modified_kwargs": kwargs}
```

**现象 B — 以为 modified_kwargs 是逐键合并**：Host 是 **`dict(modified_kwargs)` 整体替换**当前 kwargs
（`host/hook_dispatcher.py` `_merge_blocking_result`），**不是逐键 merge**。多个 blocking handler 依次执行时，
后者收到的是前者返回的**整份 dict**。所以改了 `extra_prompt` 就必须把其它键原样带回去；对同一个键而言是
「最后写入者生效」，多插件共存时仍应做**追加**而不是覆盖。

**验证来源**：主程序 `src/maisaka/chat_loop_service.py` `register_maisaka_hook_specs`；
`src/chat/replyer/maisaka_generator_base.py` `_build_reply_requirements`；
`src/plugin_runtime/host/hook_dispatcher.py` `_merge_blocking_result`

---

## P2 — 注意事项

### 陷阱 9：proactive.trigger 方法名写错

**错误**：`ctx.maisaka.proactive_trigger(...)` — 方法名不对

**正确**（SDK `maibot_sdk/capabilities/maisaka.py`）：
- `ctx.maisaka.proactive.trigger(stream_id, intent, *, reason="", priority="", metadata=None, **kwargs)`
- 便捷入口：`ctx.maisaka.trigger_proactive(stream_id, intent, **kwargs)`
- 另有 `ctx.maisaka.append_context(stream_id, segments, **kwargs)` 与 `ctx.maisaka.context.append(...)`

Host 侧注册的能力名是 `maisaka.proactive.trigger`（`capabilities/registry.py`）。

---

### 陷阱 10：config_reload_subscriptions 未声明

**现象**：`on_config_update(scope="bot")` 永远不被调用，主程序人格配置变了插件不知道。

**根因**：SDK 要求显式声明 `config_reload_subscriptions` 才能收到对应 scope 的回调；
`plugin.py` 的类属性默认是 `()`，Host 侧 `get_config_reload_subscribers` 只把 scope 命中
`registration.config_reload_subscriptions` 的插件列入广播。

**正确写法**：
```python
from typing import ClassVar, Iterable

class MyPlugin(MaiBotPlugin):
    config_reload_subscriptions: ClassVar[Iterable[str]] = ("bot", "model")
```

**注意**：只能填 `bot` / `model` 两个别名，其它值在归一化时抛 `ValueError`；直接写字符串（不是集合）会抛 `TypeError`。

**验证来源**：SDK `maibot_sdk/plugin.py` `get_config_reload_subscriptions`、`maibot_sdk/types.py`
`normalize_config_reload_subscription`；主程序 `src/plugin_runtime/host/supervisor.py` `get_config_reload_subscribers`

---

### 陷阱 11：manifest 缺少 `author.url` / `urls.repository` 导致注册失败

**现象**：启动日志报 `插件注册失败: <id>: manifest 校验失败: 缺少必需字段: author.url; 缺少必需字段: urls.repository`，插件无法加载。

**根因**：`manifest_validator.py` 的 `ManifestAuthor.url` 与 `ManifestUrls.repository` 都**无默认值**（必填），
且 `_validate_url` / `_validate_repository` 对空值和非 http(s) 抛 `ValueError`。在 `extra="forbid"` 下缺失字段直接报「缺少必需字段」。

**错误写法**：
```json
"author": { "name": "octmicy" },
"urls": { "documentation": "https://docs.mai-mai.org" }
```

**正确写法**（url 可用仓库地址，占位地址也可接受）：
```json
"author": { "name": "octmicy", "url": "https://github.com/octmicy/my-plugin" },
"urls": {
  "repository": "https://github.com/octmicy/my-plugin",
  "homepage": "https://github.com/octmicy/my-plugin",
  "documentation": "https://docs.mai-mai.org"
}
```

**验证来源**：主程序 `src/plugin_runtime/runner/manifest_validator.py` `ManifestAuthor` / `ManifestUrls` /
`_validate_url` / `_validate_repository`

---

### 陷阱 12：配置缺少 `[plugin].config_version` —— 插件进入"仅配置管理"状态

**现象**：插件能过 manifest 校验，但启动日志报
`插件 {id} 配置错误，仅加载配置管理: 插件配置文件缺少 plugin.config_version 版本号，当前版本策略不再兼容无版本配置`
（冒号后被括号带出的是 `PluginConfigVersionError` 自身的文案；另一处入口会先打
`插件配置版本检查失败: {exc}`）；所有调用返回 `E_BAD_PAYLOAD`「插件配置错误，业务暂停」。

**根因**（`runner_main.py` `extract_plugin_config_version` + `_normalize_plugin_config`）：
缺 `[plugin]` 节抛 `PluginConfigVersionError`「插件配置文件缺少 [plugin] 配置节，且必须提供 plugin.config_version 版本号」；
`config_version` 为空抛「...缺少 plugin.config_version 版本号，当前版本策略不再兼容无版本配置」。
调用方捕获后置 `meta.config_error`，随后**仍以该状态注册**——Host 侧"仅加载配置管理，不启用业务"，
invoke 时直接返回 `E_BAD_PAYLOAD`。所以这不是"完全拒载"，而是"装上了但全瘫"。

**错误写法**：
```toml
[plugin]
enabled = true
```

**正确写法**（config.py 同步声明默认值）：
```python
CONFIG_SCHEMA_VERSION = "1.0.0"

class PluginConfig(PluginConfigBase):
    config_version: str = Field(
        default=CONFIG_SCHEMA_VERSION,
        description="配置 schema 版本，请勿手动修改。",
        json_schema_extra={"disabled": True, "hidden": True, "label": "配置版本", "order": 99},
    )
```
```toml
[plugin]
enabled = true
config_version = "1.0.0"
```

**经验**：新插件起步时直接照抄成熟模板的 `_manifest.json` + `config.py` 结构
（`author.url` / `urls.repository` / `config_version` 三个坑一次到位），再删减不需要的字段。

**验证来源**：主程序 `src/plugin_runtime/runner/runner_main.py` `extract_plugin_config_version` /
`_normalize_plugin_config`（`插件配置版本检查失败` 日志）/ `_prepare_plugin_activation`
（`插件 {id} 配置错误，仅加载配置管理` 日志）/ invoke 入口的 `config_error` 分支；
`src/plugin_runtime/protocol/envelope.py`

---

### 陷阱 13：`llm.generate` 的 `model` 参数语义已演进，不再无条件当任务名

**现象**：`ctx.llm.generate(model="reply", ...)` 报「未找到名为 reply 的模型配置」，插件命令失败。

**当前真实语义**（`src/plugin_runtime/capabilities/core.py` `_resolve_llm_capability_route`）：
- **显式传 `task_name`**：`model` / `model_name` 都只表示**具体模型名**（不再按任务名解析）
- **未显式传 `task_name`**：`model` 命中 Host 可用任务表 → 当**任务名**；未命中 → 当**具体模型名**
- `model` 与 `model_name` 同时传且取值不同 → 抛 `ValueError`「model 与 model_name 不能指定不同的模型」
- 都没传时落到默认任务 `utils`（`_DEFAULT_PLUGIN_LLM_TASK`）

**关键事实**：
- 常见任务名：`replyer`（回复模型）、`planner`（规划）、`utils`（小任务）、`memory`、`mid_memory`、`learner`、`vlm`、`fast_model`（表达方式选择、回复断句等轻量任务走它）等
- **任务集合 = `src/config/model_configs.py` 的 `ModelTaskConfig` 字段**，实际可用性取决于各环境 `config/model_config.toml` 的 `[model_task_config.*]` 配置
- **没有 `reply` 这个任务名**！回复模型任务默认叫 `replyer`（各环境可能不同，取决于 model_config.toml）
- `ctx.llm.get_available_models()` 返回可用任务名列表（`List[str]`），可在 `on_load` 校验配置、或做成命令给用户自查

```python
# 明确要「replyer 这个任务」
await ctx.llm.generate(prompt="...", task_name="replyer")

# 明确要「某个具体模型」
await ctx.llm.generate(prompt="...", model_name="gpt-4o-mini")

# 旧写法（仍兼容）：未传 task_name 时，model 命中任务表才按任务名解析
await ctx.llm.generate(prompt="...", model="replyer")
```

写新代码推荐用 `task_name=` 显式表达意图，避免落在"具体模型名"分支上。

**验证来源**：主程序 `src/plugin_runtime/capabilities/core.py` `_resolve_llm_capability_route` /
`_cap_llm_generate`

---

### 陷阱 14：用了已废弃 / 已移除的装饰器

**现象 A**：写 `@Action(...)` 后控制台刷 `DeprecationWarning`，或看官方示例以为 Action 是独立组件。

**根因**：`@Action` **已废弃**，SDK 内部把它转成 `@Tool` 注册（metadata 打 `legacy_action: True`、
`invoke_method="plugin.invoke_action"`），**主程序只维护一套 Tool 抽象**。官方 `hello_world_plugin` 仍在用
`@Action`（示例本身是旧写法），照抄会把废弃写法带进新插件。

**正确做法**：新插件一律用 `@Tool` + `ToolParameterInfo`（自动生成 JSON Schema）。

**现象 B**：写 `@WorkflowStep(...)` 直接抛 `RuntimeError`。

**根因**：`WorkflowStep` 在 SDK 2.0 被 `HookHandler` 取代，SDK 只保留同名入口用于**报错而非兼容**
（`components.py` 的 `WorkflowStep` 直接 `raise RuntimeError("`WorkflowStep` 已移除，请改用 `HookHandler`。这是一个不向后兼容更改。")`）。

**验证来源**：SDK `maibot_sdk/components.py` `Action` / `WorkflowStep`

---

### 陷阱 15：EventType 枚举 11 个值里只有 2 个真的有发射点

**现象**：写 `@EventHandler(EventType.ON_MESSAGE)` 想拦截入站消息，永远不被调用；`POST_LLM` / `ON_PLAN` /
`AFTER_SEND` 等同样静默无响应。

**根因**：SDK `EventType` 枚举 11 个值，但主程序 `EventBus.emit` 全仓只有 3 处调用：
- `ON_START`：`src/main.py`（startup 流程）
- `ON_STOP`：`src/runtime.py`（关停流程）与 `src/webui/routers/system.py`（WebUI 重启前主动停插件运行时）
- 其余 9 个值**无发射点**，只存在于 `core/types.py` 定义与 `plugin_runtime/integration.py` 的 `_EVENT_TYPE_MAP` 映射表

尤其 **`ON_MESSAGE` 的分发被整段注释掉了**（`src/chat/message_receive/bot.py` `receive_message` 内三行注释代码）。
入站消息实际由 Hook 承载：`chat.receive.before_process` / `chat.receive.after_process`。

**正确做法**：
- 要拦消息/改消息 → 用 Hook（陷阱 4），不要用 `ON_MESSAGE`
- `ON_START` / `ON_STOP` 用于插件生命周期收尾（保存状态、关闭连接）
- 出站消息拦截 → `send_service.after_build_message`（附录 1）

**验证来源**：主程序 `src/core/types.py` `EventType`、`src/core/event_bus.py` `emit`、
`src/main.py`、`src/runtime.py`、`src/webui/routers/system.py`、`src/chat/message_receive/bot.py`

---

### 陷阱 16：版本区间锁死小版本 / Release 版本对不上被插件中心拒收

**现象 A**：MaiBot 升级后插件突然加载不了，日志报 `Host 版本不兼容`。

**根因**：`host_application.max_version` 写成了低于当前 Host 的版本（如 `1.2.99`），Host 升到 1.3.x 直接超出区间。
版本区间校验规则（`manifest_validator.py` `_validate_runtime_compatibility`）：
- Host **高于** `max_version` 但**主次版本相同**（仅补丁号超出）→ warning，插件照常加载（`is_same_major_minor_higher_version`）
- Host 其余情况超出区间（如 1.2.x 插件遇 1.3.x）→ error，插件被阻止加载
- SDK 超出区间 → **一律 error**，无容忍档

**正确做法（两条线两套口径，别混用）**：
- **`host_application`**：`max_version` 写 `999.999.999`，只认真约束 `min_version`。依据：Host 有同主次版本的补丁级容忍规则，超界多为 warning（见上），别把"新版本还能不能跑"交给版本号，交给实际测试。
- **`sdk`**：`max_version` 锁在当前主版本线内（如 `2.99.99`），**不要**写 `999.999.999`。依据：SDK 超出区间**一律 error、没有容忍档**（`_validate_runtime_compatibility` 对 SDK 没有任何豁免分支），而插件确实依赖 SDK 的接口形状——把上界放开等于声明支持根本不兼容的大版本，插件会被放进必炸的环境。

两处官方来源**各自实际写的值不同**，不要笼统说"官方就是这么写的"：内置插件
`src/plugins/built_in/plugin_management/_manifest.json` 写 `host_application: 1.0.0 ~ 999.999.999`、
`sdk: 2.0.0 ~ 2.99.99`；上游 `MaiM-with-u/plugin-repo` 的 `CONTRIBUTING.md` 示例写
`host_application: 1.0.0 ~ 1.99.99`、`sdk: 2.0.0 ~ 2.99.99`。两条线的 `min_version` 都是真实下限，都不是 `0.0.0`。

**现象 B**：发布了新 Release，但插件市场详情页显示「有 N 个发布版本未通过校验」，用户装不了。

**根因**：插件市场的版本按 **Git Release** 逐条收录，任何一条对不上就打回 `rejected_releases`。发布规则
（Tag 与 manifest version 一致、版本三段式不带后缀、插件 id 不变、`manifest_version` 固定 2 等）与
收录流程、多版本安装机制详见 **`references/plugin-repo-submission.md`**，此处不再重复维护。

**临时手段 — 强制插件兼容开关**：主程序 `[debug] force_plugin_compatibility`（`compat_policy.py`，
WebUI 调试配置里也有开关）开启后跳过 `host_application` / `sdk` 区间校验，超范围只 warning 不拒载。
注意：**需重启生效**（Host 经环境变量传给 Runner，不热更新）；只跳版本区间，能力白名单、依赖解析、
`llm_providers` 一致性等校验照旧。仅作排查用，别长期开。

**验证来源**：主程序 `src/plugin_runtime/runner/manifest_validator.py` `_validate_runtime_compatibility` /
`is_same_major_minor_higher_version`、`src/plugin_runtime/compat_policy.py`；
内置插件 `src/plugins/built_in/plugin_management/_manifest.json`（两条线的实际取值）；
上游 `MaiM-with-u/plugin-repo` `CONTRIBUTING.md`（manifest 版本区间示例）

---

### 陷阱 17：SDK 新能力可能领先 Host 实现——SDK 有方法不代表 Host 能执行

**现象**：插件加载正常（manifest 校验、能力授权都不拦），一调某个 `ctx.*` 方法就抛错，
Host 日志报 `未注册的能力: xxx`。

**根因**：SDK 与主程序是**独立发版**的。SDK 先有方法签名，Host 的 `capabilities/registry.py` 注册表
可能还没有对应条目。SDK 侧 `call_capability` 只是转发 RPC，Host 端 `capability_service.py` 查注册表失败即返回
`E_METHOD_NOT_ALLOWED`「未注册的能力: {capability}」。

**三个容易误判的点**：
- **manifest 写一个未注册的能力名不会导致拒载**：`authorization.py` 里 capabilities 只是逐字面记录的授权清单，
  Host 不校验名字是否真实存在；授权能过，死在运行时调用——又是「能加载但功能是摆设」的形态（陷阱 7）。
- **`ctx.*` 是 RPC 转发代理，SDK 版本无关调用成败**：升级 SDK 只能让你"写得出"调用，"跑得通"由 Host 决定。
- **主程序版本号相同 ≠ 源码没变**：Host 可能小步提交，以当时拉到的源码为准。

**已实现 / 曾经落后的实例**（用于说明判定方法，具体以当时源码为准）：
- `chat.get_avatar`：SDK 2.9.0 引入时 Host 尚未实现，当前 Host 1.3.9 已在
  `capabilities/registry.py` 注册（实现转调 `src.platform_io.avatar.avatar_service`）。
  **同类能力需现查**，不要照抄本文结论。
- `webui.claim_upload`：SDK 2.11.0 新增，需 manifest 能力 `webui.claim_upload` 与宿主 `file_upload_v1`；
  凭证一小时有效、一次性领取，文件字节不经 RPC。
- `maisaka.context.resolve_image`：SDK 2.12.0 新增，需 manifest 能力 `maisaka.context.resolve_image`。

**排查方法**：怀疑 SDK 方法 Host 不支持时，直接在主程序源码搜能力名字符串
（如 `grep -rn "get_avatar" src/plugin_runtime/`）；零命中即 Host 未实现，只能等主程序更新或换实现路径。
更稳的做法是核对 `src/plugin_runtime/capabilities/registry.py` 的注册表全集。

**验证来源**：主程序 `src/plugin_runtime/host/capability_service.py`、`host/authorization.py`、
`src/plugin_runtime/capabilities/registry.py`；SDK `maibot_sdk/capabilities/*.py`

---

## 补充陷阱 — 配置与注册期的硬失败

### 陷阱 18：WebUI 声明文件写错 schema_version 会让整个插件注册失败

**现象**：`webui.json` 里 `schema_version` 写了 1（或写了未知名），插件启动即注册失败，
日志报 `插件 <id> WebUI 声明无效: ...`，整个插件的组件全部不加载。

**根因**（`runner_main.py` `_register_plugin` → `webui_schema.py` `load_webui_extension`）：
`load_webui_extension` 抛 `OSError` / `ValueError` 时 `logger.error` 后**直接 `return False`**，
与 `llm_providers` 双向不一致是同一处逻辑——**不是 warning，是注册失败**。
`WebUIExtension.validate_size` 里 `schema_version` 不是 `2` 直接抛
`ValueError("WebUI 协议已升级为 2；请按 docs/plugin-webui.md 迁移声明")`。
没有 `webui.json` 的插件返回 `None`，不受影响。

**webui.json 的硬限制**（`src/plugin_runtime/webui_schema.py`）：
- `schema_version` 必须是 `2`
- 声明文件 ≤ 128 KiB；注册载荷 ≤ 512 KiB；每插件最多 20 页
- `declarative` 页：`content` 至少 1 个组件、最多 50 个引用节点（构建时展开上限 8 层 / 200 个组件）；
  `queries` ≤ 10、`actions` ≤ 20；`icon` 只接受 `puzzle` / `chart` / `settings` / `database` / `list`
- `custom` 页：HTML ≤ 2 MiB、总量 ≤ 8 MiB，**必须经 `entry` 指向插件内相对 `.html` 文件，不能内联 `document`**；
  `entry` 路径不允许 `..` / 绝对路径 / 符号链接
- `placement: "workspace"` 的页面必须同时声明 `workspace_title`
- `danger` 变体按钮必须声明 `confirmation`
- 结构化参数（`array` / `object`）需要 `required_capabilities: ["structured_arguments"]`；
  `custom` 页需要 `custom_pages`；图片上传需要 `image_upload`

**完整协议与字段说明见 `references/webui-pages.md`**（该文件描述的是 `webui.json` 声明式页面协议）。
另可用 `@HomeCard` 在 WebUI 首页放卡片（声明式渲染，不能执行插件提供的 HTML/JS）。

**验证来源**：主程序 `src/plugin_runtime/runner/runner_main.py` `_register_plugin`、
`src/plugin_runtime/webui_schema.py` `WebUIExtension` / `load_webui_extension`

---

### 陷阱 19：回复扩展的平台作用域需要配套 Host 版本，否则限制静默不生效

**现象**：`@ReplyExtension(..., platforms=["telegram"])` 在 QQ 聊天里模型仍然挑选到这个扩展，
`prepare` / `before_send` 照常被调用。

**根因**：`platforms` 是 SDK 2.14.0 给 `@ReplyExtension` 加的（2.13.0 先加给 `@Tool`），
Host 侧过滤靠 `component_registry.py` `check_component_enabled` 里对 `ToolEntry` / `ReplyExtensionEntry`
的平台比对 + `reply_extensions.py` `get_reply_extensions` 每次实时查询（不缓存插件生命周期）。
**旧 Host 没有这段过滤**：组件照常进 `reply.plugin_options`，平台限制被静默忽略。
同理 `@Tool(platforms=...)` 在旧 Host 上也不会被过滤（旧 Host 只在执行时报「当前平台不在插件工具的 platforms 作用域内」，
取决于调用路径是否带 platform 上下文）。

**正确做法**：
- 依赖声明写死配套 Host 下限（回复扩展本身需 Host 1.3.5 开发版本起 + SDK ≥ 2.10.0，平台作用域需更新的 Host）
- 插件内部也要自行校验平台，不要只依赖 Host 过滤
- `platforms` 省略 / `None` / `[]` 表示不限平台；传入空字符串或非字符串会抛 `ValueError`

**ReplyExtension 返回值也是硬约束**（`host/reply_extensions.py`）：
- `prepare` 阶段只允许返回 `{"extra_prompt": str}`，多一个键或类型不对直接 `raise`
- `before_send` 阶段只允许返回 `{"messages": [...]}`，返回 `{}` 保持原样
- 两次调用前都会复查扩展是否仍处于可用状态，停用/重载会让本次 reply 失败

详见 `references/reply-extensions.md`。

**验证来源**：SDK `maibot_sdk/components.py` `ReplyExtension` / `_normalize_platforms`；
主程序 `src/plugin_runtime/host/component_registry.py` `ReplyExtensionEntry` / `check_component_enabled`、
`src/plugin_runtime/host/reply_extensions.py` `ReplyExtensionExecution.prepare` / `transform`

---

### 陷阱 20：在 Schedule 之外误用某类 Hook —— `allow_abort=False` 的 Hook 里返回 abort 无效

**现象**：在 `maisaka.planner.before_request` / `maisaka.replyer.*` / `send_service.after_send`
里 `return {"action": "abort"}`，想中止模型请求或发送，毫无效果。

**根因**：这些 HookSpec 的 `allow_abort=False`（`hook_dispatcher.py` `_merge_blocking_result`）：
abort 请求被忽略并记 error，**不报错、不中止**。同理 `allow_kwargs_mutation=False` 的 Hook
（`send_service.after_send`）里返回 `modified_kwargs` 也被忽略。

**当前 Host 的 Hook 能力矩阵**（`allow_abort` / `allow_kwargs_mutation`）：

| Hook | abort | 改 kwargs | 默认超时 |
|------|-------|-----------|----------|
| `chat.receive.before_process` / `after_process` | ✅ | ✅ | 无（走全局默认） |
| `chat.command.before_execute` | ✅ | ✅ | 无（走全局默认） |
| `chat.command.after_execute` | ❌ | ✅ | 无（走全局默认） |
| `emoji.maisaka.before_select` / `after_select` | ✅ | ✅ | 5000 ms |
| `emoji.register.after_build_description` | ✅ | ✅ | 5000 ms |
| `expression.select.*` / `expression.learn.*` | ✅ | ✅ | 5000 ms |
| `jargon.extract.before_persist` / `jargon.inference.before_finalize` | ✅ | ✅ | 5000 ms |
| `send_service.after_build_message` / `before_send` | ✅ | ✅ | 5000 ms |
| `send_service.after_send` | ❌ | ❌ | 5000 ms |
| `maisaka.planner.before_request` / `after_response` | ❌ | ✅ | 6000 ms |
| `maisaka.replyer.before_request` / `before_model_request` / `after_response` | ❌ | ✅ | 6000 ms |
| `maisaka.reply.before_post_process` | ❌ | ✅ | 6000 ms |

超时解析顺序：handler 的 `timeout_ms` > HookSpec 的 `default_timeout_ms` > 全局
`plugin_runtime.hook_blocking_timeout_sec`（`hook_dispatcher.py` `_resolve_timeout_ms`）。
**Hook 执行超时同样只记 error 并走 error_policy，不会让主流程崩**——又是一个静默失效点。

**正确做法**：想中止就用 `allow_abort=True` 的 Hook；想在 planner / replyer 链上改内容就改
`items` / `output_items` / `extra_prompt` / `reply_tool_args`（附录 2），别指望 abort。

**验证来源**：主程序各 `register_*_hook_specs()`（`src/chat/message_receive/bot.py`、
`src/emoji_system/emoji_manager.py`、`src/learners/expression_learner.py`、`src/learners/jargon_miner.py`、
`src/services/send_service.py`、`src/maisaka/chat_loop_service.py`）；
`src/plugin_runtime/host/hook_dispatcher.py` `_resolve_timeout_ms` / `_merge_blocking_result`

---

### 陷阱 21：能力清单之外的静默限制——调得通、改不动

这些能力**授权能过、调用不报异常**，但结果恒为失败或受限，属于"看起来能跑"的坑：

| 能力 | 实际限制 |
|------|----------|
| `component.update_plugin_config` | 仅 `plugin_id == "builtin.plugin-management"`，否则恒返回「仅插件管理内置插件可以修改插件配置」 |
| `component.unload_plugin` | 恒返回失败「新运行时不支持单独卸载插件，请使用 reload」 |
| `component.enable` / `component.disable` | 仅支持全局：`scope != "global"` 或传了 `stream_id` 恒失败「当前仅支持全局组件启用/禁用」 |
| `database.query` | 只支持 5 种 `query_type`：`get` / `create` / `update` / `delete` / `count`；`create` / `update` 缺 `data` 直接失败 |
| `api.call` | 只能调本插件或已公开的 API：未公开返回「API {name} 未公开，禁止跨插件调用」；API 名不唯一时要求显式指定 `version` |
| `send.*` 七个方法 | 都要求 `stream_id` 非空（`send.command` 还要求 `command`，`send.custom` 要求 `message_type`），缺失返回「缺少必要参数 ...」并 `success=False` |
| `llm.generate` / `generate_with_tools` | `model` 与 `model_name` 冲突抛错（陷阱 13）；`prompt` 只能是 `str` 或 `list[dict]`，空串/空列表/非 dict 元素都抛「缺少必要参数 prompt」 |
| `llm.generate_with_tools` | `tools` / `tool_options` 必须是 `list`，否则返回「tools 必须为列表」 |

**另一类注册期硬失败**（与"静默"互补，排查时别混淆）：
- 两个插件声明同一 `llm_providers` client_type 时**双方都被阻止加载**（`integration.py` `_discover_llm_provider_conflicts`）
- manifest 的 `llm_providers` 与代码 `@LLMProvider` 必须双向一致：注册时比对 `declared_client_types` 与
  `registered_client_types`，不一致直接注册失败（`runner_main.py`）

**验证来源**：主程序 `src/plugin_runtime/capabilities/components.py`、`capabilities/data.py`、
`capabilities/core.py`、`integration.py`

---

## 陷阱排查方法论

遇到疑似 SDK 问题时，按以下顺序排查（**源码 > 官方文档**，文档有已知过时处）：

1. **查 SDK 源码** — `maibot-plugin-sdk/maibot_sdk/`（当前 2.14.0）
   - `components.py` — 装饰器签名（Command/Tool/API/HookHandler/EventHandler/HomeCard/ReplyExtension/Action）
   - `context.py` — `PluginContext`、能力代理挂载、`_BOOLEAN_SUCCESS_CAPABILITIES`、`PluginPaths`
   - `capabilities/*.py` — 各能力代理的方法签名（**文件名是 `database.py` 不是 `db.py`**）
   - `types.py` / `plugin.py` / `config.py` — 枚举、配置订阅、配置基类
2. **查主程序插件运行时** — `MaiBot/src/plugin_runtime/`
   - `component_query.py` — Command/Tool 执行器（看返回值怎么解析）
   - `capabilities/` — Host 端能力实现（看实际处理哪些参数）
   - `capabilities/registry.py` — **能力注册表全集**（判断某个能力名是否存在）
   - `host/hook_dispatcher.py` — Hook 分发（action 归一化、kwargs 替换、超时、abort 判定）
   - `host/component_registry.py` — 组件注册与 HookSpec 校验、平台作用域、aliases 匹配
   - `webui_schema.py` — `webui.json` 协议与体积限制
3. **查主程序消息链路** — `MaiBot/src/`
   - `chat/message_receive/bot.py` — chat/command Hook 触发点、命令拦截与权限
   - `services/send_service.py` — 出站 Hook 触发点与 abort 行为
   - `maisaka/chat_loop_service.py` — planner/replyer Hook 规格与 items 协议
   - `core/types.py` + `core/event_bus.py` — EventType 真实发射点
4. **查官方文档** — `docs/zh/plugin/`（SDK 仓库内）与 https://docs.mai-mai.org/plugin/
   - ⚠️ 已知过时/有误处：`commands.md` 把第三个返回值写成 `weight`（实为 `intercept_message_level`）；
     `event-handlers.md` 示例返回 `{"intercepted": True}`——当前运行时只认
     `{"continue_processing": False}`（或兼容 `{"blocked": True}`），返回 `intercepted` 不拦截
   - ⚠️ `manifest.md` 的能力示例已改为具体名（`send.text` 等），但示例插件的 `@Action` / 多返回值写法仍是旧的
5. **查官方示例插件** — `MaiBot/plugins/hello_world_plugin/plugin.py`
   （但注意它仍用废弃的 `@Action`，EventHandler 的多返回值也是过时写法）

**已知出入小结（官方文档 vs 当前源码）**：
- 命令返回值三元组第三位是 `intercept_message_level`，不是 `weight`
- `EventHandler` 拦截语义是 `continue_processing=False`（或 `blocked=True`），不是 `intercepted`
- `EventType` 11 个值只有 `ON_START` / `ON_STOP` 有发射点，`ON_MESSAGE` 分发已被注释
- WebUI 自定义页面是 `webui.json` 声明式协议（`schema_version: 2`），不是旧的 manifest 页面扩展协议（v2 之前）；
  写错 `schema_version` 会让整个插件注册失败
- 能力名是逐项分层名（`send.text` / `llm.generate`），没有 `send_message` 这种聚合名

---

## 附录 1：send_service 出站拦截 Hook 权威参考

做「输出拦截 / 关键词屏蔽 / 回复过滤」类插件时，用 `send_service.after_build_message`。

### kwargs 结构（`src/services/send_service.py` `_send_to_target_with_message` / `_send_via_platform_io` 确认）

| Hook | required kwargs | optional | abort |
|------|-----------------|----------|-------|
| `send_service.after_build_message` | `message`、`stream_id`、`processed_plain_text`、`typing`、`set_reply`、`storage_message`、`show_log` | — | ✅ |
| `send_service.before_send` | `message`、`typing`、`set_reply`、`storage_message`、`show_log` | `reply_message_id` | ✅ |
| `send_service.after_send` | `message`、`sent`、`typing`、`set_reply`、`storage_message`、`show_log` | `reply_message_id` | ❌ |

### 关键事实

1. **提取文本优先级**：`kwargs["processed_plain_text"]` → `message["processed_plain_text"]`
   （构建时强制非空：`processed_plain_text.strip() or _build_processed_plain_text(...)`）→ 从 `message["raw_message"]` 兜底。
   ⚠️ **`raw_message` 是组件 dict 列表**（`[{"type": "text", "data": "..."}]`），**不是**带 `components` 键的字典；
   TextComponent 的文本字段是 `data`，**不是** `text`。**必须按 `type == "text"` 过滤**——image/emoji 的 `data`
   是资源地址、file/at/reply/forward/dict 的 `data` 是结构化数据，不过滤会把图片 URL 当正文参与关键词匹配，
   URL 含关键词即误拦（见 `src/plugin_runtime/host/message_utils.py` `_component_to_dict`）。
2. **abort 行为**：主程序收到 `{"action": "abort"}` 后直接 `return None`，**跳过 Platform IO 发送且不写库**
   （无聊天历史残留），并打印 `[SendService] 消息 xxx 在构建后被 Hook 中止`（before_send 是「在发送前被 Hook 中止」）。
3. **HookSpec**：`allow_abort=True`、`allow_kwargs_mutation=True`、`default_timeout_ms=5000`。
4. **注意**：该 Hook 覆盖**所有**出站消息（AI 回复、主动发言、命令/其他插件发送），无法区分消息来源类型；
   关键词拦截时需接受这一点。

### 拦截模板

```python
@HookHandler(
    "send_service.after_build_message",
    name="output_blocker",
    mode=HookMode.BLOCKING,
    order=HookOrder.EARLY,
    error_policy=ErrorPolicy.SKIP,
)
async def intercept_outbound(self, **kwargs):
    text = kwargs.get("processed_plain_text") or (kwargs.get("message") or {}).get("processed_plain_text", "")
    if hit_keyword(text):
        self.ctx.logger.warning(f"[拦截] 命中提示词，消息已拦截: {text[:100]}")
        return {"action": "abort"}
    return {"action": "continue", "modified_kwargs": kwargs}
```

### 测试要点

- 正则模式注意惰性编译：配置注入后未调用 `on_load()` 时 `_compiled_patterns` 为空，regex 匹配需做「缓存为空则即时编译」的兜底。
- mock 插件测试：`plugin._set_context(fake_ctx)` 注入 ctx，`plugin._plugin_config_instance = ConfigModel(**cfg)` 注入配置（基类 `config` / `ctx` 均为只读 property，走私有字段注入）。

---

## 附录 2：maisaka Planner Hook 协议（items / output_items）— 压制/注入类插件必读

做「睡眠期间不让 Bot 说话」「给 Planner 塞额外上下文」这类插件时，**唯一有效的字段是 `items` / `output_items`**。
用 `messages` / `response` / `tool_calls` 会**静默失效**（不报错，写进去被 Host 直接忽略）。

### kwargs 结构（`src/maisaka/chat_loop_service.py` `register_maisaka_hook_specs`）

| Hook | required kwargs | 回读的字段 |
|------|-----------------|-----------|
| `maisaka.planner.before_request` | `items`、`item_schema_version`、`tool_definitions`、`selected_history_count`、`built_message_count`、`selection_reason`、`session_id` | `items`、`tool_definitions` |
| `maisaka.planner.after_response` | `output_items`、`item_schema_version`、`selected_history_count`、`built_message_count`、`selection_reason`、`session_id`、`prompt_tokens`、`completion_tokens`、`total_tokens` | `output_items` |

- `before_request` / `after_response`：**`allow_abort=False`**、`allow_kwargs_mutation=True` → 只能改写，不能中止。
- **没有** `messages`、`response`、`tool_calls`、`extra_prompt`（`extra_prompt` 只在 `maisaka.replyer.before_request`，见陷阱 8）。
- **`item_schema_version` 必须原样回带**：不等于 `CONTEXT_ITEM_SCHEMA_VERSION` 时
  `src/plugin_runtime/hook_payloads.py` 直接抛错、整份 items 被丢弃（Host 打 warning「Hook ... 返回的 items 无效，已忽略」）。

### 序列化 Context Item 的结构（`serialize_context_item_snapshot`，`src/llm_models/request_snapshot.py`）

```python
{
    "item_type": "SystemMessageItem",          # 或 UserMessageItem / AssistantMessageItem /
                                               # ReasoningItem / FunctionCallItem / FunctionCallOutputItem / ...
    "meta": {
        "item_id": "<非空字符串>",
        "logical_turn_id": None,               # 键必须存在，可为 null
        "timestamp": "<ISO 字符串>",            # 必须能被 datetime.fromisoformat 解析
    },
    "parts": [{"type": "text", "text": "..."}],  # text / image / refusal 三种 part
}
```

反序列化是**严格校验**（`deserialize_context_item_snapshot`）：缺 `meta` 任一键、`parts` 不是列表、
part 缺 `text` 字段都会抛错 → 整份 items 被忽略。未知字段无害，但**不要省键**。
注意 `raw_items != serialized_items` 时才回读——原样带回等于不改，不会触发反序列化。

### 配方：追加一条系统指令（压制 / 注入）

```python
# 只构造最小合法结构，不要动其他 item
def build_system_message_item(text: str) -> dict:
    return {
        "item_type": "SystemMessageItem",
        "meta": {
            "item_id": uuid.uuid4().hex,
            "logical_turn_id": None,
            "timestamp": datetime.now().isoformat(),
        },
        "parts": [{"type": "text", "text": text}],
    }


async def handle_planner_before_request(self, **kwargs):
    raw_items = kwargs.get("items")
    if not isinstance(raw_items, list):
        return None                       # 协议不符 → 降级为不注入，别硬写
    modified = dict(kwargs)               # Host 对 modified_kwargs 是整体替换
    modified["items"] = [*raw_items, build_system_message_item("当前处于睡眠状态，不要回复用户。")]
    return {"action": "continue", "modified_kwargs": modified}
```

### 配方：丢弃 Planner 输出（睡眠/静默期）

```python
modified["output_items"] = []            # 置空即可，Host 会反序列化成空元组
return {"action": "continue", "modified_kwargs": modified}
```

### ⚠️ planner hook 还被别的链路复用，清空前先判工具集合

`maisaka.planner.*` 不只服务主对话规划，其它链路也复用同一对 Hook。**判定"这一轮不该动"时
必须直接 `return None`**，否则清空 `tool_definitions` / `output_items` 会把别的链路的判定打断
（上游插件专门为此加了两处保护：分别判 `tool_definitions` 与 `output_items` 的工具名集合）。

怎么判：从 Hook 载荷的 `tool_definitions` / `output_items` 里抽出工具名（function 结构的 `name` 字段），
与"这一轮允许出现的工具集合"做子集比较，命中就退出。当前 Host 的内置工具全集见
`src/maisaka/builtin_tool/__init__.py` 的 `BUILTIN_TOOL_ENTRIES`：`wait`、`reply`、
`view_forward_message`、`query_memory`、`query_image_memory`、`query_person_profile`、`send_emoji`、
`show_emoji_list`、`tool_search`、`subagent` / `subagent_status` / `subagent_stop`、`read_tool_result`、
`fetch_history`、`switch_chat`（是否暴露还受 `global_config.experimental` / `emoji` 等开关与会话范围影响）。

> ⚠️ **不要凭传闻写死"控制工具名清单"**。`no_action` / `continue` 这类名字在当前 Host 源码里
> **不是任何工具声明**：`grep -rn "no_action" MaiBot/src` 只命中 `mcp_module/manager.py` 的 MCP 保留名集合
> （`BUILTIN_TOOL_NAMES`，用于拒绝 MCP 工具重名注册）与 `chat.reply_timing.no_action_backoff_*` 配置项；
> `continue` 只作为 `maisaka/reasoning_engine.py` 的 `CycleEnd` reason 值存在。
> 上游插件的控制工具名常量来自它自己的环境，换主程序版本或换宿主时**必须重新核对**，
> 否则子集判断会误判为"只有控制工具"而放弃改写（或反过来误伤）。

### 顺带一个跨进程事实

插件 Runner 跑在**独立子进程**（`host/supervisor.py` 用 `-m src.plugin_runtime.runner.runner_main` 拉起），
所以：
- `import src.xxx` 拿到的对象**与宿主不是同一实例**（如 `chat_manager`、`prompt_manager`）→ 跨进程调用等于死代码；
- 群号/显示名这类宿主侧信息，只能从 Hook 载荷的序列化 message（`message_info.group_info.group_id`）里取，或自己在插件进程里缓存。

---

## 附录 3：`@Command` 的 `aliases` 是字面前缀匹配，不是正则

`Command(name, description="", pattern="", aliases=None, **metadata)`（`maibot_sdk/components.py`）

- `pattern` → `re.compile(pattern).search(text)`，是真正则。
- **`aliases` → 普通字符串前缀匹配**：`text.startswith(alias)`（Host `host/component_registry.py` 的命令匹配循环）。
  - **必须带前导 `/`**：写 `"/sleep_wakeall"`，写 `"sleep_wakeall"` 永不命中。
  - **不能写正则**：塞 `^/xxx$` 会被当成字面字符。
  - 两者是 **OR 关系**（任一命中即触发）。
- **命中后命令的"身份"永远是装饰器的 `name`**，与命中的是 pattern 还是 alias 无关。所以改名会影响：
  - 会话禁用命令列表（`bot.py` 的 `is_command_disabled(f"{plugin_name}.{command_name}")`）
  - 权限键 `f"{plugin_name}.{command_name}"`（`bot.py` 的 `has_command_permission`）
  - `chat.command.before_execute` 载荷里的 `command_name`

**结论**：想让老用户的老命令名继续可用，必须**显式**写 `aliases=["/旧名"]`；别名不会保留旧身份。

> 相关：`@Command(..., permission="operator")` 标记后仅 `[plugin].permission` 操作员或
> `command_permissions` 放行规则可触发；无权限时 `intercept_message_level=1` 并按
> `silent_permission_denied` 决定是否回「你没有权限使用此命令」。会消耗模型资源的命令务必加。

---

## 附录 4：删除配置字段与 `config_version` 重建语义

- **删字段是安全的**：SDK `PluginConfigBase` 是 `ConfigDict(validate_assignment=True, extra="ignore")`
  （`maibot_sdk/config.py`）→ 老 `config.toml` 里残留的已删字段会被静默忽略，不会导致加载失败。
- **`[plugin].config_version` 是强校验项**：`extract_plugin_config_version` 要求非空、点分数字串，
  缺失或为空直接 `PluginConfigVersionError`（失败形态见陷阱 12）。
- **何时重建配置**（Host `runner_main.py` `_prepare_plugin_config_for_version_update`）：
  `compare_versions(current, latest)` 的定义是 `new_parts > old_parts`——
  **只有默认配置的版本号"大于"磁盘上的版本号时才会重建**。
- **重建语义**（`rebuild_plugin_config_data` + 字段覆盖）：以最新默认配置为骨架，递归覆盖**类型匹配且仍然存在**
  的旧值，并**跳过 `config_version` 本身** → 用户自定义值保留，已删字段被清掉。
- **落盘层同样会清理残留**（Host `runner_main.py` `_save_plugin_config` + `_has_extra_config_keys`）：写回时
  若检测到「磁盘上有、而新配置里没有的键」，会放弃保注释的增量 merge（`_merge_plugin_config_document`），
  直接**整文件重写**。所以即使不升版本号，残留字段也会在下次配置写盘时被清掉——代价是丢掉 `config.toml` 里的注释。

### ⚠️ 埋雷：把 `config_version` 改小

若新版本把默认 `config_version` 从 `1.9.2` 改成 `1.2.0`（数值变小），`compare_versions` 恒为 False，
**此后任何 schema 升级都再也触发不了配置重建**，老字段会永久留在用户配置里。

**需要一次"清理式重建"时，应当上调版本号**（例如 `1.9.2 → 2.0.0`），
一次性重建移除废弃字段，同时把版本线拉回自己手里。
