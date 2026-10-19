"""Independent geometry and source-truth regressions for direct connectors.

These checks examine the compiled reference, never certify Image Gen pixels.
They require short clear routes while retaining obstacles and distinct senses.
"""
import copy
import json
import math
from pathlib import Path
import unittest

from silicon_canvas import behavior_guide, engine, structure_scene


ROOT = Path(__file__).resolve().parents[1]
EPS = .01  # Six-decimal normalized coordinates can round by less than .002px.


def source(name):
    return json.loads((ROOT / "tests/fixtures/design_coverage" / (name + ".json")).read_text(encoding="utf-8"))


def compiled(payload):
    result = engine.compile_manual(payload)
    figure = next(f for f in result["figures"] if f["id"] == result["selected_figure_id"])
    return result, figure, figure["structure_layout"], figure["layout_scene"]


def pixels(scene, route):
    return [(x * scene["width"], y * scene["height"]) for x, y in route["points"]]


def rect_pixels(scene, box):
    return (box["x"] * scene["width"], box["y"] * scene["height"],
            (box["x"] + box["width"]) * scene["width"],
            (box["y"] + box["height"]) * scene["height"])


def hits_rect(a, b, rect):
    """Strict interior intersection, independently of the planner's gates."""
    x0, y0, x1, y1 = rect
    if abs(a[0] - b[0]) <= EPS:
        return x0 + EPS < a[0] < x1 - EPS and max(min(a[1], b[1]), y0) < min(max(a[1], b[1]), y1) - EPS
    if abs(a[1] - b[1]) <= EPS:
        return y0 + EPS < a[1] < y1 - EPS and max(min(a[0], b[0]), x0) < min(max(a[0], b[0]), x1) - EPS
    return False


def share_segment(a, b, c, d):
    if abs(a[0] - b[0]) <= EPS and abs(c[0] - d[0]) <= EPS and abs(a[0] - c[0]) <= EPS:
        return max(min(a[1], b[1]), min(c[1], d[1])) < min(max(a[1], b[1]), max(c[1], d[1])) - EPS
    if abs(a[1] - b[1]) <= EPS and abs(c[1] - d[1]) <= EPS and abs(a[1] - c[1]) <= EPS:
        return max(min(a[0], b[0]), min(c[0], d[0])) < min(max(a[0], b[0]), max(c[0], d[0])) - EPS
    return False


def plan_for(boxes, pairs, routing=None):
    nodes = [{"id": nid, "label": nid, "kind": "compute", "members": [nid]} for nid in boxes]
    edges = [{"id": "r" + str(i), "source": a, "target": b, "kind": "data", "label": "",
              "members": [i], "source_edge_index": i, **({"routing": copy.deepcopy(routing)} if routing else {})}
             for i, (a, b) in enumerate(pairs)]
    return {"abstract": False, "canvas": {"natural_aspect": 1.8}, "boxes": boxes,
            "macro_nodes": nodes, "macro_edges": edges, "containers": []}


def box(x, y, width=.12, height=.11):
    return {"x": x, "y": y, "width": width, "height": height}


def renamed(payload, reverse=False):
    """Preserve source facts under ids, labels, and declaration permutations."""
    changed = copy.deepcopy(payload)
    spec = changed["spec"]
    aliases = {item["id"]: "entity_" + str(i) for i, item in enumerate(spec["groups"] + spec["nodes"])}
    for group in spec["groups"]:
        old_id = group["id"]
        group["id"] = aliases[old_id]
        group["parent"] = aliases.get(group["parent"], "")
        group["label"] = group["label"].replace("Ingress Lane", "Capture Lane").replace("Channel", "Path")
    for node in spec["nodes"]:
        node["id"] = aliases[node["id"]]
        node["group"] = aliases.get(node["group"], "")
        node["label"] = node["label"].replace("Shared", "Common").replace("External", "Offsite")
    for edge in spec["edges"]:
        edge["source"], edge["target"] = aliases[edge["source"]], aliases[edge["target"]]
    if reverse:
        for field in ("groups", "nodes", "edges"):
            spec[field].reverse()
    return changed, aliases


