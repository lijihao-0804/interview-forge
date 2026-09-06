# -*- coding: utf-8 -*-
"""一次性修复 tools/lang_solutions.json：代码随想录「思路」区提取出的
伪代码/片段/示例输出（23 条）替换为站内标准实现，来源如实标注。
其余条目仅做 \xa0 规范化。运行后需重新 build_hot100 + build_html_site。"""
import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / "lang_solutions.json"
SRC = "站内标准实现"

FIXES = {
    ("11", "cpp"): """class Solution {
public:
    int maxArea(vector<int>& height) {
        int left = 0, right = (int)height.size() - 1, ans = 0;
        while (left < right) {
            ans = max(ans, min(height[left], height[right]) * (right - left));
            if (height[left] < height[right]) ++left; else --right;
        }
        return ans;
    }
};""",
    ("15", "cpp"): """class Solution {
public:
    vector<vector<int>> threeSum(vector<int>& nums) {
        vector<vector<int>> ans;
        sort(nums.begin(), nums.end());
        int n = nums.size();
        for (int i = 0; i < n - 2 && nums[i] <= 0; ++i) {
            if (i > 0 && nums[i] == nums[i - 1]) continue;
            int left = i + 1, right = n - 1;
            while (left < right) {
                long long s = (long long)nums[i] + nums[left] + nums[right];
                if (s < 0) ++left;
                else if (s > 0) --right;
                else {
                    ans.push_back({nums[i], nums[left], nums[right]});
                    while (left < right && nums[left] == nums[left + 1]) ++left;
                    while (left < right && nums[right] == nums[right - 1]) --right;
                    ++left; --right;
                }
            }
        }
        return ans;
    }
};""",
    ("31", "cpp"): """class Solution {
public:
    void nextPermutation(vector<int>& nums) {
        int n = nums.size(), i = n - 2;
        // 1) 从右往左找第一个升序对 (i, i+1)
        while (i >= 0 && nums[i] >= nums[i + 1]) --i;
        // 2) 在后缀中找最后一个大于 nums[i] 的数与之交换
        if (i >= 0) {
            int j = n - 1;
            while (nums[j] <= nums[i]) --j;
            swap(nums[i], nums[j]);
        }
        // 3) 反转后缀使其升序（变最小排列）
        reverse(nums.begin() + i + 1, nums.end());
    }
};""",
    ("55", "c"): """bool canJump(int* nums, int numsSize) {
    int farthest = 0;
    for (int i = 0; i < numsSize; ++i) {
        if (i > farthest) return false;
        if (i + nums[i] > farthest) farthest = i + nums[i];
        if (farthest >= numsSize - 1) return true;
    }
    return true;
}""",
    ("56", "c"): """int cmp(const void* a, const void* b) {
    return (*(int**)a)[0] - (*(int**)b)[0];
}

int** merge(int** intervals, int intervalsSize, int* intervalsColSize,
            int* returnSize, int** returnColumnSizes) {
    qsort(intervals, intervalsSize, sizeof(int*), cmp);
    int** ans = malloc(sizeof(int*) * intervalsSize);
    *returnColumnSizes = malloc(sizeof(int) * intervalsSize);
    *returnSize = 0;
    for (int i = 0; i < intervalsSize; ++i) {
        int l = intervals[i][0], r = intervals[i][1];
        if (*returnSize > 0 && ans[*returnSize - 1][1] >= l) {
            if (r > ans[*returnSize - 1][1]) ans[*returnSize - 1][1] = r;
        } else {
            ans[*returnSize] = malloc(sizeof(int) * 2);
            ans[*returnSize][0] = l;
            ans[*returnSize][1] = r;
            (*returnColumnSizes)[*returnSize] = 2;
            ++*returnSize;
        }
    }
    return ans;
}""",
    ("56", "cpp"): """class Solution {
public:
    vector<vector<int>> merge(vector<vector<int>>& intervals) {
        sort(intervals.begin(), intervals.end());
        vector<vector<int>> ans;
        for (auto& p : intervals) {
            if (!ans.empty() && ans.back()[1] >= p[0])
                ans.back()[1] = max(ans.back()[1], p[1]);
            else
                ans.push_back(p);
        }
        return ans;
    }
};""",
    ("70", "go"): """func climbStairs(n int) int {
	a, b := 1, 1
	for i := 2; i <= n; i++ {
		a, b = b, a+b
	}
	return b
}""",
    ("72", "cpp"): """class Solution {
public:
    int minDistance(string word1, string word2) {
        int m = word1.size(), n = word2.size();
        vector<vector<int>> dp(m + 1, vector<int>(n + 1));
        for (int i = 0; i <= m; ++i) dp[i][0] = i;
        for (int j = 0; j <= n; ++j) dp[0][j] = j;
        for (int i = 1; i <= m; ++i)
            for (int j = 1; j <= n; ++j)
                dp[i][j] = word1[i - 1] == word2[j - 1]
                    ? dp[i - 1][j - 1]
                    : min({dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]}) + 1;
        return dp[m][n];
    }
};""",
    ("74", "cpp"): """class Solution {
public:
    bool searchMatrix(vector<vector<int>>& matrix, int target) {
        int m = matrix.size(), n = matrix[0].size();
        int lo = 0, hi = m * n - 1;   // 展平成一维后二分
        while (lo <= hi) {
            int mid = lo + (hi - lo) / 2;
            int v = matrix[mid / n][mid % n];
            if (v == target) return true;
            if (v < target) lo = mid + 1; else hi = mid - 1;
        }
        return false;
    }
};""",
    ("76", "cpp"): """class Solution {
public:
    string minWindow(string s, string t) {
        int need[128] = {0};
        int missing = t.size(), left = 0, bestLeft = 0, bestLen = INT_MAX;
        for (char c : t) ++need[(unsigned char)c];
        for (int right = 0; right < (int)s.size(); ++right) {
            if (--need[(unsigned char)s[right]] >= 0) --missing;
            while (missing == 0) {          // 窗口已覆盖 t，尝试收缩
                if (right - left + 1 < bestLen) {
                    bestLen = right - left + 1;
                    bestLeft = left;
                }
                if (++need[(unsigned char)s[left++]] > 0) ++missing;
            }
        }
        return bestLen == INT_MAX ? "" : s.substr(bestLeft, bestLen);
    }
};""",
    ("101", "cpp"): """class Solution {
    bool compare(TreeNode* left, TreeNode* right) {
        if (left == nullptr && right == nullptr) return true;
        if (left == nullptr || right == nullptr || left->val != right->val) return false;
        return compare(left->left, right->right) && compare(left->right, right->left);
    }
public:
    bool isSymmetric(TreeNode* root) {
        return root == nullptr || compare(root->left, root->right);
    }
};""",
    ("108", "cpp"): """class Solution {
    TreeNode* traversal(vector<int>& nums, int left, int right) {
        if (left > right) return nullptr;
        int mid = left + (right - left) / 2;   // 取中点作根，保证高度平衡
        TreeNode* node = new TreeNode(nums[mid]);
        node->left = traversal(nums, left, mid - 1);
        node->right = traversal(nums, mid + 1, right);
        return node;
    }
public:
    TreeNode* sortedArrayToBST(vector<int>& nums) {
        return traversal(nums, 0, (int)nums.size() - 1);
    }
};""",
    ("121", "c"): """int maxProfit(int* prices, int pricesSize) {
    int minPrice = prices[0], ans = 0;
    for (int i = 1; i < pricesSize; ++i) {
        if (prices[i] < minPrice) minPrice = prices[i];
        else if (prices[i] - minPrice > ans) ans = prices[i] - minPrice;
    }
    return ans;
}""",
    ("198", "c"): """int rob(int* nums, int numsSize) {
    int prev = 0, cur = 0;   // prev = dp[i-2], cur = dp[i-1]
    for (int i = 0; i < numsSize; ++i) {
        int t = (prev + nums[i] > cur) ? prev + nums[i] : cur;
        prev = cur;
        cur = t;
    }
    return cur;
}""",
    ("200", "go"): """func numIslands(grid [][]byte) int {
	ans := 0
	m, n := len(grid), len(grid[0])
	var dfs func(i, j int)
	dfs = func(i, j int) {
		if i < 0 || i >= m || j < 0 || j >= n || grid[i][j] != '1' {
			return
		}
		grid[i][j] = '0' // 沉岛：访问过即置 0，避免重复计数
		dfs(i+1, j)
		dfs(i-1, j)
		dfs(i, j+1)
		dfs(i, j-1)
	}
	for i := 0; i < m; i++ {
		for j := 0; j < n; j++ {
			if grid[i][j] == '1' {
				ans++
				dfs(i, j)
			}
		}
	}
	return ans
}""",
    ("236", "cpp"): """class Solution {
public:
    TreeNode* lowestCommonAncestor(TreeNode* root, TreeNode* p, TreeNode* q) {
        if (root == nullptr || root == p || root == q) return root;
        TreeNode* left = lowestCommonAncestor(root->left, p, q);
        TreeNode* right = lowestCommonAncestor(root->right, p, q);
        if (left != nullptr && right != nullptr) return root; // p、q 分居两侧
        return left != nullptr ? left : right;
    }
};""",
    ("279", "c"): """int numSquares(int n) {
    int* dp = malloc(sizeof(int) * (n + 1));
    dp[0] = 0;
    for (int i = 1; i <= n; ++i) {
        dp[i] = INT_MAX;
        for (int j = 1; j * j <= i; ++j)
            if (dp[i - j * j] + 1 < dp[i]) dp[i] = dp[i - j * j] + 1;
    }
    return dp[n];
}""",
    ("300", "c"): """int lengthOfLIS(int* nums, int numsSize) {
    int* tails = malloc(sizeof(int) * numsSize); // tails[k] = 长度 k+1 的 LIS 最小结尾
    int size = 0;
    for (int i = 0; i < numsSize; ++i) {
        int lo = 0, hi = size;
        while (lo < hi) {                 // 二分找第一个 >= nums[i] 的位置
            int mid = (lo + hi) / 2;
            if (tails[mid] < nums[i]) lo = mid + 1; else hi = mid;
        }
        tails[lo] = nums[i];
        if (lo == size) ++size;
    }
    return size;
}""",
    ("322", "c"): """int coinChange(int* coins, int coinsSize, int amount) {
    int* dp = malloc(sizeof(int) * (amount + 1));
    dp[0] = 0;
    for (int i = 1; i <= amount; ++i) dp[i] = amount + 1;
    for (int i = 1; i <= amount; ++i)
        for (int j = 0; j < coinsSize; ++j)
            if (coins[j] <= i && dp[i - coins[j]] + 1 < dp[i])
                dp[i] = dp[i - coins[j]] + 1;
    return dp[amount] > amount ? -1 : dp[amount];
}""",
    ("560", "cpp"): """class Solution {
public:
    int subarraySum(vector<int>& nums, int k) {
        unordered_map<long long, int> cnt{{0, 1}}; // 前缀和出现次数
        long long sum = 0;
        int ans = 0;
        for (int x : nums) {
            sum += x;
            auto it = cnt.find(sum - k);
            if (it != cnt.end()) ans += it->second;
            ++cnt[sum];
        }
        return ans;
    }
};""",
    ("560", "go"): """func subarraySum(nums []int, k int) int {
	cnt := map[int]int{0: 1}
	sum, ans := 0, 0
	for _, x := range nums {
		sum += x
		ans += cnt[sum-k]
		cnt[sum]++
	}
	return ans
}""",
    ("763", "c"): """int* partitionLabels(char* s, int* returnSize) {
    int len = strlen(s);
    int last[26] = {0};
    for (int i = 0; i < len; ++i) last[s[i] - 'a'] = i; // 每字符最后出现位置
    int* ans = malloc(sizeof(int) * len);
    *returnSize = 0;
    int start = 0, end = 0;
    for (int i = 0; i < len; ++i) {
        if (last[s[i] - 'a'] > end) end = last[s[i] - 'a'];
        if (i == end) { // 当前片段已涵盖所有成员的最远位置
            ans[(*returnSize)++] = end - start + 1;
            start = i + 1;
        }
    }
    return ans;
}""",
    ("1143", "c"): """int longestCommonSubsequence(char* text1, char* text2) {
    int m = strlen(text1), n = strlen(text2);
    int** dp = malloc(sizeof(int*) * (m + 1));
    for (int i = 0; i <= m; ++i) dp[i] = calloc(n + 1, sizeof(int));
    for (int i = 1; i <= m; ++i)
        for (int j = 1; j <= n; ++j)
            dp[i][j] = text1[i - 1] == text2[j - 1]
                ? dp[i - 1][j - 1] + 1
                : (dp[i - 1][j] > dp[i][j - 1] ? dp[i - 1][j] : dp[i][j - 1]);
    return dp[m][n];
}""",
}

def looks_like_code(code: str, lang: str) -> bool:
    code = code.replace("\xa0", " ")
    if len(code) < 40:
        return False
    lines = [l for l in code.split("\n") if l.strip()]
    if len(lines) < 2:
        return False
    numish = sum(1 for l in lines if re.match(r"^[\s\d,.\[\]]+$", l))
    if numish > len(lines) / 2:
        return False
    if lang in ("cpp", "c", "java"):
        return ";" in code or "{" in code
    if lang == "go":
        return "func " in code or ":=" in code or "package " in code
    if lang == "python":
        return "def " in code or "class " in code or "return " in code or "print(" in code
    return True

def main():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    replaced, missing_fix = [], []
    for pid, entry in data.items():
        for lang, item in entry.items():
            item["code"] = item["code"].replace("\xa0", " ")
            if (pid, lang) in FIXES:
                item["code"] = FIXES[(pid, lang)]
                item["source"] = SRC
                replaced.append((pid, lang))
            elif not looks_like_code(item["code"], lang):
                missing_fix.append((pid, lang))
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("replaced:", len(replaced), replaced)
    print("still bad (need manual):", missing_fix)

if __name__ == "__main__":
    main()
