# Java 字符串学习笔记

## 一、String 概述

`String` 是 Java 中最常用的类之一，用于表示文本（字符串）。

### 1.1 核心特性

| 特性 | 说明 |
|------|------|
| **不可变性** | `String` 对象一旦创建，其内容**不可改变**。任何看似修改的操作都会创建新对象 |
| **final 类** | `String` 被 `final` 修饰，不能被继承 |
| **实现了序列化** | 实现了 `Serializable`、`Comparable`、`CharSequence` 等接口 |

```java
// 不可变性示例
String s = "hello";
s = s.toUpperCase(); // 原 "hello" 并未改变，s 指向了新的 String 对象 "HELLO"
```

### 1.2 字符串常量池

Java 为了提升性能，维护了一个**字符串常量池**（String Pool），位于堆内存中。

- 使用**字面量**创建字符串时，JVM 会先检查常量池中是否存在相同内容的字符串
- 若存在，直接返回引用；不存在则在池中创建再返回
- 使用 `new` 关键字会强制在堆中创建新对象（但字面量部分仍会入池）

```java
String s1 = "hello";
String s2 = "hello";
String s3 = new String("hello");

System.out.println(s1 == s2);      // true  （常量池中同一个对象）
System.out.println(s1 == s3);      // false （s3 是堆上新对象）
System.out.println(s1.equals(s3)); // true  （内容相同）
```

> `==` 比较的是引用地址，`equals()` 比较的是内容。

---

## 二、创建字符串的几种方式

```java
// 方式1：字面量（推荐）
String s1 = "hello";

// 方式2：new 关键字
String s2 = new String("hello");

// 方式3：字符数组
char[] arr = {'h', 'e', 'l', 'l', 'o'};
String s3 = new String(arr);

// 方式4：字节数组（可指定编码）
byte[] bytes = {104, 101, 108, 108, 111};
String s4 = new String(bytes);                     // 默认 UTF-8
String s5 = new String(bytes, "UTF-8");

// 方式5：StringBuilder / StringBuffer
StringBuilder sb = new StringBuilder("hello");
String s6 = sb.toString();
```

**预期结果：**
```
s1 = hello, s2 = hello, s3 = hello, s4 = hello, s5 = hello, s6 = hello
```

---

## 三、常用 API（按功能分类）

### 3.1 基础信息

| 方法 | 说明 | 示例 | 结果 |
|------|------|------|------|
| `length()` | 返回字符串长度 | `"hello".length()` | `5` |
| `isEmpty()` | 是否为空字符串 | `"".isEmpty()` | `true` |
| `isBlank()` | 是否空白（JDK 11+） | `"  ".isBlank()` | `true` |
| `charAt(i)` | 返回指定索引的字符 | `"hello".charAt(1)` | `'e'` |

```java
String str = "hello";
System.out.println(str.length());   // 5
System.out.println(str.isEmpty());  // false
System.out.println(str.charAt(0));  // h
```

---

### 3.2 判断与比较

| 方法 | 说明 | 示例 | 结果 |
|------|------|------|------|
| `equals(obj)` | 比较内容是否相等 | `"abc".equals("abc")` | `true` |
| `equalsIgnoreCase(s)` | 忽略大小写比较 | `"Abc".equalsIgnoreCase("abc")` | `true` |
| `compareTo(s)` | 字典序比较，返回差值 | `"a".compareTo("b")` | `-1` |
| `compareToIgnoreCase(s)` | 忽略大小写字典序比较 | `"A".compareToIgnoreCase("b")` | `-1` |
| `contentEquals(cs)` | 与 `CharSequence` 比较 | `"abc".contentEquals("abc")` | `true` |

```java
String a = "Java";
String b = "java";

System.out.println(a.equals(b));               // false
System.out.println(a.equalsIgnoreCase(b));     // true
System.out.println(a.compareTo(b));            // -32 （'J' - 'j' 的 ASCII 差）
System.out.println(a.compareToIgnoreCase(b));  // 0
```

> **`compareTo` 返回值规则：** 按字典序逐个比较字符，遇到第一个不同字符时返回 `char1 - char2`；若前缀相同，则返回 `len1 - len2`。

---

### 3.3 查找

