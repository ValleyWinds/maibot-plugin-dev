# MaiBot Plugin SDK 能力代理 API 速查

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）
> 源码位置：`maibot-plugin-sdk/maibot_sdk/capabilities/*.py`、`maibot_sdk/context.py`
> 文档：https://docs.mai-mai.org/plugin/api-reference

所有能力代理通过 `self.ctx.*` 访问，调用通过 RPC 转发到 Host。
以下签名均为**位置参数顺序**，与 SDK 源码逐字一致；`*` 之后是仅关键字参数。

---

## 能力代理总览（18 个 + paths + logger）

| 代理 | 类 | 说明 | 引入版本 |
|------|-----|------|----------|
| `ctx.send` | SendCapability | 消息发送（7 个方法） | 1.0.0 |
| `ctx.llm` | LLMCapability | LLM 调用与向量/语音 | 1.0.0 |
| `ctx.db` | DatabaseCapability | 数据库操作 | 1.0.0 |
| `ctx.config` | ConfigCapability | 配置读取 | 1.0.0 |
| `ctx.message` | MessageCapability | 历史消息 | 1.0.0 |
| `ctx.emoji` | EmojiCapability | 表情包管理 | 1.0.0 |
| `ctx.frequency` | FrequencyCapability | 发言频率 | 1.0.0 |
| `ctx.component` | ComponentCapability | 插件与组件管理 | 1.0.0 |
| `ctx.chat` | ChatCapability | 聊天流查询 + 头像 | 1.1.0 |
| `ctx.person` | PersonCapability | 用户信息 | 1.1.0 |
| `ctx.knowledge` | KnowledgeCapability | 知识库搜索 | 1.1.0 |
| `ctx.tool` | ToolCapability | 工具定义查询 | 1.1.0 |
| `ctx.api` | APICapability | 跨插件 API | 2.1.0 |
| `ctx.gateway` | GatewayCapability | 消息网关（不走能力声明） | 2.1.0 |
| `ctx.render` | RenderCapability | HTML 渲染 | 2.3.0 |
| `ctx.maisaka` | MaisakaCapability | 上下文注入与主动任务 | 2.5.0 |
| `ctx.statistics` | StatisticsCapability | 本机统计（`ctx.statistics.local.*`） | 2.6.0 |
| `ctx.webui` | WebUICapability | WebUI 上传凭证领取 | 2.11.0 |
| `ctx.paths` | PluginPaths | 数据/临时目录（非能力代理） | 2.6.0 |
| `ctx.logger` | stdlib Logger | 日志（非能力代理） | 1.0.0 |

---

## 返回值语义（全局规则，先读这一节）

SDK 在 `maibot_sdk/context.py` 的 `PluginContext._normalize_capability_result` 里统一拆 Host 的
`{"success": ..., "<key>": ...}` 包装，分三种情况：

1. **有解包键的能力**：直接返回 `result[key]`，不再带 `success`。解包键表见下文各节。
2. **布尔成功能力**（`_BOOLEAN_SUCCESS_CAPABILITIES`）：返回 `bool(result["success"])`。
   共 8 个：`frequency.set_adjust`、`send.text`、`send.emoji`、`send.image`、`send.forward`、
   `send.hybrid`、`send.command`、`send.custom`。
3. **其余能力**：原样返回整个 dict（含 `success` / `error`），需要自己判 `success`。

**`return_details`**：只有 `_DETAILED_SEND_CAPABILITIES`（即 7 个 `send.*`）支持。
传入 `return_details=True` 时返回 `{"sent": bool, "message_id": str | None}`——
`message_id` 是适配器回传的 `platform_message_id`，发送失败或平台未回传时为 `None`
（Host 侧组装见 `MaiBot/src/plugin_runtime/capabilities/core.py` 的 `_build_send_result`）。

**失败传播**：Host 侧能力抛异常时返回 `{"success": False, "error": "..."}`，SDK 不抛错。
除上述三类外的能力（`maisaka.*`、`chat.open_session`、`component.*`、`llm.*` 等）
失败时拿到的是带 `error` 的 dict，**不要**当成空结果继续用。

**manifest 授权**：每个能力都要在 `_manifest.json` 的 `capabilities` 里声明能力名
（不是代理方法名）。下文每节标题后标注需声明的名字。

---

## ctx.send — 消息发送

需声明 manifest 能力：`send.text` / `send.emoji` / `send.image` / `send.forward` /
`send.hybrid` / `send.command` / `send.custom`

```python
async def text(self, text: str, stream_id: str, *, return_details: bool = False, **kwargs: Any) -> bool | SendResult
async def emoji(self, emoji_data: str, stream_id: str, *, return_details: bool = False, **kwargs: Any) -> bool | SendResult
async def image(self, image_data: str, stream_id: str, *, return_details: bool = False, **kwargs: Any) -> bool | SendResult
async def forward(self, messages: list[dict[str, Any]], stream_id: str, *, return_details: bool = False, **kwargs: Any) -> bool | SendResult
async def hybrid(self, segments: list[dict[str, Any]], stream_id: str, *, return_details: bool = False, **kwargs: Any) -> bool | SendResult
async def command(self, command: str, stream_id: str, *, return_details: bool = False, **kwargs: Any) -> bool | SendResult
async def custom(self, custom_type: str, data: Any, stream_id: str, *, return_details: bool = False, **kwargs: Any) -> bool | SendResult
```

