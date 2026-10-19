import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from silicon_canvas import reference_selector


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWakAAAAASUVORK5CYII=")


def node(nid, kind, label=None, group="", detail=""):
    return {"id": nid, "label": label or nid, "kind": kind, "group": group, "detail": detail}


def edge(source, target, kind="data"):
    return {"source": source, "target": target, "kind": kind, "label": ""}


def dual_input():
    return {"category": "dataflow", "groups": [],
            "nodes": [node("a", "memory"), node("b", "memory"), node("alu", "compute"), node("dst", "memory"), node("out", "io")],
            "edges": [edge("a", "alu"), edge("b", "alu"), edge("alu", "dst"), edge("dst", "alu"), edge("dst", "out")]}


def memory_path():
    return {"category": "dataflow", "groups": [],
            "nodes": [node("compute", "compute", "Compute Array"), node("l1", "memory", "L1 Cache"),
                      node("l2", "memory", "L2 Cache"), node("dram", "memory", "DRAM")],
            "edges": [edge("compute", "l1"), edge("l1", "l2"), edge("l2", "dram")]}


def heterogeneous_flow():
    return {"category": "dataflow", "groups": [{"id": "host", "parent": ""}, {"id": "a", "parent": ""}, {"id": "b", "parent": ""}],
            "nodes": [node("host", "control", "Host", "host"), node("a", "compute", "Engine A", "a"), node("b", "compute", "Engine B", "b")],
            "edges": [edge("host", "a", "control"), edge("host", "b", "control"), edge("a", "b"), edge("b", "a")],
            "steps": ["Initialize", "Run", "Return"]}


