# ACM 输入输出专题：Java + Python

> 面向机考、笔试和在线判题（OJ）的基础专题。  
> 目标不是背模板，而是看到题目后 30 秒内判断：**单组还是多组、按 Token 还是按行、普通输入还是大数据输入**，然后写出能直接提交的 `public class Main` 或 Python 脚本。  
> 阅读建议：第一次从第 1 章顺序读；刷题时直接查第 3、5、6、7 章的模板；综合练习看第 10 章，考前查第 12 章速查表。

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

在力扣里，你通常只实现 `Solution` 的一个方法，评测器负责把数组、字符串等参数传进来。到了 ACM 模式，这一步也要自己做：程序从标准输入拿到文本，把它还原成数据，再按题目规定打印答案。

```text
力扣核心代码：评测器准备参数 → 调用你的方法 → 检查返回值
ACM 完整程序：标准输入文本 → 你解析数据 → 你处理问题 → 标准输出文本
```

Java 的入口通常是 `public class Main` 中的 `main` 方法；Python 直接执行脚本里的语句，小程序不必额外封装一个 `Solution`。本专题默认使用标准输入输出，不写 `package`，不从本地文件读取，也不打印“请输入数字”之类的提示语。

下面是一份完整的 Java ACM 程序。协议只给一个在 `int` 范围内的整数，要求原样输出；保存为 `Main.java` 后即可编译运行。

```java
import java.util.Scanner;

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

Python 的同类完整入口见[第 7 章](../../library/acm-io/chapter-07.html)，两种语言一起练见[第 10 章](../../library/acm-io/chapter-10.html)。之后遇到输入错误时，先检查“文本是怎样组织的”，不要急着怀疑算法。

---

## 2. 看到题目先判断输入模型

先问三个问题：**数据什么时候结束？换行有没有业务含义？读入规模有多大？** 读取方式必须服从题面协议，不能因为某个模板短就一律套用。

| 题面协议 | Python 选择 | Java 选择 | 为什么这样选 |
|---|---|---|---|
| 一行给两个整数 | `a, b = map(int, input().split())` | `Scanner` 读取两个数 | 简单输入先用最直接的写法 |
| 先给数量，随后若干整数仅以空白分隔 | 小规模可逐行收集；有限且内存允许时整读 token | `Scanner`；大规模用 `BufferedReader + StringTokenizer` | 数量确定，数字跨行不应改变结果 |
| 开头给 `T`，随后有 `T` 组 | 先读 `T`，每轮重新读本组尺寸和数据 | 外层 `for` 循环，每轮重新读本组数据 | `T` 不是数组长度，不能只处理第一组 |
| 没有 `T`，给到 EOF 为止 | 按行记录用 `for line in sys.stdin`；纯整数流也可连续取 token | 按行用 `readLine() != null`；合法 long 流用 `hasNextLong()` 配 `nextLong()` | EOF 是输入源结束，不是一个空字符串记录 |
| 接下来恰好 `n` 行文本，空串也算一行 | `input()`，或 `readline()` 只去换行 | `BufferedReader.readLine()`；也可按协议使用 `nextLine()` | 要保留行边界、空行及前后空格，不能全局 `split()` |
| 每行都是一条长度不定的数字记录 | 每行单独 `split()` | 每行单独建 `StringTokenizer` | 本行有几个数本身就是记录边界 |
| 逗号等特殊分隔符 | 先按指定分隔符切，再转换字段 | 按逗号切分后 `trim()`、转换 | 默认空白分词不会自动去掉逗号 |

例如同样输入 `1 2`、空行、`3 4`：如果它是纯整数流，空行只是空白；如果题面说“一行一条记录”，空行可能是一条空记录，需要输出 `0`。**是否跳过空行由题面决定。**

Python 的 `input()` 遇到一条空行返回 `""`，真正读过 EOF 会抛 `EOFError`；`sys.stdin.readline()` 遇到空行返回 `"\n"`，到 EOF 才返回 `""`。Java `readLine()` 的空行是 `""`，EOF 是 `null`。先分清这些状态，再决定转换或跳过。

规模是第二步：`sys.stdin.read()` 和 `sys.stdin.buffer.read()` 都要等到 EOF，整份输入以及切出的 token 会占内存；交互题需要边读边答时不能整读。Java `Scanner` 足够处理少量数字，不要为一个 A+B 写一屏快速输入封装；大量数字再换成第 4、5 章的连续 token 读取。

矩阵也不例外。题面若保证每行恰好 `cols` 个数，可以按行添加；若只保证总共 `rows * cols` 个数且允许跨行，就要按 token 数量还原。第 8 章讲这两种 Python 构造，第 10 章再做双语言组合练习。

---

## 3. Java 基础输入：Scanner 入门

`Scanner` 的 `nextInt()`、`nextLong()`、`nextDouble()` 读取的是**下一个空白分隔 token**，不要求这个 token 独占一行。因此 A+B 的输入写成一行或拆成两行，通常都能按相同代码读取。

### 3.1 先写一个完整的 A+B

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

**输入（`stdin`）**

```text
3 5
```

**输出（`stdout`，末尾换行）**

```text
8
```

本题约定两个加数都是 `int`，且两数之和也在 `int` 范围内。

题目若写“两个整数由空白分隔”，输入 `3`、换行、`5` 与上面的写法表示同一个 token 协议；不要把“同一行”误解成语言要求。

### 3.2 先读 n，再读 n 个整数

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
        for (int x : a) {
            sum += x;
        }
        System.out.println(sum);
    }
}
```

**输入（`stdin`）**

```text
5
1 2 3 4 5
```

**输出（`stdout`，末尾换行）**

```text
15
```

`n` 是元素个数，不需要在问题意义里额外加一。本题约定每个元素都在 `int` 范围，且每一步中间累加和与最终和都在 `long` 范围，因此数组用 `int`、总和用 `long`。`n = 0` 时数组长度为零、循环不执行，输出 `0`。

### 3.3 字符串、long、double 与一致的 Locale

`next()` 读到下一个空白前；`nextLong()` 用于可能超过 `int` 范围的整数；`nextDouble()` 读取一个小数 token。输入中的小数点规则来自 `Scanner` 的 Locale，输出格式也来自一个 Locale。两边都显式使用 `Locale.ROOT`，就固定为小数点 `.`，不会因为机器默认区域设置而出现输入用 `.`、输出却用逗号的错位。

```java
import java.util.Locale;
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in).useLocale(Locale.ROOT);
        String name = sc.next();
        long id = sc.nextLong();
        double score = sc.nextDouble();

        System.out.printf(Locale.ROOT, "%s %d %.2f%n", name, id, score);
    }
}
```

**输入（`stdin`）**

```text
Alice 9000000000 95.5
```

**输出（`stdout`，末尾换行）**

```text
Alice 9000000000 95.50
```

