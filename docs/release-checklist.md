# Release maintenance checklist

Silicon Canvas ships a local STDIO MCP server and a static Web demonstration. Maintainers currently verify and publish both manually. Source pushes and version tags do not run automatic release workflows.

## Prepare a version

- Keep `pyproject.toml`, `src/silicon_canvas/__init__.py` and `web/package.json` on the same version. Prefix the release tag with `v`, for example `v0.7.0`.
- Update the changelog, installation instructions, selected examples and workspace screenshot.
- Verify the relevant behavior, the installed MCP process and the actual built Web. Keep the source commit and validation evidence associated with the release.
- Inspect the wheel, source archive, Web ZIP and portable bundle. Exclude credentials, local configuration, internal designs, temporary experiments and raw third-party reference images.
- Preserve MIT, the font's OFL and source notice, and portable dependency licenses. See [third-party.md](third-party.md).
- Distinguish native previews, original ImageGen generations and edited derivatives. Software checks do not certify ImageGen output quality.

## Publish GitHub Release manually

Build from the intended source commit using the commands in [CONTRIBUTING.md](../CONTRIBUTING.md). Create the matching tag and GitHub Release, use the corresponding changelog section as the release description, and attach these four artifacts plus `SHA256SUMS`:

- A Python wheel, `*.whl`.
- A source distribution, `*.tar.gz`.
- The static site, `silicon-canvas-web.zip`.
- The complete Windows portable MCP, `silicon-canvas-mcp-windows-x64.zip`.

Calculate SHA-256 over the exact files being uploaded. After publication, download them and compare with `SHA256SUMS`:

```sh
sha256sum -c SHA256SUMS
```

On Windows, use `Get-FileHash -Algorithm SHA256 <file>` and compare with the corresponding entry. Hashes establish byte integrity, not a security certification. Confirm the tag resolves to the intended commit and that the attached files follow the installation instructions. GitHub Release publication does not publish a package to PyPI or npm.

## Publish Pages manually

After verifying `dist/web/`, publish its contents to the root of the `gh-pages` branch, including `.nojekyll`. Configure repository Pages to **Deploy from a branch**, with `gh-pages` and `/ (root)` as the source.

The default project-site path is `/silicon-canvas/`. Check the deployed URL, relative assets, Worker startup and mobile layout. A local build or source push alone does not prove the site has been published. Updating the source branch does not automatically rebuild the published branch.

## Optional automation templates

[CI](automation/ci.yml), [Pages](automation/pages.yml) and [Release](automation/release.yml) templates are retained under `docs/automation/`. GitHub does not execute them from this location.

Enabling automation is a separate maintainer decision: review and copy the templates into `.github/workflows/`, configure the intended Pages source and deployment permissions, and verify their behavior. The Release template calls `.github/workflows/ci.yml`, so enable the templates together. They use standard workflow credentials and pinned Actions; their presence in this repository does not mean automation is active. Current manual publication does not require adding workflow permission to existing credentials.

## Failure and recovery

Fix and reverify a failed build before publication. If release bytes need to change after publication, publish a new version instead of moving an existing tag or silently replacing assets.

For an incorrect Pages deployment, publish a previously verified static build to `gh-pages`, then verify the public URL again. Keep the source commit associated with each deployed build.