```python
# 常用写法
await ctx.send.text("你好", stream_id)

await ctx.send.image(image_base64, stream_id)
await ctx.send.emoji(emoji_base64, stream_id)

await ctx.send.hybrid(
    [
        {"type": "text", "content": "看看这张图："},
        {"type": "image", "content": image_base64},
    ],
    stream_id,
)

await ctx.send.forward(
    [{"user_id": "0", "nickname": "转发", "segments": [{"type": "text", "content": "..."}]}],
    stream_id,
)

result = await ctx.send.text("你好", stream_id, return_details=True)
# result = {"sent": bool, "message_id": str | None}
if result["sent"] and result["message_id"]:
    platform_msg_id = result["message_id"]  # 平台确认的最终消息 ID
```

**Host 侧可选 kwargs**（不进 SDK 签名，通过 `**kwargs` 透传，见
`MaiBot/src/plugin_runtime/capabilities/core.py` 的 `_cap_send_*`）：
`typing`、`set_reply`、`storage_message`（默认 True）、`show_log`、
`sync_to_maisaka_history`、`maisaka_source_kind`、`processed_plain_text`。

**⚠️ 易错点**：
- 返回值默认是 **`bool`**，不是 dict；`result["success"]` 这种写法会直接 TypeError
- `send.emoji` 的 SDK 形参叫 `emoji_data`，`send.image` 叫 `image_data`，
  但发到 Host 的字段名是 `emoji_base64` / `image_base64`——自己拼 `**kwargs` 时别写错
- `send.custom(custom_type, data, ...)` 发到 Host 时同时带 `message_type` / `content` /
  `custom_type` / `data` 四份，Host 优先读 `message_type` + `content`
- `hybrid` 的消息段用 `content` 或 `data` 都认（Host 的 `_normalize_plugin_segment` 会归一化），
  但 `type` 只认 `text` / `image` / `emoji` / `voice`

---

## ctx.llm — LLM 调用

需声明 manifest 能力：`llm.generate` / `llm.generate_with_tools` / `llm.embed` /
`llm.transcribe_audio` / `llm.get_available_models`

```python
async def generate(self, prompt: str | List[Dict[str, Any]], model: str = "", temperature: float | None = None, max_tokens: int | None = None, *, task_name: str | None = None, model_name: str = "", **kwargs: Any) -> Dict[str, Any]
async def generate_with_tools(self, prompt: str | List[Dict[str, Any]], tools: List[Dict[str, Any]], model: str = "", temperature: float | None = None, max_tokens: int | None = None, *, task_name: str | None = None, model_name: str = "", **kwargs: Any) -> Dict[str, Any]
async def embed(self, text: str | None = None, *, texts: List[str] | None = None, task_name: str = "embedding", model: str = "", model_name: str = "", max_concurrent: int | None = None, **kwargs: Any) -> Dict[str, Any]
async def transcribe_audio(self, audio: bytes | str | None = None, *, audio_base64: str = "", voice_base64: str = "", task_name: str = "voice", model: str = "", model_name: str = "", **kwargs: Any) -> Dict[str, Any]
async def get_available_models(self) -> List[str]
```

```python
result: dict = await ctx.llm.generate(
    prompt,                    # str 或 List[Dict]（消息列表）
    model="",                  # 位置参数：模型名或任务名，空串=默认任务
    temperature=None,          # 省略时用 Host 模型配置
    max_tokens=None,           # 省略时用 Host 模型配置
    *,
    task_name=None,            # 仅关键字：明确的 Host 模型任务名
    model_name="",             # 仅关键字：明确的具体模型名
)

result: dict = await ctx.llm.generate_with_tools(prompt, tools, model="", temperature=None, max_tokens=None, *, task_name=None, model_name="")
result: dict = await ctx.llm.embed(text="嵌入文本")          # 或 texts=[...] 批量
result: dict = await ctx.llm.transcribe_audio(audio=...)    # bytes 或 str
names: list[str] = await ctx.llm.get_available_models()      # 返回 List[str]，不是 dict
```

**⚠️ 没有 `system_prompt` 参数**：SDK 签名里不存在该参数，传入会被 `**kwargs` 吞掉透传、Host 也不处理。
要传 system prompt 用消息列表：

```python
result = await ctx.llm.generate(
    prompt=[
        {"role": "system", "content": "你是温柔恋人"},
        {"role": "user", "content": "你好"},
    ],
)
```

**`model` / `task_name` / `model_name` 路由规则**（SDK `LLMCapability` 类文档，2.8.1 引入、
2.8.2 修正默认值）：

- 只传 `model`：Host 先按模型任务名解析，未命中再当具体模型名，兼容旧插件
- 传 `task_name`：使用该任务，`model` 与 `model_name` 都只表示具体模型名
- 传 `model_name`：一律直选具体模型，即使它与某个任务同名

SDK 只在显式传了 `task_name` / `model_name` 时才把它们放进 RPC payload——
省略时 Host 继续按「先任务名、后具体模型」解析 `model`。**任务名必须存在于主程序
`config/model_config.toml` 的 `[model_task_config.*]`**，常见任务名：
`replyer` / `planner` / `utils` / `memory` / `vlm` / `embedding` / `voice`。
**没有 `reply` 这个任务名。**

