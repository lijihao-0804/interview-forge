# 性能优化与连接诊断实测数据

测试日期：2026-10-02 至 2026-10-03；归档日期：2026-10-09。
此目录只包含性能聚合指标与无正文的逐请求耗时，不包含凭据、Cookie、用户记录、原始日志或私有部署信息。

## 应用优化前后

4 核、16GB 单主机，本机 loopback，同一授权用户，5/15 VU 各约8秒。单 worker 基线版本 `2b01df99`；四 worker 优化版 `be63a021`。使用当时的单连接池压测方法，两侧一致，但短时结果仍可能受生成器影响。

| 接口 / VU | 优化前 RPS | 优化后 RPS | 优化前 P95 | 优化后 P95 |
| --- | ---: | ---: | ---: | ---: |
| health / 5 | 1061.9 | 1349.9 | 7ms | 6ms |
| health / 15 | 944.0 | 887.6 | 46ms | 54ms |
| bootstrap / 5 | 161.9 | 180.9 | 49ms | 69ms |
| bootstrap / 15 | 107.1 | 356.5 | 181ms | 161ms |

所有档位错误率0。15 VU bootstrap 吞吐约3.33倍，但不是所有接口或尾延迟都改善。不以这些短时结果承诺在线人数、日活或线性扩容。

原始依据：`before-backend.json`、`after-final-backend.json`。bootstrap响应内容未保存，只有字节数和统计指标。

## 发压工具本身的瓶颈

HTTPX 0.28.1 / httpcore 1.0.9，大共享池在请求分配时遍历连接/队列。VPS同一接口150 VU、约6秒的诊断：

| 配置 | RPS | P95 | 池分配墙钟耗时 | 发压CPU时间 |
| --- | ---: | ---: | ---: | ---: |
| 单池 | 190.9 | 3389ms | 5.047s | 6.125s |
| 六池，总VU不变 | 703.1 | 620ms | 2.862s | 5.993s |

计时是诊断进程内包装连接分配函数所得；墙钟耗时与CPU时间不应严格相加。依据：`client-pool-vps-2026-10-03.json`。客户端接近一核满载，原报告的“约64连接服务器硬上限”并未得到证实。

修正主压测脚本后，本机 health 50/100/150 VU分别1342.6/1019.4/824.7 RPS，P95分别88/236/443ms，零错误。依据：`corrected-ramp-vps-2026-10-03.json`。发压端仍可能成为瓶颈，这不是服务容量上限。

## 公网与TLS诊断

`connection-probe-*` 保存原单池方法的初轮测试，不能作为纯服务容量依据。`client-pool-windows-*` 表明拆池后公网仍有超时，属于另一问题。

Linux curl默认支持HTTP/2，Windows系统curl仅HTTP/1.1；默认结果不可直接比较。`tls-probe-vps-http1-*` 用HTTP/1.1对齐，逐请求字段包含DNS/TCP/TLS/首字节/总耗时和错误，无响应正文。

固定DNS并显式关闭代理后，Windows150并发的一次配对窗口，TCP connect P95约7251ms，总耗时P95约7797ms。各阶段P95可能来自不同请求，不能相减当成精确分解。

限定自有诊断来源的握手元数据采样：100条SYN流均到达且获服务器回复，首次SYN→SYN-ACK P95=0.052ms、最大0.058ms，重复SYN9次、重复SYN-ACK19次。原始握手及来源地址不公开。说明握手路径存在重传，不支持应用/数据库处理慢或服务器秒级SYN应答迟滞的解释；尚需第二网络对照才能确定具体设备或运营商因素。

`client-pool-tunnel-*` 属于受限诊断：临时隧道最终报Too many open files，不能用作容量或网络归因证据。保留数据是为了公开限制，而非择优展示。

## 复现与安全

脚本位于 `scripts/benchmarks/`：http_load.py、client_pool_diagnosis.py、tls_connection_diagnosis.py、connection_probe_local.py。

```powershell
python scripts/benchmarks/http_load.py ramp --target http://127.0.0.1:8765 --path /api/health --ramp "50:6,100:6,150:6" --out health.json
python scripts/benchmarks/client_pool_diagnosis.py --target http://127.0.0.1:8765 --out pool.json
```

仅对自己拥有且允许压测的服务运行；默认先用低并发。本批没有学习状态写压测、FSRS真实评分或Lighthouse数据，不把它们宣称为已验收。部分初轮样本窗口重叠、无预热、持续时间短；严格容量测量应使用隔离、多进程/多机生成器和长时样本。

内部完整复盘、运维备份路径及其他项目文档继续留在本地，不随本批公开。
