# AI 岗数学复习手册：线代与概率速查

> 适合：**学过概率论和线性代数，但准备 AI 岗笔试时已经忘得差不多**的人。
>
> 目标：不从头学教材，用一份手册把线代、概率、统计、信息论和 AI 常用公式重新串起来。
>
> 用法：先看每章的“必会公式”，遮住公式自己复述一遍；不要求推导证明；最后用站内 AI 岗选择题里的数学题做 20～30 道检验。
>
> 标记：`★` 表示 AI 岗笔试高频；如果时间很紧，优先看带 `★` 的段落和最后第 10 章。

---

## 第 1 章 线性代数：向量与矩阵

### 1.1 基本对象

- **标量**：一个数，记为 $a$。
- **向量**：一列数，默认是列向量：

$$
\mathbf{x}=\begin{bmatrix}x_1\\x_2\\\vdots\\x_n\end{bmatrix}\in\mathbb{R}^n
$$

- **矩阵**：$m$ 行 $n$ 列，记为 $A\in\mathbb{R}^{m\times n}$；$A_{ij}$ 表示第 $i$ 行第 $j$ 列的元素。
- **张量**：更高维数组，深度学习中常见形状如 `[batch, seq_len, hidden]`。

### 1.2 ★ 向量运算

内积（点积）：

$$
\mathbf{x}^T\mathbf{y}=\sum_{i=1}^{n}x_iy_i
$$

外积：

$$
\mathbf{x}\mathbf{y}^T=
\begin{bmatrix}
x_1y_1 & \cdots & x_1y_n\\
\vdots & & \vdots\\
x_my_1 & \cdots & x_my_n
\end{bmatrix}
$$

$L_2$ 范数：

$$
\lVert\mathbf{x}\rVert_2=\sqrt{\sum_{i=1}^{n}x_i^2}
$$

余弦相似度：

$$
\cos(\mathbf{x},\mathbf{y})=
\frac{\mathbf{x}^T\mathbf{y}}{\lVert\mathbf{x}\rVert_2\lVert\mathbf{y}\rVert_2}
$$

余弦相似度只看方向，不看长度； embedding 检索、推荐召回里非常常见。

### 1.3 ★ 矩阵运算与形状

矩阵乘法：

$$
(AB)_{ij}=\sum_{k=1}^{n}A_{ik}B_{kj}
$$

可乘条件：**$A$ 的列数必须等于 $B$ 的行数**。若 $A$ 是 $m\times n$，$B$ 是 $n\times p$，则 $AB$ 是 $m\times p$。

常用性质：

$$
(AB)^T=B^TA^T,\qquad (AB)^{-1}=B^{-1}A^{-1}
$$

$$
\operatorname{tr}(AB)=\operatorname{tr}(BA)
$$

$$
\det(AB)=\det(A)\det(B)
$$

其中逆和行列式只对方阵有定义。

### 1.4 ★ 秩、逆与行列式

- **秩** $\operatorname{rank}(A)$：矩阵中线性无关的列（或行）的最大数量。
- **满秩**：$n\times n$ 矩阵的秩为 $n$。
- **可逆**：方阵 $A$ 满足 $AA^{-1}=A^{-1}A=I$；等价于 $\det(A)\neq0$、秩为 $n$。
- **行列式**：描述线性变换对体积的缩放；$\det(A)=0$ 表示变换把空间压扁，不可逆。

常见不等式：

$$
\operatorname{rank}(AB)\le\min(\operatorname{rank}(A),\operatorname{rank}(B))
$$

### 1.5 必会判断

- 矩阵乘法不满足交换律：一般 $AB\neq BA$。
- $A^TA$ 和 $AA^T$ 都是对称半正定矩阵。
- 若 $A$ 可逆，则 $Ax=b$ 有唯一解 $x=A^{-1}b$。
- 若 $A$ 不可逆，则可能无解或有无穷多解。

---

## 第 2 章 线性变换、特征值与 SVD

### 2.1 ★ 线性变换

矩阵可以看成线性变换：

$$
T(\mathbf{x})=A\mathbf{x}
$$

例如旋转、缩放、投影、剪切都能用矩阵表示。矩阵的列就是基向量经过变换后的位置。

### 2.2 ★ 特征值与特征向量

若存在非零向量 $\mathbf{z}$ 和标量 $\lambda$，使得：

