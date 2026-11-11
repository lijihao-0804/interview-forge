# ACM 输入输出专题：Java + Python

> 面向机考、笔试和在线判题（OJ）的基础专题。  
> 目标不是背模板，而是看到题目后 30 秒内判断：**单组还是多组、按 Token 还是按行、普通输入还是大数据输入**，然后写出能直接提交的 `public class Main` 或 Python 脚本。  
> 阅读建议：第一次从第 1 章顺序读；刷题时直接查第 3、5、6、7 章的模板；考前只看第 10 章速查表。

## 目录

- [1. 先分清：LeetCode 核心代码 vs ACM 机考](#1-先分清leetcode-核心代码-vs-acm-机考)
- [2. 看到题目先判断输入模型](#2-看到题目先判断输入模型)
- [3. Java 基础输入：Scanner 入门](#3-java-基础输入scanner-入门)
- [4. Java 行输入：BufferedReader 与 StringTokenizer](#4-java-行输入bufferedreader-与-stringtokenizer)
- [5. Java 大数据输入：快速输入模板](#5-java-大数据输入快速输入模板)
- [6. Java 输出：一次只错在输出格式上](#6-java-输出一次只错在输出格式上)
- [7. Python 基础输入：input 与 sys.stdin](#7-python-基础输入input-与-sysstdin)
- [8. Python 快速输入与按行输入](#8-python-快速输入与按行输入)
- [9. Python 输出与多组数据](#9-python-输出与多组数据)
- [10. 八种高频输入模型实战](#10-八种高频输入模型实战)
- [11. 常见坑与检查清单](#11-常见坑与检查清单)
- [12. 一页速查表](#12-一页速查表)

---

## 1. 先分清：LeetCode 核心代码 vs ACM 机考

LeetCode 通常只让你实现一个 `Solution` 方法，输入由评测系统通过参数传入：

```java
class Solution {
    public int[] twoSum(int[] nums, int target) {
        // LeetCode 风格：不自己读输入
        return new int[]{0, 1};
    }
}
```

ACM 机考则要求程序自己从标准输入读数据，向标准输出写答案：

```java
import java.util.*;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        System.out.println(n);
    }
}
```

**输入示例**

```text
5
```

**输出示例**

```text
5
```

两种模式不要混：

- 机考默认使用 **`public class Main`**，除非平台明确要求其他类名；
- 不要写 `package`；
- 不要输出“请输入 n:”之类的提示语；
- 不要从文件读数据，除非题目明确要求；
- 所有输入从 `System.in` / `sys.stdin` 读，输出到 `System.out` / `sys.stdout`。

---

## 2. 看到题目先判断输入模型

| 输入特征 | 推荐写法 | 不适合的写法 |
|---|---|---|
| 单个整数、两三个整数 | Java `Scanner` / Python `input().split()` | 一上来写快速输入模板 |
| 单组 n，第二行 n 个整数 | `Scanner` 循环或 `split()` | 假设数组一定跨多行 |
| T 组数据 | 外层循环 `for (int tc = 0; tc < T; tc++)` | 只处理第一组 |
| 读到 EOF 结束 | Java `sc.hasNext()` / `br.readLine() != null`；Python `for line in sys.stdin` | 假定一定有 T |
| 一行一个含空格字符串 | Java `sc.nextLine()` / `br.readLine()`；Python `sys.stdin.readline().strip()` | Java 用 `sc.next()` 把空格截断 |
| 按行给出的数组 | `BufferedReader.readLine()` 后 `split` / `StringTokenizer` | 只按 Token 读，破坏行语义 |
| 几十万到上百万个整数 | Java 快速输入 / Python `sys.stdin.buffer.read().split()` | Java `Scanner` 可能超时 |
| 二维矩阵 | 先读行列，再双重循环；每行可以按 Token 读，除非题面要求整行 | 把矩阵默认成“所有数都在一行” |

**判断原则：题目输入格式 > 数据规模 > 代码统一性。**

---

## 3. Java 基础输入：Scanner 入门

### 3.1 最简单的 A+B

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int a = sc.nextInt();
        int b = sc.nextInt();
        System.out.println(a + b);
    }
}
```

输入：

```text
3 5
```

输出：

```text
8
```

### 3.2 读 n 个整数

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();

        int[] a = new int[n];
        for (int i = 0; i < n; i++) {
            a[i] = sc.nextInt();
        }

        long sum = 0;
        for (int x : a) sum += x;
        System.out.println(sum);
    }
}
```

**输入示例**

```text
5
1 2 3 4 5
```

**输出示例**

```text
15
```

### 3.3 读字符串、long 和 double

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        String name = sc.next();       // 只读到空格/换行前
        long id = sc.nextLong();       // 超过 int 用 nextLong
        double score = sc.nextDouble();// 小数
        System.out.println(name + " " + id + " " + String.format("%.2f", score));
    }
}
```

**输入示例**

```text
Alice 123 95.5
```

**输出示例**

```text
Alice 123 95.50
```

### 3.4 T 组数据

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int t = sc.nextInt();

        StringBuilder out = new StringBuilder();
        for (int tc = 0; tc < t; tc++) {
            int n = sc.nextInt();
            long sum = 0;
            for (int i = 0; i < n; i++) sum += sc.nextInt();
            out.append(sum).append('\n');
        }
        System.out.print(out);
    }
}
```

> 多组数据优先用 `StringBuilder` 收集输出，最后一次性输出，减少频繁 `System.out.println` 的 IO 次数。

**输入示例**

```text
2
3
1 2 3
2
4 5
```

**输出示例**

```text
6
9
```

### 3.5 EOF 多组输入

有些题没有 T，读到文件结束为止：

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        StringBuilder out = new StringBuilder();

        while (sc.hasNextInt()) {
            int a = sc.nextInt();
            int b = sc.nextInt();
            out.append(a + b).append('\n');
        }

        System.out.print(out);
    }
}
```

**输入示例**

```text
1 2
3 4
```

**输出示例**

```text
3
7
```

### 3.6 nextInt 和 nextLine 混用

`nextInt()` 只读走整数，不消费整数后面的换行符。紧接着 `nextLine()` 会读到空字符串。

```java
Scanner sc = new Scanner(System.in);
int n = sc.nextInt();
sc.nextLine(); // 必须消费掉 n 后面的换行
String line = sc.nextLine();
```

如果输入是“先读整数，再读一整行字符串”，正确写法：

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        sc.nextLine();                  // 消费行尾
        String s = sc.nextLine();       // 读完整一行，保留空格

        System.out.println(n);
        System.out.println(s);
    }
}
```

**输入示例**

```text
2
hello world
```

**输出示例**

```text
2
hello world
```

### 3.7 Scanner 什么时候不要用

Scanner 代码短、好记，但底层解析较慢。以下情况优先使用第 4、5 章的 `BufferedReader`：

- 几十万到上百万个整数；
- 大量多组数据；
- 输入字符串总长度达到几十万；
- 时间限制很紧，Scanner 已经超时。

---

## 4. Java 行输入：BufferedReader 与 StringTokenizer

### 4.1 按行读一整行文本

```java
import java.io.*;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        String line = br.readLine();

        // 原样保留行内空格
        System.out.println(line);
    }
}
```

**输入示例**

```text
hello world
```

**输出示例**

```text
hello world
```

### 4.2 一行多个整数

```java
import java.io.*;
import java.util.*;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));

        int n = Integer.parseInt(br.readLine().trim());
        StringTokenizer st = new StringTokenizer(br.readLine());

        long sum = 0;
        for (int i = 0; i < n; i++) {
            sum += Long.parseLong(st.nextToken());
        }

        System.out.println(sum);
    }
}
```

**输入示例**

```text
3
1 2 3
```

**输出示例**

```text
6
```

### 4.3 数组跨多行也要安全处理

不要假设“n 个整数一定在同一行”。如果题目只保证数字由空白分隔，应该连续读到 n 个：

```java
import java.io.*;
import java.util.*;

public class Main {
    static BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
    static StringTokenizer st;

    static String next() throws IOException {
        while (st == null || !st.hasMoreTokens()) {
            String line = br.readLine();
            if (line == null) return null;
            st = new StringTokenizer(line);
        }
        return st.nextToken();
    }

    public static void main(String[] args) throws IOException {
        int n = Integer.parseInt(next());
        long[] a = new long[n];
        for (int i = 0; i < n; i++) {
            a[i] = Long.parseLong(next());
        }

        long sum = 0;
        for (long x : a) sum += x;
        System.out.println(sum);
    }
}
```

**输入示例**

```text
5
1 2
3 4
5
```

**输出示例**

```text
15
```

### 4.4 每行格式固定：逐行解析

如果每行有固定数量字段，按行读比 Token 流更清楚：

```java
import java.io.*;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));

        int m = Integer.parseInt(br.readLine().trim());
        for (int i = 0; i < m; i++) {
            String[] parts = br.readLine().trim().split("\\s+");
            int u = Integer.parseInt(parts[0]);
            int v = Integer.parseInt(parts[1]);
            int w = Integer.parseInt(parts[2]);
            System.out.println(u + v + w);
        }
    }
}
```

`split("\\s+")` 能处理连续多个空格；如果题目保证单空格，`split(" ")` 也可以，但鲁棒性差一些。

**输入示例**

```text
2
1 2 3
4 5 6
```

**输出示例**

```text
6
15
```

### 4.5 空行与 EOF

```java
String line;
while ((line = br.readLine()) != null) {
    line = line.trim();
    if (line.isEmpty()) continue; // 跳过空行
    // 处理这一行
}
```

---

**输入示例**

```text
1 2

3 4
```

**输出示例**

```text
处理 1 2
处理 3 4
```

## 5. Java 大数据输入：快速输入模板

只有数据量明显很大时，才使用这一套模板。它的优势是**连续读 Token、避免 Scanner 的解析开销**。

```java
import java.io.*;
import java.util.*;

public class Main {
    static BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
    static StringTokenizer st;

    static String next() throws IOException {
        while (st == null || !st.hasMoreTokens()) {
            String line = br.readLine();
            if (line == null) return null;
            st = new StringTokenizer(line);
        }
        return st.nextToken();
    }

    static int nextInt() throws IOException {
        return Integer.parseInt(next());
    }

    static long nextLong() throws IOException {
        return Long.parseLong(next());
    }

    public static void main(String[] args) throws IOException {
        int n = nextInt();
        long sum = 0;
        for (int i = 0; i < n; i++) {
            sum += nextInt();
        }
        System.out.println(sum);
    }
}
```

**输入示例**

```text
5
1 2 3 4 5
```

**输出示例**

```text
15
```

### 5.1 什么时候保留快速输入

- 整数个数可能达到 `10^5`、`10^6`；
- 多组数据且总 Token 数巨大；
- 全局 `Scanner` 出现超时；
- 输入是连续数字流，不依赖行边界。

### 5.2 什么时候不要用

- 只有几行、几十个数字；
- 需要读整行含空格字符串；
- 题目强调按行解析；
- 团队/面试官更看重可读性，Scanner 足够。

### 5.3 极大数据量

极端情况下可以使用自定义字节缓冲输入，但那是最后的性能手段，不适合作为默认模板。机考复习优先掌握：

1. `Scanner`；
2. `BufferedReader.readLine()`；
3. `BufferedReader + StringTokenizer`。

---

## 6. Java 输出：一次只错在输出格式上

### 6.1 print / println / printf

```java
System.out.print("a");
System.out.println("b");              // 自动换行
System.out.printf("%.2f%n", 3.14159); // 保留两位小数
```

**输入示例**

```text
无输入
```

**输出示例**

```text
ab
3.14
```

### 6.2 StringBuilder 收集多行输出

```java
StringBuilder out = new StringBuilder();
for (int i = 0; i < n; i++) {
    out.append(answer[i]);
    if (i + 1 < n) out.append('\n');
}
System.out.print(out);
```

不要在循环里大量使用 `System.out.println` 输出十万行，容易成为性能瓶颈。

**输入示例**

```text
无输入（片段）
```

**输出示例**

```text
逐行输出 answer 数组
```

### 6.3 数字格式

```java
System.out.printf("%d%n", 1000000000000L); // long
System.out.printf("%.3f%n", 1.0 / 3);       // 三位小数
System.out.printf("%.6f%n", Math.sqrt(2));  // 六位小数
```

如果题目要求“保留两位小数”，注意：

- 用 `printf("%.2f")`；
- 不要手工 `Math.round` 后再拼接；
- 浮点误差和负零按题目/SPJ 要求处理。

---

**输入示例**

```text
无输入
```

**输出示例**

```text
1000000000000
0.333
1.414214
```

## 7. Python 基础输入：input 与 sys.stdin

### 7.1 一个整数

```python
n = int(input())
print(n)
```

**输入示例**

```text
5
```

**输出示例**

```text
5
```

### 7.2 一行两个整数

```python
a, b = map(int, input().split())
print(a + b)
```

**输入示例**

```text
3 5
```

**输出示例**

```text
8
```

### 7.3 一行 n 个整数

```python
n = int(input())
a = list(map(int, input().split()))

# 如果担心数组可能跨行，使用后面 8.2 的写法
print(sum(a))
```

**输入示例**

```text
5
1 2 3 4 5
```

**输出示例**

```text
15
```

### 7.4 多组数据 T

```python
t = int(input())
out = []
for _ in range(t):
    n = int(input())
    a = list(map(int, input().split()))
    out.append(str(sum(a)))
print("\n".join(out))
```

**输入示例**

```text
2
3
1 2 3
2
4 5
```

**输出示例**

```text
6
9
```

### 7.5 含空格的整行字符串

```python
s = input().rstrip("\n")
print(len(s), s)
```

`input()` 本身会去掉行尾换行；用 `sys.stdin.readline().strip("\n")` 时也要注意不要误删行首/行尾有意义的空格。

**输入示例**

```text
2
hello world
foo bar
```

**输出示例**

```text
11 hello world
7 foo bar
```

### 7.6 EOF 多组

```python
import sys

out = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    a, b = map(int, line.split())
    out.append(str(a + b))

sys.stdout.write("\n".join(out))
```

---

**输入示例**

```text
1 2
3 4
```

**输出示例**

```text
3
7
```

## 8. Python 快速输入与按行输入

### 8.1 大数据：一次读入所有 Token

```python
import sys

data = sys.stdin.buffer.read().split()
it = iter(data)

n = int(next(it))
a = [int(next(it)) for _ in range(n)]
print(sum(a))
```

这是 Python 机考最常用的快速输入方式：

- `read()` 一次读入；
- `split()` 按任意空白切 Token；
- `next(it)` 依次取 Token；
- 适合 `10^5` 到 `10^6` 级整数输入。

**输入示例**

```text
3
1 2 3
```

**输出示例**

```text
6
```

### 8.2 数组可能跨行

```python
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
n = data[0]
a = data[1:1 + n]
print(sum(a))
```

它不依赖“数组都在一行”，只要题目保证所有数字由空白分隔即可。

**输入示例**

```text
3
1 2
3
```

**输出示例**

```text
6
```

### 8.3 按行读

```python
import sys

input = sys.stdin.readline

n = int(input())
s = input().strip()      # 完整一行，保留空格用 rstrip("\n")
print(n, s)
```

**输入示例**

```text
2
hello world
```

**输出示例**

```text
2 hello world
```

### 8.4 固定格式多行

```python
import sys

input = sys.stdin.readline
m = int(input())

for _ in range(m):
    u, v, w = map(int, input().split())
    print(u + v + w)
```

**输入示例**

```text
2
1 2 3
4 5 6
```

**输出示例**

```text
6
15
```

### 8.5 空行与 EOF

```python
import sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    # 处理
```

---

**输入示例**

```text
1 2

3 4
```

**输出示例**

```text
处理 1 2
处理 3 4
```

## 9. Python 输出与多组数据

### 9.1 print 与 join

```python
print(a, b)                    # 空格分隔
print(a, b, sep=",")           # 自定义分隔
print("\n".join(map(str, ans))) # 一次输出多行
```

**输入示例**

```text
3 5
```

**输出示例**

```text
3 5
```

### 9.2 保留小数

```python
print(f"{x:.2f}")
print(f"{x:.6f}")
print(format(x, ".3f"))
```

**输入示例**

```text
无输入（x=3.14159）
```

**输出示例**

```text
3.14
```

### 9.3 大量输出

```python
import sys

out = []
for x in ans:
    out.append(str(x))
sys.stdout.write("\n".join(out))
```

不要在十万级循环中频繁 `print`，可以先收集再一次性输出。

---

**输入示例**

```text
无输入（ans=[1,2,3]）
```

**输出示例**

```text
1
2
3
```

## 10. 八种高频输入模型实战

### 10.1 模型一：单组 A+B

**Java**

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        System.out.println(sc.nextInt() + sc.nextInt());
    }
}
```

**Python**

```python
a, b = map(int, input().split())
print(a + b)
```

**输入示例**

```text
3 5
```

**输出示例**

```text
8
```

### 10.2 模型二：T 组 A+B

**Java**

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int t = sc.nextInt();
        StringBuilder out = new StringBuilder();
        while (t-- > 0) {
            out.append(sc.nextInt() + sc.nextInt()).append('\n');
        }
        System.out.print(out);
    }
}
```

**Python**

```python
t = int(input())
for _ in range(t):
    a, b = map(int, input().split())
    print(a + b)
```

**输入示例**

```text
2
1 2
3 5
```

**输出示例**

```text
3
8
```

### 10.3 模型三：第一行 n，第二行 n 个整数

**Java（数组可能跨行）**

```java
import java.io.*;
import java.util.*;

public class Main {
    static BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
    static StringTokenizer st;

    static String next() throws IOException {
        while (st == null || !st.hasMoreTokens()) {
            String line = br.readLine();
            if (line == null) return null;
            st = new StringTokenizer(line);
        }
        return st.nextToken();
    }

    public static void main(String[] args) throws IOException {
        int n = Integer.parseInt(next());
        long sum = 0;
        for (int i = 0; i < n; i++) sum += Long.parseLong(next());
        System.out.println(sum);
    }
}
```

**Python**

```python
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
n = data[0]
print(sum(data[1:1 + n]))
```

**输入示例**

```text
3
1 2 3
```

**输出示例**

```text
6
```

### 10.4 模型四：n × m 矩阵

**Java**

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        int m = sc.nextInt();
        int[][] a = new int[n][m];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < m; j++) {
                a[i][j] = sc.nextInt();
            }
        }
    }
}
```

**Python**

```python
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
it = iter(data)
n = next(it)
m = next(it)
a = [[next(it) for _ in range(m)] for _ in range(n)]
```

**输入示例**

```text
2 3
1 2 3
4 5 6
```

**输出示例**

```text
无输出（读入完成）
```

### 10.5 模型五：一行一个含空格字符串

**Java**

```java
import java.io.*;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        int n = Integer.parseInt(br.readLine().trim());
        for (int i = 0; i < n; i++) {
            String s = br.readLine(); // 保留空格
            System.out.println(s.length());
        }
    }
}
```

**Python**

```python
import sys

