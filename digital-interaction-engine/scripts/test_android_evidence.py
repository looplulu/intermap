import unittest
from process_android_evidence import build_review


def frame(seq, time, hash='a'):
    return dict(id=f'e_{seq}', seq=seq, kind='frame', uptime_ms=time,
                payload=dict(uptime_ms=time, sha256=hash, asset=f'f_{seq}.jpg',
                             screen_width=1080, screen_height=2400,
                             image_width=720, image_height=1600, rotation=0))


def click(seq, time):
    return dict(id=f'e_{seq}', seq=seq, kind='accessibility', uptime_ms=time,
                payload=dict(event_type=1, event_uptime_ms=time,
                             position_source='accessibility_node_bounds', touch_point=None,
                             source=dict(bounds=dict(left=810, top=120, right=1080, bottom=360))))


class EvidenceTest(unittest.TestCase):
    def test_native_bounds_align_to_before_frame_without_inventing_touch(self):
        review = build_review([frame(1, 100), click(2, 200), frame(3, 500, 'b')], {})
        item = review['interactions'][0]
        self.assertEqual(item['target_bounds_norm'], dict(x=.75, y=.05, w=.25, h=.1))
        self.assertIsNone(item['touch_point'])
        self.assertEqual(len(review['edges']), 1)
        self.assertEqual(item['before']['id'], 'e_1')

    def test_fast_clicks_do_not_fabricate_intermediate_states(self):
        review = build_review([frame(1, 100), click(2, 200), click(3, 250), frame(4, 500)], {})
        self.assertEqual(review['edges'], [])
        self.assertIn('missing_after_frame_or_rapid_actions', review['interactions'][0]['issues'])
        self.assertIn('before_frame_predates_previous_action', review['interactions'][1]['issues'])

    def test_revisits_use_actual_path_and_same_screen_clicks_are_not_success(self):
        records = [frame(1, 100), click(2, 200), frame(3, 500, 'b'), click(4, 600), frame(5, 900, 'a'), click(6, 1000), frame(7, 1300, 'a')]
        review = build_review(records, {})
        self.assertEqual([(e['from_node'], e['to_node']) for e in review['edges']], [('a', 'b'), ('b', 'a'), ('a', 'a')])
        self.assertEqual(review['edges'][-1]['outcome'], 'same_pixels')

    def test_missing_frames_or_gaps_block_candidate_edges(self):
        records = [frame(1, 100), click(2, 200), dict(id='e_3', seq=3, kind='capture_gap', uptime_ms=250, payload={}), frame(4, 500)]
        self.assertEqual(build_review(records, {})['edges'], [])
        self.assertEqual(build_review([click(1, 200)], {})['edges'], [])

    def test_annotation_is_bound_to_specific_action(self):
        records = [frame(1, 100), click(2, 200), frame(3, 500), dict(id='e_4', seq=4, kind='annotation', uptime_ms=900,
                    payload=dict(action_id='e_2', target='三个点'))]
        self.assertEqual(build_review(records, {})['interactions'][0]['annotations'][0]['target'], '三个点')

    def test_user_completion_stays_separate_from_verified_result(self):
        records = [frame(1, 100), click(2, 200), frame(3, 500, 'b'),
                   dict(id='e_4', seq=4, kind='task_outcome', uptime_ms=700, wall_time_ms=10000,
                        payload=dict(outcome='user_confirmed_completed', last_action_id='e_2'))]
        review = build_review(records, {'task': '申请退款'})
        self.assertEqual(review['task_outcome']['outcome'], 'user_confirmed_completed')
        self.assertEqual(review['task_outcome']['verification'], 'user_report_only')
        self.assertEqual(review['task_outcome']['last_action_id'], 'e_2')
        self.assertEqual(review['task_outcome']['frame']['id'], 'e_3')
        self.assertEqual(review['edges'][0]['outcome'], 'visual_change')


if __name__ == '__main__': unittest.main()