若这里改用 `sc.nextDouble()` 的默认 Locale，再用另一个默认 Locale 的 `String.format`，输入和输出对小数点的假设可能不一致。若题目明确使用本地化格式，例如逗号作小数分隔符，就应主动选择相应 Locale，而不是把 `.` 和 `,` 混在一条协议里。

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
            for (int i = 0; i < n; i++) {
                sum += sc.nextInt();
            }
            out.append(sum).append('\n');
        }

        System.out.print(out);
    }
}
```

**输入（`stdin`）**

```text
2
3
1 2 3
2
4 5
```

**输出（`stdout`，末尾换行）**

```text
6
9
```

本题约定每组元素都是 `int`，且该组每一步中间累加和与最终答案都在 `long` 范围。外层循环控制数据组数，内层循环只读当前组声明的 `n` 个数。`t = 0` 是有效的边界情况，此时没有答案行，最终 `stdout` 为空串。

### 3.5 EOF、空行与 `hasNextLong()`

没有 T、要读到文件结束时，可以让 `hasNextLong()` 先检查下一个整数 token 是否真的存在。它本身不消费 token；检查为真后再调用 `nextLong()`。本题约定输入由完整偶数个 `long` 组成，每两个数成对，且每次加法结果都在 `long` 范围。空行只是空白，`Scanner` 会继续越过它寻找后续整数；EOF 表示已经没有字符，二者不是一回事。

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        StringBuilder out = new StringBuilder();

        while (sc.hasNextLong()) {
            long a = sc.nextLong();
            long b = sc.nextLong();
            out.append(a + b).append('\n');
        }

        System.out.print(out);
    }
}
```

**输入（`stdin`）**

```text
1 2
3 4
```

**输出（`stdout`，末尾换行）**

```text
3
7
```

因为题面保证 token 成对，读到第一个数后可以直接读第二个数，不再用第二个 `hasNextLong()` 判断并把落单数无声丢掉。对 `1 2`、若干空行、`3 4` 的输入，循环仍会读到两对数据。若输入只有空行后在 EOF 结束，`hasNextLong()` 最终返回 `false`，没有输出。若要按行处理，则 `hasNextLine()` 面对空行会返回 `true`，随后的 `nextLine()` 返回空字符串；它不会把空行误判成 EOF。

### 3.6 `nextInt()` 后接 `nextLine()`：两种协议

`nextInt()` 读到整数后停在整数末尾。随后第一次 `nextLine()` 读取的是**当前行剩余部分**，不一定是空串：

- 整数独占一行，例如 `7\nhello\n`：剩余部分是空串，下一次 `nextLine()` 才得到 `hello`；
- 整数和文本在同一行，例如 `7 hello\n`：第一次 `nextLine()` 已经得到 ` hello`。

所以不能一律再补一次 `nextLine()`。先按题面判断文本从当前行余部开始，还是从下一行开始。

#### 协议 A：整数和文本在同一行

下面的诊断输出用 `|...|` 标出起始位置和行尾，观察到的前导空格是分隔整数与文本的原字符。

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int id = sc.nextInt();
        String remainder = sc.nextLine();

        System.out.println("id=" + id);
        System.out.println("remainder=|" + remainder + "|");
    }
}
```

**输入（`stdin`）**

```text
7 hello world
```

**输出（`stdout`，末尾换行）**

```text
id=7
remainder=| hello world|
```

实际题目若规定“第一项后紧跟一个空格，空格后是正文”，且正文不以空格为内容，可以用 `remainder.stripLeading()` 去掉这个格式分隔空格。这里的诊断程序故意保留它，以看清 `nextLine()` 的真实返回值。

#### 协议 B：整数独占一行，下一条完整文本在下一行

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();

        sc.nextLine();             // 结束当前行；本协议的剩余部分是空串
        String message = sc.nextLine();

        System.out.println(n + ":" + message);
    }
}
```

**输入（`stdin`）**

```text
2
hello world
```

**输出（`stdout`，末尾换行）**

```text
2:hello world
```

这里第一行只有整数，第二行才是完整文本，所以第一次 `nextLine()` 消费空余部，第二次 `nextLine()` 才读正文。若换成协议 A 的 `7 hello world`，照抄这里会丢掉文本，因为第一次 `nextLine()` 已经把 ` hello world` 读走。

---

## 4. Java 行输入：BufferedReader 与 StringTokenizer

`BufferedReader.readLine()` 返回**不含行尾换行符的一行内容**；读到 EOF 时返回 `null`，遇到真正的空行时返回 `""`。这两种情况必须分开处理。

### 4.1 原样读一整行

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        String line = br.readLine();
        if (line != null) {
            System.out.println(line);
        }
    }
}
```

**输入（`stdin`）**

```text
hello world
```

**输出（`stdout`，末尾换行）**

```text
hello world
```

这段程序不调用 `trim()`，因此行首、行尾和中间的空格都保留。空行会得到 `""`，随后 `println` 产生一个换行；只有输入耗尽时 `readLine()` 才返回 `null`，程序用条件判断避免把 `null` 当成文本输出。

### 4.2 明确保证数组就在一行

若题面明确给出“第一行是 n，第二行恰好有 n 个整数”，可以为第二行创建 `StringTokenizer`。这个写法按行取 token；如果题目允许数组跨行或允许额外空行，应改用 4.3 的跨行 token 读取。

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.StringTokenizer;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        int n = Integer.parseInt(br.readLine().trim());
        String values = br.readLine();
        StringTokenizer st = new StringTokenizer(values == null ? "" : values);

        long sum = 0;
        for (int i = 0; i < n; i++) {
            sum += Long.parseLong(st.nextToken());
        }
        System.out.println(sum);
    }
}
```

**输入（`stdin`）**

```text
3
1 2 3
```

**输出（`stdout`，末尾换行）**

```text
6
```

本题约定元素是 `long`，且每一步中间累加和与最终结果都在 `long` 范围。`n = 0` 时没有数组 token，程序不调用 `nextToken()`，输出 `0`。若第二行是空行而 `n > 0`，这个严格的一行协议本身不符合题面；不要靠一次大循环悄悄越过协议错误。

### 4.3 数字可能跨多行

`StringTokenizer` 只能切分创建它的那一个字符串。要连续读取多个由任意空白分隔的 token，可以让辅助方法在当前行没有 token 时继续调用 `readLine()`。

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.StringTokenizer;

public class Main {
    static BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
    static StringTokenizer st;

    static String next() throws IOException {
        while (st == null || !st.hasMoreTokens()) {
            String line = br.readLine();
            if (line == null) {
                return null;
            }
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
        for (long x : a) {
            sum += x;
        }
        System.out.println(sum);
    }
}
```

**输入（`stdin`）**

```text
5
1 2

3 4
5
```

**输出（`stdout`，末尾换行）**

```text
15
```

本题约定每个元素及每一步中间累加和都在 `long` 范围；单个元素放得下，也不代表任意个元素累加都不会溢出。这里跨行读取并跳过空行是合理的，**前提是题目只定义 token 序列**，空行没有字段含义。若每行本身是一条记录，空白行可能代表一条空记录，就不能让 token 辅助方法擅自越过它。

### 4.4 每行都是固定字段

每行一条记录时，直接按行读，比把所有输入混成一个 token 流更能保留行语义。

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        int m = Integer.parseInt(br.readLine().trim());

        for (int i = 0; i < m; i++) {
            String[] parts = br.readLine().trim().split("\\s+");
            long sum = 0;
            for (String part : parts) {
                sum += Long.parseLong(part);
            }
            System.out.println(sum);
        }
    }
}
```

**输入（`stdin`）**

```text
2
1 2 3
4 5 6
```

**输出（`stdout`，末尾换行）**

```text
6
15
```

本题约定每行字段可解析为 `long`，且每行中间累加和与最终结果都在 `long` 范围。题目若保证单空格，用 `split(" ")` 也能切；允许多个空格时，`split("\\s+")` 更符合“空白分隔”的协议。空行在固定记录协议里不是“没有数据”，而是取出字段会失败的异常输入，因此这里不跳过它。

### 4.5 明确允许空行时跳过，并处理 EOF

以下程序对每条非空记录输出“处理 原行”。只有题面明确说“空行是额外排版，不属于记录”时，才执行 `continue`。

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        String line;