input = sys.stdin.readline
n = int(input())
for _ in range(n):
    s = input().rstrip("\n")  # 保留行内空格
    print(len(s))
```

**输入示例**

```text
2
hello world
foo
```

**输出示例**

```text
11
3
```

### 10.6 模型六：EOF 多组

**Java**

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        StringBuilder out = new StringBuilder();
        while (sc.hasNextInt()) {
            long a = sc.nextLong();
            long b = sc.nextLong();
            out.append(a + b).append('\n');
        }
        System.out.print(out);
    }
}
```

**Python**

```python
import sys

out = []
for line in sys.stdin:
    if line.strip():
        a, b = map(int, line.split())
        out.append(str(a + b))
print("\n".join(out))
```

**输入示例**

```text
1 2
3 4
```

**输出示例**

```text
3
7
```

### 10.7 模型七：每行长度不固定

例如第一行 n，接下来 n 行每行若干个整数，处理每行：

**Java**

```java
import java.io.*;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        int n = Integer.parseInt(br.readLine().trim());

        for (int i = 0; i < n; i++) {
            String[] parts = br.readLine().trim().split("\\s+");
            long sum = 0;
            for (String p : parts) sum += Long.parseLong(p);
            System.out.println(sum);
        }
    }
}
```

**Python**

```python
import sys

input = sys.stdin.readline
n = int(input())
for _ in range(n):
    a = list(map(int, input().split()))
    print(sum(a))
```

