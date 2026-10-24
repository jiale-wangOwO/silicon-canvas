# Changelog

## Unreleased

- Codex plugin with a discoverable marketplace entry, Silicon Canvas branding, the drawing workflow Skill, and its bundled MCP launcher.
- Isolated, pinned backend setup on first use; existing clients can continue using the standalone MCP installation.
- Plugin installation instructions in the README and Agent setup page.

## 0.7.0 — 2026-10-19

First public release of Silicon Canvas.

### Create figures with your agent

- Local STDIO MCP workflow: prepare a request, let the host model organize the source specification, and compile an Image Gen brief.
- Engineering diagrams, algorithm dataflow, state/control and timing views, spatial system illustrations, and commercial product renders.
- Shared Python core for the MCP server and the browser demonstration.
- Source-backed prompts, reference roles, captions, export bundles and image review tasks.
- English artwork by default, with natural-language descriptions in Chinese or English.

### Web demonstration

- A focused workspace with automatic visual choices and optional customization previews.
- Browser-direct DeepSeek or compatible model connection; API keys stay in page memory.
- Sixteen selected works in a continuous carousel, and a matching Agent setup guide.
- GitHub Pages deployment at <https://jiale-wangOwO.github.io/silicon-canvas/>.

### Distribution

- Python wheel and source distribution, Windows portable MCP, and a self-contained static Web archive.
- MIT code license, bundled font notices, portable dependency licenses and release checksums.
- Public source history starts with reviewed synthetic fixtures; private development archives are not part of this release.

Image generation requires an image tool provided by the host or a separate platform. Generated labels, connections and details should be reviewed before use in technical documents.
