# Python 实用入门与 AI 开发：语法、API、并发及工程实践

> 这份笔记的目标读者：想用 Python 做 AI 开发的初学者，以及需要随时查语法、查工程实践的开发者。  
> 建议版本：Python 3.11+。示例主要使用现代类型标注、`asyncio.TaskGroup` 等语法。  
> 阅读方式：第一次学习按顺序读第 0~12 章打基础；做项目时对照第 13~30 章；想快速了解 AI 开发，先读第 31~33 章再回头补基础。第 34 章是语法速查表，第 36 章是术语表，第 37 章是常见问题。  
> 代码块后面的“输出”是典型运行结果；涉及并发的输出顺序可能变化。示例中的 `example.com`、`your-model` 等是占位内容，运行前必须替换。

### 怎么用这份笔记

- **零基础入门**：从第 0 章安装环境开始，第 1~12 章是语言基础，多数章节末尾有“本章练习”，做完再继续；
- **当手册查**：直接跳目录找对应小节，第 34 章有语法速查表；
- **做 AI 项目**：先读第 31~33 章理解 Token、RAG、Agent 三个核心概念，再对照第 16~30 章的工程实践动手实现；
- **遇到问题**：先看第 37 章常见问题，再把报错信息复制到搜索引擎或 AI 工具中搜索。

## 目录