| 方法 | 说明 | 示例 | 结果 |
|------|------|------|------|
| `indexOf(ch)` | 字符首次出现的索引 | `"hello".indexOf('l')` | `2` |
| `indexOf(ch, from)` | 从指定位置开始查找 | `"hello".indexOf('l', 3)` | `3` |
| `indexOf(str)` | 子串首次出现的索引 | `"hello".indexOf("ll")` | `2` |
| `lastIndexOf(ch)` | 字符最后一次出现的索引 | `"hello".lastIndexOf('l')` | `3` |
| `lastIndexOf(str)` | 子串最后一次出现的索引 | `"abab".lastIndexOf("ab")` | `2` |
| `contains(cs)` | 是否包含指定字符序列 | `"hello".contains("ell")` | `true` |
| `startsWith(prefix)` | 是否以指定前缀开头 | `"hello".startsWith("he")` | `true` |
| `endsWith(suffix)` | 是否以指定后缀结尾 | `"hello".endsWith("lo")` | `true` |

```java
String s = "hello world";

System.out.println(s.indexOf('o'));        // 4
System.out.println(s.indexOf('o', 5));     // 7
System.out.println(s.indexOf("world"));   // 6
System.out.println(s.lastIndexOf('o'));   // 7
System.out.println(s.contains("lo wo"));  // true
System.out.println(s.startsWith("he"));   // true
System.out.println(s.endsWith("ld"));     // true
```

---

### 3.4 截取与拼接

| 方法 | 说明 | 示例 | 结果 |
|------|------|------|------|
| `substring(begin)` | 从 begin 截取到末尾 | `"hello".substring(2)` | `"llo"` |
| `substring(begin, end)` | 截取 [begin, end) 区间 | `"hello".substring(1, 4)` | `"ell"` |
| `concat(s)` | 拼接字符串 | `"a".concat("b")` | `"ab"` |
| `join(delim, elements...)` | 用分隔符拼接（静态方法） | `String.join("-", "a", "b", "c")` | `"a-b-c"` |
| `repeat(n)` | 重复字符串 n 次（JDK 11+） | `"ha".repeat(3)` | `"hahaha"` |

```java
String s = "HelloWorld";

System.out.println(s.substring(5));          // World
System.out.println(s.substring(0, 5));       // Hello
System.out.println(s.concat("!!!"));         // HelloWorld!!!
System.out.println(String.join(", ", "A", "B", "C")); // A, B, C
System.out.println("ha".repeat(3));          // hahaha
```

> **注意：** `substring` 在 JDK 7+ 中是左闭右开区间 `[begin, end)`。

---

### 3.5 转换

| 方法 | 说明 | 示例 | 结果 |
|------|------|------|------|
| `toUpperCase()` | 转大写 | `"abc".toUpperCase()` | `"ABC"` |
| `toLowerCase()` | 转小写 | `"ABC".toLowerCase()` | `"abc"` |
| `trim()` | 去除首尾空格 | `"  hi  ".trim()` | `"hi"` |
| `strip()` | 去除首尾全角/半角空白（JDK 11+） | `"　hi".strip()` | `"hi"` |
| `toCharArray()` | 转为 char 数组 | `"abc".toCharArray()` | `{'a','b','c'}` |
| `getBytes()` | 转为字节数组 | `"abc".getBytes()` | `{97, 98, 99}` |
| `valueOf(x)` | 将各种类型转为字符串（静态方法） | `String.valueOf(123)` | `"123"` |

```java
String s = "  Java Programming  ";

System.out.println(s.trim());                   // "Java Programming"
System.out.println("hello".toUpperCase());      // "HELLO"
System.out.println("HELLO".toLowerCase());      // "hello"

char[] chars = "abc".toCharArray();
for (char c : chars) {
    System.out.println((int) c);                // 97 \n 98 \n 99
}

System.out.println(String.valueOf(3.14));        // "3.14"
System.out.println(String.valueOf(true));        // "true"
```

---

### 3.6 替换

| 方法 | 说明 | 示例 | 结果 |
|------|------|------|------|
| `replace(old, new)` | 替换所有匹配的字符或字符串 | `"a.b.c".replace(".", "-")` | `"a-b-c"` |
| `replaceAll(regex, new)` | 正则匹配替换 | `"a1b2c3".replaceAll("\\d", "-")` | `"a-b-c-"` |
| `replaceFirst(regex, new)` | 正则匹配替换第一个 | `"a1b2c3".replaceFirst("\\d", "-")` | `"a-b2c3"` |

