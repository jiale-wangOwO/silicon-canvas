"""Real simplified Web UI + Worker checks; only model transport is mocked.

Runs on a built Pages-style subpath. No live credentials, provider requests,
image generation or claims about the aesthetic quality of generated figures.
"""
from __future__ import annotations

import argparse
import copy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
import zipfile

from playwright.sync_api import sync_playwright
from silicon_canvas import engine

ROOT = Path(__file__).resolve().parents[1]
AUTO = {"style": "auto", "density": "auto", "aspect": "auto", "scene": "auto", "representation": "auto", "completion_mode": "auto", "explanatory_mode": "auto"}
SELECTED = {"style": "monochrome", "density": "high", "aspect": "A4"}
MOCK_KEY = "workbench-test-key-not-real"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def spec(language="en"):
    return {"title": "接收缓冲" if language == "zh" else "Receive buffer", "category": "dataflow", "groups": [],
            "nodes": [{"id": "input", "label": "输入" if language == "zh" else "Input", "kind": "io", "origin": "given", "evidence": "输入"},
                      {"id": "buffer", "label": "缓冲" if language == "zh" else "Buffer", "kind": "memory", "origin": "given", "evidence": "缓冲"}],
            "edges": [{"source": "input", "target": "buffer", "kind": "data", "label": "", "origin": "given", "evidence": "输入到缓冲"}]}


def ready(page):
    page.wait_for_function("() => document.querySelector('#cancel').hidden && !document.querySelector('#generate').disabled")


def open_download(page):
    page.locator("#downloadMenu").evaluate("node => { node.open = true; }")


