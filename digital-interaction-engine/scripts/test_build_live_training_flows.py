import unittest

from build_live_training_flows import (
    build_interaction_maps,
    build_session_candidate,
)


def event(session_id, event_type, payload, capture_mode="android_screen"):
    return {
        "session_id": session_id,
        "event_type": event_type,
        "timestamp": "2026-07-30T12:00:00+08:00",
        "app": "抖音",
        "task": "free_exploration",
        "capture_mode": capture_mode,
        "payload": payload,
    }


class InteractionMapBuilderTest(unittest.TestCase):
    def test_merges_sessions_into_app_candidate_map(self):
        first = build_session_candidate(
            [
                event(
                    "s1",
                    "node_located",
                    {
                        "node_id": "home-a",
                        "node_name": "抖音首页",
                        "page_type": "home",
                        "confidence": 0.9,
                        "layout_items": [{"text": "推荐"}, {"text": "我"}],
                    },
                ),
                event(
                    "s1",
                    "node_located",
                    {
                        "node_id": "profile-a",
                        "node_name": "个人主页",
                        "page_type": "profile",
                        "confidence": 0.88,
                        "layout_items": [{"text": "抖音号"}],
                    },
                ),
                event(
                    "s1",
                    "node_transition",
                    {
                        "from_node_id": "home-a",
                        "to_node_id": "profile-a",
                        "inferred_action": "点击右下角的我",
                    },
                ),
            ]
        )
        second = build_session_candidate(
            [
                event(
                    "s2",
                    "node_located",
                    {
                        "node_id": "home-b",
                        "node_name": "抖音首页",
                        "page_type": "home",
                        "confidence": 0.92,
                        "layout_items": [{"text": "推荐"}],
                    },
                ),
                event(
                    "s2",
                    "node_located",
                    {
                        "node_id": "profile-b",
                        "node_name": "个人主页",
                        "page_type": "profile",
                        "confidence": 0.91,
                        "layout_items": [{"text": "抖音号"}],
                    },
                ),
                event(
                    "s2",
                    "node_transition",
                    {
                        "from_node_id": "home-b",
                        "to_node_id": "profile-b",
                        "inferred_action": "点击右下角的我",
                    },
                ),
            ]
        )

        maps = build_interaction_maps([first, second])

        self.assertEqual(len(maps), 1)
        self.assertEqual(maps[0]["app"], "抖音")
        self.assertEqual(len(maps[0]["nodes"]), 2)
        self.assertEqual(len(maps[0]["edges"]), 1)
        self.assertEqual(maps[0]["edges"][0]["observations"], 2)
        self.assertEqual(
            maps[0]["edges"][0]["action_candidates"][0]["text"],
            "点击右下角的我",
        )
        self.assertEqual(maps[0]["status"], "pending_review")

    def test_accessibility_source_has_highest_live_weight(self):
        candidate = build_session_candidate(
            [
                event(
                    "s3",
                    "node_located",
                    {
                        "node_id": "home",
                        "node_name": "抖音首页",
                        "page_type": "home",
                    },
                    capture_mode="android_accessibility",
                )
            ]
        )

        self.assertEqual(candidate["source"], "live_android_accessibility")
        self.assertEqual(candidate["source_weight"], 1.0)


if __name__ == "__main__":
    unittest.main()