```java
String s = "apple,banana,apple";

System.out.println(s.replace("apple", "orange"));       // orange,banana,orange
System.out.println(s.replaceAll("a.+?e", "X"));         // X,banana,X  （正则匹配）
System.out.println(s.replaceFirst("apple", "orange"));  // orange,banana,apple
```

> **`replace` vs `replaceAll`：** `replace` 参数是普通字符串，`replaceAll` 参数是正则表达式。如果不需要正则，优先用 `replace`。

---

### 3.7 拆分

| 方法 | 说明 | 示例 | 结果 |
|------|------|------|------|
| `split(regex)` | 按正则拆分 | `"a,b,c".split(",")` | `["a","b","c"]` |
| `split(regex, limit)` | 限制拆分次数 | `"a,b,c".split(",", 2)` | `["a","b,c"]` |

```java
String s = "one,two,three,four";

String[] arr1 = s.split(",");
System.out.println(Arrays.toString(arr1));     // [one, two, three, four]

String[] arr2 = s.split(",", 2);
System.out.println(Arrays.toString(arr2));     // [one, two,three,four]

String[] arr3 = s.split(",", 3);
System.out.println(Arrays.toString(arr3));     // [one, two, three,four]

// 特殊字符需要转义
String s2 = "a.b.c";
String[] arr4 = s2.split("\\.");
System.out.println(Arrays.toString(arr4));     // [a, b, c]
```

> **陷阱提示：** `split(".")` 是错误的，因为 `.` 在正则中匹配任意字符，必须转义为 `\\\\.` 或使用 `split("\\.")`。

---

### 3.8 格式化

| 方法 | 说明 | 示例 | 结果 |
|------|------|------|------|
| `format(format, args...)` | 格式化字符串（静态方法） | `String.format("你好 %s！", "Java")` | `"你好 Java！"` |
| `formatted(args...)` | JDK 15 文本块格式 | `"你好 %s！".formatted("Java")` | `"你好 Java！"` |

```java
String name = "小明";
int age = 18;
double score = 95.5;

// %s 字符串，%d 整数，%.1f 小数（保留1位），%n 换行
String info = String.format("姓名：%s，年龄：%d，成绩：%.1f", name, age, score);
System.out.println(info);   // 姓名：小明，年龄：18，成绩：95.5

// 数字补零
System.out.println(String.format("%05d", 42));   // 00042

// 左对齐
System.out.println(String.format("%-10s!", "abc")); // abc       !
```

常用格式占位符：

| 占位符 | 说明 | 示例 |
|--------|------|------|
| `%s` | 字符串 | `"hello"` |
| `%d` | 整数 | `123` |
| `%f` | 浮点数 | `3.140000` |
| `%.2f` | 保留2位小数 | `3.14` |
| `%x` | 十六进制 | `7b` |
| `%n` | 换行符 | `\n` |
| `%tY` | 年份（4位） | `2026` |

---

### 3.9 正则相关

| 方法 | 说明 | 示例 | 结果 |
|------|------|------|------|
| `matches(regex)` | 是否完全匹配正则 | `"abc".matches("[a-z]+")` | `true` |

```java
// 手机号校验（简单版）
String phone = "13812345678";
System.out.println(phone.matches("1[3-9]\\d{9}"));  // true

// 邮箱校验（简单版）
String email = "user@example.com";
System.out.println(email.matches("\\w+@\\w+\\.\\w+"));  // true
```

---

## 四、StringBuilder 与 StringBuffer

由于 `String` 不可变，频繁拼接字符串会产生大量临时对象，性能差。应使用 `StringBuilder` 或 `StringBuffer`。

### 4.1 区别

| 类 | 线程安全 | 性能 | 适用场景 |
|----|---------|------|---------|
| `StringBuilder` | ❌ 不安全 | 高 | **单线程**（推荐） |
| `StringBuffer` | ✅ 安全（synchronized）| 较低 | 多线程共享 |

### 4.2 常用方法

