"""Hand-checked outcomes for the worked examples, including multi-case explanations.

The second field records observations that identify the answer in the actual UI.
The delimiters && and >> separate earlier observations and final-step evidence.
The first field is intentionally independent of generated demo data and ACM inputs.
"""

OUTCOMES = {
    186: ("now go we", "now|go|we"),
    1259: ("5", "累计5"),
    711: ("1", "形状数=1"),
    716: ("popMax=6, top=2, peekMax=6", "最大值为 6 >> top=2，peekMax=6"),
    1274: ("2", "总数=2"),
    723: ("[[0,0,0],[1,2,1],[2,3,2]]", "0,0,0|1,2,1|2,3,2"),
    727: ("ab", "得 ab"),
    755: ("[3,2,2]", "结果 [3,2,2]"),
    734: ("false", "false"),
    737: ("true", "true"),
    760: ("[2,0,1]", "映射 [2,0,1]"),
    426: ("2→4→7→2", "正向访问 2、4、7 后回到 2"),
    742: ("9", "到叶 9"),
    1236: ("a.test/1, a.test/2", "seen:a.test/1|seen:a.test/2"),
    750: ("3", "3×2÷2=3"),
    751: ("10.0.0.2/31, 10.0.0.4/31", "10.0.0.2/31 >> 选 .4/31"),
    243: ("1", "ans=1"),
    244: ("1", "差1"),
    245: ("2", "距离2"),
    246: ("619: true, 169: false", "true >> false"),
    247: ("11,69,88,96", "11|69|88|96"),
    248: ("2", "ans=2"),
    249: ("{az,ba}, {ab}", "{az,ba} 和 {ab}"),
    250: ("2", "count=2"),
    251: ("3,4,5; hasNext=false", "3 已读 && [4,5] >> false"),
    252: ("false", "false"),
    253: ("2", "房数2"),
    254: ("[2,8],[2,2,4],[2,2,2,2],[4,4]", "[2,8] && [2,2,4] && [2,2,2,2] >> [4,4]"),
    255: ("false", "false"),
    256: ("4", "末色0:4|末色1:6|末色2:6"),
    758: ("c<b>abd</b>e", "c|<b>abd</b>|e"),
    759: ("[[4,7]]", "空闲[4,7]"),
    259: ("2", "count=2"),
    428: ("7→[2,9], 9→[4]", "7→2|7→9 >> 9→4"),
    261: ("false", "false"),
    431: ("1→[2,3,4], 3→[5]", "1:[2,3,4]|3:[5]"),
    1176: ("0", "ans=0"),
    265: ("3", "最小为 3"),
    266: ("aabbc: true, aabc: false", "true >> false"),
    267: ("abba, baab", "得到 abba >> 得到 baab"),
    269: ("abzc (a<b, z<c)", "a|b|z|c"),
    270: ("4", "返回4"),
    271: ("decoded: [a/b, empty string]", "正文a/b >> 空串"),
    272: ("{3,6}", "{3,6}"),
    772: ("9", "3+6=9"),
    702: ("3", "返回3"),
    276: ("6", "输出 6"),
    277: ("2", "名人2"),
    774: ("3", "d=3|需2|站点3,6"),
    776: ("3→4, 5→8", "3.right=4|5.right=8"),
    280: ("[1,4,2,3]", "交换为 [1,4,2,3]"),
    281: ("4,2,9,8", "已输出 [4,2] >> 输出 9|输出 8"),
    285: ("8", "返回 8"),
    286: ("[0,1,2,-1,infinity]", "0|1|2|−1|∞"),
    288: ("false, true", "stone:false|at:true"),
    291: ("true", "返回 true"),
    293: ("---+++, ++---+, ++-+--", "输出 ---+++ && 输出 ++---+ >> 输出 ++-+--"),
    294: ("true", "G(4)=2"),
    296: ("5", "合计 5"),
    298: ("3", "best=3"),
    302: ("4", "area=4"),
    305: ("[1,2,1,1]", "输出 [1,2,1,1]"),
    800: ("#1122ff", "#1122ff"),
    308: ("6, 11", "右列6 >> 右列11"),
    311: ("[[8,10],[-3,0]]", "[[8,10],[-3,0]]"),
    314: ("[[2],[7,4,5],[9]]", "[2]|[7,4,5]|[9]"),
    317: ("3", "最小3"),
    320: ("2, 1b, a1, ab", "结果2 && 结果1b >> a1|ab"),
    323: ("2", "答案2"),
    325: ("5", "长度5"),
    333: ("2", "best=2"),
    708: ("4→5→1→3→4", "4→5→1→3→4"),
    339: ("20", "ans=20"),
    340: ("4", "长度4"),
    346: ("4,6,9", "平均4 && 平均6 >> 平均9"),
    348: ("player 1", "胜者1"),
    351: ("9", "4+4+1=9"),
    353: ("1,1,1", "身体 [1,0]，得分 1 && 身体 [2,1]，得分仍为 1 >> 分1"),
    489: ("two cells cleaned", "已扫2"),
    356: ("true", "返回 true"),
    358: ("abcab (distance 3)", "a|b|c|a|b"),
    359: ("true,false,true", "t=2，队列 [(2,A)]，返回 true && 返回 false >> 返回 true"),
    360: ("[1,4,9]", "结果 [1,4,9]"),
    361: ("2", "最大2"),
    362: ("3,1", "总3 >> 总1"),
    364: ("16", "加权16"),
    366: ("[[2,7],[8],[6]]", "[[2,7],[8],[6]]"),
    369: ("998+1=999; 999+1=1000", "返回 9→9→9 >> 1|0|0|0"),
    370: ("[0,2,1,2]", "0|2|1|2"),
    379: ("after release: 0", "再取0"),
    1265: ("C,B,A", "打印C|打印B|打印A"),
    408: ("k6d: true", "返回 true"),
    411: ("c1r or car, size 3", "c1r:3|car:3"),
    418: ("2", "遍数2"),
    425: ("[ab,ba], [ba,ab]", "保存 [ab,ba] >> 保存 [ba,ab]"),
    439: ("4", "结果4"),
    444: ("false, then true after 2→3", "原约束返回 false >> 返回 true"),
    465: ("1", "笔数1"),
    469: ("false", "返回 false"),
    471: ("4[ab]", "最短为 4[ab]"),
}


def check_graph(pid, history):
    answer, marks = OUTCOMES[pid]
    def rendered(step):
        return " ".join((step["state"], "|".join(step["cells"]), step["explanation"]))
    previous, sep, final = marks.rpartition(" >> ")
    issues = []
    if not history:
        return answer, ["missing graphical history"]
    if sep:
        before = " ".join(map(rendered, history[:-1]))
        observations = previous.split(" && ")
        for token in observations:
            if token not in before:
                issues.append("missing earlier answer evidence: "+token)
    if final not in rendered(history[-1]):
        issues.append("graphical final answer differs: "+answer)
    return answer, issues
