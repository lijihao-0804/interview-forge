# =============================================================================
# build_hot100.py —— Hot100 学习站的内容生成器（整条构建链的主入口）
# -----------------------------------------------------------------------------
# 作用：把“原始笔记 + 元数据表 + 扩展题源”三类输入，生成为学习站的整棵
#       Markdown 树（README/总览/专题/题解/模板/面板），并串起后续两个构建脚本。
#
# 输入（本文件的全部数据入口）：
#   1) SOURCE 目录（hot100/笔记）：逐题学习笔记（[0-9][0-9]-*.md 命名）
#      + 01-基础 素材 + 可视化 HTML 组件 + pic 图库，独立于本仓库维护；
#   2) PROBLEM_TSV：100 道题的核心元数据表（题号|题名|专题|主方法|时间|空间|不变量）；
#   3) EXTENSION_SOURCE 目录（06-扩展题源）：后续新增题的可重复生成正文；
#   4) 人工维护的补充数据：LEETCODE_SLUGS（力扣链接）、VARIANT_LABELS（多解法命名）、
#      MISSING_STATEMENTS（缺题面兜底）、EASY/HARD（难度白名单）。
#   日常改题只需要编辑 PROBLEM_TSV 与 06-扩展题源，不必触碰本仓库其它文件。
#
# 输出（全部写入学习站根目录，路径由各 render_* 函数决定）：
#   00-总览/（学习路线、模式地图、复习清单、复盘模板）· 01-基础/（Java 速查等 5 篇）
#   · 02-专题/（17 个专题页）· 03-题解/（每题一页，按题号-题名.md 命名）
#   · 04-模板/（算法模板等 3 篇）· 05-可视化/ · 99-原稿归档/ · README.md
#   · index.html（本地学习站首页，由 render_dashboard 注入 JSON 生成）
#   · tools/build-summary.json（构建摘要）。
#
# 构建管线（build() 自底向上：先数据后页面、先静态后动态）：
#   ① extract_original_sections   收集源笔记题解段
#   ② copy_source_materials       复制基础素材 / 原稿归档 / 可视化
#   ③ render_problem_pages        逐题生成 03-题解 页面
#   ④ render_topics / render_readme / render_overview_files / render_templates
#                                 生成专题、README、总览、模板四类导航页
#   ⑤ render_dashboard            注入 JSON 生成 index.html
#   ⑥ 末尾两个 subprocess：先后调用同目录的 build_library.py（构建 SQLite
#      本地学习库）与 build_html_site.py（Markdown 编译为静态 HTML 站点、
#      含页尾交互演示）；check=True，任一脚本失败即中断整条链（快速失败）。
#   常用命令：python tools/build_hot100.py 一键执行；python tools/check_hot100.py 事后校验。
# =============================================================================
# from __future__ import annotations：把类型注解延迟为字符串求值，
# 使 list[...] 这类新式注解语法在低版本 Python 上也能通过编译。
from __future__ import annotations

import html
import hashlib
import json
import re
import shutil
import textwrap
import subprocess
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

import build_cache
# 标准库即够：json 序列化面板数据，re 做正文/标题清洗，subprocess 串起
# 后续 build_library / build_html_site 两个构建脚本，pathlib 统一路径操作。


# ROOT：学习站根目录（本文件所在 tools/ 的上一级）。
ROOT = Path(__file__).resolve().parents[1]
# SOURCE：Hot 100 逐题原始笔记目录，位于仓库 books/hot100（与其它书籍源同级、统一归档）。
# 改题时通常只动这里的 md；缺失时构建会在第一步就明确报错。
_SOURCE_CANDIDATES = (ROOT / "books" / "hot100", ROOT / "hot100" / "笔记")
SOURCE = next((p for p in _SOURCE_CANDIDATES if p.is_dir()), _SOURCE_CANDIDATES[0])
# EXTENSION_SOURCE：学习站内的新增题目正文目录（见文件头总述），与源笔记互为补充。
EXTENSION_SOURCE = ROOT / "books" / "hot100" / "06-扩展题源"


# 17 个专题的元数据表，每个元素是四元组：
#   (专题目录名, 专题显示名, 识别信号, 核心不变量)
# - 专题目录名：同时用作 02-专题/ 与 03-题解/ 下的文件夹名，两者必须一致
#   （render_topics 与 render_problem_pages 靠它对齐路径）；
# - 识别信号：看到什么题目特征该联想到本专题（写入专题页「识别信号」区块）；
# - 核心不变量：解题时必须始终成立的可证明性质（写入专题页与每道题页）。
# 列表顺序即专题导航顺序；render_topics / render_readme / render_overview_files 都遍历它生成输出。
CATEGORIES = [
    ("01-哈希表", "哈希表", "出现“快速查找、计数、分组、去重”时先想哈希结构。", "把已经处理过的信息压成可 O(1) 查询的键。"),
    ("02-双指针", "双指针", "数组有序、原地修改、两端关系或快慢节奏。", "每次移动都要能排除一批不可能的答案。"),
    ("03-滑动窗口", "滑动窗口", "连续区间、最长/最短、窗口内满足某个条件。", "右端负责纳入，左端只在不变量被破坏或答案可收缩时移动。"),
    ("04-子串", "子串", "连续子数组/子串的计数、最值或固定和。", "前缀和解决区间和，单调队列解决区间最值，可变窗口解决覆盖关系。"),
    ("05-普通数组", "普通数组", "区间合并、原地置换、前后缀信息、局部最优。", "先明确下标含义，再决定排序、原地标记或滚动状态。"),
    ("06-矩阵", "矩阵", "二维原地修改、按层遍历、从某个角落搜索。", "方向变化必须与边界收缩同步，原地标记要预留标记位。"),
    ("07-链表", "链表", "节点交换、区间反转、环、相交、缓存结构。", "改 next 前先保存后继；复杂操作优先使用虚拟头节点。"),
    ("08-二叉树", "二叉树", "子树信息、层级信息、搜索树有序性或路径关系。", "先判断答案来自向下传参、向上汇总，还是中序有序。"),
    ("09-图论", "图论", "连通块、扩散、依赖关系、前缀匹配。", "访问即标记；多源问题先统一入队；依赖关系看入度。"),
    ("10-回溯", "回溯", "枚举所有组合、排列、切分或棋盘方案。", "路径是当前选择，选择列表是下一步范围，返回前必须恢复现场。"),
    ("11-二分查找", "二分查找", "有序、单调、答案可判定。", "先写清搜索区间语义，再让每个分支严格缩小区间。"),
    ("12-栈", "栈", "括号匹配、嵌套结构、下一个更大/更小、延迟结算。", "栈中保留尚未被解决的元素；弹栈时完成结算。"),
    ("13-堆", "堆", "动态 Top K、数据流中位数、多路合并。", "堆只维护当前真正需要的候选集合。"),
    ("14-贪心", "贪心", "每一步能安全丢弃历史、维护最远边界或局部最优。", "必须说明局部选择为何不会损失全局最优。"),
    ("15-动态规划", "动态规划", "最优值、方案数、可达性，且子问题重复。", "状态含义、转移来源、初始化、遍历顺序缺一不可。"),
    ("16-多维动态规划", "多维动态规划", "两个序列、二维网格或区间状态。", "每个维度必须对应一个明确前缀、位置或区间。"),
    ("17-技巧", "技巧", "位运算、投票、三路划分、排列、隐式链表。", "先识别题目隐藏的数据结构或数学不变量。"),
]

# 以“专题显示名”为键建索引（值为 目录名/信号/不变量 三元组），
# 供 parse_problems 把 PROBLEM_TSV 第 3 列的专题名直接映射回目录文件夹名。
CATEGORY_BY_NAME = {name: (folder, signal, invariant) for folder, name, signal, invariant in CATEGORIES}