$$
A\mathbf{z}=\lambda\mathbf{z}
$$

则 $\lambda$ 是特征值，$\mathbf{z}$ 是对应的特征向量。

直觉：特征向量在经过矩阵变换后**方向不变**，只被拉伸或压缩 $\lambda$ 倍。

对称矩阵的谱定理：

$$
A=U\Lambda U^T
$$

其中 $U$ 是正交矩阵，$\Lambda$ 是对角矩阵。对称矩阵一定有实特征值，并且可以正交对角化。

### 2.3 ★ 半正定矩阵

$A$ 是半正定矩阵（PSD），若：

$$
A=A^T,\qquad \forall\mathbf{x},\ \mathbf{x}^TA\mathbf{x}\ge0
$$

正定矩阵要求对非零向量严格大于 0。协方差矩阵、核矩阵、$A^TA$ 都是半正定的。

### 2.4 ★ SVD

任意矩阵 $A\in\mathbb{R}^{m\times n}$ 都可以分解为：

$$
A=U\Sigma V^T
$$

- $U$：左奇异向量，$m\times m$ 正交矩阵；
- $\Sigma$：奇异值对角矩阵，$m\times n$；
- $V$：右奇异向量，$n\times n$ 正交矩阵。

奇异值从大到小排列。只保留前 $k$ 个奇异值可以得到低秩近似：

$$
A\approx U_k\Sigma_k V_k^T
$$

### 2.5 ★ PCA 与 SVD 的关系

PCA 的步骤：

1. 对数据做中心化；
2. 计算协方差矩阵 $C=\frac{1}{n-1}X^TX$；
3. 求 $C$ 的前 $k$ 个特征向量；
4. 把数据投影到这些特征向量上。

PCA 也可以通过对中心化后的数据矩阵做 SVD 实现。特征值越大，对应方向保留的方差越多。

**易错点**：

- PCA 找的是方差最大的方向，不是方差最小；
- 做 PCA 前通常要标准化，否则量纲大的特征会主导；
- 标准化和 PCA 都只能在训练集上 `fit`，测试集只能 `transform`；
- 协方差矩阵是对称半正定的，所以它的特征值非负。

---

## 第 3 章 矩阵微积分与优化基础

矩阵求导题看起来吓人，实际只需要记住“形状、梯度、链式法则”三件事。

### 3.1 ★ 梯度与 Hessian

标量函数 $f(\mathbf{x})$ 对向量 $\mathbf{x}$ 的梯度：

$$
\nabla_{\mathbf{x}}f=
\begin{bmatrix}
\frac{\partial f}{\partial x_1}\\
\vdots\\
\frac{\partial f}{\partial x_n}
\end{bmatrix}
$$

Hessian 是二阶偏导矩阵：

$$
(\nabla^2f)_{ij}=\frac{\partial^2f}{\partial x_i\partial x_j}
$$

Hessian 半正定时，函数是凸函数；凸函数的局部最小值就是全局最小值。

### 3.2 ★ 必背矩阵求导

$$
\frac{\partial(\mathbf{a}^T\mathbf{x})}{\partial\mathbf{x}}=\mathbf{a}
$$

$$
\frac{\partial(\mathbf{x}^T A\mathbf{x})}{\partial\mathbf{x}}=(A+A^T)\mathbf{x}
$$

$$
\frac{\partial\lVert\mathbf{x}\rVert_2^2}{\partial\mathbf{x}}=2\mathbf{x}
$$

$$
\frac{\partial\operatorname{tr}(AB)}{\partial A}=B^T
$$

$$
\frac{\partial\log\det(A)}{\partial A}=(A^{-1})^T
$$

### 3.3 ★ 梯度下降

$$
\theta_{t+1}=\theta_t-\eta\nabla_\theta L(\theta_t)
$$

- $\eta$ 是学习率；
- 学习率太大会震荡或发散，太小会收敛慢；
- 深度学习中通常用 mini-batch 随机梯度下降或其变体（Momentum、Adam）。

### 3.4 链式法则

复合函数 $L=f(g(x))$：

$$
\frac{dL}{dx}=\frac{dL}{dg}\cdot\frac{dg}{dx}
$$

反向传播本质上就是按计算图从后往前反复使用链式法则。

---

## 第 4 章 概率基础

概率题先写清事件和条件，再判断独立、互斥与方向。

