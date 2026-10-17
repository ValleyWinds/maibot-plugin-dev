---
name: isolated-import-testing
description: 如何脱离 MaiBot 宿主，单独导入插件 plugin.py 并对纯函数做可复现验证（stub harness 套路）
---

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）

# 脱离宿主导入插件做纯函数验证

用途：**review / 排障陌生插件**时，把「猜原因」变成「跑出证据」。不启动 MaiBot、不需要真实 Host、不需要 LLM，
就能直接调用 `plugin.py` 里的纯函数并复现 bug。

## 为什么需要 stub harness

`plugin.py` 顶层通常有这些导入，脱离宿主会直接 `ImportError`：

```python
from maibot_sdk import Command, MaiBotPlugin
from maibot_sdk.types import HookMode
from src.config.model_configs import TaskConfig
from src.llm_models.utils_model import LLMOrchestrator
```

只要用最小 stub 顶掉它们，模块就能被 `importlib` 加载。

## 套路

1. 建一个独立目录（**不要放进插件仓库**，避免污染 git 状态）：

```text
<scratch>/
  stubs/
    maibot_sdk/__init__.py     # MaiBotPlugin / Field / PluginConfigBase / 各组件装饰器
    maibot_sdk/types.py        # HookMode / HookOrder / ErrorPolicy / ToolParameterInfo ...
    src/__init__.py
    src/config/__init__.py
    src/config/model_configs.py       # class TaskConfig
    src/llm_models/__init__.py
    src/llm_models/utils_model.py     # class LLMOrchestrator
  repro.py
```

2. stub 内容要点（`maibot_sdk/__init__.py`）：

```python
# stubs/maibot_sdk/__init__.py
class MaiBotPlugin:
    config_model = None
    config_reload_subscriptions = ()
    def __init__(self, *args, **kwargs): pass
    def get_components(self): return []
    def get_dynamic_api_components(self): return []
    def get_webui_config_schema(self, **kwargs): return {"sections": {}}

class PluginConfigBase: pass

def Field(default=None, description="", **kwargs): return default

class _FakeInfo:
    """模拟 __maibot_component_info__（真实 SDK 里是 pydantic 模型）"""
    def __init__(self, **kw): self.__dict__.update(kw)
    def model_dump(self, **kw): return dict(self.__dict__)

def _make_decorator(kind):
    """同时兼容 @X 与 @X(...) 两种写法"""
    def wrap(*args, **kwargs):
        if len(args) == 1 and not kwargs and callable(args[0]):
            return args[0]
        def decorator(func):
            setattr(func, "__maibot_component_info__", _FakeInfo(name="", type=kind, metadata={}))
            return func
        return decorator
    return wrap

Command      = _make_decorator("command")
Tool         = _make_decorator("tool")
API          = _make_decorator("api")
EventHandler = _make_decorator("event_handler")
ReplyExtension = _make_decorator("reply_extension")
MessageGateway  = _make_decorator("message_gateway")
HomeCard     = _make_decorator("home_card")
LLMProvider  = _make_decorator("llm_provider")

class HookHandler:                      # HookHandler 第一个位置参数是 hook 名
    def __init__(self, *args, **kwargs): pass
    def __call__(self, func): return func

def Action(*args, **kwargs):            # 2.x 已废弃，仅做占位
    def decorator(func): return func
    return decorator

def WorkflowStep(*args, **kwargs):      # SDK 2.0 起已移除，真实调用会 raise RuntimeError
    raise RuntimeError("`WorkflowStep` 已移除，请改用 `HookHandler`")
```

```python
# stubs/maibot_sdk/types.py
from enum import Enum

class HookMode(str, Enum):
    BLOCKING = "blocking"
    OBSERVE = "observe"

class HookOrder(str, Enum):
    EARLY = "early"
    NORMAL = "normal"
    LATE = "late"

class ErrorPolicy(str, Enum):
    SKIP = "skip"

class ActivationType(str, Enum):
    ALWAYS = "always"
    KEYWORD = "keyword"
    PROBABILITY = "probability"

class ChatMode(str, Enum):
    NORMAL = "normal"

class EventType(str, Enum):
    ON_MESSAGE = "on_message"

class ToolParamType(str, Enum):
    STRING = "string"

class ToolParameterInfo(dict):
    pass
```

⚠️ stub 必须覆盖到被测插件实际 import 的符号，缺一个就落进 `except ImportError` 分支。SDK 2.14.0 的装饰器全集（`maibot_sdk/__init__.py` 的 `__all__`）：`Command` / `Tool` / `API` / `EventHandler` / `ReplyExtension` / `HookHandler` / `MessageGateway` / `HomeCard` / `LLMProvider` / `Action`（已废弃）/ `WorkflowStep`（已移除）；类型枚举在 `maibot_sdk/types.py`，`Field` 与 `PluginConfigBase` 在 `maibot_sdk/config.py`。

