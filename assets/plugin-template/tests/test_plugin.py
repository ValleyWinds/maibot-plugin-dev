"""SDK 测试注入点示例：真实 SDK、只假最外层 RPC 通道（SDK 2.16.0 实测通过）。

跑法（本地有任意可用 Python 即可，不需要 MaiBot 宿主）：

    uv run --with pytest --with pydantic python -m pytest

其中 maibot_sdk 取自本地源码仓库或已安装的 SDK；详见 references/plugin-testing.md 第 1 层。
"""

import asyncio

from maibot_sdk.context import PluginContext


def test_config_injection(plugin_module):
    """注入点 1：set_plugin_config——注入 dict 必须带 [plugin].config_version 节。"""
    plugin = plugin_module.create_plugin()
    plugin.set_plugin_config({"plugin": {"config_version": "1.0.0"}})
    assert plugin.config.plugin.config_version == "1.0.0"


def test_command_with_fake_rpc(plugin_module):
    """注入点 2：_set_context + 假 rpc_call——断言 send.text 的 wire 级参数与三元组返回。"""
    async def fake_rpc(method, plugin_id, payload):
        assert method == "cap.call"
        assert payload["capability"] == "send.text"
        assert payload["args"]["text"] == "命令执行成功"
        return {"success": True}

    plugin = plugin_module.create_plugin()
    plugin._set_context(PluginContext("com.example.my-plugin", rpc_call=fake_rpc))
    success, response, level = asyncio.run(plugin.cmd_my_cmd(stream_id="s1"))
    assert success is True and level == 1