        while ((line = br.readLine()) != null) {
            String content = line.trim();
            if (content.isEmpty()) {
                continue;
            }
            System.out.println("处理 " + content);
        }
    }
}
```

**输入（`stdin`）**

```text
1 2

3 4
```

**输出（`stdout`，末尾换行）**

```text
处理 1 2
处理 3 4
```

空行得到 `""`，但循环继续；最终 `readLine()` 返回 `null`，循环结束。这里的 `trim()` 服务于“去掉排版空白”的明确约定；如果行首尾空格属于文本内容，就应只检查并使用 `line.isEmpty()`，不能改写原行。

---

## 5. Java 大数据输入：快速输入模板

第 4 章已经提供可独立运行的 [BufferedReader + StringTokenizer 统一 token 模板](../../library/acm-io/chapter-04.html)，本章说明何时采用它，不再复制同一段 helper。

### 5.1 何时用 Token 模板替换 Scanner

当 token 总数达到 `10^5`、`10^6` 级，多组数据使总 token 数很大，或者已经实测 `Scanner` 在时间限制内超时，才值得改用第 4 章的模板。题目只保证 token 由空白分隔、不要求按行解释时，它可以跨行继续读取。只有几十个 token，或者需要保留整行含空格文本时，继续用 `Scanner` 或 `readLine()` 更容易检查。

### 5.2 使用前提

- 题目保证 token 之间由任意空白分隔，空行本身没有字段含义；
- 需要整行含空格文本时，仍使用 `readLine()`，不要把文本拆成 token；
- 单个值可能超过 `int` 范围时用 `Long.parseLong(next())`，否则用 `Integer.parseInt(next())`；`long` 总和及每一步中间和也必须在 `long` 范围；
- 题目给出明确的 `n` 或 `T` 时按结构读满；只有输入长度未知、确实读到 EOF 才终止，并用 `hasNextLong()`、`readLine() != null` 或等价的 EOF 守卫，不要把 `null` 送进解析方法；
- 极端数据量下仍应先保证正确性；自定义字节级读取是单独的极端优化，不作为默认模板。

---

## 6. Java 输出：一次只错在输出格式上

### 6.1 `print`、`println`、`printf` 的换行差别

`print` 不加换行，`println` 在输出内容后换行，`printf` 按格式串输出。下面的程序读取两个整数，依次演示三种方法。

```java
import java.util.Locale;
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in).useLocale(Locale.ROOT);
        int a = sc.nextInt();
        int b = sc.nextInt();

        System.out.print(a);
        System.out.println("+" + b);
        double average = ((long) a + b) / 2.0;
        System.out.printf(Locale.ROOT, "avg=%.2f%n", average);
    }
}
```

**输入（`stdin`）**

```text
3 4
```

**输出（`stdout`，末尾换行）**

```text
3+4
avg=3.50
```

`print a` 与 `println "+b"` 拼在同一行；`printf` 再有自己的格式和换行。若把 `print` 误写成了 `println`，第一行会提前断开。平均值先把和提升到 `long`，避免这段格式教学代码自己落入整数加法溢出。

### 6.2 用 `StringBuilder` 收集多行输出

十万行输出时，反复调用 `System.out.println` 可能带来明显的输出开销。下面先收集到 `StringBuilder`，再一次性 `print`；每个答案后追加换行，最终有末尾换行。

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        StringBuilder out = new StringBuilder();

        for (int i = 0; i < n; i++) {
            out.append(sc.nextInt()).append('\n');
        }
        System.out.print(out);
    }
}
```

**输入（`stdin`）**

```text
3
1 2 3
```

**输出（`stdout`，末尾换行）**

```text
1
2
3
```

`StringBuilder` 存的是最终字符，不是答案数组。数据本身仍需按题目要求保存时，应另建数组；这里只解决输出累积。

### 6.3 前导零、精度与 `Locale.ROOT`

```java
import java.util.Locale;
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in).useLocale(Locale.ROOT);
        int id = sc.nextInt();
        double value = sc.nextDouble();

        System.out.printf(Locale.ROOT, "%04d %.3f%n", id, value);
    }
}
```

**输入（`stdin`）**

```text
7 0.6666667
```

**输出（`stdout`，末尾换行）**

```text
0007 0.667
```

`%04d` 的 `4` 是最小宽度：`7` 补成 `0007`，但 `12345` 不会被截断。`%.3f` 控制小数点后三位。`Locale.ROOT` 保证输入小数点和输出小数点都采用 `.`；若题目要求本地化逗号，就必须在题面指定的格式下统一处理，不能代码一半用逗号、一半用句点。

### 6.4 `int` 乘法先提升为 `long`

若两个乘数都是 `int`，即使结果变量声明为 `long`，乘法也会先在 `int` 中完成，超出范围后才转换。应在乘法前把至少一个乘数提升为 `long`；随后基于这个 `long` 做加法。

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int a = sc.nextInt();
        int b = sc.nextInt();

        long product = (long) a * b;
        long total = product + 1;

        System.out.println(product);
        System.out.println(total);
    }
}
```

**输入（`stdin`）**

```text
100000 100000
```

**输出（`stdout`，末尾换行）**

```text
10000000000
10000000001
```

本题约定乘积以及再加一后的 `total` 都在 `long` 范围。`100000 * 100000` 超出 `int` 范围，但 `(long) a * b` 先提升 `a`，整个乘法按 `long` 执行。`long product = (long) (a * b)` 仍然太晚：括号里的 `int` 乘法已经先发生。这里只需要这一处宽度转换，不需要扩成通用算法问题。

## 7. Python 基础输入：input 与 sys.stdin

Python 的输入题先看协议，不必一开始追求“最快模板”。如果题目按行给固定字段，用 `input()` 最直观；如果所有数字由任意空白分隔，拿 Token 更稳；如果必须保留行内空格，就先读整行再决定如何处理。以下每个示例都能直接保存为 `main.py` 运行，展示的输入、输出来自同一程序。

### 7.1 一个整数：`input()` 返回字符串

`input()` 读取一行并去掉行尾换行，返回值是 `str`。题目要整数时，必须自己用 `int()` 转换：

```python
n = int(input())
print(n)
```

**输入示例**

```text
7
```

**输出示例（末尾换行）**

```text
7
```

如果直接写 `s = input()`，`s` 是字符串 `"7"`，而不是整数 `7`。比较、加减、循环次数需要数值时才转换；要把原字符串原样输出时就不要多转一次。

### 7.2 一行两个整数：`split()`、`map()` 与解包

以输入 `10 7` 为例，可以逐层观察值和返回类型：

| 这一步做什么 | 得到的值与类型 |
|---|---|
| `input()` 读整行 | `"10 7"`，类型是 `str` |
| `split()` 切字段 | `["10", "7"]`，类型是 `list[str]`，元素仍是字符串 |
| `map(int, ...)` 建立转换 | 一个 `map` 迭代器；遍历时依次产出整数 `10`、`7` |
| `list(...)` 保存结果 | `[10, 7]`，类型是 `list[int]` |
| `a, b = ...` 解包 | `a` 为 `10`，`b` 为 `7`，各自都是 `int` |

实际代码可以压成一行：`input()` 先得到整行字符串，`split()` 得到字符串列表，`map()` 按需执行 `int()`，左侧解包再读取两个结果：

```python
a, b = map(int, input().split())
print(a + b)
```

**输入示例**

```text
10 7
```

**输出示例（末尾换行）**

```text
17
```

解包要求两边数量正好相等。若一行意外有三个数，这个程序会抛出 `ValueError`；协议固定为两个数时，这正是希望尽早暴露的错误。输入为负数时也不受影响。

### 7.3 一行 `n` 个整数：何时保留列表

下面的值后面既要检查数量，又要求和，因此先转成 `list` 合理：

```python
n = int(input())
nums = list(map(int, input().split()))
print(len(nums) == n)
print(sum(nums))
```

**输入示例**

```text
3
4 5 6
```

**输出示例（末尾换行）**

```text
True
15
```

如果后续完全不按下标访问数组，也不多次遍历，`list` 不是必需品。只要求和时，可以直接写 `sum(map(int, input().split()))`；`map` 每产生一个整数，`sum()` 就立即消费它。若还要保存数组，则用 `nums = list(map(int, input().split()))`。本题的 `len()` 检查说明 `nums` 需要变成一个可重复查看的列表。

### 7.4 `map()` 是惰性迭代器，也可能是一次性的

`map()` 不会在创建时把全部结果放进列表。它等到被迭代时才逐项计算；迭代耗尽后再取就是空的。下面先让 `sum()` 消费整数转换结果，再试着转成列表：

```python
numbers = map(int, input().split())
print(sum(numbers))
print(list(numbers))
```

**输入示例**

```
3 5
```

**输出示例（末尾换行）**

```text
8
[]
```

`sum(numbers)` 已经把 `map` 迭代到末尾，再调用 `list(numbers)` 只能得到空列表。如果转换结果还要复用，应在第一次消费前写成 `numbers = list(map(int, input().split()))`；或者提前保存 `parts = input().split()`，再用 `map(int, parts)` 重建迭代器。不能靠再次调用 `input()` 重用上一行。

选择写法时可以这样判断：

```text
只消费一次：map(...) 直接交给 sum / join / any / max
需要按下标或重复遍历：list(map(...))
数量正好已知：a, b = map(...) 解包
要一次打印所有元素：print(*map(...))
```

### 7.5 T 组数据与含空格整行

程序先读组数，随后每组恰好读一整行。这里使用 `input()`：它会去掉行尾换行，却保留行首、行尾和中间的普通空格。

```python
import sys

