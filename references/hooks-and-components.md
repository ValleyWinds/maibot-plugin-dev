# MaiBot Hook 系统与组件装饰器参考

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）
> SDK 侧源码：`maibot-plugin-sdk/maibot_sdk/components.py`、`maibot_sdk/types.py`
> Host 侧源码：`src/plugin_runtime/host/hook_dispatcher.py`、`host/component_registry.py`、
> `src/plugin_runtime/component_query.py`，以及 6 个 Hook 规格注册模块
> 官方文档：https://docs.mai-mai.org/plugin/

## 阅读顺序

- 要写 Hook 插件 → 先读「内置 Hook 完整清单」拿到逐字 kwargs 表，再看各 Hook 小节与「Host 侧执行与校验」。
- 要写组件插件 → 读「组件通用机制」与各装饰器小节。
- 改返回值语义（Command / Tool / EventHandler / HookHandler）→ 直接看对应小节的「Host 真实解包」。

---

## 组件通用机制

### 会话范围（chat_scope / allowed_session）

`@ReplyExtension` 是唯一在 SDK 装饰器上直接暴露 `chat_scope` / `allowed_session` 参数的组件类型
（`maibot_sdk/components.py` 的 `ReplyExtension` 签名，参数 `chat_scope: Literal["all", "group", "private"] = "all"`、
`allowed_session: list[str] | None = None`）。其余组件类型没有这两个装饰器参数，但 Host 的
`ComponentEntry`（`src/plugin_runtime/host/component_registry.py`）为**所有**条目保留这两个字段：

- `chat_scope`：`all` / `group` / `private`，由 `_normalize_chat_scope` 归一化。
- `allowed_session`：允许的会话 ID 集合；判定时用 `{session_id, group_id, "platform:group_id"}` 与它求交集，
  非空且不相交即视为不可用（`ComponentRegistry.check_component_enabled`）。

判定逻辑集中在 `check_component_enabled(component, session_id, is_group_chat, group_id, platform)`：
平台过滤 → 会话禁用集 → `chat_scope` → `allowed_session` → 最后返回 `enabled`。
**无上下文调用（不带 `session_id` / `is_group_chat`）时只做平台过滤**，用于组件清单查询。

### 启用 / 停用

- 组件级：`enabled` 取自组件 metadata（缺省 `True`），可被 `ComponentRegistry.toggle_component_status(full_name, enabled, session_id=None)`
  整体开关；带 `session_id` 时只对该会话生效（写入/移出 `disabled_session`）。
- 插件级：`toggle_plugin_status(plugin_id, enabled, session_id=None)` 批量操作该插件全部组件。
- 插件被禁用、卸载或重载时，组件条目随 `remove_components_by_plugin` 一并移除；`@HomeCard` 卡片同理从首页候选消失。
- `component.get_all_plugins` 用 `enabled_only=False` 列出全部组件，因此清单接口看得到已停用组件。

### 平台作用域（platforms）

`@Tool` 与 `@ReplyExtension` 共用 `_normalize_platforms`（`maibot_sdk/components.py`）：接受 `str` / `list[str]`，
去空白、转小写、去重；`None` / `[]` 表示不限平台；空字符串或非字符串元素直接抛 `ValueError`。
归一化结果只落在组件元数据里，**不进入模型调用参数 Schema**。
Host 侧 `ToolEntry` / `ReplyExtensionEntry` 各自解析 `platforms`，在 `check_component_enabled` 中与当前
`platform` 比较，不匹配即视为不可用（不展示、不可执行）。

⚠️ `platforms` 需要配套 Host 支持：旧 Host 忽略该字段，限制静默不生效，依赖平台权限的操作仍应由插件自行校验 `platform`。

---

## 内置 Hook 完整清单

共 **22 个** Hook，由 `src/plugin_runtime/hook_catalog.py` 聚合的 6 个注册函数声明：
`register_chat_hook_specs`（chat/message_receive/bot.py）、`register_send_service_hook_specs`（services/send_service.py）、
`register_emoji_hook_specs`（emoji_system/emoji_manager.py）、`register_expression_hook_specs`（learners/expression_learner.py）、
`register_jargon_hook_specs`（learners/jargon_miner.py）、`register_maisaka_hook_specs`（maisaka/chat_loop_service.py）。

