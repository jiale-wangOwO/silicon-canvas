# Third-party materials

| 材料 | 分发范围 | 许可或来源 |
| --- | --- | --- |
| Silicon Canvas 原创代码、规则和文档 | 源码、Python 包、Web 发布物 | 仓库根目录 [MIT](../LICENSE) |
| 随包字体 | Python 包与 Web 发布物 | 字体目录内的 SIL Open Font License 与上游来源记录 |
| Pyodide 与其 Python/Pillow 运行时 | Web 运行时加载或发行构建 | 各上游包许可；参见 [Pyodide](https://pyodide.org/) |
| MCP Python SDK | 本机 Python 依赖或独立程序构建 | [官方 SDK](https://github.com/modelcontextprotocol/python-sdk) 的 MIT 许可 |
| 论文与厂商参考出处 | 参考元数据 | 上游页面和论文；链接不授予原图再分发权 |

原来收集的论文 PDF、截图和商业芯片图保存在本机审核归档中，排除在当前分支、Python 包与 Web 发布物之外。项目源码许可不会将这些原图重新授权为 MIT。

当前开发工作区仍保留根目录 `reference_images/`，方便继续按 architecture、dataflow、logic、timing 和 00_inbox 整理参考。这是被 Git 忽略的个人资料库；放入图片不会自动上传，也不会未经审查地把图片内容转成目标设计。共享核心只分发构图特征元数据和来源链接。

添加新参考时，优先记录公开出处和提炼后的构图特征。若要随项目分发原图，必须先确认明确的再分发许可，并保留要求的署名、来源与许可证。对来源不明的图片不能自行声称获得授权。

字体使用 [Noto Sans CJK SC](https://github.com/notofonts/noto-cjk)。许可、来源与文件校验信息位于 `src/silicon_canvas/fonts/LICENSE` 和 `NOTICE.json`，随 Python 包与 Web 编译资源保存。未分发 Microsoft 等系统字体。