t = int(input())
out = []
for _ in range(t):
    s = input()
    out.append(f"{len(s)}:[{s}]")

if out:
    sys.stdout.write("\n".join(out) + "\n")
```

**输入示例**

```text
2
hello world
  padded  
```

**输出示例（末尾换行）**

```text
11:[hello world]
10:[  padded  ]
```

输出中的方括号只是为了让前导、尾随空格可见。若题目要求按固定组数读字符串，就不要先用 `split()`，否则空格会被拆成多个 Token；若题目本来只关心中间一个单词，才适合 `input().split()[0]`。

### 7.6 T 组 `n` 个整数

这类题有两层协议：先读组数，再在每组中读 `n`。下面的程序只用于题面保证“每组整数都在一行”的格式：

```python
import sys

t = int(input())
out = []
for _ in range(t):
    n = int(input())
    nums = list(map(int, input().split()))
    out.append(str(sum(nums)))

if out:
    sys.stdout.write("\n".join(out) + "\n")
```

**输入示例**

```text
2
3
1 2 3
2
4 5
```

**输出示例（末尾换行）**

```text
6
9
```

若数组可能跨行，应改用第 8 章连续 Token 的写法，不必为每题手写“不断读行直到凑够 `n`”的循环。

### 7.7 EOF 多组二元组

有些题不先告诉组数，而是一直读到文件结尾。`for line in sys.stdin` 会在 EOF 自动停止；下面的空行跳过只在题面允许空行作为分隔时使用：

```python
import sys

out = []
for line in sys.stdin:
    if line.strip() == "":
        continue
    a, b = map(int, line.split())
    out.append(str(a + b))

if out:
    sys.stdout.write("\n".join(out) + "\n")
```

**输入示例**

```text
1 2
3 4
```

**输出示例（末尾换行）**

```text
3
7
```

EOF 表示输入源已经结束，不是凭空出现的一条空记录。若空行本身有含义，例如表示一条空字符串，就不能统一跳过；第 8 章会把这两种情况分开。

## 8. Python 快速输入与按行输入

### 8.1 按题面协议选择输入入口

| 题面特征 | 建议写法 | 关键前提 |
|---|---|---|
| 少量单组，一行几个字段 | `input().split()` | 以行组织字段，空格可作为分隔 |
| 必须保留一行中的前后空格 | `input()` 或 `sys.stdin.readline().rstrip("\r\n")` | 不要无条件调用 `strip()` |
| 已知行数，每行固定字段 | `sys.stdin.readline()` + `split()` | 行边界就是记录边界 |
| 行数未知，按行处理到 EOF | `for line in sys.stdin` | EOF 时迭代结束，行尾换行仍可能保留 |
| 大数据，所有数字由任意空白分隔 | `sys.stdin.buffer.read().split()` | 输入会完整到达 EOF，且允许整读占内存 |

题面说“任意空白分隔”时，换行只是一种空白，数据可以在多行；题面说“每行一个字符串”时，行边界就是业务数据，不能随意合成 Token 流。

### 8.2 `buffer.read()`：一次拿到全部字节后切 Token

`sys.stdin.buffer.read()` 一直读到 EOF，返回整段 `bytes`；再调用 `.split()` 会切出 `list[bytes]`。`int()` 可以直接解析 `bytes` Token：

```python
import sys

data = sys.stdin.buffer.read().split()
it = iter(data)
n = int(next(it))
nums = [int(next(it)) for _ in range(n)]
print(type(data[0]).__name__)
print(nums)
print(sum(nums))
```

**输入示例**

```text
3
1 2 3
```

**输出示例（末尾换行）**

```text
bytes
[1, 2, 3]
6
```

这条写法适合 Token 数很大、格式允许任意空白的情况。代价是 `read()` 在交互环境里会一直等到输入源结束；如果程序还需要在输入中途立刻响应，就不能采用整读。另一个代价是峰值内存：整个输入、Token 列表和后续 `nums` 会同时存在。

`sys.stdin.read()` 与 `buffer.read()` 的区别也很直接：前者返回 `str`，后者返回 `bytes`。用 `buffer.read().decode().split()` 时，短时间内可能同时保留 `bytes` 和解码出的 `str`，大数据场景要留意这个额外峰值。

### 8.3 `readline()`：一行就是一条记录

固定格式多行题适合逐行读取。`readline()` 保留行尾换行，所以解析数字前交给 `int()` 或 `split()` 即可；若输出整行原文，则应只删行尾：

```python
import sys

input = sys.stdin.readline
n = int(input())
total = 0
for _ in range(n):
    u, v, w = map(int, input().split())
    total += u + v + w
print(total)
```

**输入示例**

```
2
1 2 3
4 5 6
```

**输出示例（末尾换行）**

```text
21
```

这里的 `split()` 会忽略字段间连续多个空格。若一行本身是答案字符串，则用 `line = input().rstrip("\r\n")` 保留其余字符；无条件的 `line.strip()` 会一并删掉有意义的行首和行尾空格。

### 8.4 `read()`、`readline()` 与内存边界

三种读取入口先按返回值区分：

| 写法 | 读到哪里 | 返回类型 | 适合的协议 |
|---|---|---|---|
| `sys.stdin.readline()` | 下一行结束 | `str` | 行就是记录，保留行内空格 |
| `sys.stdin.read()` | EOF | `str` | 需要整段文本，再自行切分 |
| `sys.stdin.buffer.read()` | EOF | `bytes` | 大量 Token，后续可直接调用 `int(bytes)` |

`readline()` 可以逐行推进，`read()` 和 `buffer.read()` 都要等输入源结束。整读并不等于输入“绝对更快”：它一定先占用整份输入的内存；`buffer.read().split()` 还会再建立 Token 列表；若转成 `str` 或 `int` 列表，又会有后续结构同时存在。判断方案时先确认输入是否一次性到达、总规模是否可承受，再比较速度。

### 8.5 EOF、空行与有意义空格

`for line in sys.stdin` 是惰性的：它逐行读取，EOF 时停止，不会先吞掉全部文件。下面的程序把完全空行与普通文本分开，并保留文本前后的空格：

```python
import sys