| # | Hook 名 | 声明处（符号） | 触发处（符号） | required 字段 | 可选字段 | abort | 改 kwargs | 默认超时 |
|---|---------|----------------|----------------|---------------|----------|-------|-----------|----------|
| 1 | `chat.receive.before_process` | `register_chat_hook_specs` | `ChatBot.receive_message` → `ChatBot._invoke_message_hook` | `message` | — | ✅ | ✅ | 0 |
| 2 | `chat.receive.after_process` | `register_chat_hook_specs` | `ChatBot.receive_message` → `ChatBot._invoke_message_hook` | `message` | — | ✅ | ✅ | 0 |
| 3 | `chat.command.before_execute` | `register_chat_hook_specs` | `ChatBot._process_commands` → `ChatBot._invoke_message_hook` | `message`、`command_name`、`plugin_id`、`matched_groups` | — | ✅ | ✅ | 0 |
| 4 | `chat.command.after_execute` | `register_chat_hook_specs` | `ChatBot._process_commands` → `ChatBot._invoke_message_hook` | `message`、`command_name`、`plugin_id`、`matched_groups`、`success`、`intercept_message_level`、`continue_process` | `response` | ❌ | ✅ | 0 |
| 5 | `emoji.maisaka.before_select` | `register_emoji_hook_specs` | `send_emoji_for_maisaka`（emoji_system/maisaka_tool.py，跨文件） | `stream_id`、`requested_emotion`、`reasoning`、`context_texts`、`sample_size` | `abort_message` | ✅ | ✅ | 5000 |
| 6 | `emoji.maisaka.after_select` | `register_emoji_hook_specs` | `send_emoji_for_maisaka`（emoji_system/maisaka_tool.py，跨文件） | `stream_id`、`requested_emotion`、`reasoning`、`context_texts`、`sample_size`、`matched_emotion` | `selected_emoji`、`selected_emoji_hash`、`abort_message` | ✅ | ✅ | 5000 |
| 7 | `emoji.register.after_build_description` | `register_emoji_hook_specs` | `EmojiManager.build_emoji_description` | `emoji`、`description`、`image_format` | — | ✅ | ✅ | 5000 |
| 8 | `expression.select.before_select` | `register_expression_hook_specs` | `MaisakaExpressionSelector.select_for_reply`（跨文件） | `chat_id`、`chat_info`、`max_num`、`think_level` | `target_message`、`reply_reason` | ✅ | ✅ | 5000 |
| 9 | `expression.select.after_selection` | `register_expression_hook_specs` | `MaisakaExpressionSelector.select_for_reply`（跨文件） | `chat_id`、`chat_info`、`max_num`、`think_level`、`selected_expressions`、`selected_expression_ids` | `target_message`、`reply_reason` | ✅ | ✅ | 5000 |
| 10 | `expression.learn.after_extract` | `register_expression_hook_specs` | `ExpressionLearner._run_learning_batch` | `session_id`、`message_count`、`expressions`、`jargon_entries` | — | ✅ | ✅ | 5000 |
| 11 | `expression.learn.before_upsert` | `register_expression_hook_specs` | `ExpressionLearner._run_learning_batch` | `session_id`、`situation`、`style` | — | ✅ | ✅ | 5000 |
| 12 | `jargon.extract.before_persist` | `register_jargon_hook_specs` | `JargonMiner.process_extracted_entries` | `session_id`、`session_name`、`entries` | — | ✅ | ✅ | 5000 |
| 13 | `jargon.inference.before_finalize` | `register_jargon_hook_specs` | `JargonMiner.infer_meaning` | `session_id`、`session_name`、`content`、`count`、`raw_content_list`、`comparison_result`、`is_jargon`、`meaning`、`is_complete`、`last_inference_count` | — | ✅ | ✅ | 5000 |
| 14 | `send_service.after_build_message` | `register_send_service_hook_specs` | `_send_to_target_with_message` → `_invoke_send_hook` | `message`、`stream_id`、`processed_plain_text`、`typing`、`set_reply`、`storage_message`、`show_log` | — | ✅ | ✅ | 5000 |
| 15 | `send_service.before_send` | `register_send_service_hook_specs` | `_send_via_platform_io` → `_invoke_send_hook` | `message`、`typing`、`set_reply`、`storage_message`、`show_log` | `reply_message_id` | ✅ | ✅ | 5000 |
| 16 | `send_service.after_send` | `register_send_service_hook_specs` | `_send_via_platform_io` → `_invoke_send_hook` | `message`、`sent`、`typing`、`set_reply`、`storage_message`、`show_log` | `reply_message_id` | ❌ | ❌ | 5000 |
| 17 | `maisaka.planner.before_request` | `register_maisaka_hook_specs` | `MaisakaChatLoopService.chat_loop_step` | `items`、`item_schema_version`、`tool_definitions`、`selected_history_count`、`built_message_count`、`selection_reason`、`session_id` | — | ❌ | ✅ | 6000 |
| 18 | `maisaka.planner.after_response` | `register_maisaka_hook_specs` | `MaisakaChatLoopService.chat_loop_step` | `output_items`、`item_schema_version`、`selected_history_count`、`built_message_count`、`selection_reason`、`session_id`、`prompt_tokens`、`completion_tokens`、`total_tokens` | — | ❌ | ✅ | 6000 |
| 19 | `maisaka.replyer.before_request` | `register_maisaka_hook_specs` | `BaseMaisakaReplyGenerator.generate_reply_with_context`（跨文件） | `session_id`、`request_type`、`task_name`、`model_name`、`extra_prompt`、`attempt`、`retry_count`、`max_retries`、`reply_message_id`、`reply_reason`、`selected_expression_ids`、`reply_tool_args` | — | ❌ | ✅ | 6000 |
| 20 | `maisaka.replyer.before_model_request` | `register_maisaka_hook_specs` | `BaseMaisakaReplyGenerator._invoke_before_model_request_hook`（跨文件） | `items`、`item_schema_version`、`session_id`、`request_type`、`task_name`、`requested_model_name`、`selected_model_name`、`selected_model_visual`、`attempt`、`retry_count`、`max_retries`、`reply_message_id`、`reply_reason`、`selected_expression_ids`、`reply_tool_args` | — | ❌ | ✅ | 6000 |
| 21 | `maisaka.replyer.after_response` | `register_maisaka_hook_specs` | `BaseMaisakaReplyGenerator.generate_reply_with_context`（跨文件） | `response`、`output_items`、`item_schema_version`、`session_id`、`request_type`、`task_name`、`requested_model_name`、`attempt`、`retry_count`、`max_retries`、`reply_message_id`、`selected_expression_ids`、`reply_tool_args`、`prompt_tokens`、`completion_tokens`、`total_tokens` | `retry`、`retry_reason`、`matched_regex`、`matched_regex_pattern`、`matched_regex_description` | ❌ | ✅ | 6000 |
| 22 | `maisaka.reply.before_post_process` | `register_maisaka_hook_specs` | `_invoke_before_post_process_hook`（maisaka/builtin_tool/reply.py，跨文件） | `response`、`session_id`、`reply_message_id`、`reply_tool_args`、`skip_post_process`、`enable_splitter`、`enable_chinese_typo` | — | ❌ | ✅ | 6000 |

> ⚠️ `emoji.register.after_build_emotion`、`jargon.query.before_search`、`jargon.query.after_search`
> 在主程序源码中**不存在**（零命中），订阅会直接注册失败。

### 超时与 allowAbort 汇总

- `timeoutMs = 0` 的 4 个（全部 chat 链）表示「用 Hook 默认值」；Hook 默认值也是 0 时，回退到
  `HookDispatcher._get_default_timeout_ms()`，即全局配置 `plugin_runtime.hook_blocking_timeout_sec`（默认 60 秒）。
- `allow_abort=False` 的 8 个：`chat.command.after_execute`、`send_service.after_send`、`maisaka.planner.before_request`、
  `maisaka.planner.after_response`、`maisaka.replyer.before_request`、`maisaka.replyer.before_model_request`、
  `maisaka.replyer.after_response`、`maisaka.reply.before_post_process`。其余 14 个为 `True`。