def save_project(page, output, name):
    open_download(page)
    with page.expect_download() as pending:
        page.locator("#saveProject").click()
    path = output / (name + ".json")
    pending.value.save_as(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert MOCK_KEY not in path.read_text(encoding="utf-8"), "API key leaked into project"
    return path, data


def hidden_technical_ui(page):
    for selector in ("#notes", "#language", "#guide", "#guideDetails", "#specEditor", ".representation-choice", "[data-tab]", "#applyStyle"):
        assert page.locator(selector).count() == 0, selector + " still exposes obsolete controls"
    assert page.locator("#outputPanel").is_hidden()
    assert not page.locator("#customDetails").evaluate("node => node.open")
    for name in AUTO:
        element = {"completion_mode": "completionMode", "explanatory_mode": "explanatoryMode"}.get(name, name)
        assert page.locator("#" + element).input_value() == "auto", name + " is not automatic by default"


def verify_workbench(browser, base, output, report, *, provider_checks=True):
    """Use the visible product flows; preserve structured result/export checks."""
    output.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    page.set_default_timeout(180000)
    errors, network, calls, held_routes = [], [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: network.append(request.url))
    mode = {"value": "normal", "sequence": 0}

    def completion(route):
        payload = json.loads(route.request.post_data)
        messages = payload["messages"]
        initial = json.loads(messages[1]["content"])
        requested = initial.get("automatic_visual_settings", {}).get("fields", [])
        language = initial["image_label_language"]
        assert "language" not in requested, "Artwork language must not be inferred from input prose"
        data = spec(language)
        if requested:
            data["visual_settings"] = {key: SELECTED[key] for key in requested}
        is_repair = len(messages) > 2
        if mode["value"] in {"repair", "fail"} and (not is_repair or mode["value"] == "fail"):
            data["nodes"][1]["evidence"] = "translated unsupported quote"
        if is_repair and mode["value"] in {"repair", "fail"}:
            assert "nodes[1].evidence" in messages[-1]["content"]
        if mode["value"] == "invalid-options" and not is_repair:
            data["visual_settings"]["style"] = "unbounded-user-color"
        if mode["value"] == "invalid-options" and is_repair:
            assert "visual_settings.style" in messages[-1]["content"]
        calls.append({"mode": mode["value"], "repair": is_repair, "requested_fields": requested,
                      "manual_overrides": initial.get("automatic_visual_settings", {}).get("manual_overrides", {}),
                      "language": initial["image_label_language"], "description": initial["description"]})
        if mode["value"] == "cancel":
            held_routes.append(route)
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(data, ensure_ascii=False)}}], "usage": {"total_tokens": 17}}))

    try:
        page.route("https://api.deepseek.com/**", completion)
        page.goto(base, wait_until="networkidle")
        hidden_technical_ui(page)
        page.screenshot(path=str(output / "workbench-empty-desktop.png"), full_page=True)
        page.locator("#fillExample").click()
        assert page.locator("#description").input_value().strip()
        assert not calls, "Example fill sent a provider request"
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
        page.screenshot(path=str(output / "workbench-input-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1050})

        if provider_checks:
            # Exercise the exact shared prepare/finish boundary, rather than
            # inferring its correctness from text on the finished page.
            parity_input = {**AUTO, "language": "auto", "category": "auto", "labels": "", "notes": "",
                            "description": "画输入到缓冲，黑白配色、A4竖版，详细一点。"}
            native_messages, native_context = engine.prepare_request(parity_input)
            page.evaluate("async () => { const {Compiler} = await import('./compiler.js'); window.qaCompiler = new Compiler(); }")
            prepared = page.evaluate("async payload => await window.qaCompiler.call('prepare', payload)", parity_input)
            assert prepared == {"messages": native_messages, "context": native_context}
            response = {**spec(), "visual_settings": SELECTED}
            worker = page.evaluate("async payload => await window.qaCompiler.call('finish', payload)", {"data": response, "context": prepared["context"]})
            native = engine.finish_request(response, native_context)
            assert worker == native, "Automatic options differ between Worker and native core"
            assert "visual_settings" not in worker["spec"]
            page.locator("#openSettings").click()
            page.locator("#apiKey").fill(MOCK_KEY)
            page.locator("#settingsForm button[type=submit]").click()
            assert MOCK_KEY not in page.evaluate("JSON.stringify({local:{...localStorage},session:{...sessionStorage}})")
            description = "画输入到缓冲，黑白配色、A4竖版，详细一点。"
            page.locator("#description").fill(description)
            page.locator("#generate").click()
            ready(page)
            assert page.locator("#outputPanel").is_visible()
            assert len(calls) == 1 and set(calls[0]["requested_fields"]) == set(SELECTED), "Auto options added another model call or did not request a real selection"
            _, project = save_project(page, output, "auto-project")
            result = project["result"]
            for field, value in SELECTED.items():
                assert result["settings"][field] == value
            assert result["settings"]["automatic_visual_settings"]["method"] == "semantic-response"
            assert project["input"]["language"] == result["settings"]["language"] == calls[-1]["language"] == "en"
            assert project["input"]["style"] == project["input"]["density"] == "auto"
            assert result["spec"]["nodes"][0]["label"] == "Input"
            assert result["spec"]["nodes"][0]["evidence"] == "输入"
            assert not project["input"].get("notes"), "New natural input unexpectedly has a second requirements field"
            assert page.locator("#promptOutput").input_value() == result["prompt"]
            assert page.locator("#resultTitle").inner_text() == result["spec"]["title"]
            page.screenshot(path=str(output / "workbench-result-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            page.screenshot(path=str(output / "workbench-result-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1050})
            open_download(page)
            with page.expect_download() as pending:
                page.locator("#downloadBundle").click()
            pack_path = output / "auto-generation-pack.zip"
            pending.value.save_as(str(pack_path))
            with zipfile.ZipFile(pack_path) as archive:
                portable = json.loads(archive.read("result.json"))
                assert portable["spec"] == result["spec"]
                assert portable["settings"]["automatic_visual_settings"] == result["settings"]["automatic_visual_settings"]
                assert not any(MOCK_KEY.encode() in archive.read(name) for name in archive.namelist())
                selected = next(item for item in portable["figures"] if item["id"] == portable["selected_figure_id"])
                if selected.get("requires_layout_guide"):
                    assert "figures/" + selected["id"] + "/layout-guide.png" in archive.namelist(), "Required generation reference was removed from export with the UI"
            page.locator("#refinement").evaluate("node => { node.open = true; }")
            page.locator("#feedback").fill("增加模块间距，保持技术关系。")
            start = len(calls)
            page.locator("#refine").click()
            ready(page)
            assert len(calls) == start + 1 and not calls[-1]["requested_fields"]
            _, refined = save_project(page, output, "refined-project")
            assert refined["result"]["spec"]["nodes"] == result["spec"]["nodes"]
            assert refined["result"]["spec"]["edges"] == result["spec"]["edges"]
            assert refined["result"]["settings"]["style"] == "monochrome"

            page.locator("#customDetails").evaluate("node => { node.open = true; }")
            page.locator("#style").select_option("blueprint")
            page.locator("#density").select_option("low")
            page.locator("#aspect").select_option("16:9")
            page.locator("#generate").click()
            ready(page)
            _, manual = save_project(page, output, "manual-project")
            for field, value in {"style": "blueprint", "language": "en", "density": "low", "aspect": "16:9"}.items():
                assert manual["result"]["settings"][field] == value
            assert not calls[-1]["requested_fields"], "Manual fields were still offered to the model as auto"
            page.locator("#resetSettings").click()
            for field in AUTO:
                element = {"completion_mode": "completionMode", "explanatory_mode": "explanatoryMode"}.get(field, field)
                assert page.locator("#" + element).input_value() == "auto"
            page.locator("#customDetails").evaluate("node => { node.open = false; }")
            page.locator("#generate").click()
            ready(page)
            assert set(calls[-1]["requested_fields"]) == set(SELECTED)
            mode["value"] = "invalid-options"
            start = len(calls)
            page.locator("#generate").click()
            ready(page)
            assert len(calls) == start + 2 and calls[-1]["repair"]
            _, options_repaired = save_project(page, output, "auto-options-repaired")
            assert options_repaired["result"].get("repaired") is True
            assert options_repaired["result"]["settings"]["style"] == "monochrome"

            mode["value"] = "cancel"
            start = len(calls)
            page.locator("#generate").click()
            page.wait_for_function("() => !document.querySelector('#cancel').hidden")
            page.wait_for_timeout(200)
            page.locator("#cancel").click()
            ready(page)
            assert "取消" in page.locator("#notice").inner_text()
            for route in held_routes:
                try:
                    route.abort()
                except Exception:
                    pass
            held_routes.clear()

            # Real one-repair control flow with a strict source error, then a
            # failed bounded repair; no provider is contacted outside this route.
            page.locator("#customDetails").evaluate("node => { node.open = true; }")
            page.locator("#completionMode").select_option("strict")
            page.locator("#description").fill("输入到缓冲。")
            mode["value"] = "repair"
            start = len(calls)
            page.locator("#generate").click()
            ready(page)
            assert len(calls) == start + 2 and calls[-1]["repair"]
            _, repaired = save_project(page, output, "strict-repaired")
            assert repaired["result"].get("repaired") is True
            assert repaired["result"]["spec"]["edges"][0]["evidence"] == "输入到缓冲"
            mode["value"] = "fail"
            start = len(calls)
            page.locator("#generate").click()
            ready(page)
            assert len(calls) == start + 2
            assert page.locator("#notice").is_visible() and "nodes[1].evidence" in page.locator("#notice").inner_text()
            mode["value"] = "normal"

        page.reload(wait_until="networkidle")
        assert not page.locator("#settingsDialog").evaluate("node => node.open")
        assert any(word in page.locator("#keyStatus").inner_text() for word in ("配置", "连接"))
        assert MOCK_KEY not in page.evaluate("JSON.stringify({local:{...localStorage},session:{...sessionStorage}})")
        assert not errors, errors
        assert not any("/api/" in url for url in network), "Unexpected application backend request"
        report["workbench"] = {"transport": "mocked provider; actual UI and Pyodide Worker", "provider_calls": len(calls),
            "default_auto_options_same_semantic_response": provider_checks, "manual_options_and_reset": provider_checks,
            "auto_prepare_finish_native_worker_equal": provider_checks,
            "single_bounded_repair": provider_checks, "key_not_in_storage_project_or_bundle": True,
            "new_english_artwork_with_chinese_input": provider_checks,
            "obsolete_technical_ui_removed": True,
            "mobile_no_horizontal_overflow": True, "page_errors": errors,
            "actual_image_quality": "not_certified_by_this_software_check"}
    finally:
        page.close()


def verify_live_workbench(browser, base, output):
    """One explicitly requested live request; never persist the configured key."""
    from silicon_canvas import provider
    configured = provider.load_settings()
    if not configured.api_key:
        raise RuntimeError("Live validation requested but provider key is not configured")
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    page.set_default_timeout(240000)
    try:
        page.goto(base, wait_until="networkidle")
        page.locator("#openSettings").click()
        page.locator("#apiKey").fill(configured.api_key)
        page.locator("#baseUrl").evaluate("node => { for (let p = node.parentElement; p; p = p.parentElement) if (p.tagName === 'DETAILS') p.open = true; }")
        page.locator("#baseUrl").fill(configured.base_url)
        page.locator("#model").fill(configured.model)
        page.locator("#settingsForm button[type=submit]").click()
        page.locator("#description").fill("画一个完整的 SoC 系统，给同事解释计算、存储和外部接口；中文标签，黑白配色，A4竖版。")
        page.locator("#generate").click()
        ready(page)
        if page.locator("#notice").is_visible() and "error" in (page.locator("#notice").get_attribute("class") or ""):
            raise RuntimeError("Live workbench generation failed: " + page.locator("#notice").inner_text())
        path, project = save_project(page, output, "live-workbench-project")
        assert configured.api_key not in path.read_text(encoding="utf-8")
        result = project["result"]
        return {"provider": configured.model, "source_nodes": len(result["spec"]["nodes"]),
                "source_edges": len(result["spec"]["edges"]), "visual_selection": result["settings"].get("automatic_visual_settings"),
                "browser_direct_api": True, "actual_image_quality": "not_checked"}
    finally:
        page.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / ".local/workbench-20261018"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    report = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "dist")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            verify_workbench(browser, f"http://127.0.0.1:{server.server_port}/web/", output, report)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