### 4.1 ★ 样本空间、事件与概率公理

- 样本空间 $S$：所有可能结果的集合；
- 事件 $E$：样本空间的子集；
- 概率满足：

$$
0\le P(E)\le1,\qquad P(S)=1
$$

若 $E_1,\dots,E_n$ 两两互斥：

$$
P\left(\bigcup_{i=1}^{n}E_i\right)=\sum_{i=1}^{n}P(E_i)
$$

### 4.2 排列与组合

排列：

$$
P(n,r)=\frac{n!}{(n-r)!}
$$

组合：

$$
C(n,r)=\binom{n}{r}=\frac{n!}{r!(n-r)!}
$$

“有序”用排列，“无序”用组合。

### 4.3 ★ 条件概率与贝叶斯

条件概率：

$$
P(A\mid B)=\frac{P(A\cap B)}{P(B)},\qquad P(B)>0
$$

乘法公式：

$$
P(A\cap B)=P(A\mid B)P(B)=P(B\mid A)P(A)
$$

贝叶斯公式：

$$
P(A\mid B)=\frac{P(B\mid A)P(A)}{P(B)}
$$

扩展形式：

$$
P(A_k\mid B)=
\frac{P(B\mid A_k)P(A_k)}
{\sum_{i=1}^{n}P(B\mid A_i)P(A_i)}
$$

其中 $P(A_k)$ 是先验，$P(B\mid A_k)$ 是似然，$P(A_k\mid B)$ 是后验。

### 4.4 ★ 独立与互斥

独立：

$$
P(A\cap B)=P(A)P(B)
$$

等价地，当 $P(B)>0$ 时：

$$
P(A\mid B)=P(A)
$$

**互斥不等于独立**：互斥事件满足 $P(A\cap B)=0$，通常不是独立；独立事件可以同时发生。

### 4.5 全概率公式

若 $A_1,\dots,A_n$ 构成样本空间的一个划分：

$$
P(B)=\sum_{i=1}^{n}P(B\mid A_i)P(A_i)
$$

经典应用：疾病检测、垃圾邮件过滤、贝叶斯分类器。

---

## 第 5 章 随机变量、期望与方差

这一章是 AI 笔试计算题的主体：先认分布，再套期望、方差和协方差。

### 5.1 ★ 随机变量与分布

- 离散型：概率质量函数 $p(x)=P(X=x)$；
- 连续型：概率密度函数 $f(x)$，满足 $f(x)\ge0$ 且 $\int f(x)dx=1$；
- 累积分布函数：

$$
F(x)=P(X\le x)
$$

连续型时：

$$
f(x)=\frac{dF(x)}{dx}
$$

### 5.2 ★ 期望

离散型：

$$
E[X]=\sum_i x_ip(x_i)
$$

连续型：

$$
E[X]=\int_{-\infty}^{+\infty}xf(x)dx
$$

期望的线性性（永远成立）：

$$
E[aX+bY+c]=aE[X]+bE[Y]+c
$$

即使 $X,Y$ 不独立也成立。

### 5.3 ★ 方差与协方差

方差：

$$
\operatorname{Var}(X)=E[(X-E[X])^2]=E[X^2]-(E[X])^2
$$

协方差：

$$
\operatorname{Cov}(X,Y)=E[(X-E[X])(Y-E[Y])]=E[XY]-E[X]E[Y]
$$

相关系数：

$$
\rho_{XY}=\frac{\operatorname{Cov}(X,Y)}{\sigma_X\sigma_Y}
$$

$$
-1\le\rho_{XY}\le1
$$

和的方差：

$$
\operatorname{Var}(aX+bY)=
a^2\operatorname{Var}(X)+b^2\operatorname{Var}(Y)+2ab\operatorname{Cov}(X,Y)
$$

若 $X,Y$ 独立，协方差为 0，和的方差等于方差之和。

### 5.4 ★ 独立、不相关与条件期望

- 独立一定不相关，但不相关不一定独立；
- 对联合正态分布，不相关等价于独立；
- 全期望公式：

$$
E[X]=E[E[X\mid Y]]
$$

- 全方差公式：

$$
\operatorname{Var}(X)=E[\operatorname{Var}(X\mid Y)]+\operatorname{Var}(E[X\mid Y])
$$

### 5.5 常见陷阱