- `allow_kwargs_mutation=False` 的只有 `send_service.after_send` 一个，其余 21 个为 `True`。

### 触发点与声明点不在同一文件的 6 个

写插件时最容易踩的不是字段名，而是**去错了文件找触发点**，从而误判「这个 Hook 到底什么时候跑」：

| Hook | 声明处 | 触发处 | 实践含义 |
|------|--------|--------|----------|
| `emoji.maisaka.before_select` | emoji_system/emoji_manager.py | emoji_system/maisaka_tool.py `send_emoji_for_maisaka` | 表情**发送**路径，不是表情注册路径；`abort` 会让本次表情不发送 |
| `emoji.maisaka.after_select` | 同上 | 同上 | 选中之后、发送之前；改 `selected_emoji_hash` / `selected_emoji` 可替换表情 |
| `expression.select.before_select` | learners/expression_learner.py | chat/replyer/maisaka_expression_selector.py `select_for_reply` | 每轮回复选择表达方式时触发，不是学习时 |
| `expression.select.after_selection` | 同上 | 同上 | 可改 `selected_expressions` / `selected_expression_ids` 影响最终注入 |
| `maisaka.replyer.before_request` / `before_model_request` / `after_response` | maisaka/chat_loop_service.py | chat/replyer/maisaka_generator_base.py | 生成回复的调用方在 replyer 侧，schema 却由 chat_loop_service 声明 |
| `maisaka.reply.before_post_process` | maisaka/chat_loop_service.py | maisaka/builtin_tool/reply.py `_invoke_before_post_process_hook` | 回复**工具**内部调用，晚于 replyer 出稿 |

⚠️ Host 的 `HookDispatcher.invoke_hook` 只透传 kwargs，**不按 schema 过滤**。因此实际可读到的键可能多于上表。
已知一例：`expression.select.before_select` 的调用处除 schema 字段外还传入了 `session_id`、`chat_history`、
`reply_message`、`reply_tool_args`、`candidates`。**依赖这些未声明键等于依赖实现细节**，换版本可能静默失效。

---

## Hook 处理器（@HookHandler）

### 装饰器签名

```python
from maibot_sdk import HookHandler
from maibot_sdk.types import HookMode, HookOrder, ErrorPolicy

@HookHandler(
    hook: str,                              # 订阅的命名 Hook 名称（必填）
    *,
    name: str = "",                         # 组件名称，留空用方法名
    description: str = "",
    mode: HookMode = HookMode.BLOCKING,     # BLOCKING / OBSERVE
    order: HookOrder = HookOrder.NORMAL,    # EARLY / NORMAL / LATE
    timeout_ms: int = 0,                    # 超时毫秒，0=用 Hook 默认值
    error_policy: ErrorPolicy = ErrorPolicy.SKIP,  # ABORT / SKIP / LOG
    **metadata: Any,
)
```

`hook` 为空或只有空白时 `ValueError`；`name` 留空取被装饰方法名，方法名为空也报错。

### 处理模式与顺序

| 模式 | 特点 | 返回值 |
|------|------|--------|
| `BLOCKING` | 串行执行，可改 kwargs | `{"action": "continue"/"abort", "modified_kwargs": kwargs}` |
| `OBSERVE` | 后台并发，只读旁路 | 返回值被忽略 |

执行顺序（`HookDispatcher._build_sort_key`）：`BLOCKING` 先于 `OBSERVE` → `EARLY` → `NORMAL` → `LATE`
→ 内置插件先于第三方插件 → 同槽位按 `plugin_id` 与处理器名稳定排序。
多个 blocking 处理器串行传递**同一份** kwargs，后一个看到的是前一个 `modified_kwargs` 的结果。

### 异常处理策略

| 策略 | 行为 |
|------|------|
| `ABORT` | 异常时终止当前 Hook 调用（仅当该 Hook `allow_abort=True` 才能声明） |
| `SKIP` | 记录日志，跳过此处理器继续（默认） |
| `LOG` | 记录日志，继续执行后续 hook |

### 处理器返回值（BLOCKING）

Runner 侧归一化（`runner/runner_main.py` 的 `_handle_hook_invoke`）只做类型兜底，不校验 action 取值：

- `None` → `{"success": True, "action": "continue"}`
- dict → 读 `action`（`str(...).strip().lower()` 后原样透传，合法与否都不拦、Runner 侧不打日志）、
  `modified_kwargs`、`custom_result`
- 其它任何类型 → `{"success": True, "action": "continue", "custom_result": raw}`

action 的合法性校验集中在 Host 侧：`HookDispatcher._invoke_handler` 对 Runner 回包的 action 必过
`_normalize_action`（`src/plugin_runtime/host/hook_dispatcher.py`）——`continue` / `abort`
（忽略大小写与首尾空白）原样保留，空值静默回落 `continue`；
**非法 action 会被规范化为 `continue` 并由 Host 打 warning**：`logger.warning(f"未知的 Hook action: {raw_value}，已按 continue 处理")`。
即非法值最终确实按放行处理，但日志里一定有这条 Host 侧 warning，不能据此认为「无任何提示」。

Host 侧 `HookDispatcher._merge_blocking_result` 的生效规则：

- `modified_kwargs` 只接受 `dict`，非 dict 打 warning 忽略；`allow_kwargs_mutation=False` 的 Hook 直接忽略并记 error。
- 生效时是 `dispatch_result.kwargs = dict(modified_kwargs)` **整体替换**，不是逐键 merge——改一个键也必须把整份 kwargs 带回去。
- `action="abort"` 只在 `allow_abort=True` 时生效，否则打 warning 并记 error。

```python
# 放行
return None

# 放行并修改参数（整份带回）
return {"action": "continue", "modified_kwargs": kwargs}

# 中止调用链（仅 allow_abort=True 的 Hook 有效）
return {"action": "abort"}
```

### 注册期校验（三条硬约束）

`ComponentRegistry._validate_hook_handler_entry` 在插件注册阶段校验，不合法直接注册失败：

