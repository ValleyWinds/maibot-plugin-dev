# MaiBot 插件配置模型与 WebUI 配置渲染参考

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）

插件配置是一条完整链路：`config.py` 的 Pydantic 模型 → Runner 归一化落盘 `config.toml` →
Host 生成 WebUI Schema → dashboard 表单渲染与保存 → 配置变更热更新回插件。
本文按这条链路组织，事实来源为 `maibot_sdk/config.py`、`maibot_sdk/plugin.py`、
`src/plugin_runtime/runner/runner_main.py`、`src/webui/routers/plugin/config_routes.py`、
`dashboard/src/routes/plugin-config.tsx`。

---

## 1. 配置模型基础

```python
from maibot_sdk import PluginConfigBase, Field

class MyPlugin(MaiBotPlugin):
    config_model = MyConfig      # 声明后 self.config 返回强类型实例
```

- `self.config` — 强类型配置实例；未声明 `config_model` 或配置尚未注入时抛 `RuntimeError`
- `self.get_plugin_config_data()` — 原始 dict 副本，始终可用（未声明 `config_model` 时是唯一入口）
- `self.get_default_config()` / `self.get_webui_config_schema()` — 默认配置与 Schema
- 基类 `model_config` 是 `validate_assignment=True, extra="ignore"`：配置里多出来的键会被静默丢弃，
  **模型里删掉的字段对应的用户配置不会报错，只是不再生效**

### 必须遵守的三条硬规则

1. **所有字段必须有默认值**（`default` 或 `default_factory`）。`build_plugin_default_config` 直接实例化模型，
   无默认值即抛：`插件配置模型 {name} 需要为所有字段提供默认值，当前无法构造默认配置`。
   `list` / `dict` / 嵌套模型等可变类型一律用 `default_factory`（否则多个实例共享同一可变对象）。
2. **不要把字段放在模型根级**。SDK 的 `generate_plugin_config_schema` 会把根级扁平字段归入一个名为
   `general` 的节（`"title": "通用设置"`），而 TOML 里它们位于根级、并不存在 `[general]` 表。
   所有字段都放进命名 `PluginConfigBase` 子类节（如 `infos_section: InfosSectionConfig`），
   对应 TOML 结构 `[infos_section]` / `[[infos_section.infos]]`。
3. **`[plugin]` 节必须含 `config_version`**，且模型要有同名字段提供默认值（见第 4 节）。

> Host 1.3.9 已对根级字段做了兼容（`_fold_root_fields_into_virtual_general` 读取时折进 `general`、
> `_unfold_virtual_general_into_root` 保存时还原回根级），表单读写不再错位。但跨 Host 版本行为不一致，
> 且根级字段在 TOML 里没有归属节，仍应全部放进命名节。

### 宿主保留键 `[plugin].enabled`

插件启停开关由 Host 解释，**不需要也不应该**在配置模型里声明。Runner 归一化按 `model_dump`
（`extra="ignore"`）会丢掉模型未声明的键，`_restore_host_reserved_plugin_config` 会把它从原始配置带回。
`config.toml` 里手写 `enabled` 同样有效。

---

## 2. 配置节与字段的 UI 元数据

### 节级（`PluginConfigBase` 子类的 ClassVar）

| 属性 | 作用 | 缺省 |
|------|------|------|
| `__ui_label__` | 节标题 | 字段名（即 TOML 节名） |
| `__ui_icon__` | 图标名 | `None` |
| `__ui_order__` | 排序序号，越小越靠前 | 字段在模型中的声明序号 |
| `__ui_i18n__` | 节多语言文本 | 空 |

节描述**来自配置类的 docstring**（`_build_section_schema` 取 `config_class.__doc__`）。
docstring 只写用户能懂的一句话（如「插件基础配置。」），开发者的技术注释用 `#` 注释放字段上方。

### 字段级 `json_schema_extra`

