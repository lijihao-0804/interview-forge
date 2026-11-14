# 聊天历史检索的本地 E5 编码器

应用在本机 CPU 编码当前查询和获准访问的历史片段。模型权重、分词器和 Python 原生库均由部署阶段准备。运行时使用 ONNX Runtime 的 CPUExecutionProvider。

## 来源与固定版本

PEP 508 依赖固定在 `requirements-history-embeddings.txt`。模型安装器和应用共同读取 `interview_forge/ai/embedding_spec.py` 中的文件名、大小和 SHA-256。

| 本地文件 | 上游文件 | 字节 | SHA-256 |
|---|---|---:|---|
| `model.onnx` | `onnx/model_quantized.onnx` | 118308185 | `f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193` |
| `tokenizer.json` | `tokenizer.json` | 17082730 | `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39` |

原始 intfloat/multilingual-e5-small 模型标注 MIT 许可，模型卡说明了查询和文段的英文前缀、掩码平均池化及 384 维表示。Xenova 的模型卡将 ONNX 转换关联到该原模型。两个仓库的分词器 SHA-256 相同。[原始模型与许可](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3) · [原作者使用说明](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/README.md) · [固定的 ONNX 转换版本](https://huggingface.co/Xenova/multilingual-e5-small/tree/761b726dd34fb83930e26aab4e9ac3899aa1fa78)

## 安装、核对与启用

在应用根目录执行，使用服务实际运行的 Python 3.11+ 虚拟环境。以下示例适用于 Linux。

```sh
.venv/bin/python -m pip install --only-binary=:all: -r requirements-history-embeddings.txt
sudo -u forge .venv/bin/python -m scripts.maintenance.provision_history_embeddings
sudo -u forge .venv/bin/python -m scripts.maintenance.provision_history_embeddings --verify-only
```

默认模型目录是 `data/runtime/semantic-models/multilingual-e5-small-q8`。安装器校验两份下载后在同一文件系统内发布整个目录，重复执行会核对已有文件。`--directory` 可指定其他目录。迁移或恢复时，选择一个尚未创建的目标路径，由安装器创建该目录，执行同路径的 `--verify-only`，再把服务目录配置指向新位置。

Windows 项目 AI 环境使用以下 PowerShell 命令。

```powershell
& .\.venv-ai\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-history-embeddings.txt
& .\.venv-ai\Scripts\python.exe -m scripts.maintenance.provision_history_embeddings
$env:AI_HISTORY_EMBEDDING_DIR = (Resolve-Path 'data/runtime/semantic-models/multilingual-e5-small-q8').Path
```

部署主进程将下列设置放入该服务专用的 systemd drop-in，然后在发布窗口执行 daemon-reload 并重启服务。回退时移除本次 drop-in 中的设置再重启，已有普通聊天及词面检索仍由原有配置使用。

```ini
[Service]
Environment="AI_HISTORY_EMBEDDING_DIR=/opt/interview-forge/data/runtime/semantic-models/multilingual-e5-small-q8"
```

可以先用部署账户和相同环境变量在单独进程运行这个最小检查。从仓库根目录以应用 Python 执行，预期得到 `CPUExecutionProvider` 和 1536 字节。该命令运行的合成语句只存在于进程内。

```python
from interview_forge.ai.history_encoder import history_encoder

encoder = history_encoder()
assert encoder is not None
blob, = encoder.encode(["周末的读书会在哪里集合？"], query=True)
assert len(blob) == 384 * 4
print(encoder.session.get_providers(), len(blob))
```

## 工作进程与首次检索

Uvicorn 的四个 worker 是独立进程。默认情况下，每个 worker 在第一次调用 `history_encoder()` 时校验文件并加载自己的原生会话，此后在该 worker 生命周期内复用。仅启动服务时常驻会话数为零，每个收到语义检索的 worker 增加一份，四个 worker 都收到相应请求后可以常驻四份。进程内的加载锁串行化同一 worker 的首次加载。用户的持久化索引与 worker 的模型会话可以分别复用。

如需提前构建某个账号已有消息的索引，可在设置相同模型目录后，对该账号的现有学习库运行以下命令。`--session` 可选，指定后只处理该会话。命令复用已有向量，输出会话数、片段数和新增向量数。

```sh
.venv/bin/python -m scripts.maintenance.backfill_history_embeddings --database "$ACCOUNT_DB" --session "$SESSION_ID"
```

负载较低时可保留按需加载，首个接到语义检索的 worker 承担冷启动。需要预热时，可用专用测试账号在部署后逐个执行需要历史检索的请求，结合进程可用的观测信息确认覆盖。负载均衡可能重复选中同一 PID。在需要保证四份就绪的部署中，可在各 worker 的应用启动钩子内调用 `history_encoder()` 并对一条合成查询执行 `encode(..., query=True)`，分批启动以控制并发加载。独立预检命令和 systemd 的 ExecStartPre 只会预热操作系统文件缓存，进程退出时它的 ONNX 会话随之释放。

## 生产主机上的离线容量测量

2026-11-14 在同一台 4 vCPU Linux 主机上以服务账户单独运行 CPU 编码。500 行与 1280 行是两组互不重合、可重复生成的中文对话片段。两组均为中位 107 字、80 个模型 token，长度范围合计 35–192 字。各设置各用一个新进程，依次运行，最大长度 256 个 token，每批最多 16 条，在每组相邻 32 条内按长度排序，关闭额外的 tokenizer 并行。未将数据库查询、用户消息、多 worker 同时索引、模型回复计入编码时间。

| 片段数 | ONNX 推理线程 | 纯片段编码 | 原生库导入、校验、加载与编码合计 | 进程峰值 RSS |
|---:|---:|---:|---:|---:|
| 500 | 1 | 7.10 s | 10.28 s | 566.7 MiB |
| 500 | 2 | 3.83 s | 4.96 s | 565.8 MiB |
| 1280 | 1 | 15.57 s | 16.54 s | 568.8 MiB |
| 1280 | 2 | 11.27 s | 13.72 s | 569.2 MiB |

这些进程复用了系统文件缓存，加载后 RSS 约 463 MiB，七次热查询的中位时延为 2.9–3.6 ms。模型刚下载时的单独首次加载实测 10.06 s。以四份最高单进程 RSS 粗算约 2.22 GiB，包含可共享页和各进程的 Python 基线，生产总体内存还受 Web 应用、并发与具体输入影响。

四个生产 worker 共用四个逻辑核，默认每份 ONNX 会话使用一个推理线程。按单线程 1280 条的本次样本计算，进入编码阶段 10 s 完成 800 条，15 s 完成 1232 条。首次请求的等待时间还包括模型加载、检索锁、分词和数据库读写。对于 30 s 的硬工具超时，可将 20 s 软预算从工具入口开始计时，预留查询、读取已验证片段与返回结果的时间。若尚有未索引内容，按实际覆盖范围返回并复用已完成的索引，下次检索再继续。站点流量增加或消息普遍变长时，应按相同口径复测。