**返回值**：`generate` / `generate_with_tools` 返回 dict，经 `_normalize_llm_result`
补齐 `model` 键（Host 原字段是 `model_name`）；Host 侧还可能带
`prompt_tokens` / `completion_tokens` / `total_tokens`。
`embed` 单条返回 `embedding`，批量返回 `results` 列表；
`transcribe_audio` 返回 `{"success": bool, "text": str, "content": str}`。
这五个能力都**没有**解包键，拿到的是完整 dict，记得先看 `success`。

---

## ctx.db — 数据库操作

需声明 manifest 能力：`database.query` / `database.save` / `database.get` /
`database.delete` / `database.count`

```python
async def query(self, model_name: str, query_type: str = "get", data: dict[str, Any] | None = None, filters: dict[str, Any] | None = None, order_by: list[str] | None = None, limit: int | None = None, single_result: bool = False) -> Any
async def save(self, model_name: str, data: dict[str, Any], key_field: str = "id", key_value: Any = None) -> Any
async def get(self, model_name: str, filters: dict[str, Any] | None = None, limit: int | None = None, order_by: str | list[str] | None = None, single_result: bool = False) -> Any
async def delete(self, model_name: str, filters: dict[str, Any]) -> Any
async def count(self, model_name: str, filters: dict[str, Any] | None = None) -> int
```

```python
# 通用查询（query_type: get / create / update / delete / count）
await ctx.db.query("MyModel", query_type="get", filters={"chat_id": chat_id}, limit=10)

# 保存（插入或更新，不会自动建表）
await ctx.db.save("MyModel", {"chat_id": chat_id, "text": "hi"}, key_field="chat_id", key_value=chat_id)

# 按条件获取
await ctx.db.get("MyModel", filters={"chat_id": chat_id}, single_result=True)

# 删除（Host 不允许无条件删除）
await ctx.db.delete("MyModel", {"chat_id": chat_id})

# 计数（返回 int）
count: int = await ctx.db.count("MyModel", {"chat_id": chat_id})
```

**解包键**：`query` / `save` / `get` / `delete` → `result`；`count` → `count`（并强转 `int`，
拿不到时返回 0）。

**⚠️ 易错点**：
- **没有 `ctx.db.create()` / `ctx.db.update()`**：写入统一走 `save()`
  （内部按 `key_field`/`key_value` 决定插入或更新），或用 `query(query_type="create"/"update", data=...)`
- `query` 的 `query_type` 只认 `get`/`create`/`update`/`delete`/`count`，Host 对其他值直接报错
- `delete` 不接受空 `filters`，Host 返回「不允许无条件删除」
- `model_name` 是 Host `database_model` 里的**类名**，不是表名

---

## ctx.config — 配置读取

需声明 manifest 能力：`config.get` / `config.get_plugin` / `config.get_all`

```python
async def get(self, key: str, default: Any = None) -> Any
async def get_plugin(self, plugin_name: str | None = None) -> dict[str, Any]
async def get_all(self) -> dict[str, Any]
```

```python
# 读取主程序全局配置（key 支持点分割）
value = await ctx.config.get("personality.personality", "")

# 读取指定插件配置（省略 plugin_name 读自己）
config = await ctx.config.get_plugin("com.example.other-plugin")

# 读取当前插件全部配置
all_config = await ctx.config.get_all()
```

**解包键**：三个能力都是 `value`；`get_plugin` / `get_all` 额外保证非 dict 时回落 `{}`，
`get` 在结果为 `None` 时回落 `default`。

**⚠️ `ctx.config.get` 读的是主程序全局配置**（如 personality），不是插件自身配置。
插件自身配置用 `self.config`（强类型）或 `self.get_plugin_config_data()`（原始 dict）。
Host 侧 `config.get_plugin` 还接受可选 `key` / `default` 参数做点路径取值，SDK 未暴露。

---

## ctx.chat — 聊天流查询与头像

需声明 manifest 能力：`chat.get_all_streams` / `chat.get_group_streams` /
`chat.get_private_streams` / `chat.get_stream_by_group_id` / `chat.get_stream_by_user_id` /
`chat.open_session` / `chat.get_avatar`

```python
async def get_avatar(self, platform: str, target_id: str, target_type: Literal["user", "group"] = "user", *, account_id: str = "", scope: str = "", force_refresh: bool = False) -> AvatarInfo
async def get_all_streams(self, platform: str = "qq") -> Any
async def get_group_streams(self, platform: str = "qq") -> Any
async def get_private_streams(self, platform: str = "qq") -> Any
async def get_stream_by_group_id(self, group_id: str, platform: str = "qq") -> Any
async def get_stream_by_user_id(self, user_id: str, platform: str = "qq") -> Any
async def open_session(self, platform: str = "qq", chat_type: str = "private", *, user_id: str = "", group_id: str = "", account_id: str = "", scope: str = "", **kwargs: Any) -> Any
```

```python
# 打开/创建聊天流（2.5.0+）
stream = await ctx.chat.open_session("qq", "group", group_id="123456")
# stream 是完整 dict：含 created、stream，以及展平的 session_id / stream_id / platform / ...

info: AvatarInfo = await ctx.chat.get_avatar("qq", "123456", "group")
# info = {"status": "available" | "unsupported" | "missing", "url": str | None, "expires_at": float}
if info["status"] == "available":
    download_from(info["url"])   # HTTP(S) 直链，图片字节不经过 RPC
```