1. Hook 名必须已注册（未注册 → `ComponentRegistrationError`）。
2. `mode` 必须匹配 Hook 能力（`allow_blocking` / `allow_observe`）。
3. `error_policy="abort"` 必须该 Hook `allow_abort=True`。

本地复核 Hook 名单：

```bash
grep -rhoE '"[a-z_]+(\.[a-z_]+){2,}"' --include=*.py MaiBot/src/plugin_runtime/ | sort -u
```

---

## 各 Hook 小节：用途与必读要点

### chat.receive.before_process / chat.receive.after_process

- **before_process**：入站消息执行 `SessionMessage.process()` 之前；`message` 是序列化后的 `SessionMessage` dict，
  `user_id` 嵌套在 `message_info.user_info.user_id`。`abort` = 这条消息不再进入后续链路。
- **after_process**：`process()` 完成后（此时才有识别出的图片/表情文本描述）。
- 两个 Hook 都只收 `message` 一个键；改写消息回带 `modified_kwargs={"message": {...}}`，Host 会尝试反序列化，
  失败则 warning 并沿用原消息。
- 图片自动注释、入站改写类插件挂这里；注意 `timeoutMs=0`，实际超时走全局默认 60 秒，别在 Hook 里跑重推理。

### chat.command.before_execute / chat.command.after_execute

- **before_execute**：命令正则匹配成功、真正执行前。`abort` 会让命令**不执行**，消息按普通消息继续。
- **after_execute**：命令执行结束后。`success` / `response` / `intercept_message_level` / `continue_process`
  都是**可改的决策值**，Host 在 `ChatBot._process_commands` 中**各自独立读回**：
  `intercept_message_level` 经 `_coerce_int` 强制回整数、`continue_process` 单独 `bool()` 判定——
  只改 `intercept_message_level` **不会**自动翻转 `continue_process`，要改拦截行为必须两者同步改。
  它不允许 abort，但允许改 kwargs——想改命令结果就从这里下手。
- 权限检查发生在 Hook 之前（`command_info.permission == "operator"` 且无权限时直接拦截，不进 Hook）。

### send_service.after_build_message / before_send / after_send

- **after_build_message**：出站 `SessionMessage` 构建完成。`abort` = 整条消息不发送（连 Platform IO 都不调）。
- **before_send**：真正调用 Platform IO 之前，`typing` / `set_reply` / `storage_message` / `show_log` / `reply_message_id`
  都可改。`abort` = 放弃本次发送。
- **after_send**：发送结束（含失败），`sent` 表示结果。**不允许 abort、不允许改 kwargs**——纯观察位，
  改写返回值会被忽略并记 error。统计、落库、监控类插件挂这里。

### emoji.maisaka.before_select / after_select

- 触发点在 `send_emoji_for_maisaka`（emoji_system/maisaka_tool.py），即**表情发送路径**。
- `before_select` 可改 `requested_emotion` / `reasoning` / `context_texts` / `sample_size`；`abort` 时不发表情，
  `abort_message` 会作为失败提示回传。
- `after_select` 可改 `selected_emoji_hash` 或 `selected_emoji` 来替换最终表情；`matched_emotion` 只读投影。
- `sample_size` 是采样数量，触发处默认 20；Hook 侧用 `_coerce_positive_int` 解析，非正数回落默认。

### emoji.register.after_build_description

- 触发点 `EmojiManager.build_emoji_description`：表情包描述生成并通过内容审查后。
- 只有 `emoji`、`description`、`image_format` 三个键；改 `description` 即改注册时的描述文本，`abort` 拒绝本次注册。
- ⚠️ 同名的情绪标签 Hook `emoji.register.after_build_emotion` 在源码中不存在，别订阅。

### expression.select.before_select / after_selection

- 触发点 `MaisakaExpressionSelector.select_for_reply`，**每轮回复选表达方式时**，不是学习时。
- `before_select`：`chat_id` / `chat_info` / `max_num` / `think_level` 必到；`abort` = 本轮不用表达方式。
  调用处还会读回 `candidates`、`max_num` 做候选过滤（这两个键不在 schema 里）。
- `after_selection`：多出 `selected_expressions` / `selected_expression_ids`，改写即改写最终注入回复的表达方式。
- `jargon_entries` 在 expression 链里是兼容字段，恒为空列表（黑话已由独立 learner 处理）。

### expression.learn.after_extract / before_upsert

- 触发点 `ExpressionLearner._run_learning_batch`：学习批处理内部。
- `after_extract`：解析出候选后，可改 `expressions` 或 `abort` 终止本轮学习。
- `before_upsert`：写库前最后一刻，可改 `situation` / `style` 或跳过本条写入。

### jargon.extract.before_persist / jargon.inference.before_finalize

- 触发点分别是 `JargonMiner.process_extracted_entries` 与 `JargonMiner.infer_meaning`。
- `before_persist`：去重后的 `entries` 写库前，可改列表或跳过持久化。
- `before_finalize`：推断完成、写回前，10 个字段全是判定与含义结果（`is_jargon` / `meaning` / `is_complete` /
  `last_inference_count` 等），改写即改写写回数据库的内容。
- ⚠️ `jargon.query.*` 系列在源码中不存在，零命中。

### maisaka.planner.before_request / after_response

- 触发点 `MaisakaChatLoopService.chat_loop_step`，即 Planner 每一步向模型请求前后。
- `before_request` 的 `items` 是序列化后的 Context Items；回带时 `item_schema_version` 必须原样不动，
  否则 Host 直接拒收整份 items（`src/plugin_runtime/hook_payloads.py` 的版本校验）。
- `after_response` 的 `output_items` 同理；压制/注入类插件（睡眠、静默期）主要靠改这两个字段实现。
- ⚠️ **planner 链没有 `extra_prompt`**，想影响回复内容请用 `maisaka.replyer.before_request`。

### maisaka.replyer.before_request

触发点 `BaseMaisakaReplyGenerator.generate_reply_with_context`（跨文件，schema 声明在 chat_loop_service.py）。

kwargs 共 12 个，全部 required：

