# Java 核心：语法、对象、集合源码、泛型反射、IO 与 NIO 及新特性

> 这份笔记的目标读者：有任意一门编程语言基础、正在准备大厂校招的 Java 后端候选人，也适合在职工程师系统回炉。  
> 建议版本：以 JDK 17 / 21 长期支持版为主讲解，凡是 JDK 8 与它们行为不同的地方都会单独标注。  
> 阅读方式：第一次学习按顺序读第 0~14 章；刷题和面试前重点回看第 5~9 章；冲刺阶段直接做第 17 章自测题。  
> 配套课程：并发编程、JVM、MySQL、Redis、计算机网络等模块会分别展开，本课程只覆盖“语言根基”这一层。  
> 示例代码以 JDK 17/21 为准；Java 8 差异与 JDK 21 专属语法会单独标注。“输出”是典型运行结果，可能因环境略有不同。

### 怎么用这份笔记

- **系统入门**：从第 0 章建立全局认知，第 1~4 章打语法与对象基础，每章末尾的“面试追问”先自己答再对答案；
- **应试突破**：第 5~7 章集合源码、第 8 章泛型、第 9 章反射是八股文高发区，需要能默写出 HashMap 的 put 流程；
- **当手册查**：第 16 章是一页速查表，第 17 章是分主题自测题；
- **学习闭环**：读完每章后，用 IDEA 对示例代码打断点，观察对象内存和集合扩容过程，比死记结论有效得多。

## 目录