- $E[XY]=E[X]E[Y]$ 只在独立（或至少不相关）时成立；
- $\operatorname{Var}(X+Y)=\operatorname{Var}(X)+\operatorname{Var}(Y)$ 需要 $X,Y$ 不相关；
- $E[1/X]\neq1/E[X]$，概率题里经常用来设陷阱。

---

## 第 6 章 常见分布

常见分布不需要背密度函数，先记住期望、方差和适用场景。

### 6.1 ★ 分布速查表

| 分布 | 记号 | 期望 | 方差 | 典型场景 |
|---|---|---|---|---|
| 伯努利 | $X\sim\operatorname{Bernoulli}(p)$ | $p$ | $p(1-p)$ | 一次成败试验 |
| 二项 | $X\sim B(n,p)$ | $np$ | $np(1-p)$ | $n$ 次独立伯努利中成功次数 |
| 泊松 | $X\sim\operatorname{Poisson}(\lambda)$ | $\lambda$ | $\lambda$ | 单位时间事件次数 |
| 均匀 | $X\sim U(a,b)$ | $\frac{a+b}{2}$ | $\frac{(b-a)^2}{12}$ | 区间等可能 |
| 正态 | $X\sim N(\mu,\sigma^2)$ | $\mu$ | $\sigma^2$ | 噪声、测量误差、聚合数据 |
| 指数 | $X\sim\operatorname{Exp}(\lambda)$ | $\frac{1}{\lambda}$ | $\frac{1}{\lambda^2}$ | 等待时间，无记忆性 |

### 6.2 ★ 中心极限定理

若 $X_1,\dots,X_n$ 独立同分布，均值为 $\mu$，方差为 $\sigma^2$，则样本均值：

$$
\bar X=\frac{1}{n}\sum_{i=1}^{n}X_i
$$

在 $n$ 较大时近似服从：

$$
\bar X\approx N\left(\mu,\frac{\sigma^2}{n}\right)
$$

这就是为什么很多统计量可以近似用正态分布做区间估计和假设检验。

### 6.3 大数定律

当样本量 $n\to\infty$ 时，样本均值依概率收敛到真实均值：

$$
\bar X\to\mu
$$

### 6.4 正态分布的 68-95-99.7 法则

- 约 68% 落在 $\mu\pm\sigma$；
- 约 95% 落在 $\mu\pm2\sigma$；
- 约 99.7% 落在 $\mu\pm3\sigma$。

### 6.5 分布之间的关系

- 二项分布在 $n$ 大、$p$ 小时可近似为泊松分布；
- 指数分布具有无记忆性：

$$
P(X>s+t\mid X>s)=P(X>t)
$$

- 多个独立正态变量线性组合仍是正态分布。

---

## 第 7 章 参数估计与统计推断

参数估计和统计推断常以“解释概念 + 小计算”出现，重点是 MLE、MAP 和评价指标。

### 7.1 ★ 样本均值与样本方差

样本均值：

$$
\bar X=\frac{1}{n}\sum_{i=1}^{n}X_i
$$

样本方差：

$$
s^2=\frac{1}{n-1}\sum_{i=1}^{n}(X_i-\bar X)^2
$$

除以 $n-1$ 是为了得到无偏估计。若除以 $n$，得到的是有偏估计。

### 7.2 ★ 偏差、方差与均方误差

偏差：

$$
\operatorname{Bias}(\hat\theta)=E[\hat\theta]-\theta
$$

均方误差：

$$
\operatorname{MSE}(\hat\theta)=
\operatorname{Bias}(\hat\theta)^2+\operatorname{Var}(\hat\theta)
$$

面试常问：偏差-方差权衡。模型太简单偏差大（欠拟合），模型太复杂方差大（过拟合）。

### 7.3 ★ 最大似然估计

给定独立同分布样本 $x_1,\dots,x_n$，似然函数：

$$
L(\theta)=\prod_{i=1}^{n}p(x_i\mid\theta)
$$

对数似然：

$$
\ell(\theta)=\sum_{i=1}^{n}\log p(x_i\mid\theta)
$$

最大似然估计：

$$
\hat\theta_{\text{MLE}}=\arg\max_\theta\ell(\theta)
$$

常见例子：伯努利分布的 MLE 是样本中正例比例；正态分布均值的 MLE 是样本均值。

### 7.4 ★ MAP 与正则化

最大后验：

