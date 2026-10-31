import unittest

from run_approved_package_batch import build_map, validate


class ApprovedPackageBatchTest(unittest.TestCase):
    def fixture(self):
        return {"source": "apk_static", "review_status": "pending_review", "sha256": "test-digest",
                "package": {"name": "example.app", "version_name": "1"},
                "activities": [{"id": "a", "name": "example.Target"}],
                "graphs": [{"id": "g", "source": "assets/page.json", "title": "test", "bindings": [
                    {"id": "b", "status": "runtime_value", "event": "data.action", "element_type": "icon", "texts": []}]}],
                "routes": [{"id": "r", "kind": "route_construction", "source_class": "example.Caller",
                            "method": "click()V", "target": "/detail"}],
                "scan": {"bindings": 1}, "limitations": ["unreviewed"]}

    def test_normalization_does_not_turn_containment_or_construction_into_navigation(self):
        data = self.fixture()
        result = build_map(data, {"key": "example", "name": "test"})
        self.assertEqual([e["kind"] for e in result["edges"]],
                         ["contains_not_navigation", "runtime_value", "route_construction"])
        self.assertEqual(len(result["gaps"]), 2)
        self.assertEqual(result["review_status"], "pending_review")
        validate(data, {"android": {"package": "example.app"}},
                 {"sha256": "test-digest", "signature": {"verified": True}}, result)

    def test_validation_rejects_identity_mismatch_and_dangling_edges(self):
        data = self.fixture()
        result = build_map(data, {"key": "example", "name": "test"})
        app = {"android": {"package": "example.app"}}
        provenance = {"sha256": "test-digest", "signature": {"verified": True}}
        with self.assertRaises(ValueError):
            validate(data, app, {**provenance, "sha256": "wrong"}, result)
        result["edges"][0]["to"] = "missing"
        with self.assertRaises(ValueError):
            validate(data, app, provenance, result)


if __name__ == "__main__":
    unittest.main()
