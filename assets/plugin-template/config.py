"""插件配置模型模板。

> **校对基线：SDK 2.16.0 + MaiBot Host 1.3.15**（2026-10-24 对照源码复核导入符号与配置语义）

基于 MaiBot SDK PluginConfigBase + pydantic Field。
声明 config_model 后，self.config 返回强类型实例，WebUI Schema 自动生成。

要点：
- 所有字段必须有默认值，否则 build_plugin_default_config 构造默认配置会失败
- 所有字段放进命名节（如 [plugin]），不要留根级字段
- [plugin].config_version 是强校验字段：缺失或为空都会让插件以「配置错误」状态注册，
  业务被暂停，仅加载配置管理（WebUI 列表仍显示 load_status=success，只有日志 warning 可见）。
  注意：该校验只对**声明了 config_model** 的插件生效——删掉本文件、纯 Hook/Command 插件缺版本号
  不会报错（runner_main.py 的 _prepare_plugin_config_for_version_update 对空 default_config 直接跳过）
- ⚠️ [plugin].enabled 是**宿主保留键**，禁止在配置模型里声明：
  Host 用它做插件启停门禁（runner 的 _is_plugin_enabled / _prepare_plugin_activation，
  值为 false 时插件直接 INACTIVE、跳过 on_load 与组件注册），WebUI 的启停开关
  （config_routes.py 的 toggle_plugin）也写这同一个键；模型未声明时，Host 的
  _restore_host_reserved_plugin_config 会在归一化后把磁盘上的值带回，行为完全不受影响。
  若在模型里重复声明 enabled，配置表单里会多出一个与顶部启停开关同键的冗余开关，
  语义混淆且关掉即停用整个插件，不是业务级"暂停"。
  需要插件自研的总开关时，请放进自己的业务节并换个名字（如 [features].xxx_enabled）。
"""

from __future__ import annotations

from typing import Any, ClassVar

from maibot_sdk import Field, PluginConfigBase

CONFIG_SCHEMA_VERSION = "1.0.0"


class PluginConfig(PluginConfigBase):
    """插件基础配置。

    只声明 config_version 一个字段。
    [plugin].enabled 是宿主保留键（WebUI 启停开关与 runner 激活门禁共用），
    模型无需也不应声明，详见模块 docstring。
    """

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    config_version: str = Field(
        default=CONFIG_SCHEMA_VERSION,
        description="配置版本，请勿手动修改。",
        json_schema_extra={
            "disabled": True,
            "hidden": True,
            "label": "配置版本",
            "order": 99,
        },
    )


class MyPluginConfig(PluginConfigBase):
    """插件完整配置。

    每个命名节对应 config.toml 里的一个 [section]，字段通过
    self.config.<section>.<field> 访问。
    """

    plugin: PluginConfig = Field(default_factory=PluginConfig)