`session_id`、`request_type`、`task_name`、`model_name`、`extra_prompt`、`attempt`、`retry_count`、
`max_retries`、`reply_message_id`、`reply_reason`、`selected_expression_ids`、`reply_tool_args`

- **`extra_prompt` 在这里**（str）。Host 读回后包成 `【额外回复要求】\n{extra_prompt}` 追加进回复要求，
  与 `【重生成约束】` 拼在一起（`BaseMaisakaReplyGenerator._build_reply_requirements`）。
  多插件共存时应当**追加**而不是覆盖：
  ```python
  kwargs["extra_prompt"] = (kwargs.get("extra_prompt") or "") + " 追加内容"
  return {"action": "continue", "modified_kwargs": kwargs}
  ```
- `task_name` / `model_name` 也可改写：`task_name` 决定用哪个模型任务，`model_name` 留空时按任务策略选模型。
- `reply_tool_args` 是 reply 工具除 `msg_id` / `set_quote` 外透传给 replyer 的额外参数，Host 只在该值为 dict 时读回。
- ⚠️ 这个 Hook 不允许 abort；也别指望 `model_config` / `reference_info` / `tool_definitions` / `max_tool_rounds`
  这些名字——它们在当前版本 schema 中不存在，写进 `modified_kwargs` 不会报错，只会被无视。

### maisaka.replyer.before_model_request

触发点 `BaseMaisakaReplyGenerator._invoke_before_model_request_hook`（跨文件）。

kwargs 15 个，全部 required：`items`、`item_schema_version`、`session_id`、`request_type`、`task_name`、
`requested_model_name`、`selected_model_name`、`selected_model_visual`、`attempt`、`retry_count`、
`max_retries`、`reply_message_id`、`reply_reason`、`selected_expression_ids`、`reply_tool_args`。

- 这是**构造完 messages 之后、真正发请求之前**的最后一站，改 `items` 就是改实际发给模型的上下文。
- ⚠️ 模型名字段叫 `requested_model_name`（另加 `selected_model_name` / `selected_model_visual`），
  **不是** `before_request` 的 `model_name`。
- `items` 回带同样受 `item_schema_version` 校验；反序列化失败时 Host warning 并继续用原消息。

### maisaka.replyer.after_response

触发点 `BaseMaisakaReplyGenerator.generate_reply_with_context`（跨文件）。

- 16 个 required：`response`、`output_items`、`item_schema_version`、`session_id`、`request_type`、`task_name`、
  `requested_model_name`、`attempt`、`retry_count`、`max_retries`、`reply_message_id`、
  `selected_expression_ids`、`reply_tool_args`、`prompt_tokens`、`completion_tokens`、`total_tokens`。
- 5 个 optional：`retry`（置 `True` 要求重新生成）、`retry_reason`（重新生成的约束原因）、
  `matched_regex`、`matched_regex_pattern`、`matched_regex_description`（触发重新生成的规则信息）。
- `response` 是正文的兼容只读投影，改写只替换正文 Item；`output_items` 改动受 schema 版本校验。
- 不允许 abort；重试次数受 `max_retries` 约束，别在 `retry` 上做无界循环。

### maisaka.reply.before_post_process

触发点 `_invoke_before_post_process_hook`（maisaka/builtin_tool/reply.py，跨文件）。

- 7 个 required：`response`、`session_id`、`reply_message_id`、`reply_tool_args`、
  `skip_post_process`、`enable_splitter`、`enable_chinese_typo`。
- 三个策略字段必须是**布尔类型**，Host 用 `_require_hook_bool` 强校验，非布尔直接抛错。
- 可完全跳过文本后处理（`skip_post_process=True`），或分别关闭拆分与中文错别字注入。
- 该 Hook 不影响富回复附件组装，也不允许 abort。

---

## Tool 组件（@Tool）

```python
from maibot_sdk import Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

@Tool(
    "my_tool",                     # 位置参数：名称
    description="工具描述",
    brief_description="简短描述",
    detailed_description="详细描述",
    parameters=[
        ToolParameterInfo(
            name="query",
            param_type=ToolParamType.STRING,
            description="搜索内容",
            required=True,
        ),
    ],
    *,
    platforms: str | list[str] | None = None,   # 平台作用域
    **metadata: Any,
)
async def handle_tool(self, query: str, **kwargs):
    return {"success": True, "result": "..."}
```

- `description` 缺省时用 `brief_description`，再缺省用 `工具 {name}`；`brief_description` / `detailed_description`
  属兼容字段，新代码写 `description` 即可。
- 参数也支持 dict 声明（兼容旧式）：`parameters={"query": {"type": "string", "description": "..."}}`；
  dict 里带 `required: True` 的项会进 JSON Schema 的 `required`。
- **工具参数平铺进 kwargs**：Host 把 LLM 生成的 `function_args` 直接展开调用处理函数，
  用显式签名（`query: str = ""`）接收即可；另有 Host 注入的上下文字段
  （`stream_id` / `chat_id` / `group_id` / `user_id` / `platform`，有锚点消息时还有 `group_id` / `user_id`）。

### 返回值与 Host 包装

Runner 把返回值原样放进 `InvokeResultPayload`；Host `_build_tool_executor` 再包一层：
dict 原样返回，非 dict 包装成 `{"content": str(result)}`。

真正决定语义的是 `ComponentQueryService._parse_tool_invoke_result`：

| 返回形态 | Host 处理 |
|----------|-----------|
| `dict` | 读 `success`（缺省 `True`）、`content` 或 `message` 作为给 LLM 的正文、`error` 作为失败信息、`stop_after_execution` |
| `(bool, str)` 形式的 list/tuple | `success = result[0]`，`result[1]` 作正文/错误信息 |
| 其他 | `success=True`，`content = str(result)` |

- `stop_after_execution: True` 表示当前工具批次执行完后结束本轮 Planner，等新消息再继续；
  **必须是布尔值**，其他类型整次调用按失败处理并报协议错误。
