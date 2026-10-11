"""一次性修复 tools/lang_solutions.json 的 80 处截断条目（2026-10-03 审计）。

根因与证据见 docs/题解完整性审计报告-2026-10-03.md：
  extract_carl 的缩进收集器把"代码块内部空行"当作块终点，导致来源 B
  （代码随想录网页格式）的所有含空行实现被拦腰截断。

修复分三部分：
  1. REEXTRACT：用候选收集器（extract_carl 的忠实变体，保留全部候选块）
     对受损条目从源稿重抽，取第一个通过完整性签名的候选；
  2. HAND：源稿没有对应语言的 8 条 C++ 实现，按各题 python/Java 实现的
     同一算法手工补写，来源如实标注"站内标准实现"；
  3. SKIP：48/73/75/114/283/189 的 python/go 共 12 条为 void 型题的扫描器
     误报（无返回值属正常），当前内容完整，保持不动。

运行后需重新 build_hot100 + build_html_site，并用签名扫描复验。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_lang_solutions import (
    LANG_HEADER,
    NORM,
    NUM_LINE,
    looks_like_code,
)

OUT = Path(__file__).resolve().parents[2] / "tools" / "lang_solutions.json"
CARL = Path(r"E:\JAVA\AI+agent\笔记\代码随想录-Hot100")
HAND_SOURCE = "站内标准实现"

HAND = {
    ("5", "cpp"): """class Solution {
public:
    string longestPalindrome(string s) {
        vector<vector<bool>> dp(s.size(), vector<bool>(s.size(), false));
        int maxlenth = 0;
        int left = 0, right = 0;
        for (int i = s.size() - 1; i >= 0; i--) {      // 遍历左边界（从后往前）
            for (int j = i; j < s.size(); j++) {       // 遍历右边界
                if (s[j] == s[i] && (j - i <= 1 || dp[i + 1][j - 1])) {
                    dp[i][j] = true;                   // s[i..j] 是回文串
                }
                if (dp[i][j] && j - i + 1 > maxlenth) {
                    maxlenth = j - i + 1;              // 记录最长回文串的长度与起点
                    left = i;
                    right = j;
                }
            }
        }
        return s.substr(left, right - left + 1);
    }
};""",
    ("17", "cpp"): """class Solution {
private:
    const string letterMap[10] = {
        "",     // 0
        "",     // 1
        "abc",  // 2
        "def",  // 3
        "ghi",  // 4
        "jkl",  // 5
        "mno",  // 6
        "pqrs", // 7
        "tuv",  // 8
        "wxyz"  // 9
    };
    string s;
    vector<string> result;

    void backtracking(const string& digits, int index) {
        if (index == digits.size()) {              // 数字串遍历完毕，收集一组组合
            result.push_back(s);
            return;
        }
        int digit = digits[index] - '0';
        const string& letters = letterMap[digit];
        for (int i = 0; i < letters.size(); i++) { // 本位数字的每个字母各走一支
            s.push_back(letters[i]);
            backtracking(digits, index + 1);
            s.pop_back();                          // 回溯，撤销本位字母
        }
    }

public:
    vector<string> letterCombinations(string digits) {
        result.clear();
        s.clear();
        if (digits.empty()) return result;         // 空串无组合
        backtracking(digits, 0);
        return result;
    }
};""",
    ("70", "cpp"): """// 完全背包思路：dp[j] 表示爬到第 j 阶的方案数，