| 方法 | 说明 |
|------|------|
| `append(x)` | 追加内容 |
| `insert(index, x)` | 在指定位置插入 |
| `delete(start, end)` | 删除 [start, end) 区间的字符 |
| `deleteCharAt(index)` | 删除指定位置的字符 |
| `replace(start, end, str)` | 替换区间内容 |
| `reverse()` | 反转字符串 |
| `toString()` | 转为 String |
| `length()` | 当前长度 |
| `charAt(index)` | 获取指定索引字符 |
| `setCharAt(index, ch)` | 修改指定索引字符 |
| `substring(start, end)` | 截取子串 |
| `capacity()` | 当前容量 |

### 4.3 使用示例

```java
StringBuilder sb = new StringBuilder();

// 追加
sb.append("Hello").append(" ").append("World");
System.out.println(sb.toString());              // Hello World

// 插入
sb.insert(5, " Java");
System.out.println(sb.toString());              // Hello Java World

// 替换
sb.replace(6, 10, "C++");
System.out.println(sb.toString());              // Hello C++ World

// 删除
sb.delete(5, 9);
System.out.println(sb.toString());              // Hello World

// 反转
sb.reverse();
System.out.println(sb.toString());              // dlroW olleH

// 修改指定字符
sb.setCharAt(0, 'D');
System.out.println(sb.toString());              // DlroW olleH
```

### 4.4 性能对比：String vs StringBuilder

```java
long start;

// ❌ 差：String 拼接（产生大量中间对象）
start = System.currentTimeMillis();
String s = "";
for (int i = 0; i < 10000; i++) {
    s += i;  // 每次循环都创建新 String 对象
}
System.out.println("String 耗时：" + (System.currentTimeMillis() - start) + "ms");

// ✅ 好：StringBuilder 拼接
start = System.currentTimeMillis();
StringBuilder sb = new StringBuilder();
for (int i = 0; i < 10000; i++) {
    sb.append(i);
}
System.out.println("StringBuilder 耗时：" + (System.currentTimeMillis() - start) + "ms");
```

**预期结果（数量级参考）：**
```
String 耗时：~150ms
StringBuilder 耗时：~1ms
```

> 在循环拼接时，`StringBuilder` 比 `String` 快 **上百倍**！

---

## 五、常见面试陷阱与注意事项

### 5.1 字符串相等比较

```java
String s1 = "abc";
String s2 = "abc";
String s3 = new String("abc");
String s4 = "ab" + "c";       // 编译期常量折叠，等价于 "abc"
String s5 = "ab";
String s6 = s5 + "c";         // 运行时拼接，堆上新对象

System.out.println(s1 == s2);     // true  （常量池）
System.out.println(s1 == s3);     // false （new 创建了新对象）
System.out.println(s1 == s4);     // true  （编译期已确定为 "abc"）
System.out.println(s1 == s6);     // false （运行时拼接，新对象）
System.out.println(s1.equals(s3)); // true （比较内容）
```

### 5.2 intern() 方法

将字符串手动加入常量池：

```java
String s1 = new String("hello");
String s2 = s1.intern();       // 从常量池中获取

System.out.println(s1 == s2);  // false（s1 是堆对象，s2 是常量池对象）
System.out.println("hello" == s2); // true（都是常量池对象）
```

### 5.3 switch 对 String 的支持

Java 7+ 支持 `switch` 使用 `String`：

```java
String fruit = "apple";

switch (fruit) {
    case "apple":
        System.out.println("苹果"); break;
    case "banana":
        System.out.println("香蕉"); break;
    default:
        System.out.println("未知"); break;
}
// 输出：苹果
```

### 5.4 空字符串与 null 的区别

```java
String s1 = "";      // 空字符串，length() = 0，不是 null
String s2 = null;    // 空对象引用

System.out.println(s1.isEmpty());   // true
System.out.println(s1.length());    // 0
// System.out.println(s2.length()); // ❌ 空指针异常 NullPointerException
```

### 5.5 文本块（JDK 15+）

```java
// 传统方式
String html1 = "<html>\n" +
               "    <body>\n" +
               "        <p>你好</p>\n" +
               "    </body>\n" +
               "</html>";

// 文本块方式（JDK 15+）
String html2 = """
              <html>
                  <body>
                      <p>你好</p>
                  </body>
              </html>
              """;
```

---

## 六、完整综合示例

