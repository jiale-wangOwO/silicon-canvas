# Web 演示指南

Web 演示将与 MCP 相同的 Python 编译核心放在浏览器 Worker 内运行。输入描述，使用自己的 DeepSeek 或兼容服务生成提示词，再下载绘图包交给图片工具。完整的 Agent 协作、生图与审查体验见 [MCP 指南](mcp.md)。

## 使用

1. 打开“连接模型”，按地址、模型、API Key 配置服务。默认地址为 `https://api.deepseek.com`，模型为 `deepseek-flash`，Key 初始为空。
2. 描述要画的内容、用途和视觉要求，点击“生成提示词”。可以用中文输入，新图的文字使用英文；“试个例子”可填入示例后修改。
3. 形式、用途、配色、详略与画幅默认自动安排。需要覆盖时展开“自定义”；其中的小图仅说明选项效果，不是当前输入的实际成图。
4. 复制结果提示词或下载绘图包。若页面要求配套参考图，应与提示词一起交给 ImageGen；若必需参考不可用，页面会提示方案未完整就绪。
5. 使用“再调整一下”修改当前结果，再查看实际生成图片，核对事实与视觉效果。

网页本身不调用 ImageGen。产品渲染与算法图通常可用提示词直接生成；工程图的配套结构底稿负责约束归属、端点、方向和标签，不能当作最终成品。

自动视觉选项在同一次语义回复中选择，解析结果随当前方案与导出包保存。反馈调整沿用当前结果的设置；修改自定义选项后，主输入区的“生成提示词”会建立新方案。需要改变技术结构时，可以取消反馈区的“保留当前模块与连接”。

## 绘图包与审查

导出包保留完整源规格、各视图提示词、参考、图注、假设和待审查材料，也记录核心返回的 `figure_strategy`。它们便于修改和追溯，但不代表实际图片已通过审查。概念功能区和产品外观不是实测裸片布局、尺寸或制造资料。

首页作品包含实际 ImageGen 图片及原生结构预览；它们展示不同的视觉组织方式，不保证任意新输入产生同等结果。表达形式与用途见 [scenes.md](scenes.md)，完整体验见 [MCP 工作流](mcp.md#agent-调用流程)。

## API 与隐私

浏览器直接请求所选提供商，无本项目的 Key 转发代理。设计内容会发送给该服务；请使用有权发送的材料。

- API Key 仅保存在当前页面内存中，刷新后需重新填写，不写入持久存储、项目或导出包。
- 兼容接口需支持 Chat Completions、所配置的模型、JSON 回复及足够的输出长度。
- 服务必须允许浏览器 CORS 预检，以及 `Authorization` 和 `Content-Type` 请求头。`Failed to fetch` 或 CORS 错误通常不能靠更换 Key 修复。
- 模型名称和服务能力以提供商的 [官方文档](https://api-docs.deepseek.com/) 为准，兼容性不代表所有服务都已验证。

详细数据路径见 [privacy.md](privacy.md)。

## 本地预览

需要 Python 3.11+：

```sh
python -m pip install -e ".[dev]"
python scripts/build_web.py
python -m http.server 8080 --directory dist
```

打开 `http://127.0.0.1:8080/web/`。不要通过 `file://` 打开 Worker 页面。这个静态 HTTP 服务仅供开发预览，不是产品的 Python 后端。

构建产物位于 `dist/web/`。共享核心和 Noto 字体打包在站点自己的 `assets/compiler.zip` 中；Pyodide 与 Pillow 运行时按 `web/runtime-lock.json` 从固定地址加载。首次加载需要网络，浏览器缓存可减少后续下载；当前不提供完整离线站点。运行时资源请求不携带 API Key。

## 静态部署

可以将 `dist/web/` 的内容托管到 GitHub Pages 或其他静态服务。资源使用相对路径，支持 Pages 项目站点的仓库子路径。

当前采用手动发布：维护者构建并验证后，将 `dist/web/` 的内容提交到 `gh-pages` 分支根目录，保留 `.nojekyll`。仓库 Pages 设置选择 **Deploy from a branch**，分支为 `gh-pages`、目录为 `/ (root)`。项目站点使用 `/silicon-canvas/` 子路径；源码 push 不会自动构建站点。

[Pages 自动化模板](automation/pages.yml)保存在文档目录，不会执行。若以后需要自动构建与部署，维护者可另行启用模板并配置相应权限。当前不要求为此增加凭据权限。维护流程见 [发布清单](release-checklist.md)。
