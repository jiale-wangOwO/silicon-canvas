"""Independent evaluation oracle tests; no live network or golden pixels."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

from silicon_canvas import engine

ROOT=Path(__file__).resolve().parents[1]
_module=importlib.util.spec_from_file_location("generalization_eval",ROOT/"scripts/generalization_eval.py")
evaluation=importlib.util.module_from_spec(_module)
_module.loader.exec_module(evaluation)
_stress_module=importlib.util.spec_from_file_location("generalization_stress",ROOT/"scripts/generalization_stress.py")
stress=importlib.util.module_from_spec(_stress_module)
_stress_module.loader.exec_module(stress)


class GeneralizationEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases={c["id"]:c for c in evaluation.load_cases("development",True)}
        cls.camera=cls.cases["fresh-02-camera"]
        cls.result=engine.compile_manual(copy.deepcopy(cls.camera["manual_payload"]))

    def test_development_and_variant_inputs_match_frozen_hashes(self):
        self.assertEqual(len(self.cases),12)
        self.assertTrue(all(c["split"]=="development" for c in self.cases.values()))

    def test_authored_source_checks_do_not_claim_semantic_or_pixel_acceptance(self):
        self.assertEqual(evaluation.software_contract(self.camera["manual_payload"]["spec"],self.result),[])
        proxy=evaluation.proxies(self.result)
        self.assertTrue(proxy["software_proxy_only"])
        self.assertEqual(proxy["imagegen_visual_acceptance"],"not_run")

    def test_natural_input_contract_accepts_id_and_container_title_changes(self):
        changed=copy.deepcopy(self.result)
        changed["spec"]["groups"][0]["label"]="On-Chip Resources"
        self.assertEqual(evaluation.semantic_contract(self.camera,changed),[])

    def test_real_producer_consumer_direction_error_is_detected(self):
        changed=copy.deepcopy(self.result)
        edge=changed["spec"]["edges"][0]
        edge["source"],edge["target"]=edge["target"],edge["source"]
        self.assertIn("relation:sensor->isp:data",evaluation.semantic_contract(self.camera,changed))

    def test_external_endpoint_cannot_be_absorbed_under_internal_owner(self):
        changed=copy.deepcopy(self.result)
        next(n for n in changed["spec"]["nodes"] if n["id"]=="host")["group"]="chip"
        failures=evaluation.semantic_contract(self.camera,changed)
        self.assertTrue(any(f.startswith("owner:") or f.startswith("external_scope:") for f in failures))

    def test_substring_matching_does_not_confuse_host_and_host_interface(self):
        found=evaluation.matching_nodes({"nodes":[{"id":"a","label":"Host Interface"},{"id":"b","label":"Host"}]},[{"concept":"host","pattern":"Host"},{"concept":"hi","pattern":"Host Interface"}])
        self.assertEqual(found["host"]["id"],"b")
        self.assertEqual(found["hi"]["id"],"a")

    def test_verbatim_evidence_error_is_not_excused_by_correct_graph(self):
        changed=copy.deepcopy(self.result)
        changed["spec"]["nodes"][0]["evidence"]="A plausible paraphrase that the user never wrote"
        self.assertIn("given_evidence:nodes",evaluation.semantic_contract(self.camera,changed))

    def test_closed_inventory_detects_extra_event_node(self):
        changed=copy.deepcopy(self.result)
        changed["spec"]["nodes"].append({**changed["spec"]["nodes"][0],"id":"extra","label":"extra"})
        self.assertIn("closed_node_inventory",evaluation.semantic_contract(self.camera,changed))

    def test_boolean_predicate_oracle_accepts_equivalence_and_rejects_priority_change(self):
        self.assertTrue(evaluation.predicates_equal("!error && stop","stop && !error"))
        self.assertTrue(evaluation.predicates_equal("unconditional",""))
        self.assertTrue(evaluation.predicates_equal("(unconditional)",""))
        self.assertTrue(evaluation.predicates_equal("always","1"))
        self.assertFalse(evaluation.predicates_equal("error || stop","!error && stop"))
        self.assertFalse(evaluation.predicates_equal("__import__('os').system('x')","true"))

    def test_metamorphics_do_not_mutate_the_frozen_source(self):
        before=copy.deepcopy(self.camera)
        variants=list(evaluation.metamorphics(self.camera))
        self.assertEqual(len(variants),4)
        self.assertEqual(self.camera,before)
        for name,payload in variants:
            with self.subTest(transformation=name):
                result=engine.compile_manual(payload)
                self.assertEqual(evaluation.software_contract(payload["spec"],result),[])

    def test_selected_endpoint_paths_cannot_be_replaced_by_ledger_retention(self):
        class Guide:
            @staticmethod
            def render(result,figure):return b"audit-guide"
        normal=stress.view_metrics(self.camera,self.result,Guide)
        self.assertEqual(normal["selected_exact_endpoint_source_edges"],5)
        changed=copy.deepcopy(self.result)
        evaluation.chosen(changed)["layout_scene"]["routes"]=[]
        folded=stress.view_metrics(self.camera,changed,Guide)
        self.assertTrue(folded["source_ledger_retained"])
        self.assertEqual(folded["selected_exact_endpoint_source_edges"],0)
        self.assertEqual(folded["selected_unrouted_or_deferred_source_edges"],5)
        self.assertIn("primary_not_complete_endpoint_mechanism",folded["limitations"])


if __name__=="__main__":unittest.main()