```python
enabled: bool = Field(
    default=True,
    description="插件总开关。",           # 列表项 label 的缺省值，也作 WebUI 描述
    json_schema_extra={
        "label": "启用插件",              # 缺省 = 英文字段名
        "hint": "打开后插件才会工作。",
        "placeholder": "",
        "order": 0,
        "group": "",                     # 前端分组
        "disabled": False,               # 渲染为禁用控件
        "hidden": True,                  # 表单不渲染（config_version 用）
        "input_type": "",                # 配合 text ui_type
        "x-widget": "textarea",          # 覆盖默认控件
        "x-icon": "",
        "rows": 3,
        "step": 1,
        "pattern": "",
        "max_length": 0,
        "min_items": 0,
        "max_items": 0,
        "depends_on": "",                # 依赖字段名
        "depends_value": None,
        "example": None,
        "i18n": {"en_US": {"label": "..."}, "ja_JP": {...}},
    },
)
```

**字段 label 缺省取英文字段名**（`_build_field_schema` 的 `str(json_extra.get("label") or field_name)`），
中文名必须逐字段传 `label`。嵌套列表项的字段 label 缺省取 `description`
（`_extract_list_item_schema`：`json_extra.get("label") or field_info.description or field_name`），
所以列表项写中文 `description` 即可。

### 类型 → 控件映射

`_map_field_type` + `_default_ui_type` 决定渲染控件：

| Python 注解 | `type` | `ui_type` | 控件 |
|---|---|---|---|
| `bool` | `boolean` | `switch` | 开关 |
| `int` / `float` | `integer` / `number` | `number` | 数字输入（读 `min`/`max`/`step`） |
| `str` | `string` | `text` | 单行输入 |
| `list[Literal[...]]` | `select` | `select` | **多选**（`multiple: True`） |
| `Literal[...]` | `select` | `select` | 单选下拉 |
| `list[PluginConfigBase]` | `array` | `list` | 列表编辑器（`item_type: object`，`item_fields` 描述每项字段） |
| `list[str]` / `list[int]` | `array` | `list` | 简单列表 |
| `dict` / `PluginConfigBase` | `object` | `json` | JSON 编辑 |

`ui_type` 可用 `x-widget` 覆盖为 `textarea` / `slider` / `password` 等；`textarea`、`list`、`slider`
在表单里占整行（`getFieldGridClassName`）。

字段在表单里的顺序 = `json_schema_extra["order"]`，缺省为声明序号；`hidden: True` 的字段被前端过滤掉。

### 多语言

两级结构都是 `{locale: {key: text}}`，由 SDK 的 `_normalize_i18n` 归一化（空文本被丢弃）：

- 节级 `__ui_i18n__`：`{"en_US": {"title": "Settings", "description": "..."}, "ja_JP": {...}}`
- 字段级 `json_schema_extra={"i18n": {...}}`：支持 `label` / `hint` / `placeholder`
- 前端 `resolveLocalizedText` 按当前语言候选（`zh`→`zh_CN`/`zh-CN`，`en`→`en_US`，`ja`→`ja_JP`…）
  逐级回退，最终回落到 schema 里的原始值

---

## 3. WebUI 渲染与保存链路

```
GET /api/plugin/config/{id}/bundle
  → runtime.inspect_plugin_config（Runner 归一化后的配置 + Schema）
  → 根级扁平字段折叠进 general 节
  → {schema, config, raw_config, message}

前端 SectionRenderer：getNestedRecord(config, section.name) 取值，按 order 排序、过滤 hidden
  → PUT /api/plugin/config/{id}（结构化补丁，deep_merge 到当前配置上，先经运行时校验）
  → PUT /api/plugin/config/{id}/raw（整份 TOML 源码，保存前 tomlkit 解析校验）
```

- 保存前会经运行时 `inspect`/`validate` 一遍，配置非法返回 400 并写回 `config_error`
- 每次保存/重置都会先备份（见第 6 节）
- 原始 TOML 编辑入口适合排查「表单里看不到的键」；结构化表单适合日常维护

---

## 4. 配置版本与重建语义

### 强校验（缺版本号即拒载）

`extract_plugin_config_version` 要求 `config.toml` 的 `[plugin]` 节含非空 `config_version`：

- 缺 `[plugin]` 节：`插件配置文件缺少 [plugin] 配置节，且必须提供 plugin.config_version 版本号`
- 缺/空 `config_version`：`插件配置文件缺少 plugin.config_version 版本号，当前版本策略不再兼容无版本配置`