$$
\hat\theta_{\text{MAP}}=\arg\max_\theta[\log p(x\mid\theta)+\log p(\theta)]
$$

- 加高斯先验等价于 L2 正则；
- 加拉普拉斯先验等价于 L1 正则；
- MLE 可以看作先验为均匀分布时的 MAP。

### 7.5 ★ 假设检验

- 原假设 $H_0$，备择假设 $H_1$；
- $p$ 值：在 $H_0$ 成立时，出现当前或更极端结果的概率；
- $p$ 值不是“$H_0$ 为真的概率”；
- 第一类错误：$H_0$ 为真却拒绝（假阳性）；
- 第二类错误：$H_0$ 为假却没拒绝（假阴性）；
- 置信区间 95% 的含义是：重复抽样构造区间，长期约 95% 的区间包含真实参数。

### 7.6 ★ 分类评价指标

混淆矩阵：

|  | 预测正 | 预测负 |
|---|---|---|
| 实际正 | TP | FN |
| 实际负 | FP | TN |

精确率：

$$
\text{Precision}=\frac{TP}{TP+FP}
$$

召回率：

$$
\text{Recall}=\frac{TP}{TP+FN}
$$

F1：

$$
F1=\frac{2\cdot\text{Precision}\cdot\text{Recall}}
{\text{Precision}+\text{Recall}}
$$

AUC 衡量排序能力，对类别不平衡比准确率更稳健。

---

## 第 8 章 信息论与损失函数

信息论部分抓住熵、交叉熵、KL 三个量及其关系即可。

### 8.1 ★ 熵

离散随机变量 $X$ 的熵：

$$
H(X)=-\sum_x p(x)\log p(x)
$$

熵衡量不确定性；分布越均匀，熵越大。

### 8.2 ★ 交叉熵

真实分布 $p$，预测分布 $q$：

$$
H(p,q)=-\sum_x p(x)\log q(x)
$$

分类任务中，真实标签是 one-hot，交叉熵等价于正确类别的负对数似然：

$$
L=-\log q(y)
$$

### 8.3 ★ KL 散度

$$
D_{\text{KL}}(p\Vert q)=\sum_x p(x)\log\frac{p(x)}{q(x)}
$$

性质：

$$
D_{\text{KL}}(p\Vert q)\ge0
$$

且一般不对称：

$$
D_{\text{KL}}(p\Vert q)\neq D_{\text{KL}}(q\Vert p)
$$

交叉熵、熵、KL 的关系：

$$
H(p,q)=H(p)+D_{\text{KL}}(p\Vert q)
$$

因为 $H(p)$ 与模型参数无关，最小化交叉熵等价于最小化 KL 散度。

### 8.4 ★ Softmax 与交叉熵

$$
\operatorname{softmax}(z_i)=\frac{e^{z_i}}{\sum_j e^{z_j}}
$$

softmax 把 logits 变成概率分布。多分类交叉熵：

$$
L=-\sum_{i=1}^{K}y_i\log\hat y_i
$$

其中 $y$ 是 one-hot 标签，$\hat y$ 是 softmax 输出。

### 8.5 互信息

$$
I(X;Y)=H(X)-H(X\mid Y)
$$

互信息衡量知道 $Y$ 之后对 $X$ 的不确定性减少了多少，对称且非负。

---

## 第 9 章 AI 岗高频题型速查

这一章把常见问法和最容易失分的点集中成一张检查表。

### 9.1 线代计算题

常见问法：

- 给两个矩阵，问乘积形状或计算结果；
- 判断矩阵是否可逆、秩是多少；
- 求特征值/特征向量；
- 判断矩阵是否半正定；
- 解释 SVD 和 PCA 的关系；
- 计算余弦相似度、$L_1/L_2$ 范数；
- 判断矩阵乘法/转置/逆的运算顺序。

快速检查：

1. 先看维度是否可乘；
2. 方阵才谈逆和行列式；
3. 对称矩阵才能直接正交对角化；
4. 协方差矩阵一定对称半正定；
5. PCA 前先中心化，通常还要标准化。

### 9.2 概率计算题

常见问法：

- 条件概率、全概率、贝叶斯；
- 期望、方差、协方差；
- 独立与互斥判断；
- 二项/泊松/正态/指数分布；
- 中心极限定理近似；
- 最大似然估计；
- 概率分布变换。