out = []
for line in sys.stdin:
    text = line.rstrip("\r\n")
    if text == "":
        out.append("<blank>")
    else:
        out.append(f"{len(text)}:[{text}]")

if out:
    sys.stdout.write("\n".join(out) + "\n")
```

**输入示例**

```text
alpha

  beta  
```

**输出示例（末尾换行）**

```text
5:[alpha]
<blank>
8:[  beta  ]
```

处理空行前先看题面语义：如果空行只是分隔符，可以显式跳过；如果空行代表空字符串，必须保留；如果题目是 Token 流，`read().split()` 通常根本不会产生空 Token。空行、只含空格的行、EOF 是三种不同的输入状态，最好分别命名和理解。

### 8.6 按行读二维数组并汇总

行列数明确时，每行先构造 `row`，再追加到 `board`。这样每一行都是独立的 `list`：

```python
rows, cols = map(int, input().split())
board = []
for _ in range(rows):
    row = list(map(int, input().split()))
    board.append(row)

print([sum(row) for row in board])
print(sum(sum(row) for row in board))
```

**输入示例**

```
2 3
1 2 3
4 5 6
```

**输出示例（末尾换行）**

```text
[6, 15]
21
```

程序信任题面保证每行恰好给出 `cols` 个数；若协议允许跨行，应改用 8.7 的平面数据还原。若某题要求先把当前行建成空列表再逐个追加 Token，正确顺序是：

```text
board.append([])
for x in values:
    board[-1].append(x)
```

第一行新列表追加到 `board` 尾部，`board[-1]` 才指向刚创建的那一行。这里重点掌握正确初始化；行别名的完整错误案例放在第 11 章集中讲解。

二维求和可以按层的自然含义读作 `sum(sum(row) for row in board)`：内层求一行之和，外层把各行之和相加。只求总量时不必手工写双层循环，后续算法若需要行列坐标再访问 `board[i][j]`。

### 8.7 从平面 `data` 还原 `board`

如果所有数据先成一维列表，前两个位置是 `rows`、`cols`，那么矩阵值从下标 2 开始。第 `i` 行第 `j` 列的位置是 `2 + i * cols + j`：

```python
import sys

flat = list(map(int, sys.stdin.buffer.read().split()))
rows = flat[0]
cols = flat[1]
board = [[0] * cols for _ in range(rows)]

for i in range(rows):
    for j in range(cols):
        board[i][j] = flat[2 + i * cols + j]

print(board)
print(sum(sum(row) for row in board))
```

**输入示例**

```
2 3
1 2 3
4 5 6
```

**输出示例（末尾换行）**

```text
[[1, 2, 3], [4, 5, 6]]
21
```

`board` 先预分配成 `rows` 个独立的 0 行，再通过 `board[i][j] = ...` 原地赋值。2×3 的平面索引可以画成：

```text
board 位置   flat 下标   flat 值
(0, 0)       2           1
(0, 1)       3           2
(0, 2)       4           3
(1, 0)       5           4
(1, 1)       6           5
(1, 2)       7           6
```

关键乘法是行号乘列数，再把列号相加。写成 `i * j + 2` 并不会跳到下一行：例如 `i = 1`、`j = 1` 时只会得到 3，而正确位置是 `2 + 1 * 3 + 1 = 6`（下标值 5）。一旦列数变化，前一种表达式更会错位。

## 9. Python 输出与多组数据

### 9.1 `print(list)` 与 `print(*nums)`

`print()` 看到多少个参数，就用 `sep` 隔开多少个参数。传入一个 `list` 时，它会打印列表表示；传入 `*nums` 时，列表先被解包成多个参数：

```python
nums = list(map(int, input().split()))
print(nums)
print(*nums)
```

**输入示例**

```text
1 2 3
```

**输出示例（末尾换行）**

```text
[1, 2, 3]
1 2 3
```

题目要数组内容时通常使用 `print(*nums)`，因为方括号和逗号只是 Python 的列表显示格式，题干很少要求。`print(*nums, sep=",")` 也可以得到逗号分隔；空列表交给 `print(*[])` 会只输出一个换行。

### 9.2 `join()` 为什么常与 `map(str, ...)` 搭配

`str.join()` 只接收字符串组成的可迭代对象，不会替调用者转换数字：

```python
nums = list(map(int, input().split()))
print(",".join(map(str, nums)))
```

**输入示例**

```text
3 5 8
```

**输出示例（末尾换行）**

```text
3,5,8
```

`map(str, nums)` 是惰性的，`join()` 迭代一次时逐项转换并拼接。它无需你自己先写 `list`；`join()` 会消费这个迭代器并构造完整结果，仍占内存。若直接写 `",".join(nums)`，第一个 `int` 就会触发 `TypeError`；这属于类型协议错误，不是 `join()` 的分隔符问题。

### 9.3 一次准备多行输出

题目要求每个元素占一行时，先把每行文本放进列表，再用换行 `join()`。这样不会在十万次循环中反复调用 `print()`：

```python
import sys

n = int(input())
lines = [f"{i}:{i * i}" for i in range(1, n + 1)]
if lines:
    sys.stdout.write("\n".join(lines) + "\n")
```

**输入示例**

```text
3
```

**输出示例（末尾换行）**

```text
1:1
2:4
3:9
```

`n` 为 0 时不写任何字符。真实题面若要求最后一行也换行，就在 `join()` 后补一个换行；若明确不允许末尾换行，则去掉补上的那一个。

### 9.4 保留小数位

需要固定小数位时，让格式说明负责补零，不要用 `round()` 后再直接打印原本的浮点数：

```python
x = float(input())
print(f"{x:.2f}")
print(f"{x:.6f}")
```

**输入示例**

```text
3.14159
```

**输出示例（末尾换行）**

```text
3.14
3.141590
```

".2f" 固定两位小数，不够两位会补 0。题目使用误差判定时，可以按题面给足位数；题目要求严格字符串格式时，必须逐字匹配小数位数和负零规则。

### 9.5 前导零

前导零是字符串格式，不是整数值的一部分。常用 f-string 宽度或 `zfill()` 生成：

```python
n = int(input())
print(f"{n:03d}")
print(str(n).zfill(5))
```

**输入示例**

```text
7
```

**输出示例（末尾换行）**

```text
007
00007
```

宽度是“至少”多少位，不会截断更长的数；例如 `1234` 用 `03d` 仍输出 `1234`。负数参与补零时，符号也占宽度：输入 `-7` 时，`f"{-7:03d}"` 得到 `-07`，`str(-7).zfill(5)` 得到 `-0007`。

## 10. 八种高频输入模型实战

本章用八道练习覆盖矩阵、T 组、EOF、按行记录、分隔字段、保留空白的字符串、跨行数组和格式化输出。每题先写清协议，再分别给 Java 与 Python 的完整程序；文本示例中的每个输出记录都以换行结束。

### 10.1 矩阵总和与逐行和：先分清行数、列数

**协议与前提**：第一行是 `rows cols`，随后恰好有 `rows * cols` 个整数，可跨行并允许任意数量的空格或制表符；`rows, cols >= 1`，总和与每行和都在 Java `long` 范围内。先输出整个矩阵的总和，再依次输出每行的和。把列数错当行数通常不会立刻报错，却会让循环读少或读多，所以程序中统一使用 `row < rows` 和 `col < cols`。

**输入示例**

```text
2 3
1 2 3
4 5 6
```

**输出示例**

```text
21
6
15
```

**Java**

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int rows = sc.nextInt();
        int cols = sc.nextInt();
        long[] rowSums = new long[rows];
        long total = 0;

        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                rowSums[row] += sc.nextLong();
            }
            total += rowSums[row];
        }

        StringBuilder out = new StringBuilder();
        out.append(total).append('\n');
        for (long sum : rowSums) {
            out.append(sum).append('\n');
        }
        System.out.print(out);
    }
}
```