# 100 道题的元数据主表（| 分隔的 TSV 文本块）。每行恰 7 列：
#   题号|题名|专题显示名|主方法一句话|时间复杂度|空间复杂度|核心不变量
# 第 7 列不变量被逐字写入每道题页的「核心不变量」区块，是全站最核心的“学一句话”；
# 行顺序即全站题目顺序（题页相邻学习、专题页练习顺序、复习清单顺序都沿用它）。
PROBLEM_TSV = r"""
1|两数之和|哈希表|一遍哈希|O(n)|O(n)|先查 target - x，再记录 x，避免元素与自身匹配
49|字母异位词分组|哈希表|排序签名 + 哈希分组|O(n·k log k)|O(n·k)|异位词必须映射成同一个稳定签名
128|最长连续序列|哈希表|哈希集合找序列起点|O(n)|O(n)|只从不存在 x - 1 的数字开始向右扩展
283|移动零|双指针|快慢指针原地交换|O(n)|O(1)|slow 始终指向下一个非零元素应放的位置
11|盛最多水的容器|双指针|相向双指针|O(n)|O(1)|移动短板才可能抵消宽度缩小带来的损失
15|三数之和|双指针|排序 + 固定一点 + 双指针|O(n²)|O(log n)|固定第一数后夹逼，并在三层位置正确去重
42|接雨水|双指针|左右最大值双指针|O(n)|O(1)|较低一侧的蓄水量已由该侧最大边界确定
3|无重复字符的最长子串|滑动窗口|可变滑动窗口|O(n)|O(字符集)|窗口内始终无重复，left 只能向右不能回退
438|找到字符串中所有字母异位词|滑动窗口|定长窗口 + 频次表|O(n)|O(字符集)|窗口长度固定，频次完全匹配时记录左端点
560|和为 K 的子数组|子串|前缀和 + 频次哈希|O(n)|O(n)|当前前缀为 pre 时，需要此前出现过 pre - k
239|滑动窗口最大值|子串|单调队列|O(n)|O(k)|队列保存有效下标，且对应值从队首到队尾递减
76|最小覆盖子串|子串|可变滑动窗口 + 计数|O(m+n)|O(字符集)|右扩直到满足，左缩直到刚好不满足
53|最大子数组和|普通数组|Kadane 动态规划|O(n)|O(1)|前一段和为负时不值得被当前位置继承
56|合并区间|普通数组|排序 + 线性合并|O(n log n)|O(log n)|每个新区间只需和结果中的最后一个区间比较
189|轮转数组|普通数组|三次反转|O(n)|O(1)|整体反转后再分别恢复前 k 段和后 n-k 段的顺序
238|除自身以外数组的乘积|普通数组|前缀积 + 后缀积|O(n)|O(1) 除答案外|答案先保存左侧乘积，再乘滚动的右侧乘积
41|缺失的第一个正数|普通数组|原地哈希 / 循环置换|O(n)|O(1)|值 x 的理想位置是下标 x - 1
73|矩阵置零|矩阵|首行首列原地标记|O(mn)|O(1)|首行首列兼作标记，另存它们自身是否需要清零
54|螺旋矩阵|矩阵|四边界模拟|O(mn)|O(1)|走完一条边立刻收缩对应边界，并防止重复访问
48|旋转图像|矩阵|转置 + 每行反转|O(n²)|O(1)|转置完成行列交换，水平翻转完成顺时针旋转
240|搜索二维矩阵 II|矩阵|右上角阶梯搜索|O(m+n)|O(1)|每次比较都能排除一整行或一整列
160|相交链表|链表|双指针换头|O(m+n)|O(1)|两指针各走 A+B 后自然对齐，比较的是节点引用
234|回文链表|链表|找中点 + 反转后半段|O(n)|O(1)|只比较等长的两半，结束后恢复链表更稳妥
206|反转链表|链表|迭代三指针|O(n)|O(1)|修改 next 前必须先保存原来的后继
141|环形链表|链表|Floyd 快慢指针|O(n)|O(1)|有环时快指针一定会在环内追上慢指针
142|环形链表 II|链表|Floyd 相遇后重置|O(n)|O(1)|相遇后一个回到头部，同速再走会在入口相遇
21|合并两个有序链表|链表|虚拟头节点 + 尾插|O(m+n)|O(1)|tail 始终指向已合并部分的最后一个节点
2|两数相加|链表|逐位模拟 + 进位|O(max(m,n))|O(1) 除答案外|循环条件必须包含两个链表和最后的 carry
19|删除链表的倒数第 N 个结点|链表|快慢指针 + 虚拟头|O(n)|O(1)|fast 先走 n 步，随后保持固定间距
24|两两交换链表中的节点|链表|虚拟头 + 局部重连|O(n)|O(1)|每轮保存下一组入口，再按固定顺序改三条指针
25|K 个一组翻转链表|链表|分组检测 + 区间反转|O(n)|O(1)|不足 k 个保持原样；先确定组尾再反转
138|随机链表的复制|链表|节点穿插复制|O(n)|O(1) 除答案外|复制节点紧跟原节点，random 可由 original.random.next 得到
148|排序链表|链表|归并排序|O(n log n)|O(1) 可用自底向上|链表适合通过断链、归并完成稳定排序
23|合并 K 个升序链表|链表|最小堆多路归并|O(N log k)|O(k)|堆中始终只放每条链表当前最小的头节点
146|LRU 缓存|链表|哈希表 + 双向链表|O(1)|O(capacity)|哈希负责定位，双链表负责 O(1) 调整新旧顺序
94|二叉树的中序遍历|二叉树|递归 / 栈 / Morris|O(n)|O(h)，Morris 为 O(1)|中序顺序是左—根—右，BST 中对应升序
104|二叉树的最大深度|二叉树|后序 DFS|O(n)|O(h)|节点深度等于左右子树最大深度加一
226|翻转二叉树|二叉树|递归交换左右子树|O(n)|O(h)|每个节点只做一件事：交换左右孩子
101|对称二叉树|二叉树|镜像递归 / 队列|O(n)|O(h)|成对比较外侧与外侧、内侧与内侧
543|二叉树的直径|二叉树|后序高度 + 全局答案|O(n)|O(h)|经过当前节点的直径是左高加右高
102|二叉树的层序遍历|二叉树|BFS 分层|O(n)|O(w)|每轮先固定队列长度，它就是当前层节点数
108|将有序数组转换为二叉搜索树|二叉树|分治取中点|O(n)|O(log n)|中点作根可同时保证 BST 有序与高度平衡
98|验证二叉搜索树|二叉树|上下界递归 / 中序|O(n)|O(h)|约束作用于整棵子树，不只是父子节点
230|二叉搜索树中第 K 小的元素|二叉树|中序遍历提前停止|O(h+k)|O(h)|BST 中序序列严格递增
199|二叉树的右视图|二叉树|分层 BFS / 右优先 DFS|O(n)|O(h)|每一层只记录最后访问或最先访问的右侧节点
114|二叉树展开为链表|二叉树|逆前序递归|O(n)|O(h)|按右—左—根处理，prev 始终是当前节点应接的后继
105|从前序与中序遍历序列构造二叉树|二叉树|前序指针 + 中序索引表|O(n)|O(n)|前序决定根，中序决定左右子树边界
437|路径总和 III|二叉树|前缀和 DFS|O(n)|O(h)|当前前缀为 sum 时，祖先前缀 sum-target 的次数就是新增路径数
236|二叉树的最近公共祖先|二叉树|后序递归|O(n)|O(h)|左右子树各找到一个目标时，当前节点就是最近公共祖先
124|二叉树中的最大路径和|二叉树|后序最大贡献|O(n)|O(h)|向上只能贡献一条支路，更新答案时可以同时取左右支路
200|岛屿数量|图论|DFS / BFS 洪泛|O(mn)|O(mn)|发现陆地就立刻标记并扩展整座岛
994|腐烂的橘子|图论|多源 BFS|O(mn)|O(mn)|所有初始腐烂橘子同时作为第 0 分钟入队
207|课程表|图论|Kahn 拓扑排序|O(V+E)|O(V+E)|每学完一门课就减少后继入度，最终处理数应等于课程数
208|实现 Trie|图论|前缀树|O(总字符数)|O(总字符数)|路径表示前缀，结束标记区分完整单词与前缀
46|全排列|回溯|路径 + used 数组|O(n·n!)|O(n)|同一条路径中每个元素只能使用一次
78|子集|回溯|起点索引回溯|O(n·2ⁿ)|O(n)|每个递归节点本身就是一个合法子集
17|电话号码的字母组合|回溯|按位选择字符|O(4ⁿ)|O(n)|递归层数对应电话号码下标
39|组合总和|回溯|排序 + 可重复选择|指数级|O(target)|允许复用当前数，因此下一层仍从 i 开始
22|括号生成|回溯|计数约束剪枝|O(Cₙ)|O(n)|任意前缀中右括号数不能超过左括号数
79|单词搜索|回溯|网格 DFS + 原地标记|O(mn·4ᴸ)|O(L)|一个格子在同一路径中只能使用一次，返回前恢复
131|分割回文串|回溯|切割回溯 + 回文判断|O(n·2ⁿ)|O(n²)|只有当前切片是回文串时才进入下一层
51|N 皇后|回溯|列与两条对角线约束|O(n!)|O(n)|row-col 与 row+col 分别唯一标识两类对角线
35|搜索插入位置|二分查找|lower_bound|O(log n)|O(1)|寻找第一个大于等于 target 的下标
74|搜索二维矩阵|二分查找|二维下标映射一维|O(log(mn))|O(1)|mid / n 得行，mid % n 得列
33|搜索旋转排序数组|二分查找|识别有序半边|O(log n)|O(1)|每轮至少有一半有序，再判断 target 是否落在其中
153|寻找旋转排序数组中的最小值|二分查找|mid 与 right 比较|O(log n)|O(1)|nums[mid] > nums[right] 时最小值一定在右侧
4|寻找两个正序数组的中位数|二分查找|短数组上二分分割线|O(log min(m,n))|O(1)|正确分割满足左半最大值不大于右半最小值
20|有效的括号|栈|栈保存期待的右括号|O(n)|O(n)|遇到右括号时必须与栈顶期待值一致
155|最小栈|栈|数据栈 + 最小值栈|O(1)|O(n)|辅助栈顶始终是当前所有元素的最小值
394|字符串解码|栈|保存外层次数与字符串|O(n)|O(n)|遇到 [ 保存现场，遇到 ] 恢复上一层并展开当前层
739|每日温度|栈|单调递减索引栈|O(n)|O(n)|栈内下标对应温度递减，升温时批量结算
84|柱状图中最大的矩形|栈|单调递增栈 + 哨兵|O(n)|O(n)|出栈时当前柱子的左右第一个更矮边界已经确定
232|用栈实现队列|栈|输入栈 + 输出栈|均摊 O(1)|O(n)|输出栈为空时才把输入栈全部倒入
215|数组中的第K个最大元素|堆|大小为 k 的小顶堆 / 快选|O(n log k)|O(k)|堆顶始终是当前前 k 大中的最小者
347|前 K 个高频元素|堆|频次表 + 小顶堆|O(n log k)|O(n)|堆按频次比较，只保留频次最高的 k 个键
295|数据流的中位数|堆|大顶堆 + 小顶堆|插入 O(log n)，查询 O(1)|O(n)|两堆元素数之差不超过一，且左堆所有值不大于右堆
121|买卖股票的最佳时机|贪心|维护历史最低价|O(n)|O(1)|卖出当天只需要此前最低买入价
55|跳跃游戏|贪心|维护最远可达位置|O(n)|O(1)|遍历位置必须不超过 farthest
45|跳跃游戏 II|贪心|分层最远边界|O(n)|O(1)|到达当前层边界时才增加一步并更新下一层边界
763|划分字母区间|贪心|最后出现位置|O(n)|O(字符集)|当前片段结束位置是片段内所有字符最后位置的最大值
70|爬楼梯|动态规划|滚动 Fibonacci|O(n)|O(1)|到第 i 阶只能来自 i-1 或 i-2
118|杨辉三角|动态规划|逐行递推|O(n²)|O(n²)|内部元素来自上一行左上与正上方
198|打家劫舍|动态规划|选或不选滚动状态|O(n)|O(1)|dp[i] 只比较跳过当前与偷当前两种选择
279|完全平方数|动态规划|完全背包|O(n√n)|O(n)|dp[i] 从所有不超过 i 的平方数转移
322|零钱兑换|动态规划|完全背包最小值|O(amount·coins)|O(amount)|正序遍历容量允许同一枚硬币重复使用
139|单词拆分|动态规划|前缀可达性|O(n²)|O(n)|dp[i] 表示前 i 个字符是否可由字典组成
300|最长递增子序列|动态规划|DP / 贪心二分|O(n log n)|O(n)|tails[len] 保存该长度递增子序列最小可能结尾
152|乘积最大子数组|动态规划|同时维护最大积与最小积|O(n)|O(1)|负数会交换最大与最小角色
416|分割等和子集|动态规划|0-1 背包|O(n·target)|O(target)|容量倒序保证每个数字只使用一次
32|最长有效括号|动态规划|以右括号结尾的 DP|O(n)|O(n)|dp[i] 只表示必须以 i 结尾的最长有效长度
62|不同路径|多维动态规划|网格路径计数|O(mn)|O(n)|当前位置方案数来自上方与左方
64|最小路径和|多维动态规划|网格最小代价|O(mn)|O(1) 可原地|当前位置最小代价来自上方和左方较小者
5|最长回文子串|多维动态规划|区间 DP / 中心扩展|O(n²)|O(n²)，中心扩展 O(1)|两端字符相同且内部是回文，当前区间才是回文
1143|最长公共子序列|多维动态规划|双序列 DP|O(mn)|O(mn)|字符相同取左上加一，否则取上方与左方最大值
72|编辑距离|多维动态规划|双序列 DP|O(mn)|O(mn)|最后字符相同不付代价，否则从增删改三种操作取最小
136|只出现一次的数字|技巧|异或消去|O(n)|O(1)|x xor x = 0，且 0 xor x = x
169|多数元素|技巧|Boyer-Moore 投票|O(n)|O(1)|不同元素两两抵消后，多数元素仍会剩下
75|颜色分类|技巧|荷兰国旗三指针|O(n)|O(1)|[0,left) 是 0，[left,i) 是 1，(right,n) 是 2
31|下一个排列|技巧|找拐点、交换、反转后缀|O(n)|O(1)|从右侧找到仍可增大的最靠右位置，并使用最小增量
287|寻找重复数|技巧|Floyd 隐式链表|O(n)|O(1)|把下标到数值看作 next 指针，重复值就是环入口
"""


# 难度表：仅收录“简单”“困难”两个白名单集合，不在其中的题号一律定为“中等”。
# 难度为人工核定值（不一定等于力扣当前标签），写入题页元信息表供快速筛选。
EASY = {1, 20, 21, 35, 70, 94, 101, 104, 108, 118, 121, 136, 141, 160, 169, 206, 226, 232, 234, 283}
HARD = {4, 23, 25, 32, 41, 42, 51, 72, 76, 84, 124, 239, 295}


def parse_problems() -> list[dict[str, object]]:
    """解析 PROBLEM_TSV，把 | 分隔的元数据行转为有序的题目字典列表。

    输入：模块常量 PROBLEM_TSV；输出：list[dict]，键为
    id/title/category/folder/method/time/space/invariant/difficulty。
    返回列表保持 TSV 行序 —— 它是全站唯一的“题目顺序”来源：
    题页相邻学习、专题页练习顺序、复习清单顺序都沿用它。
    依赖 CATEGORY_BY_NAME 与 EASY/HARD；模块加载时即被调用一次，
    结果缓存为 PROBLEMS / PROBLEM_BY_ID 供所有 render_* 函数共享。
    """
    # 逐行解析：split("|", 6) 只切前 6 个分隔符，因此第 7 列“不变量”内部
    # 可以自由出现 | 而不影响切分。
    rows: list[dict[str, object]] = []
    for raw in PROBLEM_TSV.strip().splitlines():
        pid, title, category, method, time, space, invariant = raw.split("|", 6)
        number = int(pid)
        # 由专题显示名反查目录文件夹名（02-专题/03-题解 共用同一套目录命名）。
        folder = CATEGORY_BY_NAME[category][0]
        # 难度判定：命中 EASY/HARD 白名单取对应级别，否则默认“中等”。
        difficulty = "简单" if number in EASY else "困难" if number in HARD else "中等"
        rows.append({
            "id": number,
            "title": title,
            "category": category,
            "folder": folder,
            "method": method,
            "time": time,
            "space": space,
            "invariant": invariant,
            "difficulty": difficulty,
        })
    # 保留 Hot 100 作为基础集合，同时允许后续继续追加题目。
    # 防御性断言（fail-fast）：题量下限 100；题号全局唯一，否则同名文件互相覆盖。
    assert len(rows) >= 100, len(rows)
    assert len({int(r["id"]) for r in rows}) == len(rows)
    return rows


# 模块加载即解析，形成同一份数据的两种视图：
#   PROBLEMS      —— 保持 TSV 顺序的列表（决定所有页面的渲染顺序）；
#   PROBLEM_BY_ID —— 题号 → 题目字典（供题号反查、build 统计新增题）。
PROBLEMS = parse_problems()