**解包键**：`get_all_streams` / `get_group_streams` / `get_private_streams` → `streams`；
`get_stream_by_group_id` / `get_stream_by_user_id` → `stream`（未命中为 `None`）；
`get_avatar` → `avatar`（`AvatarInfo` TypedDict）。
`chat.open_session` **没有**解包键，返回整个 dict（Host 在
`MaiBot/src/plugin_runtime/capabilities/data.py` 的 `_cap_chat_open_session` 里把
`created`、`stream` 与序列化字段一起平铺返回）。

**⚠️ 易错点**：
- 方法名是 `get_avatar`，参数是 `platform` + `target_id`（**不是** `user_id`/`group_id`）
- `get_avatar` 失败会**抛错**，不返回旧头像；`status="unsupported"` 表示当前适配器不提供头像
- `open_session` 的 `chat_type` 只认 `group`/`private`；`chat_type="group"` 必须给 `group_id`，
  `private` 必须给 `user_id`，否则 Host 报错
- `platform` 默认值是 `"qq"`，写死别的平台要显式传参
- 查不到流时 `get_stream_by_*` 返回 `None` 而不是抛错

---

## ctx.maisaka — Maisaka 上下文与主动任务

需声明 manifest 能力：`maisaka.context.append` / `maisaka.context.resolve_image` /
`maisaka.proactive.trigger`

`ctx.maisaka` 是入口对象，持两个子对象：`ctx.maisaka.context`（`MaisakaContextCapability`）
与 `ctx.maisaka.proactive`（`MaisakaProactiveCapability`）。

```python
# 子对象 self.context
async def resolve_image(self, stream_id: str, source_id: str, index: int = 0) -> Any
async def append(self, stream_id: str, segments: list[dict[str, Any]], *, visible_text: str = "", source_kind: str = "", message_id: str = "", **kwargs: Any) -> Any

# 子对象 self.proactive
async def trigger(self, stream_id: str, intent: str, *, reason: str = "", priority: str = "", metadata: dict[str, Any] | None = None, **kwargs: Any) -> Any

# 入口对象上的便捷别名
async def append_context(self, stream_id: str, segments: list[dict[str, Any]], **kwargs: Any) -> Any
async def trigger_proactive(self, stream_id: str, intent: str, **kwargs: Any) -> Any
```

```python
# 追加上下文消息
await ctx.maisaka.context.append(
    stream_id,
    [{"type": "text", "content": "上下文消息"}],
    visible_text="给模型看的摘要",
)

# 触发 planner 主动处理
await ctx.maisaka.proactive.trigger(stream_id, "提醒用户喝水", reason="定时任务", priority="high")

# 便捷别名
await ctx.maisaka.trigger_proactive(stream_id, intent)
await ctx.maisaka.append_context(stream_id, segments)
```

**这三个能力都没有解包键**，返回整个 dict：
- `context.append` → `{"success": True, "index": int, "stream_id": str, "visible_text": str, "source_kind": str}`
- `proactive.trigger` → `{"success": True, **enqueue 结果}`（Host 的
  `_cap_maisaka_proactive_trigger`）
- `resolve_image` → `{"success": True, "image": {"binary_data_base64": ..., "binary_hash": ...}}`

**⚠️ 易错点与 Host 限制**：
- 触发主动任务用的是 `proactive.trigger`（或别名 `trigger_proactive`），
  **不是** `maisaka.trigger(...)`——入口对象上没有这个方法
- `proactive.trigger` 的 `stream_id` 必须是 Host 中**已存在**的聊天流，否则报
  「未找到已存在的聊天流」
- `resolve_image` 的 `source_id` 可以是上下文消息编号（支持短别名）或
  `tool_result:<call_id>:<item_index>`；`index` 必须是非负整数，且必须是 `int` 类型
  （传 `"0"` 字符串会被拒）
- `resolve_image` 受 RPC 单帧体积上限约束（`src/plugin_runtime/transport/base.py` 的
  `MAX_FRAME_SIZE` 预留 64KB），超大图直接报错
- `append` 的 `visible_text` 留空时 Host 会从消息段自动生成，仍为空则回落
  `"[插件上下文消息]"`

---

## ctx.message — 历史消息

需声明 manifest 能力：`message.get_recent` / `message.get_by_id` / `message.build_readable` /
`message.get_by_time` / `message.get_by_time_in_chat` / `message.count_new`

```python
async def get_recent(self, chat_id: str, limit: int = 10) -> Any
async def get_by_id(self, message_id: str, *, chat_id: str = "", stream_id: str = "", include_binary_data: bool = False) -> Any
async def build_readable(self, messages: Any, **kwargs: Any) -> Any
async def get_by_time(self, start_time: str, end_time: str, **kwargs: Any) -> Any
async def get_by_time_in_chat(self, chat_id: str, start_time: str, end_time: str, **kwargs: Any) -> Any
async def count_new(self, chat_id: str, since: str) -> Any
```

```python
msgs = await ctx.message.get_recent(chat_id, limit=20)
text = await ctx.message.build_readable(msgs)

one = await ctx.message.get_by_id(message_id, chat_id=chat_id, include_binary_data=True)

new_count = await ctx.message.count_new(chat_id, since)
```

**解包键**：`get_recent` / `get_by_time` / `get_by_time_in_chat` → `messages`；
`get_by_id` → `message`（未命中为 `None`）；`build_readable` → `text`；
`count_new` → `count`。

