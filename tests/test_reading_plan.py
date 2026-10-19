import copy
import json
from pathlib import Path
import unittest
from silicon_canvas import presentation
from silicon_canvas import reading_plan

BASE = Path(__file__).resolve().parents[1] / "tests/fixtures/publication_benchmark"


def sample(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


class ReadingPlanTests(unittest.TestCase):
    def test_one_declared_repeated_group_is_not_expanded_into_invented_instances(self):
        r = sample("engine-release-cps5.json")
        r["spec"]["category"] = "architecture"
        r["spec"]["groups"] = [{"id": "front", "label": "Command Front End", "parent": ""},
                                {"id": "cluster", "label": "Compute Cluster (x4)", "parent": ""}]
        r["spec"]["nodes"] = [
            {"id": "command", "label": "Command Processor", "kind": "control", "group": "front", "detail": ""},
            {"id": "dispatch", "label": "Dispatcher", "kind": "control", "group": "front", "detail": ""},
            {"id": "simd", "label": "SIMD", "kind": "compute", "group": "cluster", "detail": ""},
            {"id": "tensor", "label": "Tensor", "kind": "compute", "group": "cluster", "detail": ""}]
        r["spec"]["edges"] = [
            {"source": "command", "target": "dispatch", "kind": "control", "label": "launch"},
            {"source": "dispatch", "target": "simd", "kind": "control", "label": "workgroups x4"},
            {"source": "dispatch", "target": "tensor", "kind": "control", "label": "workgroups x4"}]
        before = copy.deepcopy(r["spec"])
        p = self.build(r)
        f = p["figures"][0]
        self.assertEqual(f["design_contract"]["grammar"], "ownership-flow")
        self.assertEqual(r["spec"], before)
        self.assertEqual(len(f["macro_nodes"]), 2)
        owner = next(o for o in f["macro_nodes"] if o["id"] == "cluster")
        self.assertEqual(owner["label"], "Compute Cluster (x4)")
        self.assertEqual(owner["members"], ["simd", "tensor"])
        self.assertEqual(len(owner["children"]), 2)
        self.assertEqual(f["projection"]["internal_edges"], [0])
        self.assertEqual(f["macro_edges"][0]["label"], "workgroups x4")
        exact = [i for x in p["figures"] if not x["abstract"] for i in x["edge_indices"]]
        self.assertCountEqual(exact, [0, 1, 2])

    def test_different_numeric_leaf_streams_cannot_be_silently_folded(self):
        r = sample("engine-release-cps5.json")
        incoming = [e for e in r["spec"]["edges"] if e["kind"] == "data" and e["target"] in {"n_alu", "n_sfu"}]
        self.assertGreaterEqual(len(incoming), 2)
        for e in incoming:
            e["label"] = "32-bit" if e["target"] == "n_alu" else "64-bit"
        f = self.build(r)["figures"][0]
        self.assertEqual(f["projection"]["folded_groups"], [])
        self.assertTrue(any(e["label"] == "32-bit" for e in f["macro_edges"]))
        self.assertTrue(any(e["label"] == "64-bit" for e in f["macro_edges"]))

    def build(self, result):
        s = result["spec"]
        return reading_plan.build(s, result["settings"], presentation.build_plan(s, result["settings"]["density"], result["settings"]["language"]))

    def test_primary_true_group_projection_does_not_modify_source_or_lose_annex(self):
        r = sample("engine-release-cps5.json")
        before = copy.deepcopy(r["spec"])
        p = self.build(r)
        f = p["figures"][0]
        self.assertEqual(r["spec"], before)
        self.assertEqual(f["id"], "execution")
        self.assertTrue(f["abstract"])
        self.assertEqual(f["projection"]["folded_groups"], ["g_fpu"])
        actual = [i for e in f["macro_edges"] for i in e["members"]] + f["projection"]["internal_edges"]
        self.assertCountEqual(actual, f["source_edge_indices"])
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(len(actual), 14)
        exact = [i for x in p["figures"] if not x["abstract"] for i in x["edge_indices"]]
        self.assertCountEqual(exact, range(22))
        self.assertEqual(len(exact), 22)
        self.assertEqual(p["reading_plan"]["source_hash"], reading_plan.source_hash(before))

    def test_explicit_internal_dependency_is_not_replaced_by_unordered_inventory(self):
        r = sample("engine-release-cps5.json")
        r["spec"]["edges"].append({"source": "n_alu", "target": "n_sfu", "kind": "data", "label": "ordered"})
        f = self.build(r)["figures"][0]
        self.assertEqual(f["projection"]["folded_groups"], [])
        self.assertIn("n_alu", {n["id"] for n in f["macro_nodes"]})
        self.assertTrue(any(e["source"]=="n_alu" and e["target"]=="n_sfu" for e in f["macro_edges"]))

    def test_rename_and_source_order_do_not_bind_the_strategy_to_a_chip_or_model(self):
        r = sample("engine-release-cps5.json")
        rename = {n["id"]: "renamed_"+str(i) for i,n in enumerate(r["spec"]["nodes"])}
        for n in r["spec"]["nodes"]:
            n["id"] = rename[n["id"]]
            n["label"] = "Resource " + n["id"]
        for e in r["spec"]["edges"]:
            e["source"],e["target"] = rename[e["source"]],rename[e["target"]]
        r["spec"]["title"] = "Unbranded resource flow"
        f = self.build(r)["figures"][0]
        self.assertEqual(f["design_contract"]["grammar"], "folded-flow")
        self.assertTrue(f["projection"]["folded_groups"])

    def test_repeated_resource_overview_expands_only_the_real_representative(self):
        r = sample("gpu-release-cps5.json")
        before = copy.deepcopy(r["spec"])
        f = self.build(r)["figures"][0]
        self.assertEqual(r["spec"], before)
        self.assertEqual(f["design_contract"]["grammar"], "resource-array")
        populated = [o for o in f["macro_nodes"] if o["children"]]
        peers = [o for o in f["macro_nodes"] if o.get("equivalent_to")]
        self.assertEqual(len(populated), 1)
        self.assertEqual(len(populated[0]["children"]), 4)
        self.assertEqual(len(peers), 3)
        self.assertTrue(all(not o["children"] and o["equivalent_to"]==populated[0]["id"] for o in peers))

    def test_exact_parallel_conditions_remain_distinct_and_no_reverse_is_invented(self):
        s = {"edges":[{"source":"a","target":"b","kind":"control","label":"valid"},
                      {"source":"a","target":"b","kind":"control","label":"flush"}]}
        links,internal = reading_plan._project_edges(s,[0,1],{"a":"a","b":"b"})
        self.assertEqual(len(links),2)
        self.assertFalse(any(e.get("bidirectional") for e in links))
        self.assertEqual(internal,[])


if __name__ == "__main__":
    unittest.main()
