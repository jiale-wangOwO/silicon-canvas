# MCP 使用指南

Codex 的推荐入口是 **Silicon Canvas 插件**，它一起安装绘图 Skill 和本机 MCP 服务。其他支持 MCP 的 Agent 可以独立接入同一服务。默认使用宿主模型理解设计，由共享核心编译方案，再交给宿主可用的 ImageGen 生成与审查。

## Codex 插件

需要 Python 3.11+，且命令名 `python` 可用：

```sh
codex plugin marketplace add jiale-wangOwO/silicon-canvas
codex plugin add silicon-canvas@silicon-canvas
```

插件在 **Silicon Canvas** 插件来源下显示，标识为 `silicon-canvas@silicon-canvas`。它包含 Logo、绘图工作流 Skill 和 MCP 工具；安装插件后不必另填全局 MCP command。

首次启动会将已固定版本的后端安装到独立缓存，安装过程需要网络。准备环境的输出写入诊断流，MCP 的标准输出仅传协议消息。后续启动复用缓存，普通准备与编译不会请求外部语义模型。

如果以前已经手动配置 `[mcp_servers.silicon-canvas]`，确认插件安装成功后可禁用那一项，避免在工具列表出现两个来源。已有绘图产物不需要删除。

开发本地插件时，在仓库根目录运行：

```sh
codex plugin marketplace add .
codex plugin add silicon-canvas@silicon-canvas
```

插件目录是 `plugins/silicon-canvas/`，仓库的 `.agents/plugins/marketplace.json` 提供可发现的目录。版本与后端源提交记录在插件 manifest 和 `backend.json` 中。发布前用实际插件启动器完成一次 STDIO 准备、编译及结果读取；不能用独立源码服务的成功代替插件启动验证。

