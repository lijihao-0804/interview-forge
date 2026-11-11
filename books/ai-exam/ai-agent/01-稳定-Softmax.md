# 稳定 Softmax

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

**要求**：实现一维 Softmax，避免大数溢出。

### Python 实现

```python
# 题目：稳定 Softmax
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）

import math


def softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    maximum = max(values)
    exps = [math.exp(value - maximum) for value in values]
    total = sum(exps)
    return [value / total for value in exps]
```

**追问**：为什么减去最大值不改变结果？如何扩展到二维 Batch？

### Java 实现

```java
// 题目：稳定 Softmax
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）

import java.util.ArrayList;
import java.util.List;

final class StableSoftmax {
    // 核心方法：softmax
    static List<Double> softmax(List<Double> values) {
        List<Double> result = new ArrayList<>();
        // 条件判断
        if (values == null || values.isEmpty()) {
            // 返回结果
            return result;
        }
        double maximum = Double.NEGATIVE_INFINITY;
        // 循环处理
        for (double value : values) {
            // 条件判断
            if (value > maximum) {
                maximum = value;
            }
        }
        List<Double> exps = new ArrayList<>();
        double total = 0.0;
        // 循环处理
        for (double value : values) {
            double e = Math.exp(value - maximum);
            exps.add(e);
            total += e;
        }
        // 循环处理
        for (double e : exps) {
            result.add(e / total);
        }
        // 返回结果
        return result;
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) {
        System.out.println(softmax(java.util.Arrays.asList(1.0, 2.0, 3.0)));
    }
}
```
