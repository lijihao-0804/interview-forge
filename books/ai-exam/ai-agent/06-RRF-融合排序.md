# RRF 融合排序

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
# 题目：RRF 融合排序
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）

from collections import defaultdict


def reciprocal_rank_fusion(rankings, constant=60):
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (constant + rank)
    return sorted(scores, key=scores.get, reverse=True)
```

**追问**：为什么 RRF 不直接使用不同检索器的原始分数？`constant` 如何影响头部结果？

## 第三层：工具与 Agent 运行时

Agent 工程最容易出事故的部分：参数校验、循环守卫、幂等、流式解析。

### Java 实现

```java
// 题目：RRF 融合排序
// 算法：排序 + 扫描
// 模式：ACM（stdin/stdout）

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class ReciprocalRankFusion {
    // 核心方法：reciprocalRankFusion
    static List<String> reciprocalRankFusion(List<List<String>> rankings, int constant) {
        Map<String, Double> scores = new LinkedHashMap<>();
        // 循环处理
        for (List<String> ranking : rankings) {
            // 枚举位置 i
            for (int i = 0; i < ranking.size(); i++) {
                String docId = ranking.get(i);
                int rank = i + 1;
                scores.merge(docId, 1.0 / (constant + rank), Double::sum);
            }
        }
        List<String> result = new ArrayList<>(scores.keySet());
        result.sort((p, q) -> Double.compare(scores.get(q), scores.get(p)));
        // 返回结果
        return result;
    }

    // 核心方法：reciprocalRankFusion
    static List<String> reciprocalRankFusion(List<List<String>> rankings) {
        // 返回结果
        return reciprocalRankFusion(rankings, 60);
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) {
        List<List<String>> rankings = new ArrayList<>();
        rankings.add(java.util.Arrays.asList("a", "b", "c"));
        rankings.add(java.util.Arrays.asList("b", "c", "d"));
        System.out.println(reciprocalRankFusion(rankings));
    }
}
```
