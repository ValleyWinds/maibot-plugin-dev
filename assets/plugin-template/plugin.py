"""插件入口模板。

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-15 逐行对照源码复核）

包含：
- 生命周期方法（on_load/on_unload/on_config_update，三者均为加载契约必需）
- config_reload_subscriptions 声明（订阅主程序 bot/model 配置变更）
- @Tool / @Command / @HookHandler / @API 示例
- ctx.paths 标准数据目录用法
"""

import os
from typing import Any, ClassVar, Iterable

from maibot_sdk import API, Command, HookHandler, MaiBotPlugin, Tool
from maibot_sdk.types import HookMode, ToolParameterInfo, ToolParamType

from .config import MyPluginConfig


class MyPlugin(MaiBotPlugin):
    """插件主类。

    PluginLoader._validate_sdk_plugin_contract 会检查三个生命周期方法都被覆盖，
    且 config_reload_subscriptions 可归一化，缺一个都会在加载期抛 TypeError。
    """

    config_model = MyPluginConfig

    # 订阅主程序 bot/model 配置热重载（不声明则收不到对应 scope 回调）
    config_reload_subscriptions: ClassVar[Iterable[str]] = ("bot", "model")

    def __init__(self) -> None:
        super().__init__()
        # 初始化实例变量

    # ── 生命周期 ──────────────────────────────────────────────────────

    async def on_load(self) -> None:
        """插件加载时初始化。"""
        self.ctx.logger.info("插件已加载")

    async def on_unload(self) -> None:
        """插件卸载时清理。"""
        self.ctx.logger.info("插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        """配置热重载。scope 为 self/bot/model。

        scope="bot" 时主程序配置变了（如人格），此时 self.config 已自动更新。
        """
        self.ctx.logger.info(f"配置更新: scope={scope}, version={version}")

    # ── Tool（LLM 可调用）────────────────────────────────────────────

    @Tool(
        name="my_tool",
        description="工具描述",
        parameters=[
            ToolParameterInfo(
                name="query",
                param_type=ToolParamType.STRING,
                description="查询内容",
                required=True,
            ),
        ],
    )
    async def tool_my_tool(self, query: str = "", **kwargs: Any) -> dict[str, Any]:
        """LLM Tool。"""
        return {"name": "my_tool", "content": f"查询结果: {query}"}

    # ── Command（用户命令）───────────────────────────────────────────

    @Command(name="my_cmd", pattern=r"^/my_cmd\b", description="示例命令")
    async def cmd_my_cmd(self, **kwargs: Any) -> tuple[bool, str, int]:
        """用户命令。必须返回三元组 (success, response, intercept_level)。

        注意：
        - result[0] 被 Host 忽略；
        - result[1]（response 文本）也不会发给用户：Host 的
          _handle_command_processing_result 只把它写日志并传给
          chat.command.after_execute Hook，下游没有发送逻辑。
          要让用户看到失败原因，只能自己在处理器里调 ctx.send 发消息；
        - result[2] 只做布尔判定，任意非零值都会中断消息链，没有「档位」语义，
          因此示例统一返回 1，别指望 2 比 1 更「强」；
        - kwargs 里可用 stream_id / group_id / platform / user_id /
          matched_groups / message / plugin_config。
        """
        stream_id = str(kwargs.get("stream_id", ""))
        try:
            # send.text 默认返回 bool；需要 message_id 时加 return_details=True
            await self.ctx.send.text(text="命令执行成功", stream_id=stream_id)
            return True, "已发送", 1
        except Exception as e:
            self.ctx.logger.error(f"发送失败: {e}")
            return False, str(e), 1

    # ── HookHandler（命名 Hook）──────────────────────────────────────

    @HookHandler("maisaka.replyer.before_request", mode=HookMode.BLOCKING)
    async def on_replyer_before_request(self, **kwargs: Any) -> dict[str, Any]:
        """注入额外回复要求（追加而非覆盖）。

        该 Hook 的 kwargs 为：session_id、request_type、task_name、model_name、
        extra_prompt、attempt、retry_count、max_retries、reply_message_id、
        reply_reason、selected_expression_ids、reply_tool_args。
        注意：
        - extra_prompt 只在 replyer 链存在，planner 的 before_request 没有该字段；
        - modified_kwargs 是整体替换，务必把整份 kwargs 带回去；
        - 该 Hook 声明了 allow_abort=False，返回 {"action": "abort"} 会被忽略
          并记一条 error，这里只能返回 continue。
        """
        suffix = "\n【补充信息】..."
        kwargs["extra_prompt"] = (kwargs.get("extra_prompt") or "") + suffix
        return {"action": "continue", "modified_kwargs": kwargs}

    # ── API（供其他插件调用）─────────────────────────────────────────

    @API(name="my_api", description="示例 API", version="1", public=True)
    async def api_my_api(self, **kwargs: Any) -> str:
        """公开 API。只有 public=True 才能被其他插件 ctx.api.call 调用。"""
        return "API 返回值"

    # ── 内部方法 ─────────────────────────────────────────────────────

    def _get_plugin_dir(self) -> str:
        """获取插件源码目录（用于定位随源码分发的模板/静态资源）。

        注意：运行时数据不要写这里，用 ctx.paths.data_dir / runtime_dir。
        """
        return os.path.dirname(os.path.abspath(__file__))

    def _get_data_dir(self) -> str:
        """插件持久化数据目录（Host 授予的标准路径，2.6.0+）。"""
        return str(self.ctx.paths.data_dir)


def create_plugin() -> MaiBotPlugin:
    """MaiBot 插件工厂函数。PluginLoader 优先调用它来实例化插件。"""
    return MyPlugin()
