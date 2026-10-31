import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from extract_apk_flows import action_kind, scan_embedded, template_graph, trace_navigation
from render_apk_flow_report import render


def instruction(offset, name, registers=(), reference=None, extra=()):
    operands = [(0, value) for value in registers]
    if reference is not None:
        operands.append((256, 0, reference))
    operands.extend(extra)
    return offset, name, operands, str(reference or "")


class FlowEvidenceTests(unittest.TestCase):
    def test_arouter_fluent_call_requires_navigation_to_count_as_launch(self):
        instructions = [
            instruction(0, "const-string", [1], "/orders/list"),
            instruction(2, "invoke-virtual", [0, 1], "Lcom/alibaba/android/arouter/launcher/ARouter;->build(Ljava/lang/String;)Lcom/alibaba/android/arouter/facade/Postcard;"),
            instruction(8, "move-result-object", [2]),
            instruction(10, "invoke-virtual", [2], "Lcom/alibaba/android/arouter/facade/Postcard;->withFlags(I)Lcom/alibaba/android/arouter/facade/Postcard;"),
            instruction(16, "move-result-object", [2]),
        ]
        constructed = trace_navigation(instructions, "Lexample/Caller;", "click()V", "classes.dex", "example")
        self.assertEqual(constructed[0]["kind"], "route_construction")
        opened = trace_navigation(instructions + [instruction(18, "invoke-virtual", [2], "Lcom/alibaba/android/arouter/facade/Postcard;->navigation()Ljava/lang/Object;")], "Lexample/Caller;", "click()V", "classes.dex", "example")
        self.assertEqual(opened[0]["kind"], "route_launch")

    def test_set_class_name_tracks_only_literal_target(self):
        result = trace_navigation([
            instruction(0, "new-instance", [0], "Landroid/content/Intent;"),
            instruction(2, "const-string", [2], "example.Target"),
            instruction(4, "invoke-virtual", [0, 1, 2], "Landroid/content/Intent;->setClassName(Landroid/content/Context; Ljava/lang/String;)Landroid/content/Intent;"),
            instruction(10, "invoke-virtual", [1, 0], "Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V"),
        ], "Lexample/Caller;", "click()V", "classes.dex", "example")
        self.assertEqual(result[0]["target"], "example.Target")

    def test_runtime_action_is_not_promoted_to_static(self):
        status, event = action_kind({":type": "data.click_event"})
        self.assertEqual(status, "runtime_value")
        self.assertIn("data.click_event", event)
        self.assertEqual(action_kind({"type": "toAllTab"}), ("static_binding", "toAllTab"))

    def test_template_preserves_source_conditions_and_dynamic_label(self):
        graph = template_graph("assets/offline/orders/main.json", {
            ":if": "data.visible", "elements": [{"type": "Text", "click_action": {"type": "toAllTab"},
                "attr": {":text": "data.title"}}],
        })
        edge = graph["bindings"][0]
        self.assertEqual(edge["path"], "$.elements[0].click_action")
        self.assertTrue(edge["texts"][0]["dynamic"])
        self.assertEqual(edge["conditions"][0]["value"], "data.visible")

    def test_no_binding_is_not_a_flow(self):
        self.assertIsNone(template_graph("page.json", {"title": "订单", "pages": ["退款"]}))

    def test_expression_click_field_is_included_but_never_static(self):
        graph = template_graph("page.json", {":click_action": "makeMap('type', item.event_name)"})
        self.assertEqual(graph["bindings"][0]["status"], "runtime_value")
        self.assertEqual(graph["bindings"][0]["path"], "$.:click_action")

    def test_direct_intent_target_is_attributed(self):
        result = trace_navigation([
            instruction(0, "new-instance", [0], "Landroid/content/Intent;"),
            instruction(2, "const-class", [2], "Lexample/LaunchL;"),
            instruction(4, "invoke-direct", [0, 1, 2], "Landroid/content/Intent;-><init>(Landroid/content/Context; Ljava/lang/Class;)V"),
            instruction(10, "invoke-virtual", [1, 0], "Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V"),
        ], "Lexample/Caller;", "click()V", "classes.dex", "example")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["target"], "example.LaunchL")
        self.assertEqual(result[0]["source_class"], "example.Caller")

    def test_branch_target_discards_fallthrough_literal(self):
        result = trace_navigation([
            instruction(0, "if-eqz", [3], extra=[(3, 4)]),
            instruction(2, "const-string", [1], "aweme://somewhere"),
            instruction(8, "invoke-static", [0, 1], "Lcom/bytedance/router/SmartRouter;->buildRoute(Landroid/content/Context; Ljava/lang/String;)Lcom/bytedance/router/SmartRoute;"),
        ], "Lexample/Caller;", "click()V", "classes.dex", "example")
        self.assertEqual(result, [])

    def test_route_construction_is_not_reported_as_launch(self):
        result = trace_navigation([
            instruction(0, "const-string", [1], "aweme://search"),
            instruction(2, "invoke-static", [0, 1], "Lcom/bytedance/router/SmartRouter;->buildRoute(Landroid/content/Context; Ljava/lang/String;)Lcom/bytedance/router/SmartRoute;"),
        ], "Lexample/Caller;", "click()V", "classes.dex", "example")
        self.assertEqual(result[0]["kind"], "route_construction")

    def test_route_open_and_mapping_are_distinct_evidence(self):
        result = trace_navigation([
            instruction(0, "const-string", [1], "//search"),
            instruction(2, "invoke-static", [0, 1], "Lcom/bytedance/router/SmartRouter;->buildRoute(Landroid/content/Context; Ljava/lang/String;)Lcom/bytedance/router/SmartRoute;"),
            instruction(8, "move-result-object", [2]),
            instruction(10, "invoke-virtual", [2], "Lcom/bytedance/router/SmartRoute;->open()V"),
        ], "Lexample/Caller;", "click()V", "classes.dex", "example")
        self.assertEqual(result[0]["kind"], "route_launch")
        mapping = trace_navigation([
            instruction(0, "const-string", [1], "//search"),
            instruction(2, "const-string", [2], "example.SearchActivity"),
            instruction(4, "invoke-interface", [0, 1, 2], "Ljava/util/Map;->put(Ljava/lang/Object; Ljava/lang/Object;)Ljava/lang/Object;"),
        ], "Lcom/bytedance/router/mapping/SmartRouter$$Mapping;", "init(Ljava/util/Map;)V", "classes.dex", "example")
        self.assertEqual(mapping[0]["kind"], "route_declaration")
        self.assertEqual(mapping[0]["route"], "//search")
        self.assertEqual(mapping[0]["target"], "example.SearchActivity")

    def test_compressed_nested_json_preserves_origin(self):
        import zstandard
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("page.json", json.dumps({"click_action": {"type": "openDetail"}}))
        report = {"graphs": [], "unparsed": [], "asset_catalog": [], "scan": {
            "zstd_expanded": 0, "archives_expanded": 0, "embedded_json_parsed": 0}}
        scan_embedded("assets/res.zst", zstandard.ZstdCompressor().compress(buffer.getvalue()), report)
        self.assertEqual(report["scan"]["archives_expanded"], 1)
        self.assertEqual(report["graphs"][0]["source"], "assets/res.zst!expanded!page.json")
        self.assertEqual(report["unparsed"], [])

    def test_binary_program_is_not_fabricated_into_a_flow(self):
        report = {"graphs": [], "unparsed": []}
        scan_embedded("assets/template.js", b"\x00asm\xff", report)
        self.assertEqual(report["graphs"], [])
        self.assertIn("not_decompiled", report["unparsed"][0]["reason"])

    def test_report_escapes_script_end_and_resolves_exact_route(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            evidence, library, output = [folder / name for name in ("evidence.json", "dagre.js", "index.html")]
            evidence.write_text(json.dumps({"routes": [
                {"id": "mapping", "kind": "route_declaration", "route": "//search", "target": "example.Search"},
                {"kind": "route_launch", "target": "aweme://search?foo=1"}],
                "hostile": "</script><script>alert(1)</script>"}))
            library.write_text("/* test library */")
            data = render(evidence, library, output)
            self.assertEqual(data["routes"][1]["resolved_targets"][0]["evidence_id"], "mapping")
            self.assertNotIn("</script><script>alert(1)", output.read_text())

    def test_switch_or_exception_entry_discards_predecessor_values(self):
        result = trace_navigation([
            instruction(0, "const-string", [1], "//search"),
            instruction(2, "invoke-static", [0, 1], "Lcom/bytedance/router/SmartRouter;->buildRoute(Landroid/content/Context; Ljava/lang/String;)Lcom/bytedance/router/SmartRoute;"),
        ], "Lexample/Caller;", "click()V", "classes.dex", "example", block_starts={2})
        self.assertEqual(result, [])

    def test_unknown_component_replacement_invalidates_intent_target(self):
        result = trace_navigation([
            instruction(0, "new-instance", [0], "Landroid/content/Intent;"),
            instruction(2, "const-class", [2], "Lexample/Target;"),
            instruction(4, "invoke-direct", [0, 1, 2], "Landroid/content/Intent;-><init>(Landroid/content/Context; Ljava/lang/Class;)V"),
            instruction(10, "invoke-virtual", [0, 3], "Landroid/content/Intent;->setComponent(Landroid/content/ComponentName;)Landroid/content/Intent;"),
            instruction(16, "invoke-virtual", [1, 0], "Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V"),
        ], "Lexample/Caller;", "click()V", "classes.dex", "example")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