**Python**

```python
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
rows, cols = data[0], data[1]
row_sums = []
pos = 2
total = 0

for _ in range(rows):
    current = sum(data[pos:pos + cols])
    row_sums.append(current)
    total += current
    pos += cols

out = [str(total)] + [str(value) for value in row_sums]
sys.stdout.write("\n".join(out) + "\n")
```

Python 这里先整读 token，再按 `cols` 切片，`pos` 每次只前进一行的列数。若输入规模大到不能整读，应换成第 8 章的流式读取；本题没有引入更复杂的框架。

### 10.2 T 组不同尺寸矩阵：尺寸必须每组重读

**协议与前提**：第一行是组数 `T`，`T >= 1`。每组先给 `rows cols`（`rows, cols >= 1`），再给该组恰好 `rows * cols` 个整数，尺寸和数字都可以跨行。每组输出 `rows cols total`，其中 `total` 是这一组所有元素的和，均在 64 位整数范围内。不能把第一组的行列数沿用到后续组。

**输入示例**

```text
2
2 3
1 2
3 4 5 6
1 2 1
8
```

**输出示例**

```text
2 3 21
1 2 9
```

**Java**

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int groups = sc.nextInt();
        StringBuilder out = new StringBuilder();

        for (int group = 0; group < groups; group++) {
            int rows = sc.nextInt();
            int cols = sc.nextInt();
            long total = 0;
            for (int row = 0; row < rows; row++) {
                for (int col = 0; col < cols; col++) {
                    total += sc.nextLong();
                }
            }
            out.append(rows).append(' ').append(cols).append(' ')
               .append(total).append('\n');
        }
        System.out.print(out);
    }
}
```

**Python**

```python
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
it = iter(data)
groups = next(it)
out = []

for _ in range(groups):
    rows = next(it)
    cols = next(it)
    total = sum(next(it) for _ in range(rows * cols))
    out.append(f"{rows} {cols} {total}")

sys.stdout.write("\n".join(out) + "\n")
```

用 token 流后，换行只是分隔符；`2 3` 与三个矩阵值挤在同一行也能工作。Python 的生成器逐项消耗同一个迭代器，正好读完当前组而不越过下一组。

### 10.3 EOF 成对长整数：没有 T，配对跨行

**协议与前提**：输入到 EOF 为止，共包含偶数个十进制整数，可任意换行并使用空白分隔；每个整数满足 `|x| <= 10^18`，每对和仍在 Java `long` 范围内。每对输出一行和。空输入合法，此时标准输出为空字符串。

**输入示例**

```text
10000000000 -3
7
999999999999999999
```

**输出示例**

```text
9999999997
1000000000000000006
```

**Java**

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        StringBuilder out = new StringBuilder();

        while (sc.hasNextLong()) {
            long first = sc.nextLong();
            long second = sc.nextLong();
            out.append(first + second).append('\n');
        }
        System.out.print(out);
    }
}
```

**Python**

```python
import sys

data = sys.stdin.buffer.read().split()
out = []

for pos in range(0, len(data), 2):
    first = int(data[pos])
    second = int(data[pos + 1])
    out.append(str(first + second) + "\n")

sys.stdout.write("".join(out))
```

Java 用 `hasNextLong` 与 `nextLong` 保持同一 token 类型；Python 按索引 `0,2,4,...` 每次取两个。题面承诺成对；若真实输入允许落单，必须先在协议层定义落单时输出什么，不能靠偶然异常代替规则。

### 10.4 按行不定长数组：空行是一条空记录

**协议与前提**：第一行是记录数 `n`，`n >= 1`；随后恰好有 `n` 个物理行。每条非空行包含零个或多个空格分隔的整数，只含空白的行表示空记录，每行的和都在 64 位整数范围内。每行输出 `数量 总和`，空记录固定输出 `0 0`，不能因为空而跳过，否则后续记录会错位。

**输入示例**

```text
4
1 2 3

4   5

```

**输出示例**

```text
3 6
0 0
2 9
0 0
```

**Java**

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.IOException;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        int records = Integer.parseInt(br.readLine().trim());
        StringBuilder out = new StringBuilder();

        for (int record = 0; record < records; record++) {
            String line = br.readLine();
            String trimmed = line.trim();
            if (trimmed.isEmpty()) {
                out.append("0 0\n");
                continue;
            }

            String[] fields = trimmed.split("\\s+");
            long total = 0;
            for (String field : fields) {
                total += Long.parseLong(field);
            }
            out.append(fields.length).append(' ').append(total).append('\n');
        }
        System.out.print(out);
    }
}
```

**Python**

```python
import sys

records = int(sys.stdin.readline())
out = []

for _ in range(records):
    line = sys.stdin.readline()
    fields = line.split()
    out.append(f"{len(fields)} {sum(map(int, fields))}")

sys.stdout.write("\n".join(out) + "\n")
```

这里读取的是物理行，不能把整个输入摊平成 token 流。Python 的 `split()` 对空行返回空列表，`sum([])` 为 `0`；Java 则显式判断 `trimmed.isEmpty()`，两边对空记录的含义一致。

### 10.5 逗号字段：空格可变，逗号属于协议

**协议与前提**：第一行是字段个数 `k`，`k >= 1`；第二行恰好包含 `k` 个整数，字段之间用单个逗号分隔，每个字段左右允许空格。字段内部不能再有逗号，也不允许空字段。输出 `字段个数 总和`，总和在 64 位整数范围内。

**输入示例**

```text
4
 10 , 20,30 ,40 
```

**输出示例**

```text
4 100
```

**Java**

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.IOException;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        int expected = Integer.parseInt(br.readLine().trim());
        String[] fields = br.readLine().trim().split(",");
        long total = 0;

        for (String field : fields) {
            total += Long.parseLong(field.trim());
        }

        if (fields.length != expected) {
            throw new IllegalArgumentException("field count mismatch");
        }
        System.out.println(fields.length + " " + total);
    }
}
```

**Python**

```python
import sys

expected = int(sys.stdin.readline())
line = sys.stdin.readline().strip()
fields = line.split(",")
values = [int(field.strip()) for field in fields]

if len(values) != expected:
    raise ValueError("field count mismatch")
print(f"{len(values)} {sum(values)}")
```

不能直接把逗号也交给 `split()`，否则整行会变成一个字段。此处保留逗号边界，再逐个去掉字段两侧空格；如果题面允许 `1,,2` 这样的空字段，就必须单独定义空字段是否代表零，不能把本次“无空字段”的实现照搬过去。

### 10.6 每行一段含空格字符串：只删行尾，不删内容