- **把图片交给后续流程**：不要把 base64 塞进 `content`。文字放 `content`，图片本体放 `content_items`：

  ```python
  return {
      "success": True,
      "content": "这是截图，已交给模型观察",
      "content_items": [
          {"content_type": "image", "data": base64_str, "mime_type": "image/png", "name": "screenshot.png"},
      ],
  }
  ```

  Host 用 `_parse_tool_content_items` 解析，`content_type` 只认
  `text` / `image` / `audio` / `resource_link` / `resource` / `binary` / `unknown`（其余归为 `unknown`），
  并读取 `text` / `data` / `base64` / `mime_type` / `uri` / `name` / `description` / `metadata`。
  随后 reasoning engine 会把媒体项拆成紧跟 tool result 的 user message（`_append_tool_result_media_messages`），
  图片经 `_decode_tool_result_base64_data` 解码后作为图片组件进入上下文；
  `content_type` 非媒体的项只进文本投影。
- `content_items` 只接受 list；非 list 静默解析为空列表。

---

## Command 组件（@Command）

```python
from maibot_sdk import Command

@Command(
    "hello",                    # 位置参数：名称，惯例不带前导斜杠（name 不参与匹配，见文末）
    description="打招呼",
    pattern=r"^/hello\b",       # 正则匹配；SDK 默认 ""，不传且不配 aliases 则永不触发
    aliases=["/hi"],            # 可选别名（按用户要输入的完整字面写，通常带斜杠）
    permission="operator",      # 可选，经 **metadata 透传
    **metadata: Any,
)
async def handle_hello(self, **kwargs):
    stream_id = kwargs["stream_id"]
    await self.ctx.send.text("你好！", stream_id)
    return True, "已发送", 2  # (success, response, intercept_message_level)
```

**Host 实际下发的 kwargs**（`ComponentQueryService._build_command_executor`，共 7 键 + 2 个条件键）：
`text`（= `processed_plain_text`）、`stream_id`（= `session_id`）、`group_id`、`platform`、`user_id`、
`is_local_operator`（bool）、`matched_groups`（dict）；有消息对象时附 `message`（`SessionMessage` 序列化 dict，
user_id 嵌套在 `message_info.user_info.user_id`），插件有配置时附 `plugin_config`。

> ⚠️ 顶层没有 `raw_message`；原始消息内容在 `message` dict 里。

**返回值必须三元组** `(success, response, intercept_message_level)`：

- `success: bool` — ⚠️ **Host 侧实际忽略这个值**。
- `response: str` — 给系统的日志描述，不是发给用户的（回复要自己调 `ctx.send.*`）。
- `intercept_message_level: int` — 非 0 拦截消息（阻止走 Maisaka）。

**Host 侧真实解包**（`src/plugin_runtime/component_query.py` 的 `_executor`）：

```python
success   = bool(payload.get("success", False))          # 来自 RPC 是否成功，不是插件的 result[0]
intercept = bool(metadata.get("intercept_message_level", 0))
if isinstance(result, (list, tuple)) and len(result) >= 3:
    response_text = None if result[1] is None else str(result[1])   # 只看 result[1]
    intercept     = bool(result[2])                                  # 只看 result[2]
else:
    response_text = None if result is None else str(result)          # 非三元组 → str(整个 result)
```

三条推论：

1. **`result[0]` 被彻底忽略**。Runner 固定回包 `InvokeResultPayload(success=True, result=result)`，
   那个 `success=True` 只表示「调用没抛异常」。所以 `return (False, "参数错误", 1)` 也会被当成
   **成功 + 拦截**。别在 `success` 位放业务判断，失败语义靠 `response` 文本或自行发消息表达。
2. **非三元组（含 2 元组、裸字符串）会掉进 else 分支**：`response = str(整个 result)`。
   `return "你好"` → 日志里出现 `你好`；`return (True, "x")` → 日志变成 `(True, 'x')`。**必须返回 3 元组。**
3. 第三项用 `bool()` 判定，**任意 truthy 值都算拦截**（`True` / `1` / `2` / 非空字符串都行）。

消费方 `ChatBot._process_commands` 是 `continue_process = not bool(intercept_message_level)`——
语义确实是**拦截等级**，非 0 即拦截，不是官方文档写的「权重」。

**`permission="operator"`**：仅操作员（`bot_config.toml` 的 `[plugin].permission`，格式 `platform:id`，
或 `[plugin.command_permissions.<plugin>.<command>]` 的 `allow_users` / `allow_chats`）可触发；
无权限时 Host 直接回复「你没有权限使用此命令」并拦截（`silent_permission_denied` 可关掉提示）。
**会消耗模型资源的命令务必加**，防止群成员刷额度。

**正则捕获组**：

```python
@Command("echo", pattern=r"^/echo\s+(?P<text>.+)$")
async def handle_echo(self, **kwargs):
    text = kwargs.get("matched_groups", {}).get("text", "")
    ...
```

### 匹配规则与 `name` 的实际用途

匹配逻辑集中在 `ComponentRegistry.find_command_by_text`（`src/plugin_runtime/host/component_registry.py`），
只看两样东西：`pattern` 编译出的正则（Host 用 `re.search`，**不是**锚定匹配——正则自身要写 `^` 才能限定句首）
和 `aliases` 的字面前缀匹配（`text.startswith(alias)`，不是正则）。**`name` 完全不参与匹配**：
Host 从不拿 `name` 参与拼接或构造匹配文本，name 带斜杠也不影响触发。

`name` 的真实用途是把它的值**原样**用作标识符：

- 权限键与停用判定：`ChatBot._process_commands`（`src/chat/message_receive/bot.py`）用
  `f"{plugin_name}.{command_name}"` 查 `command_permissions`（`has_command_permission`，`src/core/local_operator.py`）
  并做 `is_command_disabled` 检查——name 带斜杠就得在 `bot_config.toml` 里写带斜杠的键。
- 会话级禁用列表：`global_announcement_manager.get_disabled_chat_commands(session_id)` 用**裸** `command_name` 判定。
- `chat.command.before_execute` / `after_execute` 载荷里的 `command_name`。
- WebUI 命令清单：`src/webui/routers/plugin/runtime_routes.py` 的 `list_runtime_commands` 返回**原样** `name`，
  但 `id` 拼成 `plugin_id.name`——实测 `name="/probe_slash"` 会得到 `probe.slash-name./probe_slash`（中间是 `./`）。
  **前端「配置 → 命令权限」页会在渲染时再加一个 `/`**：`dashboard/src/routes/config/bot/CommandPermissions.tsx`
  用 `/{command.name}`（列表项）与 `/{selectedCommand.name}`（详情标题）渲染，斜杠是 JSX 裸文本而非字符串常量，
  所以只 grep `'/'` 字面量会漏掉。结果就是 `name="probe_plain"` 显示 `/probe_plain`（这正是规范假定前端补斜杠的由来），
  而 `name="/probe_slash"` 显示成 **`//probe_slash`**。