触发后 `_prepare_plugin_activation` 记下 `config_error`：**插件只注册配置管理状态，业务全部暂停**
（组件不注册、`on_load` 不调用、RPC 返回「插件配置错误，业务暂停」）。在 WebUI 改好配置保存后
会以 `config_repaired` 自动重新激活，无需重启主程序。

### 重建触发条件

`_prepare_plugin_config_for_version_update` 用 `compare_versions(current, latest)` 判断：

- **只有默认版本号「上调」才重建**（`new_parts > old_parts`）
- 版本号相同或**下调都不重建**，旧配置原样归一化

⚠️ **下调版本号会永久埋雷**：假设 2.0.0 删了字段、用户升到 2.0.0 后字段已被清掉；你再把默认版本号
改回 1.5.0 发一版，老用户的配置停留在 2.0.0 → 不触发重建 → 已删字段永远回不来。
版本号只升不降，要回退配置结构就换插件 id（新 id 不继承旧配置）。

`compare_versions` 是**纯点分整数列表比较，不是语义化版本**：

- `1.0` vs `1.0.0` → 判为「有更新」（列表 `[1,0] < [1,0,0]`），每次启动都重建并落盘。版本号一律写三段式
- 带 `-beta`/`rc1` 之类后缀会 `ValueError`，被当成配置错误处理

### 重建时保留什么

Host 版 `rebuild_plugin_config_data` 以**最新默认配置为骨架**，只把旧配置里「键仍存在且类型匹配」的值
覆盖回去：

- 新增字段 → 用默认值补齐
- 已删字段 → **直接丢弃**（用户改过的值一起没）
- 保留的字段 → 用户值优先；但类型不匹配时跳过、回落默认值
- `config_version` 始终取默认值

Runner 侧写回 `config.toml` 时走 `_merge_plugin_config_document`：以 tomlkit「更新已有键、补充缺失键」
的方式尽量保留用户手写的注释和格式；保留失败（如用户写了非标准 TOML）才整文件重写。

---

## 5. 配置热重载订阅

```python
from typing import ClassVar, Iterable

class MyPlugin(MaiBotPlugin):
    config_reload_subscriptions: ClassVar[Iterable[str]] = ("bot", "model")
```

- `("bot",)` — 主程序 bot 配置变更（人格、聊天行为等）
- `("model",)` — 模型配置变更
- **只支持这两个 scope**，其它值在 `normalize_config_reload_subscription` 抛
  `不支持的配置热重载订阅: {value}`（字符串直接赋值也会抛 TypeError，必须是可迭代集合）
- **不声明就收不到对应 scope 的 `on_config_update` 回调**——Host 按
  `scope in registration.config_reload_subscriptions` 过滤订阅者
- 插件**自身** `config.toml` 的变化不通过该字段声明：Host 有 per-plugin 文件监听，变化即派发
  `scope="self"` 的 `on_config_update`（该分支会重新走一遍 `_apply_plugin_config`，
  `self.config` 已是最新值）

### 回调签名（三个参数，缺一不可）

```python
async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
    # scope: "self" / "bot" / "model"
    # config_data: 该 scope 的最新配置（bot/model 时是主程序配置，不是插件配置）
    # version: 配置版本号；bot/model 广播时 Host 传的是空串
```

`on_config_update` 是抽象生命周期方法，未实现时 `plugin_loader` 直接抛
`插件 {id} 必须实现 on_config_update()`。抛异常会被记录为错误响应，不影响其它插件。

---

## 6. 配置文件位置与备份

- 位置：插件目录下的 `config.toml`（`get_plugin_config_path` → `plugin_dir / "config.toml"`）
- 启动时若文件不存在且模型有默认配置，Runner 自动生成并落盘
- **备份目录：`<插件目录>/config_back/`**
- 备份文件名：`config.toml.backup.YYYYMMDDHHMMSS` / `config.toml.reset.YYYYMMDDHHMMSS`
  （`backup_file`，时间戳精确到秒；同秒多次保存会互相覆盖）