- [0. 准备工作：安装 Python 与开发环境](#0-准备工作安装-python-与开发环境)
- [1. 从第一行代码理解 Python](#1-从第一行代码理解-python)
- [2. 变量、对象、基本类型与运算符](#2-变量对象基本类型与运算符)
- [3. 字符串：从创建到文本处理](#3-字符串从创建到文本处理)
- [4. 容器：list、tuple、dict、set](#4-容器listtupledictset)
- [5. 条件、循环与模式匹配](#5-条件循环与模式匹配)
- [6. 函数](#6-函数)
- [7. 推导式、迭代器与生成器](#7-推导式迭代器与生成器)
- [8. 异常与资源管理](#8-异常与资源管理)
- [9. 类、dataclass 与协议](#9-类dataclass-与协议)
- [10. 类型标注](#10-类型标注)
- [11. 模块、包与虚拟环境](#11-模块包与虚拟环境)
- [12. 文件、路径、JSON 和 CSV](#12-文件路径json-和-csv)
- [13. 常用标准库](#13-常用标准库)
- [14. 装饰器、闭包与上下文管理器](#14-装饰器闭包与上下文管理器)
- [15. Python 中容易踩的坑](#15-python-中容易踩的坑)
- [16. HTTP 与 API 基础](#16-http-与-api-基础)
- [17. 调用大模型 API](#17-调用大模型-api)
- [18. 数据校验：Pydantic](#18-数据校验pydantic)
- [19. 使用 FastAPI 编写 AI 服务](#19-使用-fastapi-编写-ai-服务)
- [20. 并发模型总览](#20-并发模型总览)
- [21. 多线程](#21-多线程)
- [22. 多进程](#22-多进程)
- [23. asyncio 异步编程](#23-asyncio-异步编程)
- [24. 并发控制、超时、重试与限流](#24-并发控制超时重试与限流)
- [25. 流式响应与生成器](#25-流式响应与生成器)
- [26. AI 数据处理常用工具](#26-ai-数据处理常用工具)
- [27. 配置、日志与 Secret](#27-配置日志与-secret)
- [28. 测试、Mock 与质量工具](#28-测试mock-与质量工具)
- [29. AI 项目结构](#29-ai-项目结构)
- [30. 完整小项目：并发模型客户端](#30-完整小项目并发模型客户端)
- [31. 理解大模型 API 的核心概念](#31-理解大模型-api-的核心概念)
- [32. RAG 入门：用 Python 搭建文档问答](#32-rag-入门用-python-搭建文档问答)
- [33. Agent 入门：工具调用与循环](#33-agent-入门工具调用与循环)
- [34. 语法速查表](#34-语法速查表)
- [35. 学习路线与关联笔记](#35-学习路线与关联笔记)
- [36. AI 术语表](#36-ai-术语表)
- [37. 常见问题与故障排查](#37-常见问题与故障排查)

---

## 0. 准备工作：安装 Python 与开发环境

很多初学者卡在“第一行代码”之前：不知道装哪个版本、用哪个编辑器、报错怎么处理。先把环境准备好，后面的学习才会顺畅。

### 0.1 安装 Python

1. 到 [python.org/downloads](https://www.python.org/downloads/) 下载最新稳定版（建议 3.11 或更高）；
2. Windows 安装时**务必勾选 “Add python.exe to PATH”**，否则命令行找不到 `python`；
3. 安装完成后，打开终端（Windows 用 PowerShell），输入：

```powershell
python --version
```

能输出版本号（如 `Python 3.12.4`）就说明安装成功。如果提示“不是内部或外部命令”，通常是 PATH 没有配置好，重新安装并勾选 PATH，或搜索“python 添加 PATH”按步骤配置。

### 0.2 选择编辑器

| 工具 | 适合 | 说明 |
|---|---|---|
| VS Code | 大多数入门者 | 安装官方 Python 扩展后支持补全、调试 |
| PyCharm | 写较大项目 | 功能全，社区版免费 |
| Jupyter Notebook | 实验和教学 | 单元格逐个运行，适合边学边试 |
| IDLE | 临时验证 | Python 自带，最简单 |

正式项目代码建议保存在 `.py` 文件中用 VS Code 或 PyCharm 编写；Jupyter 适合探索，但不要只依赖它。

### 0.3 运行第一个程序

新建文件 `hello.py`，写入：

```python
print("你好，Python")
```

在终端运行：

```powershell
python hello.py
```

终端会输出 `你好，Python`。如果输出乱码，通常是终端编码问题，Windows 可以在 PowerShell 中先执行：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

也可以右键终端标题栏 → 属性，把代码页改为 UTF-8。Python 3 源码默认就是 UTF-8，一般不需要在文件里加编码声明。

### 0.4 安装第三方库

Python 自带标准库，但 AI 开发常用 `httpx`、`fastapi`、`pydantic` 等第三方库，用 pip 安装：

```powershell
python -m pip install httpx fastapi uvicorn pydantic pytest
python -m pip install numpy pandas        # 数据处理常用
```

- 推荐用 `python -m pip` 而不是直接 `pip`，避免装到了错误的 Python；
- 每个项目建议使用独立虚拟环境（见 11.3），避免依赖互相冲突；
- 安装失败先看报错：网络问题可换镜像源，权限问题可加 `--user`。

### 0.5 遇到报错怎么办

1. 认真读最后一行报错：它告诉你**发生了什么**和**发生在哪一行**；
2. 从报错里找到你自己写的文件名和行号；
3. 把报错信息完整复制到搜索引擎或 AI 工具中，附带最小可复现代码；
4. 不要盲目重装、乱改，先理解根因（第 1.9 节有详细方法）。

> **本笔记所有代码，只要没有特殊说明，都假设你已经安装好依赖，并且在正确的目录下运行。**

---

## 1. 从第一行代码理解 Python

学习 Python 时，先不要急着记 API。需要先看懂：一行代码由什么组成、解释器按什么顺序执行、名字和值是什么关系。

- Python 程序由语句组成，语句中可以包含表达式；
- 表达式会计算出值；
- 赋值让一个名字绑定到对象；
- 缩进决定代码块；
- 程序通常自上而下执行，条件、循环和函数会改变流程。

> **给初学者的提示**：这一章讲的是“代码怎么被理解”，不是要背的 API。装好环境后（见第 0 章），把每个例子都亲手敲一遍、改一改，比只读一遍有用得多。

### 1.1 第一段程序逐行解释

```python
name = "小明"
age = 20
next_age = age + 1
print(f"{name} 明年 {next_age} 岁")
```

解释器依次执行：

1. 创建字符串 `"小明"`，让名字 `name` 指向它；
2. 创建整数 `20`，让 `age` 指向它；
3. 读取 `age`，计算 `20 + 1`，把结果绑定给 `next_age`；
4. 计算 f-string，再调用 `print()`。

`=` 是赋值，不是数学等式。`age = age + 1` 表示先计算右边，再让 `age` 指向新结果。

### 1.2 表达式、语句与代码块

表达式会产生值：

```python
1 + 2
len("Python")
score >= 60
name.upper()
```

语句让程序执行动作，例如赋值、导入、条件、循环和函数定义：

```python
total = 1 + 2
import math

if total > 0:
    print(total)
```

`1 + 2` 是表达式，`total = 1 + 2` 整体是赋值语句。通常一行写一条语句。虽然可以写 `a = 1; b = 2`，但不推荐。

### 1.3 缩进、冒号与 `pass`

Python 用缩进表示层级，惯例是每层 4 个空格：

```python
score = 85

if score >= 60:
    result = "通过"
    print("条件成立")
else:
    result = "未通过"

print(result)
```

- `if`、`else` 行末的冒号表示接下来开始代码块；
- 两条缩进语句属于 `if`；
- 最后的 `print(result)` 没有缩进，因此总会执行。

不要混用 Tab 和空格。暂时需要空代码块时使用 `pass`：

```python
if score < 0:
    pass  # 以后补充错误处理
```

`pass` 不执行任何动作，只满足“代码块不能为空”的语法要求。

### 1.4 注释与文档字符串

单行注释以 `#` 开始：

```python
# 解释为什么使用较低温度
temperature = 0.2  # 行尾注释
```

注释应解释原因和约束，不要机械复述代码。

函数、类或模块开头的三引号字符串是文档字符串：

```python
def add(a: int, b: int) -> int:
    """返回两个整数之和。"""
    return a + b
```

三引号字符串本质仍是字符串，不应普遍代替多行注释。

### 1.5 标识符、关键字与命名

名称可包含字母、数字、下划线，但不能以数字开头，也不能使用关键字：

```python
user_name = "Ada"    # 合法
model2 = "small"     # 合法
_private = "内部用"  # 合法
# 2model = "x"        # 非法
# class = "x"         # 非法
```

```python
import keyword

print(keyword.iskeyword("class"))  # True
```

命名约定：

| 对象 | 约定 | 示例 |
|---|---|---|
| 变量、函数、模块 | 小写蛇形 | `user_name`、`load_model` |
| 类 | 大驼峰 | `ModelClient` |
| 常量 | 全大写蛇形 | `MAX_RETRIES` |
| 内部实现 | 单下划线开头 | `_parse_response` |

Python 区分大小写。不要把变量命名为 `list`、`str`、`dict` 等，否则会遮蔽内置对象。

### 1.6 换行、括号与尾逗号

括号内部可以自然换行：

```python
config = {
    "model": "demo",
    "temperature": 0.2,
    "max_tokens": 1024,
}

total = (
    10
    + 20
    + 30
)
```

函数参数也可逐行书写：

```python
response = request_model(
    prompt="解释 Python",
    temperature=0.2,
    max_tokens=512,
)
```

尾逗号便于追加内容和格式化。行末反斜杠也能续行，但容易因空格出错，优先使用括号。

### 1.7 Python 的运行方式

CPython 通常先把源码编译成字节码，再由虚拟机执行：

```text
source.py -> 解析/编译 -> bytecode -> Python VM
```

```powershell
python app.py
python -m package.module
python -c "print(1 + 2)"
```

- 直接运行脚本适合简单入口；
- `python -m` 按模块运行，项目内导入通常更稳定；
- `python -c` 适合临时验证；
- 直接输入 `python` 可进入 REPL。

```pycon
>>> 1 + 2
3
>>> "Ada".upper()
'ADA'
```

Jupyter Notebook 适合实验，但单元格执行顺序可能与页面顺序不同。正式逻辑应整理到 `.py` 文件中。

第一次看到 `import math` 时，可以这样理解：`import` 会加载另一个 Python 模块，之后通过 `模块名.名字` 使用其中的对象；`from pathlib import Path` 则是把模块里的某个名字直接引入当前作用域；`as` 可以给模块或名字取别名：

```python
import numpy as np
from pathlib import Path

print(Path(".").resolve())
```

不确定某个对象支持哪些操作时，可以在 REPL 中用 `dir(obj)` 列出名字、用 `help(obj)` 或 `help(obj.method)` 查看文档：

```python
text = "hello"
print("upper" in dir(text))  # True
```

`help(str.upper)` 会在交互环境中显示该方法的说明。

### 1.8 `print()` 与 `input()`

`print()` 默认用空格分隔多个对象，并在末尾换行：

```python
print("模型", "开始", 3)
print("a", "b", "c", sep=",", end="!\n")
```

`input()` 返回值始终是字符串：

```python
raw_age = input("请输入年龄：")
age = int(raw_age)
print(f"明年 {age + 1} 岁")
```

即使输入 20，`raw_age` 仍是 `"20"`，需要显式转换。服务端程序通常从 HTTP 请求、配置或文件获得数据。

### 1.9 怎样阅读错误信息

```python
count = "3"
print(count + 1)
```

会得到类似：

```text
TypeError: can only concatenate str (not "int") to str
```

阅读 Traceback：

1. 先看最后一行的异常类型和描述；
2. 找到指向自己代码的最后一个文件和行号；
3. 检查该行参与运算的值与类型；
4. 必要时再沿调用链向上分析。

不要一看到异常就用 `try/except` 吞掉，应先理解根因。

### 1.10 本章练习

1. 用 `print()` 输出 `"你好，Python"`，再用 f-string 输出你的名字和明年年龄；
2. 把 `"3"` 转换成整数后加 1，观察不转换时会发生什么错误；
3. 打开 REPL，用 `dir("hello")` 找出 3 个字符串方法，再用 `help()` 查看其中一个的说明；
4. 故意写一个 `if` 语句但忘记缩进，运行后阅读报错信息，看它提示在哪一行。

---

## 2. 变量、对象、基本类型与运算符

### 2.1 变量是名字，对象才有类型

Python 的变量更准确地说是“名字”。赋值让名字绑定到对象：

```python
x = 10
print(type(x))  # <class 'int'>

x = "ten"
print(type(x))  # <class 'str'>
```

名字 `x` 没有被永久声明成整数，它可以重新绑定到字符串。动态类型不等于没有类型：对象始终有类型，类型错误通常在运行到相关代码时出现。

> **初学提示**：可以把“变量”想成贴在盒子上的便利贴：贴纸换到别的盒子上，原来的盒子还在。判断某个操作会不会影响别的变量，问自己：它改的是“盒子里的内容”，还是只换了“便利贴”？

查看和判断类型：

```python
value = 42

print(type(value))
print(isinstance(value, int))
print(isinstance(value, (int, float)))
```

业务代码通常优先使用 `isinstance()`，因为它能够正确处理继承关系。

### 2.2 赋值、连续赋值与解包

普通赋值：

```python
name = "Ada"
age = 20
```

同时赋值：

```python
x, y = 10, 20
print(x, y)
```

右侧先产生两个值，再按位置解包。数量不匹配会抛出 `ValueError`。

交换变量无需临时变量：

```python
x, y = y, x
```

星号收集剩余元素：

```python
first, *middle, last = [10, 20, 30, 40, 50]

print(first)   # 10
print(middle)  # [20, 30, 40]
print(last)    # 50
```

连续赋值让多个名字指向同一个对象：

```python
a = b = []
a.append(1)
print(b)  # [1]
```

若希望两个独立列表，应分别创建：

```python
a = []
b = []
```

### 2.3 常见基本类型

| 类型 | 示例 | 主要含义 |
|---|---|---|
| `int` | `42` | 整数，通常可任意增大 |
| `float` | `3.14` | 双精度浮点数 |
| `bool` | `True`、`False` | 逻辑真假 |
| `NoneType` | `None` | 没有值、尚无结果 |
| `str` | `"hello"` | Unicode 文本 |
| `bytes` | `b"abc"` | 原始字节 |
| `complex` | `1 + 2j` | 复数，科学计算中可能使用 |

Python 还有 list、tuple、dict、set 等容器类型，后文单独讲解。

### 2.4 整数 `int`

```python
count = 42
large = 10**100
binary = 0b1010   # 二进制，等于 10
octal = 0o12      # 八进制，等于 10
hex_value = 0xFF  # 十六进制，等于 255
```

数字中的下划线只为提高可读性：

```python
population = 1_400_000_000
token_limit = 128_000
```

Python 整数通常没有固定 32 位或 64 位上限，只受可用内存约束。

### 2.5 浮点数与精度

```python
temperature = 0.7
scientific = 1.5e3  # 1500.0
```

许多十进制小数无法用二进制浮点数精确表示：

```python
print(0.1 + 0.2)
# 0.30000000000000004
```

比较计算结果时使用容差：

```python
import math

print(math.isclose(0.1 + 0.2, 0.3))  # True
```

金融等需要精确十进制的场景可用 `Decimal`，并从字符串构造：

```python
from decimal import Decimal

price = Decimal("0.1")
tax = Decimal("0.2")
print(price + tax)  # 0.3
```

AI 张量计算中的微小浮点误差很常见，不应假定不同硬件和并行顺序得到逐位完全相同的结果。

真实数据还会遇到无穷和 NaN。`float("inf")` 表示正无穷，`float("nan")` 表示“不是一个数”，例如解析缺失值或非法数值时可能出现：

```python
import math

print(math.isfinite(1.0))       # True
print(math.isnan(float("nan")))  # True
print(math.isinf(float("inf")))  # True
```

NaN 有一个容易踩的规则：`nan == nan` 为 False，所以不要用 `==` 判断 NaN，要用 `math.isnan()`。另外 `float("nan")` 会成功而不是报错，外部数据转 float 后应检查业务上是否允许 NaN，避免把缺失值当作普通数字继续计算。

### 2.6 `bool` 与 `None`

布尔值只有 `True` 和 `False`，首字母必须大写：

```python
is_ready = 3 > 1
print(is_ready)  # True
```

`None` 表示“没有值”或“尚无结果”，它不是空字符串、0 或 False：

```python
result = None

if result is None:
    print("暂时没有结果")
```

判断 None 使用 `is None` 或 `is not None`。函数没有显式 `return` 时返回 None：

```python
def log_message(message):
    print(message)

returned = log_message("hello")
print(returned)  # None
```

### 2.7 算术运算符

| 运算符 | 含义 | 示例 |
|---|---|---|
| `+` | 加 | `7 + 3` 为 `10` |
| `-` | 减 | `7 - 3` 为 `4` |
| `*` | 乘 | `7 * 3` 为 `21` |
| `/` | 真除法，结果通常为 float | `7 / 2` 为 `3.5` |
| `//` | 向下取整除法 | `7 // 2` 为 `3` |
| `%` | 取模 | `7 % 2` 为 `1` |
| `**` | 幂 | `2 ** 3` 为 `8` |

`//` 朝负无穷方向取整，不是简单去掉小数：

```python
print(-7 // 2)  # -4
print(-7 % 2)   # 1
```

同时获得商和余数：

```python
quotient, remainder = divmod(17, 5)
print(quotient, remainder)  # 3 2
```

增强赋值：

```python
count = 10
count += 1
count *= 2
```

`count += 1` 通常相当于 `count = count + 1`。但列表的 `+=` 可能原地修改对象，涉及共享引用时要特别注意。

常用数值工具：

```python
print(abs(-5))          # 5
print(round(3.14159, 2))  # 3.14
print(pow(2, 10))       # 1024
print(min(3, 1, 2))     # 1
print(max([3, 1, 2]))   # 3
print(sum([3, 1, 2]))   # 6
```

`round()` 采用银行家舍入等二进制浮点规则，不要用它代替 `Decimal` 做金融精度计算。

当表达式包含多个运算符时，可以记住最常用的优先级：括号 > 幂 > 正负号 > 乘除取模 > 加减 > 比较 > `not` > `and` > `or`。例如 `2 + 3 * 4 == 14`，而 `(2 + 3) * 4 == 20`。不确定时使用括号，代码会更容易读懂。

### 2.8 比较、成员与链式比较

```python
a == b  # 值相等
a != b  # 值不等
a < b
a <= b
a > b
a >= b
```

链式比较：

```python
temperature = 0.7
print(0 <= temperature <= 2)  # True
```

它相当于两个比较通过 `and` 连接，但中间表达式只求值一次。

成员运算：

```python
print("py" in "python")           # True
print("model" in {"model": "x"})  # True，字典默认检查键
print(5 not in [1, 2, 3])         # True
```

### 2.9 `==` 与 `is`

- `==` 比较值；
- `is` 比较是否为同一个对象。

```python
a = [1, 2]
b = [1, 2]
c = a

print(a == b)  # True
print(a is b)  # False
print(a is c)  # True
```

不要用 `is` 比较普通整数和字符串。解释器可能复用某些小对象，但这是实现细节。除 `is None` 等单例判断外，值比较使用 `==`。

### 2.10 逻辑运算与短路

逻辑运算符是 `and`、`or`、`not`：

```python
age = 20
has_ticket = True
can_enter = age >= 18 and has_ticket
```

它们会短路：

```python
user = None

if user is not None and user.is_active:
    print("有效用户")
```

左边为 False 后，右边不再执行，因此不会访问 `None.is_active`。

`and` 和 `or` 返回某个操作数，不保证返回 bool：

```python
display_name = "" or "匿名用户"
print(display_name)  # 匿名用户

config = {"timeout": 30}
timeout = config and config["timeout"]
print(timeout)  # 30
```

当 0 或空字符串本身是合法值时，不要滥用这种默认值写法。

优先级大致为：算术 > 比较 > `not` > `and` > `or`。不确定时用括号表达意图。

### 2.11 真值判断

条件中视为 False 的常见对象：

- `None`、`False`；
- 数值 0；
- 空字符串；
- 空列表、元组、字典、集合。

其余对象通常为 True：

```python
items = []

if not items:
    print("列表为空")
```

“未提供”和“提供了空值”有时不同：

```python
value = ""

if value is None:
    print("没有提供")
else:
    print("已经提供，即使是空字符串")
```

### 2.12 类型转换

```python
count = int("42")
ratio = float("0.75")
text = str(123)
enabled = bool(1)
numbers = list((1, 2, 3))
unique = set([1, 1, 2])
```

非法转换会抛出异常：

```python
# int("3.14")  # ValueError
# int("abc")   # ValueError
```

指定进制：

```python
print(int("1010", 2))  # 10
print(int("ff", 16))   # 255
```

特别注意：

```python
print(bool("False"))  # True
```

任何非空字符串都为真。解析配置字符串应显式判断：

```python
raw = "false"
enabled = raw.strip().lower() in {"1", "true", "yes", "on"}
```

### 2.13 可变与不可变

常见不可变类型：int、float、bool、str、bytes、tuple、frozenset。

常见可变类型：list、dict、set 和大多数自定义类实例。

```python
text = "hello"
new_text = text.upper()

print(text)      # hello
print(new_text)  # HELLO
```

字符串方法返回新对象，原字符串不变。

```python
items = [1, 2]
items.append(3)
print(items)  # [1, 2, 3]
```

列表可以原地改变。

### 2.14 引用与共享修改

```python
a = [1, 2]
b = a
b.append(3)

print(a)       # [1, 2, 3]
print(a is b)  # True
```

`b = a` 没有复制列表，只增加一个指向同一对象的名字。

### 2.15 浅复制与深复制

浅复制创建新外层容器，但嵌套对象仍共享：

```python
original = [1, ["a", "b"]]
shallow = original.copy()

shallow[0] = 99
shallow[1].append("c")

print(original)  # [1, ['a', 'b', 'c']]
print(shallow)   # [99, ['a', 'b', 'c']]
```

常见浅复制写法：

```python
copy1 = original.copy()
copy2 = list(original)
copy3 = original[:]
```

深复制递归复制嵌套对象：

```python
import copy

original = [1, ["a", "b"]]
deep = copy.deepcopy(original)
deep[1].append("c")

print(original)  # [1, ['a', 'b']]
print(deep)      # [1, ['a', 'b', 'c']]
```

深复制大型模型、数组、连接和锁可能昂贵或不合理。NumPy 使用 `array.copy()`，PyTorch 张量常使用 `tensor.clone()`。

### 2.16 `del` 删除的是名字或元素

```python
value = [1, 2, 3]
alias = value
del value

print(alias)  # 对象仍存在
```

`del value` 删除名字绑定，不保证对象立刻销毁，因为 `alias` 仍引用它。`del items[0]` 则从列表中删除一个元素；`del mapping["key"]` 删除字典键。

---

## 3. 字符串：从创建到文本处理

`str` 表示 Unicode 文本。字符串是不可变序列：可以读取字符、切片和调用方法，但这些操作不会原地修改原字符串。

### 3.1 单引号、双引号与三引号

单引号和双引号没有类型差异，选择能减少转义的一种：

```python
message1 = '他说："你好"'
message2 = "I'm learning Python"
```

三引号字符串可以跨多行：

```python
prompt = """你是一个代码助手。
请解释下面的 Python 代码。
回答要简洁。"""
```

换行会成为内容的一部分。若只想让源码分行、运行时不换行，可利用括号内相邻字符串自动拼接：

```python
message = (
    "这是一段很长的文本，"
    "源码中分成多行，"
    "运行时仍是连续字符串。"
)
```

### 3.2 转义字符与 `repr()`

| 写法 | 含义 |
|---|---|
| `\n` | 换行 |
| `\t` | 制表符 |
| `\\` | 一个反斜杠 |
| `\"` | 双引号 |
| `\'` | 单引号 |
| `\r` | 回车 |
| `\u4f60` | Unicode 转义，`\u` 后跟 4 位十六进制表示一个字符 |

例如 `"\u4f60"` 与 `"你"` 是同一个字符串。打印日志或处理外部文本时，转义符也可能以 `\\u` 的字面形式出现（即源码里是两个字符：反斜杠和 u），需要区分“真正换行”与“反斜杠加字母 n”。

```python
text = "第一行\n第二行"
print(text)
print(repr(text))
```

`print()` 显示真实换行，`repr()` 显示适合调试的表示，例如 `'第一行\n第二行'`。

### 3.3 原始字符串

字符串前加 `r` 后，大多数反斜杠不再作为转义：

```python
windows_path = r"C:\new_folder\test.txt"
pattern = r"\d+\.\d+"
```

常用于 Windows 路径和正则表达式。原始字符串不能以单个反斜杠结尾。路径处理更推荐 `pathlib.Path`。

### 3.4 长度、索引和负索引

```python
word = "Python"

print(len(word))  # 6
print(word[0])    # P
print(word[1])    # y
print(word[-1])   # n
print(word[-2])   # o
```

索引从 0 开始，负索引从末尾开始。越界索引抛出 `IndexError`。

字符串不可变，不能写 `word[0] = "J"`。可以构造新字符串：

```python
new_word = "J" + word[1:]
print(new_word)  # Jython
```

### 3.5 切片 `[start:stop:step]`

切片包含 start，不包含 stop：

```python
word = "Python"

print(word[0:2])   # Py
print(word[2:])    # thon
print(word[:4])    # Pyth
print(word[:])     # Python
print(word[::2])   # Pto
print(word[::-1])  # nohtyP
```

省略起点表示从头开始，省略终点表示到末尾，省略步长表示 1。切片越界通常不报错，而是返回可取得的部分。

### 3.6 查找、计数与包含判断

```python
text = "  Hello, Python  "

print(text.startswith("  He"))  # True
print(text.endswith("  "))      # True
print(text.find("Python"))      # 起始下标
print(text.find("Java"))        # -1
print(text.count("o"))          # 2
print("Python" in text)         # True
```

`find()` 找不到返回 -1；`index()` 找不到抛出 `ValueError`。只判断是否包含时，使用 `in` 最清晰。

### 3.7 大小写和空白处理

字符串方法返回新字符串：

```python
text = "  Hello, Python  "

clean = text.strip()
lower = clean.lower()
upper = clean.upper()

print(clean)
print(lower)
print(upper)
print(text)  # 原字符串没变
```

- `strip()` 只处理两端空白，不删除中间空格；
- `lstrip()`、`rstrip()` 分别处理左侧和右侧；
- `casefold()` 比 `lower()` 更适合 Unicode 的不区分大小写比较。

其他常用方法：`title()` 把每个单词首字母大写，`capitalize()` 只大写首个字符，`splitlines()` 按换行拆分成列表（`keepends=True` 可保留换行符）：

```python
print("hello world".title())      # Hello World
print("hello".capitalize())       # Hello
print("a\nb".splitlines())        # ['a', 'b']
```

`strip(chars)` 参数是字符集合，不是完整前后缀。移除确定前后缀使用：

```python
print("report.json".removesuffix(".json"))
print("https://example.com".removeprefix("https://"))
```

### 3.8 拆分和连接

```python
line = "model,temperature,max_tokens"
fields = line.split(",")
print(fields)
```

不传分隔符时，`split()` 按连续空白拆分：

```python
print("  one   two\nthree ".split())
# ['one', 'two', 'three']
```

限制拆分次数：

```python
key, value = "model=gpt=demo".split("=", maxsplit=1)
```

`partition()` 始终返回前部、分隔符、后部：

```python
before, sep, after = "name=Ada".partition("=")
```

连接字符串由分隔符调用 `join()`：

```python
parts = ["模型", "正在", "生成"]
print(" ".join(parts))
```

元素必须全是字符串：

```python
numbers = [1, 2, 3]
print(",".join(str(n) for n in numbers))
```

大量文本应先收集再 `join()`，避免循环中反复创建临时字符串。

### 3.9 替换与简单字符判断

```python
text = "Python is good. Python is readable."

print(text.replace("Python", "Python 3", 1))
print("123".isdigit())       # True
print("abc".isalpha())       # True
print("abc123".isalnum())    # True
print("   ".isspace())       # True
```

`replace()` 的第三个参数限制替换次数。字符判断适合简单检查，真实日期、金额和 API 数据需要严格解析与校验。

### 3.10 f-string 详解

```python
model = "demo-model"
tokens = 1234
cost = 0.05678

print(f"模型={model}, tokens={tokens:,}, cost=${cost:.3f}")
```

常用格式：

| 语法 | 含义 | 示例 |
|---|---|---|
| `{x:.2f}` | 两位小数 | `3.14` |
| `{x:,}` | 千位分隔 | `1,000,000` |
| `{x:.1%}` | 百分比 | `25.6%` |
| `{x:>10}` | 右对齐，宽度 10 | `"        hi"` |
| `{x:<10}` | 左对齐，宽度 10 | `"hi        "` |
| `{x:^10}` | 居中，宽度 10 | `"    hi    "` |
| `{x=}` | 显示变量名和值 | `x=5` |

花括号内可以放表达式：

```python
items = [10, 20, 30]
print(f"数量={len(items)}, 总和={sum(items)}")
```

f-string 里使用字典下标时，内层引号不能与外层相同，否则会提前结束字符串：

```python
record = {"name": "Ada"}
print(f"{record['name']}")   # 正确：内层用单引号
# print(f"{record["name"]}")  # 语法错误
```

字面量花括号写成 `{{` 和 `}}`。`!r` 使用 `repr()`，适合调试隐藏字符：

```python
name = " Ada\n"
print(f"{name!r}")
```

### 3.11 `str` 与 `bytes`

- str 表示 Unicode 文本；
- bytes 表示原始字节；
- 编码把 str 转为 bytes；
- 解码把 bytes 转回 str。

```python
text = "你好"
data = text.encode("utf-8")

print(data)
print(data.decode("utf-8"))
print(len(text))  # 2 个字符
print(len(data))  # 6 个字节
```

网络、图片和压缩文件底层使用 bytes，JSON 和业务文本通常使用 str。编码不一致会产生 `UnicodeDecodeError` 或乱码。

读取文本文件应显式指定编码：

```python
from pathlib import Path

text = Path("data.txt").read_text(encoding="utf-8")
```

### 3.12 常见错误

1. 以为 `strip()` 会删除所有空格——它只处理两端；
2. 调用 `text.upper()` 后忘记接收结果——字符串不可变；
3. 混用 str 与 bytes；
4. 手工拼 JSON——应使用 `json.dumps()`；
5. 用 `split(",")` 解析完整 CSV——应使用 `csv` 模块；
6. 把用户输入直接拼入 SQL——应使用参数化查询。

### 3.13 本章练习

1. 把 `"  python,AI,agent  "` 去掉两端空白后按逗号拆分，得到 `["python", "AI", "agent"]`；
2. 用 f-string 输出：一个数字带千位分隔、一个小数保留 2 位、一个百分比；
3. 把 `"hello world"` 中所有空格替换为 `_`，并统计字母 `o` 出现次数；
4. 写出 `"你好".encode("utf-8")` 的长度，并解释为什么和字符数不同。

---

## 4. 容器：list、tuple、dict、set

容器用于把多个对象组织在一起。选择容器前先问：

- 是否需要保持顺序？
- 是否允许重复？
- 是否需要按键快速查找？
- 是否需要修改？
- 元素是否需要去重？

### 4.1 `list`：有序、可变、允许重复

创建列表：

```python
empty = []
numbers = [10, 20, 30]
mixed = [1, "hello", True]  # 语法允许，但业务数据通常保持同类
chars = list("abc")         # ['a', 'b', 'c']
```

列表按插入顺序保存元素，元素可重复。

#### 4.1.1 读取、索引与切片

```python
models = ["small", "medium", "large"]

print(models[0])     # small
print(models[-1])    # large
print(models[1:])    # ['medium', 'large']
print(len(models))   # 3
print("small" in models)
```

索引越界会抛出 `IndexError`，切片越界通常不会。

#### 4.1.2 修改元素与切片

```python
numbers = [10, 20, 30]
numbers[1] = 99
print(numbers)  # [10, 99, 30]
```

切片赋值可以替换任意数量的元素：

```python
numbers[1:2] = [40, 50]
print(numbers)  # [10, 40, 50, 30]
```

这是原地修改原列表，不会创建新列表绑定给变量。

#### 4.1.3 添加元素

```python
items = ["a"]
items.append("b")          # 把一个对象作为一个元素加入
items.extend(["c", "d"])   # 逐个加入可迭代对象中的元素
items.insert(1, "x")       # 在下标 1 前插入
```

`append()` 与 `extend()` 的区别：

```python
a = [1, 2]
a.append([3, 4])
print(a)  # [1, 2, [3, 4]]

b = [1, 2]
b.extend([3, 4])
print(b)  # [1, 2, 3, 4]
```

这些方法原地修改列表，返回值是 None：

```python
items = [1, 2]
result = items.append(3)

print(result)  # None
print(items)   # [1, 2, 3]
```

因此不要写 `items = items.append(3)`，否则 items 会变成 None。

#### 4.1.4 删除元素

```python
items = ["a", "b", "c", "b"]

items.remove("b")   # 删除第一个匹配值，找不到抛 ValueError
last = items.pop()  # 删除并返回最后一个
first = items.pop(0)
del items[0]        # 按下标删除
items.clear()       # 清空
```

频繁从列表头部 `pop(0)` 需要移动后续元素，效率较低。队列应使用 `collections.deque`。

#### 4.1.5 查找与计数

```python
items = ["a", "b", "a"]

print(items.count("a"))  # 2
print(items.index("b"))  # 1
```

`index()` 找不到会抛 `ValueError`。只判断存在性使用 `in`。

#### 4.1.6 排序、反转和 key

`list.sort()` 原地排序并返回 None；`sorted()` 接收任意可迭代对象，返回新列表：

```python
numbers = [3, 1, 2]

new_numbers = sorted(numbers)
print(numbers)      # [3, 1, 2]
print(new_numbers)  # [1, 2, 3]

numbers.sort(reverse=True)
print(numbers)      # [3, 2, 1]
```

按字段排序：

```python
users = [
    {"name": "Ada", "score": 91},
    {"name": "Bob", "score": 85},
]

users.sort(key=lambda user: user["score"], reverse=True)
```

排序是稳定的：key 相等的元素保留原相对顺序。复杂逻辑可定义普通函数替代 lambda。

多字段排序让 key 返回元组，元组按顺序比较：

```python
users.sort(key=lambda user: (user["department"], user["score"]))
```

若某个字段要降序，通常先升序排次要字段，再对目标字段使用 `reverse=True`；更可控的做法是让 key 返回负数值。

#### 4.1.7 `+`、`*` 与嵌套列表陷阱

```python
print([1, 2] + [3, 4])
print(["a"] * 3)
```

创建二维列表时不要写：

```python
bad_grid = [[0] * 3] * 2
bad_grid[0][0] = 1
print(bad_grid)  # 两行都被修改
```

两个外层元素引用同一个内层列表。正确写法：

```python
grid = [[0] * 3 for _ in range(2)]
```

### 4.2 `tuple`：有序、不可变、允许重复

```python
point = (10, 20)
shape = (32, 3, 224, 224)
empty = ()
single = (1,)  # 单元素元组必须有逗号
```

括号常可省略，逗号才是形成元组的关键：

```python
pair = 10, 20
```

元组支持索引、切片、`len()`、`count()`、`index()`，但不能修改元素。

解包：

```python
batch, channels, height, width = shape
```

忽略不关心的值通常用 `_`：

```python
name, _, score = ("Ada", 20, 95)
```

扩展解包：

```python
first, *rest = (1, 2, 3, 4)
```

元组本身不可变，但若内部包含列表，该列表仍可变：

```python
record = (1, ["a"])
record[1].append("b")  # 合法
```

元组适合固定结构、函数返回多个值和字典键，但业务字段多时 dataclass 或命名结构更清晰。

### 4.3 `dict`：键值映射

创建字典：

```python
config = {
    "model": "demo",
    "temperature": 0.2,
    "max_tokens": 512,
}

empty = {}
from_pairs = dict([("a", 1), ("b", 2)])
from_keywords = dict(timeout=30, retries=2)
```

键必须可哈希且保持稳定，例如 str、int、tuple；list、dict、set 不能作键。

#### 4.3.1 读取键

```python
print(config["model"])
print(config.get("timeout"))
print(config.get("timeout", 30))
```

- `mapping[key]` 不存在时抛 `KeyError`；
- `get()` 不存在时返回 None 或给定默认值；
- `get()` 不会把默认值写入字典。

需要区分“键不存在”和“键存在但值为 None”：

```python
if "timeout" in config:
    print(config["timeout"])
```

#### 4.3.2 新增与更新

```python
config["timeout"] = 30
config["temperature"] = 0.1
config.update({"retries": 2, "timeout": 60})
```

`setdefault()` 在键不存在时写入默认值，并返回最终值：

```python
groups = {}
groups.setdefault("python", []).append("Ada")
```

简单场景可用，但批量分组更适合 `collections.defaultdict`。

#### 4.3.3 删除

```python
timeout = config.pop("timeout", 30)  # 删除并返回，可给默认值
key, value = config.popitem()        # 删除并返回最后插入项
del config["model"]                  # 不存在时抛 KeyError
config.clear()
```

#### 4.3.4 遍历

```python
config = {"model": "demo", "timeout": 30}

for key in config:
    print(key)

for value in config.values():
    print(value)

for key, value in config.items():
    print(key, value)
```

遍历过程中不要改变字典大小，否则可能抛 `RuntimeError`。若确实要删除，可先遍历 `list(config)` 或构造新字典。

Python 3.7+ 字典保留插入顺序，但不是自动按键排序。

`keys()`、`values()` 和 `items()` 返回的是“视图”而不是快照列表：它们会随字典变化自动更新，也不能直接用下标访问。需要按下标取值时先转成列表，例如 `list(config.items())[0]`。

#### 4.3.5 合并与覆盖顺序

```python
base = {"timeout": 30, "retries": 2}
override = {"timeout": 60}

final = base | override
print(final)  # timeout 为 60
```

后面的字典覆盖前面相同键。原字典不变。`base |= override` 会原地更新 base。

### 4.4 `set`：无重复元素集合

创建：

```python
empty = set()        # {} 是空字典，不是空集合
values = {1, 2, 3}
unique = set([1, 1, 2, 3])
```

集合不保证业务上可依赖的顺序。元素必须可哈希。

添加与删除：

```python
values.add(4)
values.update([5, 6])
values.remove(2)   # 不存在抛 KeyError
values.discard(9)  # 不存在也不报错
item = values.pop()
values.clear()
```

集合运算：

```python
a = {"read", "write"}
b = {"read", "search"}

print(a | b)  # 并集
print(a & b)  # 交集
print(a - b)  # 差集
print(a ^ b)  # 对称差
print({"read"} <= a)  # 是否为子集
print(a >= {"read"})  # 是否为超集
print(a.isdisjoint({"admin"}))
```

成员测试通常比列表快，适合权限、去重、黑白名单。但若需要保留原顺序，不能简单转 set 后再转回 list，可使用：

```python
items = ["a", "b", "a", "c"]
unique_in_order = list(dict.fromkeys(items))
```

不可变集合 `frozenset` 可作为字典键或放进另一个集合。

### 4.5 容器嵌套与安全访问

真实数据经常嵌套：

```python
response = {
    "choices": [
        {"message": {"role": "assistant", "content": "你好"}}
    ]
}

content = response["choices"][0]["message"]["content"]
```

每一层都可能缺失时，不要写过长的链式索引并假设结构永远正确。对外部 API 应使用 Pydantic、TypedDict 或显式校验。

### 4.6 容器常用内置函数

```python
numbers = [3, 1, 4]

print(len(numbers))
print(min(numbers))
print(max(numbers))
print(sum(numbers))
print(any([False, True, False]))
print(all([True, True]))
print(sorted(numbers))
```

- `any()`：至少一个元素真则为 True；
- `all()`：所有元素真则为 True；空可迭代对象的 `all()` 为 True；
- `reversed()` 返回反向迭代器，不直接返回列表；
- `sorted()` 返回列表，不修改输入。

`min()` 和 `max()` 同样支持 `key`：

```python
words = ["a", "ccc", "bb"]
print(min(words, key=len))  # a
print(max(words, key=len))  # ccc
```

### 4.7 怎样选择容器

| 需求 | 优先选择 |
|---|---|
| 保持顺序、允许重复、经常追加 | list |
| 固定的一组位置值、不可变 | tuple |
| 按键查找和更新字段 | dict |
| 去重、集合运算、快速成员测试 | set |
| 高效队列和两端操作 | collections.deque |
| 计数 | collections.Counter |
| 自动创建默认值 | collections.defaultdict |

不要为了“性能”随意替换容器。先选择语义正确、代码清晰的结构，再依据真实测量优化。

### 4.8 本章练习

1. 用列表推导式把 `[1, 2, 3, 4, 5]` 中的偶数筛选出来并乘 2；
2. 用字典统计一句话里每个字符出现的次数（提示：`collections.Counter`）；
3. 把两个列表 `["a", "b"]` 和 `[1, 2]` 用 `zip` 合并成字典 `{"a": 1, "b": 2}`；
4. 用 `set` 去除列表中重复元素，同时保持原顺序（提示：`dict.fromkeys`）。

---

## 5. 条件、循环与模式匹配

控制流决定“哪些代码执行、执行多少次、何时停止”。

### 5.1 `if / elif / else`

```python
status = 429

if status == 200:
    action = "成功"
elif status == 429:
    action = "限流后重试"
else:
    action = "记录错误"

print(action)
```

解释器从上到下检查条件，遇到第一个为 True 的分支后执行该代码块，并跳过后续分支。`elif` 可以有多个，`else` 可省略。

条件可以组合：

```python
age = 20
has_permission = True

if age >= 18 and has_permission:
    print("允许访问")
```

复杂条件建议拆成有意义的布尔变量：

```python
is_adult = age >= 18
can_access = is_adult and has_permission

if can_access:
    print("允许访问")
```

### 5.2 真值条件与显式比较

```python
items = []

if not items:
    print("没有数据")
```

这比 `if len(items) == 0` 更符合 Python 风格。

但如果 None、0、空字符串代表不同业务含义，应显式判断：

```python
timeout = 0

if timeout is None:
    print("没有配置")
elif timeout == 0:
    print("不等待")
```

### 5.3 条件表达式（三元表达式）

简单的二选一可写成：

```python
status_text = "通过" if score >= 60 else "未通过"
```

阅读顺序是“成立时的值 if 条件 else 不成立时的值”。只适合短小表达式，复杂分支使用普通 if。

### 5.4 海象运算符 `:=`

`:=` 在表达式中计算并赋值：

```python
text = "hello"

if (length := len(text)) > 3:
    print(f"长度为 {length}")
```

它能避免重复计算，但过度使用会降低可读性。普通赋值 `=` 不能直接写在 if 条件中。

### 5.5 `for` 循环本质上遍历可迭代对象

```python
for name in ["Ada", "Bob", "Cindy"]:
    print(name)
```

每轮把下一个元素绑定给 `name`。循环结束后，`name` 在当前作用域中通常仍存在并保留最后一个值，因此不要依赖循环变量作为临时私有变量。

遍历字符串、字典和文件也使用同一语法：

```python
for char in "AI":
    print(char)

config = {"model": "demo", "timeout": 30}
for key, value in config.items():
    print(key, value)
```

### 5.6 `range()`

```python
print(list(range(5)))         # 0,1,2,3,4
print(list(range(2, 5)))      # 2,3,4
print(list(range(2, 10, 2)))  # 2,4,6,8
print(list(range(5, 0, -1)))  # 5,4,3,2,1
```

规则与切片类似：包含 start，不包含 stop。`range` 是惰性序列，不会提前创建所有整数。

重复固定次数但不使用当前数字时，变量常命名为 `_`：

```python
for _ in range(3):
    print("重试")
```

不要用 `for i in range(len(items))` 仅仅为了读取元素，直接遍历更清晰。需要索引时用 enumerate。

### 5.7 `enumerate()`

```python
names = ["Ada", "Bob"]

for index, name in enumerate(names, start=1):
    print(index, name)
```

`start=1` 只改变输出编号，不改变列表真实下标。比手工维护 `index += 1` 更安全。

### 5.8 `zip()`

```python
names = ["A", "B", "C"]
scores = [0.91, 0.85, 0.93]

for name, score in zip(names, scores):
    print(name, score)
```

`zip()` 默认在最短输入结束，可能悄悄丢弃多余元素。长度必须一致时使用：

```python
for name, score in zip(names, scores, strict=True):
    print(name, score)
```

长度不一致会抛 `ValueError`。解压一组二元数据：

```python
pairs = [("A", 1), ("B", 2)]
names, values = zip(*pairs)
```

### 5.9 `while` 循环

`while` 在条件仍为 True 时重复执行：

```python
attempt = 0

while attempt < 3:
    attempt += 1
    print("第", attempt, "次")
```

适合“不知道具体次数、直到条件满足”的任务，例如轮询状态。必须确保条件最终可能变为 False，否则会无限循环。

```python
while True:
    command = input("输入 quit 退出：")
    if command == "quit":
        break
```

生产服务中的无限循环应有取消、超时、错误处理或停机信号。

### 5.10 `break`、`continue` 与 `pass`

- `break`：立即结束当前最内层循环；
- `continue`：跳过本轮剩余代码，进入下一轮；
- `pass`：什么也不做。

```python
for value in [3, -1, 0, 5]:
    if value < 0:
        continue
    if value == 0:
        break
    print(value)
```

`break` 只结束一层循环。多层循环要退出时，可以封装成函数后 `return`，或使用标志变量，避免难懂的控制逻辑。

### 5.11 循环的 `else`

循环正常结束且没有执行 break 时，else 执行：

```python
target = 7
numbers = [1, 3, 5]

for number in numbers:
    if number == target:
        print("找到了")
        break
else:
    print("没有找到")
```

它不是“最后一次循环的 else”，而是“没有被 break 中断”。while 也支持同样语法。

### 5.12 不要边遍历边改变容器大小

错误示例：

```python
numbers = [1, 2, 3, 4]

for number in numbers:
    if number % 2 == 0:
        numbers.remove(number)
```

迭代位置与列表长度同时变化，可能跳过元素。推荐构造新列表：

```python
numbers = [number for number in numbers if number % 2 != 0]
```

或遍历副本：

```python
for number in numbers.copy():
    if number % 2 == 0:
        numbers.remove(number)
```

字典和集合在遍历时改变大小通常直接抛 `RuntimeError`。

### 5.13 嵌套循环

```python
for row in range(2):
    for column in range(3):
        print(row, column)
```

总执行次数约为两层次数乘积。对大数据，嵌套循环可能迅速变慢。先确保逻辑正确，再考虑字典索引、集合、NumPy 向量化或批处理。

### 5.14 `match / case`

模式匹配适合结构明确的数据：

```python
event = {"type": "token", "text": "Hello"}

match event:
    case {"type": "token", "text": text}:
        print("增量文本：", text)
    case {"type": "error", "message": message}:
        print("错误：", message)
    case _:
        print("未知事件")
```

它不只是 switch，可以解构序列、字典和类。

匹配序列：

```python
point = (10, 20)

match point:
    case (0, 0):
        print("原点")
    case (x, 0):
        print("X 轴", x)
    case (x, y):
        print("普通点", x, y)
```

守卫条件：

```python
match event:
    case {"type": "result", "score": score} if score >= 0.9:
        print("高置信结果")
    case {"type": "result", "score": score}:
        print("普通结果", score)
```

注意模式中的裸名称通常表示“捕获并绑定”，不是与已有变量比较。常量模式要使用字面量、枚举或限定名。

### 5.15 选择控制结构

| 需求 | 结构 |
|---|---|
| 多个互斥条件 | if / elif / else |
| 简单二选一值 | 条件表达式 |
| 遍历已知集合 | for |
| 直到某条件改变 | while |
| 查找并提前结束 | for + break + else |
| 跳过不合格元素 | continue |
| 解析固定结构数据 | match / case |

清晰优先于“写成一行”。过深的条件嵌套可通过提前 return、拆分函数和有意义的布尔变量降低复杂度。

### 5.16 `assert` 断言

`assert` 在开发期检查“这里必须成立”的假设，条件为假时抛出 `AssertionError`：

```python
def split_ratio(total: int, used: int) -> float:
    assert total > 0, "total 必须大于 0"
    return used / total
```

不要用 `assert` 校验用户输入：以 `python -O` 运行 Python 时断言会被移除，生产输入校验应使用显式 `if/raise` 或 Pydantic。

---

## 6. 函数：定义、调用、参数、返回值与作用域

函数把一段有明确职责的逻辑命名，便于重复调用、测试和组合。

### 6.1 定义函数与调用函数

```python
def greet(name):
    message = f"你好，{name}"
    return message

result = greet("Ada")
print(result)
```

定义时：

1. `def` 创建函数对象；
2. 名字 `greet` 绑定到这个函数；
3. 函数体此时不会执行。

调用 `greet("Ada")` 时：

1. 实参 `"Ada"` 绑定到形参 `name`；
2. 创建本次调用的局部作用域；
3. 自上而下执行函数体；
4. `return` 把结果交回调用位置；
5. 局部作用域结束。

函数名后的括号很重要：

```python
print(greet)         # 函数对象本身
print(greet("Ada"))  # 调用函数后的返回值
```

### 6.2 参数、实参与返回值

- 形参：函数定义中的名字，例如 `name`；
- 实参：调用时传入的对象，例如 `"Ada"`；
- 返回值：函数通过 return 交给调用者的对象。

```python
def add(a, b):
    return a + b

total = add(10, 20)
```

`return` 会立即结束本次函数调用，后面的语句不会执行：

```python
def absolute(value):
    if value >= 0:
        return value
    return -value
```

没有显式 return 的函数返回 None。

### 6.3 返回多个值的本质是元组

```python
def min_max(numbers):
    return min(numbers), max(numbers)

result = min_max([3, 1, 8])
print(result)  # (1, 8)

smallest, largest = min_max([3, 1, 8])
```

函数实际只返回一个元组，再由调用者解包。元素很多、语义复杂时，使用 dataclass、NamedTuple 或结构化模型比长元组清晰。

### 6.4 文档字符串与类型标注

```python
def estimate_cost(tokens: int, price_per_million: float) -> float:
    """按每百万 Token 单价估算费用。

    Args:
        tokens: 输入和输出 Token 总数。
        price_per_million: 每百万 Token 的价格。

    Returns:
        估算费用。
    """
    return tokens / 1_000_000 * price_per_million
```

类型标注主要用于阅读、IDE、静态检查和生成文档，Python 默认不会在运行时强制检查。传入错误类型仍可能到函数内部才报错。外部数据应使用 Pydantic 等做运行时校验。

### 6.5 位置参数和关键字参数

```python
def connect(host, port=443, timeout=30):
    return f"{host}:{port}, timeout={timeout}"

print(connect("example.com", 80, 10))
print(connect("example.com", timeout=5))
print(connect(host="example.com", port=8080))
```

- 位置参数按顺序匹配；
- 关键字参数按名字匹配；
- 位置参数必须写在关键字参数之前；
- 同一参数不能重复提供；
- 关键字参数能提升可读性。

### 6.6 默认参数

```python
def greet(name, prefix="你好"):
    return f"{prefix}，{name}"
```

有默认值的参数通常放在无默认值参数后面。

默认参数在函数定义时计算一次，而不是每次调用时计算。不要使用可变对象作为默认值：

```python
def bad_add(item, items=[]):
    items.append(item)
    return items

print(bad_add("a"))  # ['a']
print(bad_add("b"))  # ['a', 'b']
```

正确写法：

```python
def add(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items
```

同理，默认值若写成 `datetime.now()` 或某次函数调用，也只在定义时计算一次。需要每次重新计算时在函数体内完成。

### 6.7 仅限位置参数与仅限关键字参数

```python
def request_model(
    prompt,
    /,                       # 前面只能按位置传
    model="demo",
    *,                       # 后面只能按关键字传
    timeout=30.0,
):
    return f"{model}: {prompt} ({timeout}s)"
```

调用：

```python
request_model("你好", model="fast", timeout=10)
```

- `/` 前的参数只能按位置传；
- `*` 后的参数只能按关键字传；
- 中间参数两种方式都可用。

仅限关键字参数适合布尔开关、超时和重试次数，避免调用处出现难懂的 `func(x, True, 30, 2)`。

### 6.8 `*args` 收集额外位置参数

```python
def total(*numbers):
    print(type(numbers))  # tuple
    return sum(numbers)

print(total(1, 2, 3))
```

`numbers` 是元组。`*args` 中的 `args` 只是惯例名称，星号才有语法意义。

若稳定业务函数的参数已知，应明确写出名称，不要用 args 隐藏接口。

### 6.9 `**kwargs` 收集额外关键字参数

```python
def show_metadata(**metadata):
    print(type(metadata))  # dict
    print(metadata)

show_metadata(source="user", language="zh")
```

kwargs 是字典。它适合适配器、装饰器和透传少量可选配置，但过度使用会让拼写错误无法被函数签名和静态工具发现。

### 6.10 调用时的 `*` 与 `**` 解包

在调用位置，星号含义是把容器拆开：

```python
def add(a, b):
    return a + b

numbers = [10, 20]
print(add(*numbers))
```

字典解包为关键字参数：

```python
options = {"model": "demo", "timeout": 10}
print(request_model("你好", **options))
```

键必须与参数名匹配；重复提供同一参数会抛 `TypeError`。

定义中的 `*args` 是“收集”，调用中的 `*values` 是“展开”。

### 6.11 Python 的参数传递：传递对象引用

调用时，形参绑定到实参所指向的对象。若函数原地修改可变对象，调用者能看到：

```python
def add_item(items):
    items.append("new")

values = ["old"]
add_item(values)
print(values)  # ['old', 'new']
```

若函数只是让局部名字重新绑定，调用者变量不变：

```python
def replace(items):
    items = ["new"]
    print(items)

values = ["old"]
replace(values)
print(values)  # ['old']
```

对不可变对象的“修改”会创建新对象并重新绑定局部名字：

```python
def increase(number):
    number += 1
    return number

count = 10
new_count = increase(count)
```

API 设计时应明确函数是否修改传入对象。能返回新值时通常更容易推理和测试。

### 6.12 作用域与 LEGB

查找名字的顺序是：

1. Local：当前函数局部；
2. Enclosing：外层函数；
3. Global：当前模块；
4. Built-in：内置名称。

```python
message = "全局"

def outer():
    message = "外层"

    def inner():
        message = "局部"
        print(message)

    inner()

outer()
```

函数内赋值默认创建局部变量：

```python
count = 0

def increment():
    count = 1  # 新的局部变量
    return count
```

确实要修改模块级变量需 `global`：

```python
count = 0

def increment():
    global count
    count += 1
```

但大量全局可变状态难以测试，并发时也危险，通常应通过参数、返回值或对象管理状态。

修改外层函数变量使用 `nonlocal`：

```python
def make_counter():
    count = 0

    def next_value():
        nonlocal count
        count += 1
        return count

    return next_value
```

### 6.13 函数是一等对象

函数可以赋给变量、放入容器、作为参数或返回值：

```python
def square(value):
    return value * value

operation = square
print(operation(5))

operations = {"square": square}
print(operations["square"](4))
```

高阶函数：

```python
def apply(value, operation):
    return operation(value)

print(apply(5, square))
```

这也是回调、装饰器、路由表和策略模式的基础。

### 6.14 `lambda`

lambda 创建只有一个表达式的匿名函数：

```python
square = lambda x: x * x
print(square(5))
```

常见于短小 key 或回调：

```python
users.sort(key=lambda user: user["score"])
```

lambda 不能包含普通赋值、while、try 等语句。逻辑稍复杂、需要注释、类型或复用时，使用 def。

与 lambda 相关的内置函数 `map()` 和 `filter()` 分别对每个元素做转换、保留满足条件的元素，返回迭代器：

```python
values = [1, 2, 3, 4]

print(list(map(lambda x: x * 2, values)))
print(list(filter(lambda x: x % 2 == 0, values)))
```

现代代码通常用推导式表达得更直接：

```python
print([x * 2 for x in values])
print([x for x in values if x % 2 == 0])
```

`callable(obj)` 可以判断对象能否被调用，常用于区分“配置项是一个函数还是一个普通值”。

### 6.15 纯函数、副作用与可测试性

纯函数只依赖参数并返回结果：

```python
def calculate_price(unit_price, count):
    return unit_price * count
```

副作用包括修改外部对象、写文件、发网络请求、打印、写数据库：

```python
def save_result(path, text):
    path.write_text(text, encoding="utf-8")
```

工程中不是不能有副作用，而是应把计算和 I/O 分开，使核心逻辑容易测试。

### 6.16 递归及其边界

函数可以调用自身：

```python
def factorial(n):
    if n < 0:
        raise ValueError("n 不能为负数")
    if n <= 1:
        return 1
    return n * factorial(n - 1)
```

必须有终止条件。Python 不做尾递归优化，递归层数有限。遍历很深的目录、树或图时，要考虑显式栈、循环和循环引用。

### 6.17 函数设计建议

- 一个函数只承担一个清晰职责；
- 名称表达动作，如 `load_config`；
- 输入和返回值尽量明确；
- 不要把所有参数都塞进 kwargs；
- 不要用可变默认参数；
- 不要悄悄修改调用者数据；
- 边界处校验输入，内部保持清晰契约；
- 长函数先按责任拆分，而不是机械按行数拆分。

### 6.18 本章练习

1. 写一个 `classify(score: int) -> str` 函数：`>= 90` 返回 `"A"`，`>= 60` 返回 `"B"`，否则返回 `"C"`，加上类型标注和文档字符串；
2. 写一个 `retry(func, times)` 高阶函数：调用 `func()`，抛出异常则重试，最多 `times` 次；
3. 写一个函数用 `*args` 接收任意数量的数字并返回平均值；
4. 解释为什么 `def f(x, items=[])` 是危险的，并写出正确写法（答案见 6.6）。

---

## 7. 推导式、迭代器与生成器

### 7.1 推导式：看懂它的执行顺序

推导式是“用一条表达式从可迭代对象生成新容器”的语法。先看最常见的形式：

```python
long_lengths = [n for n in lengths if n >= 10]
```

它读作：**对 `lengths` 中的每个 `n`，如果 `n >= 10`，就把 `n` 放进新列表**。执行顺序是：

1. `for n in lengths`：逐个取出元素；
2. `if n >= 10`：过滤掉不满足条件的元素；
3. 最前面的 `n`：对每个留下的元素计算放入容器的值。

注意“放在最前面的表达式”最后才计算，但它是结果的值。

列表推导式：

```python
lengths = [5, 10, 20, 3]
long_lengths = [n for n in lengths if n >= 10]
print(long_lengths)  # [10, 20]
```

字典推导式使用 `键: 值`：

```python
squares = {n: n * n for n in range(4)}
print(squares)  # {0: 0, 1: 1, 2: 4, 3: 9}
```

集合推导式使用花括号但只有值：

```python
unique = {len(word) for word in ["a", "bb", "ccc", "dd"]}
print(unique)  # {1, 2, 3}
```

需要“二选一”时，可以在最前面的表达式里使用条件表达式：

```python
values = [-2, 3, -1, 4]
print([x if x >= 0 else -x for x in values])
# [2, 3, 1, 4]
```

嵌套循环会按书写顺序展开：

```python
pairs = [(x, y) for x in [1, 2] for y in ["a", "b"]]
print(pairs)  # [(1, 'a'), (1, 'b'), (2, 'a'), (2, 'b')]
```

什么时候不要用推导式：

- 超过两层循环；
- 表达式里有明显的副作用（例如调用网络请求）；
- 需要在循环体内写多行逻辑；
- 结果很难一眼看懂。

此时普通 `for` 循环更清晰。推导式的价值是“可读且简洁”，不是为了把代码挤成一行。

### 7.2 Iterable 与 Iterator

- **可迭代对象（Iterable）**：能被 `for` 遍历的对象，例如列表、字符串、字典、文件；
- **迭代器（Iterator）**：记录遍历位置的对象，每次调用 `next()` 返回下一个元素。

`for` 循环底层做的事情相当于：

```python
iterator = iter(values)
while True:
    try:
        value = next(iterator)
    except StopIteration:
        break
    print(value)
```

`iter()` 从可迭代对象创建迭代器；`next()` 推进迭代器；元素耗尽后抛出 `StopIteration`，`for` 会捕获它并正常结束。

```python
values = [10, 20]
iterator = iter(values)

print(next(iterator))  # 10
print(next(iterator))  # 20
# next(iterator)  # StopIteration
```

迭代器是**一次性**的：遍历完就耗尽，再次 `for` 不会从头开始。可迭代对象本身可以反复创建新迭代器：

```python
values = [1, 2]
print(list(values))  # 第一次
print(list(values))  # 仍然可以从头开始

iterator = iter(values)
list(iterator)
print(list(iterator))  # 空列表：同一个迭代器已经耗尽
```

`list()`、`tuple()`、`sum()`、`for` 等操作都会“消费”传入的迭代器。这是后续生成器和流式处理必须理解的基础。

### 7.3 生成器

生成器是按需产生值的函数。函数体中一旦出现 `yield`，它就不再是普通函数：

```python
from collections.abc import Iterator

def chunks(items: list[int], size: int) -> Iterator[list[int]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]
```

调用 `chunks(...)` 不会立刻执行函数体，而是返回一个生成器对象。每次 `next()` 或 `for` 推进时，函数执行到下一个 `yield` 暂停，把值交给调用者；下次推进时从暂停处继续。

```python
for chunk in chunks([1, 2, 3, 4, 5], 2):
    print(chunk)
```

输出：

```text
[1, 2]
[3, 4]
[5]
```

生成器是一次性迭代器，而且可以手动推进：

```python
gen = chunks([1, 2, 3], 2)
print(next(gen))  # [1, 2]
print(next(gen))  # [3]
```

生成器表达式是另一种写法，把列表推导式的方括号换成圆括号：

```python
total = sum(x * x for x in range(5))
print(total)  # 30
```

它不会立即生成完整列表，而是边遍历边计算，适合大数据流。

什么时候用生成器：

- 文件很大，不想一次全部读入内存；
- Token 流、分块批处理、日志逐行处理；
- 数据量超过可用内存，需要边算边消费。

什么时候不要用：

- 需要随机访问或多次遍历同一数据；
- 函数逻辑本身很短、数据量很小，普通列表更直观。

AI 场景中，数据流、Token 流、文件分块和批处理都适合生成器，但要注意生成器不能被重复消费，调试时不要先 `list()` 一次又遍历一次。

### 7.4 `yield from`

`yield from` 把一个子迭代器中的元素逐个转交给外层，等价于内层循环加 `yield`：

```python
def flatten(groups: list[list[int]]):
    for group in groups:
        yield from group

print(list(flatten([[1, 2], [3], [4, 5]])))
```

输出：

```text
[1, 2, 3, 4, 5]
```

它适合把“递归遍历”或“委托给另一个生成器”的代码写得更短，例如展开嵌套序列时。语义仍是逐元素生成，不会一次复制所有数据。

---
## 8. 异常与资源管理

### 8.1 异常是什么，怎样捕获

程序执行到 `raise` 或运行时错误时，会创建一个异常对象并沿调用栈向上传播。若某层用 `try/except` 处理了它，程序继续执行；否则最终显示 Traceback 并退出。

`try` 中放可能出错的代码，`except` 处理可预期的错误：

```python
try:
    temperature = float("high")
except ValueError as exc:
    print("转换失败：", exc)
```

`as exc` 把异常对象绑定给 `exc`，通常用它的 `str(exc)` 或 `exc.args` 获取错误信息。

一次捕获多个不相关类型：

```python
try:
    value = items[index] + int(raw)
except (ValueError, TypeError) as exc:
    print("数值错误：", exc)
```

多个 `except` 从上到下匹配，先捕获具体异常，再捕获更宽的异常：

```python
try:
    risky()
except KeyError:
    print("缺少键")
except ValueError:
    print("值不合法")
except Exception as exc:
    print("其他错误：", exc)
```

不要只写 `except Exception: pass`：它会吞掉编程错误，让问题延迟爆发且难以定位。可以捕获后记录日志，再决定继续、返回默认值或重新抛出。

### 8.2 `else`：没有异常时才执行

`try/except/else` 中，`else` 只在 `try` 成功且没有异常时执行：

```python
def parse_temperature(value: str) -> float:
    try:
        temperature = float(value)
    except ValueError as exc:
        raise ValueError(f"非法 temperature：{value!r}") from exc
    else:
        return temperature
```

把“依赖 try 成功结果”的代码放在 `else` 中，可以避免把它们的异常误当成 try 内部异常处理。

### 8.3 `raise` 与异常链

主动抛出异常：

```python
def require_positive(value: int) -> int:
    if value <= 0:
        raise ValueError("value 必须为正数")
    return value
```

在 `except` 中想保留原始原因时使用 `raise ... from exc`，Traceback 会同时显示原始异常和新异常：

```python
try:
    float("high")
except ValueError as exc:
    raise RuntimeError("解析配置失败") from exc
```

在 `except` 里不带参数的 `raise` 会把当前异常原样重新抛出，适合“记录后继续向上传播”：

```python
try:
    result = call_model()
except TimeoutError:
    log_error("模型超时")
    raise  # 让调用方决定如何处理
```

### 8.4 `finally`：无论结果如何都执行

`finally` 在 try 成功、异常被捕获、异常未被捕获甚至函数 `return` 时都会执行：

```python
try:
    print("开始")
finally:
    print("清理")
```

如果 `try` 中 return，`finally` 仍会先执行。因此清理工作放在 `finally`，不要依赖它返回值：

```python
def read_config():
    try:
        return "配置内容"
    finally:
        print("关闭资源")
```

完整组合：

```python
try:
    value = int(raw)
except ValueError:
    value = 0
else:
    print("转换成功")
finally:
    print("无论如何都会执行")
```

### 8.5 异常层级与内置异常

常用层级：

```text
BaseException
├── KeyboardInterrupt      # Ctrl+C
├── SystemExit             # sys.exit()
└── Exception              # 业务和运行错误都继承它
    ├── ValueError
    ├── TypeError
    ├── KeyError
    ├── IndexError
    ├── RuntimeError
    └── OSError
```

- `KeyboardInterrupt` 和 `SystemExit` 继承自 `BaseException`，一般不要捕获；
- 写 `except Exception` 已能覆盖绝大多数可恢复错误；
- 不要捕获 `BaseException`，它会吞掉中断和退出信号。

自定义异常通常继承 `Exception` 或更具体的 `RuntimeError`、`ValueError`：

```python
class ModelTimeoutError(RuntimeError):
    pass

def run_model(seconds: int) -> None:
    if seconds > 30:
        raise ModelTimeoutError("模型调用超过预算")

try:
    run_model(60)
except ModelTimeoutError as exc:
    print(exc)
```

自定义异常让上层能按错误类型决定重试、降级或返回用户错误，例如 `ModelTimeoutError` 可重试，`ValidationError` 直接返回给用户。

### 8.6 `with` 与上下文管理

`with` 保证进入时获取资源、退出时释放资源，即使中途出错：

```python
from pathlib import Path

path = Path("demo.txt")
with path.open("w", encoding="utf-8") as file:
    file.write("hello")
```

等价于手动保证关闭文件，但更不易遗漏。

同时管理多个资源：

```python
with open("a.txt", encoding="utf-8") as src, open("b.txt", "w", encoding="utf-8") as dst:
    dst.write(src.read())
```

`with` 不限于文件，也可以用于锁、数据库事务和 HTTP 会话：

```python
import threading

lock = threading.Lock()
with lock:
    shared_value += 1
```

原理是进入时调用对象的 `__enter__()`，退出时调用 `__exit__()`；用 `contextlib.contextmanager` 自定义上下文管理器会在第 14 章介绍。

### 8.7 什么时候不该用异常

1. **不要用异常表达正常流程**：例如“找不到就返回 None”用普通分支即可，不需要 try/except；
2. **不要吞掉异常后当作成功**：`except Exception: return None` 会把编程错误也伪装成“没有结果”；
3. **不要在 except 中做危险操作再失败**：清理代码要保证自身不会再次抛出，必要时嵌套 try；
4. **捕获范围尽量小**：能捕获 `ValueError` 就不捕获 `Exception`，能捕获 `Exception` 就不捕获 `BaseException`；
5. **记录上下文**：生产代码至少记录异常类型、消息、相关数据和位置，便于事后定位。

### 8.8 本章练习

1. 把 `"abc"` 转成 `int`，用 `try/except` 捕获 `ValueError` 并打印友好提示；
2. 写一个函数：用 `with` 打开文件读取内容，保证文件一定被关闭；
3. 自定义一个 `ConfigError(Exception)`，在配置缺少必需字段时抛出，并在调用处捕获；
4. 在 `except` 中用 `raise ... from exc` 包装异常，观察 Traceback 中“The above exception was the direct cause”部分。

---
## 9. 类、dataclass 与协议

### 9.1 类、实例与 `self`

类是创建对象的模板：类定义里写“每个实例应有哪些属性和方法”，调用类时创建独立实例。

```python
class ChatSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.messages: list[str] = []

    def add(self, message: str) -> None:
        self.messages.append(message)

    @property
    def size(self) -> int:
        return len(self.messages)

session = ChatSession("s-1")
session.add("你好")
print(session.session_id, session.size)
```

输出：

```text
s-1 1
```

需要理解几个点：

- `__init__` 是“初始化方法”，在创建实例后自动调用，用来设置实例属性；
- `self` 指“当前这个实例本身”，不是关键字，只是惯例名称。定义方法时它必须写在第一个位置；
- `session.add("你好")` 等价于 `ChatSession.add(session, "你好")`：Python 自动把实例作为第一个参数传入；
- `session.messages` 属于**实例属性**，每个实例独立保存一份。

> **初学提示**：类可以类比成“模具”，实例是“用模具做出的产品”。`__init__` 是给每个新产品做初始设置的地方；`self` 就是“这个产品自己”。方法和普通函数唯一的区别，就是第一个参数自动收到“自己这个实例”。

### 9.2 实例属性与类属性

类体直接赋值的变量是类属性，所有实例共享：

```python
class Config:
    default_timeout = 30

a = Config()
b = Config()
print(a.default_timeout)  # 30
```

实例属性写在 `self.xxx = ...`，每个实例独立：

```python
a.default_timeout = 60
print(a.default_timeout)  # 60
print(b.default_timeout)  # 30
```

注意“读取”会先查实例属性再查类属性，所以 `a.default_timeout = 60` 只是给 a 创建了实例属性，不修改类属性。类属性适合常量；可变类属性（例如直接写 `messages = []`）会因为所有实例共享而互相污染，通常应放到 `__init__` 中。

### 9.3 `__repr__` 与 `__str__`

- `str(obj)` 面向用户显示，对应 `__str__`；
- `repr(obj)` 面向调试显示，对应 `__repr__`，理想情况下应能看出类型和关键字段。

```python
class ModelConfig:
    def __init__(self, name: str, temperature: float):
        self.name = name
        self.temperature = temperature

    def __repr__(self) -> str:
        return f"ModelConfig(name={self.name!r}, temperature={self.temperature})"

config = ModelConfig("demo", 0.2)
print(repr(config))
print(config)  # 没有 __str__ 时回退到 __repr__
```

打印日志和调试时，`repr` 能避免只看到一个难以辨认的内存地址。

### 9.4 `property`：把方法包装成属性

`@property` 让方法像属性一样读取：

```python
session.size  # 无需括号
```

适合“计算得到、不应随意赋值”的值。要真正控制赋值逻辑时再写 setter，不要为了“看起来很面向对象”而滥用。

### 9.5 实例方法、类方法、静态方法

```python
class ModelClient:
    registry = {}

    def __init__(self, name: str):
        self.name = name

    def call(self):
        return f"调用 {self.name}"

    @classmethod
    def from_default(cls):
        return cls("default-model")

    @staticmethod
    def is_valid_name(name: str) -> bool:
        return bool(name.strip())
```

- 实例方法第一个参数是 `self`；
- 类方法第一个参数是 `cls`，可以访问类属性或构造本类实例；
- 静态方法既不需要实例也不需要类，只是逻辑上放在类里，适合工厂校验等工具方法。

大多数时候先写普通实例方法，等真正需要 `cls` 或完全独立逻辑时再用后两种。

### 9.6 dataclass：减少样板代码

`dataclass` 根据字段自动生成 `__init__`、`__repr__`、`__eq__` 等：

```python
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class ModelConfig:
    name: str
    temperature: float = 0.0
    tags: tuple[str, ...] = field(default_factory=tuple)

config = ModelConfig("demo", tags=("test",))
print(config)
```

输出：

```text
ModelConfig(name='demo', temperature=0.0, tags=('test',))
```

- `frozen=True` 防止字段被重新赋值，适合不可变配置对象；
- `slots=True` 减少内存并阻止随意新增属性；
- 可变默认值必须用 `default_factory`，否则所有实例共享同一个列表或字典。

dataclass 适合“主要保存数据”的对象；需要大量行为时仍写普通类。

### 9.7 继承与组合

继承表示“是一种”，子类复用并扩展父类：

```python
class BaseClient:
    def __init__(self, name: str) -> None:
        self.name = name

    def describe(self) -> str:
        return f"客户端 {self.name}"

class ChatClient(BaseClient):
    def __init__(self, name: str, max_tokens: int) -> None:
        super().__init__(name)
        self.max_tokens = max_tokens

    def describe(self) -> str:
        return f"{super().describe()}，上限 {self.max_tokens} tokens"

client = ChatClient("chat", 1024)
print(client.describe())
print(isinstance(client, BaseClient))  # True
```

- `super().__init__` 调用父类初始化；
- 子类重写同名方法时，`super().method()` 可以显式调用父类版本；
- 不要设计很深的继承链；多重继承容易引入方法解析顺序（MRO）问题，除非必要否则避免。

组合表示“拥有一个”，把依赖作为字段传入：

```python
class RetryPolicy:
    def __init__(self, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts

class ModelClient:
    def __init__(self, retry_policy: RetryPolicy) -> None:
        self.retry_policy = retry_policy

client = ModelClient(RetryPolicy(5))
print(client.retry_policy.max_attempts)
```

工程中优先组合，因为组合依赖关系显式、容易替换和测试；只有当“子类确实是一种父类”且共享稳定行为时才用继承。

### 9.8 Protocol：结构化接口

`Protocol` 描述“需要哪些方法”，只要对象结构满足即可，不要求显式继承：

```python
from typing import Protocol

class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...

class DemoEmbedder:
    def embed(self, text: str) -> list[float]:
        return [float(len(text))]

def vectorize(text: str, embedder: Embedder) -> list[float]:
    return embedder.embed(text)

print(vectorize("hello", DemoEmbedder()))
```

`Protocol` 只影响静态检查，运行时 `DemoEmbedder` 不需要继承 `Embedder`。它适合定义“接入层接口”，让多个实现不需要共享同一个父类。

---
## 10. 类型标注

类型标注不改变普通 Python 的运行行为，主要帮助 IDE、静态检查和读者理解接口。例如 `def add(a: int, b: int) -> int:` 中的 `: int` 和 `-> int` 不会阻止你传入字符串，但检查工具会给出警告。

### 10.1 内置泛型标注

Python 3.9+ 可以直接用内置类型表示容器元素类型：

```python
from collections.abc import Callable, Iterable, Mapping, Sequence

def total(values: list[int]) -> int:
    return sum(values)

def build_config() -> dict[str, int]:
    return {"timeout": 30}

def labels() -> tuple[str, ...]:
    return ("a", "b")
```

- `list[int]`：整数列表；
- `dict[str, int]`：键为 str、值为 int 的字典；
- `tuple[str, ...]`：任意长度的字符串元组；`tuple[str, int]` 表示固定两个元素；
- `set[int]`：整数集合；
- `Callable[[int, int], int]`：接收两个 int 并返回 int 的可调用对象；
- 返回值写 `None` 表示“不返回有意义的值”。

只读场景优先标注 `Sequence[int]` 或 `Iterable[int]`，而不是限定 `list`，接口会更灵活：

```python
def total(values: Sequence[int]) -> int:
    return sum(values)
```

### 10.2 Optional、Union 与 `|`

“可能没有值”用 `str | None` 表达：

```python
def find_name(data: dict[str, str]) -> str | None:
    return data.get("name")

name = find_name({})
print(name)  # None
```

`Optional[str]` 与 `str | None` 等价，但 `|` 语法更直观，也支持任意联合类型：

```python
def parse(value: int | str | None) -> str:
    if value is None:
        return "无值"
    if isinstance(value, int):
        return f"整数 {value}"
    return f"字符串 {value}"
```

使用前要“缩窄类型”：通过 `if value is None`、`isinstance(value, int)` 等判断后，静态检查器才知道当前分支的类型。

### 10.3 `Any` 与 `object`

- `Any` 表示“不做检查”，会关闭这一处的类型推断，适合临时过渡或确无类型的动态数据；
- `object` 是所有类型的基类，表示“接收任何对象”，但静态检查器不允许直接调用 `obj.some_method()`，必须先判断类型。

```python
from typing import Any

def passthrough(value: Any) -> Any:
    return value
```

优先使用具体类型或 `object + isinstance`，把 `Any` 当作需要消除的技术债。

### 10.4 `Literal`：限定字面值

```python
from typing import Literal

ModelRole = Literal["system", "user", "assistant", "tool"]

def build_message(role: ModelRole, content: str) -> dict[str, str]:
    return {"role": role, "content": content}
```

`Literal` 把允许的取值写成字面量联合，适合角色、状态、日志级别等枚举字符串。注意它仍是静态检查，运行时传入 `"管理员"` 不会自动报错。

### 10.5 `TypedDict`：描述字典结构

```python
from typing import TypedDict

class Message(TypedDict):
    role: str
    content: str

message: Message = {"role": "user", "content": "你好"}
print(message["content"])
```

`TypedDict` 只用于静态检查，不会在运行时验证外部 JSON。所有字段都必填；要允许缺省字段可加 `total=False`：

```python
class PartialMessage(TypedDict, total=False):
    role: str
    content: str
```

外部输入需要运行时校验时，应使用 Pydantic（见第 18 章）。

### 10.6 泛型：让函数保持类型关系

```python
from typing import TypeVar

T = TypeVar("T")

def first(items: list[T]) -> T:
    if not items:
        raise ValueError("items 不能为空")
    return items[0]

print(first([10, 20]))   # int
print(first(["a", "b"]))  # str
```

`T` 表示“同一个类型占位”：传入 `list[int]` 时返回 `int`，传入 `list[str]` 时返回 `str`，而不是一律退化成 `Any`。

可以限制允许的类型范围：

```python
Number = TypeVar("Number", int, float)

def double(value: Number) -> Number:
    return value * 2
```

自定义泛型类使用 `Generic[T]`：

```python
from typing import Generic

class Box(Generic[T]):
    def __init__(self, value: T) -> None:
        self.value = value
```

初学者先把“泛型函数”用熟即可，不需要一开始掌握所有泛型语法。

### 10.7 类型检查工具与运行时校验

- `mypy` 或基于 Pyright 的检查器负责静态检查，在 CI 中运行可提前发现类型错误；
- 类型标注不会阻止错误数据进入函数，因此**外部数据**（HTTP 请求、文件、数据库行）需要 Pydantic 等运行时校验；
- 两者互补：标注定义接口契约，校验保证运行时数据真实满足契约。

---
## 11. 模块、包与虚拟环境

### 11.1 导入

```python
import json
from pathlib import Path
from collections.abc import Iterator
```

两种写法的区别：

- `import json`：把模块本身引入当前作用域，之后用 `json.dumps(...)`；
- `from pathlib import Path`：只把模块里的名字 `Path` 引入，直接写 `Path(...)`。

可以用 `as` 取别名，避免名字冲突或缩短长名称：

```python
import numpy as np
from package.submodule import load_model as load
```

“包”是包含模块文件的目录，模块是 `.py` 文件。导入时 Python 从当前目录、已配置路径和安装位置逐级查找，因此不要随意在项目里创建与标准库同名的文件。

避免 `from module import *`，它会污染命名空间，也让代码检查工具无法知道名字来自哪里。不要把自己的文件命名为 `json.py`、`typing.py`、`asyncio.py`，否则会遮蔽标准库。

### 11.2 `__name__` 入口

```python
def main() -> None:
    print("程序入口")

if __name__ == "__main__":
    main()
```

直接运行时输出：

```text
程序入口
```

被其他模块导入时不会自动调用 `main()`。多进程在 Windows 上尤其需要入口保护。

### 11.3 虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install httpx fastapi uvicorn pydantic pytest
```

虚拟环境隔离项目依赖。使用 `python -m pip` 能减少 `pip` 与当前解释器不一致的问题。

### 11.4 项目依赖

小项目可使用 `requirements.txt`，现代项目可使用 `pyproject.toml`。生产应固定可复现版本并定期升级，不应永远使用无上限依赖。

---

## 12. 文件、路径、JSON 和 CSV

### 12.1 pathlib

```python
from pathlib import Path

root = Path("data")
path = root / "sample.json"

print(path.suffix)
print(path.name)
print(path.parent)
```

输出：

```text
.json
sample.json
data
```

跨平台代码优先使用 `Path`，避免手工拼接 `/` 或 `\`。

### 12.2 JSON

```python
import json

data = {"model": "demo", "temperature": 0.2, "stream": True}
text = json.dumps(data, ensure_ascii=False, indent=2)
restored = json.loads(text)

print(text)
print(restored["stream"])
```

输出：

```text
{
  "model": "demo",
  "temperature": 0.2,
  "stream": true
}
True
```

常用参数：

```python
text = json.dumps(
    data,
    ensure_ascii=False,  # 保留中文等字符，而不是转成 \uXXXX
    indent=2,            # 格式化输出
    sort_keys=True,      # 按键排序，便于比较和 diff
)
```

写入文件时使用 `json.dump(data, file)`，读取时使用 `json.load(file)`，它们处理编码和流式读写。

JSON 不支持 Python 的 tuple、set、datetime 和任意对象，需要先转换或自定义 `default` 编码函数。

### 12.3 JSON Lines

大规模 AI 数据常一行一个 JSON，便于流式处理：

```python
import json
from io import StringIO

source = StringIO('{"text":"A"}\n{"text":"B"}\n')
records = [json.loads(line) for line in source if line.strip()]
print(records)
```

输出：

```text
[{'text': 'A'}, {'text': 'B'}]
```

### 12.4 CSV

```python
import csv
from io import StringIO

buffer = StringIO()
writer = csv.DictWriter(buffer, fieldnames=["name", "score"])
writer.writeheader()
writer.writerow({"name": "model-a", "score": 0.91})

print(buffer.getvalue().strip())
```

输出：

```text
name,score
model-a,0.91
```

CSV 中可能包含逗号、换行和引号，不要手工 `split(',')`。

### 12.5 本章练习

1. 把一个字典列表写入 JSON 文件，再读回来并验证内容一致；
2. 生成一个 5 行的 JSONL 文件（每行一个 JSON），逐行读取并统计每行 `text` 字段的平均长度；
3. 用 `csv.DictWriter` 写出 3 行数据，再用 `csv.DictReader` 读回；
4. 用 `pathlib.Path` 找出当前目录下所有 `.json` 文件，并打印文件名。

---

## 13. 常用标准库

### 13.1 collections

```python
from collections import Counter, defaultdict, deque

tokens = ["a", "b", "a"]
print(Counter(tokens))

groups: defaultdict[str, list[int]] = defaultdict(list)
groups["x"].append(1)
print(dict(groups))

queue = deque([1, 2])
queue.append(3)
print(queue.popleft())
```

输出：

```text
Counter({'a': 2, 'b': 1})
{'x': [1]}
1
```

### 13.2 itertools

```python
from itertools import batched, chain

print(list(batched(range(7), 3)))
print(list(chain([1, 2], [3, 4])))
```

Python 3.12+ 输出：

```text
[(0, 1, 2), (3, 4, 5), (6,)]
[1, 2, 3, 4]
```

若需要兼容更早 Python，可自己实现批处理生成器。

### 13.3 functools

```python
from functools import lru_cache, partial

@lru_cache(maxsize=128)
def tokenize(text: str) -> tuple[str, ...]:
    print("实际计算")
    return tuple(text.split())

print(tokenize("hello world"))
print(tokenize("hello world"))

base_two = partial(int, base=2)
print(base_two("1010"))
```

输出：

```text
实际计算
('hello', 'world')
('hello', 'world')
10
```

缓存参数和结果必须可哈希，并注意缓存可能长期占用内存、返回过期结果。

### 13.4 datetime

```python
from datetime import UTC, datetime, timedelta

now = datetime.now(UTC)
later = now + timedelta(minutes=5)

print(now.tzinfo)
print(later > now)
```

典型输出：

```text
UTC
True
```

服务端优先保存带时区 UTC 时间，展示时再转换用户时区。

### 13.5 enum

```python
from enum import StrEnum

class Status(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"

print(Status.RUNNING)
print(Status.RUNNING.value)
```

输出：

```text
running
running
```

---

## 14. 装饰器、闭包与上下文管理器

### 14.1 装饰器

```python
from collections.abc import Callable
from functools import wraps
from time import perf_counter
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

def timed(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            print(f"{func.__name__} 耗时 {perf_counter() - start:.6f}s")
    return wrapper

@timed
def add(a: int, b: int) -> int:
    return a + b

print(add(2, 3))
```

典型输出：

```text
add 耗时 0.000001s
5
```

实际耗时会变化。`wraps` 保留原函数名称和文档。

### 14.2 闭包

```python
def make_prefixer(prefix: str):
    def add_prefix(text: str) -> str:
        return f"{prefix}{text}"
    return add_prefix

error = make_prefixer("ERROR: ")
print(error("timeout"))
```

输出：

```text
ERROR: timeout
```

### 14.3 自定义上下文管理器

```python
from contextlib import contextmanager

@contextmanager
def trace(name: str):
    print("start", name)
    try:
        yield
    finally:
        print("end", name)

with trace("model_call"):
    print("running")
```

输出：

```text
start model_call
running
end model_call
```

---

## 15. Python 中容易踩的坑

### 15.1 浅复制

```python
matrix = [[0, 0]] * 3
matrix[0][0] = 1
print(matrix)
```

输出：

```text
[[1, 0], [1, 0], [1, 0]]
```

三行引用同一个内部列表。正确写法：`[[0, 0] for _ in range(3)]`。

### 15.2 浮点数

```python
print(0.1 + 0.2 == 0.3)
print(round(0.1 + 0.2, 10))
```

输出：

```text
False
0.3
```

货币等精确十进制使用 `decimal.Decimal`；科学计算通常使用容差比较。

### 15.3 捕获过宽异常

不要这样：

```python
try:
    risky_operation()
except Exception:
    pass
```

它会隐藏编程错误、取消信号语义和真实故障。应捕获可处理的具体异常，并记录上下文。

### 15.4 循环变量闭包

```python
functions = [lambda: i for i in range(3)]
print([func() for func in functions])
```

输出：

```text
[2, 2, 2]
```

闭包在调用时读取最终 `i`。可用默认参数绑定：`lambda i=i: i`。

### 15.5 列表边迭代边删除

应构建新列表，或遍历副本。直接删除会跳过元素。

```python
values = [1, 2, 3, 4]
values = [value for value in values if value % 2 == 1]
print(values)
```

输出：

```text
[1, 3]
```

### 15.6 阻塞调用进入异步函数

在 `async def` 中使用 `time.sleep()`、同步 HTTP 或重 CPU 循环会阻塞整个事件循环。使用异步库，或将阻塞函数放到线程/进程池。

---

## 16. HTTP 与 API 基础

### 16.1 请求组成

HTTP 是客户端与服务端之间传输数据的协议：**客户端发请求，服务端回响应**。调用模型 API 的本质，就是向一个 HTTP 地址发送请求并解析响应。先记住这个模型，再去记方法、状态码这些细节。

HTTP 请求包括：方法、URL、Headers、Query、Body。常见方法：

- GET：读取；
- POST：创建/执行；
- PUT：整体替换；
- PATCH：部分更新；
- DELETE：删除。

常见状态码：

| 状态码 | 含义 | 客户端处理 |
|---|---|---|
| 200/201 | 成功 | 解析结果 |
| 400 | 请求参数错误 | 修正请求，不盲目重试 |
| 401/403 | 认证/授权失败 | 检查凭据和权限 |
| 404 | 资源不存在 | 检查 ID/路径 |
| 409 | 状态冲突 | 根据业务处理幂等/版本 |
| 429 | 限流 | 读取重试提示，退避 |
| 500/502/503/504 | 服务/网关临时错误 | 有限重试或降级 |

### 16.2 使用 httpx

```python
import httpx

response = httpx.get(
    "https://httpbin.org/get",
    params={"q": "python"},
    timeout=10.0,
)
response.raise_for_status()
data = response.json()

print(response.status_code)
print(data["args"])
```

联网时典型输出：

```text
200
{'q': 'python'}
```

生产中使用 `httpx.Client`/`AsyncClient` 复用连接，不要每次请求重新建立连接。

### 16.3 Timeout 不是一个数字那么简单

连接、读取、写入和连接池等待可以分别超时。没有超时的外部调用可能永久占用 Worker。

```python
import httpx

timeout = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)

with httpx.Client(timeout=timeout) as client:
    # response = client.get("https://example.com")
    print(type(client).__name__)
```

输出：

```text
Client
```

### 16.4 认证和幂等

API Key 常通过 `Authorization: Bearer ...` 发送。不要放 Query、源码、日志或前端浏览器。

创建付款、任务等操作可能因网络超时被客户端重试。服务端应支持 Idempotency Key，避免同一逻辑执行两次。

---

## 17. 调用大模型 API

不同厂商 SDK 不同，但核心数据流相似：

```text
输入消息/内容 → HTTP/SDK → 模型服务
→ 文本/结构化输出/工具调用/流式事件
```

### 17.1 使用通用 HTTP 调用兼容接口

```python
import os
import httpx

API_URL = os.environ.get("MODEL_API_URL", "https://example.com/v1/responses")
API_KEY = os.environ.get("MODEL_API_KEY")

if not API_KEY:
    raise RuntimeError("请设置 MODEL_API_KEY")

payload = {
    "model": "your-model",
    "input": "用一句话解释 Python 生成器。",
}

with httpx.Client(timeout=60.0) as client:
    response = client.post(
        API_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=payload,
    )
    response.raise_for_status()
    print(response.json())
```

输出结构取决于服务。`example.com` 是占位地址，运行前必须替换接口和模型名。

另一种常见格式是 `messages`：把对话历史按角色分组发送，适合多轮对话：

```python
payload = {
    "model": "your-model",
    "messages": [
        {"role": "system", "content": "你是一个乐于助人的助手。"},
        {"role": "user", "content": "用一句话解释生成器。"},
    ],
}
```

`system` 消息设定行为，`user` 是用户输入，`assistant` 是模型历史回复。不同厂商字段名略有差异，以官方文档为准。角色和 Token 的概念详见第 31 章。

### 17.2 不要假定输出永远是字符串

现代模型可能返回：文本块、图片、音频、引用、工具调用和拒答。应按 Schema/事件类型解析，而不是直接访问猜测字段。

```python
response = {
    "items": [
        {"type": "text", "text": "答案"},
        {"type": "tool_call", "name": "search", "arguments": {"q": "Python"}},
    ]
}

for item in response["items"]:
    match item:
        case {"type": "text", "text": text}:
            print("TEXT:", text)
        case {"type": "tool_call", "name": name, "arguments": arguments}:
            print("TOOL:", name, arguments)
```

输出：

```text
TEXT: 答案
TOOL: search {'q': 'Python'}
```

### 17.3 结构化输出

让模型输出 JSON Schema 能减少格式漂移，但必须继续做业务校验。

```python
from dataclasses import dataclass
import json

@dataclass
class Classification:
    label: str
    confidence: float

raw = '{"label":"positive","confidence":0.91}'
data = json.loads(raw)
result = Classification(**data)

if not 0 <= result.confidence <= 1:
    raise ValueError("confidence 越界")

print(result)
```

输出：

```text
Classification(label='positive', confidence=0.91)
```

真实项目优先使用 Pydantic 等运行时校验，而不是直接 `**data`。

### 17.4 请求 ID、模型版本与评估

记录请求 ID、模型、版本、延迟、Token、费用和错误类型，但不要记录未经脱敏的 Prompt、Secret 或个人信息。模型行为会变化，重要应用应固定模型版本并建立回归评测。

### 17.5 本章练习

1. 用 httpx 调用一个真实的模型 API（或本地 mock 服务），分别用 `input` 和 `messages` 两种格式请求，观察响应差异；
2. 把“提取响应文本”封装成函数，返回 `(text, error)` 元组；
3. 手动构造一个 `items` 列表（包含 `text` 和 `tool_call` 两种类型），用 `match/case` 解析并打印；
4. 调用一次真实 API，打印 `usage` 字段（Token 数）并估算费用。

---

## 18. 数据校验：Pydantic

Pydantic 根据类型标注校验、转换和序列化外部数据。它常用于 FastAPI、配置和模型结构化输出。

```python
from typing import Literal
from pydantic import BaseModel, Field, ValidationError

class GenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)
    temperature: float = Field(default=0.0, ge=0, le=2)
    mode: Literal["fast", "quality"] = "fast"

request = GenerationRequest.model_validate({
    "prompt": "你好",
    "temperature": "0.7",  # 可按规则转换为 float
})

print(request)
print(request.model_dump())

try:
    GenerationRequest(prompt="", temperature=5)
except ValidationError as exc:
    print("字段错误数：", exc.error_count())
```

输出：

```text
prompt='你好' temperature=0.7 mode='fast'
{'prompt': '你好', 'temperature': 0.7, 'mode': 'fast'}
字段错误数： 2
```

### 18.1 严格模式

自动转换很方便，也可能掩盖上游类型错误。关键字段可启用严格验证。

### 18.2 Pydantic 与 dataclass

- dataclass：内部可信数据对象，标准库、开销较小；
- Pydantic：外部 JSON、环境变量、API 请求，需要运行时校验和 Schema。

---

## 19. 使用 FastAPI 编写 AI 服务

安装并启动：

```powershell
python -m pip install fastapi "uvicorn[standard]"
uvicorn app:app --reload
```

`app.py`：

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Demo AI API")

class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5_000)

class GenerateResponse(BaseModel):
    text: str
    input_length: int

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    if "forbidden" in request.prompt.lower():
        raise HTTPException(status_code=400, detail="不允许的输入")

    # 实际项目在此 await 异步模型客户端
    return GenerateResponse(
        text=f"Echo: {request.prompt}",
        input_length=len(request.prompt),
    )
```

调用：

```powershell
curl -X POST http://127.0.0.1:8000/generate `
  -H "Content-Type: application/json" `
  -d '{"prompt":"hello"}'
```

输出：

```json
{"text":"Echo: hello","input_length":5}
```

### 19.1 `def` 还是 `async def`

- 异步 HTTP/数据库/模型 SDK：使用 `async def` 并 `await`；
- 阻塞库：普通 `def` 可由 FastAPI 线程池运行，或显式 `asyncio.to_thread()`；
- CPU 密集推理：不要在事件循环中直接运行，使用进程、独立模型 Worker 或推理服务。

把同步阻塞 SDK 写进 `async def` 会卡住事件循环，降低所有并发请求性能。

### 19.2 生命周期与共享客户端

HTTP Client、数据库连接池和模型应在应用启动时创建、关闭时释放，而不是每请求创建。多 Worker 部署时，每个进程都有独立内存，不能假设 Python 全局变量跨进程共享。

### 19.3 API 必需的工程控制

- 认证与授权；
- 输入大小限制；
- Timeout、限流和并发上限；
- 请求 ID 与结构化日志；
- 健康检查和就绪检查；
- 错误映射与脱敏；
- 指标和 Trace；
- 优雅关闭。

---

## 20. 并发模型总览

并发表示多个任务在时间上重叠；并行表示同一时刻真正执行多个任务。

> **初学类比**：把任务想成“去银行办业务”。**并发**是一个柜员在等待打印时先给下一位客户填表，多个业务在时间上重叠；**并行**是开了多个窗口，多个柜员同时干活。Python 的 asyncio 是“一个柜员快速切换”，多进程是“开多个窗口”，多线程介于两者之间。

| 方法 | 适合 | 特点 |
|---|---|---|
| 同步 | 简单、低并发 | 容易理解 |
| 线程 | 阻塞 I/O、同步 SDK | 共享内存，要加锁 |
| 进程 | CPU 密集、故障隔离 | 真并行，序列化开销大 |
| asyncio | 大量异步 I/O | 单线程事件循环、高并发 |
| GPU/分布式 | 张量计算、大模型 | 由框架和硬件调度 |

经典 CPython 受 GIL 影响，同一解释器内通常只有一个线程执行 Python 字节码，因此 CPU 密集 Python 线程难以利用多核；I/O 等待时线程仍然有用。自由线程构建正在发展，但第三方库兼容和默认运行环境必须实际确认，不能假设“新版 Python 已经没有 GIL”。

---

## 21. 多线程

### 21.1 ThreadPoolExecutor

适合并发调用同步 HTTP、读取文件等 I/O 任务。

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep

def call_api(task_id: int) -> str:
    sleep(0.1)  # 模拟网络等待
    return f"task-{task_id}"

with ThreadPoolExecutor(max_workers=3) as pool:
    futures = [pool.submit(call_api, i) for i in range(5)]
    results = [future.result() for future in as_completed(futures)]

print(sorted(results))
```

输出顺序由完成时间决定，排序后：

```text
['task-0', 'task-1', 'task-2', 'task-3', 'task-4']
```

`executor.map()` 保持输入顺序，`as_completed()` 按完成顺序返回。

### 21.2 竞态条件与 Lock

多个线程读写共享状态需要同步。不要依赖“某个操作看起来原子”作为业务正确性保证。

```python
from threading import Lock, Thread

counter = 0
lock = Lock()

def increment() -> None:
    global counter
    for _ in range(10_000):
        with lock:
            counter += 1

threads = [Thread(target=increment) for _ in range(4)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()

print(counter)
```

输出：

```text
40000
```

### 21.3 Queue 生产者—消费者

`queue.Queue` 是线程安全的，适合任务移交和背压。应设计结束信号、最大长度和异常传播，避免生产速度无限超过消费速度。

### 21.4 线程池常见错误

- Worker 内等待同一小线程池中的另一个 Future，可能死锁；
- 无限提交任务导致内存增长；
- 线程共享非线程安全 Client；
- 忘记处理 Future 异常；
- 用线程处理纯 Python CPU 密集任务，速度不升反降。

---

## 22. 多进程

多进程拥有独立解释器和内存，可利用多核处理 CPU 密集任务。

```python
from concurrent.futures import ProcessPoolExecutor

def count_squares(limit: int) -> int:
    return sum(i * i for i in range(limit))

def main() -> None:
    with ProcessPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(count_squares, [10, 100]))
    print(results)

if __name__ == "__main__":
    main()
```

输出：

```text
[285, 328350]
```

### 22.1 Windows 的入口保护

Windows 常使用 spawn 启动子进程，会重新导入主模块。缺少 `if __name__ == "__main__"` 可能递归创建进程。

### 22.2 序列化开销

参数和结果通常需要 Pickle 在进程间传输。大型 NumPy 数组、模型或不可 Pickle 对象传输成本高。可使用共享内存、内存映射、对象存储，或让 Worker 自己加载长期对象。

### 22.3 GPU 与多进程

GPU 模型多进程需要明确每进程设备、CUDA Context 和显存。不要无意中让每个 Web Worker 都加载一份大模型。大型推理通常使用独立模型服务，而不是在普通 API 进程内随意启动 ProcessPool。

---

## 23. asyncio 异步编程

事件循环在任务执行到可等待 I/O 时切换其他任务。异步适合大量网络请求，不会让 CPU 密集 Python 自动并行。

### 23.1 Coroutine 与 Task

```python
import asyncio

async def fetch(task_id: int) -> str:
    await asyncio.sleep(0.1)
    return f"result-{task_id}"

async def main() -> None:
    tasks = [asyncio.create_task(fetch(i)) for i in range(3)]
    results = await asyncio.gather(*tasks)
    print(results)

asyncio.run(main())
```

输出：

```text
['result-0', 'result-1', 'result-2']
```

调用 `fetch(1)` 只创建 Coroutine，不会自动开始执行；`create_task()` 才调度为 Task。

> **初学提示**：把 `async def` 函数想象成“可以暂停的菜谱”，`await` 是“等水烧开”的时刻——等待期间事件循环会去做别的事。这能帮你理解为什么异步适合 I/O 等待，而 CPU 计算不会因此变快。

### 23.2 TaskGroup：结构化并发

```python
import asyncio

async def work(value: int) -> int:
    await asyncio.sleep(0.05)
    return value * 2

async def main() -> None:
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(work(i)) for i in range(3)]
    print([task.result() for task in tasks])

asyncio.run(main())
```

输出：

```text
[0, 2, 4]
```

TaskGroup 中一个任务失败时会取消其他未完成任务，退出时统一抛出异常组，生命周期比散落 Task 更容易管理。

### 23.3 异步 HTTP Client

```python
import asyncio
import httpx

async def fetch_status(client: httpx.AsyncClient, url: str) -> int:
    response = await client.get(url)
    return response.status_code

async def main() -> None:
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        statuses = await asyncio.gather(
            fetch_status(client, "https://httpbin.org/status/200"),
            fetch_status(client, "https://httpbin.org/status/204"),
        )
    print(statuses)

asyncio.run(main())
```

联网时输出：

```text
[200, 204]
```

### 23.4 把阻塞函数放入线程

```python
import asyncio
from time import sleep

def blocking_call() -> str:
    sleep(0.1)
    return "done"

async def main() -> None:
    result = await asyncio.to_thread(blocking_call)
    print(result)

asyncio.run(main())
```

输出：

```text
done
```

`to_thread` 主要用于无法替换的阻塞 I/O。CPU 密集纯 Python 应考虑进程池。

### 23.5 取消

协程应允许 `CancelledError` 正常传播，并在 `finally` 中清理资源。不要捕获后无条件吞掉取消，否则服务无法优雅关闭。

---

## 24. 并发控制、超时、重试与限流

### 24.1 Semaphore 限制并发

```python
import asyncio

async def call(index: int, semaphore: asyncio.Semaphore) -> int:
    async with semaphore:
        await asyncio.sleep(0.05)
        return index

async def main() -> None:
    semaphore = asyncio.Semaphore(2)
    results = await asyncio.gather(
        *(call(i, semaphore) for i in range(5))
    )
    print(results)

asyncio.run(main())
```

输出：

```text
[0, 1, 2, 3, 4]
```

虽然创建了 5 个任务，同时进入受保护区的最多 2 个。

### 24.2 Timeout

```python
import asyncio

async def slow() -> None:
    await asyncio.sleep(1)

async def main() -> None:
    try:
        async with asyncio.timeout(0.05):
            await slow()
    except TimeoutError:
        print("超时")

asyncio.run(main())
```

输出：

```text
超时
```

Timeout 要覆盖连接、读取和整体业务预算。外层取消后，底层服务不一定自动停止，需要协议支持。

### 24.3 指数退避与抖动

```python
import random

def backoff(attempt: int, base: float = 0.5, cap: float = 8.0) -> float:
    maximum = min(cap, base * 2**attempt)
    return random.uniform(0, maximum)

random.seed(1)
print([round(backoff(i), 2) for i in range(4)])
```

输出：

```text
[0.07, 0.85, 1.53, 1.02]
```

抖动避免大量客户端同时重试形成“惊群”。只重试网络错误、429 和部分 5xx；400、认证失败和业务拒绝通常不重试。

### 24.4 Retry 与幂等

读取请求通常可安全重试；创建任务、付款、发邮件可能产生副作用，需要 Idempotency Key 或服务端去重。不能因为捕获了 Timeout 就断定服务端没有执行。

### 24.5 限流

- 并发限制控制同时进行多少请求；
- Rate Limit 控制一段时间请求/Token 数；
- Token Bucket 允许一定突发；
- Queue 提供缓冲，但必须有上限和超时。

客户端应读取 `Retry-After` 或服务端返回的限流信息。

---

## 25. 流式响应与生成器

流式模型常使用 Server-Sent Events（SSE）或 WebSocket。客户端不能假设每个网络分块恰好是一条完整 JSON 事件，需要按协议分帧。

### 25.1 同步生成器模拟流式 Token

```python
from collections.abc import Iterator
from time import sleep

def stream_text() -> Iterator[str]:
    for token in ["Hello", ", ", "world", "!"]:
        sleep(0.02)
        yield token

for token in stream_text():
    print(token, end="", flush=True)
print()
```

输出逐步出现：

```text
Hello, world!
```

### 25.2 异步生成器

```python
import asyncio
from collections.abc import AsyncIterator

async def stream_tokens() -> AsyncIterator[str]:
    for token in ["A", "I", "!"]:
        await asyncio.sleep(0.02)
        yield token

async def main() -> None:
    output = []
    async for token in stream_tokens():
        output.append(token)
    print("".join(output))

asyncio.run(main())
```

输出：

```text
AI!
```

### 25.3 流式错误处理

HTTP 200 只表示流成功建立，流中途仍可能出现错误或不完整结束。需要处理：

- 事件类型和结束事件；
- 增量文本与工具调用参数；
- 心跳与空行；
- 客户端断开和取消；
- 部分结果是否可保存；
- 中途错误和重试是否会重复输出。

---

## 26. AI 数据处理常用工具

### 26.1 NumPy 数组与广播

```python
import numpy as np

vectors = np.array([[1.0, 2.0], [3.0, 4.0]])
mean = vectors.mean(axis=0)
centered = vectors - mean

print(mean)
print(centered)
```

输出：

```text
[2. 3.]
[[-1. -1.]
 [ 1.  1.]]
```

`axis=0` 按行汇总得到每列统计。广播会自动扩展兼容维度，但 Shape 错误可能悄悄产生非预期结果。

### 26.2 余弦相似度

```python
import numpy as np

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        raise ValueError("零向量没有余弦方向")
    return float(np.dot(a, b) / denominator)

print(round(cosine(np.array([1, 0]), np.array([1, 1])), 3))
```

输出：

```text
0.707
```

### 26.3 Pandas 的适用边界

Pandas 适合内存内表格分析和清洗。大于单机内存、需要并行 ETL 时可使用 Polars、DuckDB、Spark、Ray Data 等，但先确认真正瓶颈。

```python
import pandas as pd

df = pd.DataFrame({
    "model": ["a", "a", "b"],
    "latency_ms": [100, 120, 80],
})

print(df.groupby("model")["latency_ms"].mean())
```

输出：

```text
model
a    110.0
b     80.0
Name: latency_ms, dtype: float64
```

### 26.4 Token 与批处理预算

不要只按字符数量估计模型输入。不同语言和 Tokenizer 的 Token 比例不同。模型 SDK/Tokenizer 应负责精确计数，并为系统提示、工具结果和输出留预算。

---

## 27. 配置、日志与 Secret

### 27.1 环境变量

```python
import os

api_key = os.environ.get("MODEL_API_KEY")
timeout = float(os.environ.get("MODEL_TIMEOUT", "30"))

print(timeout)
print(api_key is None)
```

未设置 Key 时输出可能为：

```text
30.0
True
```

环境变量都是字符串，需要校验和转换。`.env` 适合本地开发且必须加入 `.gitignore`；生产使用 Secret Manager/Kubernetes Secret 等受控方案。

### 27.2 logging

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ai_service")

logger.info("request_completed", extra={"request_id": "r-1"})
```

典型输出包含时间：

```text
2026-01-01 12:00:00,000 INFO ai_service request_completed
```

生产优先结构化 JSON 日志。不得记录 API Key、Authorization Header、完整个人数据和未经批准的 Prompt。

### 27.3 配置优先级

常见优先级：默认值 < 配置文件 < 环境变量 < CLI 参数。启动时打印脱敏后的最终配置，避免“不知道当前用了哪个参数”。

---

## 28. 测试、Mock 与质量工具

### 28.1 pytest

业务函数：

```python
def normalize_score(value: float) -> float:
    if not 0 <= value <= 100:
        raise ValueError("score 必须在 0～100")
    return value / 100
```

测试：

```python
import pytest

def test_normalize_score() -> None:
    assert normalize_score(75) == 0.75

def test_normalize_score_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="0～100"):
        normalize_score(101)
```

运行：

```powershell
pytest -q
```

输出示例：

```text
2 passed
```

### 28.2 Mock 外部 API

测试不应真实消耗模型费用，也不应依赖网络稳定性。把 Client 通过参数注入，测试中提供 Fake：

```python
from typing import Protocol

class TextClient(Protocol):
    def generate(self, prompt: str) -> str: ...

class FakeClient:
    def generate(self, prompt: str) -> str:
        return "fixed-response"

def answer(prompt: str, client: TextClient) -> str:
    return client.generate(prompt)

print(answer("hello", FakeClient()))
```

输出：

```text
fixed-response
```

### 28.3 AI 应用测试层次

- 普通单元测试：校验解析、权限、预算、重试；
- Schema 测试：模型输出能否解析；
- Tool 测试：参数、幂等和错误码；
- 轨迹测试：是否选择正确工具；
- 模型评测集：质量、事实性、安全；
- 集成测试：真实模型少量运行；
- 负载测试：并发、超时和资源。

### 28.4 质量工具

- Ruff：Lint 和格式化；
- mypy/Pyright：静态类型检查；
- pytest：测试；
- coverage：覆盖率；
- pre-commit：提交前自动检查。

工具不能证明业务正确，但可以消除大量低级错误。

---

## 29. AI 项目结构

```text
ai-service/
├─ pyproject.toml
├─ README.md
├─ .env.example
├─ src/
│  └─ ai_service/
│     ├─ __init__.py
│     ├─ main.py          # FastAPI 入口
│     ├─ config.py        # 配置与 Secret 引用
│     ├─ schemas.py       # Pydantic 请求/响应
│     ├─ clients.py       # 模型、向量库、外部 API
│     ├─ services.py      # 业务编排
│     ├─ tools.py         # Agent 工具
│     └─ observability.py # 日志、指标、Trace
└─ tests/
   ├─ test_services.py
   └─ test_api.py
```

### 29.1 分层原则

- API 层负责 HTTP，不承担复杂业务；
- Service 层组织业务规则；
- Client 层封装外部依赖；
- Schema 定义边界数据；
- Domain 对象表达内部状态；
- 配置、日志和指标是横切能力；
- 测试通过依赖注入替换外部模型。

### 29.2 不要过早抽象

一个文件能清楚表达的小项目不必立即拆十层。随着职责稳定再拆分。抽象应减少重复和耦合，而不是增加文件数量。

---

## 30. 完整小项目：并发模型客户端

目标：并发处理多个 Prompt，同时限制并发、设置超时、重试临时错误，并保持输出顺序。示例使用模拟调用，可直接运行且不消耗 API。

```python
import asyncio
import random
from dataclasses import dataclass

class TemporaryModelError(RuntimeError):
    pass

@dataclass(frozen=True)
class Result:
    prompt: str
    text: str | None
    error: str | None = None

class DemoModelClient:
    async def generate(self, prompt: str) -> str:
        await asyncio.sleep(0.03)
        if prompt == "retry" and random.random() < 0.5:
            raise TemporaryModelError("临时限流")
        return prompt.upper()

async def generate_with_retry(
    client: DemoModelClient,
    prompt: str,
    semaphore: asyncio.Semaphore,
    max_attempts: int = 3,
) -> Result:
    async with semaphore:
        for attempt in range(max_attempts):
            try:
                async with asyncio.timeout(1.0):
                    text = await client.generate(prompt)
                return Result(prompt=prompt, text=text)
            except TemporaryModelError as exc:
                if attempt == max_attempts - 1:
                    return Result(prompt=prompt, text=None, error=str(exc))
                await asyncio.sleep(0.02 * 2**attempt)
            except TimeoutError:
                return Result(prompt=prompt, text=None, error="timeout")

    return Result(prompt=prompt, text=None, error="unexpected")

async def main() -> None:
    random.seed(1)
    client = DemoModelClient()
    semaphore = asyncio.Semaphore(2)
    prompts = ["hello", "python", "retry", "agent"]

    results = await asyncio.gather(*(
        generate_with_retry(client, prompt, semaphore)
        for prompt in prompts
    ))

    for result in results:
        print(result)

asyncio.run(main())
```

典型输出：

```text
Result(prompt='hello', text='HELLO', error=None)
Result(prompt='python', text='PYTHON', error=None)
Result(prompt='retry', text='RETRY', error=None)
Result(prompt='agent', text='AGENT', error=None)
```

这个小项目体现了 AI API 客户端最常用的组合：

- dataclass 表达结果；
- 自定义异常区分可重试错误；
- Async Client 处理 I/O；
- Semaphore 控制并发；
- Timeout 限制等待；
- 指数退避；
- `gather` 保持与输入相同的结果顺序；
- 单个请求失败不会让所有请求丢失。

真实项目还要加入认证、连接池、请求 ID、Token/费用预算、429 `Retry-After`、日志脱敏、取消传播和指标。

---

## 31. 理解大模型 API 的核心概念

调用模型 API 之前，先理解几个高频概念。它们出现在几乎所有模型的文档、账单和报错里。

### 31.1 Token：模型计数的最小单位

模型不直接按“字符”理解文本，而是按 Token 计数。Token 可以近似理解为“词的碎片”：

- 英文大约 1 个词 ≈ 1~2 个 Token（例如 `"Hello"` 约 1~2 个 Token）；
- 中文通常 1 个字 ≈ 1~2 个 Token，所以同样的内容，中文往往比英文更“贵”；
- Token 数决定费用和上下文窗口占用，不要用 `len(text)` 代替 Token 计数。

```python
# 粗略估算，仅用于预算；精确计数要用厂商的 Tokenizer 或 SDK
def rough_tokens(text: str) -> int:
    return max(1, len(text) // 2)  # 中文场景的粗估
```

厂商 SDK 或 Tokenizer 会给出精确数字，例如响应中的 `usage` 字段：

```json
{"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46}
```

### 31.2 上下文窗口（Context Window）

上下文窗口是模型一次能“看到”的 Token 总量（输入 + 输出）。例如 128K 窗口表示输入和输出合计不能超过约 128K Token，超出会报错或截断。

实际开发时，要为以下内容预留预算：

- 系统提示（system prompt）和工具定义；
- 对话历史（多轮消息会累积）；
- 检索到的文档片段（RAG，见第 32 章）；
- 模型输出本身。

所以长对话通常要**截断或压缩历史**，而不是无限追加。

### 31.3 messages：角色与对话结构

大多数聊天模型接收一个消息列表，每条消息有角色：

| 角色 | 作用 | 示例 |
|---|---|---|
| system | 设定行为、风格和约束 | `"你是 Python 老师，回答要简洁"` |
| user | 用户输入 | `"解释什么是生成器"` |
| assistant | 模型历史回复 | 多轮对话时回填 |
| tool | 工具执行结果 | 函数调用后返回给模型（见第 33 章） |

```python
messages = [
    {"role": "system", "content": "你是 Python 老师，回答要简洁。"},
    {"role": "user", "content": "解释什么是生成器。"},
    {"role": "assistant", "content": "生成器是按需产生值的函数，用 yield 暂停。"},
    {"role": "user", "content": "给一个例子。"},
]
```

调用模型时把整个列表发给服务端；保持角色顺序（system → user → assistant 交替），否则有些模型会报错或表现异常。

### 31.4 temperature 与 top_p：控制随机性

- `temperature` 越高，输出越多样、越“发散”；越低越确定、越可复现。取值范围通常 0~2，默认约 1；
- `top_p` 是另一种采样参数（核采样），与 temperature 二选一调整即可，不必同时微调；
- 需要稳定结果（解析、分类、代码）时用低温度（0~0.3）；需要创意写作时用较高温度。

### 31.5 输出长度、流式与费用

- `max_tokens`（或 `max_completion_tokens`）限制输出长度，防止模型无限生成；
- 流式（`stream: true`）让内容逐段到达，首字延迟更低，适合打字机效果（见第 25 章）；
- 费用 = 输入 Token × 输入单价 + 输出 Token × 输出单价，两者单价通常不同，输出更贵；
- 账单异常先查 `usage` 字段，再查是否有循环调用或历史消息无限累积。

### 31.6 函数调用（Function Calling / Tools）

除了返回文本，模型还能“提出要调用某个工具”，由你的程序执行后再把结果交给模型继续推理。这是 Agent 的基础，第 33 章会完整实现。

### 31.7 结构化输出与思考能力

- 结构化输出：用 JSON Schema 约束输出格式，适合需要程序解析的结果（见 17.3）；
- 推理模型：部分模型支持“思考过程”，会在回复前内部推理，通常更慢、更贵，但复杂任务更可靠。

> 记住一个原则：**模型输出永远是“可能出错”的数据**。把它当作外部输入来校验，而不是当作可信代码或事实。

### 31.8 本章练习

1. 用任意模型 API 打印一次调用的 `usage` 字段，核对 Token 数与你的估算；
2. 构造一段多轮 `messages`（system → user → assistant → user），观察不同模型对角色顺序的要求；
3. 把 `temperature` 分别设为 0 和 1.5，各生成 5 次，比较输出差异；
4. 说出 3 种“上下文窗口超限”的缓解方法（提示：截断、压缩、RAG）。

---

## 32. RAG 入门：用 Python 搭建文档问答

RAG（Retrieval-Augmented Generation，检索增强生成）解决“模型不知道你的私有资料”的问题：先从文档里检索相关内容，再连同问题一起交给模型回答。

### 32.1 整体流程

```text
文档 → 分块(chunking) → 嵌入(embedding) → 存入向量库
用户问题 → 嵌入 → 检索最相似的块 → 拼进 prompt → 模型生成答案
```

可以先用“纯 Python + NumPy”实现一个最小版本，理解原理后再换专业向量库（如 FAISS、Chroma、Milvus）。

### 32.2 分块（Chunking）

模型一次能处理的内容有限，文档要先切成小块。常用策略：

- 按固定长度切分，相邻块重叠一部分（overlap），避免一句话被切断；
- 按段落、标题或语义切分，块内容更完整；
- 块大小要平衡：太大检索不精准，太小上下文不足，常见几百到一两千 Token。

```python
def chunk_text(text: str, size: int = 200, overlap: int = 20) -> list[str]:
    """按字符切分，带重叠。真实项目应优先按句子/段落边界切。"""
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks

print(chunk_text("这是一段很长的文档。" * 20, size=30, overlap=5)[:2])
```

### 32.3 嵌入（Embedding）

嵌入把文本变成固定长度的向量，语义相近的文本向量距离更近。使用嵌入 API 或本地模型：

```python
# 伪代码：用真实 API 时替换为厂商 SDK
# vectors = embed(["Python 是动态语言", "Python 适合 AI"])
# 每个文本得到一个向量，例如 1024 维的 float 列表
```

得到向量后，用余弦相似度衡量语义接近程度（实现见 26.2）。

### 32.4 最小向量检索

```python
import numpy as np

def search(query_vec: np.ndarray, chunk_vecs: np.ndarray, top_k: int = 2) -> list[int]:
    """返回与 query 最相似的前 top_k 个块的索引。"""
    scores = chunk_vecs @ query_vec / (
        np.linalg.norm(chunk_vecs, axis=1) * np.linalg.norm(query_vec) + 1e-9
    )
    return scores.argsort()[::-1][:top_k].tolist()
```

向量都归一化到单位长度时，点积等价于余弦相似度。真实项目会使用向量库做近似最近邻检索，数据量大时性能差距巨大。

### 32.5 组装 Prompt 并生成

```python
def build_rag_prompt(question: str, context: str) -> str:
    return f"""请根据下面提供的资料回答用户问题。
如果资料中没有相关信息，请直接说明不知道，不要编造。

【资料】
{context}

【问题】
{question}"""
```

把检索到的块按相关性拼接进 `context`，再调用模型。注意：

- 限制检索结果数量，避免上下文超预算（见 31.2）；
- 回答必须“基于资料”，提示词里要写清楚，否则模型会自由发挥（幻觉）；
- 检索质量比提示词更能决定 RAG 效果：先优化分块和检索，再调提示词。

### 32.6 RAG 的常见改进方向

- 元数据过滤：只检索某日期、某类别下的文档；
- 混合检索：关键词（BM25）+ 向量检索结合；
- 重排（Rerank）：先召回一批，再用重排模型精排；
- 引用来源：把命中的文档 ID 一起返回，便于用户核对；
- 评测：准备一批“问题→标准答案”对，持续衡量检索命中率和回答质量。

### 32.7 本章练习

1. 把一篇长文切成带重叠的块，验证没有明显内容丢失；
2. 用 embedding API 为 5 个句子生成向量，用余弦相似度找出与查询句最相似的两个；
3. 把“最小向量检索”接入一个模型 API，实现“资料库问答”的最小闭环；
4. 想一个 RAG 会答错的例子（例如资料里没有答案），观察模型如何应对。

---

## 33. Agent 入门：工具调用与循环

Agent（智能体）= 大模型 + 工具 + 循环：模型决定“下一步调用哪个工具”，程序执行工具，把结果交回模型，直到模型认为任务完成。

### 33.1 工具调用（Function Calling）流程

```text
1. 声明工具：给模型一份工具清单（名称、描述、参数 Schema）
2. 模型返回工具调用：{"name": "search", "arguments": {"q": "..."}}
3. 程序执行工具，得到结果
4. 把结果以 tool 角色消息交回模型
5. 模型给出最终回答，或继续调用下一个工具
```

关键点：**工具真正由你的程序执行**，模型只负责“决定调用谁、传什么参数”。所以工具代码必须由你控制并校验参数。

### 33.2 最小 Agent 循环

```python
import json
from typing import Any

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]

def get_weather(city: str) -> dict[str, Any]:
    # 真实项目在这里调用天气 API
    return {"city": city, "weather": "晴", "temperature": 25}

def run_agent(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """模拟：模型返回工具调用；真实项目把 messages + TOOLS 发给模型。"""
    last = messages[-1]["content"]
    if "天气" in last:
        return [{
            "role": "assistant",
            "tool_calls": [{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": json.dumps({"city": "北京"}, ensure_ascii=False),
                },
            }],
        }]
    return [{"role": "assistant", "content": "我已经帮你查好了。"}]

def execute_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    """执行工具调用，返回以 tool 角色表示的结果消息。"""
    name = tool_call["function"]["name"]
    arguments = json.loads(tool_call["function"]["arguments"])
    result = get_weather(**arguments) if name == "get_weather" else {"error": "未知工具"}
    return {"role": "tool", "tool_call_id": tool_call.get("id", "t-1"), "content": json.dumps(result, ensure_ascii=False)}

def agent_loop(question: str, max_steps: int = 5) -> str:
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    for _ in range(max_steps):
        model_reply = run_agent(messages)[0]
        if "tool_calls" in model_reply:
            messages.append(model_reply)
            for tool_call in model_reply["tool_calls"]:
                messages.append(execute_tool_call(tool_call))
            continue  # 把工具结果交回模型，继续循环
        return model_reply["content"]
    return "达到最大步数，提前结束"

print(agent_loop("北京天气怎么样？"))
```

输出：

```text
我已经帮你查好了。
```

这个最小实现里 `run_agent` 是模拟的：真实项目中它调用模型 API，把 `messages + TOOLS` 发给模型，解析返回的 `tool_calls`。循环逻辑（执行工具 → 回填结果 → 再次请求模型）就是 Agent 的骨架。

### 33.3 Agent 的工程要点

- **最大步数限制**：防止模型无限循环调用工具；
- **参数校验**：工具收到的参数来自模型，可能格式错误，要校验后再执行；
- **超时与预算**：每一步调用都要超时，整个 Agent 也要有总预算（Token/时间/费用）；
- **工具权限**：只暴露必要的工具，危险操作（删除文件、转账）要二次确认；
- **错误反馈**：工具执行失败时，把错误信息作为 tool 结果交回模型，让它尝试修正；
- **日志**：记录每一步的模型回复、工具调用和结果，便于排查“为什么它这么干”。

### 33.4 从工具调用到 Agent 框架

掌握上面的循环后，LangChain、LangGraph 或自研框架对你来说就是“循环 + 更多控制”的组合：

- 状态管理：多步之间的变量保存与恢复；
- 规划：拆解任务、多分支执行；
- 记忆：短期对话历史 + 长期知识库（RAG，见第 32 章）；
- 人机协作：关键步骤请求人工确认；
- 评测与护栏：验证每一步输出，防止越界。

### 33.5 本章练习

1. 给上面的最小 Agent 增加第二个工具 `add(a, b)`，让模型能做算术；
2. 在 `execute_tool_call` 中捕获异常，把错误信息作为 tool 结果交回模型；
3. 测试“模型反复调用工具”时，最大步数限制能否及时停止循环；
4. 把 `run_agent` 换成真实模型 API（参考第 17 章），跑通真实工具调用。

---

## 34. 语法速查表

```python
# 条件表达式
label = "yes" if score >= 0.5 else "no"

# 解包
first, *middle, last = [1, 2, 3, 4]

# 字典解包
config = {**defaults, **overrides}

# Walrus：计算并赋值
if (length := len(text)) > 100:
    print(length)

# 排序
items = sorted(records, key=lambda item: item["score"], reverse=True)

# 安全获取带默认值
timeout = config.get("timeout", 30)

# 同时迭代
for name, score in zip(names, scores, strict=True):
    ...

# 带下标
for index, item in enumerate(items, start=1):
    ...

# 任意/全部
has_error = any(item.error for item in results)
all_ok = all(item.error is None for item in results)

# 上下文管理
with path.open(encoding="utf-8") as file:
    text = file.read()

# 异步上下文和异步迭代必须位于 async def 中
async def consume_stream(stream):
    async with httpx.AsyncClient() as client:
        async for event in stream:
            ...
```

这段是速查片段，变量依赖上下文，不作为独立程序执行。

---

## 35. 学习路线与关联笔记

### 第一阶段：语法速查（第 0~12 章）

先按顺序读完第 0~12 章，重点掌握字符串、容器、函数、异常、文件、类、dataclass 和类型标注。练习：把一份 JSONL 文件分批读取、校验和输出统计。

### 第二阶段：API 工程（第 13~30 章）

学习 HTTP、httpx、Pydantic、FastAPI、配置、日志和 pytest。完成一个同步模型 API Client，再为它编写 Fake 测试。

### 第三阶段：并发（第 20~25 章）

分别使用线程池和 asyncio 并发执行 20 个模拟 I/O 请求；加入 Semaphore、Timeout 和 Retry，比较耗时及异常行为。

### 第四阶段：理解 AI 核心概念（第 31~33 章）

读懂 Token、上下文窗口、messages 结构（第 31 章），动手实现一个最小 RAG 问答（第 32 章），再实现一个工具调用循环（第 33 章）。这三章是学习 Agent、LangChain 等框架前最值得亲手写的代码。

### 第五阶段：AI 工程整合

把模型客户端、结构化输出、流式响应、工具调用和评测放入一个 FastAPI 服务。加入请求 ID、限流和测试。概念记不清时查第 36 章术语表，遇到报错查第 37 章。

### 本地关联笔记

- [Agent 开发学习笔记](../%E5%8D%95%E8%A1%8C%E6%9C%AC/Agent%20%E5%BC%80%E5%8F%91%E5%AD%A6%E4%B9%A0%E7%AC%94%E8%AE%B0%EF%BC%9A%E4%BB%8E%E5%8E%9F%E7%90%86%E3%80%81%E6%8A%80%E6%9C%AF%E6%A0%88%E5%88%B0%E5%B7%A5%E7%A8%8B%E8%90%BD%E5%9C%B0.md)
- [LangChain 入门学习笔记](../langchain/LangChain%E5%85%A5%E9%97%A8%E5%AD%A6%E4%B9%A0%E7%AC%94%E8%AE%B0.md)
- [机器学习快速入门](../%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0/%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0%E5%BF%AB%E9%80%9F%E5%85%A5%E9%97%A8%EF%BC%9A%E4%BB%8E%E5%9F%BA%E6%9C%AC%E6%A6%82%E5%BF%B5%E5%88%B0%E5%AE%8C%E6%95%B4%E5%AE%9E%E8%B7%B5.md)
- [深度学习快速入门](../%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0/%E6%B7%B1%E5%BA%A6%E5%AD%A6%E4%B9%A0%E5%BF%AB%E9%80%9F%E5%85%A5%E9%97%A8%EF%BC%9A%E4%BB%8E%E7%A5%9E%E7%BB%8F%E7%BD%91%E7%BB%9C%E5%88%B0%20Transformer.md)
- [AI Infra 完整学习笔记](../%E5%8D%95%E8%A1%8C%E6%9C%AC/AI%20Infra%E5%AE%8C%E6%95%B4%E5%AD%A6%E4%B9%A0%E7%AC%94%E8%AE%B0%EF%BC%9A%E4%BB%8EGPU%E3%80%81%E5%88%86%E5%B8%83%E5%BC%8F%E8%AE%AD%E7%BB%83%E5%88%B0%E5%A4%A7%E6%A8%A1%E5%9E%8B%E6%8E%A8%E7%90%86%E4%B8%8EMLOps.md)
- [Function Calling 与 MCP](../0816MCP/Function%20Calling%20%E4%B8%8E%20MCP%20%E5%8D%8F%E8%AE%AE%EF%BC%9A%E8%AE%BE%E8%AE%A1%E5%8E%9F%E7%90%86%E4%B8%8E%E5%B7%A5%E7%A8%8B%E5%AE%9E%E8%B7%B5.md)

### 官方资料

- [Python Tutorial](https://docs.python.org/3/tutorial/)
- [Python Standard Library](https://docs.python.org/3/library/)
- [typing](https://docs.python.org/3/library/typing.html)
- [concurrent.futures](https://docs.python.org/3/library/concurrent.futures.html)
- [asyncio](https://docs.python.org/3/library/asyncio.html)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Pydantic](https://docs.pydantic.dev/latest/)
- [HTTPX](https://www.python-httpx.org/)
- [pytest](https://docs.pytest.org/)

---

## 36. AI 术语表

| 术语 | 中文/解释 |
|---|---|
| LLM | 大语言模型（Large Language Model），基于海量文本训练、能生成文本的模型 |
| Token | 模型计数和计费的最小文本单位，见 31.1 |
| Prompt | 提示词，发给模型的输入文本或消息列表 |
| System Prompt | 系统提示，设定模型角色和行为 |
| Context Window | 上下文窗口，模型一次能处理的最大 Token 数，见 31.2 |
| Temperature / Top-p | 控制输出随机性的采样参数，见 31.4 |
| Hallucination | 幻觉，模型生成看似合理但错误或虚构的内容 |
| Embedding | 嵌入，把文本变成语义向量，见 32.3 |
| Vector Database | 向量数据库，按向量相似度检索，RAG 的核心组件 |
| RAG | 检索增强生成，先检索资料再生成回答，见第 32 章 |
| Agent | 智能体，模型 + 工具 + 循环完成任务的程序，见第 33 章 |
| Function Calling / Tools | 函数调用，模型请求执行外部工具 |
| MCP | Model Context Protocol，模型与工具/数据源之间的一种标准化协议 |
| Fine-tuning | 微调，用特定数据进一步训练模型 |
| LoRA / QLoRA | 低秩微调方法，用较少资源微调大模型 |
| Quantization | 量化，压缩模型精度以降低显存占用 |
| KV Cache | 推理时缓存历史注意力键值，加速长对话 |
| Streaming / SSE | 流式输出，内容逐段返回 |
| Eval | 评测，用数据集衡量模型或 Agent 的效果 |
| Guardrails | 护栏，对输入输出的安全与合规检查 |
| Prompt Injection | 提示注入，通过输入内容操纵模型执行非预期行为 |
| Rerank | 重排，对召回结果按相关性精排 |
| Latency / Throughput | 延迟（单个请求耗时）/ 吞吐（单位时间请求数） |

---

## 37. 常见问题与故障排查

### 37.1 `ModuleNotFoundError: No module named 'xxx'`

```text
ModuleNotFoundError: No module named 'httpx'
```

原因：没有安装，或装到了另一个 Python/虚拟环境。

```powershell
python -m pip install httpx
python -c "import httpx; print(httpx.__version__)"
```

如果已安装仍报错，检查当前终端是否激活了正确的虚拟环境（见 11.3），并确认 `python` 与 `pip` 属于同一个解释器。

### 37.2 中文乱码

- 代码里 `print("中文")` 出现乱码：Windows 终端编码问题，参考 0.3；
- 读写文件乱码：`open` 时显式指定 `encoding="utf-8"`；
- JSON 中文被转成 `\uXXXX`：`json.dumps(data, ensure_ascii=False)`。

### 37.3 网络相关：超时、SSL、代理

- 请求一直卡住：检查是否设置了 `timeout`（见 16.3）；
- SSL 证书错误：通常是公司代理或系统时间问题，不要用 `verify=False` 一关了之；
- 访问外网不稳定：确认代理或镜像配置，不要在代码里硬编码代理；
- 429：限流，读取 `Retry-After` 并按退避重试（见 24.3）。

### 37.4 类型相关报错

```text
TypeError: can only concatenate str (not "int") to str
TypeError: 'int' object is not callable
TypeError: missing 1 required positional argument
```

- 前两个：类型不匹配或变量遮蔽了函数名，检查赋值；
- 第三个：调用函数时少传了参数，对照函数签名检查；
- 处理外部数据（HTTP、文件）时，先 `print(type(x))` 确认实际类型。

### 37.5 异步相关报错

```text
RuntimeWarning: coroutine 'fetch' was never awaited
```

原因：调用了 `async def` 函数但没用 `await` 或 `create_task`。修正：

```python
result = await fetch(1)                 # 直接等待
task = asyncio.create_task(fetch(1))    # 或创建任务
```

- `asyncio.run()` 只能调用一次且必须作为程序入口；
- 在 `async def` 里用 `time.sleep()` 会阻塞事件循环，改用 `asyncio.sleep()` 或 `asyncio.to_thread()`（见 23.4）。

### 37.6 文件路径问题

- Windows 路径字符串：优先用 `Path`（见 12.1），避免手写 `\`；
- “找不到文件”却确认文件存在：检查当前工作目录，用 `Path(__file__).parent` 定位脚本所在目录；
- 文件名与标准库同名（如 `json.py`）导致导入错误：改名。

### 37.7 调试建议

1. 从 Traceback 最后一行开始读，先修“第一个真正出错的位置”；
2. 用 `print()` 或日志打印关键变量的类型和值（`f"{x!r}"` 能看出隐藏字符）；
3. 把报错信息和最小复现代码一起搜索或问 AI；
4. 修好一类问题后，加一条对应测试，避免回归（见第 28 章）。

---

## 最后的判断

面向 AI 开发，Python 最重要的不是记住所有语法，而是具备四层能力：

```text
语言层：对象、容器、函数、异常、类、类型。
数据层：文件、JSON、数组、批处理、生成器。
服务层：HTTP、API、校验、日志、配置、测试。
并发层：线程、进程、asyncio、超时、重试、限流。
```

掌握这些内容后，LangChain、模型 SDK、RAG、Agent 和推理服务中的大多数 Python 代码都会变成这些基础能力的组合，而不是完全陌生的新语法。











