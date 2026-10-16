"""插件配置模型模板。

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）

基于 MaiBot SDK PluginConfigBase + pydantic Field。
声明 config_model 后，self.config 返回强类型实例，WebUI Schema 自动生成。

要点：
- 所有字段必须有默认值，否则 build_plugin_default_config 构造默认配置会失败
- 所有字段放进命名节（如 [plugin]），不要留根级字段
- [plugin].config_version 是强校验字段：缺失或为空都会让插件以「配置错误」状态注册，
  业务被暂停，仅加载配置管理
"""

from __future__ import annotations

from typing import Any, ClassVar

from maibot_sdk import Field, PluginConfigBase

CONFIG_SCHEMA_VERSION = "1.0.0"


class PluginConfig(PluginConfigBase):
    """插件基础配置。"""

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
    enabled: bool = Field(
        default=True,
        description="插件总开关。",
        json_schema_extra={
            "hint": "打开后插件才会工作。",
            "label": "启用插件",
            "order": 0,
        },
    )


class MyPluginConfig(PluginConfigBase):
    """插件完整配置。

    每个命名节对应 config.toml 里的一个 [section]，字段通过
    self.config.<section>.<field> 访问。
    """

    plugin: PluginConfig = Field(default_factory=PluginConfig)