3. 用 `importlib` 按路径加载，当作普通模块用：

```python
import importlib.util, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PLUGIN = BASE.parent / "<repo>"          # 插件目录（含 plugin.py）
sys.path.insert(0, str(BASE / "stubs"))

pkg = "ssp_plugin"
spec = importlib.util.spec_from_file_location(
    pkg,
    PLUGIN / "plugin.py",
    submodule_search_locations=[str(PLUGIN)],   # 相对导入必需
)
mod = importlib.util.module_from_spec(spec)
mod.__path__ = [str(PLUGIN)]                   # 同上，缺了就是 ImportError
sys.modules[pkg] = mod            # 必须先注册，模块内部若有自引用才不炸
spec.loader.exec_module(mod)

mod._split_text_at_brackets("...")       # 直接调纯函数
```

## 关键陷阱

- **`pydantic` 不一定需要**。插件普遍写成 `try: from maibot_sdk import Field, HookHandler, PluginConfigBase / except ImportError:` 回退到 pydantic。
  只要 stub 里**同时提供** `Field` 和 `PluginConfigBase`，走的就是 stub 分支，无需安装 pydantic。
  反之若只提供一部分，就可能落进 `except` 分支去找 pydantic 而失败。
- **插件目录内的相对导入会让裸 `spec_from_file_location` 直接失败**。插件模板（`plugin-template/plugin.py`）就是
  `from .config import MyPluginConfig` 这种写法；不设 `submodule_search_locations` 且不给 `mod.__path__` 赋值，
  `exec_module` 时抛 `ImportError: attempted relative import with no known parent package`。
  这不是插件 bug，是加载方式不对——照上面第 3 步写即可。
- **注解在函数定义时求值**。`def f(self, task_config: TaskConfig)` 这种注解会在 `def` 执行时求值（没有 `from __future__ import annotations`），
  所以 `TaskConfig`、`LLMOrchestrator`（含作为基类被继承）**必须真实存在**，不能省略。
- **decorator 必须是「可调用 → 返回 decorator」或「可调用」两种形态都兼容**：`@Command("name", pattern=...)` 和 `@HookHandler("hook", name=...)`
  用法不同，stub 要写成 `__init__` + `__call__` 或返回闭包。
- **`__maibot_component_info__` 挂错位置等于没测**。真实 SDK 的 `collect_components`（`maibot_sdk/components.py`）是扫实例属性上的这个标记，
  再 `model_dump` 成组件声明；stub 只保证「模块能 import」，组件元数据的字段正确性要靠真实 SDK 路线验（见下）。
- **测试后处理管线时用 monkeypatch**。模块里的 `_merge_x` / `_split_y` 之间是通过模块全局名互相调用的，
  直接改模块属性即可让「下游函数」走你的补丁版本，无需改动仓库源码：

```python
orig = mod._has_unbalanced_brackets
mod._has_unbalanced_brackets = lambda text: orig(mask_something(text))
```

- **验证「修复有效」要做前后对比**：先记录原始函数结果，再替换，再跑同一批样本输出对照表。
  同时必须包含「不应改变」的对照组（例如 RP 旁白 `（理理缓缓起身）`），证明没有引入回归。

## 有真实 SDK 源码时：直接注入真实 SDK（优于 stub）

本地有 `maibot-plugin-sdk` 源码副本时，优先用真实 SDK 而不是 stub——配置模型、组件装饰器、
默认值生成等判定与 Host 完全一致，不需要手工维护 stub（stub 覆盖不到的行为差异就是误判来源）。

```python
# verify.py —— 不需要 stubs/ 目录
import importlib.util, sys
from pathlib import Path

sys.path.insert(0, str(Path("<sdk-repo>")))   # SDK 源码根目录（含 maibot_sdk/）
PLUGIN = Path("<plugin_dir>")

pkg = "plugin_under_test"
spec = importlib.util.spec_from_file_location(
    pkg,
    PLUGIN / "plugin.py",
    submodule_search_locations=[str(PLUGIN)],   # 插件目录内有相对导入时必需
)
mod = importlib.util.module_from_spec(spec)
mod.__path__ = [str(PLUGIN)]                   # 缺了会 ImportError: attempted relative import
sys.modules[pkg] = mod
spec.loader.exec_module(mod)

plugin = mod.create_plugin()  # 直接实例化、直接断言
```

⚠️ `build_plugin_default_config` 不在包根导出，从 `maibot_sdk.config` 导入（`from maibot_sdk import build_plugin_default_config` 会 ImportError）。

