# Validation

Silicon Canvas separates software correctness from generated-image quality. A passing compiler or protocol check does not certify an Image Gen output.

## Repeatable checks

| Layer | Command | What it establishes |
| --- | --- | --- |
| Python core and MCP SDK | `python -m unittest discover -s tests -t . -v` | Source facts, ownership, dependencies, planning, export, resources and real STDIO behavior |
| Web modules | `npm --prefix web test` | Provider requests, error handling and carousel behavior |
| Browser and native core | `python scripts/build_web.py` then `python scripts/verify_browser.py` | Actual Chromium/Pyodide compilation compared with native JSON and guide pixels |
| Workbench | `python scripts/verify_workbench.py` | Current input, customization, model dialog, feedback and download interactions |
| Installed or portable MCP | `python scripts/verify_mcp_executable.py PATH_TO_MCP` | Real STDIO discovery, preparation, compilation, resources and export from another working directory |
| Python distributions | `python -m build` | Installable wheel and source distribution; inspect contents before release |

Use Python 3.11 or later. Browser checks need Playwright Chromium. The default checks use synthetic fixtures or local mock providers and do not need a real API key or invoke paid image generation. CI repeats the core checks on Linux and Windows; a local pass does not establish a remote CI result.

## Test sources

Regression fixtures represent generic, synthetic designs and public algorithm concepts. They preserve topology, quantities, conditions and source ownership as test facts rather than measurements of a commercial chip. The [design benchmark](design-benchmark.md) covers distinct reader tasks and independent technical checks. Once a case has informed a change, it is a regression case, not an unseen holdout.

Changes to fixtures must preserve the intended independent invariant. Do not rewrite a source merely to fit a planner, hide a reverse relation, or remove a difficult ownership boundary.

## Actual images

The [homepage showcase](../web/index.html#showcaseTitle) contains selected generated images, branded edits and explicitly identified native structure previews. Associated prompts, source records and available generation/review metadata remain beside the assets. Historical metadata describes the version used for that image; it is not a claim that the current compiler produced identical pixels.

For each new Image Gen trial, review technical correctness, reading order and readability at its intended document size. Keep the exact tool-returned prompt, source, supplied reference roles and original output. Identify subsequent edits separately. Generated labels, routing, formulas and fine physical details can still require another image-editing pass.

Reference planning, layout preflight and actual image review have separate states. A new result begins as `not_reviewed`. Neither software tests nor a visually pleasing example prove that arbitrary inputs or image models meet publication requirements.
