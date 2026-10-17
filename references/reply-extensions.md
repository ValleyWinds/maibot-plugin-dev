# MaiBot 回复扩展（ReplyExtension）参考

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）
> 源码位置：`maibot_sdk/components.py`（装饰器）、`maibot_sdk/types.py`（组件信息）、
> Host 侧 `src/plugin_runtime/host/reply_extensions.py`（两阶段调度与消息组校验）
> SDK 仓库内最权威文档：`maibot-plugin-sdk/docs/reply_extensions.md`（协议与语音示例以它为准）

## 解决什么问题

回复扩展让模型在决定回复内容时，可以顺手挑选插件提供的能力：转成语音、附带图片/表情、追加自定义卡片、按需改写正文措辞等。此前这类需求只能靠 Hook 硬编码（对每条回复都生效），插件无法把「是否使用、用什么参数」的决定权交给模型。

调用形态在模型侧：Planner 的 `reply` 工具多出一个 `plugin_options` 参数，键为 `"插件ID.组件名"`：

```json
{
  "msg_id": "m123",
  "set_quote": true,
  "plugin_options": {
    "voice_plugin.voice": {"attach_voice": true, "keep_text": false}
  }
}
```

- 省略某个键 = 本次回复不调用该插件；参数名在不同插件间即使同名也不会冲突。
- Replyer 依据这些参数生成正文，因此 `prepare` 阶段可以先把要求注入进去。

## 依赖门槛

- 需要支持 `REPLY_EXTENSION` 的 MaiBot 主程序（1.3.5 开发版本起）与 `maibot-plugin-sdk>=2.10.0`。
- 正式插件应在依赖声明中写死该下限；本地联调可设 `MAIBOT_PLUGIN_SDK_PATH` 指向 SDK 仓库目录，重启插件 Runner 后加载本地 SDK。
- 插件只依赖 SDK，无需导入主程序，也不需要改 Planner Hook。

## 装饰器签名

`maibot_sdk/components.py` 中的 `ReplyExtension` 逐字签名：

```python
def ReplyExtension(
    name: str,
    description: str = "",
    parameters: list[ToolParameterInfo] | dict[str, Any] | None = None,
    *,
    platforms: str | list[str] | None = None,
    priority: int = 0,
    timeout_ms: int = 60000,
    chat_scope: Literal["all", "group", "private"] = "all",
    allowed_session: list[str] | None = None,
    enabled: bool = True,
    **metadata: Any,
) -> _Decorator
```

与 `@Tool` 的差异：没有 Tool 那套执行类语义，多出 `timeout_ms`；两阶段协议由返回值约定（见下文）。组件元数据落在 `ReplyExtensionComponentInfo`（`maibot_sdk/types.py`），`collect_components` 会额外输出 `chat_scope` / `allowed_session`。

### parameters 的三种写法

1. `ToolParameterInfo` 列表（与 `@Tool` 相同）。
2. 属性字典，如 `{"attach_voice": {"type": "boolean", "default": False}}`。
3. 完整 object JSON Schema（带 `type`/`properties`/`required`）。

归一化规则：省略或传 `None` 时归一化为 `{"type": "object", "properties": {}}`，并 `setdefault("additionalProperties", False)`。非法声明在导入期即时抛错，不会拖到运行时：

| 情况 | 异常 |
|------|------|
| 非 `dict`/`list` | `TypeError` |
| `list` 中含非 `ToolParameterInfo` | `TypeError` |
| `dict` 根 `type != "object"` | `ValueError` |
| `dict` 属性值不是 JSON Schema 对象 | `TypeError` |
| 最终根 Schema 不是 object | `ValueError` |

⚠️ 主程序侧不支持 `$ref` / `$dynamicRef`，请内联声明；未知顶层参数默认拒绝。
⚠️ **默认值只在模型选中本扩展时才补齐**——声明了参数不会让插件自动启用，模型不选就不调用、不补默认值。

### 作用域与开关

`chat_scope="group"/"private"/"all"`、`allowed_session=[...]`、`enabled` 与其它组件装饰器一致。停用、卸载后，该扩展的参数会从后续 `reply` 声明中移除。

## 两阶段协议

同一个 handler 被调用两次，用 `phase` 关键字参数区分：

| phase | 时机 | 合法返回值 |
|-------|------|-----------|
| `prepare` | 生成正文之前 | `{"extra_prompt": "额外要求"}` 或 `{}` |
| `before_send` | 后处理与附件完成之后、任何消息发送之前 | `{"messages": [...]}` 或 `{}`（保留原样） |

