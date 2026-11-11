# Scaled Dot-Product Attention

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

### Python 实现

```python
# 题目：Scaled Dot-Product Attention
# 算法：按题意模拟
# 模式：ACM（stdin/stdout）

import math


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def attention(query, keys, values):
    dimension = len(query)
    scores = [dot(query, key) / math.sqrt(dimension) for key in keys]
    weights = softmax(scores)
    output = [0.0] * len(values[0])
    for weight, value in zip(weights, values):
        for index, number in enumerate(value):
            output[index] += weight * number
    return output, weights
```

**追问**：Mask 加在哪里？为什么除以 `sqrt(d_k)`？Multi-Head 如何拆分和合并？

### Java 实现

```java
// 题目：Scaled Dot-Product Attention
// 算法：按题意模拟
// 模式：ACM（stdin/stdout）

import java.util.ArrayList;
import java.util.List;

final class ScaledDotProductAttention {
    static double dot(List<Double> left, List<Double> right) {
        double sum = 0.0;
        int n = Math.min(left.size(), right.size());
        for (int i = 0; i < n; i++) {
            sum += left.get(i) * right.get(i);
        }
        return sum;
    }

    static List<Double> softmax(List<Double> values) {
        List<Double> result = new ArrayList<>();
        if (values.isEmpty()) {
            return result;
        }
        double maximum = Double.NEGATIVE_INFINITY;
        for (double value : values) {
            maximum = Math.max(maximum, value);
        }
        double total = 0.0;
        for (double value : values) {
            total += Math.exp(value - maximum);
        }
        for (double value : values) {
            result.add(Math.exp(value - maximum) / total);
        }
        return result;
    }

    static final class Result {
        final double[] output;
        final List<Double> weights;

        Result(double[] output, List<Double> weights) {
            this.output = output;
            this.weights = weights;
        }
    }

    static Result attention(List<Double> query, List<List<Double>> keys, List<List<Double>> values) {
        int dimension = query.size();
        List<Double> scores = new ArrayList<>();
        for (List<Double> key : keys) {
            scores.add(dot(query, key) / Math.sqrt(dimension));
        }
        List<Double> weights = softmax(scores);
        int outputSize = values.get(0).size();
        double[] output = new double[outputSize];
        for (int i = 0; i < weights.size(); i++) {
            double weight = weights.get(i);
            List<Double> value = values.get(i);
            for (int j = 0; j < outputSize; j++) {
                output[j] += weight * value.get(j);
            }
        }
        return new Result(output, weights);
    }

    // 主函数：读取输入并输出答案
    public static void main(String[] args) {
        List<List<Double>> keys = new ArrayList<>();
        keys.add(java.util.Arrays.asList(1.0, 0.0));
        keys.add(java.util.Arrays.asList(0.0, 1.0));
        List<List<Double>> values = new ArrayList<>();
        values.add(java.util.Arrays.asList(1.0, 2.0));
        values.add(java.util.Arrays.asList(3.0, 4.0));
        Result result = attention(java.util.Arrays.asList(1.0, 1.0), keys, values);
        System.out.println(java.util.Arrays.toString(result.output));
        System.out.println(result.weights);
    }
}
```