class RouteSimplicityTests(unittest.TestCase):
    def assert_compact(self, points, *, orthogonal=True, minimum_interior=0):
        self.assertGreaterEqual(len(points), 2)
        lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
        self.assertTrue(all(length > EPS for length in lengths), ("zero-length segment", points))
        if orthogonal:
            for a, b in zip(points, points[1:]):
                self.assertTrue(abs(a[0] - b[0]) <= EPS or abs(a[1] - b[1]) <= EPS, points)
        for a, b, c in zip(points, points[1:], points[2:]):
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            self.assertGreater(abs(cross), EPS, ("redundant collinear bend", points))
        for length in lengths[1:-1]:
            self.assertGreaterEqual(length + EPS, minimum_interior, ("micro jog", points))

    def assert_clear(self, plan, scene, figure=None):
        self.assertTrue(scene["quality"]["routes_complete"], scene["quality"])
        for route in scene["routes"]:
            points = pixels(scene, route)
            for nid, b in plan["boxes"].items():
                if nid in (route["source"], route["target"]):
                    continue
                rect = rect_pixels(scene, b)
                self.assertFalse(any(hits_rect(a, b, rect) for a, b in zip(points, points[1:])), (route, nid))
            for inset in plan.get("insets", []):
                rect = rect_pixels(scene, inset["box"])
                self.assertFalse(any(hits_rect(a, b, rect) for a, b in zip(points, points[1:])), (route, inset["id"]))
            if figure:
                for label in figure["label_layout"]["labels"]:
                    rect = rect_pixels(scene, label["box"])
                    self.assertFalse(any(hits_rect(a, b, rect) for a, b in zip(points, points[1:])), (route, label))

    def assert_projected_truth(self, payload, result, figure, plan, scene):
        spec = payload["spec"]
        self.assertEqual(result["spec"], spec)
        self.assertEqual(plan["source_ownership"], {n["id"]: n["group"] for n in spec["nodes"]})
        mapping = figure["projection"]["source_node_to_macro"]
        self.assertEqual(set(mapping), {n["id"] for n in spec["nodes"]})
        objects = {n["id"]: n for n in figure["macro_nodes"]}
        for nid, obj in objects.items():
            self.assertEqual(set(obj["members"]), {source_id for source_id, owner in mapping.items() if owner == nid})
        shown = [i for e in figure["macro_edges"] for i in e["members"]]
        expected_internal = [i for i, e in enumerate(spec["edges"]) if mapping[e["source"]] == mapping[e["target"]]]
        expected_shown = [i for i in range(len(spec["edges"])) if i not in expected_internal]
        self.assertCountEqual(shown, expected_shown, "Every real cross-owner relationship must remain visible in the primary view")
        internal = figure["projection"].get("internal_edges", [])
        self.assertCountEqual(internal, expected_internal)
        self.assertCountEqual(shown + internal, range(len(spec["edges"])))
        self.assertEqual(len(shown + internal), len(set(shown + internal)))
        self.assertCountEqual([i for r in scene["routes"] for i in r["members"]], shown)
        self.assertEqual(len(scene["routes"]), len(figure["macro_edges"]))
        for route in scene["routes"]:
            self.assertFalse(route.get("bidirectional"), route)
            for index in route["members"]:
                original = spec["edges"][index]
                self.assertEqual((route["source"], route["target"], route["kind"]),
                                 (mapping[original["source"]], mapping[original["target"]], original["kind"]))

    def assert_independent_ports(self, scene):
        for nid in {r[side] for r in scene["routes"] for side in ("source", "target")}:
            endpoints = [pixels(scene, route)[position] for route in scene["routes"]
                         for side, position in (("source", 0), ("target", -1)) if route[side] == nid]
            for index, point in enumerate(endpoints):
                for other in endpoints[index + 1:]:
                    self.assertGreater(math.dist(point, other), 10, (nid, endpoints))

    def test_clear_aligned_facing_ports_connect_straight_at_arbitrary_coordinates(self):
        arrangements = [
            ({"a": box(.071, .2515), "b": box(.661, .2515)}, ("right", "left")),
            ({"b": box(.071, .2515), "a": box(.661, .2515)}, ("left", "right")),
            ({"a": box(.1915, .113), "b": box(.1915, .613)}, ("bottom", "top")),
            ({"b": box(.1915, .113), "a": box(.1915, .613)}, ("top", "bottom")),
        ]
        for boxes, sides in arrangements:
            with self.subTest(sides=sides):
                plan = plan_for(boxes, [("a", "b")], {"source_side": sides[0], "target_side": sides[1]})
                before = copy.deepcopy(plan)
                scene = structure_scene.prepare(plan)
                self.assertEqual(plan, before)
                self.assert_clear(plan, scene)
                self.assertEqual(len(scene["routes"][0]["points"]), 2, scene["routes"])

    def test_overlapping_port_spans_can_align_without_equating_box_centers(self):
        plan = plan_for({"a": box(.08, .20, height=.20), "b": box(.68, .29, height=.12)}, [("a", "b")],
                        {"source_side": "right", "target_side": "left"})
        scene = structure_scene.prepare(plan)
        self.assert_clear(plan, scene)
        points = pixels(scene, scene["routes"][0])
        self.assertEqual(len(points), 2, points)
        self.assertAlmostEqual(points[0][1], points[1][1], delta=EPS)

    def test_explicit_fractions_keep_ports_and_only_the_required_two_bends(self):
        routing = {"source_side": "right", "target_side": "left", "source_fraction": .25, "target_fraction": .75}
        plan = plan_for({"a": box(.083, .143), "b": box(.683, .553)}, [("a", "b")], routing)
        scene = structure_scene.prepare(plan)
        self.assert_clear(plan, scene)
        points = pixels(scene, scene["routes"][0])
        self.assertEqual(len(points), 4, points)
        self.assertAlmostEqual(points[0][1], (plan["boxes"]["a"]["y"] + .25 * .11) * scene["height"], delta=EPS)
        self.assertAlmostEqual(points[-1][1], (plan["boxes"]["b"]["y"] + .75 * .11) * scene["height"], delta=EPS)
        self.assert_compact(points, minimum_interior=8)
        manhattan = abs(points[-1][0] - points[0][0]) + abs(points[-1][1] - points[0][1])
        self.assertAlmostEqual(sum(math.dist(a, b) for a, b in zip(points, points[1:])), manhattan, delta=EPS)

    def test_clear_fanin_keeps_independent_routes_and_target_attachments(self):
        plan = plan_for({"first": box(.08, .20), "second": box(.08, .42),
                         "receiver": box(.68, .18, height=.44)},
                        [("first", "receiver"), ("second", "receiver")],
                        {"source_side": "right", "target_side": "left"})
        scene = structure_scene.prepare(plan)
        self.assert_clear(plan, scene)
        self.assertEqual([(r["source"], r["target"], r["members"]) for r in scene["routes"]],
                         [("first", "receiver", [0]), ("second", "receiver", [1])])
        paths = [pixels(scene, route) for route in scene["routes"]]
        for path in paths:
            self.assertEqual(len(path), 2, path)
        self.assertGreater(math.dist(paths[0][-1], paths[1][-1]), 100)
        self.assertFalse(any(share_segment(a, b, c, d) for a, b in zip(paths[0], paths[0][1:])
                             for c, d in zip(paths[1], paths[1][1:])), paths)

    def test_straight_shortcut_is_rejected_for_a_real_resource_or_scope_caption(self):
        for obstruction in ("resource", "caption"):
            with self.subTest(obstruction=obstruction):
                boxes = {"a": box(.08, .345), "b": box(.72, .345)}
                plan = plan_for(boxes, [("a", "b")], {"source_side": "right", "target_side": "left"})
                if obstruction == "resource":
                    plan["boxes"]["guard"] = box(.40, .23, .14, .36)
                    plan["macro_nodes"].append({"id": "guard", "label": "Unrelated resource", "kind": "memory"})
                    rect = rect_pixels({"width": 1800, "height": 1000}, plan["boxes"]["guard"])
                else:
                    plan["containers"] = [{"id": "scope", "label": "Reserved scope heading", "box": box(.40, .42, .25, .30)}]
                    rect = (728, 397, 981, 420)
                scene = structure_scene.prepare(plan)
                self.assert_clear(plan, scene)
                points = pixels(scene, scene["routes"][0])
                self.assertGreater(len(points), 2, points)
                self.assertFalse(any(hits_rect(a, b, rect) for a, b in zip(points, points[1:])), points)
                self.assert_compact(points)

    def test_explicit_outer_route_and_directed_senses_keep_distinct_ports(self):
        plan = plan_for({"a": box(.09, .31), "b": box(.70, .31)}, [("a", "b"), ("b", "a")])
        plan["macro_edges"][0]["routing"] = {"source_side": "right", "target_side": "left"}
        plan["macro_edges"][1].update(kind="feedback", routing={"source_side": "bottom", "target_side": "bottom",
            "source_fraction": .7, "target_fraction": .3, "outer_route": True, "waypoint_axis": "y", "waypoint_value": .82})
        scene = structure_scene.prepare(plan)
        self.assert_clear(plan, scene)
        self.assertEqual([(r["source"], r["target"], r["members"]) for r in scene["routes"]], [("a", "b", [0]), ("b", "a", [1])])
        forward, returning = scene["routes"]
        self.assertEqual(len(forward["points"]), 2)
        self.assertTrue(any(abs(p[1] - .82) < .005 for p in returning["points"]), returning)
        self.assertNotEqual(forward["points"][0], returning["points"][-1])
        self.assertNotEqual(forward["points"][-1], returning["points"][0])
        for route in scene["routes"]:
            self.assertFalse(route.get("bidirectional"))
            self.assert_compact(pixels(scene, route), minimum_interior=8)

    def test_heterogeneous_owner_join_uses_direct_data_and_distinct_fanin(self):
        for variant in ("original", "renamed", "reordered"):
            with self.subTest(variant=variant):
                payload = source("heterogeneous-instrument")
                ids = {nid: nid for nid in ("fast", "slow", "common", "external")}
                if variant != "original":
                    payload, ids = renamed(payload, reverse=variant == "reordered")
                result, figure, plan, scene = compiled(payload)
                self.assert_projected_truth(payload, result, figure, plan, scene)
                self.assert_clear(plan, scene, figure)
                self.assert_independent_ports(scene)
                incoming = [r for r in scene["routes"] if r["kind"] == "data" and r["target"] == ids["common"]]
                self.assertEqual(len(incoming), 2)
                self.assertGreater(math.dist(*[pixels(scene, r)[-1] for r in incoming]), 40)
                for route in scene["routes"]:
                    self.assert_compact(pixels(scene, route), minimum_interior=8)
                    if (route["source"], route["target"]) in ((ids["fast"], ids["common"]), (ids["common"], ids["external"])):
                        self.assertEqual(len(route["points"]), 2, route)
                paths = [pixels(scene, r) for r in incoming]
                self.assertFalse(any(share_segment(a, b, c, d) for a, b in zip(paths[0], paths[0][1:])
                                     for c, d in zip(paths[1], paths[1][1:])), incoming)

    def test_repeated_ingress_data_trunk_is_clear_of_control_only_branch(self):
        for variant in ("original", "renamed", "reordered"):
            with self.subTest(variant=variant):
                payload = source("repeated-ingress")
                ids = {nid: nid for nid in ("arb", "classifier", "outputq", "manage")}
                if variant != "original":
                    payload, ids = renamed(payload, reverse=variant == "reordered")
                result, figure, plan, scene = compiled(payload)
                self.assert_projected_truth(payload, result, figure, plan, scene)
                self.assert_clear(plan, scene, figure)
                self.assert_independent_ports(scene)
                for route in scene["routes"]:
                    self.assert_compact(pixels(scene, route), minimum_interior=8)
                    if (route["source"], route["target"]) in ((ids["arb"], ids["classifier"]), (ids["classifier"], ids["outputq"])):
                        self.assertLessEqual(len(route["points"]), 4, route)
                        points = pixels(scene, route)
                        manhattan = abs(points[-1][0] - points[0][0]) + abs(points[-1][1] - points[0][1])
                        self.assertAlmostEqual(sum(math.dist(a, b) for a, b in zip(points, points[1:])), manhattan, delta=EPS)
                fanin = [r for r in scene["routes"] if r["target"] == ids["arb"] and r["kind"] == "data"]
                self.assertEqual(len(fanin), 4)
                self.assertEqual(len({tuple(r["points"][-1]) for r in fanin}), 4)
                for first, path in enumerate([pixels(scene, r) for r in fanin]):
                    for other in fanin[first + 1:]:
                        other_points = pixels(scene, other)
                        self.assertFalse(any(share_segment(a, b, c, d) for a, b in zip(path, path[1:])
                                             for c, d in zip(other_points, other_points[1:])), (fanin[first], other))

    def test_process_branch_returns_and_hold_loops_keep_exact_source_edges(self):
        for name in ("branched-tile-return", "elastic-pipeline", "retry-controller"):
            with self.subTest(case=name):
                payload, _ = renamed(source(name))
                result, figure, plan, scene = compiled(payload)
                self.assertEqual(result["spec"], payload["spec"])
                self.assertCountEqual([r["members"][0] for r in scene["routes"]], range(len(payload["spec"]["edges"])))
                for route in scene["routes"]:
                    index = route["members"][0]
                    original = payload["spec"]["edges"][index]
                    for field in ("source", "target", "kind", "label"):
                        self.assertEqual(route[field], original[field])
                    self.assertFalse(route.get("bidirectional"))
                    points = pixels(scene, route) if "width" in scene else route["points"]
                    self.assert_compact(points, orthogonal=plan.get("grammar") != "state-machine")
                    if route["source"] == route["target"]:
                        self.assertGreater(len(route["points"]), 2, route)
                # A resource receiving ready and emitting upstream ready must
                # retain separate endpoint coordinates, rather than a bypass.
                if name == "elastic-pipeline":
                    for node in payload["spec"]["nodes"]:
                        arriving = [r for r in scene["routes"] if r["kind"] == "control" and r["target"] == node["id"]]
                        departing = [r for r in scene["routes"] if r["kind"] == "control" and r["source"] == node["id"]]
                        for a in arriving:
                            for b in departing:
                                self.assertGreater(math.dist(a["points"][-1], b["points"][0]), 10)

    def test_logical_topology_has_only_explicit_links_and_keeps_opposite_senses(self):
        spec = engine.normalize_spec({"title": "Independent logical link holdout", "category": "memory", "groups": [],
            "nodes": [{"id": nid, "label": "Router " + nid, "kind": "control", "group": "", "detail": "Logical position " + coordinate}
                      for nid, coordinate in (("rA", "0,0"), ("rB", "1,0"), ("rC", "1,1"))],
            "edges": [{"source": a, "target": b, "kind": kind, "label": label}
                      for a, b, kind, label in (("rA", "rB", "data", "request"), ("rB", "rA", "data", "reply"),
                                                ("rB", "rC", "data", "forward"), ("rC", "rC", "feedback", "local retry"))]})
        base = copy.deepcopy(spec)
        figure = behavior_guide.primary(spec)
        outcome = behavior_guide.build(spec, figure, {"style": "paper"})
        self.assertIsNotNone(outcome)
        self.assertEqual(spec, base)
        routes = outcome["layout_scene"]["routes"]
        self.assertEqual(len(routes), 4)
        self.assertEqual({(r["source"], r["target"]) for r in routes}, {("rA", "rB"), ("rB", "rA"), ("rB", "rC"), ("rC", "rC")})
        for index, route in enumerate(routes):
            self.assertEqual(route["members"], [index])
            self.assertFalse(route.get("bidirectional"))
            self.assert_compact(route["points"])
            if route["source"] != route["target"]:
                self.assertEqual(len(route["points"]), 2)
        self.assertNotEqual(routes[0]["points"], list(reversed(routes[1]["points"])))


if __name__ == "__main__":
    unittest.main()
