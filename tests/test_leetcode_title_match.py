"""回归测试：力扣中文标题与站内标题不一致时，同步仍能匹配到题目（208/238）。"""
from unittest import TestCase

from interview_forge.services import leetcode
from interview_forge.core.problem_catalog import PROBLEM_BY_ID, LEETCODE_SLUGS


class LeetCodeTitleMatchTests(TestCase):
    def test_known_mismatches_are_aliased(self) -> None:
        """208/238 的站内标题和力扣中文标题不同，必须都在别名表里映射到正确 pid。"""
        self.assertEqual(leetcode._LC_TITLE_ALIASES.get("实现 Trie (前缀树)"), 208)
        self.assertEqual(leetcode._LC_TITLE_ALIASES.get("除了自身以外数组的乘积"), 238)

    def test_alias_titles_point_to_right_problem(self) -> None:
        for lc_title, pid in leetcode._LC_TITLE_ALIASES.items():
            self.assertIn(pid, PROBLEM_BY_ID)
            self.assertIn(pid, LEETCODE_SLUGS)

    def test_norm_title_matches_parenthesis_variant(self) -> None:
        """「实现 Trie (前缀树)」归一化后应与站内「实现 Trie」一致。"""
        self.assertEqual(
            leetcode._norm_title("实现 Trie (前缀树)"),
            leetcode._norm_title("实现 Trie"),
        )

    def test_norm_title_ignores_space_and_punct(self) -> None:
        self.assertEqual(
            leetcode._norm_title("Product of Array Except Self"),
            leetcode._norm_title("product-of-array-except-self"),
        )

    def test_simulated_lookup_hits_208_238(self) -> None:
        """模拟同步构建 title_to_id + norm_to_id 后，力扣中文标题能查到 pid。"""
        title_to_id = {}
        for pid, problem in PROBLEM_BY_ID.items():
            title_to_id.setdefault(str(problem["title"]).strip(), int(pid))
        for t, p in leetcode._LC_TITLE_ALIASES.items():
            title_to_id.setdefault(t, int(p))
        norm_to_id = {}
        for t, p in title_to_id.items():
            norm_to_id.setdefault(leetcode._norm_title(t), int(p))

        def lookup(title):
            return title_to_id.get(title) or norm_to_id.get(leetcode._norm_title(title))

        self.assertEqual(lookup("实现 Trie (前缀树)"), 208)
        self.assertEqual(lookup("除了自身以外数组的乘积"), 238)

    def test_nearest_pid_matches_one_char_variant(self) -> None:
        """力扣标题与站内标题仅差一个字（如「除自身以外」vs「除了自身以外」）也能匹配。"""
        items = [(str(p["title"]).strip(), pid) for pid, p in PROBLEM_BY_ID.items()]
        self.assertEqual(leetcode._nearest_pid("除了自身以外数组的乘积", items), 238)
        self.assertEqual(leetcode._nearest_pid("实现 Trie (前缀树)", items), 208)
        self.assertEqual(
            leetcode._levenshtein(
                leetcode._norm_title("除了自身以外数组的乘积"),
                leetcode._norm_title("除自身以外数组的乘积"),
            ),
            1,
        )