// 每次可以爬 1~m 个台阶，抽象为物品重量 1~m。
// 排列题，注意循环顺序：背包在外、物品在内。
int climbing_stairs(int n, int m) {
    vector<int> dp(n + 1, 0);   // 背包总容量
    dp[0] = 1;
    for (int j = 1; j <= n; j++) {          // 背包容量
        for (int i = 1; i <= m; i++) {      // 物品（每次爬的阶数）
            if (j >= i) dp[j] += dp[j - i]; // 这里 i 就是阶数而非下标
        }
    }
    return dp[n];
}""",
    ("78", "cpp"): """class Solution {
private:
    vector<vector<int>> result;
    vector<int> path;

    void backtracking(vector<int>& nums, int start_index) {
        result.push_back(path);              // 收集树上每个节点，不只是叶子
        if (start_index >= nums.size()) return;
        for (int i = start_index; i < nums.size(); i++) {
            path.push_back(nums[i]);
            backtracking(nums, i + 1);
            path.pop_back();                 // 回溯，撤销本次选择
        }
    }

public:
    vector<vector<int>> subsets(vector<int>& nums) {
        result.clear();
        path.clear();
        backtracking(nums, 0);
        return result;
    }
};""",
    ("131", "cpp"): """class Solution {
private:
    vector<vector<string>> result;
    vector<string> path;

    bool is_palindrome(const string& s, int start, int end) {
        for (int i = start, j = end; i < j; i++, j--) {
            if (s[i] != s[j]) return false;
        }
        return true;
    }

    void backtracking(const string& s, int start_index) {
        if (start_index >= s.size()) {       // 切割线到末尾，找到一种切割方案
            result.push_back(path);
            return;
        }
        for (int i = start_index; i < s.size(); i++) {
            if (!is_palindrome(s, start_index, i)) continue;
            path.push_back(s.substr(start_index, i - start_index + 1));
            backtracking(s, i + 1);          // 从 i+1 起继续切割，不重复同一位置
            path.pop_back();
        }
    }

public:
    vector<vector<string>> partition(string s) {
        result.clear();
        path.clear();
        backtracking(s, 0);
        return result;
    }
};""",
    ("279", "cpp"): """class Solution {
public:
    int numSquares(int n) {
        vector<int> dp(n + 1, INT_MAX);   // dp[i]：凑出 i 所需的最少完全平方数数量
        dp[0] = 0;
        for (int i = 1; i <= n; i++) {            // 背包容量
            for (int j = 1; j * j <= i; j++) {    // 物品：完全平方数 j²
                dp[i] = min(dp[i], dp[i - j * j] + 1);
            }
        }
        return dp[n];
    }
};""",
    ("300", "cpp"): """class Solution {
public:
    int lengthOfLIS(vector<int>& nums) {
        if (nums.size() <= 1) return nums.size();
        vector<int> dp(nums.size(), 1);   // dp[i]：以 nums[i] 结尾的最长递增子序列长度
        int result = 1;
        for (int i = 1; i < nums.size(); i++) {
            for (int j = 0; j < i; j++) {
                if (nums[i] > nums[j]) dp[i] = max(dp[i], dp[j] + 1);
            }
            result = max(result, dp[i]);  // 取长的子序列
        }
        return result;
    }
};""",
    ("1143", "cpp"): """class Solution {
public:
    int longestCommonSubsequence(string text1, string text2) {
        // dp[i][j]：text1 前 i 个字符与 text2 前 j 个字符的最长公共子序列长度
        vector<vector<int>> dp(text1.size() + 1, vector<int>(text2.size() + 1, 0));
        for (int i = 1; i <= text1.size(); i++) {
            for (int j = 1; j <= text2.size(); j++) {
                if (text1[i - 1] == text2[j - 1]) {
                    dp[i][j] = dp[i - 1][j - 1] + 1;   // 尾字符相同，各退一步 + 1
                } else {
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1]);
                }
            }
        }
        return dp[text1.size()][text2.size()];
    }
};""",
}

# void 型题的扫描器误报：python/go 原地修改无返回值属正常，当前内容已验真完整
VOID_COMPLETE = {("48", "python"), ("48", "go"), ("73", "python"), ("73", "go"),
                 ("75", "python"), ("75", "go"), ("114", "python"), ("114", "go"),
                 ("283", "python"), ("283", "go"), ("189", "python"), ("189", "go")}


def strip_noise(line):
    line = re.sub(r'"[^"]*"', '""', line)
    line = re.sub(r"'[^']*'", "''", line)
    return re.sub(r"//.*$", "", line)


def signature_ok(code, lang):
    """完整性签名：括号平衡；非 void 主实现须含 return。"""
    lines = [strip_noise(l) for l in code.splitlines() if l.strip()]
    if not lines:
        return False
    depth = sum(x.count("{") - x.count("}") + x.count("[") - x.count("]")
                + x.count("(") - x.count(")") for x in lines)
    if depth != 0:
        return False
    if any("void" in x for x in lines[:4]):
        return True
    return any("return" in x for x in lines)


def candidates_by_lang(text):
    """extract_carl 的忠实变体（同 LANG_HEADER/NUM_LINE/looks_like_code 状态机），
    唯一差别：不做"每语言第一块"截断，保留全部候选块——
    思路区的伪代码/片段排在完整实现之前，由调用方取第一个通过完整性签名的候选。"""
    out = {}
    cur_lang = None
    buf = []

    def flush():
        nonlocal buf
        code = "\n".join(l.removeprefix("    ") for l in buf).strip("\n").strip()
        code = code.replace("\xa0", " ")
        _lines = code.split("\n")
        while _lines and re.match(r"^[（(【]?[^\x00-\x7F]", _lines[0]):
            _lines.pop(0)
        code = "\n".join(_lines).strip()
        if code and cur_lang and looks_like_code(code, cur_lang):
            out.setdefault(cur_lang, []).append(code)
        buf = []

    for line in text.split("\n"):
        h = LANG_HEADER.match(line)
        if h:
            flush()
            raw = h.group(1).lower()
            cur_lang = NORM.get(raw.replace("c语言", "c").replace("golang", "go"))
            if raw == "c语言":
                cur_lang = "c"
            continue
        if line.startswith("## "):
            title = line[3:].strip()
            if any(k in title for k in ("思路", "方法", "解法", "题意", "算法")):
                flush()
                cur_lang = "cpp"      # carl 主思路区代码默认 C++
            elif any(k in title for k in ("其他语言", "公开课", "总结")):
                flush()
                cur_lang = None
            continue
        if line.startswith("    ") and line.strip():
            buf.append(line)
        elif not line.strip():
            buf.append("")            # 代码块内部空行：延续收集（本轮修复的核心）
        elif NUM_LINE.match(line):
            continue                  # 行号噪声行：跳过且不断开
        else:
            flush()
    flush()
    return out


def main():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    name_by_pid = {}
    for f in CARL.glob("*.md"):
        m = re.match(r"^(\d{4})\.", f.name)
        if m:
            name_by_pid[int(m.group(1))] = f

    reextract, hand, skipped, failed = [], [], [], []
    for pid, langs in data.items():
        for lang, item in langs.items():
            if not isinstance(item, dict) or not item.get("code"):
                continue
            key = (pid, lang)
            if key in VOID_COMPLETE:
                skipped.append(key)
                continue
            if signature_ok(item["code"], lang):
                continue  # 本就完整（含 f72676ce 修复的条目），不动
            fresh = ""
            note = name_by_pid.get(int(pid)) if pid.isdigit() else None
            if note is not None:
                for cand in candidates_by_lang(note.read_text(encoding="utf-8-sig")).get(lang, []):
                    if signature_ok(cand, lang):
                        fresh = cand
                        break
            if fresh and signature_ok(fresh, lang):
                item["code"] = fresh
                reextract.append(key)
            elif key in HAND:
                item["code"] = HAND[key]
                item["source"] = HAND_SOURCE
                hand.append(key)
            else:
                failed.append(key)

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"重抽恢复 {len(reextract)} | 手写补齐 {len(hand)} | void 完整保留 {len(skipped)} | 失败 {len(failed)}")
    if failed:
        print("失败清单:", sorted(failed))
        sys.exit(1)
    # 全库复验：任何截断签名残留都算失败（void 型误报集已人工验真完整，豁免）
    bad = []
    for pid, langs in json.loads(OUT.read_text(encoding="utf-8")).items():
        for lang, item in langs.items():
            if not isinstance(item, dict) or not item.get("code"):
                continue
            if (pid, lang) in VOID_COMPLETE:
                continue
            if not signature_ok(item["code"], lang):
                bad.append((pid, lang))
    print("全库签名复验:", "通过（0 处截断签名）" if not bad else f"仍有 {len(bad)} 处: {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