**⚠️ 易错点**：
- **没有 `get_history(stream_id, limit)`**；第一个参数一律叫 `chat_id`
- `get_by_id` 的 `chat_id` 与 `stream_id` **等价**（Host 两个都读，任填一个即可），
  且都是仅关键字参数——`get_by_id(msg_id, chat_id)` 这种位置写法会报错
- `get_recent` 的 Host 实现是按时间窗口（`hours`，默认 24h）取最近消息，
  `limit` 默认 100；要更早的历史用 `get_by_time_in_chat`
- `get_by_time` 的 `start_time` / `end_time` 在 Host 侧按 `float` 解析，
  也接受 `limit` / `limit_mode` / `filter_mai` / `include_binary_data` 等 kwargs
- `build_readable` 不传 `messages` 时 Host 可改为按 `chat_id` + 时间窗取数

---

## ctx.person — 用户信息

需声明 manifest 能力：`person.get_id` / `person.get_value` / `person.get_id_by_name`

```python
async def get_id(self, platform: str, user_id: str) -> Any
async def get_value(self, person_id: str, field_name: str) -> Any
async def get_id_by_name(self, person_name: str) -> Any
```

```python
person_id = await ctx.person.get_id("qq", "123456")
nickname = await ctx.person.get_value(person_id, "name")
person_id = await ctx.person.get_id_by_name("小明")
```

**解包键**：`get_id` / `get_id_by_name` → `person_id`；`get_value` → `value`
（Host 侧字段为 `None` 时回落调用方 `default`）。

**⚠️ 没有 `person.get(user_id=...)`**；取内部人物 ID 用 `get_id(platform, user_id)`，
两个都是位置参数。

---

## ctx.emoji — 表情包管理

需声明 manifest 能力：`emoji.get_random` / `emoji.get_by_description` / `emoji.get_count` /
`emoji.get_info` / `emoji.get_emotions` / `emoji.get_all` / `emoji.register` / `emoji.delete`

```python
async def get_random(self, count: int = 5) -> Any
async def get_by_description(self, description: str, limit: int = 5) -> Any
async def get_count(self) -> Any
async def get_info(self) -> Any
async def get_emotions(self) -> Any
async def get_all(self) -> Any
async def register_emoji(self, emoji_base64: str) -> Any
async def delete_emoji(self, emoji_hash: str, keep_desc: bool | None = None) -> Any
```

```python
emojis = await ctx.emoji.get_random(3)                    # 随机若干张
emoji = await ctx.emoji.get_by_description("开心", 1)      # 语义检索
info = await ctx.emoji.get_info()                          # {"current_count", "max_count", ...}
await ctx.emoji.register_emoji(png_base64)                # 注册
await ctx.emoji.delete_emoji(file_hash)                   # 删除
```

**解包键**：`get_random` / `get_all` → `emojis`（元素为
`{"base64", "description", "emotion"}`）；`get_by_description` → `emoji`（可能为 `None`）；
`get_count` → `count`；`get_emotions` → `emotions`；`get_info` → `info`；
`register_emoji` / `delete_emoji` **没有**解包键，返回完整 dict
（`register` 带 `message` / `description` / `emotions` / `replaced` / `hash`；
`delete` 带 `message` / `hash` / `keep_desc`）。

**⚠️ 易错点**：
- 代理方法名与能力名不一致：`register_emoji` → 能力 **`emoji.register`**；
  `delete_emoji` → 能力 **`emoji.delete`**。manifest 要写后者
- **没有 `emoji.random(stream_id=...)`**；`get_random` 不接受 `stream_id`，
  返回的是数据列表，需要自己用 `send.emoji` / `send.image` 发送
- `delete_emoji` 的 `keep_desc` 只在显式传 `True`/`False` 时才进 payload，
  传 `None`（默认）由 Host 按「该表情是否有描述」自动决定

---

## ctx.frequency — 发言频率

需声明 manifest 能力：`frequency.get_current_talk_value` / `frequency.set_adjust` /
`frequency.get_adjust`

```python
async def get_current_talk_value(self, chat_id: str) -> Any
async def set_adjust(self, chat_id: str, value: float) -> Any
async def get_adjust(self, chat_id: str) -> Any
```

```python
current = await ctx.frequency.get_current_talk_value(chat_id)
await ctx.frequency.set_adjust(chat_id, 1.5)   # 返回 bool
adjust = await ctx.frequency.get_adjust(chat_id)
```

**返回值**：`set_adjust` 在布尔成功能力集合中，返回 `bool`；
`get_current_talk_value` / `get_adjust` 解包键为 `value`。
`get_current_talk_value` 是「频率调整值 × 该聊天的 talk value」的乘积。

**⚠️ 没有 `frequency.check(stream_id)`**；参数名一律是 `chat_id`，不是 `stream_id`。

---

## ctx.component — 插件与组件管理

需声明 manifest 能力：`component.get_all_plugins` / `component.get_plugin_info` /
`component.get_plugin_config_schema` / `component.list_loaded_plugins` /
`component.list_registered_plugins` / `component.enable` / `component.disable` /
`component.load_plugin` / `component.unload_plugin` / `component.reload_plugin`