所以「不带前导斜杠」有**两条真实代价**，不是纯惯例：① 权限键 / 禁用列表 / Hook 载荷里的标识符变成
`plugin_id./name` 这种带 `./` 的怪串；② WebUI 命令权限页显示成 `//name`。Host 侧匹配本身不看 `name`，
带斜杠照样能触发——坏的是标识符与界面呈现，不是触发。

---

## API 组件（@API）

```python
from maibot_sdk import API

@API(
    "my_api",                # 位置参数：名称
    description="API 描述",
    version="1",
    public=False,            # True 才能被其他插件调用
    **metadata: Any,
)
async def handle_api(self, **kwargs):
    return "返回值"
```

其他插件调用：`await ctx.api.call("plugin-id.api_name", arg1="value")`。
跨插件调用时 Host 会再包一层 `{"success": True, "result": ...}` 返回给调用方
（`capabilities/components.py` 的 `_cap_api_call`）。`public=False` 的 API 不可被跨插件调用。

---

## EventHandler 组件（@EventHandler）

```python
from maibot_sdk import EventHandler
from maibot_sdk.types import EventType

@EventHandler(
    "on_start",                       # 位置参数：名称
    description="",
    event_type=EventType.ON_START,
    intercept_message=False,          # True=阻塞等待并可用返回值中断, False=异步 fire-and-forget
    weight=0,                         # 越大越先执行
    **metadata: Any,
)
async def handle_start(self, **kwargs):
    ...
```

### EventType 的实际发射现实

`maibot_sdk.types.EventType` 有 11 个值（`UNKNOWN` 外加 10 个），但**只有 2 个在 Host 源码里有真实发射点**：

| 值 | 是否有发射点 |
|----|--------------|
| `ON_START` | ✅ `src/main.py` 的 `event_bus.emit(event_type=EventType.ON_START)` |
| `ON_STOP` | ✅ `src/runtime.py` 停机流程、`src/webui/routers/system.py` 重启前，各一处 `event_bus.emit` |
| `ON_MESSAGE` | ❌ 分发调用在 `src/chat/message_receive/bot.py` 被整段注释掉 |
| `ON_MESSAGE_PRE_PROCESS` / `ON_PLAN` / `POST_LLM` / `AFTER_LLM` / `POST_SEND_PRE_PROCESS` / `POST_SEND` / `AFTER_SEND` | ❌ 无发射点 |
| `UNKNOWN` | ❌ 哨兵值 |

**实践中只有 `ON_START` 和 `ON_STOP` 能收到事件。** 需要盯消息链路请改用 Hook
（`chat.receive.*` / `send_service.*`），需要盯命令链用 `chat.command.*`。
`EventType` 只作为声明存在，写 `event_type=EventType.ON_MESSAGE` 不会报错，只是永远不触发。

### 返回值——官方示例与官方文档在这里都是错的

Runner 侧归一化（`runner/runner_main.py` 的 `_handle_event_invoke`）只认这几种返回：

- `None` → 继续处理（`continue_processing=True`）
- **dict** → 读 `continue_processing`（并兼容 `{"blocked": True}` 等价 `continue_processing=False`）、
  `modified_message`、`custom_result`
- **其它任何类型** → 整个塞进 `custom_result`，`continue_processing` 恒为 `True`

Host 侧 `EventDispatcher` 只看 `continue_processing` 与 `modified_message` 决定是否中断，
`custom_result` 只进历史记录。

```python
# ❌ 官方 hello_world 示例的 5 元组——不拦截，整个元组被塞进 custom_result 无人解析
return True, True, "消息已打印", None, None

# ❌ 官方文档 event-handlers.md 的写法——"intercepted" 不是运行时可认识的 key
return {"intercepted": True, "reason": "spam"}

# ✅ 真正生效的拦截写法（拦截 + 可选改写消息）
return {"continue_processing": False, "modified_message": modified_msg_dict}
# ✅ 旧版兼容写法，同样拦截
return {"blocked": True}
```

非拦截型（`intercept_message=False`）处理器异步执行，返回值被忽略。
参数用显式签名接收更安全（如 `message: Any = None, stream_id: str = ""`）；
`message` 是序列化 dict，user_id 嵌套在 `message_info.user_info.user_id`，取字段要 `.get()` 容错。

---

## LLMProvider 组件（@LLMProvider）

```python
from maibot_sdk import LLMProvider

@LLMProvider(
    "my_custom_llm",       # 位置参数：client_type，对应模型配置 api_providers[].client_type
    name="My Custom LLM",
    description="自定义 LLM Provider",
    version="1.0.0",
    **metadata: Any,
)
async def handle_llm(self, **kwargs):
    ...
```

**双向声明**：`_manifest.json` 的 `llm_providers` 与 `@LLMProvider` 必须同时声明，
且 `declared_client_types` 与代码注册的 `registered_client_types` 排序后必须完全相等，否则注册失败
（`runner/runner_main.py` 的 `llm_providers` 一致性校验）。
处理器返回 `{"content": ...}` 等 dict；两个插件使用相同 `client_type` 会被双方禁载。

---

## MessageGateway 组件（@MessageGateway）

```python
from maibot_sdk import MessageGateway

@MessageGateway(
    "duplex",        # 位置参数：send / receive / duplex（大小写不敏感，recive/recv 也接受）
    name="my_gateway",
    platform="qq",
    protocol="napcat",
    account_id="",
    scope="",
    **metadata: Any,
)
async def handle_gateway(self, **kwargs):
    ...
```