- `prepare` 的 `extra_prompt` 必须是字符串；主程序把它交给 Replyer，并在生成 Hook 的 `extra_prompt` 中提供。Host 侧 `prepare` 只接受字符串 `extra_prompt` 这一个键。
- `before_send` 的 `messages` 是整组待发送消息；返回 `{}` 表示原样保留。Host 侧只接受 `messages` 键。
- 两个阶段共享同一个 `reply_id`，可用来在 `prepare` 与 `before_send` 之间传递状态（如先记住本次要转语音）。

### handler 收到的全部关键字参数

| 参数 | 含义 |
|------|------|
| `phase` | `prepare` 或 `before_send`（见上表） |
| `reply_id` | 本次回复的唯一 ID，两阶段相同；并发回复各自独立 |
| `call_id` | 原始 `reply` 工具调用 ID |
| `session_id` | 聊天流 ID |
| `reply_message_id` | 目标消息 ID |
| `chat` | `platform`、`is_group_chat`、`group_id`、`user_id`、`session_id`、`stream_id` |
| `parameters` | 仅本扩展的参数，已校验并补齐默认值 |
| `text` | `prepare` 时为空；`before_send` 时为生成与 Hook 处理后的完整正文 |
| `messages` | `prepare` 时为空；`before_send` 时为整组待发送消息 |

### 执行顺序

多个扩展按 `(priority, 完整名称字典序)` 从小到大依次处理；上一个扩展的输出会交给下一个。因此改写 `messages` 时要保留别人塞进来的内容。

## 消息组与消息段格式

每条消息是一个 dict，Host 强制校验：

```python
{"segments": [...], "quote_previous": False}
```

- 键必须恰好是 `{segments, quote_previous}` 两个；`quote_previous` 必须是 `bool`；`segments` 必须是非空列表。
- 列表顺序即发送顺序。第一条消息沿用 `reply` 的 `set_quote`；后续消息 `quote_previous=True` 时引用前一条。

消息段沿用 SDK Send 字典协议：`text`、`image`、`emoji`、`voice`、`at`、`reply`、`file`、`forward`、`dict`。Host 侧逐类校验：

| 类型 | data 要求 |
|------|-----------|
| `text` | 必须非空字符串 |
| `image` / `emoji` | 字符串；带 `binary_data_base64` 时必须有效非空 Base64，缺 Base64 时必须有非空 `hash` |
| `voice` | 字符串；**必须**携带有效非空 `binary_data_base64` |
| `at` / `reply` | 需 `target_user_id` / `target_message_id` |
| `file` / `dict` | 非空对象 |

二进制与自定义卡片写法：

```python
# 语音：data 是语音内容描述，音频走 Base64
{"type": "voice", "data": text, "binary_data_base64": base64.b64encode(audio).decode("ascii")}

# 新图片/表情：建议直接带 Base64；原有图片/表情可保留 hash
{"type": "image", "data": "https://...", "binary_data_base64": "..."}

# 自定义卡片
{"type": "dict", "data": {"type": "json", "data": {...}}}
```

⚠️ SDK 不内置 TTS，音频合成由插件自行完成；具体卡片与音频格式取决于消息适配器。
⚠️ **保留原有附件**：改写文字时应原样保留无关的图片、@、表情段和 `quote_previous`，避免丢附件。多插件按顺序转换整组消息，不会对每个文字片段分别调用——所以「整组只合成一次语音再追加」是正确姿势，而不是逐段处理。

## 失败语义

以下任一情况都会让**本次 reply 失败**：空消息组、无效返回值、插件抛异常、超过 `timeout_ms` 超时。

- 在发送前失败（`prepare` 或 `before_send`）时**不会发出任何消息**。
- 插件**不得**直接调用 Send 代理替主程序发送这组回复；发送、历史记录、监控与失败判断都由主程序负责。
- 扩展被停用、卸载或重载时，Host 会主动抛错要求重新发起回复——正在生成的回复不会带着半截状态发出去。

## 平台作用域 platforms

```python
@ReplyExtension("forward_images", platforms="qq", parameters={...})
@ReplyExtension("forward_images", platforms=["qq", "telegram"])
```

