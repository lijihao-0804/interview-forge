# 稳定 Softmax

> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题

**要求**：实现一维 Softmax，避免大数溢出。

### Python 实现

```python
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
import java.util.ArrayList;
import java.util.List;

final class StableSoftmax {
    static List<Double> softmax(List<Double> values) {
        List<Double> result = new ArrayList<>();
        if (values == null || values.isEmpty()) {
            return result;
        }
        double maximum = Double.NEGATIVE_INFINITY;
        for (double value : values) {
            if (value > maximum) {
                maximum = value;
            }
        }
        List<Double> exps = new ArrayList<>();
        double total = 0.0;
        for (double value : values) {
            double e = Math.exp(value - maximum);
            exps.add(e);
            total += e;
        }
        for (double e : exps) {
            result.add(e / total);
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(softmax(java.util.Arrays.asList(1.0, 2.0, 3.0)));
    }
}
```
