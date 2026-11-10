# LSTM 激活函数

> 来源：https://onefly.top/zero2Leetcode/04_real_interviews/meituan/algo-20260818/ · 美团 · 2026-08-18 · 算法岗

LSTM 的遗忘门、输入门和输出门使用 Sigmoid，细胞状态更新与隐状态输出使用 tanh。正确说法是：A. Sigmoid 饱和时容易梯度消失，tanh 用于控制信息是否通过；B. Sigmoid 产生 0 到 1 的门控值，tanh 用于状态与输出的数值变换；C. 两者职责与 B 相反；D. tanh 可以抵消门控造成的梯度消失。
答案 ：B。Sigmoid 的值域适合作为保留比例，tanh 的值域为 [-1,1] ，用于生成候选状态和输出值。
输入
输出

```text
无编程输入
B
```

## 题解代码

### Python 实现

```python
print("B")
```

## 复杂度分析

本题为理论选择题，无算法复杂度。