下面的独立 MCP 安装方式供其他客户端使用。插件打包方式依据 [OpenAI 插件文档](https://developers.openai.com/plugins/build/plugins)。

## 安装与客户端配置

源码或 wheel 安装需要 **Python 3.11+**。在源码根目录运行：

```powershell
# Windows PowerShell
.\scripts\install-mcp.ps1 -PackagePath .
```

```sh
# macOS / Linux
bash scripts/install-mcp.sh .
```

也可把源码目录参数替换为本地 wheel 路径。Windows 安装时，`install-mcp.ps1` 与 `install_mcp_support.py` 必须保存在同一目录。

安装器创建独立虚拟环境并检查启动，不改写宿主配置：

| 系统 | 默认安装目录 |
| --- | --- |
| Windows | `%LOCALAPPDATA%/SiliconCanvas/mcp` |
| macOS / Linux | `${XDG_DATA_HOME:-~/.local/share}/silicon-canvas/mcp` |

安装完成后，使用输出的 `mcp-config.json` 配置通用 MCP 客户端，或将 `codex-mcp.toml` 片段合并到 Codex 配置。宿主应以安装器给出的绝对路径启动 `silicon-canvas-mcp`，参数为空；建议启动超时 30 秒、工具调用超时 180 秒。客户端配置方式以其文档为准，例如 [Codex MCP 文档](https://developers.openai.com/codex/mcp/)。

Windows 可用 `-InstallDir`、`-Python` 覆盖安装位置与解释器；macOS/Linux 可设置 `SILICON_CANVAS_INSTALL_DIR`、`PYTHON`。服务是由客户端启动的协议进程，无需额外绘图命令行。

### Windows 便携包

项目可构建 `silicon-canvas-mcp-windows-x64.zip`。使用此分发包时无需另外安装 Python：解压整个目录，把 `MCP-CONFIG.json` 中的 command 替换为 `silicon-canvas-mcp.exe` 的绝对路径，再添加到宿主。EXE 依赖相邻的 `_internal`，移动时保留完整文件夹。构建方式见 [贡献指南](../CONTRIBUTING.md)。

## Agent 调用流程

默认流程不需要额外语义 API Key，但宿主仍需具备可用的模型与图片工具：

1. 调用 `silicon_prepare(description, settings)`，读取返回的语义要求和 `preparation_id`。
2. 宿主模型整理完整 `spec`，保留用户事实、原文证据、假设与视觉意图。
3. 调用 `silicon_compile(spec, preparation_id)`，取得提示词、参考角色、视图和 `artifact_id`。准备阶段的设置具有权威性，不在同一次编译中另传冲突的描述或设置。
4. 按当前图的 `guide_role`、`guide_optional` 和 `next_step` 使用 ImageGen；实际查看结果。
5. 有修改意见时重新准备、编译与生成；使用 `silicon_export` 保存绘图包，使用 `silicon_prepare_review` 获取源事实支持的审查要点。

`silicon_prepare_review` 返回的是待审查材料，初始状态为 `not_reviewed`。它不读取最终图片，也不会自动批准图片。

### 正确使用参考图

| 当前视图 | ImageGen 输入 |
| --- | --- |
| 工程图，`guide_role: target_structure` | 使用工具原样提示词及对应结构底稿，约束模块归属、标签、端点与方向。若必需底稿不可用，应先调整范围并重新编译，不能宣称已有受控工程结果。 |
| 算法依赖图，存在 `algorithm_flow_plan` | 按工具提示词与张量／算子计划生成；不需要硬件结构底稿。这与必需底稿生成失败是不同情况。 |
| 产品渲染或空间插画，`guide_role: composition_reference` | 提示词本身足够使用；取景参考仅按需附上，不提供实测几何、物理数量或布线依据。 |

每张图的 `figure_strategy` 记录阅读问题、表现形式、可见范围和规划限制。先检查它是否回答当前问题，再生成图片。布局预检和策略记录不能替代对实际位图的审查。

默认一次生成完整图文。工具返回 `generation_steps` 时，按其中的完整生成步骤执行；只有明确要求分步或保留已批准图片时才使用编辑步骤，编辑目标必须是真实成图。最终生图由宿主或用户选择的平台提供，MCP 不附带图片模型。

## 描述需求与选择形式

描述内容、用途和画面重点即可，不要求用户先分类。例如：

> 用 Silicon Canvas 画一个缓存一致性请求的状态机，保留给定事件和优先级。用英文标签，便于架构评审；生成后检查所有转移。

> 做一张完整 AI 加速板卡的产品展示图：两颗计算封装和四颗显存封装，浅色背景、无文字，不编造电气连线或性能参数。

新建请求默认 `scene: auto` 和 `representation: auto`。需要显式控制时可传：

```json
{
  "description": "GPU 架构总览，突出计算簇、共享缓存与片外显存之间的关系。",
  "settings": {
    "representation": "diagram",
    "scene": "system",
    "language": "en"
  }
}
```

`representation` 区分工程图 `diagram`、空间系统示意 `system_illustration` 和产品渲染 `product_render`；`scene` 决定概念、系统、过程或细节范围。配色、详略、画幅可独立选择。镜头、材质、背景、留白等要求可以直接写在描述或 `settings.notes` 中。详见 [表达方式与用途](scenes.md)。

新图省略语言或使用 `language: auto` 时都使用英文，中文描述和原文证据保持中文。显式保存的历史语言设置仍用于原规格的重编译与修改。直接编译旧规格且未指定 `representation` 时保留原工程图行为；新任务优先使用准备流程。

修改已有 artifact 时，在 `silicon_prepare` 中传入 `previous_artifact_id`、`feedback` 和 `lock_structure`；默认保留现有结构。技术变化应更新源规格，而非只在图片上掩盖错误。

## 可选：独立语义服务

`silicon_generate` 可调用本机配置的 DeepSeek 或兼容服务整理规格，再编译。它会向外部服务发送设计内容并可能产生费用；返回的仍是绘图方案，不是最终图片。

| 环境变量 | 默认值 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 未配置 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | `deepseek-flash` |
| `DEEPSEEK_MAX_TOKENS` | `12000` |

通过宿主进程环境提供配置，不把 Key 放入描述、规格或工具参数。变量示例见 [`.env.example`](../.env.example)；默认宿主流程不需要这些变量。模型名应使用所选服务实际提供的名称。

## 产物与故障排查

服务返回 artifact 和资源句柄；使用它们读取提示词、图注、参考、完整源规格和审查材料，不要自行拼接内部文件路径。`silicon_export` 可导出单图或全部视图的 ZIP。

默认产物目录为 Windows 的 `%LOCALAPPDATA%/SiliconCanvas/artifacts`，或 macOS/Linux 的 `${XDG_CACHE_HOME:-~/.cache}/silicon-canvas/artifacts`。可通过 `SILICON_CANVAS_OUTPUT_DIR` 更改。记录在重启后保留，不自动清理。

客户端看不到工具时，检查启动路径、Python 版本、安装目录完整性，并重新加载 MCP 配置。协议进程的 STDOUT 仅用于 MCP 消息，诊断应写入 STDERR。可选提供商的鉴权或余额错误不影响本地准备与编译流程。

[数据与隐私](privacy.md)说明哪些请求会发送给外部服务。报告问题时请去除 Key、认证头和内部设计，漏洞报告方式见 [安全说明](../SECURITY.md)。