- `route_type="receive"` 只参与入站注入；`"duplex"` 同时承担入站与出站。
- 仅声明还不够：链路可用时必须调用 `ctx.gateway.update_state(..., ready=True)`，Host 才把它纳入实际路由。

---

## HomeCard 组件（@HomeCard）— WebUI 首页卡片

```python
from maibot_sdk import HomeCard

@HomeCard(
    "status",                       # 位置参数：name，同插件内唯一
    title="插件状态",                # 必填
    content=[                        # str（按 Markdown 渲染）或 list[dict] 内容块
        {"type": "markdown", "content": "**运行中**，最近一次同步成功。"},
        {"type": "stat", "label": "今日任务", "value": "12", "detail": "失败 0 次"},
        {"type": "actions", "actions": [{"label": "打开配置", "url": "/plugin-config?plugin=demo.status"}]},
    ],
    link_url="/plugin-config?plugin=demo.status",
    link_label="插件配置",
    width="medium",
    order=100,
)
async def home_card_marker(self) -> None:
    return None
```

- 签名：`HomeCard(name, title, content="", *, description="", link_url="", link_label="", icon="", width="medium", order=1000, **metadata)`
- `name` / `title` 为空会 `ValueError`。
- 内容块类型：`markdown` / `text` / `stat` / `key_value` / `list` / `actions`。
- `width`：`small`(2/10) / `medium`(3/10) / `large`(5/10) / `wide`(7/10) / `full`(10/10)；`order` 越小越靠前。
- `link_url` 只允许 WebUI 内部路径、`http(s)`、`mailto`。
- 安全边界：**WebUI 不执行插件提供的 HTML/JS**，Markdown 里的 HTML 也按纯文本处理。
- 卡片随插件加载注册，插件禁用 / 卸载 / 重载后自动从首页候选移除。

### 声明式页面（webui.json）— 与 HomeCard 并行的另一套机制

Host 侧另有 `src/plugin_runtime/webui_schema.py` 实现的 `webui.json` 声明式页面协议，
2 种 page mode：`declarative`（声明式组件页）与 `custom`（`entry` 指向插件内 `.html` 文件，不能内联 document）。
硬限制：声明文件 ≤128 KiB、注册载荷 ≤512 KiB、每插件最多 20 页、custom 页 HTML ≤2 MiB、总量 ≤8 MiB、
`icon` 只接受 `puzzle` / `chart` / `settings` / `database` / `list`。
**校验失败会让插件注册失败**（`load_webui_extension` 抛 `OSError` / `ValueError` 时直接 `return False`）；
没有 `webui.json` 则不受影响。
旧的 manifest 页面扩展协议（v2 之前）在当前版本已不存在，不要按它写 manifest。

---

## ReplyExtension 组件（@ReplyExtension）

```python
from maibot_sdk import ReplyExtension

@ReplyExtension(
    "voice",                        # 位置参数：name
    description="需要语音回复时启用",
    parameters={"attach_voice": {"type": "boolean", "default": False}},
    *,
    platforms: str | list[str] | None = None,
    priority: int = 0,
    timeout_ms: int = 60000,
    chat_scope: Literal["all", "group", "private"] = "all",
    allowed_session: list[str] | None = None,
    enabled: bool = True,
    **metadata: Any,
)
async def reply_voice(self, *, phase, parameters, text, messages, **context):
    if phase == "prepare":
        return {"extra_prompt": "这次回复会转成语音，请使用适合朗读的自然口语。"}
    return {"messages": [...]}
```

同一 handler 被调用两次，用 `phase` 区分：

| phase | 时机 | 合法返回值 |
|-------|------|-----------|
| `prepare` | 生成正文之前 | `{"extra_prompt": "..."}` 或 `{}` |
| `before_send` | 后处理与附件完成之后、发送之前 | `{"messages": [...]}` 或 `{}` |

- Host 对 `prepare` 只接受字符串 `extra_prompt` 这一个键，对 `before_send` 只接受 `messages` 键；
  **多一个键即视为无效返回值，直接让本次 reply 失败**。
- 完整协议（消息组校验、段类型、语音示例、失败语义）见 `references/reply-extensions.md`。
- 依赖门槛：`maibot-plugin-sdk>=2.10.0` 且主程序支持 `REPLY_EXTENSION`（1.3.5 开发版本起）。

---

## Action 组件（@Action）— ⚠️ 已废弃，不要在新插件里用

`@Action` 自 SDK 2.x 起**已废弃**，使用时会触发 `DeprecationWarning`。
SDK 内部把它转换成 `@Tool` 注册（`invoke_method="plugin.invoke_action"`，metadata 打 `legacy_action: True`），
**主程序只维护一套 Tool 抽象**。新插件请直接用 `@Tool`。

维护旧插件时才需要知道它的签名：

```python
@Action(
    name,                                        # 位置参数：名称
    description="",
    activation_type=ActivationType.ALWAYS,       # ALWAYS / KEYWORD / RANDOM / NEVER
    activation_keywords=None,
    activation_probability=1.0,
    chat_mode=ChatMode.NORMAL,                   # FOCUS / NORMAL / PRIORITY / ALL
    action_parameters=None,                      # {"参数名": "描述"}，全部按 string 处理
    action_require=None,
    associated_types=None,
    parallel_action=False,
    action_prompt="",
    **metadata: Any,
)
```

迁移到 `@Tool` 的差异：参数从 `action_parameters={"k":"描述"}` 改为 `parameters=[ToolParameterInfo(...)]`
（支持 7 种类型 + 自动生成 JSON Schema）；描述从单一 `description` 改为 `brief_description` + `detailed_description`；
激活方式不再需要声明，由 LLM 自行判断是否调用。

Host 侧 `_build_action_executor` 的返回值解包与 Command 不同：`list/tuple` 且 `len>=2` 时取
`(bool(result[0]), str(result[1]))`，`len==1` 时取 `(bool(result[0]), "")`；非 list/tuple 时
success 走 RPC 层的 success、result 转 str。

---

## WorkflowStep — ⚠️ 已移除

`WorkflowStep` 在 SDK 2.0 被 `HookHandler` 取代，**调用会直接抛 `RuntimeError`**（不做静默兼容）。
旧代码看到它一律改成 `@HookHandler`。