- WebUI 保存（结构化与原始 TOML）都是**复制**备份；「重置配置」是 `shutil.move`——原文件被移走，
  运行时刷新为默认配置
- 备份文件不会被插件加载器识别为插件，可安全删除

---

## 7. 完整示例

```python
# config.py
"""插件配置模型。"""

from __future__ import annotations

from typing import ClassVar, Literal

from maibot_sdk import Field, PluginConfigBase
from pydantic import field_validator

CONFIG_SCHEMA_VERSION = "1.0.0"


class PluginConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0
    __ui_i18n__: ClassVar[dict[str, dict[str, str]]] = {
        "en_US": {"title": "Settings"},
        "ja_JP": {"title": "設定"},
    }

    config_version: str = Field(
        default=CONFIG_SCHEMA_VERSION,
        description="配置版本，请勿手动修改。",
        json_schema_extra={"disabled": True, "hidden": True, "label": "配置版本", "order": 99},
    )
    enabled: bool = Field(
        default=True,
        description="插件总开关。",
        json_schema_extra={"hint": "打开后插件才会工作。", "label": "启用插件", "order": 0},
    )


class InfosSectionConfig(PluginConfigBase):
    """需要注入的补充信息。"""

    __ui_label__: ClassVar[str] = "信息注入"
    __ui_icon__: ClassVar[str] = "info"
    __ui_order__: ClassVar[int] = 1

    enabled: bool = Field(default=False, description="是否注入补充信息。")
    modes: list[Literal["chat", "group", "private"]] = Field(
        default_factory=list,
        description="生效范围，可多选。",
        json_schema_extra={"label": "生效范围", "order": 1},
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="触发关键词。",
        json_schema_extra={"label": "关键词", "order": 2},
    )


class MyConfig(PluginConfigBase):
    """插件完整配置。"""

    plugin: PluginConfig = Field(default_factory=PluginConfig)
    infos_section: InfosSectionConfig = Field(default_factory=InfosSectionConfig)

    @field_validator("plugin", mode="before")
    @classmethod
    def _normalize_plugin(cls, value: object) -> object:
        return PluginConfig(**value) if isinstance(value, dict) else value
```

对应的 `config.toml`：

```toml
# 插件配置文件
# 修改后可通过 WebUI 或重启插件生效

[plugin]
config_version = "1.0.0"
enabled = true

[infos_section]
enabled = false
modes = ["chat", "group"]
keywords = ["你好", "在吗"]
```

WebUI Schema 里 `sections` 含两个键 `plugin` 与 `infos_section`（顺序由 `__ui_order__` 决定），
各节 `fields` 按 `order` 排序，`config_version` 因 `hidden` 不出现在表单里。
列表字段 `modes` 渲染为多选（选项来自 `Literal` 参数），`keywords` 渲染为简单列表编辑器。

---

## 8. 排查速查

| 现象 | 原因 | 处理 |
|------|------|------|
| 启动报「当前版本策略不再兼容无版本配置」 | `config.toml` 缺 `[plugin].config_version` | 补上，与模型默认值一致 |
| 插件在列表里但业务不工作、日志有「配置错误，仅加载配置管理」 | `config_error`：版本缺失 / 模型校验失败 | WebUI 打开该插件配置页看 `config_error`，修正保存后自动恢复 |
| 改字段名后用户配置没变 | 版本号没上调，未触发重建 | 上调 `config_version`（只升不降） |
| 每次重启配置都被重写 | 版本号段数不一致（如 `1.0` vs `1.0.0`） | 统一三段式版本号 |
| 表单里某些字段不显示 | `hidden: True`，或字段在模型根级 | 检查 `json_schema_extra`，字段移入命名节 |
| 字段名是英文 | 没传 `label` | 逐字段补 `json_schema_extra={"label": "..."}` |
| 表单里看不到某节描述 | 节类没写 docstring | 给配置类加一句话 docstring |
| 收不到 bot/model 配置变更回调 | 没声明 `config_reload_subscriptions` | 加 `("bot", "model")` |
| `on_config_update` 不被调用 | 方法签名不是三参数，或未实现 | `async def on_config_update(self, scope, config_data, version)` |