**输入示例**

```text
2
1 2 3
4 5
```

**输出示例**

```text
6
9
```

### 10.8 模型八：大数据 + 多组

**Java** 使用第 5 章快速输入模板；**Python** 使用：

```python
import sys

data = sys.stdin.buffer.read().split()
it = iter(data)
t = int(next(it))
out = []
for _ in range(t):
    n = int(next(it))
    s = 0
    for _ in range(n):
        s += int(next(it))
    out.append(str(s))
sys.stdout.write("\n".join(out))
```

---

**输入示例**

```text
2
3
1 2 3
2
4 5
```

**输出示例**

```text
6
9
```

## 11. 常见坑与检查清单

### 11.1 输入坑

- **Java `nextInt()` 后直接 `nextLine()`**：会读到空行，先补一次 `nextLine()`。
- **把含空格字符串写成 `sc.next()`**：只读到第一个空格前。
- **假设数组必在一行**：除非题面明确，否则用 Token 流连续读 n 个。
- **`split(" ")` 遇到多个空格产生空串**：用 `split("\\s+")` 或 `StringTokenizer`。
- **`readLine()` 返回 null**：EOF 要处理，不能直接 `Integer.parseInt(null)`。
- **空行**：T 组/按行题要先 `trim()` 判断空行。
- **输入有 BOM 或 CRLF**：读第一行时注意 `\uFEFF`/`\r`，必要时 `strip`。

