import copy
from collections import Counter
import unittest

from silicon_canvas import engine


def sample():
    return {
        "title": "DMA dataflow", "summary": "DMA 将数据搬到 Buffer，再送入 MAC。", "category": "dataflow",
        "groups": [{"id": "g", "label": "NPU"}],
        "nodes": [{"id": "dma", "label": "DMA", "kind": "io", "group": "", "detail": ""}, {"id": "buf", "label": "Buffer", "kind": "memory", "group": "g", "detail": ""}, {"id": "mac", "label": "MAC", "kind": "compute", "group": "g", "detail": ""}],
        "edges": [{"source": "dma", "target": "buf", "label": "payload[31:0]", "kind": "data"}, {"source": "buf", "target": "mac", "label": "", "kind": "data"}, {"source": "mac", "target": "buf", "label": "ready=1", "kind": "control"}],
        "layout": "Main path left to right; control lane below.", "steps": [], "annotations": [],
        "assumptions": [], "questions": ["Buffer 容量未指定。"], "checks": ["核对 ready 方向。"]
    }


class EngineTests(unittest.TestCase):
    def test_automatic_planning_offers_views_without_user_form_fields(self):
        import json
        messages, _ = engine.prepare_request({"description": "完整的 GPU 架构"})
        planning = json.loads(messages[1]["content"])["figure_planning"]
        self.assertEqual(set(planning["view_patterns"]), set(engine.CATEGORIES))
        messages, _ = engine.prepare_request({"description": "缓存层级", "category": "memory"})
        self.assertEqual(set(json.loads(messages[1]["content"])["figure_planning"]["view_patterns"]), {"memory"})

    def test_crowded_graph_keeps_every_edge_and_warns_about_hub_routing(self):
        spec = sample()
        for index in range(9):
            spec["nodes"].append({"id": f"unit{index}", "label": f"Unit {index}", "kind": "compute"})
            spec["edges"].append({"source": "dma", "target": f"unit{index}", "kind": "data", "label": f"stream{index}"})
        before = copy.deepcopy(spec)
        result = engine.compile_manual({"spec": spec, "settings": {"density": "low"}})
        self.assertEqual(spec, before)
        self.assertEqual(result["spec"], engine.normalize_spec(before))
        self.assertTrue(any("DMA" in warning and "连线集中" in warning for warning in result["warnings"]))
        self.assertEqual(result["render_plan"]["strategy"], "atlas")
        self.assertEqual(result["render_plan"]["coverage"]["missing_edges"], [])
        exact = [f for f in result["figures"] if not f["abstract"]]
        self.assertTrue(exact)
        self.assertTrue(all(f["node_count"] <= 8 for f in exact))
        self.assertTrue(all(len(f["edge_indices"]) <= 12 for f in exact))
        self.assertEqual(Counter(i for f in exact for i in f["edge_indices"]), Counter(range(len(before["edges"]))))
        self.assertEqual(sum(bool(f["primary"]) for f in result["figures"]), 1)
        for f in result["figures"]:
            self.assertEqual(f["design_contract"]["target_width_mm"], 160)
            self.assertEqual(f["design_contract"]["body_pt"], 9)
            if f["layout_strategy"] == "text-only":
                self.assertFalse(f["requires_layout_guide"])
                self.assertEqual(f["generation_inputs"], [])
                self.assertIn("without a reviewed layout plate", f["prompt"])
            for index in f["edge_indices"]:
                edge = result["spec"]["edges"][index]
                self.assertIn(edge["source"], f["node_ids"])
                self.assertIn(edge["target"], f["node_ids"])
        prompts = "\n".join(f["prompt"] for f in result["figures"])
        for index in range(9):
            self.assertIn(f'"stream{index}"', prompts)

    def test_unconnected_overview_does_not_gain_connections_or_hubs(self):
        spec = sample()
        spec["category"] = "architecture"
        spec["edges"] = []
        result = engine.compile_manual({"spec": spec})
        self.assertEqual(result["spec"]["edges"], [])
        self.assertNotIn("Routing hotspots:", result["prompt"])
        self.assertIn("No relationship is supplied in this view. Add no arrows.", result["prompt"])
        self.assertEqual(result["render_plan"]["coverage"]["edges_total"], 0)
        for figure in result["figures"]:
            self.assertEqual(figure["edge_indices"], [])
            self.assertEqual(figure.get("macro_edges", []), [])
            self.assertEqual(figure.get("layout_scene", {}).get("routes", []), [])

    def test_public_taxonomy_groups_internal_diagram_grammars(self):
        families = {item["id"] for item in engine.CATALOG["families"]}
        self.assertEqual(families, {"structure", "flow", "behavior", "timing"})
        self.assertTrue(all(item.get("family") in families for item in engine.CATALOG["categories"]))

    def test_edges_labels_and_review_separation_survive_compilation(self):
        result = engine.compile_manual({"spec": sample(), "settings": {"category": "dataflow"}})
        figure=result['figures'][0]
        self.assertTrue(any(e['source']=='mac' and e['target']=='buf' and e['kind']=='control' for e in figure['layout_scene']['routes']))
        self.assertIn('dashed control, clock or recovery lines', result['prompt'])
        self.assertIn('"MAC" -> "Buffer" [control]; meaning "ready=1"', result['prompt'])
        self.assertEqual(figure['structure_layout']['source_ownership'], {'dma': '', 'buf': 'g', 'mac': 'g'})
        self.assertCountEqual([index for route in figure['layout_scene']['routes'] for index in route['members']], [0, 1, 2])
        self.assertIn('"Buffer" — memory; belongs to "NPU"', result['prompt'])
        self.assertIn('"MAC" — compute; belongs to "NPU"', result['prompt'])
        self.assertIn('"payload[31:0]"', result["prompt"])
        self.assertEqual({entry['text'] for entry in figure['label_layout']['labels']}, {'payload[31:0]', 'ready=1'})
        for edge in result['spec']['edges']:
            by_id = {node['id']: node['label'] for node in result['spec']['nodes']}
            original = by_id[edge['source']] + ' → ' + by_id[edge['target']] + (': ' + edge['label'] if edge['label'] else '') + ' [' + edge['kind'] + ']'
            self.assertIn(original, figure['caption'])
        self.assertNotIn("Buffer 容量未指定", result["prompt"])
        self.assertEqual(result["spec"]["questions"], ["Buffer 容量未指定。"])

    def test_invalid_references_and_duplicate_ids_rejected(self):
        spec = sample()
        spec["edges"][0]["target"] = "missing"
        with self.assertRaises(ValueError):
            engine.normalize_spec(spec)
        spec = sample()
        spec["nodes"].append(copy.deepcopy(spec["nodes"][0]))
        with self.assertRaises(ValueError):
            engine.normalize_spec(spec)

    def test_locked_revision_cannot_change_technical_facts_or_style(self):
        previous = engine.compile_manual({"spec": sample(), "settings": {"category": "dataflow", "style": "paper"}, "description": "DMA → Buffer → MAC"})
        _, context = engine.prepare_request({"description": "irrelevant new text", "style": "signal", "feedback": "扩大模块间距", "previous": previous, "lock_structure": True})
        changed = sample()
        changed["nodes"][0]["label"] = "WRONG"
        changed["edges"].pop()
        changed["steps"] = ["Invented behavior"]
        changed["layout"] = "Increase the gap between blocks."
        result = engine.finish_request(changed, context)
        self.assertEqual(result["spec"]["nodes"], previous["spec"]["nodes"])
        self.assertEqual(result["spec"]["edges"], previous["spec"]["edges"])
        self.assertEqual(result["spec"]["steps"], [])
        self.assertEqual(result["style_fingerprint"], previous["style_fingerprint"])
        self.assertEqual(result["description"], previous["description"])
        self.assertEqual(result["spec"]["layout"], changed["layout"])

    def test_unlocked_revision_applies_explicit_semantic_changes(self):
        previous = engine.compile_manual({"spec": sample(), "settings": {"category": "dataflow"}})
        _, context = engine.prepare_request({"description": "DMA → Buffer → MAC", "feedback": "将 MAC 标签改成 PE", "previous": previous, "lock_structure": False})
        changed = sample()
        changed["nodes"][2]["label"] = "PE"
        result = engine.finish_request(changed, context)
        self.assertEqual(result["spec"]["nodes"][2]["label"], "PE")

    def test_style_and_compilation_are_deterministic(self):
        payload = {"spec": sample(), "settings": {"category": "dataflow", "style": "signal"}}
        first = engine.compile_manual(payload)
        second = engine.compile_manual(payload)
        self.assertEqual(first["prompt"], second["prompt"])
        changed = sample()
        changed["title"] = "Another figure"
        third = engine.compile_manual({**payload, "spec": changed})
        self.assertEqual(first["style_fingerprint"], third["style_fingerprint"])

    def test_unknown_values_and_bad_structure_are_rejected(self):
        for payload in ({"style": "unknown"}, {"labels": 42}, {"category": []}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                engine.normalize_settings(payload)
        with self.assertRaises(ValueError):
            engine.normalize_spec({"title": "No nodes", "category": "architecture"})

    def test_missing_exact_label_is_actionable_warning_not_invented_hardware(self):
        result = engine.compile_manual({"spec": sample(), "settings": {"category": "dataflow", "labels": "UNSPECIFIED"}})
        self.assertTrue(any("UNSPECIFIED" in warning for warning in result["warnings"]))
        self.assertEqual(len(result["spec"]["nodes"]), 3)

    def test_timing_events_preserved_without_guessing_later_cycles(self):
        spec = sample()
        spec["category"] = "timing"
        spec["steps"] = ["C1: valid=1, ready=0, data=A", "C2: valid=1, ready=1, data=A; transfer"]
        result = engine.compile_manual({"spec": spec, "settings": {"category": "timing"}})
        self.assertIn(spec["steps"][0], result["prompt"])
        self.assertIn(spec["steps"][1], result["prompt"])
        self.assertTrue(any("逐周期" in warning for warning in result["warnings"]))

    def test_nested_groups_supported_and_cycles_rejected(self):
        spec = sample()
        spec["groups"].append({"id": "soc", "label": "SoC"})
        spec["groups"][0]["parent"] = "soc"
        result = engine.compile_manual({"spec": spec, "settings": {"category": "architecture"}})
        layout = result['figures'][0]['structure_layout']
        containers={cap['id']:cap for cap in layout['containers']}
        # CPS6 separates source ancestry from optional visible scope outlines;
        # hiding an overcrowded title must never flatten the source ownership.
        parents = layout.get('source_group_parents') or {gid: cap['parent'] for gid, cap in containers.items()}
        self.assertEqual(parents, {'g': 'soc', 'soc': ''})
        self.assertEqual(layout['source_ownership'], {'dma': '', 'buf': 'g', 'mac': 'g'})
        self.assertEqual(set(containers['g']['members']), {'buf', 'mac'})
        self.assertEqual(set(containers['soc']['members']), {'buf', 'mac'})
        self.assertIn('Scope "SoC"',result['prompt'])
        self.assertIn('Scope "NPU"; original parent "SoC"', result['prompt'])
        self.assertEqual(result['spec']['groups'], engine.normalize_spec(spec)['groups'])
        spec["groups"][1]["parent"] = "g"
        with self.assertRaises(ValueError):
            engine.normalize_spec(spec)

    def test_evidence_is_not_a_visible_exact_label(self):
        spec = sample()
        spec["nodes"][0]["evidence"] = "SecretLabel"
        result = engine.compile_manual({"spec": spec, "settings": {"category": "dataflow", "labels": "SecretLabel"}})
        self.assertTrue(any("SecretLabel" in warning for warning in result["warnings"]))
        spec["nodes"][0]["group"] = []
        with self.assertRaises(ValueError):
            engine.normalize_spec(spec)
        with self.assertRaises(ValueError):
            engine.normalize_spec({"category": []})

    def test_fsm_unconditional_exit_with_self_loop_is_flagged(self):
        spec = sample()
        spec["edges"] = [{"source": "mac", "target": "dma", "label": "unconditional next cycle", "kind": "control"}, {"source": "mac", "target": "mac", "label": "otherwise", "kind": "control"}]
        result = engine.compile_manual({"spec": spec, "settings": {"category": "fsm"}})
        self.assertTrue(any("无条件出边和自循环" in warning for warning in result["warnings"]))

    def test_short_intent_defaults_to_smart_completion_with_visible_provenance(self):
        messages, context = engine.prepare_request({"description": "完整的一个Soc系统"})
        self.assertEqual(context["settings"]["completion_mode"], "auto")
        self.assertEqual(context["settings"]["category"], "auto")
        import json
        request = json.loads(messages[1]["content"])
        self.assertIn("starter_guidance", request)
        self.assertEqual(len(request["category_candidates"]), 8)
        self.assertTrue(all(item.get("rules") for item in request["category_candidates"]))
        result = engine.finish_request(sample(), context)
        self.assertEqual(result["settings"]["category"], "dataflow")
        self.assertEqual(result["completion_summary"]["assumed_nodes"], 3)
        self.assertEqual(result["completion_summary"]["assumed_edges"], 3)
        self.assertTrue(result["spec"]["assumptions"])
        for section in ("nodes", "edges", "groups"):
            self.assertTrue(all(item["origin"] == "assumed" and item["rationale"] and item["evidence"] == "" for item in result["spec"][section]))
        self.assertEqual(result["figures"][0]["caption"].count("[assumed coordination example]"), len(result["spec"]["edges"]))
        self.assertNotIn(result["spec"]["assumptions"][0], result["prompt"])
        self.assertIn('"DMA" -> "Buffer" [data]', result["prompt"])
        self.assertFalse(any("缺少可直接匹配输入" in warning for warning in result["warnings"]))
        self.assertTrue(all(node["origin"] == "assumed" for node in result["spec"]["nodes"]))

    def test_explicit_verbatim_labels_are_merged_into_prompt_checks(self):
        spec = sample()
        spec["verbatim_labels"] = ["DMA", "payload[31:0]"]
        result = engine.compile_manual({"spec": spec, "settings": {"category": "auto"}})
        self.assertEqual(result["settings"]["category"], "dataflow")
        self.assertEqual(result["spec"]["verbatim_labels"], spec["verbatim_labels"])
        self.assertEqual(result["figures"][0]["required_verbatim_labels"], spec["verbatim_labels"])
        self.assertIn('Mandatory verbatim text, only on its matching supplied object:', result["prompt"])
        self.assertIn('"DMA"; "payload[31:0]"', result["prompt"])
        self.assertIn('payload[31:0]', {item['text'] for item in result['figures'][0]['label_layout']['labels']})
        self.assertEqual(result['spec']['nodes'], engine.normalize_spec(sample())['nodes'])
        self.assertFalse(any("精确标签尚未映射到结构" in warning for warning in result["warnings"]))

    def test_wrapped_text_items_from_model_are_normalized(self):
        spec = sample()
        spec["steps"] = [{"label": "C0: valid=1"}]
        spec["annotations"] = [{"text": "C2 transfer"}]
        normalized = engine.normalize_spec(spec)
        self.assertEqual(normalized["steps"], ["C0: valid=1"])
        self.assertEqual(normalized["annotations"], ["C2 transfer"])

    def test_model_cannot_promote_ordinary_terms_to_verbatim_labels(self):
        spec = sample()
        spec["verbatim_labels"] = ["DMA", "MAC"]
        _, context = engine.prepare_request({"description": "DMA 输入到 MAC", "category": "auto"})
        result = engine.finish_request(spec, context)
        self.assertEqual(result["spec"]["verbatim_labels"], [])

        _, context = engine.prepare_request({"description": "DMA 输入到 MAC", "category": "auto", "notes": "MAC 必须原样保留"})
        result = engine.finish_request(spec, context)
        self.assertEqual(result["spec"]["verbatim_labels"], ["MAC"])

    def test_given_evidence_and_assumed_parts_stay_distinct(self):
        _, context = engine.prepare_request({"description": "DMA 输入到 Buffer，后面帮我补完整", "category": "dataflow"})
        spec = sample()
        spec["nodes"][0]["evidence"] = "DMA 输入到 Buffer"
        spec["nodes"][1]["evidence"] = "DMA 输入到 Buffer"
        spec["edges"][0]["evidence"] = "DMA 输入到 Buffer"
        result = engine.finish_request(spec, context)
        self.assertEqual([n["origin"] for n in result["spec"]["nodes"]], ["given", "given", "assumed"])
        self.assertEqual(result["completion_summary"]["assumed_nodes"], 1)
        self.assertEqual(result["spec"]["nodes"][2]["evidence"], "")

    def test_assumptions_survive_local_recompile_and_locked_revision(self):
        _, context = engine.prepare_request({"description": "做一个数据流", "category": "dataflow"})
        previous = engine.finish_request(sample(), context)
        local = engine.compile_manual({"spec": previous["spec"], "settings": previous["settings"]})
        self.assertEqual(local["completion_summary"], previous["completion_summary"])
        _, revision = engine.prepare_request({"description": "做一个数据流", "feedback": "增加间距", "previous": previous})
        result = engine.finish_request(sample(), revision)
        self.assertEqual(result["spec"]["nodes"], previous["spec"]["nodes"])
        self.assertEqual(result["spec"]["assumptions"], previous["spec"]["assumptions"])
        self.assertEqual(result["style_fingerprint"], previous["style_fingerprint"])

    def test_strict_mode_does_not_accept_suggested_technical_structure(self):
        _, context = engine.prepare_request({"description": "DMA 输入到 Buffer", "category": "dataflow", "completion_mode": "strict"})
        spec = sample()
        spec["nodes"][2]["origin"] = "assumed"
        with self.assertRaises(ValueError):
            engine.finish_request(spec, context)
        with self.assertRaises(ValueError):
            engine.normalize_settings({"completion_mode": "invalid"})

    def test_repair_retains_explicit_user_scope_and_mode(self):
        description = "只画 CPU、SRAM，不要 NPU，也不要加连线"
        messages, context = engine.prepare_request({"description": description, "completion_mode": "strict"})
        repaired = engine.prepare_repair(messages, {"nodes": []}, context, ValueError("empty nodes"))
        self.assertEqual(repaired[:2], messages)
        self.assertIn("STRICT mode still applies", repaired[-1]["content"])
        self.assertEqual(len(repaired), 4)

    def test_strict_rejects_unattributed_nodes_even_if_origin_omitted(self):
        _, context = engine.prepare_request({"description": "DMA 输入到 Buffer", "category": "dataflow", "completion_mode": "strict"})
        with self.assertRaises(ValueError):
            engine.finish_request(sample(), context)

    def test_legacy_revision_keeps_strict_unless_user_chooses_auto(self):
        previous = engine.compile_manual({"spec": sample(), "settings": {"category": "dataflow"}})
        previous["settings"].pop("completion_mode")
        payload = {"description": "DMA 输入到 Buffer", "feedback": "增加间距", "previous": previous}
        _, context = engine.prepare_request(payload)
        self.assertEqual(context["settings"]["completion_mode"], "strict")
        _, context = engine.prepare_request({**payload, "completion_mode": "auto"})
        self.assertEqual(context["settings"]["completion_mode"], "auto")

    def test_layout_mention_does_not_promote_assumption_to_given(self):
        _, context = engine.prepare_request({"description": "一个数据流", "category": "dataflow"})
        previous = engine.finish_request(sample(), context)
        changed = copy.deepcopy(previous["spec"])
        changed["nodes"][0].update(origin="given", evidence="DMA", rationale="")
        changed["layout"] = "Place DMA on the left."
        _, revision = engine.prepare_request({"description": "一个数据流", "feedback": "把 DMA 移到左边", "previous": previous, "lock_structure": False})
        result = engine.finish_request(changed, revision)
        self.assertEqual(result["spec"]["nodes"][0]["origin"], "assumed")
        self.assertEqual(result["spec"]["nodes"][0]["rationale"], previous["spec"]["nodes"][0]["rationale"])

    def test_generated_fsm_does_not_use_signal_as_transition_source(self):
        _, context = engine.prepare_request({"description": "画一个 DMA 状态机", "category": "fsm"})
        spec = sample()
        spec["nodes"][0].update(label="start", kind="event")
        with self.assertRaises(ValueError):
            engine.finish_request(spec, context)


if __name__ == "__main__":
    unittest.main()