```python
async def get_all_plugins(self) -> Any
async def get_plugin_info(self, plugin_name: str) -> Any
async def get_plugin_config_schema(self, plugin_name: str) -> Any
async def list_loaded_plugins(self) -> Any
async def list_registered_plugins(self) -> Any
async def enable_component(self, name: str, component_type: str, scope: str = "global", stream_id: str = "", version: str = "") -> Any
async def disable_component(self, name: str, component_type: str, scope: str = "global", stream_id: str = "", version: str = "") -> Any
async def load_plugin(self, plugin_name: str) -> Any
async def unload_plugin(self, plugin_name: str) -> Any
async def reload_plugin(self, plugin_name: str) -> Any
```

```python
plugins = await ctx.component.list_loaded_plugins()
info = await ctx.component.get_plugin_info("com.example.other")
await ctx.component.enable_component("other.my_command", "command")
await ctx.component.reload_plugin("com.example.other")
```

**解包键**：`get_all_plugins` / `list_loaded_plugins` / `list_registered_plugins` → `plugins`；
`get_plugin_info` → `plugin`；`get_plugin_config_schema`、`enable` / `disable` /
`load_plugin` / `unload_plugin` / `reload_plugin` **没有**解包键，返回完整 dict
（`load_plugin` 成功时带 `count`）。

**⚠️ Host 侧限制（`MaiBot/src/plugin_runtime/capabilities/components.py` 核实，第三方插件必读）**：

- `component.update_plugin_config`（Host 已注册、SDK 代理未暴露的方法）——
  **仅内置 `builtin.plugin-management` 插件可用**，其他调用方恒返回
  `{"success": False, "error": "仅插件管理内置插件可以修改插件配置"}`
- `unload_plugin` — **恒返回失败**："新运行时不支持单独卸载插件，请使用 reload"；
  要重载统一走 `reload_plugin`
- `enable_component` / `disable_component` — Host 仅支持 `scope="global"` 且不传
  `stream_id`，传了会话级参数返回「当前仅支持全局组件启用/禁用」；
  组件名不唯一时要求用完整名 `plugin_id.component_name`
- `component_type` 经 SDK 的 `normalize_component_type_name` 归一化为大写，
  接受 `command` / `COMMAND` 等写法，但 `workflow_step` 直接抛 ValueError
  （`WorkflowStep` 已移除，改用 `HookHandler`）

**⚠️ 代理方法名与能力名不一致**：`enable_component` → 能力 **`component.enable`**，
`disable_component` → 能力 **`component.disable`**。manifest 要写后者。
**没有 `component.list(plugin_id=...)`**。

---

## ctx.api — 插件间 API

需声明 manifest 能力：`api.call` / `api.get` / `api.list` / `api.replace_dynamic`

```python
async def call(self, api_name: str, *, version: str = "", **kwargs: Any) -> Any
async def get(self, api_name: str, *, version: str = "") -> Any
async def list(self, *, plugin_id: str = "") -> Any
async def replace_dynamic_apis(self, apis: builtins_list[dict[str, Any]], *, offline_reason: str = "动态 API 已下线") -> bool
```

```python
result = await ctx.api.call("other.send_card", card={"type": "json", "data": {...}})
meta = await ctx.api.get("other.send_card")
apis = await ctx.api.list(plugin_id="com.example.other")
ok = await ctx.api.replace_dynamic_apis([{"name": "my_api", "component_type": "API", "metadata": {...}}])
```

**解包键**：`call` → `result`；`get` → `api`（未命中为 `None`）；`list` → `apis`。
`replace_dynamic_apis` **没有**解包键，SDK 自己判 `success` 后返回 `bool`。

**⚠️ 易错点**：
- `version` 是**仅关键字**参数，`ctx.api.call("name", "1")` 会报错
- `api_name` 支持 `plugin_id.api_name` 或唯一短名
- 只有 `public=True` 的 `@API` 才能被其他插件 `ctx.api.call` 调到
- 动态 API 不能覆盖同名静态 API（Host 的 `_cap_api_replace_dynamic` 会拒绝），
  被下线的 API 对外返回 `offline_reason`

---

## ctx.gateway — 消息网关

**⚠️ gateway 不走能力声明**：Host 侧没有 `gateway.*` 能力名，SDK 通过白名单裸方法
`host.route_message` / `host.update_message_gateway_state` 调用
（`maibot_sdk/context.py` 的 `_ALLOWED_RAW_HOST_METHODS`），
**不需要（也无法）写进 manifest `capabilities`**。

```python
async def route_message(self, gateway_name: str, message: dict[str, Any], *, route_metadata: dict[str, Any] | None = None, external_message_id: str = "", dedupe_key: str = "") -> bool
async def update_state(self, gateway_name: str, *, ready: bool, platform: str = "", account_id: str = "", scope: str = "", metadata: dict[str, Any] | None = None) -> bool
async def receive_external_message(self, message: dict[str, Any], *, gateway_name: str, route_metadata: dict[str, Any] | None = None, external_message_id: str = "", dedupe_key: str = "") -> bool
async def update_runtime_state(self, *, gateway_name: str, connected: bool, platform: str = "", account_id: str = "", scope: str = "", metadata: dict[str, Any] | None = None) -> bool
```

```python
# 启动后必须先上报就绪，否则注入消息会被拒
await ctx.gateway.update_state("my_gateway", ready=True, platform="telegram", account_id="bot1")

# 入站路由（receive_external_message / update_runtime_state 是兼容旧命名的别名）
await ctx.gateway.route_message("my_gateway", message, external_message_id="42", dedupe_key="42")
```

**返回值**：四个方法都返回 `bool`，取自 Host 响应的 `accepted` 字段
（非 dict 响应一律 `False`）。

