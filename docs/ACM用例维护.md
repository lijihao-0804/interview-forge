# ACM 公开用例与运行检查

题库入口：<https://hot100.xyz/books/ai-exam/index.html>。进入题目后，代码旁的“运行代码”会打开 ACM 编辑器；点击“运行全部用例”会使用当前代码逐个执行该题的公开用例。每组用例独立启动程序，不把多个输入拼接成一次运行。

用例分为题面样例和站内补充。补充用例覆盖最小合法输入、边界、重复与并列、排序和逆序、不可达、零和负数（仅在题意允许时）、一般组合及常见错误。它们不能替代原平台隐藏测试；通过所有用例只能说明通过当前公开测试。

## 维护入口

- `scripts/check/acm_cases_a.py`、`acm_cases_b.py`、`acm_cases_c.py`：按题意使用独立暴力、直接模拟、公式或手工推导生成补充期望，不把题库参考程序当作唯一 oracle。
- `data/ai_exam/practice-cases-{a,b,c}.json`：逐题 checker、输入、期望、名称、类别、验证方法，以及有证据的题面提取错误排除记录。
- `data/ai_exam/practice-code-fixes.json`：已确认的最小代码勘误，单独保存，保留原始收录材料和来源；构建时在题页显示勘误说明。
- `scripts/build/build_ai_exam.py`：保留题面样例、追加去重后的补充用例；出现同一输入冲突答案、未知题目、无效 checker 或超执行输入限制时阻止构建。
- `books/ai-exam/practice-meta.json`：生成的发布目录。携带的代码与最终题页一致，包括已有标准 Java 修订，不能手工编辑。

重新生成并构建：

```powershell
python scripts/check/acm_cases_a.py
python scripts/check/acm_cases_b.py
python scripts/check/acm_cases_c.py
python scripts/build/build_ai_exam.py
```

## 一次执行全部参考程序

```powershell
python scripts/check/check_acm_cases.py --language both
```

可以使用 `--language python`、`--language java`、`--id 标题片段`、`--report 输出.json`，以及 `--workers 1` 降低机器负载。默认最多四个题目并行，每题内部顺序运行；Java 每题只编译一次，使用 Java 17 编译目标。需要 Node.js、JDK 和题目使用的 Python 科学计算库。命令只执行仓库内经过审核的参考程序，不提供任意用户代码的沙箱服务。网站执行用户代码仍使用现有独立沙箱、输入输出及运行时间限制。

报告包含每个语言、题目、用例的实际输出和判定。退出码 0 表示没有自动检查失败；`review` 表示题面有歧义或缺少稳定判定规则，不能计作“已证明正确”。运行、编译、超时和服务异常分别记录。

生产沙箱给每个进程固定单个 BLAS/OpenMP 数值线程，避免科学计算库创建线程池时耗尽启动预算；Python 与 Java 运行仍限制为 3 秒，内存、进程数、网络隔离和输出上限保持执行器定义。

## 防止误判

普通整数序列按 token 比较；必须保留行结构的输出使用 exact。浮点按题面打印精度设置绝对/相对公差，JSON 按结构比较并保留数组顺序。没有统一强套 `1e-6`。不能把一个浮点算法的舍入差异当作整道题的错误。

有多个合法答案时优先使用语义 checker，例如检查排列达到最大总和、逐个区间计数、重排的元素与间距、最大数位和。语义规则无法从材料确定时，显示“待人工核对”，说明原因，不强行逐字比较。

批量评测固定点击时的代码和语言，支持停止。服务繁忙有限重试；服务错误、登录失效或中途停止后，剩余用例标为未执行。输出详情均以文本呈现，用户修改输入和期望不会改变内置用例。游客可阅读，运行单例或全部用例均需要登录。

## Hot 100 两卷的站内提交评测

`data/acm/hot100.json` 和 `data/acm/hot200-extra.json` 分别提供第一卷和第二卷的正式判题用例。两卷各 100 题，目前分别有 332 和 200 组输入。每一行输入是一个 JSON 参数，每次运行输出一个 JSON 值；链表、树、操作序列和多解排序等约定见各题的 `case_note`。

```powershell
python -m scripts.check.check_native_acm_references --report logs/native-acm-check/full.jsonl
python -m scripts.check.check_native_acm_references --id hot100-5 --language java
```

命令从正式题页读取 Java、Python 的主解法，按约定补上平台提供的节点、交互接口和输入输出入口。同一题的程序与样例数据分别构造，各用例均在独立进程中从 stdin 读取实际输入，再将原始 stdout 交给提交接口使用的 `native_acm.matches`。Java 在本机按题编译一次，目标为 JDK 17。报告逐例记录程序 SHA-256、输入、期望、stdout、stderr 和判定，用 `--volume hot100` 或 `--volume hot200` 可单独复跑一卷。

生产 Linux 主机使用部署版本的 Python 运行 `python -m scripts.check.check_native_acm_references --engine sandbox --workers 1 --report <报告路径>`。使用与 `practice-runner.service` 相同的系统用户及 bwrap、Python、JDK 配置，安排在独立低优先级进程或 systemd 单元中。每组调用正式执行器，使用线上编译、运行、隔离和输出限制。该路径只读取题库与题页，报告写入指定文件。退出码 0 表示所选的每一题、每种语言、每一例均通过。