快速检查：

1. 事件是否独立？互斥不要当独立；
2. 方差相加前先看协方差是否为 0；
3. 条件概率方向不要写反：$P(A\mid B)\neq P(B\mid A)$；
4. 期望线性性永远成立，方差没有无条件可加性；
5. 贝叶斯题先写先验、似然、后验。

### 9.3 信息论与损失函数

常见问法：

- 熵、交叉熵、KL 的定义和关系；
- 为什么分类用交叉熵而不是 MSE；
- softmax 配合交叉熵的梯度；
- 最大似然和最小交叉熵为什么等价；
- KL 散度为什么不对称。

### 9.4 优化与矩阵微积分

常见问法：

- 梯度、Hessian、凸函数判断；
- 梯度下降更新公式；
- 学习率过大/过小会怎样；
- 链式法则和反向传播；
- 常见矩阵求导结果。

### 9.5 最容易失分的 8 个点

1. 矩阵乘法维度写错；
2. 把“互斥”当成“独立”；
3. 方差无条件相加；
4. 条件概率方向写反；
5. 忘记 $n-1$ 的无偏样本方差；
6. 把 PCA 说成“找方差最小方向”；
7. 把 KL 散度当成对称距离；
8. $p$ 值解释成“原假设为真的概率”。

---

## 第 10 章 考前 30 分钟速记

下面是可以贴在书桌前的最后一页速记。

### 10.1 线代

$$
(AB)^T=B^TA^T
$$

$$
(AB)^{-1}=B^{-1}A^{-1}
$$

$$
\operatorname{tr}(AB)=\operatorname{tr}(BA)
$$

$$
\det(AB)=\det(A)\det(B)
$$

$$
A\mathbf{z}=\lambda\mathbf{z}
$$

$$
A=U\Sigma V^T
$$

$$
A\approx U_k\Sigma_k V_k^T
$$

### 10.2 矩阵求导

$$
\frac{\partial(\mathbf{a}^T\mathbf{x})}{\partial\mathbf{x}}=\mathbf{a}
$$

$$
\frac{\partial(\mathbf{x}^TA\mathbf{x})}{\partial\mathbf{x}}=(A+A^T)\mathbf{x}
$$

$$
\frac{\partial\lVert\mathbf{x}\rVert_2^2}{\partial\mathbf{x}}=2\mathbf{x}
$$

$$
\frac{\partial\operatorname{tr}(AB)}{\partial A}=B^T
$$

### 10.3 概率

$$
P(A\mid B)=\frac{P(A\cap B)}{P(B)}
$$

$$
P(A\mid B)=\frac{P(B\mid A)P(A)}{P(B)}
$$

$$
P(B)=\sum_i P(B\mid A_i)P(A_i)
$$

$$
E[aX+bY]=aE[X]+bE[Y]
$$

$$
\operatorname{Var}(X)=E[X^2]-(E[X])^2
$$

$$
\operatorname{Cov}(X,Y)=E[XY]-E[X]E[Y]
$$

### 10.4 统计与信息论

$$
\bar X=\frac{1}{n}\sum_i X_i
$$

$$
s^2=\frac{1}{n-1}\sum_i(X_i-\bar X)^2
$$

$$
H(p,q)=-\sum_i p_i\log q_i
$$

$$
D_{\text{KL}}(p\Vert q)=\sum_i p_i\log\frac{p_i}{q_i}
$$

$$
H(p,q)=H(p)+D_{\text{KL}}(p\Vert q)
$$

### 10.5 最后一句话

线代抓“**形状、秩、特征值/SVD、矩阵求导**”；概率抓“**条件概率、期望方差、分布、MLE、交叉熵**”。其他细节都可以从这两条主线挂上去。

---

### 延伸参考

- Stanford CS229 VIP Cheatsheet 中文版：[线性代数与微积分](https://stanford.edu/~shervine/l/zh/teaching/cs-229/refresher-algebra-calculus)、[概率与统计](https://stanford.edu/~shervine/l/zh/teaching/cs-229/refresher-probabilities-statistics)
- [Mathematics for Machine Learning](https://mml-book.github.io/)
- [The Matrix Cookbook](https://www.math.uwaterloo.ca/~hwolkowi/matrixcookbook.pdf)
- [The Matrix Calculus You Need For Deep Learning](https://explained.ai/matrix-calculus/)