**协议与前提**：第一行是 `n`，`n >= 1`；随后恰好 `n` 个物理行，每行是 ASCII 字符串，可以含前导空格、尾随空格或完全为空。空格属于内容，字符串长度按 ASCII 字符数计算。每行输出该字符串长度。示例输入第三行就是完全空行。

**输入示例**

```text
4
hello world
  padded  

Java
```

**输出示例**

```text
11
10
0
4
```

**Java**

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.IOException;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        int lines = Integer.parseInt(br.readLine().trim());
        StringBuilder out = new StringBuilder();

        for (int lineNumber = 0; lineNumber < lines; lineNumber++) {
            String line = br.readLine();
            out.append(line.length()).append('\n');
        }
        System.out.print(out);
    }
}
```

**Python**

```python
import sys

lines = int(sys.stdin.readline())
out = []

for _ in range(lines):
    line = sys.stdin.readline()
    if line.endswith("\n"):
        line = line[:-1]
    if line.endswith("\r"):
        line = line[:-1]
    out.append(str(len(line)))

sys.stdout.write("\n".join(out) + "\n")
```

`BufferedReader.readLine()` 和 Python 的去行尾操作都保留行内空格。没有调用 `strip()`，是因为它会把题目要求计数的前后空格删掉。这里限定 ASCII，是为了避免把 Java `String.length()` 的 UTF-16 单元数与 Python 的 Unicode 码点数混为一谈。

### 10.7 跨行一维数组：包括 `n = 0` 的约定

**协议与前提**：第一个 token 是元素个数 `n`，`n >= 0`；随后恰好有 `n` 个 32 位有符号整数，可出现在任意物理行。先输出 `n`，再把原数组按输入顺序每行输出一个整数；当 `n = 0` 时只输出一行 `0`。

**输入示例**

```text
5
10 20
30  40
50
```

**输出示例**

```text
5
10
20
30
40
50
```

**Java**

```java
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        int[] values = new int[n];

        for (int i = 0; i < n; i++) {
            values[i] = sc.nextInt();
        }

        StringBuilder out = new StringBuilder();
        out.append(n).append('\n');
        for (int value : values) {
            out.append(value).append('\n');
        }
        System.out.print(out);
    }
}
```

**Python**

```python
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
n = data[0]
values = data[1:1 + n]

out = [str(n)] + [str(value) for value in values]
sys.stdout.write("\n".join(out) + "\n")
```

这题故意保留 `n = 0`，因为“先读一个 `n`”和“没有输入”是两种不同协议：前者仍必须输出 `0`，后者才会产生空输出。Java 用 `Scanner` 已足够；第五到第八章的快速输入模板只在规模需要时替换读取层，不改变后面的数组逻辑。

### 10.8 前导零与定点小数：格式由输出协议决定

**协议与前提**：第一行是记录数 `n`，`n >= 1`；随后每条记录是 `id amount`，其中 `0 <= id <= 999999`，`0 <= amount <= 1000` 且小数部分最多两位。不需要做超过两位小数的舍入。按输入顺序输出 `ITEM-四位以上 id=两位小数`，例如 id 为 7 时写成 `ITEM-0007`；小数点固定为 `.`，末尾换行。

**输入示例**

```text
3
7 12.5
42 0.75
1234 1000
```

**输出示例**

```text
ITEM-0007=12.50
ITEM-0042=0.75
ITEM-1234=1000.00
```

**Java**

```java
import java.util.Locale;
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        sc.useLocale(Locale.ROOT);
        int n = sc.nextInt();
        StringBuilder out = new StringBuilder();

        for (int i = 0; i < n; i++) {
            int id = sc.nextInt();
            double amount = sc.nextDouble();
            out.append(String.format(Locale.ROOT, "ITEM-%04d=%.2f\n", id, amount));
        }
        System.out.print(out);
    }
}
```

**Python**

```python
import sys

n = int(sys.stdin.readline())
out = []

for _ in range(n):
    id_text, amount_text = sys.stdin.readline().split()
    item_id = int(id_text)
    amount = float(amount_text)
    out.append(f"ITEM-{item_id:04d}={amount:.2f}")

sys.stdout.write("\n".join(out) + "\n")
```

`%04d` 与 `:04d` 表示至少四位，不是截断：`1234` 仍完整输出。Java 使用 `Locale.ROOT` 固定小数点，避免运行环境把它改成逗号；本题输入最多两位小数，所以 `%.2f` 只负责补零。若题目要求精确到更多位或指定舍入规则，应改用整数分单位或高精度十进制，不要继续依赖二进制浮点数的偶然结果。

## 11. 常见坑与检查清单

这一章用五个小反例定位“为什么错、怎样改”。它们都是完整程序，且全部不可作为提交答案；其中三个直接抛错，另外两个正常退出却产生错误结果。矩阵正确读写的完整流程见第 8 章的 8.6 与 8.7；10.1 和 10.2 是汇总练习。Java 的 `nextInt()` 后混读 `nextLine()`、整数乘法溢出等完整对照见第 3～6 章，这里不重复代码。

### 11.1 输入坑与矩阵小反例

- **把 EOF 当空行**：`readLine()` 返回 `null` 表示没有更多物理行，不是空字符串；只有真正的一条空行才返回 `""`。
- **未分类就跳过空行**：空行可能只是分组间隔，也可能是按行协议中的空记录。先看题面，再决定输出 `0` 或跳过；不能把所有空行统一 `strip()` 掉。
- **把物理行协议改成 token 流**：含空格字符串、逗号字段和“一行一条记录”都必须先保留行边界。
- **`split(" ")` 处理多空格**：它会留下空串；无分隔协议的 token 行可明确使用 `split("\\s+")` 或 `StringTokenizer`。
- **BOM/CRLF**：只有协议要求时才处理首 token 的 `\uFEFF`；行尾只删 `\r\n`，不要顺手删内容两侧空格。

**反例一：空 `board` 没有最后一行。** 输入 `0 3` 时外层列表为空，`board[-1]` 找不到合法行并抛出 `IndexError`。若要取“最后一行”，协议必须先保证 `rows >= 1`；若 `rows` 可以为 0，则应在访问前分支处理。

**输入示例**

```text
0 3
```

**预期结果**：标准输出为空字符串；退出码 `1`，`stderr` 含 `IndexError`。

```python
import sys

rows, cols = map(int, sys.stdin.readline().split())
board = [[0] * cols for _ in range(rows)]
print(board[-1])
```

**反例二：`sum(board)` 把每一行当成可以相加的数。** 输入一条记录 `2 3` 时，`board` 是 `[[2, 3]]`，外层 `sum` 会尝试执行 `0 + [2, 3]`，抛出 `TypeError`。空矩阵反而得到 `0`，这会掩盖错误，所以不能只用空输入验证它。

**输入示例**

```text
1
2 3
```

**预期结果**：标准输出为空字符串；退出码 `1`，`stderr` 含 `TypeError`。

```python
import sys

rows = int(sys.stdin.readline())
board = [list(map(int, sys.stdin.readline().split())) for _ in range(rows)]
print(sum(board))
```

修正时先把每行求和，再求这些行和的总和：可以写成 `sum(sum(row) for row in board)`。空行本身也能贡献 `sum([]) == 0`；这里真正要修的是外层求和对象。若还需要边读边处理超出一行保存能力的数据，可改用 `total = 0` 后逐行累加。

**反例三：`[[0] * cols] * rows` 复制的是行引用。** 输入 `2 3` 时矩阵只有两行，修改 `board[0][0]` 会同时改变两处第一列，因为两行指向同一个列表。只有 `rows = 1` 时这个错误碰巧看不出来，不能据此判断正确。

**输入示例**

```text
2 3
```

**错误结果示例**（程序正常退出，但答案语义错误）

```text
[[1, 0, 0], [1, 0, 0]]
```

```python
import sys