- [0. 学习地图：Java 核心考什么](#0-学习地图java-核心考什么)
- [1. JDK、JRE、JVM 与字节码](#1-jdkjrejvm-与字节码)
- [2. 基本语法与类型系统](#2-基本语法与类型系统)
- [3. 面向对象三大特性](#3-面向对象三大特性)
- [4. Object、equals/hashCode 与 String](#4-objectequalshashcode-与-string)
- [5. 集合框架总览与 List 家族](#5-集合框架总览与-list-家族)
- [6. HashMap 源码精读](#6-hashmap-源码精读)
- [7. 其他 Map 与 Set 家族](#7-其他-map-与-set-家族)
- [8. 泛型：类型擦除与通配符](#8-泛型类型擦除与通配符)
- [9. 反射与动态代理](#9-反射与动态代理)
- [10. 异常体系与最佳实践](#10-异常体系与最佳实践)
- [11. IO 流体系与装饰器模式](#11-io-流体系与装饰器模式)
- [12. BIO、NIO、AIO 与零拷贝](#12-bionioaio-与零拷贝)
- [13. 序列化与反序列化](#13-序列化与反序列化)
- [14. Java 8 新特性：Lambda、Stream 与新日期](#14-java-8-新特性lambdastream-与新日期)
- [15. Java 9~25 新特性演进](#15-java-925-新特性演进)
- [16. 编程规范与一页速查](#16-编程规范与一页速查)
- [17. 高频自测题与参考资料](#17-高频自测题与参考资料)

---

## 0. 学习地图：Java 核心考什么

大厂校招对 Java 后端的考察通常分六层：**语言根基 → 并发 → JVM → 数据库 → 网络 → 框架与工程**。本课程是第一层，也是后面所有层的地基。语言根基不过关，谈并发和 JVM 时连“对象引用”“泛型擦除”“异常链”这类概念都会卡壳。

### 0.1 本课程覆盖的高频考点

| 主题 | 大厂高频考点 | 面试权重 |
|---|---|---|
| 类型系统 | 8 种基本类型、包装类缓存、自动装箱拆箱、`==` 与 `equals` | ★★★ |
| 面向对象 | 封装/继承/多态、重载与重写、抽象类与接口、初始化顺序 | ★★★ |
| String | 不可变性、常量池、`intern`、StringBuilder 与 StringBuffer | ★★★ |
| 集合 | ArrayList 扩容、HashMap 源码、LinkedList 对比、fail-fast | ★★★★★ |
| 泛型 | 类型擦除、通配符、PECS、桥方法 | ★★★★ |
| 反射 | Class 对象、动态代理、为什么框架离不开反射 | ★★★★ |
| 异常 | 受检/非受检、finally、try-with-resources、异常链 | ★★★ |
| IO/NIO | 字节流与字符流、装饰器模式、BIO/NIO/AIO、零拷贝 | ★★★★ |
| 序列化 | serialVersionUID、transient、反序列化安全 | ★★★ |
| 新特性 | Java 8 Lambda/Stream、Java 17/21 新特性 | ★★★ |

> 边界说明：本课只覆盖“语言根基”。并发原语、ThreadLocal、JMM、类加载与 GC 等分别由《Java 并发编程》《JVM》课程展开；在本课目录里找不到它们不是遗漏。

### 0.2 知识体系图

```mermaid
flowchart TD
    root[Java 核心<br/>语言根基] --> a[类型与对象]
    root --> b[集合源码]
    root --> c[语言机制]
    root --> d[IO 与序列化]
    root --> e[新特性与规范]
    a --> a1[基本类型 / 包装类]
    a --> a2[面向对象 / String]
    b --> b1[ArrayList / LinkedList]
    b --> b2[HashMap 源码]
    c --> c1[泛型 / 反射]
    c --> c2[异常体系]
    d --> d1[BIO / NIO / AIO]
    d --> d2[序列化]
    e --> e1[Java 8 Lambda/Stream]
    e --> e2[Java 17/21 新特性]
```

### 0.3 学习方法：源码驱动

1. **先画结构，再背结论**。集合、异常、IO 都有清晰的类层次，先画出体系图，再把每个类的行为挂到图上，记忆负担会小很多。
2. **直接读源码**。IDEA 里按住 Ctrl 点击 `ArrayList`、`HashMap` 就能进源码。面试问“扩容多少倍”“为什么转红黑树”，答案都在源码常量和注释里。
3. **版本敏感**。JDK 8 与 JDK 17/21 在 `String` 存储、`switch`、接口方法、集合 API 上都有差异，回答时主动说明“以 JDK 哪个版本为准”，这是加分项。
4. **用“是什么→为什么→怎么用→坑在哪”四问学习每个知识点**，而不是背单句结论。

### 0.4 面试追问

- 问：语言根基和并发、JVM 的关系是什么？
- 答：集合源码里的 `modCount`、HashMap 并发问题、String 不可变性都直接关联并发和 JVM 的内存模型，这一层是后续所有讨论的共同语言。

## 1. JDK、JRE、JVM 与字节码

几乎所有 Java 面试的第一题都是“JVM、JRE、JDK 有什么区别”，以及“Java 为什么能跨平台”。这一章把运行模型讲透，后面的所有内容都建立在这套模型上。

### 1.1 三者的关系

```mermaid
flowchart TD
    JDK[JDK<br/>javac 等开发工具 + JRE] --> JRE[JRE<br/>JVM + 核心类库]
    JRE --> JVM[JVM<br/>加载并执行字节码]
    JVM --> OS[操作系统<br/>Windows / Linux / macOS]
    SRC[.java 源文件] -->|javac 编译| BC[.class 字节码]
    BC --> JVM
```

- **JDK（Java Development Kit）**：面向开发者的工具包，包含 JRE 和 `javac`、`jar`、`javadoc`、`jdb` 等开发调试工具。
- **JRE（Java Runtime Environment）**：面向运行时的环境，包含 JVM 和 Java 核心类库（`java.lang`、`java.util` 等），供已经编译好的程序运行。
- **JVM（Java Virtual Machine）**：真正执行字节码的虚拟机。同一份字节码，在 Windows、Linux、macOS 上有各自的 JVM 实现，因此 Java 程序“一次编写，到处运行”。

JDK 9 引入模块化后，JRE 不再是独立的目录结构，JDK 直接内置运行时模块，但这个“JDK 包含 JRE，JRE 包含 JVM”的包含关系在概念上仍然成立。

### 1.2 从源码到运行：编译与解释并存

```text
.java 源码 --javac 编译--> .class 字节码 --JVM 加载--> 解释执行 + JIT 编译热点代码
```

严格说，Java 是“**编译与解释并存**”的语言：

1. `javac` 把 `.java` 编译成与平台无关的 `.class` 字节码（编译期）；
2. JVM 启动后逐条解释执行字节码（解释期）；
3. 对频繁执行的“热点代码”，JIT（Just-In-Time，即时编译器，如 C1/C2）会把它编译成当前平台的机器码并缓存，后续直接执行机器码。

这正是“先编译、后解释、再即时编译”的三段式模型。字节码是中间语言，机器码是最终产物。

### 1.3 类路径与 main 方法

运行一个 Java 程序的基本姿势：

```bash
javac Hello.java        # 生成 Hello.class
java Hello              # 启动 JVM，加载并执行 Hello 类
```

`java` 命令通过 **classpath（类路径）** 找到类和依赖的 jar。JDK 9 之后还引入了模块路径（module path），但校招阶段掌握 classpath 即可。

main 方法的签名必须精确是：

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java");
    }
}
```

为什么是这样？

- `public`：JVM 启动时从类外部调用它，必须可见；
- `static`：JVM 启动时还没有创建任何对象，必须通过类直接调用；
- `void`：JVM 不需要接收返回值；
- `String[] args`：接收命令行参数。

JDK 21 预览、JDK 25 正式化的“隐式类与实例 main 方法”允许简写成 `void main() { ... }`，适合教学和小脚本，但面试仍以标准签名为准。

### 1.4 JDK 版本节奏：LTS 与普通版本

| 版本 | 发布年份 | 是否 LTS | 校招关注点 |
|---|---|---|---|
| Java 8 | 2014 | 是 | 存量最大，Lambda/Stream/新日期时间 API 的起点 |
| Java 11 | 2018 | 是 | HttpClient 正式、String 新方法、单文件源码运行、ZGC 实验 |
| Java 17 | 2021 | 是 | 密封类正式、模式匹配 switch 预览、强封装 |
| Java 21 | 2023 | 是 | 虚拟线程、模式匹配 switch、record 模式正式 |
| Java 25 | 2025 | 是 | 最新 LTS，隐式类与主方法、灵活构造器主体正式化 |

校招简历写“熟悉 Java”时，建议写明“熟练掌握 Java 8/17/21”，并在回答中体现版本差异。

### 1.5 面试追问

- 问：JVM vs JDK vs JRE？
- 答：JDK 是开发工具包（JRE + javac 等）；JRE 是运行环境（JVM + 核心类库）；JVM 是执行字节码的虚拟机，负责类加载、字节码执行、内存管理。
- 问：Java 是编译型还是解释型语言？
- 答：编译与解释并存：`javac` 编译为字节码，JVM 解释执行字节码，热点代码再由 JIT 编译为机器码。
- 问：什么是字节码？为什么字节码能跨平台？
- 答：字节码是 `.class` 文件中的中间指令，与具体平台无关；JVM 针对每个平台有独立实现，把字节码翻译成对应平台的机器指令。
- 问：`public static void main(String[] args)` 每个修饰符的作用？
- 答：见 1.3，JVM 从外部、无对象、无返回值地启动程序，并传入命令行参数。

## 2. 基本语法与类型系统

类型系统是 Java 的“世界观”：一切数据要么是基本类型（存在栈上、按值传递），要么是对象引用（指向堆上的对象）。这一章先把类型、包装类和运算符讲清楚，集合与泛型章节都会用到。

### 2.1 八种基本类型

| 类型 | 字节数 | 默认值 | 取值范围（节选） |
|---|---|---|---|
| `byte` | 1 | 0 | -128 ~ 127 |
| `short` | 2 | 0 | -32768 ~ 32767 |
| `int` | 4 | 0 | 约 ±21 亿 |
| `long` | 8 | 0L | ±9.22e18 |
| `float` | 4 | 0.0f | 单精度浮点 |
| `double` | 8 | 0.0d | 双精度浮点 |
| `char` | 2 | `'\u0000'` | 0 ~ 65535（无符号） |
| `boolean` | 规范未定 | false | true / false |

要点：

- `char` 是无符号 16 位，Java 内部用 UTF-16 表示字符，所以一个“字符”不总等于一个 Unicode 码点，生僻字或 emoji 需要两个 `char`（代理对）。
- `boolean` 在 JLS 中没有规定精确大小：HotSpot 中局部变量通常占 4 字节，`boolean[]` 每个元素占 1 字节。
- 浮点默认字面量是 `double`，写 `float f = 1.2;` 会编译报错，必须写 `1.2f`。
- 长整型字面量建议加 `L`：`long x = 12345678901L;`。

### 2.2 基本类型 vs 引用类型：== 与 equals

```java
int a = 100;
int b = 100;
System.out.println(a == b);        // true，基本类型比较的是值

String s1 = new String("abc");
String s2 = new String("abc");
System.out.println(s1 == s2);      // false，引用类型 == 比较的是地址
System.out.println(s1.equals(s2)); // true，equals 比较的是内容
```

规则只有一条：**`==` 比较基本类型的值；比较引用类型时只比较“是否指向同一个对象”**。要比较对象内容必须用 `equals`，而自定义类要比较内容就必须重写 `equals`（见“Object 与 String”章）。

### 2.3 包装类与自动装箱、拆箱

每个基本类型都有对应的包装类：`Byte`、`Short`、`Integer`、`Long`、`Float`、`Double`、`Character`、`Boolean`。

```java
Integer i = 100;     // 自动装箱：等价于 Integer.valueOf(100)
int n = i;           // 自动拆箱：等价于 i.intValue()
```

包装类有两个高频考点：

**1. 缓存池**。`Integer`、`Long`、`Short`、`Byte` 默认缓存 -128~127，`Character` 缓存 0~127，`Boolean` 只有 true/false。`Integer` 缓存上限可用 `-XX:AutoBoxCacheMax` 调整。`valueOf` 优先返回缓存对象，`new Integer()` 一定创建新对象（JDK 9 起该构造器已废弃）。

```java
Integer a = 100, b = 100;
System.out.println(a == b);  // true，命中缓存

Integer c = 200, d = 200;
System.out.println(c == d);  // false，超出缓存范围，是两个对象
```

**2. 拆箱空指针**。

```java
Integer x = null;
int y = x;   // 抛 NullPointerException：拆箱时调用 x.intValue()
```

比较包装类一律用 `equals` 或拆成基本类型后再比，不要用 `==` 赌缓存范围。`Integer` 与 `int` 混用时 `==` 会触发自动拆箱，所以 `new Integer(100) == 100` 为 true。

### 2.4 final、static 与访问修饰符

| 修饰符 | 修饰类 | 修饰方法 | 修饰变量 |
|---|---|---|---|
| `final` | 不可被继承 | 不可被重写 | 引用不可变（对象内容仍可变） |
| `static` | 只能修饰内部类（静态内部类） | 属于类，不依赖实例 | 属于类，只有一份 |
| `abstract` | 抽象类，不可实例化 | 抽象方法，只有声明 | 不可用 |

```java
final class Config { }          // 不能被继承

class User {
    final int id;               // 初始化后不可再赋值
    static int count;           // 所有实例共享

    static void reset() { }     // 类方法，通过 类名.方法名 调用
}
```

访问修饰符控制可见性，从宽到窄：

| 修饰符 | 同类 | 同包 | 子类 | 任意 |
|---|---|---|---|---|
| `public` | 是 | 是 | 是 | 是 |
| `protected` | 是 | 是 | 是 | 否 |
| 默认（包私有） | 是 | 是 | 否 | 否 |
| `private` | 是 | 否 | 否 | 否 |

注意：`protected` 的“子类可访问”指的是子类内部通过继承访问，不是说子类能访问父类实例的 protected 字段。

### 2.5 运算符与类型转换

- **类型提升**：运算时 `byte`/`short`/`char` 先提升为 `int`，所以 `byte a = 1; byte b = a + a;` 编译报错，要写成 `byte b = (byte)(a + a);`。
- **隐式转换**：小范围向大范围自动转（`int → long → float → double`）；`long → float` 精度可能丢失但语法允许。
- **强制转换**：大范围向小范围可能截断：`int x = 130; byte y = (byte)x;` 结果是 -126。
- **短路运算**：`&&`、`||` 左侧能决定结果时不再计算右侧；`&`、`|` 不短路。
- **位运算**：`&` 按位与、`|` 按位或、`^` 异或、`~` 取反；`<<` 左移补零、`>>` 右移保留符号位、`>>>` 无符号右移补零。`int` 移位距离按 32 取模，`long` 按 64 取模。
- **溢出**：`Integer.MAX_VALUE + 1` 会回绕成 `Integer.MIN_VALUE` 且不抛异常；需要检测溢出时用 `Math.addExact`、`Math.multiplyExact`（溢出抛 `ArithmeticException`）。
- **三目运算**：`条件 ? 表达式1 : 表达式2`，两分支类型不一致时可能发生隐式转换，例如 `Object o = flag ? 1 : 2.0;` 结果是 `Double`。

### 2.6 面试追问

- 问：`Integer a = 200; Integer b = 200; a == b` 结果？
- 答：false。`200` 超出 -128~127 缓存范围，`valueOf` 创建两个不同对象。
- 问：自动装箱拆箱的原理？
- 答：装箱调用包装类的 `valueOf`，拆箱调用 `intValue` 等 xxxValue 方法；拆箱 null 会抛 NPE。
- 问：`short s1 = 1; s1 = s1 + 1;` 能否编译？
- 答：不能。`s1 + 1` 提升为 `int`，需要强制转换；`s1 += 1` 可以，因为复合赋值隐含强制转换。
- 问：`final` 修饰的引用能修改对象内容吗？
- 答：能。`final` 只保证引用不再指向别的对象，不保证对象内部状态不变。

## 3. 面向对象三大特性

封装、继承、多态是 Java 的三大特性，面试常考“重写规则”“抽象类与接口区别”“初始化顺序”三个点，这一章全部覆盖。

### 3.1 封装

封装是用访问修饰符把内部状态藏起来，只暴露必要的方法：

```java
public class BankAccount {
    private long balance;          // 内部状态对外不可见

    public void deposit(long amount) {
        if (amount <= 0) throw new IllegalArgumentException("金额必须为正");
        this.balance += amount;    // 通过方法约束状态变化
    }
}
```

好处：状态变化可控、实现可替换、降低耦合。命名上使用 getter/setter 是惯例，不是语法要求。

### 3.2 继承

Java 类只允许**单继承**（一个类只能有一个父类），但可以**多实现接口**。子类自动拥有父类的非 private 成员，并通过 `super` 调用父类构造器或方法。

```java
public class Animal {
    protected String name;
    public Animal(String name) { this.name = name; }
    public void speak() { System.out.println("..."); }
}

public class Dog extends Animal {
    public Dog(String name) { super(name); }   // 必须先调用父类构造器
    @Override
    public void speak() { System.out.println(name + " 汪汪"); }
}
```

继承的注意点：

- 子类构造器第一行必须调用 `super(...)` 或 `this(...)`；都没写时编译器隐式调用父类无参构造器，父类没有无参构造器就会编译报错。
- `private` 成员不继承，`final` 方法不可重写，`final` 类不可继承。
- 能用组合就不要滥用继承：继承暴露了父类实现，容易造成脆弱的基类问题；“is-a”关系才适合继承，“has-a”关系用组合。

### 3.3 多态：重载与重写

**重载（Overload）** 发生在同一类中，方法名相同、参数列表不同，与返回类型无关；在编译期根据参数静态决定调用哪个方法。

**重写（Override）** 发生在父子类之间，方法签名相同，运行时根据对象实际类型动态绑定。

```java
Animal a = new Dog("旺财");
a.speak();   // 编译期看 Animal，运行期调 Dog.speak()，输出“旺财 汪汪”
```

重写必须满足四条规则：

1. 方法名、参数列表必须完全一致；
2. 返回类型相同或为其子类型（协变返回）；
3. 访问权限不能比父类更严格（`protected` 不能被改成 `private`）；
4. 不能抛出比父类更宽泛的受检异常。

静态方法可以被“隐藏”但不能被重写；`private`/`final` 方法也不能被重写。重载解析优先级：精确匹配 → 自动类型提升 → 装箱 → 可变参数，逐级降级。

### 3.4 抽象类与接口

| 对比项 | 抽象类 | 接口 |
|---|---|---|
| 关键字 | `abstract class` | `interface` |
| 继承方式 | 单继承 | 可多实现、可多继承（接口继承接口） |
| 构造器 | 有 | 无 |
| 实例字段 | 可以有 | 只能有 `public static final` 常量 |
| 方法 | 抽象方法 + 具体方法 | JDK 8 起 default/static，JDK 9 起 private |
| 设计语义 | “是什么”的模板 | “能做什么”的能力契约 |

```java
public abstract class Shape {
    protected String color;
    public abstract double area();          // 抽象方法，子类必须实现
    public String describe() { return color + "图形"; }
}

public interface Runnable2 {
    void run();                              // 抽象方法
    default void log() { }                   // JDK 8：默认方法，实现类可覆写
    static String kind() { return "R"; }     // JDK 8：静态方法，接口名调用
}
```

什么时候用谁：要共享状态或模板逻辑（如模板方法模式）用抽象类；要定义“能力契约”且允许多重身份（如一个类既能 `Runnable` 又能 `Serializable`）用接口。现代设计更倾向于接口 + 组合。

接口默认方法的冲突规则（钻石问题）：一个类同时实现两个接口，且两个接口存在**同名同参**的 default 方法时，实现类必须重写该方法消除冲突；若一个接口继承自另一个，子接口的 default 方法优先。

### 3.5 初始化顺序

创建一个子类对象时，初始化顺序是：

```text
父类静态变量/静态块（按声明顺序） → 子类静态变量/静态块 → main
→ new 对象：父类实例变量/实例块 → 父类构造器 → 子类实例变量/实例块 → 子类构造器
```

```java
class Parent {
    static { System.out.print("P-static "); }
    { System.out.print("P-instance "); }
    Parent() { System.out.print("P-ctor "); }
}
class Child extends Parent {
    static { System.out.print("C-static "); }
    { System.out.print("C-instance "); }
    Child() { System.out.print("C-ctor "); }
}
// new Child() 输出：P-static C-static P-instance P-ctor C-instance C-ctor
```

静态初始化只在类首次被加载时执行一次，与创建多少个对象无关。

### 3.6 内部类

内部类有四种：

| 类型 | 特点 | 典型用途 |
|---|---|---|
| 静态内部类 | 不持有外部类引用，可独立创建 | 与外部类逻辑相关的辅助类 |
| 成员内部类 | 隐式持有外部类引用，`Outer.this` 访问外部 | 需要访问外部实例状态 |
| 局部内部类 | 定义在方法内，作用域限方法 | 极少用 |
| 匿名内部类 | 没有名字，一次创建并实现接口/继承类 | 回调、事件监听；Java 8 后多被 Lambda 替代 |

关键坑：匿名/局部内部类访问方法局部变量时，该变量必须是 `final` 或 **effectively final**（初始化后不再重新赋值）。原因：内部类会复制局部变量的副本，两份变量必须保证一致。

```java
public class Outer {
    private int x = 1;
    class Inner {
        int read() { return x; }       // 成员内部类通过 Outer.this.x 访问
    }
    static class StaticInner { }

    Runnable make() {
        int y = 2;                      // effectively final
        return () -> System.out.println(x + y);  // Lambda 也能捕获
    }
}
```

### 3.7 枚举 enum：一组有名字的常量

`enum` 是 Java 5 引入的特殊类，编译器会把 `OrderStatus` 变成继承 `java.lang.Enum` 的 final 类，每个枚举常量就是该类的一个静态 final 实例。

```java
public enum OrderStatus {
    CREATED, PAID, SHIPPED, DONE
}

OrderStatus s = OrderStatus.valueOf("PAID");     // 按名字取，找不到抛 IllegalArgumentException
OrderStatus[] all = OrderStatus.values();        // 按声明顺序返回全部常量
int order = OrderStatus.SHIPPED.ordinal();       // 声明序号，从 0 开始
```

枚举可以与 switch 配合，也可以带字段、构造器和方法：

```java
public enum Level {
    LOW(1), MEDIUM(2), HIGH(3);                  // 必须先声明常量，再写字段和方法

    private final int score;
    Level(int score) { this.score = score; }
    public int score() { return score; }
}

switch (level) {
    case LOW -> System.out.println("低");
    case MEDIUM -> System.out.println("中");
    case HIGH -> System.out.println("高");
}
```

要点：

- 枚举天然是单例，单例模式最简单可靠的写法就是“只有一个常量的枚举”；
- `EnumMap`/`EnumSet` 是专为枚举设计的高性能容器（见第 7 章），底层用数组，比 HashMap 更快；
- 构造器默认私有，不允许外部 new；枚举常量全局唯一，比较直接用 `==`。

### 3.8 面试追问

- 问：重写和重载的区别？
- 答：重载是同名不同参、编译期静态分派；重写是父子类同签名、运行期动态绑定，且返回类型、访问权限、异常范围有约束。
- 问：接口能实例化吗？为什么接口中可以有实现？
- 答：接口不能实例化。JDK 8 起接口可以有 default/static 方法，JDK 9 起可以有 private 方法，用于在接口内复用代码，但不改变“接口定义能力”的本质。
- 问：子类构造器可以不调用父类构造器吗？
- 答：语法上可以不写，但编译器会隐式调用父类无参构造器；父类没有无参构造器时必须显式 `super(参数)`。
- 问：为什么局部内部类访问的局部变量要求 effectively final？
- 答：内部类持有变量的副本，若原变量再被赋值，两份值会不一致；限制变量不可变来保证语义一致。

## 4. Object、equals/hashCode 与 String

所有类的祖先都是 `Object`，而 `String` 是 Java 里使用频率最高的类，也是面试最爱深挖的类。这一章讲透两者的底层机制。

### 4.1 Object 的方法总览

| 方法 | 作用 | 注意 |
|---|---|---|
| `equals(Object)` | 内容相等比较 | 默认是引用比较，需重写 |
| `hashCode()` | 返回散列值 | 与 equals 有契约关系 |
| `toString()` | 字符串表示 | 默认是 `类名@hashCode` |
| `getClass()` | 返回运行时 Class | 泛型擦除后取真实类型 |
| `clone()` | 浅拷贝 | protected native，需实现 Cloneable；深拷贝见下方说明 |
| `wait()/notify()/notifyAll()` | 线程等待/唤醒 | 必须在 synchronized 块内，见并发课程 |
| `finalize()` | 对象回收前回调 | JDK 9 起弃用，不要使用 |

`clone()` 默认是**浅拷贝**：引用字段只复制引用，不复制被引用对象。需要深拷贝时，要么在 `clone()` 里手动复制每个可变字段，要么用序列化拷贝（实现 `Serializable` 后写字节再读回），或用拷贝构造器/工厂方法。

### 4.2 equals 的五条契约

重写 `equals` 必须满足：

1. **自反**：`x.equals(x)` 为 true；
2. **对称**：`x.equals(y)` 与 `y.equals(x)` 结果一致；
3. **传递**：`x.equals(y)`、`y.equals(z)` 为 true 时，`x.equals(z)` 必为 true；
4. **一致**：对象未修改时，多次调用结果一致；
5. **非空性**：`x.equals(null)` 为 false。

标准写法（IDEA 可自动生成）：

```java
@Override
public boolean equals(Object o) {
    if (this == o) return true;
    if (o == null || getClass() != o.getClass()) return false;
    User user = (User) o;
    return id == user.id && name.equals(user.name);
}
```

用 `getClass() != o.getClass()` 而不是 `instanceof`，可以避免子类与父类互相 equals 破坏对称性（如 `Person` 和 `Student` 用 instanceof 时可能双向为 true，但反过来比较结果不一致）。

### 4.3 hashCode 契约

- 两个对象 `equals` 相等，`hashCode` **必须**相等；
- 两个对象 `hashCode` 不等，`equals` **必然**不等（逆否命题）；
- 两个对象 `hashCode` 相等，`equals` 可能不等（哈希碰撞，合法）。

这就是“重写 equals 必须重写 hashCode”的原因：HashMap 等散列容器先用 hashCode 定位桶，再用 equals 精确比较；桶里是 hashCode 相等但内容不同的对象，equals 就会返回 false，导致 `map.get(key)` 取不到值。

```java
@Override
public int hashCode() {
    return Objects.hash(id, name);   // 内部使用 31 作为乘数
}
```

为什么常用 31：它是奇素数，`31 * h + value` 在编译器里可优化为 `(h << 5) - h`，碰撞率低且计算快。

### 4.4 String 的不可变性与常量池

`String` 被 `final` 修饰，且 JDK 8 内部用 `char[]` 存储、JDK 9 起改用 `byte[] + coder`（紧凑字符串，Latin-1 字符只占 1 字节）。所有修改方法都返回新字符串，原对象不变。

**为什么 String 要不可变**：

1. **缓存安全**：字符串常量池、HashMap 的 key 依赖 hashCode，可变会导致散列失效；
2. **线程安全**：不可变对象天然可共享，无需同步；
3. **安全**：类加载器、网络地址、文件路径等敏感字符串不会被意外篡改；
4. **性能**：常量池复用，避免重复创建。

**字符串常量池（String Pool）**：

- JDK 7 之前位于方法区（PermGen），JDK 7 起移入堆；
- 编译期字面量 `"abc"` 会入池；`new String("abc")` 在堆上新建对象，不改变池中内容；
- `intern()` 方法把字符串加入池并返回池中的引用。

```java
String s1 = "abc";                 // 常量池中创建/复用
String s2 = new String("abc");     // 堆上新建对象
System.out.println(s1 == s2);      // false
System.out.println(s1 == s2.intern()); // true，intern 返回池中引用

String s3 = "a" + "b";             // 编译期常量折叠，等价于 "ab"
String s4 = "ab";
System.out.println(s3 == s4);      // true
```

高频题：`new String("abc")` 创建几个对象？

- 若常量池中没有 `"abc"`：创建 2 个（常量池的 `"abc"` + 堆上的 String 对象；实际还可能包含 `char[]`，可视为 2 个主要对象）；
- 若常量池已有 `"abc"`：只创建 1 个堆对象。

拼接细节：JDK 8 的 javac 会把变量拼接编译成 `StringBuilder.append`；JDK 9 起改用 `invokedynamic` + `StringConcatFactory`，但“每次拼接创建新对象”的本质不变，循环内拼接仍应手写 `StringBuilder`。

### 4.5 StringBuilder 与 StringBuffer

| 对比项 | String | StringBuilder | StringBuffer |
|---|---|---|---|
| 可变 | 否 | 是 | 是 |
| 线程安全 | 是（不可变） | 否 | 是（方法加 synchronized） |
| 性能 | 拼接最慢 | 最快 | 居中 |
| 适用 | 常量/少量拼接 | 单线程大量拼接 | 多线程共享同一对象 |

```java
StringBuilder sb = new StringBuilder();
for (int i = 0; i < 1000; i++) {
    sb.append(i);          // 原地修改，不产生中间对象
}
String result = sb.toString();
```

容量细节：`new StringBuilder()` 默认容量 16，容量不足时按“旧容量 × 2 + 2”扩容（`AbstractStringBuilder` 的 grow 逻辑）；能预估大小时用 `new StringBuilder(initialCapacity)` 预分配，减少扩容复制。

### 4.6 面试追问

- 问：为什么重写 equals 必须重写 hashCode？
- 答：散列容器先用 hashCode 定位桶再用 equals 比较；违反契约会导致相同内容的对象放进不同桶，get 不到。
- 问：`String s = new String("abc")` 创建了几个对象？
- 答：取决于常量池是否已有 `"abc"`：没有则 2 个，已有则 1 个堆对象。
- 问：`intern()` 的作用？
- 答：把字符串加入常量池（若不在）并返回池中引用，可用于减少重复字符串占用的内存。
- 问：String、StringBuilder、StringBuffer 怎么选？
- 答：不变内容用 String，单线程拼接用 StringBuilder，多线程共享可变字符串用 StringBuffer。
- 问：String 为什么设计成不可变？
- 答：常量池与散列缓存安全、天然线程安全、安全敏感场景防篡改、池化提升性能。

## 5. 集合框架总览与 List 家族

集合是 Java 使用频率最高、面试挖得最深的类库。先建立整体体系，再逐个读源码，这是大厂要求的“源码驱动”式学习。

### 5.1 集合体系总览

```mermaid
flowchart TD
    subgraph Collection 体系
        C[Collection] --> L[List]
        C --> S[Set]
        C --> Q[Queue]
        L --> AL[ArrayList]
        L --> LL[LinkedList]
        S --> HS[HashSet]
        S --> TS[TreeSet]
        Q --> AD[ArrayDeque]
    end
    subgraph Map 体系
        M[Map] --> HM[HashMap]
        M --> TM[TreeMap]
        M --> LHM[LinkedHashMap]
        M --> CHM[ConcurrentHashMap]
    end
```

- **Collection** 是单列集合的根接口，下面分 `List`（有序可重复）、`Set`（不可重复）、`Queue`（队列）；
- **Map** 是双列集合，存键值对，与 Collection 是并列的两大体系；
- 集合里存的是**对象引用**，基本类型会自动装箱；`Set` 的去重依赖 `equals` 与 `hashCode`（见“Object 与 String”章）。

### 5.2 ArrayList 源码精读

`ArrayList` 底层是 `Object[]` 数组，支持随机访问。

**扩容机制**：

1. 无参构造只创建一个空数组，**第一次 add 时才扩容到默认容量 10**（懒加载）；
2. 容量不够时 `grow()`：`newCapacity = oldCapacity + (oldCapacity >> 1)`，即 **1.5 倍**；
3. 若 1.5 倍仍小于需求容量，直接扩容到需求容量；
4. 复制使用 `Arrays.copyOf`（底层 `System.arraycopy`，native 方法）；
5. 最大容量约 `Integer.MAX_VALUE - 8`。

```java
ArrayList<Integer> list = new ArrayList<>();   // 此时容量 0
for (int i = 0; i < 11; i++) list.add(i);      // 第一次 add 扩到 10，第 11 个元素再扩到 15
```

**增删复杂度**：末尾 add 均摊 $O(1)$（扩容偶尔发生）；指定位置 add/remove 需要移动元素，$O(n)$；`get(i)` 直接按下标访问，$O(1)$。

**modCount 与 fail-fast**：每次结构修改（add/remove/clear）都会 `modCount++`。迭代器创建时记录 `expectedModCount`，迭代中检测到不一致就抛 `ConcurrentModificationException`，防止多线程或遍历中修改造成不可预期的结果。

**subList 是视图**：`list.subList(1, 3)` 返回的是原列表的视图，修改它会反映到原列表；在视图上结构性修改会导致原列表的 modCount 变化，再操作原列表可能抛异常。

### 5.3 LinkedList 源码精读

`LinkedList` 底层是**双向链表**：每个节点持有 `prev`、`item`、`next` 三个引用。

- 头尾 add/remove 是 $O(1)$；按下标 `get(i)`/`add(i)` 需要从头或尾开始遍历，$O(n)$；
- 实现了 `List` 和 `Deque`，可当栈、队列、双端队列用；
- 每个节点还要存前后指针，**内存占用比 ArrayList 大**，且节点在堆上分散，缓存局部性差；
- 面试结论：数据量小、以遍历为主时 ArrayList 更优；频繁在头部插入删除才考虑 LinkedList。

### 5.4 Vector、Stack 与 ArrayDeque

- `Vector` 的方法用 `synchronized` 修饰，线程安全但性能差；扩容默认 2 倍（可指定 `capacityIncrement`）。JDK 1.2 起就被建议用 ArrayList 替代，只在遗留代码中出现。
- `Stack` 继承 Vector，用它的 `addElement`/`removeElementAt`/`elementAt` 实现栈操作，整表同步，历史包袱重，官方建议用 `ArrayDeque`。
- `ArrayDeque` 底层是循环数组，push/pop/offer/poll 均为 $O(1)$，**不允许 null**；作为栈/队列是首选。

```java
Deque<Integer> stack = new ArrayDeque<>();
stack.push(1); stack.push(2);
System.out.println(stack.pop());   // 2
```

### 5.5 Arrays.asList 与 List.of 的坑

```java
List<String> list = Arrays.asList("a", "b");
list.add("c");   // 抛 UnsupportedOperationException：Arrays.asList 返回固定大小列表
list.set(0, "x"); // 可以，修改会同步到原数组

List<String> list2 = List.of("a", "b");  // JDK 9+，完全不可变
list2.set(0, "x");  // 抛 UnsupportedOperationException
```

`Arrays.asList` 返回的是 `java.util.Arrays$ArrayList`（内部数组），不是 `java.util.ArrayList`，只能替换元素不能增删。`List.of`/`Map.of`/`Set.of` 返回不可变集合，任何修改都抛异常；它们也**不允许 null 元素**，传入 null 会抛 NullPointerException。

### 5.6 遍历时删除的正确姿势

```java
// 错误：for-each 中调用 list.remove，迭代器检查 modCount 失败
// for (String s : list) { if (s.equals("a")) list.remove(s); }

// 正确 1：迭代器 remove
Iterator<String> it = list.iterator();
while (it.hasNext()) {
    if (it.next().equals("a")) it.remove();
}

// 正确 2：JDK 8 removeIf
list.removeIf(s -> s.equals("a"));

// 正确 3：倒序 for 循环按索引删除
for (int i = list.size() - 1; i >= 0; i--) {
    if (list.get(i).equals("a")) list.remove(i);
}
```

**fail-fast vs fail-safe**：ArrayList/HashMap 的迭代器是 fail-fast（快速失败，结构变化立即抛异常）；`CopyOnWriteArrayList`、`ConcurrentHashMap` 等并发容器的迭代器基于快照或弱一致语义，迭代过程中修改不会抛异常（fail-safe），但也不保证看到最新数据。

### 5.7 List 家族对比表

| 对比项 | ArrayList | LinkedList | Vector |
|---|---|---|---|
| 底层结构 | Object 数组 | 双向链表 | Object 数组 |
| 随机访问 get(i) | $O(1)$ | $O(n)$ | $O(1)$ |
| 头尾插入删除 | 头 $O(n)$，尾均摊 $O(1)$ | $O(1)$ | 同 ArrayList |
| 中间插入删除 | $O(n)$ | $O(n)$（先找再改） | $O(n)$ |
| 扩容 | 1.5 倍 | 无 | 2 倍 |
| 线程安全 | 否 | 否 | 是（方法级同步） |
| 内存 | 连续数组，占用少 | 每节点多两个指针 | 连续数组 |

### 5.8 PriorityQueue：二叉堆

`PriorityQueue` 底层是二叉堆（用数组存储），默认**小顶堆**（堆顶最小）：

- `offer`/`poll` 入堆、出堆 $O(\log n)$，`peek` 看堆顶 $O(1)$；
- 用集合构造时采用堆化，整体构建 $O(n)$；
- 传 `Comparator` 可改顺序，`new PriorityQueue<>(Comparator.reverseOrder())` 就是大顶堆；
- **不允许 null**，线程不安全；并发场景用 `PriorityBlockingQueue`（并发课程展开）；
- 容量不足时按策略扩容：容量小于 64 时近乎翻倍，否则 1.5 倍；
- 典型用途：Top K、任务调度、合并 K 个有序流（与 Hot 100 的堆专题直接衔接）。

```java
PriorityQueue<Integer> pq = new PriorityQueue<>();
pq.offer(3); pq.offer(1); pq.offer(2);
System.out.println(pq.poll());   // 1，小顶堆先出最小
```

### 5.9 面试追问

- 问：ArrayList 和 LinkedList 的区别？
- 答：底层数组 vs 双向链表；随机访问 $O(1)$ vs $O(n)$；尾插均摊 $O(1)$，头插 LinkedList 更优；内存模型不同。
- 问：ArrayList 扩容多少倍？为什么是 1.5 倍？
- 答：`old + (old >> 1)`，即 1.5 倍；扩容要复制整个数组，倍率过小频繁复制、过大浪费内存，1.5 是时间与空间的折中。
- 问：为什么遍历时用集合自身的 remove 会抛 ConcurrentModificationException？
- 答：迭代器持有 `expectedModCount`，集合结构修改会使 `modCount` 变化，迭代器下一次校验不一致即快速失败。
- 问：`Arrays.asList` 和 `List.of` 有什么区别？
- 答：前者是数组视图、定长可变元素；后者是完全不可变集合（JDK 9+）。

## 6. HashMap 源码精读

HashMap 是 Java 面试的“必考之王”：存储结构、hash 计算、put 流程、扩容、红黑树转换、线程安全，每一环都会被追问。这一章按“结构 → 流程 → 为什么”三层讲透。

### 6.1 底层结构

JDK 8 起 HashMap 是**数组 + 链表 + 红黑树**：

```text
table: Node[] 数组，每个槽位叫“桶”(bucket)
桶内: 链表（Node）或红黑树（TreeNode）
```

数组长度默认 16；当桶内链表过长（阈值 8）且数组长度不小于 64 时，链表转红黑树，把最坏查找从 $O(n)$ 降到 $O(\log n)$。

### 6.2 关键常量

| 常量 | 值 | 含义 |
|---|---|---|
| `DEFAULT_INITIAL_CAPACITY` | 1 << 4 = 16 | 默认初始容量 |
| `MAXIMUM_CAPACITY` | 1 << 30 | 最大容量 |
| `DEFAULT_LOAD_FACTOR` | 0.75f | 默认负载因子 |
| `TREEIFY_THRESHOLD` | 8 | 链表长度达到 8 尝试转树 |
| `UNTREEIFY_THRESHOLD` | 6 | 扩容拆分后节点数 ≤ 6 转回链表 |
| `MIN_TREEIFY_CAPACITY` | 64 | 转树要求的最小数组长度 |

**懒初始化**：无参构造只设置 `loadFactor`，不创建数组；第一次 `put` 时才在 `resize()` 中创建长度为 16 的 table。

**容量与阈值**：`threshold = capacity × loadFactor`，默认 16 × 0.75 = 12。元素个数 `size` 超过 threshold 时扩容。指定初始容量时，构造器调用 `tableSizeFor()` 把容量向上取整为 2 的幂，并暂存到 threshold，真正建表发生在首次 resize。

### 6.3 hash 计算与寻址

```java
static final int hash(Object key) {
    int h;
    return (key == null) ? 0 : (h = key.hashCode()) ^ (h >>> 16);
}
```

- key 为 null 时 hash 为 0，所以 null key 固定落在 table[0]；
- 扰动函数：把 hashCode 的高 16 位与低 16 位异或，让高位信息参与低位计算，减少碰撞；
- 桶下标：`(n - 1) & hash`。n 是 2 的幂时等价于 `hash % n`，但位运算更快且结果非负。

### 6.4 put 流程

```mermaid
flowchart TD
    start[put key,value] --> h[计算 hash<br/>key.hashCode 扰动]
    h --> tab{table 为空?}
    tab -->|是| init[resize 初始化]
    tab -->|否| idx[按 n-1 与 hash 定位桶]
    init --> idx
    idx --> empty{桶为空?}
    empty -->|是| put[直接放入新节点]
    empty -->|否| tree{桶是红黑树?}
    tree -->|是| putTree[放入红黑树]
    tree -->|否| list[遍历链表]
    list --> eq{key 已存在?}
    eq -->|是| replace[覆盖 value]
    eq -->|否| tail[尾插新节点<br/>长度达 8 触发 treeifyBin]
    put --> after[modCount++ size++]
    putTree --> after
    replace --> after
    tail --> after
    after --> chk{size 大于 threshold?}
    chk -->|是| resize[resize 扩容]
    chk -->|否| end1[结束]
    resize --> end1
```

简化源码（JDK 8 逻辑）：

```java
final V putVal(int hash, K key, V value, boolean onlyIfAbsent, boolean evict) {
    Node<K,V>[] tab; Node<K,V> p; int n, i;
    if ((tab = table) == null || (n = tab.length) == 0)
        n = (tab = resize()).length;              // 懒初始化
    if ((p = tab[i = (n - 1) & hash]) == null)
        tab[i] = newNode(hash, key, value, null); // 桶空，直接放
    else {
        Node<K,V> e; K k;
        if (p.hash == hash && ((k = p.key) == key || (key != null && key.equals(k))))
            e = p;                                 // 首节点 key 相同
        else if (p instanceof TreeNode)
            e = ((TreeNode<K,V>) p).putTreeVal(this, tab, hash, key, value);
        else {
            for (int binCount = 0; ; ++binCount) {
                if ((e = p.next) == null) {
                    p.next = newNode(hash, key, value, null);  // 尾插
                    if (binCount >= TREEIFY_THRESHOLD - 1)
                        treeifyBin(tab, hash);     // 长度达 8，尝试转树
                    break;
                }
                if (e.hash == hash && ((k = e.key) == key || (key != null && key.equals(k))))
                    break;
                p = e;
            }
        }
        if (e != null) {
            V oldValue = e.value;
            e.value = value;                       // key 已存在，覆盖
            return oldValue;
        }
    }
    ++modCount;
    if (++size > threshold) resize();
    return null;
}
```

要点：JDK 8 采用**尾插法**（新节点挂链表尾部），JDK 7 是**头插法**；头插在并发扩容时可能形成环形链表，导致 get 死循环，JDK 8 改为尾插后不再出现该问题（但并发仍不安全）。

### 6.5 get 流程

```text
计算 hash → (n-1)&hash 定位桶 → 桶空返回 null
→ 首节点 key 命中直接返回 → 是树则树中查找 → 否则遍历链表
```

比较条件永远是 `hash 相等 && (引用相同 || equals 相等)`，这就是自定义 key 必须重写 `equals` 和 `hashCode` 的原因。

### 6.6 resize 扩容

扩容发生在两种时机：

1. 首次 put 建表（容量 16，阈值 12）；
2. `size > threshold` 时，容量翻倍、阈值翻倍。

扩容过程：

1. 创建长度为 2 倍的新数组；
2. 迁移每个桶：
   - 单节点：按 `hash & (newCap - 1)` 重新定位；
   - 链表：根据 `(e.hash & oldCap) == 0` 拆成两条，等于 0 的留在**原下标**，否则移到**原下标 + oldCap**；
   - 红黑树：`split()` 拆成两棵子树，节点数 ≤ 6 的子树转回链表。

关键优化：因为容量总是 2 的幂，扩容后元素要么在原位、要么在原位加旧容量，不需要重新计算 hash，并且 JDK 8 尾插保持了链表相对顺序。

### 6.7 为什么转红黑树，阈值为什么是 8 和 6

- 极端坏数据下所有 key 挤进同一桶，链表查找退化为 $O(n)$；红黑树保证 $O(\log n)$；
- 阈值 8 来自泊松分布：负载因子 0.75、哈希均匀的理想情况下，桶内出现 8 个节点的概率约为 6e-8，基本不可能自然发生；出现 8 往往意味着 hashCode 很差，转树用于抵御恶意构造；
- 树转回链表的阈值是 6，与 8 之间留 2 的缓冲，避免元素在 7、8 之间反复横跳触发频繁转换；
- 转树前必须满足数组长度 ≥ 64，否则先扩容（扩容能让元素分散，比直接转树更划算）。
- 转树有内存代价：`TreeNode` 比普通 `Node` 多 parent/left/right/prev/red 等字段，内存约为 2 倍，所以只在桶足够长时才转，短链表用树反而更慢更占内存。

### 6.8 为什么容量必须是 2 的幂

1. 下标计算 `(n - 1) & hash` 只有在 n 为 2 的幂时才等价于取模，且更快；
2. 扩容时只需看 `hash & oldCap` 是 0 还是 1，就能决定元素留在原位还是搬到“原下标 + oldCap”，无需重新散列；
3. `tableSizeFor()` 负责把传入的初始容量向上取整为 2 的幂：`new HashMap<>(10)` 实际容量是 16。

### 6.9 HashMap 的线程安全问题

HashMap 不是线程安全的，并发 put 可能：

- **数据覆盖**：两个线程同时命中空桶，各自写入，后写者覆盖先写者；
- **size 计数丢失**：`++size` 非原子；
- JDK 7 并发扩容可能形成环形链表，get 死循环；JDK 8 改为尾插后不再死循环，但覆盖与丢失问题仍在。

并发场景的替代：

| 方案 | 说明 |
|---|---|
| `Hashtable` | 全表 synchronized，性能差，基本淘汰 |
| `Collections.synchronizedMap(map)` | 包装类，同样全表锁 |
| `ConcurrentHashMap` | 首选，锁粒度细，见 6.10 |

### 6.10 ConcurrentHashMap 演进

- **JDK 7**：分段锁（Segment），把表分成 16 段，每段一把 ReentrantLock，不同段可并发写；
- **JDK 8**：抛弃分段锁，改为 **CAS + synchronized**：桶为空时用 CAS 放入节点，桶非空时锁住桶头节点；锁粒度从“段”细化到“桶”，并发度更高；
- 读操作无锁（volatile 读 + 弱一致），size 用 CounterCell 数组近似计数。

`ConcurrentHashMap` 不允许 null key/null value（因为并发下无法区分“没有这个 key”和“value 是 null”），与 HashMap 不同。

### 6.11 面试追问

- 问：HashMap 的底层结构？
- 答：JDK 8+ 是数组 + 链表 + 红黑树；链表长度达 8 且数组长度 ≥ 64 时转红黑树。
- 问：put 的完整流程？
- 答：hash 扰动 → (n-1)&hash 定位 → 桶空直接放 / key 相同覆盖 / 树中插入 / 链表尾插 → modCount++ → 超阈值扩容。
- 问：为什么用红黑树而不是二叉搜索树？
- 答：普通二叉搜索树在最坏情况下退化成链表；红黑树自平衡，保证 $O(\log n)$。
- 问：扩容时链表怎么迁移？
- 答：按 `hash & oldCap` 拆成两条链，分别放原下标和“原下标 + oldCap”，不需要重新计算 hash。
- 问：HashMap 为什么不安全？JDK 8 还有死循环问题吗？
- 答：并发 put 会覆盖和丢数据；JDK 8 尾插消除了 JDK 7 头插导致的环形链表死循环，但仍不是线程安全容器。
- 问：如何预估 HashMap 容量？
- 答：期望元素数除以 0.75 再向上取 2 的幂，例如想放 1000 个元素，`new HashMap<>(1000 / 0.75f)` 附近取值，避免频繁扩容。

## 7. 其他 Map 与 Set 家族

HashMap 讲透后，LinkedHashMap、TreeMap 和 Set 家族都是它的“变体”，理解底层再对比差异，就能举一反三。

### 7.1 LinkedHashMap：有序的 HashMap

`LinkedHashMap` 在 HashMap 的数组 + 链表/红黑树之外，额外维护一条**双向链表**记录元素的顺序：

- **插入序**（默认）：按 put 顺序遍历；
- **访问序**：`accessOrder=true` 时，每次 get/put 会把命中的节点移到链表尾部，从而可以按“最近最少使用”淘汰头部。

访问序正是 **LRU 缓存**的实现基础：

```java
class LRUCache<K, V> extends LinkedHashMap<K, V> {
    private final int capacity;

    public LRUCache(int capacity) {
        super(capacity, 0.75f, true);   // accessOrder = true
        this.capacity = capacity;
    }

    @Override
    protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
        return size() > capacity;       // 超过容量时淘汰最久未访问的头部
    }
}
```

面试常问“手写 LRU”，除了继承 LinkedHashMap，还可以用 HashMap + 双向链表自实现，后者更能体现基本功。

### 7.2 TreeMap：有序的 Map

`TreeMap` 底层是**红黑树**，key 必须可比较（实现 `Comparable`）或构造时传入 `Comparator`：

- put/get/remove 均为 $O(\log n)$；
- 支持范围操作：`firstKey()`、`lastKey()`、`ceilingKey()`、`floorKey()`、`subMap()` 等；
- 不允许 null key（无法比较），而 HashMap 允许一个 null key；
- 遍历按 key 的自然顺序或比较器顺序。

```java
Map<String, Integer> map = new TreeMap<>();
map.put("b", 2); map.put("a", 1); map.put("c", 3);
System.out.println(map.keySet());      // [a, b, c]，按字典序
System.out.println(map.ceilingKey("b")); // b
```

需要“按 key 排序、找邻近 key”时用 TreeMap；只需要存取速度时用 HashMap。

### 7.3 Set 家族：Map 的马甲

Set 内部几乎都包装了对应的 Map：

| Set | 底层 | 特点 |
|---|---|---|
| `HashSet` | HashMap | 无序、去重、$O(1)$；元素作为 key，value 是固定对象 |
| `LinkedHashSet` | LinkedHashMap | 去重且保持插入顺序 |
| `TreeSet` | TreeMap（红黑树） | 去重且按自然序/比较器排序，$O(\log n)$ |

```java
Set<String> set = new HashSet<>();
set.add("a"); set.add("a");          // 第二次 add 返回 false
System.out.println(set.size());      // 1
```

去重依据是 `hashCode` + `equals`，所以自定义对象放进 Set 前必须重写这两个方法，否则两个内容相同的对象会被当成不同元素。

### 7.4 Map 的遍历方式

```java
Map<String, Integer> map = new HashMap<>();
map.put("a", 1); map.put("b", 2);

// 1. entrySet（推荐，一次拿 key 和 value）
for (Map.Entry<String, Integer> e : map.entrySet()) {
    System.out.println(e.getKey() + "=" + e.getValue());
}

// 2. keySet + get（两次查找，不推荐大数据量）
for (String key : map.keySet()) {
    System.out.println(key + "=" + map.get(key));
}

// 3. JDK 8 forEach
map.forEach((k, v) -> System.out.println(k + "=" + v));
```

**不要在遍历中修改 Map 结构**（put/remove 非迭代器方式），否则抛 ConcurrentModificationException；需要删除用 `Iterator.remove()` 或 `removeIf`。

### 7.5 其他 Map 简表

| Map | 特点 | 用途 |
|---|---|---|
| `WeakHashMap` | key 用弱引用，GC 后可回收 | 缓存、监听器注册 |
| `IdentityHashMap` | 用引用相等代替 equals 比较 key | 特殊场景，如序列化框架记录对象身份 |
| `EnumMap` | 以枚举为 key，数组实现，性能极高 | 枚举状态映射 |
| `Hashtable` | 全表同步，不允许 null | 遗留代码 |

### 7.6 面试追问

- 问：如何实现一个 LRU 缓存？
- 答：LinkedHashMap 设置 accessOrder=true 并重写 removeEldestEntry；或 HashMap + 双向链表自实现，get 时移动到链表头，满时淘汰链表尾。
- 问：TreeMap 和 HashMap 的区别？
- 答：HashMap 无序 $O(1)$，TreeMap 有序 $O(\log n)$；TreeMap 支持范围查询，key 必须可比较。
- 问：HashSet 为什么能去重？
- 答：底层是 HashMap，元素作为 key；先比 hashCode 定位桶，再用 equals 判断是否重复。
- 问：Map 的 entrySet 和 keySet 有什么区别？
- 答：entrySet 直接遍历键值对，一次访问；keySet 遍历后再 get 需要再次查找，数据量大时更慢。

## 8. 泛型：类型擦除与通配符

泛型把“运行时错误”提前到“编译期错误”，是类型安全的核心机制。面试重点永远是**类型擦除**和**通配符 PECS**。

### 8.1 为什么需要泛型

没有泛型时只能用 Object 容器，取出时必须强转，转错类型到运行期才暴露：

```java
List list = new ArrayList();
list.add("abc");
Integer x = (Integer) list.get(0);   // 编译通过，运行期 ClassCastException
```

使用泛型后：

```java
List<String> list = new ArrayList<>();
list.add("abc");
String x = list.get(0);              // 无需强转，编译期检查类型
```

### 8.2 泛型类、接口与方法

```java
public class Box<T> {                 // 泛型类
    private T value;
    public T get() { return value; }
    public void set(T value) { this.value = value; }

    public static <E> Box<E> of(E e) {   // 泛型方法：<E> 在返回类型前
        Box<E> box = new Box<>();
        box.set(e);
        return box;
    }
}

public interface Comparable<T> {      // 泛型接口
    int compareTo(T o);
}
```

类型参数命名惯例：`T`（Type）、`E`（Element）、`K/V`（Key/Value）、`R`（Return）。

### 8.3 类型擦除

**运行时不存在泛型**。编译器完成类型检查后，会把泛型信息擦除：

- 无界类型参数 `T` 擦除为 `Object`；
- 有界类型参数 `T extends Number` 擦除为上界 `Number`；
- `List<String>` 和 `List<Integer>` 在运行时都是同一个 `List` 类。

```java
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
System.out.println(a.getClass() == b.getClass());  // true，都是 ArrayList

// 不能 instanceof 泛型类型
// if (obj instanceof List<String>) { }   // 编译错误
```

擦除带来的限制：

- 不能用 `new T()`（不知道 T 的构造器）；
- 不能 `new T[10]`（见 8.5）；
- 静态字段/静态方法不能用类级类型参数（静态成员属于类本身，不依赖具体类型）；
- 异常类不能泛型化，`catch` 不能捕获类型参数。

### 8.4 通配符与 PECS

通配符 `?` 解决“泛型不可协变”的问题（`List<String>` 不是 `List<Object>` 的子类型）：

| 写法 | 含义 | 能做什么 |
|---|---|---|
| `List<?>` | 未知类型 | 只能读（读成 Object），不能写 |
| `List<? extends Number>` | 上界：Number 及其子类 | 只能读（读成 Number），不能写 |
| `List<? super Integer>` | 下界：Integer 及其父类 | 可以写 Integer，读只能读成 Object |

记忆口诀 **PECS：Producer Extends，Consumer Super**：

- 要从集合中取数据（生产方），用 `? extends T`；
- 要向集合中放数据（消费方），用 `? super T`；
- 只读不写用 extends，只写不读用 super，读写都有就用具体类型 `T`。

```java
public static void copy(List<? extends Number> src, List<? super Number> dst) {
    for (Number n : src) {     // extends：可以读
        dst.add(n);            // super：可以写
    }
}
```

### 8.5 泛型与数组、重载的冲突

数组是**协变且运行时保留类型**（reified）的，泛型是**不可变且擦除**的，二者天然冲突：

```java
// String[] 是 Object[] 的子类型（数组协变）
Object[] arr = new String[3];

// 泛型数组创建被禁止
// T[] arr = new T[10];                 // 编译错误
// List<String>[] arr = new List<>[10]; // 编译错误

// 解决办法：通过反射创建或使用 List
T[] arr = (T[]) Array.newInstance(clazz, 10);
```

重载冲突：擦除后签名相同的方法不能共存：

```java
// void f(List<String> list) { }
// void f(List<Integer> list) { }   // 编译错误：擦除后都是 void f(List)
```

### 8.6 桥方法与运行时获取类型

擦除时编译器可能生成**桥方法（bridge method）**保持多态。例如父类 `Number get()`，子类 `Integer get()`，擦除后子类的 `Integer get()` 覆盖不了 `Number get()`，编译器会生成一个桥方法 `Number get()` 内部调用 `Integer get()`。

需要拿到运行时真实泛型（如 JSON 反序列化、MyBatis）时：

```java
// 方式 1：类声明里带类型参数，可反射拿到
class MyHandler extends TypeReference<List<String>> { }

// 方式 2：Jackson/MyBatis 常见写法
Type type = new TypeToken<List<String>>() { }.getType();   // Guava
```

原理：`class X extends TypeReference<List<String>>` 这类**泛型父类**的签名信息通过 `getGenericSuperclass()` 保留在字节码里，可以解析出 `List<String>`。

### 8.7 面试追问

- 问：什么是类型擦除？
- 答：编译器检查后把泛型擦除为原始类型或上界，运行时没有泛型信息；`List<String>` 与 `List<Integer>` 是同一个类。
- 问：`? extends T` 和 `? super T` 的区别？
- 答：extends 上界只读，super 下界只写；记忆 PECS。
- 问：为什么不能创建泛型数组？
- 答：数组运行时保留类型且协变，泛型擦除，二者冲突，可能造成 ArrayStoreException 无法拦截的类型混入。
- 问：如何绕过擦除拿到运行时类型？
- 答：通过泛型父类的 `getGenericSuperclass()`/`ParameterizedType`，或显式传入 `Class<T>`。

## 9. 反射与动态代理

反射是“框架的基石”：Spring 的 IoC/AOP、MyBatis 的 Mapper、各种 ORM 和序列化框架，底层都依赖反射或动态代理。面试常问“为什么框架需要反射”“JDK 动态代理为什么必须基于接口”。

### 9.1 获取 Class 对象的三种方式

```java
// 1. 类名.class（不会触发静态初始化）
Class<String> c1 = String.class;

// 2. 实例.getClass()（运行时实际类型）
Class<?> c2 = "hello".getClass();

// 3. Class.forName("全限定名")（默认触发静态初始化）
Class<?> c3 = Class.forName("java.lang.String");
```

注意：`Class.forName` 默认 `initialize=true`，会执行类的静态初始化；JDBC 驱动注册就是利用这个行为。`类名.class` 只完成加载，不触发初始化。

### 9.2 反射常用 API

| API | 作用 |
|---|---|
| `getDeclaredConstructor(...)` / `getConstructor(...)` | 获取构造器（Declared 只能取本类声明的） |
| `getDeclaredField(...)` / `getField(...)` | 获取字段 |
| `getDeclaredMethod(name, 参数类型...)` / `getMethod(...)` | 获取方法 |
| `setAccessible(true)` | 绕过 private 和访问检查 |
| `newInstance()` / `constructor.newInstance(args)` | 创建对象 |
| `field.get/set(obj, value)` | 读写字段 |
| `method.invoke(obj, args)` | 调用方法 |

```java
Class<?> clazz = Class.forName("com.example.User");
Object obj = clazz.getDeclaredConstructor().newInstance();      // 反射创建
Method setName = clazz.getDeclaredMethod("setName", String.class);
setName.invoke(obj, "张三");                                    // 反射调用
Field name = clazz.getDeclaredField("name");
name.setAccessible(true);                                       // 访问私有字段
System.out.println(name.get(obj));
```

### 9.3 强封装与反射安全

JDK 16 起默认**强封装 JDK 内部 API**：反射访问 `jdk.internal` 等模块内部会抛 `InaccessibleObjectException`，需要通过 `--add-opens` 开启。反射仍能访问应用自己的 private 成员（加 `setAccessible(true)`），但它破坏了封装，是最后手段。

反射的性能代价：

- 动态解析方法、类型检查，无法像直接调用那样内联；
- `setAccessible` 本身有安全检查；
- 优化手段：缓存 `Method`/`Field` 对象（不要每次都 get）、批量 `setAccessible`、用 `MethodHandle` 或 `LambdaMetafactory`。

### 9.4 动态代理

**JDK 动态代理**：运行时生成一个实现指定接口的代理类，把方法调用转发给 `InvocationHandler`：

```java
public interface Greeting {
    void sayHello(String name);
}

Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[]{Greeting.class},
        (obj, method, args) -> {
            System.out.println("before: " + method.getName());
            Object result = method.invoke(new GreetingImpl(), args);
            System.out.println("after");
            return result;
        });
proxy.sayHello("世界");
```

**CGLIB 动态代理**：通过生成目标类的子类来代理，**不要求接口**，但不能代理 `final` 类和 `final` 方法。

| 对比项 | JDK Proxy | CGLIB |
|---|---|---|
| 代理原理 | 生成接口实现类 | 生成子类 |
| 是否必须接口 | 是 | 否 |
| final 类/方法 | 无影响 | 不能代理 |
| 性能 | 反射调用 | 生成字节码，调用更快（ASM） |
| 框架现状 | Spring AOP 默认（有接口时） | Spring Boot 2+ 默认强制 CGLIB |

### 9.5 反射与代理的应用场景

- **Spring IoC**：扫描类 → 反射创建 Bean、按注解注入依赖；
- **Spring AOP**：JDK Proxy/CGLIB 生成代理对象，在方法调用前后织入切面逻辑（事务、日志、鉴权）；
- **MyBatis**：`Mapper` 接口没有实现类，通过 JDK 动态代理生成实现，把方法调用翻译成 SQL 执行；
- **序列化/JSON 框架**：Jackson、Gson 反射读写字段；
- **注解处理**：运行时通过反射读取注解（`@Autowired`、`@RequestMapping` 等）决定行为。

### 9.6 面试追问

- 问：什么是反射？为什么框架离不开反射？
- 答：反射允许在运行时获取类信息、创建对象、调用方法。框架在编译期不知道用户会写什么类，只能靠配置（类名）在运行时反射加载和装配。
- 问：new 和反射创建对象的区别？
- 答：new 是编译期确定、直接分配；反射是运行期动态解析，灵活但更慢；框架场景必须用反射。
- 问：JDK 动态代理为什么必须基于接口？
- 答：JDK Proxy 生成的是实现指定接口的代理类，通过接口约束方法集合；没有接口就只能用 CGLIB 生成子类。
- 问：如何提升反射性能？
- 答：缓存 Method/Field、一次 setAccessible、尽量用 MethodHandle。

## 10. 异常体系与最佳实践

异常处理考察的是“工程素养”：能不能说清受检/非受检，知不知道 finally 与 return 的优先级，会不会写 try-with-resources。

### 10.1 Throwable 层级

```mermaid
flowchart TD
    T[Throwable] --> E[Error]
    T --> X[Exception]
    E --> OOM[OutOfMemoryError]
    E --> SO[StackOverflowError]
    X --> R[RuntimeException<br/>非受检异常]
    X --> C[受检异常<br/>IOException 等]
    R --> NPE[NullPointerException]
    R --> IAE[IllegalArgumentException]
    R --> CCE[ClassCastException]
```

### 10.2 Error vs Exception

- **Error**：JVM 层面严重问题，程序无法也不应处理，如 `OutOfMemoryError`、`StackOverflowError`、`NoClassDefFoundError`；不要捕获，捕获也无法恢复；
- **Exception**：程序可处理的问题，分为受检异常和非受检异常。

### 10.3 受检异常 vs 非受检异常

| 对比项 | 受检异常（Checked） | 非受检异常（Unchecked） |
|---|---|---|
| 父类 | Exception（非 RuntimeException） | RuntimeException |
| 是否强制处理 | 必须捕获或 throws 声明 | 不需要 |
| 典型 | IOException、SQLException、FileNotFoundException | NullPointerException、IllegalArgumentException、ClassCastException |
| 设计意图 | 可预期的外部失败，调用方应处理 | 编程错误，修复代码而不是捕获 |

```java
// 受检异常：编译器强制处理
try {
    Files.readString(Path.of("a.txt"));
} catch (IOException e) {
    log.error("读取失败", e);
}

// 非受检异常：不强制，但好的代码仍会校验参数
if (arg == null) throw new IllegalArgumentException("参数不能为空");
```

### 10.4 try-catch-finally 的执行顺序

规则：

1. try 无异常：先执行 try 剩余部分，再执行 finally，然后继续；
2. try 有异常：跳到匹配的 catch，再执行 finally；
3. **finally 一定执行**，除非 JVM 退出（`System.exit`）或线程被杀；
4. **return 的值在进入 finally 之前已经确定**；finally 里的 return 会覆盖 try/catch 的返回值；
5. finally 里抛异常会覆盖 try 的异常（异常丢失）。

```java
static int test() {
    try {
        return 1;
    } finally {
        return 2;      // 覆盖，结果永远是 2
    }
}
```

最佳实践：**不要在 finally 中 return 或抛异常**；finally 只做资源释放等收尾。

### 10.5 try-with-resources

JDK 7 引入，自动关闭实现了 `AutoCloseable` 的资源：

```java
try (FileInputStream in = new FileInputStream("a.txt");
     FileOutputStream out = new FileOutputStream("b.txt")) {
    in.transferTo(out);
} catch (IOException e) {
    log.error("复制失败", e);
}
```

要点：

- 多个资源按**声明逆序**关闭（out 先关，in 后关）；
- 关闭异常会被收集为 **suppressed 异常**，主异常正常抛出，不会像 finally 那样互相覆盖；
- 自定义资源只需实现 `AutoCloseable`（`close()` 抛 Exception）或 `Closeable`（close 抛 IOException）。

### 10.6 自定义异常与最佳实践

```java
public class BusinessException extends RuntimeException {
    private final int code;
    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }
    public int getCode() { return code; }
}
```

工程规范：

1. **不要吞异常**：`catch (Exception e) { }` 空捕获是最大的反模式，至少要记日志；
2. **精确捕获**：优先 catch 具体异常，多个异常用多 catch 而不是一个 Exception；同类处理逻辑的多个异常用竖线合并：`catch (IOException | SQLException e)`；
3. **早抛出、晚捕获**：底层抛详细异常，顶层统一处理并记录上下文；
4. **保留原始异常**：`throw new BusinessException(e)` 时把原异常作为 cause 传入，形成异常链；
5. **不要用异常控制正常流程**：异常抛出的开销远高于 if 判断；
6. 日志用 `log.error("message", e)` 打印完整堆栈，不要只打 `e.getMessage()`。

### 10.7 面试追问

- 问：Error 和 Exception 的区别？
- 答：Error 是 JVM 级不可恢复问题；Exception 是程序可处理的问题。
- 问：受检异常和非受检异常怎么选？
- 答：可预期的外部失败（IO、网络）用受检；编程错误（参数非法、空指针）用 RuntimeException，让调用方自行保证。
- 问：finally 中的 return 会怎样？
- 答：覆盖 try/catch 的返回值；不推荐，会掩盖真实结果。
- 问：try-with-resources 相对 finally 的优势？
- 答：自动按逆序关闭、异常不互相覆盖（suppressed）、代码更简洁。
- 问：final、finally、finalize 的区别？
- 答：final 修饰类/方法/变量；finally 是异常收尾块；finalize 是已弃用的回收前回调。

## 11. IO 流体系与装饰器模式

Java IO 是典型的装饰器模式应用，也是“字节流 vs 字符流”“为什么需要缓冲流”等高频题的来源。

### 11.1 流的概念与分类

**流（Stream）** 是数据的单向通道：输入流读数据，输出流写数据。按处理单位分：

| 分类 | 输入 | 输出 | 处理对象 |
|---|---|---|---|
| 字节流 | `InputStream` | `OutputStream` | 字节（二进制），一切文件 |
| 字符流 | `Reader` | `Writer` | 字符（文本），内部处理编码 |

按功能分：

| 分类 | 说明 | 典型 |
|---|---|---|
| 节点流 | 直接连接数据源 | FileInputStream、FileReader |
| 处理流 | 包装其他流，增强功能 | BufferedInputStream、DataInputStream、ObjectInputStream |

### 11.2 字节流 vs 字符流

- 字节流以 `byte` 为单位，可以处理图片、视频、压缩包等任意二进制；
- 字符流以 `char` 为单位，负责把字节按字符集解码/编码，适合处理文本；
- 字符流内部本质仍是字节流 + 编码转换，所以文本用 Reader/Writer，二进制用 Stream；
- 读取文本建议 `Files.readString()`（JDK 11+）或 BufferedReader 按行读：

```java
// 按行读文本（JDK 11+）
String content = Files.readString(Path.of("a.txt"), StandardCharsets.UTF_8);

// 传统方式
try (BufferedReader reader = Files.newBufferedReader(Path.of("a.txt"))) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

### 11.3 装饰器模式：IO 的核心设计

```java
InputStream in = new BufferedInputStream(new FileInputStream("a.bin"));
```

`FileInputStream` 负责从文件读字节，`BufferedInputStream` 在内存里缓存 8KB，减少系统调用次数。这种“一层包一层、动态叠加能力”的设计就是**装饰器模式**：

- 组件（Component）：`InputStream` 抽象；
- 具体组件（ConcreteComponent）：`FileInputStream`；
- 装饰器（Decorator）：`BufferedInputStream`、`DataInputStream` 等。

好处：按需组合，`Buffered + Data + File` 任意搭配；符合开闭原则。代价：类数量膨胀（这正是 Java IO 类多的原因）。

### 11.4 常用流清单

| 流 | 用途 | 备注 |
|---|---|---|
| FileInputStream / FileOutputStream | 文件字节读写 | 老 API，新代码优先 Files/Path |
| FileReader / FileWriter | 文件字符读写 | 默认平台编码，建议显式指定 |
| BufferedInputStream / BufferedOutputStream | 字节缓冲 | 默认 8KB |
| BufferedReader / BufferedWriter | 字符缓冲 | `readLine()` 高频使用 |
| DataInputStream / DataOutputStream | 读写基本类型 | 顺序敏感，读写必须对称 |
| ObjectInputStream / ObjectOutputStream | 对象序列化 | 见“序列化与反序列化”章 |
| PrintStream / PrintWriter | 格式化输出 | System.out 就是 PrintStream |
| ByteArrayInputStream / ByteArrayOutputStream | 内存字节流 | 把字节数组当流 |
| PushbackInputStream | 可回推字节 | 解析器常用 |

### 11.5 转换流与字符编码

**转换流**是字节流与字符流的桥梁：

```java
Reader reader = new InputStreamReader(
        new FileInputStream("a.txt"), StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(
        new FileOutputStream("b.txt"), StandardCharsets.UTF_8);
```

常用编码：

| 编码 | 特点 |
|---|---|
| ASCII | 7 位，1 字节，只能表示英文 |
| UTF-8 | 变长 1~4 字节，兼容 ASCII，互联网默认 |
| UTF-16 | 2 或 4 字节，Java 内部 char 的编码 |
| GBK | 中文 2 字节，历史遗留 |

乱码的根本原因：**写入与读取使用的字符集不一致**。修复手段：`String` 与字节互转时显式指定 charset（`getBytes(StandardCharsets.UTF_8)`），不要依赖平台默认编码。

### 11.6 面试追问

- 问：字节流和字符流怎么选？
- 答：二进制用字节流，文本用字符流；字符流内部就是字节流加编码转换。
- 问：为什么 IO 用装饰器模式？
- 答：能力可动态组合、按需叠加（缓冲、数据读写、对象序列化），符合开闭原则。
- 问：为什么要用缓冲流？
- 答：减少与内核的系统调用次数；每读一个字节就发起一次系统调用代价极高，缓冲到 8KB 一次读入。
- 问：乱码怎么排查？
- 答：确认写入编码与读取编码一致，文件本身编码可用文本编辑器查看，代码里统一指定 UTF-8。

## 12. BIO、NIO、AIO 与零拷贝

IO 模型决定高并发服务的骨架：BIO 一连接一线程，NIO 一个线程管千连接，AIO 回调式异步。这一章是后续 Netty、网络编程课程的直接前置。

### 12.1 五种 IO 模型（Java 视角）

操作系统层面的 IO 模型有五种：**阻塞 IO、非阻塞 IO、IO 多路复用、信号驱动 IO、异步 IO**。Java 对应到三个 API：

- **BIO（Blocking IO）**：对应阻塞 IO，JDK 1.0；
- **NIO（Non-blocking IO）**：对应非阻塞 + 多路复用，JDK 1.4；
- **AIO（NIO.2，Asynchronous IO）**：对应异步 IO，JDK 1.7。

### 12.2 BIO：一连接一线程

```java
ServerSocket server = new ServerSocket(8080);
while (true) {
    Socket socket = server.accept();     // 阻塞等待连接
    new Thread(() -> handle(socket)).start();   // 每连接一线程
}
```

- `accept()`、`read()`、`write()` 都会阻塞线程；
- 并发高时线程数爆炸，线程上下文切换开销巨大，1 万连接基本不可行；
- 适合连接数少、逻辑简单的场景（如传统 tomcat 7 的默认模型）。

### 12.3 NIO：Buffer、Channel、Selector

NIO 有三大核心组件：

| 组件 | 作用 |
|---|---|
| **Channel（通道）** | 双向数据通道：SocketChannel、ServerSocketChannel、FileChannel |
| **Buffer（缓冲区）** | 读写数据的容器：ByteBuffer、CharBuffer 等；position/limit/capacity 三个游标 |
| **Selector（选择器）** | 多路复用器：一个线程注册多个 Channel，事件就绪时被唤醒 |

```mermaid
flowchart LR
    S[Selector<br/>一个线程] -->|OP_ACCEPT| A[ServerSocketChannel]
    S -->|OP_READ / OP_WRITE| C1[SocketChannel 1]
    S -->|OP_READ / OP_WRITE| C2[SocketChannel 2]
    S -->|OP_READ / OP_WRITE| C3[SocketChannel N]
```

NIO 关键机制：

- `configureBlocking(false)` 让 Channel 非阻塞；
- 注册感兴趣的事件：`OP_ACCEPT`（新连接）、`OP_READ`（可读）、`OP_WRITE`（可写）；
- `selector.select()` 阻塞等待就绪事件，返回就绪集合 `selectedKeys`；
- 一个线程可以管理成千上万连接，线程数不再随连接数增长；
- 底层对应操作系统的 `select`/`poll`/`epoll`（Linux）或 IOCP（Windows）。

注意：NIO 的“非阻塞”是 **IO 非阻塞**，不是线程非阻塞；读数据仍需要自己处理半包、粘包问题（这正是 Netty 解决的痛点）。

### 12.4 AIO：异步回调

```java
AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open().bind(new InetSocketAddress(8080));
server.accept(null, new CompletionHandler<AsynchronousSocketChannel, Void>() {
    @Override
    public void completed(AsynchronousSocketChannel ch, Void attachment) { }
    @Override
    public void failed(Throwable exc, Void attachment) { }
});
```

- 操作系统完成 IO 后回调 `CompletionHandler`，是真正的异步（Proactor 模式）；
- 但 Linux 的 AIO 支持不成熟，Netty 等主流框架最终选择 NIO + Reactor，而不是 AIO；
- 校招只需说清“AIO 是异步回调、实际用得少、Linux 生态下 NIO 是主流”即可。

### 12.5 零拷贝

传统 `read + write` 传输文件，数据要经过 4 次拷贝（2 次 CPU 拷贝 + 2 次 DMA 拷贝）、4 次用户态/内核态切换：

```text
磁盘 → 内核缓冲区（DMA）→ 用户缓冲区（CPU）→ Socket 缓冲区（CPU）→ 网卡（DMA）
```

零拷贝的目标是减少 CPU 拷贝和上下文切换：

| 技术 | 原理 | 效果 |
|---|---|---|
| mmap | 用户空间直接映射内核缓冲区，省一次 CPU 拷贝 | 拷贝从 4 次降到 3 次 |
| sendfile | 数据在内核内直接送到 Socket 缓冲区，不进用户态 | 2 次上下文切换，2 次拷贝；网卡支持 SG-DMA 时 0 CPU 拷贝 |
| Java `FileChannel.transferTo()` | 底层调用 sendfile | 适合大文件传输，如 Nginx 静态文件 |

“零拷贝”不是零次拷贝，而是**零 CPU 拷贝**（内核态与用户态之间的拷贝为 0）。

### 12.6 Reactor 模型与 Netty

NIO 的经典编程范式是 **Reactor 模式**：

- **单 Reactor 单线程**：一个线程同时处理 accept 和 IO 事件，简单但 CPU 用不满；
- **单 Reactor 多线程**：accept 与 IO 分离，IO 事件交给 worker 线程池处理业务；
- **主从 Reactor 多线程**（Netty 默认）：mainReactor 只负责 accept，subReactor 组负责读写，业务交给线程池。

Netty 是对 NIO 的高性能封装：解决粘包/半包、提供编解码器、内存池、零拷贝（CompositeByteBuf、FileRegion），是 Java 后端高并发方向必须掌握的框架（后续网络模块展开）。

### 12.7 三种模型对比

| 对比项 | BIO | NIO | AIO |
|---|---|---|---|
| IO 模型 | 阻塞 | 非阻塞 + 多路复用 | 异步 |
| 线程模型 | 一连接一线程 | 一线程多连接 | 回调线程 |
| 并发能力 | 低 | 高 | 高 |
| 编程复杂度 | 低 | 高（半包/粘包） | 中 |
| 适用 | 低并发、简单服务 | 高并发网关、RPC、Netty | 场景少 |
| 典型代表 | Tomcat 7 默认 | Netty、Dubbo | 少见 |

### 12.8 面试追问

- 问：BIO、NIO、AIO 的区别？
- 答：阻塞 vs 非阻塞多路复用 vs 异步回调；线程模型从一连接一线程变成一线程多连接，再到回调。
- 问：NIO 为什么快？
- 答：非阻塞 + Selector 多路复用，一个线程管理大量连接，减少线程创建和上下文切换开销。
- 问：什么是零拷贝？
- 答：减少内核与用户态之间的 CPU 拷贝；sendfile 让数据在内核内直接流转，Java 用 FileChannel.transferTo。
- 问：select、poll、epoll 的区别？
- 答：select 有 1024 文件描述符上限且每次全量扫描；poll 去掉上限但仍全量扫描；epoll 事件驱动，只处理就绪事件，效率更高（详见计算机网络课程）。
- 问：Netty 为什么不用 AIO？
- 答：Linux 的 AIO 支持不成熟，NIO + Reactor 已能满足高并发，且可控性更好。

## 13. 序列化与反序列化

对象在内存里是一堆字节分布，跨进程传输（RPC）、落盘、缓存时都需要把对象变成字节（序列化），再在另一端还原（反序列化）。

### 13.1 什么是序列化

```text
序列化：对象 → 字节序列（存储/传输）
反序列化：字节序列 → 对象
```

Java 自带的序列化机制让类实现 `Serializable`（标记接口）即可：

```java
public class User implements Serializable {
    private static final long serialVersionUID = 1L;   // 强烈建议显式声明
    private String name;
    private int age;
}

// 写
try (ObjectOutputStream oos = new ObjectOutputStream(new FileOutputStream("user.bin"))) {
    oos.writeObject(new User("张三", 20));
}
// 读
try (ObjectInputStream ois = new ObjectInputStream(new FileInputStream("user.bin"))) {
    User user = (User) ois.readObject();
}
```

### 13.2 serialVersionUID 的作用

`serialVersionUID` 是序列化版本的“指纹”：

- 未显式声明时，JVM 根据类结构（字段、方法等）自动生成；
- 反序列化时，如果字节流里的 UID 与当前类的 UID 不一致，抛 `InvalidClassException`；
- **类结构变更**（增删字段、改类型）会导致自动生成的 UID 变化，老数据无法反序列化；
- 显式声明固定 UID 后，兼容新增字段、删除字段等普通变更（字段匹配按名字，多余的忽略，缺少的用默认值），从而保持前后兼容。

所以规范要求：**实现 Serializable 的类必须显式声明 `serialVersionUID`**，这是线上兼容的底线。

### 13.3 transient 与 static

- `transient` 修饰的字段**不参与序列化**，反序列化后为默认值（null、0、false）；
- `static` 字段属于类、不属于对象，**不参与序列化**；
- 典型用途：密码、敏感 token、派生字段（如从其他字段算出来的缓存）用 transient 排除。

```java
public class Account implements Serializable {
    private static final long serialVersionUID = 1L;
    private String username;
    private transient String password;   // 不落盘
}
```

### 13.4 反序列化的构造行为

- Java 反序列化**不会调用被序列化类的构造器**，而是通过底层机制直接分配对象；
- 若存在**不可序列化的父类**，会调用该父类的无参构造器；
- 因此反序列化可以绕过构造器校验，这正是安全问题的根源之一。

### 13.5 反序列化安全

反序列化是著名的攻击面：

- 攻击者构造恶意字节流，可能触发 `readObject` 中的危险调用链，造成 **RCE**（历史上 fastjson、Apache Commons Collections 等多次爆出反序列化漏洞）；
- 防御手段：
  - 对不可信数据**不要直接反序列化**，优先用 JSON 等白名单格式；
  - JDK 9+ 用 `ObjectInputFilter` 设置类型白名单/黑名单；
  - 升级有漏洞的库，避免使用默认 AutoType 的序列化框架。

### 13.6 主流序列化方案对比

| 方案 | 格式 | 跨语言 | 性能 | 场景 |
|---|---|---|---|---|
| Java 原生 Serializable | 二进制 | 否 | 慢 | 仅限 Java 到 Java 的简单场景 |
| JSON（Jackson/Gson） | 文本 | 是 | 中 | HTTP API、配置文件，互联网主流 |
| Protobuf | 二进制 | 是 | 高 | gRPC、微服务内部通信 |
| Kryo | 二进制 | 否 | 高 | Java 集群内部、缓存 |
| Hessian | 二进制 | 部分 | 中 | 老式 RPC（Dubbo 早期） |

工程建议：对外接口用 JSON；高性能内部 RPC 用 Protobuf 或 Kryo；几乎不用 Java 原生序列化（性能差、兼容差、不安全）。

### 13.7 面试追问

- 问：serialVersionUID 有什么用？
- 答：标识序列化版本，显式声明后类结构兼容变更不会导致反序列化失败。
- 问：transient 的作用？
- 答：修饰的字段不参与序列化，反序列化后是默认值。
- 问：反序列化会调用构造器吗？
- 答：不会调用被序列化类的构造器；不可序列化父类的无参构造器会被调用。
- 问：如何防止反序列化攻击？
- 答：不可信数据不做 Java 反序列化、用白名单过滤（ObjectInputFilter）、避免有漏洞的框架。

## 14. Java 8 新特性：Lambda、Stream 与新日期

Java 8 是历史上影响最大的一次版本升级，校招默认你熟悉它。函数式编程、Stream 管道、新日期 API 都是日常开发高频能力。

### 14.1 Lambda 与函数式接口

**函数式接口**是只有一个抽象方法的接口（可以有多个 default/static 方法），通常加 `@FunctionalInterface` 注解声明：

```java
@FunctionalInterface
interface Calculator {
    int calc(int a, int b);
}

Calculator add = (a, b) -> a + b;          // Lambda 是函数式接口的实例
Calculator mul = Integer::sum;             // 方法引用
System.out.println(add.calc(2, 3));        // 5
```

JDK 内置的常用函数式接口：

| 接口 | 抽象方法 | 用途 |
|---|---|---|
| `Predicate<T>` | `boolean test(T)` | 判断 |
| `Function<T, R>` | `R apply(T)` | 转换 |
| `Consumer<T>` | `void accept(T)` | 消费 |
| `Supplier<T>` | `T get()` | 供给 |
| `Runnable` | `void run()` | 无参无返回值 |
| `Comparator<T>` | `int compare(T, T)` | 比较 |

Lambda 捕获的局部变量必须是 `final` 或 effectively final（与内部类规则一致）。

### 14.2 方法引用

| 形式 | 示例 | 等价 Lambda |
|---|---|---|
| 静态方法 | `Integer::parseInt` | `s -> Integer.parseInt(s)` |
| 实例方法（特定对象） | `System.out::println` | `x -> System.out.println(x)` |
| 实例方法（任意对象） | `String::length` | `s -> s.length()` |
| 构造器 | `ArrayList::new` | `() -> new ArrayList<>()` |

### 14.3 Stream 管道

Stream 的三段式：**创建 → 中间操作（惰性）→ 终止操作（触发执行）**。

```java
List<String> names = List.of("Tom", "Jerry", "Alice", "Bob");

List<String> result = names.stream()                 // 创建
        .filter(s -> s.length() > 3)                 // 中间：过滤
        .map(String::toUpperCase)                    // 中间：映射
        .sorted()                                    // 中间：排序
        .limit(2)                                    // 中间：截断
        .collect(Collectors.toList());               // 终止：收集
```

常用操作：

| 类别 | 方法 |
|---|---|
| 创建 | `stream()`、`parallelStream()`、`Stream.of`、`Arrays.stream`、`Stream.iterate` |
| 中间 | `filter`、`map`、`flatMap`、`sorted`、`distinct`、`limit`、`skip`、`peek` |
| 终止 | `collect`、`forEach`、`count`、`reduce`、`min/max`、`anyMatch/allMatch/noneMatch`、`findFirst/findAny` |
| 收集器 | `toList`、`toSet`、`toMap`、`joining`、`groupingBy`、`partitioningBy`、`summarizingInt` |

```java
// 分组统计
Map<Integer, Long> countByLen = names.stream()
        .collect(Collectors.groupingBy(String::length, Collectors.counting()));

// 拼接
String joined = names.stream().collect(Collectors.joining(", "));
```

**惰性求值**：中间操作不执行，直到遇到终止操作；`limit`、`findFirst` 等短路操作可以提前结束。**并行流** `parallelStream()` 使用公共 ForkJoinPool，处理大数据时才可能更快，且必须保证元素操作无副作用、线程安全；小数据用并行反而更慢。

收集差异：`Stream.toList()` 是 JDK 16 加入的，返回**不可变**列表；`collect(Collectors.toList())` 从 JDK 8 就有，返回**可变**列表，需要增删结果时用后者。

### 14.4 Optional

`Optional` 用于显式表达“可能为空”，避免到处判 null：

```java
Optional<String> opt = Optional.ofNullable(name);

String result = opt
        .map(String::trim)                          // 存在才转换
        .filter(s -> !s.isEmpty())                  // 过滤
        .orElse("默认值");                          // 为空给默认值

// 或抛异常
String v = opt.orElseThrow(() -> new IllegalArgumentException("name 缺失"));
```

反模式：把 Optional 当字段、方法参数；拿到 Optional 后直接 `.get()` 不判断；用 Optional 包裹必然非空的值。

### 14.5 新日期时间 API（java.time）

JDK 8 之前用 `Date`/`Calendar`/`SimpleDateFormat`，问题一堆：可变、线程不安全、API 混乱。新 API 全部**不可变且线程安全**：

| 类 | 含义 |
|---|---|
| `LocalDate` | 日期（年-月-日） |
| `LocalTime` | 时间（时:分:秒.纳秒） |
| `LocalDateTime` | 日期 + 时间，无时区 |
| `Instant` | 时间戳（UTC） |
| `Duration` / `Period` | 时间差 / 日期间隔 |
| `ZonedDateTime` | 带时区的完整时间 |
| `DateTimeFormatter` | 格式化（线程安全） |

```java
LocalDate today = LocalDate.now();
LocalDate date = LocalDate.of(2026, 8, 29);
String text = date.format(DateTimeFormatter.ofPattern("yyyy-MM-dd"));

// SimpleDateFormat 非线程安全；DateTimeFormatter 线程安全，可静态共享
LocalDateTime dt = LocalDateTime.parse("2026-08-29 10:30:00",
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
```

### 14.6 其他 Java 8 要点

- 接口 default/static 方法（第 3 章）；
- `java.util.function` 全套函数式接口；
- `CompletableFuture` 异步编程（并发课程展开）；
- 默认使用 G1 垃圾回收器（JVM 课程展开）；
- 元空间（Metaspace）取代永久代（JVM 课程展开）。

### 14.7 面试追问

- 问：Lambda 表达式捕获局部变量的限制？
- 答：必须是 final 或 effectively final，保证捕获副本的一致性。
- 问：Stream 的中间操作和终止操作的区别？
- 答：中间操作惰性、不执行；终止操作触发整条管道执行并产出结果。
- 问：SimpleDateFormat 为什么线程不安全？替代方案？
- 答：内部共享可变状态（Calendar），多线程并发格式化会错乱；用 DateTimeFormatter（线程安全）或 ThreadLocal 隔离。
- 问：parallelStream 有什么注意点？
- 答：共享公共 ForkJoinPool，操作需无副作用且线程安全；数据量小或操作昂贵时反而更慢。

## 15. Java 9~25 新特性演进

面试官问“JDK 8 之后你了解哪些新特性”，不是要你背 JEP 编号，而是要你能说出几个**用得上**的特性及其版本。

### 15.1 版本演进

```mermaid
flowchart LR
    J8[Java 8 2014] --> J11[Java 11 2018]
    J11 --> J17[Java 17 2021]
    J17 --> J21[Java 21 2023]
    J21 --> J25[Java 25 2025]
```

### 15.2 分版本速览

| 版本 | 年份 | 值得说的特性 |
|---|---|---|
| Java 9 | 2017 | 模块化 JPMS；`List.of`/`Map.of`/`Set.of`；JShell；Stream 增强 |
| Java 10 | 2018 | `var` 局部变量类型推断 |
| Java 11 | 2018 LTS | HttpClient 正式；`String.isBlank/lines/strip/repeat`；单文件源码运行 |
| Java 12/13 | 2019 | switch 表达式预览；文本块预览 |
| Java 14 | 2020 | switch 表达式正式；record 预览；instanceof 模式匹配预览 |
| Java 15 | 2020 | 文本块正式；密封类预览；ZGC 正式 |
| Java 16 | 2021 | record 正式；instanceof 模式匹配正式；强封装 JDK 内部 |
| Java 17 | 2021 LTS | 密封类正式；模式匹配 switch 预览 |
| Java 21 | 2023 LTS | 虚拟线程；模式匹配 switch 正式；record 模式；有序集合；分代 ZGC |
| Java 25 | 2025 LTS | 隐式类与主方法正式化；灵活构造器主体；Primitive 类型模式（预览） |

### 15.3 校招必须会写的几个新语法

**var（Java 10）**：局部变量类型推断，必须有初始值，不能用于字段、方法参数和返回类型：

```java
var list = new ArrayList<String>();   // 推断为 ArrayList<String>
```

**文本块（Java 15 正式）**：多行字符串：

```java
String json = """
        {
          "name": "张三",
          "age": 20
        }
        """;
```

**record（Java 16 正式）**：不可变数据载体，自动生成构造器、`equals`/`hashCode`/`toString`：

```java
public record Point(int x, int y) { }

Point p = new Point(1, 2);
System.out.println(p.x() + ", " + p.y());   // 访问器是 x() 而不是 getX()
```

record 与普通类的区别：字段隐式 final、类隐式 final、没有无参构造器、不能扩展其他类；适合做 DTO、传输对象、不可变值对象。

**密封类（Java 17 正式）**：限制继承范围：

```java
public sealed interface Shape permits Circle, Square { }
public final class Circle implements Shape { }
public final class Square implements Shape { }
```

**switch 表达式（Java 14 正式）**：箭头语法自带 break，多个匹配项用逗号合并，需要返回值的块分支用 `yield`：

```java
String grade = switch (score / 10) {
    case 9, 10 -> "A";
    case 8 -> "B";
    default -> {
        System.out.println("继续加油");
        yield "C";       // 块形式的 switch 表达式必须 yield 返回值
    }
};
```

**模式匹配 switch（Java 21 正式）**：

```java
static String describe(Object obj) {
    return switch (obj) {
        case Integer i -> "整数 " + i;
        case String s -> "字符串 " + s;
        case null -> "null";              // JDK 21 正式，17 起为预览
        default -> "其他";
    };
}
```

**record 模式（Java 21 正式）**：解构 record：

```java
if (obj instanceof Point(int x, int y)) {
    System.out.println(x + y);            // 直接拿到组件
}
```

### 15.4 Java 21 的重头戏：虚拟线程

**虚拟线程（Virtual Threads，JEP 444，Java 21 正式）**解决“线程太贵”的问题：

- 传统平台线程由操作系统调度，创建和切换开销大，几万线程就顶不住；
- 虚拟线程由 JVM 调度（M:N 模型），创建成本极低，可以创建百万级；
- 虚拟线程在阻塞 IO（如等待数据库、网络响应）时自动让出载体线程，不浪费 CPU；
- 使用方式几乎无感：

```java
// 传统
new Thread(() -> handle()).start();

// 虚拟线程（Java 21）
Thread.startVirtualThread(() -> handle());
// 或
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> handle());
}
```

注意：虚拟线程适合 IO 密集型任务；CPU 密集任务不会变快。它**不改变并发安全问题**，该加锁还是加锁（详见并发课程）。

### 15.5 有序集合（Sequenced Collections）

Java 21 为有确定顺序的集合统一了首尾访问 API：

```java
List<Integer> list = new ArrayList<>(List.of(1, 2, 3));
System.out.println(list.getFirst());        // 1
System.out.println(list.getLast());         // 3
System.out.println(list.reversed());        // [3, 2, 1]

LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
map.put("a", 1); map.put("b", 2);
System.out.println(map.firstEntry());       // a=1
```

### 15.6 面试追问

- 问：JDK 8 之后你用过哪些新特性？
- 答：回答“var、文本块、record、switch 表达式、instanceof 模式匹配、密封类，以及 Java 21 的虚拟线程和有序集合”，每个配一句用途。
- 问：record 和普通类的区别？
- 答：record 自动生成构造器、equals/hashCode/toString，字段和类隐式 final，适合不可变数据载体。
- 问：虚拟线程是什么？解决了什么问题？
- 答：JVM 调度的轻量线程，解决平台线程创建和切换成本高的问题，适合 IO 密集型高并发；不解决数据竞争。
- 问：sealed 类的作用？
- 答：限制哪些类可以实现/继承它，配合模式匹配让穷尽性检查更可靠。

## 16. 编程规范与一页速查

这一章把《阿里巴巴 Java 开发手册》里与“语言根基”直接相关的核心规范提炼出来，再给一页常用 API 速查，方便日常写代码时对照。

### 16.1 核心规范

**命名**：

- 类名：大驼峰 `UserService`；方法/变量：小驼峰 `getUserName`；常量：全大写下划线 `MAX_RETRY_COUNT`；包名：全小写 `com.example.order`；
- 布尔变量不要用 `is` 前缀加动词（如 `isDeleted` 的 getter 会生成 `getDeleted` 还是 `isDeleted` 有歧义），POJO 布尔字段规范上避免 `isXxx`；
- 不要用拼音或自造缩写命名。

**代码**：

- 禁止魔法值：`if (status == 1)` 应写成具名常量或枚举；
- 方法尽量单一职责、参数不超过 5 个；
- 循环内不要做字符串 `+` 拼接（用 StringBuilder）；
- 集合初始化尽量预估容量，避免扩容；
- `equals` 用常量调用：`"abc".equals(s)` 而不是 `s.equals("abc")`（防空指针）；
- 大整数、金额用 `BigDecimal`，且**用字符串构造**：`new BigDecimal("0.1")`，不要 `new BigDecimal(0.1)`；比较大小用 `compareTo` 而不是 `equals`（`equals` 要求精度 scale 也相同，`0.1` 与 `0.10` 会不相等）；需要固定小数位用 `setScale(2, RoundingMode.HALF_UP)`；
- 浮点比较不要用 `==`，用差值范围或 `BigDecimal`；
- 时间相关用 `java.time`，不直接用 `Date` 做业务逻辑；`SimpleDateFormat` 不要定义为 static 共享；
- 并发场景不用 `HashMap`、`ArrayList`，用 `ConcurrentHashMap`、`CopyOnWriteArrayList` 或加锁（详见并发课程）；
- 日志：`log.error("订单创建失败，orderId={}", orderId, e)`，异常要打印堆栈，不要只打 `e.getMessage()`。

### 16.2 高频踩坑清单

| 坑 | 正确做法 |
|---|---|
| `Integer` 用 `==` 比较 | 用 `equals` 或拆箱 |
| 循环内字符串 `+` 拼接 | 用 `StringBuilder` |
| 遍历集合时直接 `remove` | `Iterator.remove` 或 `removeIf` |
| 自定义对象放进 HashMap/Set 没重写 hashCode | 同时重写 equals 和 hashCode |
| `Arrays.asList` 结果调 add | 用 `new ArrayList<>(Arrays.asList(...))` 包装 |
| 浮点直接 `==` 比较 | `BigDecimal` 或误差范围 |
| `SimpleDateFormat` 静态共享 | `DateTimeFormatter` 或 ThreadLocal |
| 受检异常 catch 后什么都不做 | 至少记日志，能处理就处理 |
| finally 里 return | 不要，finally 只做资源释放 |
| 用 `new Integer(100)` | 用 `Integer.valueOf(100)` 或自动装箱 |
| 忽略返回值（如 `set.remove`） | 按需检查返回值 |
| 大集合默认容量 | 预估后指定 initialCapacity |
| BigDecimal 比较 | 用 compareTo，equals 会因 scale 不同误判 |
| 需要只读集合 | Collections.unmodifiableXxx 包装 |

### 16.3 一页速查

**String**：

```java
" abc ".trim();                    // 去首尾空白（JDK 11+ 用 strip 处理 Unicode）
"abc".equalsIgnoreCase("ABC");     // 忽略大小写比较
String.join(",", "a", "b", "c");   // a,b,c
"ab\ncd".lines().toList();         // 按行拆分（JDK 11+）
"a".repeat(3);                     // aaa（JDK 11+）
```

**集合**：

```java
List<String> list = new ArrayList<>(List.of("a", "b"));
list.removeIf(s -> s.equals("a"));               // 安全删除
Map<String, Integer> map = new HashMap<>();
map.merge("k", 1, Integer::sum);                 // 计数累加
map.computeIfAbsent("k", k -> new ArrayList<>()).add("v");  // 初始化后添加
list.sort(Comparator.comparing(String::length)); // 按长度排序
Collections.sort(list);                          // 稳定排序
Collections.reverse(list);                       // 反转
Collections.unmodifiableList(list);              // 只读视图，防外部修改
Collections.emptyList();                         // 空列表，不新建对象
```

**Stream**：

```java
int[] arr = {3, 1, 2};
int sum = Arrays.stream(arr).sum();
List<Integer> sorted = Arrays.stream(arr).boxed().sorted().toList();  // JDK 16+，结果不可变
Map<Boolean, List<Integer>> part =
        Arrays.stream(arr).boxed().collect(Collectors.partitioningBy(n -> n % 2 == 0));
```

**日期**：

```java
LocalDate today = LocalDate.now();
LocalDate firstDay = today.withDayOfMonth(1);
long days = ChronoUnit.DAYS.between(LocalDate.of(2026, 1, 1), today);
String s = today.format(DateTimeFormatter.ofPattern("yyyyMMdd"));
```

**空指针防护**：

```java
Objects.requireNonNull(obj, "obj 不能为空");
String safe = Optional.ofNullable(obj).map(Object::toString).orElse("");
```

### 16.4 如何继续深入

- 读完集合章节后在 IDEA 里给 ArrayList/HashMap 打断点，观察扩容前后的数组长度；
- 手写 HashMap 的 put 流程图和 LRU，面试前默写一遍；
- 用 `javap -c` 反编译 `.class` 观察泛型擦除、字符串拼接、Lambda 的实际字节码；
- 后续按顺序学习《Java 并发编程》《JVM》《Java Web 与 Spring》，把本课程的线索（volatile、类加载、反射注解）逐个接上。

## 17. 高频自测题与参考资料

### 17.1 分主题自测

本页把全书高频考点压缩成 52 道自测题：先盖住“一句话要点”尝试作答，再对照检查；能一次答对八成以上，就可以进入下一门课《Java 并发编程》。

| 主题 | 问题 | 一句话要点 |
|---|---|---|
| 基础 | JVM、JRE、JDK 区别 | JDK 含 JRE 和开发工具，JRE 含 JVM 和类库 |
| 基础 | Java 为什么跨平台 | 字节码 + 各平台 JVM 实现 |
| 基础 | main 方法为什么是 static | JVM 启动时无对象可调用 |
| 类型 | 基本类型有哪些，各占多少字节 | 8 种，byte1/short2/int4/long8/float4/double8/char2/boolean 不定 |
| 类型 | Integer 缓存范围 | -128~127，可用 AutoBoxCacheMax 调整 |
| 类型 | 拆箱空指针怎么发生 | Integer null 赋给 int 触发 intValue |
| OOP | 重写有哪些约束 | 签名一致、协变返回、权限不收紧、异常不扩大 |
| OOP | 抽象类和接口区别 | 模板 vs 契约；状态、构造器、多继承 |
| OOP | 初始化顺序 | 父静态→子静态→父实例→父构造→子实例→子构造 |
| OOP | 内部类为什么要求 effectively final | 捕获副本需保持一致 |
| String | 为什么不可变 | 池化、缓存、线程安全、安全 |
| String | new String 创建几个对象 | 看常量池，1 或 2 |
| String | StringBuffer 和 StringBuilder | 一个同步一个不同步 |
| 集合 | ArrayList 扩容 | 懒初始化 10，之后 1.5 倍 |
| 集合 | ArrayList vs LinkedList | 数组 vs 链表，随机访问与增删复杂度互换 |
| 集合 | fail-fast 原理 | modCount 校验 |
| 集合 | Arrays.asList 的坑 | 定长视图，只能 set 不能 add |
| 集合 | HashMap 底层结构 | 数组+链表+红黑树 |
| 集合 | HashMap put 流程 | 扰动→定位→空桶/覆盖/树/尾插→modCount→扩容 |
| 集合 | 为什么用红黑树 | 最坏 O(log n)，抵御恶意哈希 |
| 集合 | 为什么阈值 8 和 6 | 泊松概率极低；留缓冲防抖动 |
| 集合 | 为什么容量是 2 的幂 | 位运算寻址 + 扩容原地/加旧容量 |
| 集合 | HashMap 为什么线程不安全 | 覆盖、丢数据；JDK8 不再死循环 |
| 集合 | ConcurrentHashMap 怎么做 | JDK8 CAS + synchronized 锁桶头 |
| 集合 | LRU 怎么实现 | LinkedHashMap accessOrder 或 HashMap+双向链表 |
| 泛型 | 什么是类型擦除 | 编译后擦除为 Object/上界，运行时无泛型 |
| 泛型 | extends 和 super | PECS：生产者 extends，消费者 super |
| 泛型 | 为什么不能 new T[] | 数组协变且保留类型，与擦除冲突 |
| 反射 | 获取 Class 的三种方式 | .class、getClass、forName（会初始化） |
| 反射 | 为什么框架需要反射 | 编译期不知道用户类，运行时按配置加载 |
| 反射 | JDK 动态代理为什么必须接口 | 生成接口实现类；无接口用 CGLIB 子类 |
| 异常 | Error 和 Exception | 不可恢复 vs 可处理 |
| 异常 | finally 和 return | finally 覆盖返回值，不要在里面 return |
| 异常 | try-with-resources 优点 | 自动逆序关闭、suppressed 异常 |
| IO | 字节流和字符流 | 二进制 vs 文本+编码 |
| IO | 为什么用缓冲流 | 减少系统调用 |
| IO | IO 为什么用装饰器模式 | 能力动态组合 |
| NIO | BIO/NIO/AIO | 阻塞/多路复用/异步回调 |
| NIO | NIO 三大件 | Channel、Buffer、Selector |
| NIO | 什么是零拷贝 | 减少 CPU 拷贝，sendfile/transferTo |
| 序列化 | serialVersionUID 作用 | 版本兼容，必须显式声明 |
| 序列化 | transient 作用 | 不参与序列化 |
| 新特性 | Java 8 核心 | Lambda、Stream、Optional、新日期 |
| 新特性 | Stream 惰性 | 中间操作不执行，终止操作触发 |
| 新特性 | record 是什么 | 不可变数据载体，自动生成常用方法 |
| 新特性 | 虚拟线程 | JVM 调度轻量线程，适合 IO 密集 |
| 新特性 | switch 表达式和 yield | 箭头语法自动 break，块分支用 yield 返回值 |
| OOP | 枚举的本质是什么 | 继承 java.lang.Enum 的 final 类，每个常量是静态实例 |
| 集合 | PriorityQueue 底层与复杂度 | 二叉堆，入堆出堆 O(log n)，默认小顶堆 |
| 规范 | Integer 怎么比较 | equals |
| 规范 | 金额怎么算 | BigDecimal 字符串构造 |
| 规范 | BigDecimal 怎么比较 | 用 compareTo，equals 会因 scale 不同误判 |

### 17.2 考前 30 分钟速记

- 一句话回答“ArrayList 与 LinkedList”：数组 vs 链表，get 快 vs 插删头快；
- 一句话回答“HashMap”：数组 + 链表 + 红黑树，2 的幂容量，0.75 负载因子，8/6 转树阈值，扩容翻倍；
- 一句话回答“泛型”：编译期检查、运行期擦除、extends 只读、super 只写；
- 一句话回答“反射”：运行时获取类信息并操作对象，框架装配的基础，JDK 代理基于接口、CGLIB 基于子类；
- 一句话回答“BIO/NIO/AIO”：一连接一线程、一线程多连接、异步回调；
- 一句话回答“String”：不可变、常量池、intern、Builder 拼接；
- 一句话回答“新特性”：Java 8 函数式、17 密封类、21 虚拟线程。

### 17.3 参考资料

本课程内容以 JDK 官方文档与下列公开资料为参考，建议按需查阅原文：

- [Java 官方教程（Oracle Java Tutorials）](https://docs.oracle.com/javase/tutorial/)
- [Java 语言规范（JLS）](https://docs.oracle.com/javase/specs/jls/se21/html/index.html)
- [JavaGuide：Java 基础与集合源码](https://javaguide.cn/java/basis/java-basic-questions-01.html)
- [JavaGuide：HashMap 源码分析](https://javaguide.cn/java/collection/hashmap-source-code.html)
- [JavaGuide：Java 21 新特性概览](https://javaguide.cn/java/new-features/java21.html)
- [CS-Notes：Java 容器](https://github.com/CyC2018/CS-Notes)
- [菜鸟教程：Java 教程](https://www.runoob.com/java/java-tutorial.html)
- [OpenJDK JEP 索引](https://openjdk.org/jeps/0)
- 《Java 编程思想》《Effective Java》《阿里巴巴 Java 开发手册》

> 学习闭环：每章末尾的“面试追问”建议先默写答案再看笔记；自测题能一口气答出 80% 后，就可以进入下一门课《Java 并发编程》了。