**⚠️ Host 侧限制**：
- `route_message` 要求该 `gateway_name` 已在 Host 注册、`route_type` 支持 receive
  （`send`/`receive`/`duplex` 及别名 `recv`/`recive`），且运行时状态 `ready=True`，
  否则返回 `E_METHOD_NOT_ALLOWED`
- 仅声明 `@MessageGateway` 组件不够，必须调 `update_state(..., ready=True)` 才参与收发
- **没有 `gateway.get_status()`**

---

## ctx.render — HTML 渲染

需声明 manifest 能力：`render.html2png`

```python
async def html2png(self, html: str, *, selector: str = "body", viewport: dict[str, int] | None = None, device_scale_factor: float = 2.0, full_page: bool = False, omit_background: bool = False, wait_until: str = "load", wait_for_selector: str = "", wait_for_timeout_ms: int = 0, render_timeout_ms: int = 0, allow_network: bool = False) -> Any
```

```python
png = await ctx.render.html2png(
    "<h1>你好</h1>",
    viewport={"width": 800, "height": 600},
    full_page=True,
    allow_network=False,
)
image_base64 = png["image_base64"]
```

**解包键**：`render.html2png` → `result`（含 `image_base64`、`mime_type`、`width`、`height`）。

**⚠️ 方法名是 `html2png`，不是 `html_to_image`**；
除 `html` 外全部是仅关键字参数。`allow_network` 默认 `False`，页面里的外链资源不会加载。

---

## ctx.knowledge — 知识库搜索

需声明 manifest 能力：`knowledge.search`

```python
async def search(self, query: str, limit: int = 5) -> Any
```

```python
text = await ctx.knowledge.search("麦麦喜欢什么", limit=3)
```

**解包键**：`knowledge.search` → `content`（一段拼好的文本，不是结构化列表；
无结果时 Host 返回「你不太了解有关…的知识」）。
Host 侧还支持 `mode` / `chat_id` / `person_id` / `user_id` / `group_id` /
`respect_filter` / `time_start` / `time_end` 等 kwargs，SDK 签名未暴露。

**⚠️ 参数名是 `limit`，不是 `top_k`**。

---

## ctx.tool — 工具定义查询

需声明 manifest 能力：`tool.get_definitions`

```python
async def get_definitions(self) -> Any
```

```python
definitions = await ctx.tool.get_definitions()
# [{"name": ..., "definition": {...}}, ...]
```

**解包键**：`tool.get_definitions` → `tools`（元素为 `name` + `definition`）。
**⚠️ 方法是 `get_definitions()`，不是 `list()`**；无参数。

---

## ctx.statistics — 本机统计（SDK 2.6.0+）

需声明 manifest 能力：`statistics.local.models` / `statistics.local.model_trend` /
`statistics.local.token_trend` / `statistics.local.token_distribution` /
`statistics.local.message_trend` / `statistics.local.tool_trend` /
`statistics.local.online_time_trend`

`ctx.statistics` 是入口对象，真实方法在子对象 `ctx.statistics.local`
（`LocalStatisticsCapability`）上，**且全部参数都是仅关键字的**：

```python
async def models(self, *, days: int = 7, limit: int = 10) -> list[dict[str, Any]]
async def model_trend(self, *, days: int = 7, bucket: str = "day", top_models: int = 10, metric: str = "token", module_name: str = "") -> dict[str, Any]
async def token_trend(self, *, days: int = 7, bucket: str = "day", group_by: str = "", top_items: int = 10) -> dict[str, Any]
async def token_distribution(self, *, days: int = 7, group_by: str = "model", top_items: int = 10) -> dict[str, Any]
async def message_trend(self, *, days: int = 7, bucket: str = "day", top_chats: int = 10) -> dict[str, Any]
async def tool_trend(self, *, days: int = 7, bucket: str = "day", top_tools: int = 10) -> dict[str, Any]
async def online_time_trend(self, *, days: int = 7, bucket: str = "day") -> dict[str, Any]
```

```python
models = await ctx.statistics.local.models(days=7, limit=10)
trend = await ctx.statistics.local.token_trend(days=30, bucket="day", group_by="model")
dist = await ctx.statistics.local.token_distribution(group_by="module")
```

**解包键**：`models` → `models`（`list[dict]`，元素含 `model_name` / `request_count` /
`total_cost` / `total_tokens` / `avg_response_time`）；六个趋势/分布能力 →
`series` / `distribution`。趋势类 `series` 含 `timestamps` / `values_by_key` /
`labels_by_key` / `total` / `source_count`；`token_distribution` 的 `distribution`
含用于饼图的 `pies`（Token 与请求次数两张）与 `total`。
`token_trend` 不传 `group_by` 时 `values_by_key` 固定为
`total_tokens` / `prompt_tokens` / `completion_tokens` / `request_count`。

**⚠️ Host 侧参数校验（`MaiBot/src/plugin_runtime/capabilities/data.py`）**：
- `days` 必须为正整数，上限 365
- `limit` / `top_*` / `top_items` 必须为正整数，上限 50
- `bucket` 只支持 `hour` / `day`（大小写不敏感，也认 `1h` / `按小时` 等别名）
- `group_by` 只支持 `model` / `module` / `provider` / `type`
- `metric` 只支持 `token` / `request` / `cost` / `latency`
- 违法参数会抛 `ValueError` 并被 Host 捕获为 `{"success": False, "error": ...}`，
  SDK 侧 `models` 回落 `[]`、其余回落 `{}`

