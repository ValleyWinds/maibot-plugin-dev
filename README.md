# maibot-plugin-dev — MaiBot 插件开发技能（ZCode Skill）

这是一个用于 ZCode 客户端的 Agent 技能（Skill），帮助你（或你的 AI 助手）开发、调试、重构 **MaiBot（麦麦）** 的 Plugin SDK 插件。技能内容基于对 MaiBot 主程序与 maibot-plugin-sdk 源码的逐行核对与运行时实测整理而成，涵盖：

- **SDK 能力代理签名**（18 种 `ctx.*` 代理，逐方法核对）
- **组件装饰器规范**（Tool / Command / HookHandler / API / ReplyExtension / HomeCard / MessageGateway / LLMProvider 等）
- **Hook 系统清单**（22 个内置 Hook 的真实 kwargs 结构与返回值协议）
- **配置模型与 WebUI**（`PluginConfigBase` 规范、`webui.json` 声明式页面协议 v2）
- **常见陷阱**（均来自真实开发中的踩坑记录，按致命程度分级）
- **插件模板**（`assets/plugin-template/`，可直接复制起步）

## 目录结构

```
maibot-plugin-dev/
├── SKILL.md                      # 技能入口：核心规范 + 陷阱速查索引
├── references/                   # 详细参考（纯 Markdown，可整体喂给任意 LLM 会话）
│   ├── sdk-api-reference.md      #   18 种能力代理完整签名
│   ├── hooks-and-components.md   #   22 个 Hook 的真实 kwargs + 全部组件装饰器
│   ├── common-pitfalls.md        #   常见陷阱详解与修复方案
│   ├── plugin-config.md          #   配置系统全解
│   ├── webui-pages.md            #   webui.json 声明式页面协议 v2
│   ├── reply-extensions.md       #   @ReplyExtension 两阶段协议
│   ├── isolated-import-testing.md#   脱离宿主做纯函数验证的 stub 套路
│   └── plugin-repo-submission.md #   插件仓库提交与收录规则
└── assets/plugin-template/       # 插件模板（_manifest.json / plugin.py / config.py / config.toml）
```

安装方式：把本目录整体放进 `~/.zcode/skills/` 即可被 ZCode 自动发现。没有 ZCode 也没关系——`references/` 下全部是纯 Markdown，可以作为上下文直接提供给任何 AI 编程助手使用。

## ⚠️ 时效性声明

本技能的校对基线是 **SDK 2.14.0 + MaiBot Host 1.3.9**。MaiBot 与 SDK 在独立且快速地迭代，**技能内容可能已经过时**——包括版本行为差异、能力注册表、Hook 清单等，都会随上游发版变化。

请把这份技能当作**加速上手的地图**，而不是最终答案。遇到行为疑问，一律以下列顺序为准：

1. **运行中的实际行为**（本地实例 + WebUI 端点 + 日志）
2. **SDK / 主程序源码**（技能引用的路径为 `maibot-plugin-sdk/maibot_sdk/` 与 `MaiBot/src/plugin_runtime/`）
3. 官方文档 https://docs.mai-mai.org （文档存在滞后与自相矛盾处，技能内已标注已知偏差）
4. 本技能

## 致谢与配套仓库

本技能的全部内容都构建在以下三个开源仓库之上，谨向 **Mai-with-u** 社区与各位贡献者致谢 🙏：

| 仓库 | 内容 |
|------|------|
| [Mai-with-u/MaiBot](https://github.com/Mai-with-u/MaiBot) | 麦麦主程序（Host），插件运行时源码在 `src/plugin_runtime/` |
| [Mai-with-u/maibot-plugin-sdk](https://github.com/Mai-with-u/maibot-plugin-sdk) | 插件 SDK（`maibot_sdk`），能力代理与装饰器的权威定义 |
| [Mai-with-u/docs](https://github.com/Mai-with-u/docs) | 官方文档站源码（docs.mai-mai.org） |

强烈建议把这三个仓库拉到本地常备——技能中所有断言都标注了源码出处，随时可以按图索骥地复核；上游更新后 `git pull` 一遍再对照技能，就是最高效的“技能保鲜”方式。

目录组织可以像我一样用一个容器目录聚合三个独立仓库（技能里引用的相对路径也是按这个结构写的）：

```
MaiBot-Project/
├── MaiBot/                 # git clone https://github.com/Mai-with-u/MaiBot.git
├── maibot-plugin-sdk/      # git clone https://github.com/Mai-with-u/maibot-plugin-sdk.git
└── docs/                   # git clone https://github.com/Mai-with-u/docs.git
```

```bash
mkdir MaiBot-Project && cd MaiBot-Project
git clone https://github.com/Mai-with-u/MaiBot.git
git clone https://github.com/Mai-with-u/maibot-plugin-sdk.git
git clone https://github.com/Mai-with-u/docs.git
```

## 许可

本技能采用 **[CC BY-SA 4.0](LICENSE)**（署名 - 相同方式共享 4.0 国际）：你可以自由复制、再分发、改编本仓库内容用于任何用途（含商用），但必须署名，且**基于本内容改编的作品必须以相同协议共享**——fork 改完再发布的，也保持开源。

仓库内容中的 API 事实与行为描述版权归各上游仓库——**MaiBot 采用 GPL-3.0、maibot-plugin-sdk 采用 LGPL-3.0、docs 采用 GPL-3.0**，谨此致谢。