SDK 2.14.0 运行时真正需要的第三方依赖只有 `pydantic`（`maibot_sdk/config.py` / `types.py` / `messages.py` 等直接 import），PIL 视插件而定。`msgpack` 只是 `pyproject.toml` 的声明项，SDK 源码里没有任何一处 import 它，本地缺了也能跑通——真正使用 msgpack 的是 Host 侧 `src/plugin_runtime/protocol/codec.py` 的插件进程间 RPC 编解码，与这条独立导入验证路线无关（SDK 自带的 `docs/guide.md` 重复了「运行时依赖 pydantic + msgpack」的过时说法，勿被带偏）。用 uv 临时环境补齐即可，不污染系统 Python：

```bash
# msgpack 非必需，仅是声明项，多装无害
uv run --with pydantic --with msgpack --with pillow python verify.py
```

可断言的项（fork 适配 / 新插件发布前跑一遍）：

| 断言 | 依据 |
| --- | --- |
| 生命周期三方法**被覆盖**（不只是签名对）：`on_load()` / `on_unload()` 0 参、`on_config_update` 3 参（`scope` / `config_data` / `version`） | `maibot_sdk/plugin.py` 的 `MaiBotPlugin.on_load` / `on_unload` / `on_config_update`；Host 侧 `plugin_loader.py` 的 `_validate_sdk_plugin_contract` 检查 `type(instance).on_load is MaiBotPlugin.on_load`，未覆盖直接 `TypeError` |
| `create_plugin()` 可调用并返回 `MaiBotPlugin` 子类实例 | `_validate_sdk_plugin_contract` 的 `isinstance(instance, MaiBotPlugin)` |
| `get_config_reload_subscriptions()` 可调用且不抛 | 同上，契约校验会调用它；`config_reload_subscriptions` 写成字符串会 `TypeError` |
| 每个组件方法带 `__maibot_component_info__`，元数据含 `name`、`type`、`handler_name` | `maibot_sdk/components.py` 的 `collect_components` |
| `build_plugin_default_config(config_model)` 成功（所有字段有默认值） | `maibot_sdk/config.py` 的 `build_plugin_default_config`，字段无默认值时抛 `ValueError` |
| `config.toml` 可被 `tomllib` 解析并 `config_model.model_validate` 通过，含 `[plugin]` 节的 `config_version` | `maibot_sdk/config.py` 的 `extract_plugin_config_version`（缺失抛 `PluginConfigVersionError`）；Host 侧 `runner_main.py` 的 `_load_plugin_config` 用 `tomllib.load` |
| manifest 必填字段齐全、无多余字段 | `src/plugin_runtime/runner/manifest_validator.py` 的 `PluginManifest`（基类 `_StrictManifestModel` 是 `extra="forbid"`，多一个字段就校验失败） |
| `manifest_version` 为 `2`；`version` / 区间上下界都是严格三段式语义版本 | `PluginManifest.manifest_version`（`Literal[2]`）与 `VersionComparator.is_valid_semver` |
| `sdk` 区间覆盖 2.14.0、`host_application` 区间覆盖 1.3.9 | `PluginManifest` 的 `ManifestVersionRange`（闭区间，`min_version > max_version` 直接失败） |
| `author` / `urls.repository` 存在且是 http(s) URL | `ManifestAuthor` / `ManifestUrls` |
| `capabilities` 字段存在（缺失即校验失败），无空字符串项、无重复项；其中每个能力都要能在 plugin.py 里找到对应 `ctx.*` 调用点 | `PluginManifest.capabilities`（`List[str]` 无默认值，缺失报 missing）；`_validate_capabilities` 只校验非空项与去重——**空数组合法**，无能力时写 `[]` |

manifest 必填清单（`PluginManifest`）：`manifest_version`、`version`、`name`、`description`、`author`（`name` + `url`）、
`license`、`urls`（`repository`）、`host_application`、`sdk`、`capabilities`、`i18n`、`id`；
可选（有默认值，可省略）：`dependencies`、`llm_providers`、`plugin_type`、`display`、`changelog`。

⚠️ `capabilities` 与代码调用点要**双向核对**：manifest 声明了但代码没用到 = 冗余声明；代码调了但 manifest 没声明 = 运行时被 Host 拦。
少数 Host 侧内部能力（如消息路由 / 网关状态）不需要也无法写进 `capabilities`。

## GitHub 克隆

仓库在国内直连慢/超时，用前缀式镜像：

```bash
git clone https://gh-proxy.com/https://github.com/<owner>/<repo>.git
```

若返回 `CONNECT tunnel failed, response 502`，换一个镜像前缀（`ghfast.top` / `ghproxy.net`）重试即可。