```java
public class StringDemo {
    public static void main(String[] args) {

        // ========== 1. 创建字符串 ==========
        String str1 = "  Hello, Java World!  ";
        String str2 = "hello, java world!";

        System.out.println("原始字符串1: '" + str1 + "'");
        System.out.println("原始字符串2: '" + str2 + "'");

        // ========== 2. 基础信息 ==========
        System.out.println("\n===== 基础信息 =====");
        System.out.println("str1 长度: " + str1.length());
        System.out.println("str1 是否为空: " + str1.isEmpty());
        System.out.println("str1 索引2的字符: " + str1.charAt(2));

        // ========== 3. 比较 ==========
        System.out.println("\n===== 比较 =====");
        System.out.println("忽略大小写比较: " + str1.trim().equalsIgnoreCase(str2));
        System.out.println("严格比较: " + str1.trim().equals(str2));

        // ========== 4. 查找 ==========
        System.out.println("\n===== 查找 =====");
        System.out.println("'Java' 首次出现位置: " + str1.indexOf("Java"));
        System.out.println("'o' 最后出现位置: " + str1.lastIndexOf('o'));
        System.out.println("包含 'World': " + str1.contains("World"));
        System.out.println("以空格开头: " + str1.startsWith(" "));
        System.out.println("以空格结尾: " + str1.endsWith("  "));

        // ========== 5. 截取与拼接 ==========
        System.out.println("\n===== 截取与拼接 =====");
        String trimmed = str1.trim();
        System.out.println("去空格后: '" + trimmed + "'");
        System.out.println("substring(7, 11): " + trimmed.substring(7, 11));
        System.out.println("拼接: " + trimmed.concat("!"));
        System.out.println("join: " + String.join("-", "A", "B", "C"));

        // ========== 6. 转换 ==========
        System.out.println("\n===== 转换 =====");
        System.out.println("大写: " + trimmed.toUpperCase());
        System.out.println("小写: " + trimmed.toLowerCase());

        char[] chars = trimmed.toCharArray();
        System.out.println("char数组第一个字符: " + chars[0]);

        System.out.println("String.valueOf(123): " + String.valueOf(123));
        System.out.println("String.valueOf(true): " + String.valueOf(true));

        // ========== 7. 替换与拆分 ==========
        System.out.println("\n===== 替换与拆分 =====");
        String csv = "apple,banana,orange,grape";
        System.out.println("替换逗号为竖线: " + csv.replace(",", " | "));

        String[] fruits = csv.split(",");
        System.out.print("拆分结果: ");
        for (String f : fruits) {
            System.out.print(f + " ");
        }
        System.out.println();

        // ========== 8. 正则 ==========
        System.out.println("\n===== 正则 =====");
        System.out.println("'123' 是否全为数字: " + "123".matches("\\d+"));
        System.out.println("'abc123' 替换数字为*: " + "abc123xyz".replaceAll("\\d+", "*"));

        // ========== 9. StringBuilder ==========
        System.out.println("\n===== StringBuilder =====");
        StringBuilder sb = new StringBuilder();
        sb.append("《静夜思》").append("\n");
        sb.append("床前明月光，").append("\n");
        sb.append("疑是地上霜。").append("\n");
        sb.append("举头望明月，").append("\n");
        sb.append("低头思故乡。");
        System.out.println(sb.toString());

        // 反转
        sb.reverse();
        System.out.println("反转后: " + sb.toString());

        // ========== 10. 格式化 ==========
        System.out.println("\n===== 格式化 =====");
        String formatted = String.format(
            "姓名：%s，年龄：%d，分数：%.1f", "张三", 20, 92.5
        );
        System.out.println(formatted);
    }
}
```

**预期输出：**
```
原始字符串1: '  Hello, Java World!  '
原始字符串2: 'hello, java world!'

===== 基础信息 =====
str1 长度: 22
str1 是否为空: false
str1 索引2的字符: H

===== 比较 =====
忽略大小写比较: true
严格比较: false

===== 查找 =====
'Java' 首次出现位置: 9
'o' 最后出现位置: 16
包含 'World': true
以空格开头: true
以空格结尾: true

===== 截取与拼接 =====
去空格后: 'Hello, Java World!'
substring(7, 11): Java
拼接: Hello, Java World!!
join: A-B-C

===== 转换 =====
大写: HELLO, JAVA WORLD!
小写: hello, java world!
char数组第一个字符: H
String.valueOf(123): 123
String.valueOf(true): true

===== 替换与拆分 =====
替换逗号为竖线: apple | banana | orange | grape
拆分结果: apple banana orange grape

===== 正则 =====
'123' 是否全为数字: true
'abc123' 替换数字为*: abc*xyz

===== StringBuilder =====
《静夜思》
床前明月光，
疑是地上霜。
举头望明月，
低头思故乡。
反转后: 。乡故思头低
，月明望头举
。霜上地是疑
，光月明前床
《思夜静》

===== 格式化 =====
姓名：张三，年龄：20，分数：92.5
```