### 11.2 数据类型坑

- `int` 约 21 亿，累加/乘法可能溢出，改用 `long`；
- 题目范围到 `10^18` 时必须 `long` / Python `int`；
- 小数比较不要直接用 `==`，按题目要求处理误差；
- 输出 `-0.00` 时按题面/SPJ 要求处理。

### 11.3 输出坑

- 多组数据最后一行是否要换行，按题目要求；
- 一行多个答案用空格还是换行；
- 保留小数位数、前导零、`YES/NO` 大小写；
- 不要输出调试信息；
- 大量输出用 `StringBuilder` / `join`。

### 11.4 提交前检查

- [ ] 类名是否为 `Main`（Java）
- [ ] 有没有 `package`
- [ ] 有没有从文件读
- [ ] 有没有输出提示语
- [ ] 是否处理 T 组 / EOF
- [ ] 数组是否可能跨行
- [ ] 是否用了 `long`
- [ ] 输出格式/小数位是否正确
- [ ] 大数据是否使用了合适的输入方式

---

## 12. 一页速查表

### 12.1 Java 输入选择

| 场景 | 写法 |
|---|---|
| 少量整数 | `Scanner sc = new Scanner(System.in); sc.nextInt()` |
| 读整行 | `BufferedReader br = new BufferedReader(new InputStreamReader(System.in)); br.readLine()` |
| 一行多个数 | `new StringTokenizer(line)` + `nextToken()` |
| 大数据 Token | 第 5 章 `BufferedReader + StringTokenizer` 模板 |
| EOF | `while (sc.hasNext())` / `while ((line = br.readLine()) != null)` |

### 12.2 Python 输入选择

| 场景 | 写法 |
|---|---|
| 一行两个数 | `a, b = map(int, input().split())` |
| 一行数组 | `list(map(int, input().split()))` |
| 大数据 | `sys.stdin.buffer.read().split()` + 迭代器 |
| 整行字符串 | `sys.stdin.readline().rstrip("\n")` |
| EOF | `for line in sys.stdin:` |

### 12.3 最小心智模型

```text
先看输入格式，再看数据规模：
  小数据、单组/少量多组 -> Scanner / input
  按行、含空格、整行字符串 -> BufferedReader / readline
  大数据、连续 Token -> 快速输入模板 / buffer.read().split()
```

记住：**正确性优先，其次是符合题面输入格式，最后才是性能模板。**
