"""Regression checks for distinct matching and image-to-page click coordinates."""
import base64
from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock, patch

from PIL import Image

from interview_forge.services import gym_automation as gym
from interview_forge.services import gym as gym_service


class CandidateModel:
    def __init__(self, rows):
        self.rows = iter(rows)

    def classification(self, _image, probability=False):
        assert probability
        return {"charset": ["", "甲", "乙"],
                "probabilities": [[0, *next(self.rows)]], "text": ""}


class CaptchaMatchingTests(TestCase):
    def test_default_environment_does_not_require_legacy_deepseek_key(self):
        playwright = Mock()
        playwright.__enter__ = Mock(return_value=playwright)
        playwright.__exit__ = Mock(return_value=False)
        playwright.chromium.executable_path = __file__
        with patch("playwright.sync_api.sync_playwright", return_value=playwright), \
                patch.object(gym, "deepseek_key", return_value=None):
            check = gym_service.environment_check()
        self.assertTrue(check["ok"])
        optional = next(i for i in check["items"] if i["name"] == "DeepSeek 认字凭据")
        self.assertFalse(optional["ok"])
        self.assertIn("可选", optional["detail"])

    def test_joint_matching_uses_second_choice_to_avoid_greedy_collision(self):
        ids, gap = gym._best_probability_assignment([[.9, .8], [.89, .1]])
        self.assertEqual(ids, (1, 0))
        self.assertGreater(gap, 0)

    def test_missing_character_or_bad_score_does_not_force_assignment(self):
        for scores in ([[.4], [.3]], [[.4, .5], [0, 0]],
                       [[float("nan"), .2]], [[-.1, .2]]):
            with self.subTest(scores=scores), self.assertRaises(ValueError):
                gym._best_probability_assignment(scores)

    def test_model_disagreement_abstains_before_clicking(self):
        image = Image.new("RGB", (40, 20))
        boxes = [[0, 0, 20, 20], [20, 0, 40, 20]]
        assignment, diagnostics = gym.match_click_targets_probability(
            image, boxes, ["甲", "乙"],
            CandidateModel([[.9, .1], [.1, .9]]),
            CandidateModel([[.1, .9], [.9, .1]]))
        self.assertEqual(assignment, {})
        self.assertFalse(diagnostics["model_agreement"])

    def test_agreed_joint_match_returns_correct_distinct_boxes(self):
        image = Image.new("RGB", (40, 20))
        boxes = [[0, 0, 20, 20], [20, 0, 40, 20]]
        rows = [[.9, .89], [.8, .1]]
        assignment, diagnostics = gym.match_click_targets_probability(
            image, boxes, ["甲", "乙"], CandidateModel(rows), CandidateModel(rows))
        self.assertEqual(assignment["甲"]["box"], boxes[1])
        self.assertEqual(assignment["乙"]["box"], boxes[0])
        self.assertTrue(diagnostics["model_agreement"])

    def test_legacy_votes_cannot_assign_two_targets_to_one_box(self):
        entry = {"std": "甲", "beta": "乙", "box": [0, 0, 10, 10]}
        assignment = gym.assign_targets([entry], ["甲", "乙"])
        self.assertEqual(len(assignment), 1)

    def test_distinct_assignment_cannot_place_target_in_zero_support_box(self):
        image = Image.new("RGB", (40, 20))
        boxes = [[0, 0, 20, 20], [20, 0, 40, 20]]
        rows = [[.9, .1], [0, 0]]
        assignment, diagnostics = gym.match_click_targets_probability(
            image, boxes, ["甲", "乙"], CandidateModel(rows), CandidateModel(rows))
        self.assertEqual(assignment, {})
        self.assertIn("缺少候选支持", diagnostics["reason"])

    def test_scaled_coordinates_preserve_prompt_order(self):
        assignment = {"甲": {"box": [0, 0, 20, 20], "center": (10, 10)},
                      "乙": {"box": [20, 0, 40, 20], "center": (30, 10)}}
        points = gym._captcha_click_points(
            assignment, ["乙", "甲"], {"rect": [100, 200, 80, 40], "natural": [40, 20]})
        self.assertEqual(points, [("乙", 160, 220), ("甲", 120, 220)])

    def test_duplicate_boxes_and_zero_image_size_reject_clicks(self):
        entry = {"box": [0, 0, 20, 20], "center": (10, 10)}
        with self.assertRaises(ValueError):
            gym._captcha_click_points({"甲": entry, "乙": entry}, ["甲", "乙"],
                                     {"rect": [0, 0, 40, 20], "natural": [40, 20]})
        with self.assertRaises(ValueError):
            gym._captcha_click_points({"甲": entry}, ["甲"],
                                     {"rect": [0, 0, 0, 20], "natural": [40, 20]})

    def test_changed_image_is_not_clicked_and_default_skips_remote_ocr(self):
        buffer = BytesIO()
        Image.new("RGB", (40, 20)).save(buffer, format="PNG")
        source = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        dump = {"src": source, "prompt": "甲,乙", "rect": [0, 0, 40, 20], "natural": [40, 20]}
        page = Mock()
        page.evaluate.side_effect = [dump, {**dump, "src": source + "changed"}]
        detector = Mock()
        detector.detection.return_value = [[0, 0, 20, 20], [20, 0, 40, 20]]
        assignment = {"甲": {"box": [0, 0, 20, 20], "center": (10, 10)},
                      "乙": {"box": [20, 0, 40, 20], "center": (30, 10)}}
        with patch("ddddocr.DdddOcr", side_effect=[detector, Mock(), Mock()]), \
                patch.object(gym, "match_click_targets_probability", return_value=(assignment, {})), \
                patch.object(gym, "deepseek_key", side_effect=AssertionError("remote key lookup")), \
                patch.object(gym, "_get_paddle", side_effect=AssertionError("Paddle init")), \
                patch.object(gym, "_wait_for_manual_captcha", return_value=None):
            self.assertIsNone(gym.solve_click_captcha(page, None, max_attempts=1))
        page.mouse.click.assert_not_called()
        page.mouse.down.assert_not_called()

    def test_human_click_lands_inside_the_box_after_a_gradual_move(self):
        page = Mock()
        x, y, w, h = 300.0, 200.0, 40.0, 36.0
        with patch.object(gym.time, "sleep"):
            tx, ty = gym.human_click(page, x, y, w, h)
        self.assertLessEqual(abs(tx - x), w * 0.2, "落点必须还在字框内")
        self.assertLessEqual(abs(ty - y), h * 0.2, "落点必须还在字框内")
        self.assertGreaterEqual(page.mouse.move.call_count, 5, "瞬移没有中间轨迹")
        page.mouse.down.assert_called_once()
        page.mouse.up.assert_called_once()
        order = [c[0] for c in page.mock_calls if c[0] in ("mouse.down", "mouse.up")]
        self.assertEqual(order, ["mouse.down", "mouse.up"])

    def test_human_click_starts_from_the_previous_landing_point(self):
        page = Mock()
        with patch.object(gym.time, "sleep"):
            first = gym.human_click(page, 100.0, 100.0, 40.0, 36.0)
            page.mouse.move.reset_mock()
            gym.human_click(page, 300.0, 200.0, 40.0, 36.0, from_xy=first)
        fx, fy = page.mouse.move.call_args_list[0][0]
        self.assertLess(abs(fx - first[0]), 60, "第二次点击应从上一次落点滑过去")
        self.assertLess(abs(fy - first[1]), 60)

    def test_captcha_popup_text_is_optional(self):
        page = Mock()
        page.evaluate.return_value = "验证失败，请重试"
        self.assertEqual(gym._captcha_popup_text(page), "验证失败，请重试")
        page.evaluate.return_value = None
        self.assertEqual(gym._captcha_popup_text(page), "")
        page.evaluate.side_effect = RuntimeError("页面已切换")
        self.assertEqual(gym._captcha_popup_text(page), "", "读不到不能影响判定")

    def test_new_puzzle_in_the_same_popup_is_re_solved_without_refreshing(self):
        """站点判错后通常在同一弹窗换新题：应直接按新题重解。

        老行为是白等 18 秒再点一次刷新，等于把站点刚给的新题又换掉。
        """
        buffer = BytesIO()
        Image.new("RGB", (40, 20)).save(buffer, format="PNG")
        blob = base64.b64encode(buffer.getvalue()).decode()
        puzzle_a = {"src": "data:image/png;base64," + blob, "prompt": "甲,乙",
                    "rect": [0, 0, 40, 20], "natural": [40, 20]}
        puzzle_b = {**puzzle_a, "src": "data:image/png;base64," + blob + "B"}

        class Page:
            url = "https://ggtypt.nju.edu.cn/venue/venue-reservation/1"

            def __init__(self) -> None:
                self.mouse = Mock()
                self.context = Mock(pages=[])
                self.dump_calls = 0
                self.locator = Mock(side_effect=AssertionError("判错换新题时不该点刷新"))

            def evaluate(self, script):
                if script is gym.JS_CAPTCHA_POPUP_TEXT:
                    return ""
                if script is gym.JS_CAPTCHA_DUMP:
                    self.dump_calls += 1
                    if self.dump_calls == 1:
                        return puzzle_a
                    if self.dump_calls == 4:
                        self.url = "https://ggtypt.nju.edu.cn/venue/orders?tradeNo=X"
                    return puzzle_b
                raise AssertionError(f"unexpected page evaluation: {script}")

        page = Page()
        assignment = {"甲": {"box": [0, 0, 20, 20], "center": (10, 10)},
                      "乙": {"box": [20, 0, 40, 20], "center": (30, 10)}}
        detector = Mock()
        detector.detection.return_value = [[0, 0, 20, 20], [20, 0, 40, 20]]
        with patch("ddddocr.DdddOcr", side_effect=[detector, Mock(), Mock()]), \
                patch.object(gym, "match_click_targets_probability", return_value=(assignment, {})), \
                patch.object(gym, "click_first_visible", return_value=False), \
                patch.object(gym, "_wait_for_manual_captcha", return_value=None), \
                patch.object(gym.time, "sleep"):
            result = gym.solve_click_captcha(page, None, max_attempts=2)
        self.assertIs(result, page, "换新题后应重解并成功")
        self.assertGreaterEqual(page.dump_calls, 4, "应当重新读过新题")
        page.locator.assert_not_called()
