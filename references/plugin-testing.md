# 插件测试流程

写完插件到敢发布，分三层：**离线导入测试 → 本地实例实测 → 收录前自检**。
前两层都不需要把代码 push 到任何地方；测试中产生的 `config.toml`、日志、数据目录都不该进 git（模板自带 `.gitignore` 已覆盖）。

## 第 0 层：测试前的环境准备

- 本地跑一个 MaiBot 实例：clone 官方仓库后按仓库说明装依赖（`uv sync`）并启动；WebUI 默认端口 8001，地址以启动日志为准，首次启动会生成 `data/webui.json` 存登录 token——**这个文件和启动日志里的明文 token 都不要提交、不要外传**。
- 你的插件是独立 git 仓库，开发时把插件目录放进 MaiBot 实例根的 `plugins/` 文件夹（**不是 `data/plugins/`**，那里是插件运行时数据目录；放错位置不会被加载）。
- 插件配置文件 `config.toml` 由插件系统在**首次运行时按 `config.py` 的默认值自动生成**，不需要也不应该手工上传；实机上改过的配置可能含 token/密码，模板自带的 `.gitignore` 已忽略它。

## 第 1 层：离线导入测试（不启动宿主）

对 `plugin.py` 做脱离宿主的纯函数验证：stub 掉 SDK 依赖后导入，断言生命周期方法签名、组件元数据、默认配置可生成、manifest 合法。
完整的 stub harness 套路与命令见 [isolated-import-testing.md](isolated-import-testing.md)（`references/isolated-import-testing.md`）。

这一层的价值：几秒钟抓住「签名写错、配置模型缺默认值、manifest 字段非法」这类最低级但最常见的错，不用等宿主启动。

### 用 SDK 现成注入点测业务逻辑（比 stub 更进一步）

stub harness 把 SDK 整个替掉，适合验导入契约；测**业务逻辑**时可以用**真实 SDK、只假最外层通道**——`MaiBotPlugin` 上有两个现成注入点（SDK `plugin.py`，官方文档未记载，主要贡献者插件实战在用）：

- `plugin.set_plugin_config(dict)` —— 注入配置、拿到强类型 `self.config`。**注入的 dict 必须带 `[plugin].config_version` 节**，且配置模型要声明 `plugin` 节（缺任一，默认配置生成阶段就抛 `PluginConfigVersionError`，与 `common-pitfalls.md` 陷阱 12 同源）；只带必需节时业务字段走模型默认值。
- `plugin._set_context(PluginContext(plugin_id, rpc_call=fake))` —— 注入假 RPC 通道：SDK 的参数组包、返回归一化都是真的，只有到 Host 的最后一跳是假的，能断言到 wire 级参数。

```python
# tests/conftest.py —— 隔离加载 plugin.py（多文件插件另见 isolated-import-testing.md）
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import pytest

@pytest.fixture(scope="session")
def plugin_module():
    spec = spec_from_file_location("my_plugin", Path(__file__).parents[1] / "plugin.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

```python
# tests/test_logic.py —— 两个注入点合用（SDK 2.16.0 实测通过）
import asyncio
from maibot_sdk.context import PluginContext

def test_config_injection(plugin_module):
    plugin = plugin_module.create_plugin()
    plugin.set_plugin_config({"plugin": {"config_version": "1.0.0"}, "api_key": "test-secret"})
    assert plugin.config.api_key == "test-secret"

def test_fake_rpc(plugin_module):
    plugin = plugin_module.create_plugin()

    async def fake_rpc(method, plugin_id, payload):
        assert payload["capability"] == "send.text"
        assert payload["args"]["text"] == "hi"     # wire 级断言（args 还会自动带 return_details: False）
        return {"success": True}

    plugin._set_context(PluginContext("demo.plugin", rpc_call=fake_rpc))
    ok = asyncio.run(plugin.notify(stream_id="s1", text="hi"))
    assert ok is True                              # send.text 按 success 归一化返回 bool
```

### tests/ 的工程化惯例（官方文档只有目录树一行，无内容说明）

官方 vibe-coding 页给插件留了 `tests/` 目录——Host 不加载它，纯给开发者。实战惯例：

- `tests/conftest.py` 放隔离加载 fixture（见上例）；`pyproject.toml` 配 `[tool.pytest.ini_options]`：`testpaths = ["tests"]`、`pythonpath = ["."]`；
- 依赖双轨：`requirements.txt` 供本地开发/测试（**把 `maibot-plugin-sdk` 也列进去，pytest 才能 import 它**），运行环境安装走 manifest `dependencies`（Host 依赖管道装）；
- 规模参照：小插件两个文件（conftest + 契约/逻辑测试）即可；中型插件按模块一个 test 文件；重工程（AI 推理类）再加 worker 生命周期、依赖下载、断点续传等专项。发布时 tests 随仓库分发，是插件质量的加分项。

## 第 2 层：本地实例实测

离线过了不等于能跑——Host 侧校验、能力声明、Hook 触发只有真加载才知道。按顺序核对：

1. **放进插件目录，等热加载**：把插件目录放进实例 `plugins/` 后，文件监听会自动发现并加载，通常几秒内完成，无需重启实例。
2. **插件列表出现**：WebUI 插件管理页能看到你的插件，`_manifest.json` 里的名称、版本、描述正确显示。
3. **组件注册成功**：声明了的 Tool / Command / EventHandler / HookHandler 在 WebUI 对应清单（指令、Hook）里能看到；启动日志里没有插件加载报错。
   ⚠️ **禁用状态的插件不走注册校验**——「没报错」不等于「声明合法」；要验证 manifest/组件声明，必须让插件处于启用状态，或离线调 `manifest_validator` 单独校验。
4. **配置表单能用**：WebUI 插件配置页能渲染你的配置模型、改一个字段并保存，`config.toml` 里出现新值、插件日志触发 `on_config_update`。
5. **真实触发一次**：发一条消息触发你的 Command / Tool / EventHandler，确认行为与返回值符合预期（Command 的返回值三元组、`ctx.send` 的 bool 归一化等语义见各参考文件，别凭直觉猜）。
6. **停用/卸载测试**：禁用或卸载插件后，确认它留下的后台任务、连接和缓存被正确清理（官方「测试建议」的最后一项，也是最容易被漏的一项）。

常用排查手段：

- **改了不生效**：先确认文件真的在 `plugins/` 下、目录名与 `_manifest.json` 的 `id` 对得上；热加载失败看启动日志的插件加载段。
- **临时停用插件**：改插件 `config.toml` 的 `[plugin].enabled = false`（改前把原文件备份到 `config_back/` 之类的目录，改完要还原）。**不要用移走插件目录的方式停用**——那等于变相卸载，会丢注册状态。
- **日志**：实例 `logs/` 下的 jsonl 日志按时间滚动，插件相关报错优先搜插件 `id`。
- **测试期的凭据**：插件测试需要的 LLM API key 等配置在**实例自身的配置文件**里填，不要为了图省事写进插件目录、更不要写进示例代码——测试产物同样要过一遍 `references/plugin-repo-submission.md` §9 的泄漏自查再上传。

## 第 3 层：收录前自检

准备上架到插件中心前，过一遍 [plugin-repo-submission.md](plugin-repo-submission.md)（`references/plugin-repo-submission.md`）的
「收录前自检清单」与「**公开发布前安全检查**」——特别是 `.env`、密钥、本机绝对路径和运行数据的泄漏自查，这一步漏了，泄漏出去的凭据删库也救不回来。
