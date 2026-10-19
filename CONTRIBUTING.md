# Contributing

感谢帮助 Silicon Canvas 改进。贡献可以是可复现的问题、通用构图规则、MCP/Web 体验或可公开的示例；目标是让不同输入都更好，而非针对一张展示图硬编码。

## 开发环境

需要 Python 3.11+。Web 单元测试使用 Node.js 的内置测试运行器；浏览器验证使用 Playwright Chromium。

```sh
python -m venv .venv
```

激活环境：

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```sh
# macOS / Linux
source .venv/bin/activate
```

安装开发依赖：

```sh
python -m pip install -e ".[dev]"
```

## 代码结构

| 路径 | 职责 |
| --- | --- |
| `src/silicon_canvas/` | 共享语义合同、事实整理、图形规划、布局、渲染方案和导出 |
| `src/silicon_canvas/mcp_server.py` | 本地 STDIO MCP 工具与资源 |
| `web/` | 静态工作台、模型请求适配与 Pyodide Worker |
| `tests/`、`web/tests/` | 核心、协议、Web 行为与回归夹具 |
| `scripts/` | 安装、构建和开发验证 |
| `examples/` | 可公开的源规格示例 |
| `docs/` | 使用、设计、隐私和资源许可说明 |

Web 与 MCP 共用同一编译核心。不要为网页复制一套布局规则，也不要为固定示例添加模块名特判、删除数量或隐藏反向关系。设计背景见 [项目架构](docs/architecture.md)和 [系统设计](docs/system-design.md)。

## 验证

运行与改动相关的检查，说明实际覆盖范围。通常使用：

```sh
python -m unittest discover -s tests -t . -v
npm --prefix web test
```

涉及 Web Worker、页面或浏览器与本地编译一致性时：

```sh
python scripts/build_web.py
python -m playwright install chromium
python scripts/verify_browser.py
```

这些默认检查使用本地夹具或 Mock，不需要真实语义 API Key，也不会生成实际 ImageGen 图片。外部模型验证必须单独说明提供商、调用与费用边界，不能把编译回归分数当作自然输入或实际成图的成功率。

修改图形策略时，补充不同结构和输入表达的案例，检查事实、归属、数量、条件、关系和参考角色。针对已公开回归集调试后，不能继续把它称为独立盲测。实际图片应独立审查技术正确性、阅读顺序与文档尺寸下的效果。

## 构建与预览

Python wheel 与源码分发包：

```sh
python -m build
```

静态 Web：

```sh
python scripts/build_web.py
python -m http.server 8080 --directory dist
```

打开 `http://127.0.0.1:8080/web/`。输出分别位于 `dist/*.whl`、`dist/*.tar.gz` 和 `dist/web/`。

Windows x64 便携 MCP：

```sh
python scripts/build_mcp.py
python scripts/verify_mcp_executable.py dist/portable/silicon-canvas-mcp/silicon-canvas-mcp.exe
```

在 Windows x64 构建得到 `dist/silicon-canvas-mcp-windows-x64.zip`。发布时保留 EXE、`_internal` 与第三方许可文件，不只分发 EXE。源码安装器和 wheel 安装说明见 [MCP 指南](docs/mcp.md)。

## 提交贡献

PR 说明应包含实际问题、最终行为、验证方法和未解决限制。版面改动附前后结构参考；涉及生图效果时附实际 ImageGen 输出及对应输入，不以程序底稿替代成品。

示例只使用可公开、可再分发的材料，保留来源与生成/编辑关系。新增字体和外部素材时核实许可。厂商原图与论文截图不能因为可公开下载就放进发行物；可以记录官方链接与自己的分析。

测试使用 Mock，不提交 API Key、认证头、内部设计或未脱敏响应。安全问题按 [SECURITY.md](SECURITY.md)处理，普通问题可通过仓库 Issue 提交。

## 发布检查

公开前的源码、资源与历史检查见 [发布清单](docs/release-checklist.md)。

当前由维护者验证构建物后手动发布 GitHub Release，并把静态站点部署到 `gh-pages` 分支；源码 push 和版本标签不会自动发布。`docs/automation/` 保留 [CI](docs/automation/ci.yml)、[Pages](docs/automation/pages.yml)和 [Release](docs/automation/release.yml)可选模板，只有另外启用到 `.github/workflows/` 并配置相应权限后才会运行。当前不发布到 PyPI。维护者应在发布前：

- 核对源码、版本、构建产物与验证范围对应，并在目标平台验证 MCP 启动。
- 检查资源许可、依赖、凭据与公开内容；区分实际首图、编辑衍生图和原生结构预览。
- 确认 Release 附件与安装说明一致，标签与三处版本字段匹配；核对 Pages 的 `gh-pages` 分支根目录及访问设置。
- 如果需要发布到其他包索引，另行完成该渠道的发布验证，不从本地构建推定已经上线。

已有图片的审查只适用于当时的源规格和图片。改变真实生图输入或上游结构合同后，应重新查看实际位图。许可见 [LICENSE](LICENSE)、[第三方资源](docs/third-party.md)，数据处理见 [隐私说明](docs/privacy.md)。

完整发布流程、附件清单和恢复原则见 [发布维护清单](docs/release-checklist.md)。