---

## 七、String 常用 API 速查表

```text
┌──────────────────────────────────────────────────────────┐
│                   String 常用方法速查                      │
├────────────────────┬─────────────────────────────────────┤
│   length()         │   获取字符串长度                      │
│   charAt(i)        │   获取指定索引字符                    │
│   toCharArray()    │   转 char 数组                        │
│   equals(s)        │   比较内容是否相等                     │
│   equalsIgnoreCase │   忽略大小写比较                      │
│   compareTo(s)     │   字典序比较                          │
│   indexOf(s)       │   查找子串首次出现位置                 │
│   lastIndexOf(s)   │   查找子串最后出现位置                 │
│   contains(s)      │   是否包含子串                        │
│   startsWith(s)    │   是否以指定前缀开头                   │
│   endsWith(s)      │   是否以指定后缀结尾                   │
│   substring(b,e)   │   截取 [b, e) 子串                    │
│   concat(s)        │   拼接                                │
│   join(delim, ..)  │   用分隔符拼接（静态）                 │
│   toUpperCase()    │   转大写                              │
│   toLowerCase()    │   转小写                              │
│   trim()           │   去首尾空格                          │
│   strip()          │   去首尾空白（含全角，JDK 11+）        │
│   replace(a,b)     │   替换字符/字符串                     │
│   replaceAll(r,s)  │   正则替换                            │
│   split(regex)     │   按正则拆分                          │
│   matches(regex)   │   是否匹配正则                        │
│   format(f,args)   │   格式化（静态）                      │
│   valueOf(x)       │   各种类型转字符串（静态）             │
│   repeat(n)        │   重复 n 次（JDK 11+）                │
│   isBlank()        │   是否空白（JDK 11+）                 │
│   indent(n)        │   缩进 n 格（JDK 11+）                │
│   intern()         │   从常量池获取                        │
├────────────────────┴─────────────────────────────────────┤
│                  StringBuilder 常用方法                    │
├────────────────────┬─────────────────────────────────────┤
│   append(x)        │   追加（返回自身，可链式调用）          │
│   insert(i, x)     │   插入                                │
│   delete(s, e)     │   删除 [s, e)                         │
│   reverse()        │   反转                                │
│   toString()       │   转 String                           │
└────────────────────┴─────────────────────────────────────┘
```

---

## 八、LeetCode 字符串相关经典题目

| 题目 | 难度 | 涉及知识点 |
|------|------|-----------|
| [344. 反转字符串](https://leetcode.cn/problems/reverse-string/) | 简单 | `toCharArray()`、双指针 |
| [541. 反转字符串 II](https://leetcode.cn/problems/reverse-string-ii/) | 简单 | 字符串操作 |
| [151. 反转字符串中的单词](https://leetcode.cn/problems/reverse-words-in-a-string/) | 中等 | `split()`、`trim()`、`join()` |
| [28. 找出字符串中第一个匹配项的下标](https://leetcode.cn/problems/find-the-index-of-the-first-occurrence-in-a-string/) | 简单 | `indexOf()`、KMP |
| [125. 验证回文串](https://leetcode.cn/problems/valid-palindrome/) | 简单 | `Character` 类、双指针 |
| [3. 无重复字符的最长子串](https://leetcode.cn/problems/longest-substring-without-repeating-characters/) | 中等 | 滑动窗口 |
| [5. 最长回文子串](https://leetcode.cn/problems/longest-palindromic-substring/) | 中等 | 中心扩展法、动态规划 |
| [14. 最长公共前缀](https://leetcode.cn/problems/longest-common-prefix/) | 简单 | 字符串比较 |

---

> **提示：** 字符串题目在面试中出镜率极高，务必熟练掌握以上所有 API 的用法。尤其注意 `==` 与 `equals()` 的区别、`StringBuilder` 的性能优势、以及正则表达式的常见用法。
