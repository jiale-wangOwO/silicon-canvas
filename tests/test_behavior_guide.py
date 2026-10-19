"""Behavioral figure contracts on semantic counterexamples and real exports."""
import copy
import io
import json
import re
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw
from silicon_canvas import behavior_guide, bundle, engine, layout_guide

FIXTURES = Path(__file__).parent / "fixtures/design_coverage"


def request(name):
    return json.loads((FIXTURES / (name + ".json")).read_text(encoding="utf-8"))


def spec(category, nodes, edges=(), groups=(), annotations=()):
    return engine.normalize_spec({"title": "Synthetic behavior case", "category": category,
                                  "nodes": nodes, "edges": list(edges), "groups": list(groups),
                                  "annotations": list(annotations), "steps": []})


def node(nid, kind="state", label=None, detail="", group=""):
    return {"id": nid, "label": label or nid.upper(), "kind": kind, "group": group, "detail": detail}


def edge(a, b, label="", kind="control"):
    return {"source": a, "target": b, "kind": kind, "label": label}


def primary(result):
    return next(figure for figure in result["figures"] if figure["primary"])


class BehaviorGuideTests(unittest.TestCase):
    def test_retry_fsm_keeps_every_predicate_hold_and_unconditional_exit(self):
        payload = request("retry-controller")
        before = copy.deepcopy(payload)
        result = engine.compile_manual(payload)
        figure = primary(result)
        plan = figure["behavior_plan"]
        self.assertEqual(payload, before)
        self.assertEqual(plan["grammar"], "state-machine")
        self.assertEqual(plan["initial_node_ids"], ["idle"])
        transitions = {(item["source"], item["target"], item["label"]) for item in plan["relations"]}
        self.assertEqual(transitions, {(item["source"], item["target"], item["label"]) for item in payload["spec"]["edges"]})
        holds = {route["source"] for route in plan["routes"] if route["source"] == route["target"]}
        self.assertEqual(holds, {"idle", "issue", "wait", "error"})
        self.assertNotIn("retry", holds)
        self.assertNotIn("done", holds)
        self.assertTrue(all(route["stroke_style"] == "solid" and not route["bidirectional"] for route in plan["routes"]))
        self.assertIn("busy=0", plan["state_outputs"]["idle"])
        self.assertIn("done=1", plan["state_outputs"]["done"])
        self.assertTrue(any("highest priority" in text for text in plan["reset_notes"]))
        self.assertCountEqual([index for route in plan["routes"] for index in route["members"]], range(len(payload["spec"]["edges"])))

    def test_no_initial_declaration_does_not_create_an_initial_marker(self):
        source = spec("fsm", [node("a", detail="A normal state"), node("b", detail="A second state")],
                      [edge("a", "b", "event")])
        figure = behavior_guide.primary(source)
        compiled = behavior_guide.build(source, figure, {})
        self.assertEqual(compiled["behavior_plan"]["initial_node_ids"], [])

    def test_negated_initial_state_is_not_an_entry_declaration(self):
        source = spec("fsm", [node("a", detail="This is not an initial state; busy=1"), node("b", detail="Regular state; busy=0")],
                      [edge("a", "b", "finish")])
        compiled = behavior_guide.build(source, behavior_guide.primary(source), {})
        self.assertEqual(compiled["behavior_plan"]["initial_node_ids"], [])

    def test_competing_self_loops_have_distinct_visible_paths_and_predicate_positions(self):
        source = spec("fsm", [node("wait", detail="busy=1")],
                      [edge("wait", "wait", "!response && !timeout"), edge("wait", "wait", "paused && !cancel")])
        plan = behavior_guide.build(source, behavior_guide.primary(source), {})["behavior_plan"]
        self.assertEqual(len(plan["routes"]), 2)
        self.assertNotEqual(plan["routes"][0]["points"], plan["routes"][1]["points"])
        self.assertNotEqual(plan["routes"][0]["label_at"], plan["routes"][1]["label_at"])
        self.assertEqual({item["label"] for item in plan["routes"]}, {"!response && !timeout", "paused && !cancel"})

    def test_input_guard_is_not_misclassified_as_a_state_output_in_plan_or_guide(self):
        source = spec("fsm", [node("wait", detail="Wait until ack=1; busy=1"), node("done", detail="done=1")],
                      [edge("wait", "done", "ack=1"), edge("wait", "wait", "ack=0")])
        result = engine.compile_manual({"spec": source, "settings": {"representation": "diagram"}})
        figure = primary(result)
        plan = figure["behavior_plan"]
        self.assertEqual(plan["state_outputs"]["wait"], ["busy=1"])
        assigned = [item["text"] for item in figure["label_layout"]["labels"]
                    if item["role"] == "state-output" and item["source_node_ids"] == ["wait"]]
        self.assertEqual(assigned, ["busy=1"])
        # The renderer must use the same interpretation, rather than parsing
        # all assignments again and showing an input as a asserted output.
        calls, original_draw = [], ImageDraw.Draw
        class RecordingDraw:
            def __init__(self, drawing): self.drawing = drawing
            def __getattr__(self, name): return getattr(self.drawing, name)
            def text(self, xy, text, *args, **kwargs):
                calls.append((xy, text))
                return self.drawing.text(xy, text, *args, **kwargs)
        with patch.object(ImageDraw, "Draw", side_effect=lambda *args, **kwargs: RecordingDraw(original_draw(*args, **kwargs))):
            self.assertTrue(layout_guide.render(result, figure))
        x, y = plan["positions"]["wait"]
        inside_wait = [text for (tx, ty), text in calls if x - 78 < tx < x + 78 and y - 78 < ty < y + 78]
        self.assertTrue(any("busy=1" in text for text in inside_wait))
        self.assertFalse(any("ack=1" in text for text in inside_wait))

    def test_sampled_handshake_preserves_stall_and_three_adjacent_transfers(self):
        result = engine.compile_manual(request("ready-valid-trace"))
        figure = primary(result)
        plan = figure["behavior_plan"]
        self.assertEqual(plan["grammar"], "sampled-timing")
        self.assertEqual(plan["axis"], ["c" + str(i) for i in range(8)])
        rows = {row["id"]: row for row in plan["rows"]}
        self.assertEqual(rows["clk"]["kind"], "sample-markers")
        self.assertEqual(rows["clk"]["values"], [])
        self.assertEqual(rows["data"]["values"][2:5], ["A", "A", "A"])
        accepted = [i for i, (valid, ready) in enumerate(zip(rows["valid"]["values"], rows["ready"]["values"])) if valid == ready == "1"]
        self.assertEqual(accepted, [4, 5, 6])
        self.assertEqual([rows["data"]["values"][index] for index in accepted], ["A", "B", "C"])
        self.assertEqual([i for i, value in enumerate(rows["transfer"]["values"]) if value == "1"], accepted)
        self.assertNotIn("duty_cycle", plan)
        self.assertIn("unspecified", plan["sampling_policy"])
        samples = [item for item in figure["label_layout"]["labels"] if item["role"] == "sample"]
        self.assertEqual(len(samples), 8 * (len(rows) - 1))
        self.assertEqual({tuple(item["source_node_ids"]) for item in samples}, {(nid,) for nid in rows if nid != "clk"})

    def test_state_guide_draws_the_actual_conditions_outputs_and_one_head_per_transition(self):
        result = engine.compile_manual(request("retry-controller"))
        figure = primary(result)
        text_calls, polygons = [], []
        original_draw = ImageDraw.Draw
        class RecordingDraw:
            def __init__(self, drawing):
                self.drawing = drawing
            def __getattr__(self, name):
                return getattr(self.drawing, name)
            def text(self, xy, text, *args, **kwargs):
                text_calls.append(text)
                return self.drawing.text(xy, text, *args, **kwargs)
            def polygon(self, points, *args, **kwargs):
                polygons.append(points)
                return self.drawing.polygon(points, *args, **kwargs)
        with patch.object(ImageDraw, "Draw", side_effect=lambda *args, **kwargs: RecordingDraw(original_draw(*args, **kwargs))):
            guide = layout_guide.render(result, figure)
        self.assertTrue(guide)
        rendered_text = "".join(re.sub(r"\s+", "", text) for text in text_calls)
        for source_node in result["spec"]["nodes"]:
            self.assertIn(source_node["label"], rendered_text)
        for relation in result["spec"]["edges"]:
            self.assertIn(re.sub(r"\s+", "", relation["label"]), rendered_text)
        self.assertIn("busy=0", rendered_text)
        self.assertIn("busy=1", rendered_text)
        self.assertIn("done=1", rendered_text)
        routes = figure["structure_layout"]["routes"]
        self.assertEqual(len(polygons), len(routes) + len(figure["behavior_plan"]["initial_node_ids"]))
        # The actual renderer head tips end on the declared directed targets;
        # this catches a guide that reverses heads despite a correct ledger.
        for route, arrowhead in zip(routes, polygons):
            self.assertEqual(tuple(arrowhead[0]), tuple(route["points"][-1]))

    def test_inconsistent_or_truncated_trace_is_not_certified_as_a_sample_table(self):
        source = spec("timing", [node("valid", "signal", detail="c0..c2: 0 1 1"),
                                 node("ready", "signal", detail="c0..c3: 0 1 1 1")])
        self.assertIsNone(behavior_guide.primary(source))
        source["nodes"][1]["detail"] = "c0..c2: 0 1"
        self.assertIsNone(behavior_guide.primary(source))

    def test_topology_retains_only_real_mesh_links_and_endpoint_attachments(self):
        payload = request("mesh-memory")
        source = payload["spec"]
        result = engine.compile_manual(payload)
        figure = primary(result)
        plan = figure["behavior_plan"]
        self.assertEqual(plan["grammar"], "logical-topology")
        self.assertEqual(set(plan["positions"]), {node["id"] for node in source["nodes"]})
        relations = [(item["source"], item["target"], item["kind"], item["label"]) for item in plan["relations"]]
        self.assertEqual(relations, [(item["source"], item["target"], item["kind"], item["label"]) for item in source["edges"]])
        anchors = {item["id"]: item["coordinate"] for item in plan["anchors"]}
        for relation in plan["relations"]:
            a, b = relation["source"], relation["target"]
            if a in anchors and b in anchors:
                self.assertEqual(sum(abs(x - y) for x, y in zip(anchors[a], anchors[b])), 1)
        self.assertTrue(all(not route["bidirectional"] for route in plan["routes"]))
        self.assertCountEqual([index for route in plan["routes"] for index in route["members"]], range(len(source["edges"])))
        self.assertNotIn("bandwidth", plan)

    def test_multiple_endpoints_on_one_router_do_not_overlap(self):
        source = spec("memory", [node("r0", "control", detail="logical position (0,0)"),
                                 node("r1", "control", detail="logical position (1,0)"),
                                 node("r2", "control", detail="logical position (2,0)"),
                                 node("hosta", "io"), node("hostb", "io")],
                      [edge("r0", "r1", "request", "data"), edge("r1", "r2", "request", "data"),
                       edge("hosta", "r0", "A", "data"), edge("hostb", "r0", "B", "data")])
        plan = behavior_guide.build(source, behavior_guide.primary(source), {})["behavior_plan"]
        self.assertNotEqual(plan["positions"]["hosta"], plan["positions"]["hostb"])
        xa, ya = plan["positions"]["hosta"]
        xb, yb = plan["positions"]["hostb"]
        self.assertTrue(abs(xa - xb) >= 196 or abs(ya - yb) >= 84)

    def test_unconnected_topology_resource_keeps_the_compiler_usable_and_source_complete(self):
        source = spec("memory", [node("r0", "control", detail="logical position (0,0)"),
                                 node("r1", "control", detail="logical position (1,0)"),
                                 node("r2", "control", detail="logical position (2,0)"), node("monitor", "control")],
                      [edge("r0", "r1", "forward", "data"), edge("r1", "r2", "forward", "data")])
        result = engine.compile_manual({"spec": source, "settings": {"representation": "diagram"}})
        self.assertEqual(result["spec"], source)
        figure = primary(result)
        represented = {nid for obj in figure["macro_nodes"] for nid in obj.get("members", [obj["id"]])}
        self.assertEqual(represented, {"r0", "r1", "r2", "monitor"})

    def test_explicit_topology_self_loop_compiles_without_losing_the_real_relation(self):
        source = spec("memory", [node("r0", "control", detail="logical position (0,0)"),
                                 node("r1", "control", detail="logical position (1,0)"),
                                 node("r2", "control", detail="logical position (2,0)")],
                      [edge("r0", "r1", "forward", "data"), edge("r1", "r2", "forward", "data"),
                       edge("r0", "r0", "local return", "data")])
        result = engine.compile_manual({"spec": source, "settings": {"representation": "diagram"}})
        figure = primary(result)
        self.assertEqual(result["spec"], source)
        self.assertEqual(figure["behavior_plan"]["grammar"], "logical-topology")
        loops = [route for route in figure["behavior_plan"]["routes"] if route["source"] == route["target"]]
        self.assertEqual(len(loops), 1)
        self.assertEqual(loops[0]["source"], "r0")
        self.assertEqual(loops[0]["label"], "local return")
        self.assertEqual(loops[0]["members"], [2])
        self.assertGreater(len({tuple(point) for point in loops[0]["points"]}), 2)
        self.assertTrue(layout_guide.render(result, figure))

    def test_process_fallback_preserves_private_shared_branches_return_and_numeric_selection(self):
        payload = request("branched-tile-return")
        source = engine.normalize_spec(payload["spec"])
        figure = {"id": "all", "title": source["title"], "primary": True,
                  "node_ids": [node["id"] for node in source["nodes"]]}
        compiled = behavior_guide.flow_fallback(source, figure, {})
        self.assertIsNotNone(compiled)
        plan = compiled["behavior_plan"]
        self.assertEqual(plan["grammar"], "directed-process")
        self.assertEqual(set(plan["positions"]), {node["id"] for node in source["nodes"]})
        self.assertCountEqual([index for route in plan["routes"] for index in route["members"]], range(len(source["edges"])))
        self.assertEqual([(item["source"], item["target"], item["kind"], item["label"]) for item in plan["relations"]],
                         [(item["source"], item["target"], item["kind"], item["label"]) for item in source["edges"]])
        self.assertFalse(plan["initial_node_ids"])
        self.assertIn("6 banks", plan["object_text"]["bank"]["source_detail"])
        self.assertIn("64-B tile", plan["object_text"]["bank"]["source_detail"])
        self.assertTrue(any(item["text"] == "2x4 tile selection" for item in compiled["label_layout"]["labels"]))
        self.assertNotIn("cycles", plan)

    def test_reverse_ready_arrival_and_departure_do_not_bypass_an_intermediate_stage(self):
        source = engine.normalize_spec(request("elastic-pipeline")["spec"])
        compiled = behavior_guide.flow_fallback(source, {"primary": True, "node_ids": [item["id"] for item in source["nodes"]]}, {})
        self.assertIsNotNone(compiled, "The six-stage elastic example must keep a usable semantic guide")
        routes = compiled["behavior_plan"]["routes"]
        ready = [route for route in routes if route["kind"] == "control"]
        self.assertEqual(len(ready), 5)
        for nid in ["decode", "crc", "fifo", "frame"]:
            incoming = next(route for route in ready if route["target"] == nid)
            outgoing = next(route for route in ready if route["source"] == nid)
            self.assertEqual(incoming["label"], "ready")
            self.assertEqual(outgoing["label"], "ready")
            self.assertNotEqual(incoming["points"][-1], outgoing["points"][0])
            # A common vertical leg forms a visible T-junction bypassing the
            # stage, even if the metadata lists two independent connections.
            a, b = incoming["points"][-2:]
            c, d = outgoing["points"][:2]
            shared_vertical = abs(a[0] - b[0]) < .01 and abs(c[0] - d[0]) < .01 and abs(a[0] - c[0]) < .01
            overlap = min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1]))
            self.assertFalse(shared_vertical and overlap > .01, f"Ready bypasses {nid}")
            self.assertEqual(incoming["stroke_style"], "dashed")
            self.assertEqual(outgoing["stroke_style"], "dashed")

    def test_long_process_cannot_claim_a_readable_guide_with_overlapping_resource_glyphs(self):
        nodes = [node("s" + str(i), "stage", "Stage " + str(i)) for i in range(12)]
        source = spec("pipeline", nodes, [edge("s" + str(i), "s" + str(i + 1), "payload", "data") for i in range(11)])
        compiled = behavior_guide.flow_fallback(source, {"primary": True, "node_ids": [item["id"] for item in nodes]}, {})
        if compiled is None:
            return  # Explicit layout limitations are preferable to false preflight.
        plan = compiled["behavior_plan"]
        for index, nid in enumerate(plan["positions"]):
            xa, ya = plan["positions"][nid]; wa, ha = plan["sizes"][nid]
            for other in list(plan["positions"])[index + 1:]:
                xb, yb = plan["positions"][other]; wb, hb = plan["sizes"][other]
                self.assertTrue(abs(xa - xb) >= (wa + wb) / 2 or abs(ya - yb) >= (ha + hb) / 2,
                                f"Source resources {nid} and {other} overlap")

    def test_exported_semantics_guide_and_review_match_the_selected_source_scope(self):
        for name in ["retry-controller", "ready-valid-trace", "mesh-memory", "elastic-pipeline"]:
            with self.subTest(name=name):
                result = engine.compile_manual(request(name))
                figure = primary(result)
                self.assertIn("behavior_plan", figure)
                guide = layout_guide.render(result, figure)
                self.assertTrue(guide.startswith(b"\x89PNG\r\n\x1a\n"))
                image = Image.open(io.BytesIO(guide)); image.load()
                self.assertEqual(image.size, (1800, figure["structure_layout"]["height"]))
                review = figure["review_task"]
                self.assertEqual(review["status"], "not_reviewed")
                self.assertEqual(review["semantic_plan"], figure["behavior_plan"])
                self.assertEqual(review["source_scope"], figure["source_edge_indices"])
                self.assertEqual(figure["behavior_plan"]["actual_image_status"], "not_reviewed")
                self.assertFalse(figure["layout_scene"]["quality"]["typography_measured"])
                with zipfile.ZipFile(io.BytesIO(bundle.build(result, figure["id"]))) as archive:
                    prefix = "figures/" + figure["id"] + "/"
                    self.assertEqual(json.loads(archive.read(prefix + "semantic-plan.json")), figure["behavior_plan"])
                    self.assertEqual(archive.read(prefix + "layout-guide.png"), guide)
                    self.assertEqual(json.loads(archive.read("result.json"))["spec"], result["spec"])
                    self.assertEqual(json.loads(archive.read(prefix + "review-manifest.json"))["status"], "not_reviewed")


if __name__ == "__main__":
    unittest.main()