**⚠️ 易错点**：调用路径是 `ctx.statistics.local.models(...)`，
**不是** `ctx.statistics.models(...)`；manifest 能力名带 `statistics.local.` 前缀。

---

## ctx.webui — WebUI 上传凭证（SDK 2.11.0+）

需声明 manifest 能力：`webui.claim_upload`（依赖 Host 的 `file_upload_v1`）

```python
async def claim_upload(self, upload_id: str) -> dict[str, Any]
```

```python
upload = await ctx.webui.claim_upload(upload_id)
# {"path": ".../data/plugins/<plugin_id>/uploads/<token><suffix>", "sha256": ..., "upload_id": ...}
data = Path(upload["path"]).read_bytes()
```

**解包键**：`webui.claim_upload` → `upload`。

**⚠️ 语义（Host `src/plugin_runtime/upload_store.py` 的 `claim`）**：
- 凭证由 Host 校验**归属插件**、有效期与一次性领取状态，过期或已领取直接抛错
- 凭证有效期一小时，只能领取一次；文件字节**不经过 RPC**，领取即落盘到
  `paths.data_dir/uploads/`
- 该能力只负责把暂存文件搬进插件数据目录，不接受目标路径参数

---

## 非能力代理对象

### ctx.paths（SDK 2.6.0+）

`PluginPaths` dataclass（`maibot_sdk/context.py`），两个字段都是 `pathlib.Path`：

```python
data_path = ctx.paths.data_dir / "records.json"      # data/plugins/<plugin_id>/
runtime_path = ctx.paths.runtime_dir / "latest.png"  # temp/plugins/<plugin_id>/
```

- 拼路径直接用 `/` 或 `str()`
- 持久数据 → `data_dir`；可重建的缓存/中间产物 → `runtime_dir`（不承诺长期保留）
- 不要再自建 `plugins/<plugin>/data`；不要把用户输入直接当文件名
- 未注入 paths 时 SDK 兜底为 `Path("data")/plugin_id` 与 `Path("temp")/plugin_id`

### ctx.logger

`PluginContext.logger` 属性，返回名为 `plugin.<plugin_id>` 的标准库 Logger，
日志经 IPC 自动转发到主进程：

```python
ctx.logger.info("插件已启动")
ctx.logger.error(f"请求失败: {err}", exc_info=True)

# 或 stdlib logging，同样会被自动转发到主进程
import logging
logger = logging.getLogger(__name__)
```

**⚠️ 旧版的 `await self.ctx.logging.info(...)` 异步 API 已移除**，改用上述标准 `logging` 写法。

---

## manifest capabilities 速查

| 能力名 | 对应代理方法 |
|--------|--------------|
| `send.text` / `send.emoji` / `send.image` / `send.forward` / `send.hybrid` / `send.command` / `send.custom` | `ctx.send.*` |
| `llm.generate` / `llm.generate_with_tools` / `llm.embed` / `llm.transcribe_audio` / `llm.get_available_models` | `ctx.llm.*` |
| `config.get` / `config.get_plugin` / `config.get_all` | `ctx.config.*` |
| `database.query` / `database.save` / `database.get` / `database.delete` / `database.count` | `ctx.db.*` |
| `message.get_recent` / `message.get_by_id` / `message.build_readable` / `message.get_by_time` / `message.get_by_time_in_chat` / `message.count_new` | `ctx.message.*` |
| `emoji.get_random` / `emoji.get_by_description` / `emoji.get_count` / `emoji.get_info` / `emoji.get_emotions` / `emoji.get_all` / `emoji.register` / `emoji.delete` | `ctx.emoji.*` |
| `frequency.get_current_talk_value` / `frequency.set_adjust` / `frequency.get_adjust` | `ctx.frequency.*` |
| `component.get_all_plugins` / `component.get_plugin_info` / `component.get_plugin_config_schema` / `component.list_loaded_plugins` / `component.list_registered_plugins` / `component.enable` / `component.disable` / `component.load_plugin` / `component.unload_plugin` / `component.reload_plugin` | `ctx.component.*` |
| `chat.get_avatar` / `chat.get_all_streams` / `chat.get_group_streams` / `chat.get_private_streams` / `chat.get_stream_by_group_id` / `chat.get_stream_by_user_id` / `chat.open_session` | `ctx.chat.*` |
| `person.get_id` / `person.get_value` / `person.get_id_by_name` | `ctx.person.*` |
| `knowledge.search` | `ctx.knowledge.search` |
| `tool.get_definitions` | `ctx.tool.get_definitions` |
| `api.call` / `api.get` / `api.list` / `api.replace_dynamic` | `ctx.api.*` |
| `maisaka.context.append` / `maisaka.context.resolve_image` / `maisaka.proactive.trigger` | `ctx.maisaka.*` |
| `statistics.local.models` / `statistics.local.model_trend` / `statistics.local.token_trend` / `statistics.local.token_distribution` / `statistics.local.message_trend` / `statistics.local.tool_trend` / `statistics.local.online_time_trend` | `ctx.statistics.local.*` |
| `render.html2png` | `ctx.render.html2png` |
| `webui.claim_upload` | `ctx.webui.claim_upload` |
| （无） | `ctx.gateway.*`、`ctx.paths`、`ctx.logger` |