def _problems_source_hash() -> str:
    """render_problem_pages 的输入指纹：全部题解源文件 + 题目元数据（PROBLEMS）。

    任一源笔记/扩展题源/元数据表变化都会改变哈希，从而触发 100 道题页重建；
    全部未变时增量跳过。聚合哈希按文件名排序拼接，顺序稳定。
    """
    hasher = hashlib.sha256()
    for path in sorted(SOURCE.glob("[0-9][0-9]-*.md")):
        if path.name.startswith("00-"):
            continue
        hasher.update(path.read_bytes())
    for path in sorted(EXTENSION_SOURCE.glob("*.md")):
        hasher.update(path.read_bytes())
    hasher.update(json.dumps(PROBLEMS, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return hasher.hexdigest()
PROBLEM_BY_ID = {int(p["id"]): p for p in PROBLEMS}

# === 力扣原题链接数据 ===
# LEETCODE_BASE 是带 {slug} 占位符的 URL 模板，由 render_problem_pages 用
# format() 填充；LEETCODE_SLUGS 以题号为键保存每题 slug（题号与 PROBLEM_TSV
# 一一对应）。有 slug 的题页才会拼出“前往力扣原题验证 →”链接。
# 力扣原题链接：slug 已逐一联网核验（2026-08，100/100 有效）。
# 带 study-plan 参数会在力扣的 Hot 100 计划上下文中打开本题。
LEETCODE_BASE = "https://leetcode.cn/problems/{slug}/?envType=study-plan-v2&envId=top-100-liked"
LEETCODE_SLUGS: dict[int, str] = {
    1: "two-sum",
    49: "group-anagrams",
    128: "longest-consecutive-sequence",
    283: "move-zeroes",
    11: "container-with-most-water",
    15: "3sum",
    42: "trapping-rain-water",
    3: "longest-substring-without-repeating-characters",
    438: "find-all-anagrams-in-a-string",
    560: "subarray-sum-equals-k",
    239: "sliding-window-maximum",
    76: "minimum-window-substring",
    53: "maximum-subarray",
    56: "merge-intervals",
    189: "rotate-array",
    238: "product-of-array-except-self",
    41: "first-missing-positive",
    73: "set-matrix-zeroes",
    54: "spiral-matrix",
    48: "rotate-image",
    240: "search-a-2d-matrix-ii",
    160: "intersection-of-two-linked-lists",
    234: "palindrome-linked-list",
    206: "reverse-linked-list",
    141: "linked-list-cycle",
    142: "linked-list-cycle-ii",
    21: "merge-two-sorted-lists",
    2: "add-two-numbers",
    19: "remove-nth-node-from-end-of-list",
    24: "swap-nodes-in-pairs",
    25: "reverse-nodes-in-k-group",
    138: "copy-list-with-random-pointer",
    148: "sort-list",
    23: "merge-k-sorted-lists",
    146: "lru-cache",
    94: "binary-tree-inorder-traversal",
    104: "maximum-depth-of-binary-tree",
    226: "invert-binary-tree",
    101: "symmetric-tree",
    543: "diameter-of-binary-tree",
    102: "binary-tree-level-order-traversal",
    108: "convert-sorted-array-to-binary-search-tree",
    98: "validate-binary-search-tree",
    230: "kth-smallest-element-in-a-bst",
    199: "binary-tree-right-side-view",
    114: "flatten-binary-tree-to-linked-list",
    105: "construct-binary-tree-from-preorder-and-inorder-traversal",
    437: "path-sum-iii",
    236: "lowest-common-ancestor-of-a-binary-tree",
    124: "binary-tree-maximum-path-sum",
    200: "number-of-islands",
    994: "rotting-oranges",
    207: "course-schedule",
    208: "implement-trie-prefix-tree",
    46: "permutations",
    78: "subsets",
    17: "letter-combinations-of-a-phone-number",
    39: "combination-sum",
    22: "generate-parentheses",
    79: "word-search",
    131: "palindrome-partitioning",
    51: "n-queens",
    35: "search-insert-position",
    74: "search-a-2d-matrix",
    33: "search-in-rotated-sorted-array",
    153: "find-minimum-in-rotated-sorted-array",
    4: "median-of-two-sorted-arrays",
    20: "valid-parentheses",
    155: "min-stack",
    394: "decode-string",
    739: "daily-temperatures",
    84: "largest-rectangle-in-histogram",
    232: "implement-queue-using-stacks",
    215: "kth-largest-element-in-an-array",
    347: "top-k-frequent-elements",
    295: "find-median-from-data-stream",
    121: "best-time-to-buy-and-sell-stock",
    55: "jump-game",
    45: "jump-game-ii",
    763: "partition-labels",
    70: "climbing-stairs",
    118: "pascals-triangle",
    198: "house-robber",
    279: "perfect-squares",
    322: "coin-change",
    139: "word-break",
    300: "longest-increasing-subsequence",
    152: "maximum-product-subarray",
    416: "partition-equal-subset-sum",
    32: "longest-valid-parentheses",
    62: "unique-paths",
    64: "minimum-path-sum",
    5: "longest-palindromic-substring",
    1143: "longest-common-subsequence",
    72: "edit-distance",
    136: "single-number",
    169: "majority-element",
    75: "sort-colors",
    31: "next-permutation",
    287: "find-the-duplicate-number",
}

# 一题多解时的“解法命名表”：题号 → 各版本解法标题列表。
# render_problem_pages 发现某个题在源笔记里有多段解法时，优先用这里维护的
# 名字给每段编成“## 解法 N：<名字>”，避免把原稿的碎标题直接暴露给读者。
VARIANT_LABELS = {
    76: ["哈希计数版", "数组频次优化版"],
    94: ["迭代栈版", "递归版", "Morris O(1) 空间版"],
    98: ["上下界递归版", "中序遍历版"],
    101: ["递归镜像版", "迭代队列版"],
    148: ["自顶向下归并版", "自底向上 O(1) 空间版"],
    215: ["快速选择版", "小顶堆版"],
    300: ["O(n²) 动态规划版", "O(n log n) 贪心二分版"],
}


# 「术语净化」替换表（只换措辞、不改语义）：被 calm_language() 应用到每一份
# 最终正文 —— 把原稿里夸张、情绪化的说法换成中性的学术表达，
# 使全站措辞平稳一致、适合长期反复阅读（如“大厂→面试”“封神→加分”）。
CALM_REPLACEMENTS = {
    "大厂": "面试",
    "大神": "进阶",
    "神仙思路": "简洁思路",
    "生死局": "高频考点",
    "死亡": "关键",
    "夺命": "高频",
    "绝杀": "进阶",
    "变态": "高难",
    "降维打击": "优化思路",
    "封神": "加分",
    "灵魂拷问": "关键追问",
    "巅峰之作": "经典例题",
    "魔鬼": "关键",
}


def safe_name(text: str) -> str:
    """把任意字符串清洗成可安全用作文件名的形式。

    把 Windows 文件名非法字符（< > : " / \\ | ? *）替换为连字符 -，
    再去首尾空白并去掉末尾句点（Windows 不允许文件名以 . 结尾）。
    被 problem_filename 复用，保证生成的 .md/.html 文件名处处合法。
    """
    return re.sub(r'[<>:"/\\|?*]', "-", text).strip().rstrip(".")


def problem_filename(problem: dict[str, object]) -> str:
    """生成题页文件名：“题号(4 位补零)-题名.md”，如 0042-接雨水.md。

    命名规则集中在同一处：专题页、复习清单、dashboard 数据里的所有相对链接
    都必须与之精确一致，任何一处不一致都会产生 404。
    """
    return f"{int(problem['id']):04d}-{safe_name(str(problem['title']))}.md"


def write(path: Path, content: str) -> None:
    """统一写盘函数：UTF-8 编码、自动创建父目录、去掉末尾多余空白并保证以单个换行收尾。

    全站所有 Markdown/JSON/HTML 输出都经它写出，从而统一编码与文件末尾格式
    （后续 build_html_site 按行解析这些文件，格式一致性是它的前置条件）。
    """
    # 幂等建目录：03-题解/<专题>/ 这类层级不存在时自动创建，已存在则不报错。
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def extract_original_sections() -> dict[int, list[tuple[str, str, str]]]:
    """从源笔记抽取每道题的“解法段”并按题号归类 —— 整条链的第一道工序。

    输入：SOURCE 目录下所有 [0-9][0-9]-*.md（00- 开头的总览文件跳过），
         以及 EXTENSION_SOURCE 目录里的新增题文件；
    输出：dict[题号 → list[(小节标题, 正文, 来源文件名)]]；
         一个题号可对应多段（同一题的多个版本），供 render_problem_pages 并列渲染。
    切分原理：以“### 📝 <前缀>笔记：题号. 标题”三级标题为锚点，
    每个锚点到下一个锚点之间的区间就是该题的独立解法段 ——
    这样的切分让新增题目无需改动原始目录结构。
    """
    sections: dict[int, list[tuple[str, str, str]]] = defaultdict(list)
    # 锚点正则：允许 0~3 个前导空格，兼容“进阶算法笔记/算法避坑笔记/算法笔记”三种前缀；
    # 第 1 组捕获题号、第 2 组捕获小节标题（(?m) 多行模式 + ^ 行首锚定，逐行扫描）。
    heading = re.compile(
        r"(?m)^\s{0,3}###\s+📝\s+(?:(?:进阶算法|算法避坑|算法)笔记)：\s*(\d+)\.\s*(.+?)\s*$"
    )
    for path in sorted(SOURCE.glob("[0-9][0-9]-*.md")):
        if path.name.startswith("00-"):
            # 跳过 00- 开头的总览/索引类文件，它们不是逐题笔记。
            continue
        # utf-8-sig：兼容带 BOM 的原稿（Windows 记事本导出的 md 常带 BOM）。
        text = path.read_text(encoding="utf-8-sig")
        matches = list(heading.finditer(text))
        for index, match in enumerate(matches):
            pid = int(match.group(1))
            # 正文边界：当前锚点结束 到 下一个锚点（否则到文件末尾），保证一段只含一个解法区
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[match.end():end]
            # 存 (小节标题, 原始正文, 来源文件名)；来源文件名用于题页反查出处
            sections[pid].append((match.group(2).strip(), body, path.name))
    # 第二路输入：扩展题源（文件名必须形如 \d{4,}-xxx.md，题号至少 4 位，否则视为非题目文件跳过）。
    # 新增题目不必改动原始目录。文件名格式：四位题号-题名.md；
    # 文件正文直接从“### 题目与约束”等三级标题开始。
    for path in sorted(EXTENSION_SOURCE.glob("*.md")):
        match = re.match(r"^(\d{4,})-(.+)\.md$", path.name)
        if not match:
            continue
        pid = int(match.group(1))
        body = path.read_text(encoding="utf-8-sig").strip()
        # 空文件不占位，避免生成空的占位题页。
        if body:
            sections[pid].append((match.group(2).strip(), body, f"books/hot100/06-扩展题源/{path.name}"))
    return sections


def calm_language(text: str) -> str:
    """通用文本清洗：术语净化 + 版式规整 —— 写盘前的最后一道公共工序。

    输入/输出都是 Markdown 正文，只做字符串级整体替换、不改段落结构；
    被 normalize_original_body、copy_source_materials 等多处复用。
    """
    # 逐对执行净化替换（词对出现顺序即替换顺序，先出现的词优先被处理）。
    for old, new in CALM_REPLACEMENTS.items():
        text = text.replace(old, new)
    # 零宽空格 \u200b：AI 复制稿常见的隐藏字符，会破坏后续正则的 ^/行匹配，先整体剔除。
    text = text.replace("\u200b", "")
    # 去掉“整行 ≥5 个连字符”的分隔线（复制过程产生的装饰线，Markdown 会渲染成标题线）。
    text = re.sub(r"(?m)^\s*-{5,}\s*$", "", text)
    # 4 个及以上连续换行压成 2 个，统一段落间距（避免 HTML 渲染出现大片空白）。
    text = re.sub(r"\n{4,}", "\n\n", text)
    return text


def repair_indented_headings(text: str) -> str:
    """把误嵌在列表/缩进块中的标题和代码围栏恢复为块级结构。

    Python-Markdown 不解析列表内部的 fenced code；AI 复制稿也偶尔会给
    标题及其后整段内容统一加上若干空格。先把成对的缩进围栏整体提到
    行首，再处理缩进标题，保留代码内部和小节内部的相对缩进。
    """
    lines = text.splitlines()

    # 逐行两遍处理：第一遍救回“被整体缩进”的代码围栏，第二遍救回“被缩进”的标题行。
    index = 0
    while index < len(lines):
        # 围栏开头行：1 组 = 连续空格缩进；2 组 = ```/~~~ 及其长度；3 组允许语言标识等尾随字符。
        opening = re.match(r"^( +)(`{3,}|~{3,})[^`~]*$", lines[index])
        if opening is None:
            index += 1
            continue
        indent = len(opening.group(1))
        marker_char = opening.group(2)[0]
        marker_length = len(opening.group(2))
        closing = index + 1
        # 向后找闭合围栏：strip 后为“同字符且长度 ≥ 开头”的整行（容忍 ````` 式长收尾）。
        while closing < len(lines):
            candidate = lines[closing].strip()
            if re.fullmatch(rf"{re.escape(marker_char)}{{{marker_length},}}", candidate):
                break
            closing += 1
        if closing >= len(lines):
            # 找不到闭合行 = 残缺围栏，保持原样，继续向后扫描。
            index += 1
            continue
        prefix = " " * indent
        # 围栏块内所有带公共前缀的行统一去掉该前缀：围栏整体提到行首，块内相对缩进不变。
        for line_index in range(index, closing + 1):
            if lines[line_index].startswith(prefix):
                lines[line_index] = lines[line_index][indent:]
        index = closing + 1

    in_fence = False
    fence = ""
    index = 0
    # 第二遍：仅在围栏外扫描缩进标题；in_fence 状态机跟踪 ```/~~~ 配对，
    # 防止把代码块里的“ # 注释”误当标题处理。
    while index < len(lines):
        stripped = lines[index].lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            index += 1
            continue

        # 匹配 {2,} 空格起始的标题（# 后必须有内容），这一行就是待“提行首”的标题；
        # in_fence 为真时强制不匹配，直接跳过代码块内部。
        match = None if in_fence else re.match(r"^( {2,})(#{1,6}\s+\S.*)$", lines[index])
        if match is None:
            index += 1
            continue

        indent = len(match.group(1))
        end = index + 1
        # 把其后“缩进不小于标题”的连续行视为同一小节一并恢复：空行跳过，缩进变浅即停。
        while end < len(lines):
            if not lines[end].strip():
                end += 1
                continue
            leading = len(lines[end]) - len(lines[end].lstrip(" "))
            if leading < indent:
                break
            end += 1
        prefix = " " * indent
        # 小节内同样只去掉公共前缀，保留代码示例等内部相对缩进。
        for line_index in range(index, end):
            if lines[line_index].startswith(prefix):
                lines[line_index] = lines[line_index][indent:]
        index = end
    return "\n".join(lines)


def normalize_original_body(body: str) -> str:
    """把一段源笔记“解法正文”规整为学习站统一格式的题页正文。

    输入：extract_original_sections 抽出的某个解法段正文；
    输出：清洗后的正文，标题统一为约定三级结构：
        题目与约束 / 思路推导 / Java 实现 / 复杂度 / 易错点与扩展（/ 补充：…）。
    处理链（顺序有讲究，见各步注释）：
      calm_language（术语净化）→ textwrap.dedent（去公共缩进）
      → repair_indented_headings（恢复块级结构）→ 损坏强调修复
      → 本地图片提示替换 → emoji 标题归一化（replacements 表）→ 标题降级。
    它是 render_problem_pages 渲染每段解法前的必经步骤，输出被
    split_problem_statement 继续拆分；check_hot100 的格式检查也以它为准。
    """
    # 部分 AI 原稿把整个题解缩进了 2～5 个空格，Markdown 会将其误判为代码块。
    # 先消除整段公共缩进，再做标题清洗；不会改变代码围栏内部的相对缩进。
    # 顺序说明：calm_language 只动字符不动缩进；dedent 只去“公共”前缀，
    # 因此嵌套列表、代码示例的 4 空格相对缩进不受影响；围栏/标题修复放最后。
    body = repair_indented_headings(textwrap.dedent(calm_language(body)))
    # 修复原稿中由复制/转义产生的损坏强调标记，例如 \*\*核心\*\* 与 \**文字**。
    # 损坏强调修复：去掉“被意外写进原文”的反斜杠转义星号（如 \*\*核心\*\*、\**文字**），
    # 否则 Markdown 渲染会输出裸星号而不是粗体（这两处替换只影响这类反斜杠残迹）。
    body = body.replace(r"\*\*", "**").replace(r"\**", "**")
    # 失效图片提示替换：匹配“整行是本地绝对路径图片”（![图](C:\xxx\yyy.png)）并换成
    # 统一提示语 —— 源笔记本地图片未随站点迁移，留着会渲染成裂图；
    # 本题可视化演示已由页尾「交互演示」组件另行提供。
    body = re.sub(
        r"(?m)^\s*!\[[^\]]*\]\([A-Za-z]:\\[^)]+\)\s*$",
        "> 笔记中的本地图片未随迁；本题的可视化演示位于页尾「交互演示」部分。",
        body,
    )
    # ---- emoji 标题归一化表（整表按顺序逐条执行 re.sub）----
    # 目的：把原稿里“emoji 开头、单词/加粗/列表/标题等写法五花八门”的段落标题
    # 统一成站点约定的三级标题。每条正则都带 (?m) 且 ^ 锚定行首，只命中整行、
    # 不误伤正文；归一化之后：
    #   1) split_problem_statement 得以稳定切出“### 题目与约束”；
    #   2) check_hot100 的“残留 emoji 整理标题”检查才能通过。
    replacements = [
        # —— 📌 核心题意 / 题目类 → “### 题目与约束”（兼容列表项、加粗、# 标题三种写法）——
        (r"(?m)^\s*[-*]\s*\*\*📌\s*核心题意\s*\*\*：?\s*$", "### 题目与约束"),
        (r"(?m)^\s*\*\*📌\s*核心题意\s*\*\*：?\s*$", "### 题目与约束"),
        (r"(?m)^\s*#{1,4}\s*📌\s*核心题意\s*[:：]?\s*$", "### 题目与约束"),
        # —— 📌 核心思想/核心概念、🧠 思考过程/逻辑推演 → “### 思路推导” ——
        # “核心思想[^*]*”容忍标题里夹带说明文字（如“核心思想：xxx”），只要不含 * 就整体归并。
        (r"(?m)^\s*[-*]\s*\*\*📌\s*核心思想[^*]*\*\*：?\s*$", "### 思路推导"),
        (r"(?m)^\s*[-*]\s*\*\*📌\s*核心概念[^*]*\*\*：?\s*$", "### 思路推导"),
        (r"(?m)^\s*[-*]\s*\*\*🧠\s*思考过程\s*\*\*：?\s*$", "### 思路推导"),
        (r"(?m)^\s*\*\*🧠\s*思考过程\s*\*\*：?\s*$", "### 思路推导"),
        (r"(?m)^\s*#{1,4}\s*🧠\s*思考过程\s*[:：]?\s*$", "### 思路推导"),
        (r"(?m)^\s*#{1,4}\s*🧠\s*\d*[.、]?\s*逻辑推演[^*：:]*[:：]?\s*$", "### 思路推导"),
        (r"(?m)^\s*[-*]\s*\*\*🧠\s*[^*]*\*\*：?\s*$", "### 思路推导"),
        # —— 🛠️ Java 代码 → “### Java 实现”（保留括号/后缀限定词，如“Java 实现（迭代版）”）——
        (r"(?m)^\s*[-*]\s*\*\*🛠️\s*Java\s*[^*：:]*?代码([^*：:]*?)\s*\*\*：?\s*$", r"### Java 实现\1"),
        (r"(?m)^\s*\*\*🛠️\s*Java\s*([^*：:]*?)\s*\*\*：?\s*$", r"### Java 实现\1"),
        (r"(?m)^\s*#{1,4}\s*🛠️\s*Java\s*([^*：:]*?)\s*[:：]?\s*$", r"### Java 实现\1"),
        # —— 兜底：任何其它 🛠️ 开头的“列表项加粗标题”（非 Java）也归入思路推导 ——
        (r"(?m)^\s*[-*]\s*\*\*🛠️\s*(?!Java)[^*]*\*\*：?\s*$", "### 思路推导"),
        # —— ⏱️ 复杂度分析 → “### 复杂度”（兼容 “Complexity 复杂度分析” 双语写法）——
        (r"(?m)^\s*[-*]\s*\*\*⏱️\s*(?:Complexity\s*)?复杂度分析[^*]*\*\*：?\s*$", "### 复杂度"),
        (r"(?m)^\s*\*\*⏱️\s*(?:Complexity\s*)?复杂度分析[^*]*\*\*：?\s*$", "### 复杂度"),
        (r"(?m)^\s*#{1,4}\s*⏱️\s*(?:Complexity\s*)?复杂度分析[^*]*[:：]?\s*$", "### 复杂度"),
        # —— 💡 易错点 / 掌握它：四级标题提升为约定三级标题 ——
        (r"(?m)^####\s+💡\s*面试避坑与考点拓展(.*)$", r"### 易错点与扩展\1"),
        (r"(?m)^####\s+💡\s*掌握它(.*)$", r"### 补充：掌握它\1"),
        # —— 其余“### 🛠️ xxx”通用标题：只剥掉 emoji 前缀，保留原文字 ——
        (r"(?m)^###\s+🛠️\s*(.*)$", r"### \1"),
    ]
    for pattern, replacement in replacements:
        body = re.sub(pattern, replacement, body)
    # 已知原稿漏掉了这句话末尾的强调闭合符；在生成阶段修复，避免残留 Markdown。
    # 属“原稿已知缺陷的一次性修补”：与上面的通用规则分开维护，避免误伤其它题目的正文。
    body = body.replace(
        "**水是从短板溢出的，只要确认了哪边是绝对的短板，就可以直接结算那一列的水量。",
        "**水是从短板溢出的，只要确认了哪边是绝对的短板，就可以直接结算那一列的水量。**",
    )
    # 原稿内部偶尔出现与页面主结构平级的三级标题；统一压到三级或四级。
    # 降级规则（防页面层级混乱，白名单与页面结构强绑定）：
    #   “# ” / “## ”：题页正文不允许页级标题，一级/二级一律压成三级；
    #   “### ”：仅白名单标题（题目与约束/思路推导/Java 实现/复杂度/易错点与扩展/补充：）
    #           保留三级 —— split_problem_statement 与页面结构都依赖它们；
    #           其余原稿三级小节降为四级，一眼看出是正文内的细分小节。
    lines = []
    for line in body.splitlines():
        if line.startswith("# "):
            line = "### " + line[2:]
        elif line.startswith("## "):
            line = "### " + line[3:]
        elif line.startswith("### ") and not re.match(r"### (题目与约束|思路推导|Java 实现|复杂度|易错点与扩展|补充：)", line):
            line = "#### " + line[4:]
        lines.append(line.rstrip())
    # 收尾：合并 ≥3 个连续换行并去掉首尾空白，正文以紧凑、整齐的状态进入题页。
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def new_problem_226() -> str:
    """返回 226「翻转二叉树」的整页正文（已符合站点格式，不经 normalize 直接使用）。

    226 是 Hot 100 中唯一在源笔记目录里没有可复用正文的题（build-summary 的
    added_ids 印证了这点），因此在这里硬编码一份完整题页：
    题目与约束 / 思路推导 / Java 实现 / 复杂度 / 易错点与扩展。
    render_problem_pages 对它走独立的 pid == 226 分支：只 split 题面，不再清洗。
    """
    return r"""
### 题目与约束

给你一棵二叉树的根节点 `root` ，翻转这棵二叉树，并返回其根节点。

**示例 1：**

![](https://__LC_IMG_ROOT__/lc-ea332f6b891c59.jpg)

**输入：**root = [4,2,7,1,3,6,9]<br>**输出：**[4,7,2,9,6,3,1]

**示例 2：**

![](https://__LC_IMG_ROOT__/lc-a43653625d07e5.jpg)

**输入：**root = [2,1,3]<br>**输出：**[2,3,1]

**示例 3：**

**输入：**root = []<br>**输出：**[]

**提示：**

- 树中节点数目范围在 `[0, 100]` 内
- `-100 <= Node.val <= 100`

### 思路推导

这道题最适合训练“递归函数只负责当前节点”的思维：

1. 空节点无需处理，直接返回。
2. 当前节点交换 `left` 与 `right`。
3. 对交换后的左右子树继续做同样的事情。

先交换再递归、先递归再交换都能得到正确结果；关键是整棵树的每个节点都恰好被处理一次。

### Java 实现

```java
class Solution {
    public TreeNode invertTree(TreeNode root) {
        if (root == null) {
            return null;
        }

        TreeNode temp = root.left;
        root.left = root.right;
        root.right = temp;

        invertTree(root.left);
        invertTree(root.right);
        return root;
    }
}
```

### 复杂度

- 时间复杂度：`O(n)`，每个节点访问一次。
- 空间复杂度：`O(h)`，递归栈深度等于树高；退化链表时最坏为 `O(n)`。

### 易错点与扩展

1. 交换的是节点引用，而不是节点值。
2. 不要只交换根节点；左右子树也必须递归处理。
3. 迭代写法可使用队列做 BFS：节点出队后交换孩子，再把非空孩子入队。
""".strip()


# 极少数原稿没有“题目与约束”小节（如 295 直接从思考过程开始），
# 在这里补一句可读的题面，保证每道题页都以题目开头。
# 兜底逻辑：split_problem_statement 拆不出题面时，render_problem_pages 从这里取值；
# 若某题既无题面又未登记于此表，题页「题目与约束」区块会为空 ——
# 因此新增题目时应先在扩展题源正文里写清“### 题目与约束”。
MISSING_STATEMENTS = {
    295: "设计一个数据结构，支持两个操作：`addNum(int num)` 向数据流中添加一个整数；`findMedian()` 返回当前所有元素的中位数。中位数定义为：元素个数为奇数时取排序后中间的那个数，为偶数时取中间两个数的平均值。",
}


def split_problem_statement(clean: str) -> tuple[str, str]:
    """把规范化正文中的「### 题目与约束」小节拆出，返回 (题目, 其余正文)。"""
    # 定位正文中唯一约定的“### 题目与约束”标题；找不到说明此题无题面，
    # 返回空题目（由 render_problem_pages 的 MISSING_STATEMENTS 兜底）。
    match = re.search(r"(?m)^###\s*题目与约束\s*$", clean)
    if match is None:
        return "", clean
    start = match.end()
    tail = clean[start:]
    # 题面边界：从标题行末尾截到下一个 ### 标题之前；没有下一个标题则取到文末。
    end_match = re.search(r"(?m)^###\s+", tail)
    end = start + end_match.start() if end_match else len(clean)
    statement = clean[start:end].strip()
    # 其余正文 = 题面前内容 + 题面后内容，用两个换行接回，仍是一篇完整 Markdown。
    rest = clean[:match.start()].rstrip() + "\n\n" + clean[end:].lstrip("\n")
    return statement, re.sub(r"\n{3,}", "\n\n", rest).strip()


def render_problem_pages(original: dict[int, list[tuple[str, str, str]]]) -> None:
    """为每道题生成 03-题解/<专题目录>/<题号-题名>.md 独立题页 —— 全站最核心的输出。

    输入：extract_original_sections() 的归类结果（题号 → 解法段列表）；
    输出：每题一个 Markdown 文件，页面结构自上而下：
      标题行 → 导航（专题/总目录/复习清单）→ 元信息表（难度/核心模式/时间/空间）
      → ## 题目与约束（含力扣原题链接）→ ## 核心不变量
      → 解法正文（## 完整推导；多版本时 ## 解法 N：…）→ 底部按钮导航。
    与其它函数的关系：题目顺序沿用 PROBLEMS（TSV 行序），文件命名沿用
    problem_filename()；render_topics / render_overview_files 里指向本题的链接
    必须与本函数产出的路径完全一致，因此本函数是全站链接约定的“唯一真相源”。
    """
    for index, problem in enumerate(PROBLEMS):
        pid = int(problem["id"])
        category_folder = str(problem["folder"])
        # 页顶导航：回专题页/总目录/复习清单；路径相对本页（03-题解/<专题>/xxx.md）向上两级。
        topic_path = f"../../02-专题/{category_folder}.md"
        nav = f"[← {problem['category']}专题]({topic_path}) · [总目录](../../../../README.md) · [复习清单](../../00-总览/03-复习清单.md)"
        # 元信息表 1：题目标题 + 导航 + TSV 六项元数据，供读者 30 秒速览。
        header = f"""# {pid}. {problem['title']}

{nav}

| 题目信息 | 内容 |
|---|---|
| 难度 | {problem['difficulty']} |
| 核心模式 | {problem['method']} |
| 时间复杂度 | {problem['time']} |
| 空间复杂度 | {problem['space']} |
"""
        # 取该题全部源解法段；空列表 = 源笔记里没有任何记录（只能占位或走特例分支）。
        variants = original.get(pid, [])
        # sections：页内解法正文小节列表；statements：各段拆出的题面候选。
        sections: list[tuple[str, str]] = []
        statements: list[str] = []
        if pid == 226:
            # 特例分支：226 无源笔记，直接用硬编码正文（不再清洗，仅拆题面）。
            statement, clean_rest = split_problem_statement(new_problem_226())
            if statement:
                statements.append(statement)
            sections.append(("## 完整推导", clean_rest))
        elif variants:
            for number, (variant_title, body, source_name) in enumerate(variants, start=1):
                # 每段解法都独立走一遍完整清洗链，再拆出题面。
                clean = normalize_original_body(body)
                statement, clean_rest = split_problem_statement(clean)
                if statement:
                    statements.append(statement)
                if len(variants) == 1:
                    # 只有一段解法时统一叫「完整推导」，让所有题页结构一致。
                    section_title = "## 完整推导"
                else:
                    # 多版本并列：优先用 VARIANT_LABELS 里的规范命名，未登记才退回原稿标题。
                    labels = VARIANT_LABELS.get(pid, [])
                    label = labels[number - 1] if number <= len(labels) else variant_title
                    section_title = f"## 解法 {number}：{label or '完整版本'}"
                sections.append((section_title, clean_rest))
        else:
            # 源笔记与扩展题源都没有 → 占位提示；同时会被 check_hot100 的
            # “本题正文待补充”检查捕获，提醒维护者补题。
            sections.append(("## 完整推导", "本题正文待补充，可参考维护文档中的扩展题源流程补齐。"))

        # 题面取第一段非空候选；全部为空则回落到 MISSING_STATEMENTS 登记值（仍可能为空串）。
        statement = next((item for item in statements if item.strip()), MISSING_STATEMENTS.get(pid, ""))
        # 源笔记里的图片占位统一替换为题页可用的相对路径（问题页位于 03-题解/专题/ 下，深度为 4）。
        statement = statement.replace("https://__LC_IMG_ROOT__/", "../../../../assets/leetcode/")
        slug = LEETCODE_SLUGS.get(pid, "")
        statement_section = f"## 题目与约束\n\n{statement}"
        # 页体组装：标题/元信息表 + 题面 + 核心不变量 + 各解法小节。
        body_parts = [
            header,
            statement_section,
            f"## 核心不变量\n\n> {problem['invariant']}。",
        ]
        body_parts.extend(f"{title}\n\n{rest}" for title, rest in sections)
        if slug:
            # 力扣原题链接放在正文末尾（易错点与扩展之后），保持题面干净。
            body_parts.append(f"## 力扣原题\n\n[🔗 前往力扣原题验证 →]({LEETCODE_BASE.format(slug=slug)})")

        # 底部按钮导航：上一题 / 回到 Hot 100 目录 / 下一题，整体挪到交互动画之后。
        nav_buttons = []
        if index > 0:
            prev = PROBLEMS[index - 1]
            prev_href = problem_filename(prev).replace(".md", ".html")
            nav_buttons.append(
                f'<a class="problem-nav-btn" href="../{prev["folder"]}/{prev_href}" target="_blank" rel="noopener noreferrer">← 上一题</a>'
            )
        nav_buttons.append(
            '<a class="problem-nav-btn" href="../../../../index.html">🏠 回到 Hot 100 目录</a>'
        )
        if index + 1 < len(PROBLEMS):
            nxt = PROBLEMS[index + 1]
            next_href = problem_filename(nxt).replace(".md", ".html")
            nav_buttons.append(
                f'<a class="problem-nav-btn primary" href="../{nxt["folder"]}/{next_href}" target="_blank" rel="noopener noreferrer">下一题 →</a>'
            )
        footer = (
            "<!--bottom-nav-->\n"
            + '<div class="problem-nav">\n'
            + "\n".join(nav_buttons)
            + "\n</div>\n<!--/bottom-nav-->"
        )
        content = "\n\n".join(body_parts) + "\n\n" + footer
        # 输出到 03-题解/<专题目录>/，目录与文件名都绑定 problem_filename 命名规则。
        path = ROOT / "books" / "hot100" / "03-题解" / category_folder / problem_filename(problem)
        write(path, content)


# 专题页的“深度内容表”：专题显示名 → (一句话讲解, 下笔顺序规则列表, 工具箱关键词)。
# 只被 render_topics 消费；17 个键必须与 CATEGORIES 的显示名一一对应（否则 KeyError）。
CATEGORY_DETAILS = {
    "哈希表": ("键必须代表可稳定复用的特征；值保存下标、频次、分组或状态。", ["先决定查什么，再决定 key", "若依赖此前信息，通常先查后存", "对象作 key 时确保 equals/hashCode 稳定"], "计数、补数查找、规范化签名、集合边界"),
    "双指针": ("双指针不是‘放两个变量’，而是用两个位置维护一个可证明的不变量。", ["先说明两指针各代表什么", "证明移动哪一侧能排除答案", "原地改写时区分已处理区与未知区"], "快慢、相向、同向覆盖、链表节奏"),
    "滑动窗口": ("窗口只适合连续区间；关键在于条件能否随着左右端移动被增量维护。", ["右端加入元素并更新状态", "while 循环收缩左端", "在正确时机更新最长或最短答案"], "定长窗口、可变窗口、频次表"),
    "子串": ("先区分题目要的是区间和、区间最值还是覆盖关系，再选前缀和、单调队列或窗口。", ["连续但允许负数求和：优先前缀和", "固定窗口最值：单调队列", "覆盖/频次条件：滑动窗口"], "前缀和、单调队列、最小覆盖"),
    "普通数组": ("数组题最常见的突破口是改变遍历顺序或把值映射回下标。", ["区间先排序", "需要左右信息时分两趟", "值域落在 1..n 时考虑原地哈希"], "Kadane、区间合并、反转、前后缀、循环置换"),
    "矩阵": ("写矩阵题先统一行列含义，所有边界都使用同一套闭区间或开区间语义。", ["记录 rows 与 cols，避免方阵假设", "原地标记先保护首行首列", "模拟遍历每走一边就收边界"], "原地标记、边界模拟、角点搜索"),
    "链表": ("链表算法的难点是引用变化；画出局部的前驱、当前、后继比背代码可靠。", ["优先添加 dummy", "改 next 前保存断开后仍需要的节点", "返回头节点前检查头部是否发生变化"], "虚拟头、快慢指针、局部反转、归并、哈希+双链表"),
    "二叉树": ("看到树先问：信息是从父节点向下传，还是从子树向上汇总。", ["向下传参数：前序/DFS", "向上返回信息：后序", "BST 排序性质：中序", "按层处理：BFS"], "前序传参、后序汇总、中序有序、层序遍历"),
    "图论": ("树是无环图的特例；图中必须显式处理 visited、入度或状态标记。", ["入队或进入递归时立刻标记", "多源扩散把所有源同时入队", "依赖可行性用拓扑排序"], "洪泛搜索、多源 BFS、拓扑排序、Trie"),
    "回溯": ("回溯 = 枚举决策树；剪枝来自题目约束，而不是凭感觉提前 return。", ["明确 path、选择范围、终止条件", "做选择", "递归", "撤销选择"], "排列、子集、组合、切割、棋盘"),
    "二分查找": ("二分最怕区间语义混用；模板不重要，循环不变量最重要。", ["写出答案可能存在的区间", "判断 mid 后排除不可能半边", "保证区间严格缩小", "退出后解释 left/right 指向什么"], "精确查找、lower_bound、旋转数组、二分答案"),
    "栈": ("栈适合处理尚未闭合的结构或尚未找到答案的元素。", ["明确栈中存值还是下标", "说明栈内单调性或匹配关系", "弹栈时完成结算"], "括号、嵌套、单调栈、双栈模拟"),
    "堆": ("堆不负责全局排序，只负责随时给出当前候选中的极值。", ["先决定堆顶应该是谁", "Top K 通常只保留 k 个", "对象比较器避免用减法造成溢出"], "Top K、多路归并、双堆"),
    "贪心": ("贪心解法必须有排除证明：被丢掉的选择以后不可能更优。", ["定义当前维护的最优边界", "说明何时提交一次选择", "用反证或交换论证局部选择安全"], "历史最优、最远边界、分段边界"),
    "动态规划": ("先写状态定义，再写转移；不要从代码循环反推 dp 含义。", ["状态是什么", "答案从哪些更小状态来", "边界如何初始化", "遍历顺序是否满足依赖", "能否压缩空间"], "线性 DP、完全背包、0-1 背包、序列 DP"),
    "多维动态规划": ("二维表的每个坐标必须有一句完整定义，否则转移方向很容易写反。", ["画出 3×3 小表", "填第一行和第一列", "标出当前格依赖的方向", "最后再考虑滚动数组"], "网格 DP、区间 DP、双序列 DP"),
    "技巧": ("这组题不依赖统一数据结构，重点是识别隐藏模型并记住证明。", ["位运算先列恒等式", "投票法先说抵消含义", "三路划分画出四个区间", "排列题从字典序定义推导"], "异或、投票、三路划分、字典序、隐式链表"),
}


def render_topics() -> None:
    """生成 02-专题/ 下 17 个专题页 —— 每个专题一页，串起该专题的全部题目。

    页面结构（自上而下）：识别信号 → 一句话讲解 → 核心不变量 → 下笔顺序 →
    工具箱 → 练习顺序表（本专题题目按 TSV 顺序、链接到 03-题解 对应题页）
    → 复习标准。素材来源：CATEGORIES（信号/不变量）与 CATEGORY_DETAILS（讲解/规则/工具箱）。
    """
    # 按专题显示名把题目分组；defaultdict 保证没有任何题的专题也得到空列表。
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for problem in PROBLEMS:
        grouped[str(problem["category"])].append(problem)
    for folder, category, signal, invariant in CATEGORIES:
        intro, rules, toolkit = CATEGORY_DETAILS[category]
        rows = []
        # 练习顺序表行：序号 / 题名链接（相对 02-专题 目录指向 03-题解）/ 难度 / 主方法 / 时间·空间。
        for order, problem in enumerate(grouped[category], start=1):
            href = f"../03-题解/{folder}/{problem_filename(problem)}"
            rows.append(f"| {order} | [{problem['id']}. {problem['title']}]({href}) | {problem['difficulty']} | {problem['method']} | {problem['time']} / {problem['space']} |")
        # 把“下笔顺序”规则列表按 1. 2. 3. 编号渲染成多行文本。
        rule_lines = "\n".join(f"{i}. {rule}" for i, rule in enumerate(rules, start=1))
        content = f"""# {category}

[总目录](../../../README.md) · [算法模式地图](../00-总览/02-算法模式地图.md)

## 识别信号

{signal}

{intro}

## 核心不变量

> {invariant}

## 下笔顺序

{rule_lines}

## 工具箱

{toolkit}。完整 Java 模板见 [Hot 100 算法模板](../04-模板/01-Hot100算法模板.md)。

## 练习顺序

| 顺序 | 题目 | 难度 | 主方法 | 时间 / 空间 |
|---:|---|---|---|---|
{chr(10).join(rows)}

## 复习标准

- 能在 30 秒内说出每题的核心不变量。
- 能不看答案写出主循环或递归函数签名。
- 能解释为什么移动指针、弹栈、剪枝或状态转移不会漏解。
- 能主动写出至少 3 个边界用例。
"""
        # 输出 02-专题/<专题目录名>.md；目录名与 03-题解 下同名目录一致，链接因此精确对应。
        write(ROOT / "books" / "hot100" / "02-专题" / f"{folder}.md", content)


def render_readme() -> None:
    """生成学习站根目录 README.md（整棵 Markdown 树的总入口）。

    内容依次为：站点简介 → 立即开始（index.html/学习路线/模式地图/复习清单/
    速查/模板/维护指南）→ 每道题怎么学（5 步学习法）→ 专题导航表 →
    目录结构 → 整理原则。专题导航表的题数由本题从 PROBLEMS 现场统计，
    识别信号直接复用 CATEGORIES 元数据 —— 单一数据源，避免两处维护漂移。
    """
    rows = []
    # 先做“专题 → 题数”统计，再按 CATEGORIES 顺序输出导航表，保证与专题页顺序一致。
    grouped = defaultdict(int)
    for problem in PROBLEMS:
        grouped[str(problem["category"])] += 1
    for folder, category, signal, invariant in CATEGORIES:
        # 导航表行：专题链接（相对根目录的路径）/ 题数 / 识别信号。
        rows.append(f"| [{category}](books/hot100/02-专题/{folder}.md) | {grouped[category]} | {signal} |")
    content = f"""# InterviewForge · LeetCode Hot 100 深度整理版（Java）

面向大厂校招的**本地离线学习项目**：把 Hot 100 高频题整理成独立题页（题目、核心不变量、完整推导、Java 实现、复杂度与交互演示），并配套 17 个专题框架、算法模板、复习清单，以及覆盖 Java 核心、并发、JVM、数据库、网络、Spring、分布式、RAG/Agent 等校招主线的**学习书架（37 模块 / 709 章）**。

项目内置**学习记录、间隔重复复习、学习轨迹、限时模拟、力扣提交同步**等能力，形成“学 → 练 → 复盘 → 复习”的完整闭环；所有数据只保存在本机 SQLite，完全离线可用。

## 立即开始

1. 双击根目录的 `启动学习站.cmd`（自动检测端口并打开浏览器）；
2. 访问 [项目首页](index.html)（http://127.0.0.1:8765/）；
3. 首次使用建议按 [四阶段学习路线](books/hot100/00-总览/01-学习路线.md) 开始；
4. 打开任意题解页或章节会自动记录浏览，点“完成一轮”推进复习。

依赖：仅需本机 Python 3.10+；Mermaid、uPlot 等前端资源全部本地内置，**零网络依赖**。

## 主要功能详解

### 1. Hot 100 算法精讲

- 100 道高频题独立题页：题目与约束、核心不变量、完整推导、Java 实现、复杂度、易错点与扩展、高频追问；
- [17 个专题框架](books/hot100/02-专题/)（哈希表、双指针、滑动窗口、动态规划…）、[算法模式地图](books/hot100/00-总览/02-算法模式地图.md)、[复习清单](books/hot100/00-总览/03-复习清单.md)、[Java 刷题速查](books/hot100/01-基础/01-Java刷题速查.md)、[算法模板](books/hot100/04-模板/01-Hot100算法模板.md)；
- 18 个交互可视化演示内嵌到对应题解/章节（哈希表、双指针、链表、锁升级、TCP 握手挥手、ReadView 版本链等），只展示关键状态变化，一键播放/分步。

### 2. 学习书架（37 模块 / 709 章）

- 校招主线全覆盖：语言根基、并发、JVM、MySQL、网络、Spring 家族、设计模式、消息队列、分布式、微服务、部署运维、RAG/Agent 等；
- 新增《小林面试笔记》系列 7 本与《Agent 面经》，覆盖大厂 Agent、RAG、工具调用、大模型工程、LangChain 面试题与图解专栏；
- Mermaid 流程图离线渲染（浅色主题、品牌配色）、Pygments 代码高亮（Java/Python 等）、章节内嵌交互演示；
- 模块页“本模块待复习”区块、章节卡到期徽标、章节页“下次复习”日期、章节级多轮学习记录；
- [全文搜索](library/search.html)：709 章离线索引，标题 / 模块名 / 正文命中排序。

### 3. 学习记录（本机 SQLite）

- 打开题解/章节自动记录浏览（同内容 60 秒内去重）；点“完成一轮”写入复习轮次；
- 面板统计：今天看题、今天完成、已刷题目、累计轮次、连续学习、每日目标；
- 365 天活跃热力图（点击格子看当日明细）+ 近 28 天趋势折线（看题 / 完成轮次双线）+ 周报导出；
- 所有历史保存在 `data/hot100-study.db`，可随时备份。

### 4. 间隔重复复习

- 题目间隔：第 1 轮后 1 天 → 3 → 7 → 15 → 30 → 60 天稳定；
- 书架章节间隔：第 1 轮后 3 天 → 7 → 15 → 30 → 60 → 90 天稳定；
- 到期自动进“今日待复习”，逾期红色标记；完成一轮自动推进下次复习；
- 面板“今日待复习”只显示 Hot 100 题目；书架章节在书架各模块页展示，互不混排（可开启设置 `review_include_contents` 在面板追加独立折叠子区）。

### 5. 今日计划

- 组合“待复习 + 薄弱 + 新题（按最久未看补足）”并标注理由；点“换一组”随机抽取新题；
- 每日目标轮次可设置，目标达成情况显示在统计卡。

### 6. 薄弱标记与错题本

- 题卡/章节卡可标记“薄弱 / 复习中 / 已掌握”；
- [错题本页](books/hot100/00-总览/05-错题本.html)：专题分布条形图 + 薄弱清单（题号/题名/方法/轮次/最近复习/标记时间）+ 一键移除，可打印；
- 薄弱题自动进入今日计划；标记可导出为薄弱清单文件。

### 7. 限时模拟

- 随机组卷：题目数（5/10/20）、时长（10/20/30 分钟）、专题、难度均可配置；
- 倒计时、逐题“完成 / 跳过”、结束报告（完成/跳过/用时）；
- “模拟完成的题计入学习轮次”默认关闭，勾选后模拟结束才批量推进复习，避免污染正常调度。

### 8. 力扣导入学习记录（详细）

把你在力扣的提交结果同步进本地数据库：**已解答（AC）回填 + 最近 50 条提交记录（含语言、耗时）**，并联动复习调度。

#### 为什么需要导入登录会话

力扣没有第三方授权（无 OAuth），无法“一键授权”。项目采用**导入你的登录 Cookie** 方式：会话只保存在本机 SQLite，仅用于读取你的提交记录；提交代码仍在力扣官网进行，项目不会自动提交。

#### 四步接入（[力扣连接页](pages/leetcode-connect.html)）

1. 打开 [leetcode.cn](https://leetcode.cn/) 并登录（用户名密码只交给力扣）；
2. 复制登录 Cookie：
   - 方式 A（推荐）：安装 [CookieMate](https://chromewebstore.google.com/detail/cookiemate-%E2%80%94-cookie-edito/jdmdgfbbjjdnflajkclafekpcgkaegdi) 扩展，在 leetcode.cn 一键复制 `LEETCODE_SESSION`；
   - 方式 B：按 F12 → Application → Cookies → `https://leetcode.cn`，找到 `LEETCODE_SESSION` 复制其值（`csrftoken` 可选，只读同步一般可省略）；
3. 粘贴到力扣连接页并点“保存并测试连接”，显示“连接成功：用户名（已解决 N 题）”即成功；
4. 点“同步”：拉取“已解答”回填到本地数据库 + 最近 50 条提交记录。

#### 同步后的效果

- 面板统计卡新增“日 AC / 提交、累计 AC、通过率”；
- 题卡右上角出现“已 AC”徽标（该题 AC 过即显示）；
- 提交记录按题留存（语言、耗时、内存、来源），可查任意题最近 50 条；
- **AC 提示推进复习**（建议再点一次“完成一轮”）；**WA 自动标记薄弱并提前进入“今日待复习”**。

#### 不连接力扣的手动方式

每张题卡自带“已 AC / WA”按钮：在力扣通过后点“已 AC”，未通过点“WA”——同样写入提交记录并联动薄弱标记，无需导入 Cookie。

#### 安全说明

- 凭证只存在本机 `data/hot100-study.db` 的 `credentials` 表，可随时在力扣连接页“清除凭证”；
- 同步只读取力扣页面接口，不修改你的力扣账号数据；工作目录外请勿粘贴凭证。

### 9. 导出与备份

- **Anki CSV**：UTF-8 BOM + 记忆锚点（核心不变量）+ 复杂度 + 力扣链接，AnkiDroid 可直接导入；
- 薄弱清单、记录 JSON、周报（近 7 天看题/轮次/AC）、数据库备份；
- 书架章节“导出本章 HTML”（内联样式，可离线保存分享）。

### 10. PWA 与本地服务

- PWA 可安装，离线缓存采用**网络优先**策略（离线时回退缓存）；
- 复习到期通知（需授权）；服务对静态资源统一 `Cache-Control: no-store`，保证每次打开都是最新内容；
- 本地服务监听 `0.0.0.0:8765`，局域网内其他设备也可访问（本机地址 http://127.0.0.1:8765/）。

## 每道题怎么学

1. 先读题页顶部的“核心模式”和“核心不变量”，用自己的话复述不变量。
2. 在题解底部运行对应的交互演示或手算示例，只跟踪关键状态，不急着看代码。
3. 关闭笔记写出主循环/递归，再对照题解。
4. 用空输入、最小规模、重复值、极端顺序四类用例自测。
5. 24 小时、7 天、30 天后只看题名重写，失败就放入错题复盘。

## 专题导航

| 专题 | 题数 | 识别信号 |
|---|---:|---|
{chr(10).join(rows)}

## 目录结构

```text
interview-forge/
├─ README.md                 项目总入口
├─ MAINTENANCE.md            维护、扩展与发布规范
├─ index.html                学习面板（由模板生成）
├─ guide.html                完整使用指南（由 README 生成）
├─ maintenance.html          维护指南（由 MAINTENANCE 生成）
├─ 启动学习站.cmd            自动杀旧进程并启动本地服务
├─ manifest.webmanifest       PWA 清单
├─ service-worker.js          PWA 离线缓存
├─ pages/                    独立功能页
│  ├─ history.html           学习记录页
│  ├─ leetcode-connect.html  力扣连接向导页
│  ├─ login.html             登录页
│  ├─ register.html          注册码注册页
│  └─ admin.html             管理后台（仅管理员）
├─ docs/                     文档与报告
│  ├─ QA-REPORT.md/.html     发布前校验报告
│  ├─ MOBILE-UX-REPORT.md    移动端 UX 优化报告
│  └─ InterviewForge-SSH部署与版本更新指南.md
├─ assets/                   公共样式、脚本与图标（生成结果）
├─ data/                     SQLite 学习记录（首次启动自动创建，不入库）
├─ library/                  学习书架生成结果（37 模块 / 709 章）
├─ tools/                    生成、校验、服务与维护脚本
│  ├─ build_hot100.py        全量重建 Hot 100 面板与题解
│  ├─ build_library.py       学习书架生成器
│  ├─ build_html_site.py     阅读页渲染与公共资源生成
│  ├─ check_hot100.py        发布前全站校验
│  ├─ study_server.py        本地 HTTP 服务 + SQLite 学习记录
│  ├─ library_catalog.py     书架模块登记表
│  ├─ scrape_xiaolinnote.py  小林面试笔记抓取脚本
│  ├─ update_leetcode_statements.py  力扣题面批量更新脚本
│  ├─ templates/             面板模板
│  └─ vendor/                离线前端库（Mermaid、uPlot 等）
└─ books/                    全部内容源（一“书”一目录）
   ├─ hot100/                Hot 100 全书
   │  ├─ 00-总览/ 01-基础/ 02-专题/ 03-题解/ 04-模板/
   │  ├─ 05-可视化/ 06-扩展题源/ 99-原稿归档/
   │  └─ 00-数组.md ~ 17-技巧.md（专题源笔记）
   ├─ Java校招/  Python/  机器学习/  langchain/
   ├─ 0816MCP/  20260419_Hermes_Agent/  单行本/
   ├─ 小林面试笔记AI/        小林笔记抓取结果 + 合订本
   │  ├─ agent/ rag/ tools/ llm/ langchain/
   │  ├─ tujie-agent/ tujie-claude-code/
   │  └─ images/
   └─ agent面经/             Agent 面经合订本 + 图片
```

## 开发与维护

```bash
cd interview-forge
python .\\tools\\build_hot100.py   # 全量重建（面板 + 书架 + 全部页面）
python .\\tools\\check_hot100.py   # 发布前检查（必须 errors: 0）
```

详细约定见 [MAINTENANCE.md](MAINTENANCE.md)。

## 整理原则

- 算法路线不因润色而改变；重复版本改为并列多解法。
- 删除夸张、重复的 AI 式措辞，但保留有效推导、代码、复杂度和追问。
- 推荐方法写在页首，原稿中的替代方法仍保留在正文。
- 所有新增内容都服务于“识别模式—说出不变量—独立实现—边界验证”。
"""
    write(ROOT / "README.md", content)


def render_overview_files() -> None:
    """生成 00-总览/ 下的 4 个规划文件（一次调用写 4 个目标文件）。

    - 01-学习路线.md：四阶段路线（建立模式 → 闭卷写模板 → 专题内递进 → 混合检索与复盘）；
    - 02-算法模式地图.md：从题目特征反推算法的对照表（信号+不变量两列复用 CATEGORIES）；
    - 03-复习清单.md：17 个专题逐题勾选清单（链接规则与 render_problem_pages 完全一致）；
    - 04-错题复盘模板.md：固定复盘结构，防止“伪复习”。
    与其它函数的关系：01/02/04 基本是静态文本 + 少量复用数据；03 是全站
    复习工具，其链接必须与 03-题解 目录下的真实文件精确一致。
    """
    # 01 学习路线：内容基本为静态 Markdown，仅内嵌指向 04-模板 等目录的相对链接。
    route = """# 四阶段学习路线

[返回总目录](../../../README.md)

## 阶段一：建立模式（建议 7 天）

目标不是做完 100 题，而是认出 17 个专题的典型信号。每天学习 2～3 个专题，只做每个专题前两题，并完成一次可视化手推。

推荐顺序：

1. 哈希表 → 双指针 → 滑动窗口 → 子串。
2. 普通数组 → 矩阵 → 链表。
3. 二叉树 → 图论 → 回溯。
4. 二分查找 → 栈 → 堆。
5. 贪心 → 动态规划 → 多维动态规划 → 技巧。

## 阶段二：闭卷写模板（建议 7～10 天）

每天从 [算法模板](../04-模板/01-Hot100算法模板.md) 选 3 个模板闭卷默写。模板不是整题答案，只写最能表达不变量的主干；写完立即用最小用例手推。

## 阶段三：专题内递进（建议 14～21 天）

按各专题页给出的顺序完成题目。简单题限时 15 分钟，中等题 30 分钟，困难题 45 分钟。超时先看“核心不变量”，仍无思路再看完整推导。

## 阶段四：混合检索与复盘（长期）

打乱专题，只看题名回答四个问题：

1. 识别信号是什么？
2. 核心不变量是什么？
3. 时间和空间复杂度是多少？
4. 哪个边界最容易写错？

无法在 60 秒内回答，就在 [错题复盘模板](04-错题复盘模板.md) 中记录，并安排 1、3、7、30 天回看。

## 一次有效复习的标准

- 不是“看懂”，而是能关掉笔记写出主干。
- 不是“记住代码”，而是能解释每个指针、状态和容器的含义。
- 不是只通过样例，而是能主动构造破坏错误写法的反例。
"""
    write(ROOT / "books" / "hot100" / "00-总览" / "01-学习路线.md", route)

    map_rows = []
    # 02 模式地图：一行一专题，信号与不变量直接复用 CATEGORIES 原始数据，免于双份维护。
    for folder, category, signal, invariant in CATEGORIES:
        map_rows.append(f"| [{category}](../02-专题/{folder}.md) | {signal} | {invariant} |")
    pattern_map = f"""# 算法模式地图

[返回总目录](../../../README.md)

遇到陌生题时，先根据输入结构和目标函数定位模式，再进入对应专题。

| 模式 | 常见信号 | 解题不变量 |
|---|---|---|
{chr(10).join(map_rows)}

## 容易混淆的选择

| 题目特征 | 优先选择 | 不优先选择的原因 |
|---|---|---|
| 连续区间 + 元素全非负 + 最短/最长 | 滑动窗口 | 前缀和能算区间值，但不一定能单调移动边界 |
| 连续区间和 + 允许负数 | 前缀和 + 哈希 | 窗口和不再随右移单调变化 |
| 固定窗口最大值 | 单调队列 | 堆能做但过期元素处理更复杂，复杂度也更高 |
| 有序数组上的边界位置 | 二分查找 | 双指针通常仍需线性扫描 |
| 树中答案由子树贡献组成 | 后序 DFS | 前序无法先得到子树返回值 |
| Top K 且数据持续到来 | 堆 | 全排序会保存和处理不需要的顺序信息 |
| 每个元素只能选一次的背包 | 容量倒序 | 正序会在同一轮复用当前元素 |
| 每个元素可无限选的背包 | 容量正序 | 倒序会把问题误写成 0-1 背包 |
"""
    write(ROOT / "books" / "hot100" / "00-总览" / "02-算法模式地图.md", pattern_map)

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    # 03 复习清单：先把题目按专题分组，再按 CATEGORIES 顺序逐题生成勾选项。
    for p in PROBLEMS:
        grouped[str(p["category"])].append(p)
    checklist = ["# Hot 100 复习清单", "", "[返回总目录](../../../README.md)", "", "勾选规则：能闭卷写出主干并解释不变量才算完成。建议在行尾追加复习日期，例如 `2026-08-25 / 08-28 / 09-25`。", ""]
    for folder, category, *_ in CATEGORIES:
        checklist.append(f"## {category}")
        checklist.append("")
        for p in grouped[category]:
            checklist.append(f"- [ ] [{p['id']}. {p['title']}](../03-题解/{folder}/{problem_filename(p)}) — {p['method']}；记忆锚点：{p['invariant']}")
        checklist.append("")
    # 03 复习清单：文件路径 00-总览/03-复习清单.md，行尾追加复习日期用于错题回收。
    write(ROOT / "books" / "hot100" / "00-总览" / "03-复习清单.md", "\n".join(checklist))

    # 04 复盘模板：纯静态 Markdown，给学习者复制使用的固定复盘骨架。
    review = """# 错题复盘模板

[返回总目录](../../../README.md)

复制下面的模板，每道错题只记录导致失败的最小信息。

```markdown
# 题号与题名

- 日期：
- 失败类型：没识别模式 / 不变量不清 / 实现错误 / 边界遗漏 / 复杂度不达标
- 我当时的错误思路：
- 能击穿错误思路的最小反例：
- 正确模式：
- 一句话不变量：
- 代码中最关键的 3 行：
- 下次看到什么信号要立刻想到它：
- 复习日期：D+1 / D+3 / D+7 / D+30
```

## 复盘禁区

- 不要整段复制题解；这会让复盘再次变成阅读。
- 不要只写“粗心”；必须定位到具体变量、区间语义或状态定义。
- 不要只保存正确代码；一定保存能击穿错误代码的反例。
"""
    write(ROOT / "books" / "hot100" / "00-总览" / "04-错题复盘模板.md", review)


def render_templates() -> None:
    """生成 04-模板/ 下的 3 个文件（一次调用写 3 个目标文件）。

    - 01-Hot100算法模板.md：17 个算法主干模板（只留结构，使用前须重述变量含义与不变量）；
    - 02-边界用例检查表.md：按题型的必测边界清单 + 5 个代码级检查；
    - 03-Java数据结构选择表.md：容器/结构选择速查。
    三个文件都是固定文本：01 用原始字符串（r'''...'''）写死，避免转义破坏 ```java 围栏。
    """
    # 01 算法模板：r''' 原始字符串内嵌大量 Java 代码围栏与反斜杠，不做转义处理。
    templates = r'''# Hot 100 Java 算法模板

[返回总目录](../../../README.md) · [Java 刷题速查](../01-基础/01-Java刷题速查.md)

模板只保留结构。使用前必须重新说明变量含义、循环不变量和边界语义。

## 1. 一遍哈希

```java
Map<Integer, Integer> seen = new HashMap<>();
for (int i = 0; i < nums.length; i++) {
    int need = target - nums[i];
    if (seen.containsKey(need)) {
        return new int[]{seen.get(need), i};
    }
    seen.put(nums[i], i); // 依赖“此前元素”时先查后存
}
```

## 2. 相向双指针

```java
int left = 0, right = nums.length - 1;
while (left < right) {
    // 使用 nums[left] 与 nums[right]
    if (shouldMoveLeft(nums, left, right)) left++;
    else right--;
}
```

## 3. 可变滑动窗口

```java
int left = 0;
for (int right = 0; right < nums.length; right++) {
    add(nums[right]);
    while (windowInvalidOrCanShrink()) {
        remove(nums[left++]);
    }
    updateAnswer(left, right);
}
```

## 4. 前缀和 + 频次

```java
Map<Integer, Integer> count = new HashMap<>();
count.put(0, 1);
int prefix = 0, answer = 0;
for (int x : nums) {
    prefix += x;
    answer += count.getOrDefault(prefix - k, 0);
    count.merge(prefix, 1, Integer::sum);
}
```

## 5. 单调队列

```java
Deque<Integer> deque = new ArrayDeque<>(); // 存下标，对应值递减
for (int i = 0; i < nums.length; i++) {
    while (!deque.isEmpty() && deque.peekFirst() <= i - k) deque.pollFirst();
    while (!deque.isEmpty() && nums[deque.peekLast()] <= nums[i]) deque.pollLast();
    deque.offerLast(i);
    if (i >= k - 1) answer[i - k + 1] = nums[deque.peekFirst()];
}
```

## 6. 链表反转

```java
ListNode prev = null, current = head;
while (current != null) {
    ListNode next = current.next;
    current.next = prev;
    prev = current;
    current = next;
}
return prev;
```

## 7. 二叉树 DFS：向上汇总

```java
int dfs(TreeNode node) {
    if (node == null) return 0;
    int left = dfs(node.left);
    int right = dfs(node.right);
    updateGlobalAnswer(node, left, right);
    return contributionToParent(node, left, right);
}
```

## 8. BFS 分层

```java
Queue<TreeNode> queue = new ArrayDeque<>();
queue.offer(root);
while (!queue.isEmpty()) {
    int size = queue.size();
    for (int i = 0; i < size; i++) {
        TreeNode node = queue.poll();
        if (node.left != null) queue.offer(node.left);
        if (node.right != null) queue.offer(node.right);
    }
}
```

## 9. 网格 DFS

```java
void dfs(char[][] grid, int row, int col) {
    if (row < 0 || row >= grid.length || col < 0 || col >= grid[0].length
            || grid[row][col] != '1') return;
    grid[row][col] = '0'; // 进入即标记
    dfs(grid, row + 1, col);
    dfs(grid, row - 1, col);
    dfs(grid, row, col + 1);
    dfs(grid, row, col - 1);
}
```

## 10. 拓扑排序

```java
Queue<Integer> queue = new ArrayDeque<>();
for (int i = 0; i < n; i++) if (indegree[i] == 0) queue.offer(i);
int visited = 0;
while (!queue.isEmpty()) {
    int current = queue.poll();
    visited++;
    for (int next : graph.get(current)) {
        if (--indegree[next] == 0) queue.offer(next);
    }
}
return visited == n;
```

## 11. 回溯

```java
void backtrack(int start) {
    if (isComplete()) {
        answer.add(new ArrayList<>(path));
        return;
    }
    for (int i = start; i < choices.length; i++) {
        if (shouldSkip(i)) continue;
        path.add(choices[i]);
        backtrack(nextStart(i));
        path.remove(path.size() - 1);
    }
}
```

## 12. lower_bound：第一个大于等于 target

```java
int left = 0, right = nums.length; // [left, right)
while (left < right) {
    int mid = left + (right - left) / 2;
    if (nums[mid] < target) left = mid + 1;
    else right = mid;
}
return left;
```

## 13. 单调栈

```java
Deque<Integer> stack = new ArrayDeque<>();
for (int i = 0; i < nums.length; i++) {
    while (!stack.isEmpty() && nums[i] > nums[stack.peek()]) {
        int index = stack.pop();
        answer[index] = i - index;
    }
    stack.push(i);
}
```

## 14. Top K 小顶堆

```java
PriorityQueue<Integer> heap = new PriorityQueue<>();
for (int x : nums) {
    heap.offer(x);
    if (heap.size() > k) heap.poll();
}
return heap.peek();
```

## 15. 0-1 背包与完全背包

```java
// 0-1：每个数只能用一次，容量倒序
for (int x : nums) {
    for (int capacity = target; capacity >= x; capacity--) {
        dp[capacity] |= dp[capacity - x];
    }
}

// 完全：每个数可重复使用，容量正序
for (int coin : coins) {
    for (int capacity = coin; capacity <= amount; capacity++) {
        dp[capacity] = Math.min(dp[capacity], dp[capacity - coin] + 1);
    }
}
```

## 16. 二维 DP

```java
for (int i = 1; i <= m; i++) {
    for (int j = 1; j <= n; j++) {
        if (a.charAt(i - 1) == b.charAt(j - 1)) {
            dp[i][j] = dp[i - 1][j - 1] + 1;
        } else {
            dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
    }
}
```

## 17. 三路划分

```java
int left = 0, i = 0, right = nums.length - 1;
while (i <= right) {
    if (nums[i] == 0) swap(nums, left++, i++);
    else if (nums[i] == 2) swap(nums, i, right--); // i 不动，新值尚未检查
    else i++;
}
```
'''
    # 01 算法模板落盘：04-模板/01-Hot100算法模板.md（专题页“工具箱”链接指向它）。
    write(ROOT / "books" / "hot100" / "04-模板" / "01-Hot100算法模板.md", templates)

    # 02 边界自查表：纯静态表格 + 5 点代码级检查，供写代码前逐条自问。
    edge = """# 边界用例检查表

[返回总目录](../../../README.md)

提交前不要机械地全测；根据题型选最可能击穿实现的用例。

| 题型 | 必测边界 |
|---|---|
| 数组/字符串 | 空、长度 1、全相同、严格升序、严格降序、目标在两端、不存在目标 |
| 滑动窗口 | 答案是整个串、答案长度 1、无答案、重复字符集中在窗口左端 |
| 二分 | 空数组、单元素、target 小于最小值、大于最大值、重复值的左右边界 |
| 链表 | 空、单节点、两节点、删除头、删除尾、环入口是头、完全不相交 |
| 二叉树 | 空树、单节点、只有左链、只有右链、答案经过根、答案完全在子树 |
| 图/网格 | 1×1、全阻塞、全连通、多个孤立块、有环、多个初始源 |
| 回溯 | 无解、只有一个解、重复候选、目标为 0、路径必须恢复 |
| 动态规划 | dp[0] 的含义、第一行/列、无法到达的状态、整数溢出、遍历方向 |
| 堆/栈 | k=1、k=n、全部相等、严格单调输入、容器为空时的 peek/poll |

## 五个代码级检查

1. `mid` 是否使用 `left + (right - left) / 2`。
2. `Comparator` 是否使用 `Integer.compare(a, b)` 避免减法溢出。
3. 递归是否有完整的空节点或越界终止条件。
4. 链表改指针前是否保存了之后仍需访问的节点。
5. 0-1 背包是否倒序、完全背包是否正序。
"""
    write(ROOT / "books" / "hot100" / "04-模板" / "02-边界用例检查表.md", edge)

    # 03 数据结构选择表：纯静态表格，先推荐结构、再点常见坑。
    choose = """# Java 数据结构选择表

[返回总目录](../../../README.md)

| 需要 | 推荐结构 | 关键操作 | 常见坑 |
|---|---|---|---|
| 键到值、计数、定位 | `HashMap<K,V>` | `getOrDefault`、`merge`、`computeIfAbsent` | `getOrDefault` 不会自动写回 |
| 去重、O(1) 存在性 | `HashSet<E>` | `add`、`contains`、`remove` | 不保证遍历顺序 |
| 尾部动态追加 | `ArrayList<E>` | `add`、`get`、`remove(size-1)` | `remove(int)` 与 `remove(Object)` 重载 |
| 栈 | `ArrayDeque<E>` | `push`、`pop`、`peek` | 不允许 `null` |
| 队列 | `ArrayDeque<E>` | `offer`、`poll`、`peek` | 不建议 `LinkedList` 作为默认选择 |
| 双端/单调队列 | `ArrayDeque<E>` | `offerLast`、`pollFirst`、`peekLast` | 明确队首队尾语义 |
| 动态极值、Top K | `PriorityQueue<E>` | `offer`、`poll`、`peek` | 默认是小顶堆 |
| 有序键与边界查询 | `TreeMap<K,V>` | `floorKey`、`ceilingKey` | O(log n)，不要误认为 O(1) |

优先使用接口类型声明变量，例如 `Map<Integer, Integer> map = new HashMap<>();`。完整 API 见 [Java 刷题速查](../01-基础/01-Java刷题速查.md)。
"""
    write(ROOT / "books" / "hot100" / "04-模板" / "03-Java数据结构选择表.md", choose)


def copy_source_materials() -> None:
    """把源笔记目录中的“基础素材”复制进学习站的三个子目录。

    - 01-基础/：5 篇 Java 速查素材（复制时统一过 calm_language，并改写站内相对链接）；
    - 99-原稿归档/：源目录全部 md 的未修改副本 + 归档说明（用于核对整理前后的算法方法）；
    - 05-可视化/：源目录“可视化”下的交互组件 HTML 与 pic 图库（供题页页尾交互演示使用）。
    与其它函数的关系：在 render_problem_pages 之前执行（build 的②步），
    它写入的 01-基础 会被 README 与模板页链接引用。
    """
    basics = ROOT / "books" / "hot100" / "01-基础"
    basics.mkdir(parents=True, exist_ok=True)
    # 素材重命名映射：源文件名 → 站内文件名（01-基础 下按语义顺序编号）。
    mapping = {
        "Hot100-Java基础语法、常用类与API速查.md": "01-Java刷题速查.md",
        "00-数组.md": "02-Java数组.md",
        "00-字符串.md": "03-Java字符串.md",
        "00-集合.md": "04-Java集合.md",
        "00-排序方式.md": "05-排序算法.md",
    }
    for source_name, target_name in mapping.items():
        text = (SOURCE / source_name).read_text(encoding="utf-8-sig")
        # 每个素材同样过一遍术语净化，保证全站措辞口径一致。
        text = calm_language(text)
        if source_name == "Hot100-Java基础语法、常用类与API速查.md":
            # 只对“Java 速查”这一篇做站内链接改写：原稿里指向同级素材的链接
            # 在站的目录结构下会 404，这里显式映射为站内目标路径。
            local_links = {
                "00-集合.md": "04-Java集合.md",
                "00-数组.md": "02-Java数组.md",
                "00-字符串.md": "03-Java字符串.md",
                "00-排序方式.md": "05-排序算法.md",
                "01-哈希表.md": "../02-专题/01-哈希表.md",
                "02-双指针.md": "../02-专题/02-双指针.md",
                "03-滑动窗口.md": "../02-专题/03-滑动窗口.md",
                "07-链表.md": "../02-专题/07-链表.md",
                "08-二叉树.md": "../02-专题/08-二叉树.md",
                "09-图论.md": "../02-专题/09-图论.md",
                "10-回溯.md": "../02-专题/10-回溯.md",
                "11-二分查找.md": "../02-专题/11-二分查找.md",
                "12-栈.md": "../02-专题/12-栈.md",
                "13-堆.md": "../02-专题/13-堆.md",
                "15-动态规划.md": "../02-专题/15-动态规划.md",
            }
            for old, new in local_links.items():
                # 源稿里的链接可能是明文或 URL 编码（%E9...）两种形态，都改写。
                text = text.replace(f"]({old})", f"]({new})")
                text = text.replace(f"]({urllib.parse.quote(old)})", f"]({new})")
        # 保持排序动画的原相对链接可用。
        # 其余素材（数组/字符串/集合/排序）不做链接改写。
        write(basics / target_name, text)
    if (SOURCE / "pic").exists():
        # 图库整体复制到 01-基础/pic，供速查素材里的排序动画图片引用。
        shutil.copytree(SOURCE / "pic", basics / "pic", dirs_exist_ok=True)

    # 原稿归档：整目录复制未修改副本 + 归档说明，用于对照“整理前后的算法方法”。
    archive = ROOT / "books" / "hot100" / "99-原稿归档"
    archive.mkdir(parents=True, exist_ok=True)
    for path in SOURCE.glob("*.md"):
        shutil.copy2(path, archive / path.name)
    write(archive / "README.md", "# 原稿归档\n\n这里保存源目录 Markdown 的未修改副本，用于核对整理前后的算法方法。主学习入口请返回 [总目录](../../../README.md)。")

    # 可视化素材：复制交互组件 HTML 与图片到 05-可视化/，供 build_html_site 嵌入题页页尾演示。
    visuals = ROOT / "books" / "hot100" / "05-可视化"
    visuals.mkdir(parents=True, exist_ok=True)
    for path in (SOURCE / "可视化").glob("*.html"):
        shutil.copy2(path, visuals / path.name)
    if (SOURCE / "pic").exists():
        shutil.copytree(SOURCE / "pic", visuals / "assets", dirs_exist_ok=True)


def render_dashboard() -> None:
    """从模板生成学习站首页 index.html（浏览器中的本地学习站入口）。

    做法：把题目清单 JSON 注入 HTML 模板的 4 个占位符（__HOT100_PROBLEMS__ 等）。
    JSON 里每题带 note 字段 = 对应 03-题解/<专题>/<题号>.html 的路径，
    前端搜索/筛选命中后可直接跳转到 build_html_site 生成的静态题页。
    输入：tools/templates/dashboard.tpl 模板 + PROBLEMS；输出：根目录 index.html。
    """
    # 资源版本号：改动前端模板/JS/CSS 后递增，用于让浏览器强制刷新静态资源缓存。
    dashboard_asset_version = "20260830-enhance"
    data = []
    for p in PROBLEMS:
        data.append({
            "id": p["id"],
            "title": p["title"],
            "category": p["category"],
            "difficulty": p["difficulty"],
            "method": p["method"],
            # note 预先算好静态题页路径（.md → .html），前端无需自己拼路径。
            "note": f"books/hot100/03-题解/{p['folder']}/{Path(problem_filename(p)).with_suffix('.html').name}",
        })
    # ensure_ascii=False 保留中文可读；replace("</", "<\\/") 防止 JSON 里出现
    # “</script>”直接截断内联脚本标签（语法破损与注入风险），<\/ 在 JS 字符串中即普通左斜杠。
    json_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    template_path = ROOT / "tools" / "templates" / "dashboard.tpl"
    # 专题数由题目列表现场去重统计，与模板里的 __TOPIC_COUNT__ 保持一致。
    topics = sorted({p["category"] for p in PROBLEMS})
    # 顺序替换 4 个占位符；模板其余静态部分原样保留，最终写回根目录 index.html。
    page = (
        template_path.read_text(encoding="utf-8")
        .replace("__HOT100_PROBLEMS__", json_data)
        .replace("__PROBLEM_COUNT__", str(len(PROBLEMS)))
        .replace("__TOPIC_COUNT__", str(len(topics)))
        .replace("__ASSET_VERSION__", dashboard_asset_version)
    )
    write(ROOT / "index.html", page)


def build() -> None:
    """整条构建链的调度入口 —— 从原始输入一直产出完整学习站。

    执行顺序（每步只依赖前面步骤的产物，串行即可）：
      ① extract_original_sections()  收集源笔记题解段；
      ② copy_source_materials()      复制 01-基础 / 原稿归档 / 可视化素材；
      ③ render_problem_pages()       逐题生成 03-题解；
      ④ render_topics() / render_readme() / render_overview_files() / render_templates()
                                    生成专题、README、总览、模板四类导航页；
      ⑤ render_dashboard()           注入 JSON 生成 index.html；
      ⑥ 末尾两个 subprocess：先跑 tools/build_library.py（构建 SQLite 本地学习库），
         再跑 tools/build_html_site.py（Markdown 编译为静态 HTML 站点、含页尾交互演示）；
         check=True：任一脚本失败立即抛异常、终止整条链（快速失败）；
      ⑦ 汇总写入 tools/build-summary.json 并打印，供 check_hot100 / 维护脚本对照。
    """
    # 幂等：目录已存在时不报错。
    ROOT.mkdir(parents=True, exist_ok=True)
    # ① 源笔记题解段，随后传给 render_problem_pages。
    original = extract_original_sections()
    # ② 素材复制（与题解生成互不依赖，可先做）。
    copy_source_materials()
    # ③ 核心输出：100 道独立题页。
    # 增量：源笔记/扩展题源/题目元数据未变且 100 道题页都存在 → 跳过重写；
    # 聚合导航页（专题/README/总览/模板/首页）仍全量生成（渲染量小）。
    cache = build_cache.load_cache(ROOT)
    tool_sha = build_cache.tools_fingerprint(Path(__file__).resolve())
    if cache.get("tool_sha") != tool_sha or cache.get("version") != build_cache.CACHE_VERSION:
        cache = {"version": build_cache.CACHE_VERSION, "tool_sha": tool_sha, "entries": {}}
    problems_sha = _problems_source_hash()
    problems_outputs = [
        f"books/hot100/03-题解/{problem['folder']}/{problem_filename(problem)}"
        for problem in PROBLEMS
    ]
    if build_cache.needs_rebuild(cache, "problems:", problems_sha, problems_outputs, ROOT):
        render_problem_pages(original)
        build_cache.mark_built(cache, "problems:", problems_sha, problems_outputs)
        print(f"Problem pages rebuilt: {len(PROBLEMS)}")
    else:
        print(f"Problem pages: {len(PROBLEMS)} up to date (incremental skip)")
    build_cache.save_cache(ROOT, cache)
    # ④ 专题页（链接到 ③ 产出的题页文件）。
    render_topics()
    # ④ README 总入口（引用专题页与题数）。
    render_readme()
    # ④ 学习路线 / 模式地图 / 复习清单 / 复盘模板。
    render_overview_files()
    # ④ 算法模板 / 边界检查表 / 数据结构选择表。
    render_templates()
    # ⑤ 首页 index.html（依赖 ③ 的 .html 路径约定）。
    render_dashboard()
    library_builder = ROOT / "tools" / "build_library.py"
    # ⑥ 前半段：构建 SQLite 本地学习库（供本地学习站记录看题与复习进度）。
    if library_builder.exists():
        # 用与本次相同的解释器（sys.executable）调用；脚本可缺省，不存在的步骤自动跳过。
        subprocess.run([sys.executable, str(library_builder)], check=True)
    summary = {
        # 题页总数
        "problem_pages": len(PROBLEMS),
        # 源笔记覆盖的题号数
        "original_unique_ids": len(original),
        # 相对源笔记新增的题号
        "added_ids": sorted(set(PROBLEM_BY_ID) - set(original)),
        # 多解法段总数
        "source_variants": sum(len(v) for v in original.values()),
    }
    # ⑦ 中间产物落盘：构建摘要先写文件，供 check_hot100 / 后续脚本与人工核对。
    write(ROOT / "tools" / "build-summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    html_builder = ROOT / "tools" / "build_html_site.py"
    # ⑥ 后半段：把目录里全部 Markdown 编译为静态 HTML 站点（题页页尾交互演示也由此注入）。
    if html_builder.exists():
        subprocess.run([sys.executable, str(html_builder)], check=True)
    # ⑦ 向终端输出摘要，供人工核对。
    print(json.dumps(summary, ensure_ascii=False))


# 命令入口：python tools/build_hot100.py 即触发整条构建链；
# 被其它脚本 import 时（如 check_hot100）只加载数据常量与函数定义，不执行构建。
if __name__ == "__main__":
    build()