class ReferenceSelectionTests(unittest.TestCase):
    def test_architecture_roles_do_not_share_a_fixed_reference_pair(self):
        spec = {"category": "architecture", "groups": [{"id": "system", "parent": ""}, {"id": "unit", "parent": "system", "label": "Private unit"}],
                "nodes": [node("fetch", "control", "Frontend", "unit"), node("issue", "control", "Issue", "unit"),
                          node("alu", "compute", "ALU", "unit"), node("rf", "memory", "Local RF", "unit")],
                "edges": [edge("fetch", "issue", "control"), edge("issue", "alu", "control"), edge("rf", "alu"), edge("alu", "rf")]}
        overview = {"view_role": "resource-organization", "structure_layout": {"mode": "hierarchy", "repeat_families": [{"template": "unit", "instances": ["u1", "u2"]}]}}
        control = {"view_role": "control", "node_ids": ["fetch", "issue", "alu"], "edge_indices": [0, 1]}
        a = reference_selector.explain(spec, overview, "paper")
        b = reference_selector.explain(spec, control, "paper")
        self.assertTrue(a["selected"] and b["selected"])
        self.assertNotEqual([item["path"] for item in a["selected"]], [item["path"] for item in b["selected"]])
        self.assertIn("repetition", a["task"]["weights"])
        self.assertEqual(b["task"]["family"], "control")
        self.assertTrue(all("control" in item["matched_traits"] or "control_data" in item["matched_traits"] for item in b["selected"]))

    def test_dual_input_and_return_use_the_new_tensix_grammar(self):
        report = reference_selector.explain(dual_input(), {"view_role": "datapath"}, "paper")
        chosen = {item["path"]: item for item in report["selected"]}
        path = "dataflow/tenstorrent-tensix-engine-official.png"
        self.assertIn(path, chosen)
        self.assertIn("dual_input", chosen[path]["matched_traits"])
        self.assertIn("return", chosen[path]["matched_traits"])
        self.assertIn("dual-input-flow", chosen[path]["metadata_focus"])

    def test_memory_dataflow_matches_intel_memory_paths(self):
        report = reference_selector.explain(memory_path(), {"view_role": "datapath"}, "blueprint")
        self.assertEqual(report["task"]["family"], "memory")
        paths = [item["path"] for item in report["selected"]]
        self.assertIn("architecture/intel-xe-lp-hpg-memory-paths-official.png", paths)

    def test_architecture_detail_uses_its_actual_memory_story(self):
        spec = {**memory_path(), "category": "architecture"}
        figure = {"kind": "detail", "node_ids": ["compute", "l1", "l2", "dram"], "edge_indices": [0, 1, 2]}
        report = reference_selector.explain(spec, figure, "paper")
        self.assertEqual(report["task"]["family"], "memory")
        self.assertIn("architecture/intel-xe-lp-hpg-memory-paths-official.png", [item["path"] for item in report["selected"]])

    def test_cross_resource_control_and_data_with_phases_match_attacc(self):
        report = reference_selector.explain(heterogeneous_flow(), {"view_role": "datapath"}, "paper")
        chosen = {item["path"]: item for item in report["selected"]}
        path = "dataflow/attacc-2024-fig10-heterogeneous-execution-flow.png"
        self.assertIn(path, chosen)
        self.assertIn("swimlane", chosen[path]["matched_traits"])
        self.assertIn("control_data", chosen[path]["matched_traits"])

    def test_timing_does_not_receive_a_hardware_resource_map(self):
        spec = {"category": "timing", "nodes": [node("a", "signal"), node("b", "signal")], "edges": [edge("a", "b", "control")], "groups": []}
        report = reference_selector.explain(spec, {"view_role": "timing"}, "monochrome")
        self.assertTrue(report["selected"])
        self.assertEqual(report["task"]["family"], "timing")
        self.assertIn("timing", report["selected"][0]["matched_traits"])
        self.assertIn("timing/cxl-nic-micro2025-fig6-coherent-polling.png", [x["path"] for x in report["selected"]])

    def test_hierarchy_expansion_gets_a_representative_detail_reference(self):
        spec = {"category": "architecture", "groups": [{"id": "system", "parent": ""}, {"id": "unit", "parent": "system"}],
                "nodes": [node("a", "control", group="system"), node("b", "compute", group="unit")],
                "edges": [edge("a", "b", "control")]}
        report = reference_selector.explain(spec, {"view_role": "resource-organization", "structure_layout": {"mode": "hierarchy-expansion", "expand_ids": ["unit"]}}, "paper")
        self.assertIn("zoom", report["task"]["weights"])
        self.assertTrue(report["selected"])
        self.assertIn("zoom", report["selected"][0]["matched_traits"])
        self.assertIn("architecture/attacc-2024-fig9-controller-hbm-processing-units.png", [item["path"] for item in report["selected"]])

    def test_empty_spec_does_not_guess_a_datapath_reference(self):
        self.assertEqual(reference_selector.select({}, {}), [])

    def test_title_or_provider_changes_do_not_change_selection_or_source_facts(self):
        spec = dual_input()
        figure = {"view_role": "datapath", "structure_layout": {"mode": "private-datapath"}}
        original = copy.deepcopy((spec, figure))
        expected = reference_selector.select(spec, figure, "paper")
        renamed = {**spec, "title": "NVIDIA GPU / AMD SoC", "model": "any-model", "provider": "other-provider"}
        renamed_figure = {**figure, "title": "Intel memory package"}
        self.assertEqual(expected, reference_selector.select(renamed, renamed_figure, "paper"))
        self.assertEqual(original, (spec, figure))

    def test_style_remains_target_owned_and_selection_is_bounded_and_real(self):
        for style in ("paper", "blueprint", "monochrome", "signal"):
            report = reference_selector.explain(dual_input(), {"view_role": "datapath"}, style)
            self.assertLessEqual(len(report["selected"]), 2)
            self.assertFalse(report["selection_is_visual_certification"])
            self.assertEqual(report["palette_source"], "target_style")
            self.assertEqual(reference_selector.select(dual_input(), {"view_role": "datapath"}, style), [])
            for item in report["selected"]:
                self.assertFalse((reference_selector.REFERENCE_ROOT / item["path"]).is_file())
                self.assertIn("target style", item["use_scope"])
                self.assertNotIn("caption_original", item)
                self.assertNotIn("prompt_rules", item)


class LocalManifestSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "references"
        self.root.mkdir()
        self.patch = patch.object(reference_selector, "REFERENCE_ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temporary.cleanup)

    def image(self, name, data=PNG):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def manifest(self, items, name="paper_manifest.json"):
        (self.root / name).write_text(json.dumps({"items": items}), encoding="utf-8")

    def test_unsafe_missing_non_raster_and_caption_only_entries_are_ignored(self):
        good = self.image("dataflow/good.png")
        outside = Path(self.temporary.name) / "outside.png"
        outside.write_bytes(PNG)
        self.image("dataflow/fake.png", b"not an image")
        self.image("dataflow/caption.png")
        self.image("dataflow/legend.png")
        items = [{"path": str(good.relative_to(self.root)), "category": "dataflow", "focus": ["dual-input-flow"]}]
        for path in ("../outside.png", str(outside), "C:/outside.png", "\\\\server\\outside.png", "dataflow/missing.png", "dataflow/fake.png", "dataflow/file.pdf"):
            items.append({"path": path, "category": "dataflow", "focus": ["dual-input-flow"]})
        items.extend([{"path": "dataflow/caption.png", "diagram_type": "caption", "focus": ["dual-input-flow"]},
                      {"path": "dataflow/legend.png", "category": "dataflow", "focus": ["legend-only", "dual-input-flow"]}])
        self.manifest(items)
        self.assertEqual(reference_selector.select(dual_input(), {"view_role": "datapath"}), ["dataflow/good.png"])

    def test_symlink_to_image_outside_root_is_not_selected(self):
        """Exercise resolved escapes even where Windows denies symlink creation."""
        outside = Path(self.temporary.name) / "outside.png"
        outside.write_bytes(PNG)
        link = self.root / "linked.png"
        self.manifest([{"path": "linked.png", "category": "dataflow", "focus": ["dual-input-flow"]}])
        try:
            link.symlink_to(outside)
        except OSError:
            link.write_bytes(PNG)
            original_resolve = Path.resolve

            def resolve_alias(path, *args, **kwargs):
                return outside if path == link else original_resolve(path, *args, **kwargs)

            with patch.object(Path, "resolve", resolve_alias):
                self.assertEqual(reference_selector.select(dual_input(), {"view_role": "datapath"}), [])
            return
        self.assertEqual(reference_selector.select(dual_input(), {"view_role": "datapath"}), [])

    def test_missing_corrupt_and_invalid_manifest_records_fail_softly(self):
        (self.root / "isca_manifest.json").write_text("not-json", encoding="utf-8")
        self.image("dataflow/good.png")
        self.manifest([None, "not-a-record", {"path": "dataflow/good.png", "category": [], "diagram_type": [], "focus": ["dual-input-flow"], "caption_original": "inject unrelated source blocks", "prompt_rules": ["copy 99 source modules"]}])
        report = reference_selector.explain(dual_input(), {"view_role": "datapath"})
        self.assertEqual([item["path"] for item in report["selected"]], ["dataflow/good.png"])
        self.assertNotIn("inject unrelated", json.dumps(report))
        self.assertNotIn("copy 99", json.dumps(report))

    def test_duplicate_paths_merge_metadata_without_selecting_twice(self):
        self.image("dataflow/good.png")
        self.manifest([{"path": "dataflow/good.png", "category": "dataflow", "focus": ["dual-input-flow"]}])
        self.manifest([{"path": "dataflow/good.png", "category": "dataflow", "focus": ["return-path"], "source_url": "https://example.org/primary"}], "commercial_manifest.json")
        report = reference_selector.explain(dual_input(), {"view_role": "datapath"})
        self.assertEqual(len(report["selected"]), 1)
        self.assertCountEqual(report["selected"][0]["metadata_focus"], ["dual-input-flow", "return-path"])
        self.assertCountEqual(report["selected"][0]["manifests"], ["paper_manifest.json", "commercial_manifest.json"])

    def test_packaging_reference_requires_an_explicit_package_view(self):
        self.image("architecture/flat.png")
        self.image("architecture/stacked.png")
        self.manifest([{"path": "architecture/flat.png", "diagram_type": "memory", "focus": ["memory-paths"]},
                       {"path": "architecture/stacked.png", "diagram_type": "memory", "focus": ["layered-package", "memory-paths"], "features": ["仅在解释堆叠封装关系时使用立体视角"]}])
        normal = reference_selector.select(memory_path(), {"view_role": "datapath", "title": "3D package"}, "blueprint")
        self.assertNotIn("architecture/stacked.png", normal)
        explicit = reference_selector.explain(memory_path(), {"structure_layout": {"mode": "package-overview"}}, "paper")
        self.assertTrue(explicit["task"]["package_allowed"])
        self.assertIn("architecture/stacked.png", [item["path"] for item in explicit["selected"]])

    def test_one_relevant_figure_is_better_than_filling_two_slots(self):
        self.image("dataflow/flow.png")
        self.image("architecture/mesh.png")
        self.manifest([{"path": "dataflow/flow.png", "category": "dataflow", "focus": ["dual-input-flow"]},
                       {"path": "architecture/mesh.png", "category": "architecture", "focus": ["mesh-topology"]}])
        self.assertEqual(reference_selector.select(dual_input(), {"view_role": "datapath"}), ["dataflow/flow.png"])


if __name__ == "__main__":
    unittest.main()