rows, cols = map(int, sys.stdin.readline().split())
board = [[0] * cols] * rows
board[0][0] = 1
print(board)
```

应改为 `board = [[0] * cols for _ in range(rows)]`；列表推导式每轮都创建一条独立的内层列表。

**反例四：过滤结果为空时，`ans[-1]` 仍要求至少一个元素。** 第一行没有正整数时，`ans` 为空，访问最后一个答案触发 `IndexError`。先判断 `ans`，或在协议允许“无答案”时为它定义单独输出。

**输入示例**

```text
0 -2
```

**预期结果**：标准输出为空字符串；退出码 `1`，`stderr` 含 `IndexError`。

```python
import sys

values = list(map(int, sys.stdin.readline().split()))
ans = [value for value in values if value > 0]
print(ans[-1])
```

当输入为 `0 5` 时，`ans` 是 `[5]`，程序才会正常输出 `5`；这说明边界数据的选择会直接决定错误是否暴露。

修正时，先在题面协议中明确“没有正数”应输出什么；例如约定为 `NONE`，结构可写成：

```text
if ans:
    print(ans[-1])
else:
    print("NONE")
```

**反例五：在完整 `data` 上把 `i * j + 2` 当成元素下标。** 输入形如 `data = [rows, cols, ...]`，开头两个位置是尺寸值，矩阵元素从 `data[2]` 开始。对 `2 3` 矩阵取 `i = j = 1`，正确扁平位置是 `data[2 + i * cols + j]`，即 `data[6]`，值为 `14`；错误表达式 `i * j + 2` 却读到 `data[3]`，值为 `11`。下标仍在范围内，所以程序通常不会崩，只会静默读错。

**输入示例**

```text
2 3
10 11 12
13 14 15
```

**错误结果示例**（程序正常退出，但读错元素）

```text
11
```

```python
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
rows, cols = data[0], data[1]
i, j = 1, 1
print(data[i * j + 2])
```

错误表达式里的 `+2` 确实跳过了开头两个尺寸值，但 `i * j` 没有按列宽跳行。若把输入换成 `2 4`，错误代码仍读 `data[3] = 11`，而正确位置变成 `data[2 + 1 * 4 + 1] = data[7] = 21`；因此“这次没崩”不能证明下标正确。

**综合修正版：从完整输入构造并访问矩阵。** 下面仍从 `data` 读取，但先切掉开头两个尺寸值，再用列表推导式构造独立行。程序修改 `board[0][0]` 后检查最后一行、总和与正确扁平位置；输入限定 `rows, cols >= 2`，以便访问 `(1, 1)`。

**输入示例**

```text
2 3
10 11 12
13 14 15
```

**输出示例**

```text
13 14 15
175
14 14
```

```python
import sys

data = list(map(int, sys.stdin.buffer.read().split()))
rows, cols = data[0], data[1]
values = data[2:]

board = [[values[row * cols + col] for col in range(cols)] for row in range(rows)]
board[0][0] += 100

total = sum(sum(row) for row in board)
i, j = 1, 1
flat_index = 2 + i * cols + j

print(*board[-1])
print(total)
print(board[i][j], data[flat_index])
```

第一行仍是 `13 14 15`，说明修改首行没有连带修改末行；`175` 是每行先求和、再汇总的结果；最后一行同时输出二维访问值 `board[1][1]` 与计入开头偏移的正确扁平值 `data[2 + 1 * 3 + 1]`，两者都是 `14`。

### 11.2 数据类型坑

- Java `int` 的求和或乘法可能溢出，即使最终答案看起来“不大”；涉及累加与乘法时先判断上界，必要时提升为 `long`。
- 题目单个值到十亿级并不自动说明总和安全；应看元素个数和运算次数。Python 整数不设固定位宽，但内存与输出长度仍受规模约束。
- 小数比较不要直接用 `==`；按题目给出的误差处理。需要固定小数格式时还要显式控制 locale。
- 输出可能出现 `-0.00` 时，按题面或特殊评测要求归一化，不能凭习惯自行删除负号。

### 11.3 输出坑

- 多组输出是否要求最终换行、行列之间用空格还是换行，都以题面为准；本文件的程序为每条可见输出保留最终换行。
- 前导零、固定小数位、`YES/NO` 大小写都属于答案内容。
- 不要输出“请输入”“结果为”等提示语，也不要保留调试日志。
- 大量输出应集中到 `StringBuilder`、列表后 `join` 或等价缓冲中，减少逐项刷新。

### 11.4 提交前检查

- [ ] 类名是否为 `Main`（Java）
- [ ] 有没有 `package`
- [ ] 有没有从文件读
- [ ] 有没有输出提示语
- [ ] 是否处理 T 组或 EOF
- [ ] 数组是否可能跨行
- [ ] 是否用了 `long`
- [ ] 输出格式和小数位是否正确
- [ ] 大数据是否使用了合适的输入方式
- [ ] 空行是按协议保留、当作空记录，还是明确跳过

## 12. 一页速查表

这一页只负责定位：先找到自己卡住的环节，再回对应章节看完整程序、前提与输入输出，不再复制一套相同模板。

| 现在的问题 | 去哪里看 | 先记住这一点 |
|---|---|---|
| 题目究竟是单组、T 组还是 EOF？ | [第 2 章：输入协议](../../library/acm-io/chapter-02.html) | 结束条件和换行含义先于读取速度 |
| Java `nextInt()` 后怎么读整行？ | [第 3 章：Scanner](../../library/acm-io/chapter-03.html) | `nextLine()` 读当前行余部；是否丢弃它取决于协议 |
| Java 数字可以跨行，或数据量很大？ | [第 4 章：连续 token](../../library/acm-io/chapter-04.html)、[第 5 章：高效读入](../../library/acm-io/chapter-05.html) | token 读取可以跨空白；整行文本不能这么读 |
| Java 输出 long、小数或前导零？ | [第 6 章：输出格式](../../library/acm-io/chapter-06.html) | 运算前提升类型，格式化时确认小数点与宽度 |
| `list(map(int, input().split()))` 每层做什么？ | [第 7 章：语句拆解](../../library/acm-io/chapter-07.html) | 字符串切开后仍是字符串；`map` 是待消费的迭代器 |
| 二维数组怎么创建、追加、赋值和求和？ | [第 8 章：矩阵与读取方式](../../library/acm-io/chapter-08.html) | 行要独立，平面位置是 `2 + i * cols + j`（含两个尺寸 token） |
| 怎么输出元素，而不是 `[1, 2]`？ | [第 9 章：Python 输出](../../library/acm-io/chapter-09.html) | `print(*nums)` 输出元素；`join` 需要字符串 |
| 想连起来练一次？ | [第 10 章：8 个组合练习](../../library/acm-io/chapter-10.html) | 每题先核对协议，再提交自己的完整程序 |
| 空列表越界、矩阵求和或共享行出了错？ | [第 11 章：反例与修正](../../library/acm-io/chapter-11.html) | 不报错也可能取错数据，要用具体小输入推演 |

如果卡在 `self`、`nonlocal`、容器 API 或递归语法，去[Python 实用入门与 AI 开发](../../library/python/index.html)查语言基础；这些内容不在本专题重复展开。

回到笔试时，用题目允许的数据做四次小检查：一个最小合法输入、两组不同尺寸的数据、协议允许的空白或空记录、接近数值上界的输入。不能为了“测边界”给题目不允许的负数、空矩阵或残缺记录。