- 接口与 `@Tool` 的 `platforms` 一致：省略、`None`、`[]` 表示不限平台；名称去除首尾空白、转小写并去重；空名称及非法类型直接报错。SDK 2.14.0 起 `ReplyExtension` 与 `Tool` 共用同一套 `_normalize_platforms` 校验。
- 它是**组件声明**，不是 `plugin_options` 里的模型参数，与 `chat_scope`、`allowed_session` 同时生效。
- 支持该特性的 Host 只在匹配平台的 `reply.plugin_options` Schema 中暴露该扩展；手动提交其他平台的扩展也会在调用前被拒绝，发送前会再次检查。无上下文的管理清单仍能查看全部扩展。
- ⚠️ 需要 SDK 2.14.0 **且**配套 Host 的平台过滤实现。旧 Host 不执行该限制（扩展对所有平台可见、可调用），部署时必须同时更新主程序，否则会出现「SDK 声明了限制但线上没拦住」的错配。

## 语音示例

```python
import base64
from maibot_sdk import ReplyExtension

@ReplyExtension(
    "voice",
    description="需要语音回复时启用，可选择同时保留文字",
    parameters={
        "attach_voice": {"type": "boolean", "default": False, "description": "是否合成语音"},
        "keep_text": {"type": "boolean", "default": True, "description": "是否同时发送文字"},
    },
    timeout_ms=60000,
)
async def reply_voice(self, *, phase, parameters, text, messages, **context):
    if not parameters["attach_voice"]:
        return {}
    if phase == "prepare":
        return {"extra_prompt": "这次回复会转成语音，请使用适合朗读的自然口语。"}
    audio = await self.synthesize_voice(text)
    result = []
    for message in messages:
        segments = [
            segment for segment in message["segments"]
            if parameters["keep_text"] or segment["type"] != "text"
        ]
        if segments:
            result.append({"segments": segments, "quote_previous": message["quote_previous"]})
    voice = {
        "segments": [{
            "type": "voice", "data": text,
            "binary_data_base64": base64.b64encode(audio).decode("ascii"),
        }],
        "quote_previous": False,
    }
    result.append(voice)
    return {"messages": result}
```

要点：`prepare` 只注入 extra_prompt，`before_send` 只重组消息；整组正文只合成一次音频，原有附件顺序不变。

## 常见陷阱

- 在 `prepare` 阶段去读 `messages`/`text`——它们此时为空，只有 `before_send` 才有值。
- `before_send` 返回的 dict 里塞 `extra_prompt`，或 `prepare` 返回 `messages`——Host 只认各自那一个键，多余键视为无效返回值，直接让本次回复失败。
- 用 Send 代理把扩展产出的消息发出去——会造成重复发送，发送权在主程序。
- 拼消息组时漏掉 `quote_previous` 或写成字符串——Host 校验 `bool` 不通过即失败。
- voice 段忘带 `binary_data_base64`——必填校验失败。
- 忘了在依赖里写 `maibot-plugin-sdk>=2.10.0`，旧 SDK 上导入 `ReplyExtension` 直接报错。
- 用了 `platforms` 但主程序没同步升级——限制静默不生效。

## 版本沿革

- **2.10.0**（2026-10-07）：新增 `@ReplyExtension` 装饰器、`ReplyExtensionComponentInfo`、`ComponentType.REPLY_EXTENSION`；`collect_components` 额外输出 `chat_scope` / `allowed_session`；附 `docs/reply_extensions.md` 与参数化测试。无更名、无废弃。
  - 出处：SDK 仓库 git tag `v2.10.0`（提交 03ece72「feat: 发布 2.10.0 并新增回复扩展接口」，改动 `maibot_sdk/components.py`、`maibot_sdk/types.py`，新增 `docs/reply_extensions.md` 与 `tests/test_reply_extensions.py`），以及 SDK 官方文档 `docs/reply_extensions.md` 声明的依赖下限 `maibot-plugin-sdk>=2.10.0`。
  - ⚠️ 注意：**SDK 的 `CHANGELOG.md` 没有 2.10.0 条目**（版本标题从 `[2.11.0]` 直接跳到 `[2.9.0]`，属 CHANGELOG 遗漏），本条沿革并非出自 CHANGELOG，请勿因查不到而怀疑此记录。
- **2.13.0**（2026-10-13）：`@Tool` 新增仅关键字参数 `platforms`；平台作用域随组件元数据传递，不进入模型调用参数 Schema。
- **2.14.0**（2026-10-15）：`@ReplyExtension` 跟进 `platforms`，与 `@Tool` 共用 `_normalize_platforms`；Host 按当前聊天平台过滤 `reply.plugin_options` 中的扩展，并在准备、发送前各复查一次。
