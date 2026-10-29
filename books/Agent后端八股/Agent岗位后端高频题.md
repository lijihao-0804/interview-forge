# Agent 岗位后端高频题

> 来源：[Snailclimb/JavaGuide](https://github.com/Snailclimb/JavaGuide)（★159k，Apache-2.0 License）。本项目仅本地学习使用。
>
> 岗位定位：**Agent / AI 应用开发岗位会追问的后端问题**。内容取自 JavaGuide 的问答式题集，答案正文保持原样未改。

## 为什么 Agent 岗位要准备后端题

Agent 岗位的实际面试里，后端问题通常不是单独一轮，而是**揉在系统设计里追问**：

- 你说用了缓存 → 追问 Redis 缓存穿透/雪崩怎么处理、语义缓存怎么设计；
- 你说任务异步执行 → 追问消息队列怎么保证不丢、怎么幂等；
- 你说流式返回 → 追问 SSE 和 WebSocket 的区别、长连接怎么扛并发；
- 你说多租户 → 追问数据隔离怎么做、权限模型怎么设计。

所以这部分不需要像后端岗那样背全，**重点是能接住追问**。建议按下面的顺序看：Redis 与缓存 → 消息队列 → 网络协议（SSE/WebSocket）→ MySQL → 并发。

> 说明：Java 并发一章为 Java 专属，Python/Go 岗位可跳过；其余章节语言无关，通用。

## 章节总览

| 章 | 覆盖内容 | 题数 |
|---|---|---|
| Redis 与缓存 | 缓存策略、数据结构、持久化、分布式锁——Agent 服务最常被问的存储层 | 55 |
| MySQL 与索引 | 索引原理、事务与 MVCC、锁、优化——会话与知识库的落库基础 | 55 |
| 消息队列 | Kafka / RocketMQ / RabbitMQ 的可靠性、顺序、幂等与选型 | 77 |
| 网络协议 | TCP/UDP、HTTP 演进、WebSocket 与长连接——Agent 流式输出必考 | 51 |
| Java 并发 | 线程池、锁、JMM、并发容器——Java 服务端 Agent 的并发基础 | 89 |

合计 **327 题**。

## Redis 与缓存

> 缓存策略、数据结构、持久化、分布式锁——Agent 服务最常被问的存储层（55 题）

### 【Redis 基础】

#### 什么是 Redis？

[Redis](https://redis.io/) （**RE**mote **DI**ctionary **S**erver）是一个基于 C 语言开发的开源 NoSQL 数据库（BSD 许可）。与传统数据库不同的是，Redis 的数据是保存在内存中的（内存数据库，支持持久化），因此读写速度非常快，被广泛应用于分布式缓存方向。并且，Redis 存储的是 KV 键值对数据。

为了满足不同的业务场景，Redis 内置了多种数据类型实现（比如 String、Hash、Sorted Set、Bitmap、HyperLogLog、GEO）。并且，Redis 还支持事务、持久化、Lua 脚本、发布订阅模型、多种开箱即用的集群方案（Redis Sentinel、Redis Cluster）。

![Redis 数据类型概览](images/redis-overview-of-data-types-2023-09-28-6335ecff.jpg)

Redis 没有外部依赖，Linux 和 OS X 是 Redis 开发和测试最多的两个操作系统，官方推荐生产环境使用 Linux 部署 Redis。

个人学习的话，你可以自己本机安装 Redis 或者通过 Redis 官网提供的[在线 Redis 环境](https://try.redis.io/)（少部分命令无法使用）来实际体验 Redis。

![try-redis](images/try.redis.io-34d730cc.png)

全世界有非常多的网站使用到了 Redis，[techstacks.io](https://techstacks.io/) 专门维护了一个[使用 Redis 的热门站点列表](https://techstacks.io/tech/redis)，感兴趣的话可以看看。

#### ⭐️Redis 为什么这么快？

Redis 内部做了非常多的性能优化，比较重要的有下面 4 点：

1. **纯内存操作 (Memory-Based Storage)** ：这是最主要的原因。Redis 数据读写操作都发生在内存中，访问速度是纳秒级别，而传统数据库频繁读写磁盘的速度是毫秒级别，两者相差数个数量级。
2. **高效的 I/O 模型 (I/O Multiplexing & Single-Threaded Event Loop)** ：Redis 使用单线程事件循环配合 I/O 多路复用技术，让单个线程可以同时处理多个网络连接上的 I/O 事件（如读写），避免了多线程模型中的上下文切换和锁竞争问题。虽然是单线程，但结合内存操作的高效性和 I/O 多路复用，使得 Redis 能轻松处理大量并发请求（Redis 线程模型会在后文中详细介绍到）。
3. **优化的内部数据结构 (Optimized Data Structures)** ：Redis 提供多种数据类型（如 String, List, Hash, Set, Sorted Set 等），其内部实现采用高度优化的编码方式（如 ziplist, quicklist, skiplist, hashtable 等）。Redis 会根据数据大小和类型动态选择最合适的内部编码，以在性能和空间效率之间取得最佳平衡。
4. **简洁高效的通信协议 (Simple Protocol - RESP)** ：Redis 使用的是自己设计的 RESP (REdis Serialization Protocol) 协议。这个协议实现简单、解析性能好，并且是二进制安全的。客户端和服务端之间通信的序列化/反序列化开销很小，有助于提升整体的交互速度。

> 下面这张图片总结的挺不错的，分享一下，出自 [Why is Redis so fast?](https://twitter.com/alexxubyte/status/1498703822528544770)。

![why-redis-so-fast](images/why-redis-so-fast-c4e8975b.png)

那既然都这么快了，为什么不直接用 Redis 当主数据库呢？主要是因为内存成本太高，并且 Redis 提供的数据持久化仍然有数据丢失的风险。

#### 除了 Redis，你还知道其他分布式缓存方案吗？

如果面试中被问到这个问题的话，面试官主要想看看：

1. 你在选择 Redis 作为分布式缓存方案时，是否是经过严谨的调研和思考，还是只是因为 Redis 是当前的“热门”技术。
2. 你在分布式缓存方向的技术广度。

如果你了解其他方案，并且能解释为什么最终选择了 Redis（更进一步！），这会对你面试表现加分不少！

下面简单聊聊常见的分布式缓存技术选型。

分布式缓存的话，比较老牌同时也是使用的比较多的还是 **Memcached** 和 **Redis**。不过，现在基本没有看过还有项目使用 **Memcached** 来做缓存，都是直接用 **Redis**。

Memcached 是分布式缓存最开始兴起的那会，比较常用的。后来，随着 Redis 的发展，大家慢慢都转而使用更加强大的 Redis 了。

有一些大厂也开源了类似于 Redis 的分布式高性能 KV 存储数据库，例如，腾讯开源的 [**Tendis**](https://github.com/Tencent/Tendis)。Tendis 基于知名开源项目 [RocksDB](https://github.com/facebook/rocksdb) 作为存储引擎 ，100% 兼容 Redis 协议和 Redis4.0 所有数据模型。关于 Redis 和 Tendis 的对比，腾讯官方曾经发过一篇文章：[Redis vs Tendis：冷热混合存储版架构揭秘](https://mp.weixin.qq.com/s/MeYkfOIdnU6LYlsGb24KjQ)，可以简单参考一下。

不过，从 Tendis 这个项目的 Github 提交记录可以看出，Tendis 开源版几乎已经没有被维护更新了，加上其关注度并不高，使用的公司也比较少。因此，不建议你使用 Tendis 来实现分布式缓存。

目前，比较业界认可的 Redis 替代品还是下面这两个开源分布式缓存（都是通过碰瓷 Redis 火的）：

- [Dragonfly](https://github.com/dragonflydb/dragonfly)：一种针对现代应用程序负荷需求而构建的内存数据库，完全兼容 Redis 和 Memcached 的 API，迁移时无需修改任何代码，号称全世界最快的内存数据库。
- [KeyDB](https://github.com/Snapchat/KeyDB)：Redis 的一个高性能分支，专注于多线程、内存效率和高吞吐量。

不过，个人还是建议分布式缓存首选 Redis，毕竟经过了这么多年的考验，生态非常优秀，资料也很全面！

PS：篇幅问题，我这并没有对上面提到的分布式缓存选型做详细介绍和对比，感兴趣的话，可以自行研究一下。

#### 说一下 Redis 和 Memcached 的区别和共同点

现在公司一般都是用 Redis 来实现缓存，而且 Redis 自身也越来越强大了！不过，了解 Redis 和 Memcached 的区别和共同点，有助于我们在做相应的技术选型的时候，能够做到有理有据！

**共同点**：

1. 都是基于内存的数据库，一般都用来当做缓存使用。
2. 都有过期策略。
3. 两者的性能都非常高。

**区别**：

1. **数据类型**：Redis 支持更丰富的数据类型（支持更复杂的应用场景）。Redis 不仅仅支持简单的 k/v 类型的数据，同时还提供 list、set、zset、hash 等数据结构的存储；而 Memcached 只支持最简单的 k/v 数据类型。
2. **数据持久化**：Redis 支持数据的持久化，可以将内存中的数据保持在磁盘中，重启的时候可以再次加载进行使用；而 Memcached 把数据全部存在内存之中。也就是说，Redis 有灾难恢复机制，而 Memcached 没有。
3. **集群模式支持**：Memcached 没有原生的集群模式，需要依靠客户端来实现往集群中分片写入数据；而 Redis 自 3.0 版本起是原生支持集群模式的。
4. **线程模型**：Memcached 是多线程、非阻塞 IO 复用的网络模型；而 Redis 使用单线程的多路 IO 复用模型（Redis 6.0 针对网络数据的读写引入了多线程）。
5. **特性支持**：Redis 支持发布订阅模型、Lua 脚本、事务等功能，而 Memcached 不支持。并且，Redis 支持更多的编程语言。
6. **过期数据删除**：Memcached 过期数据的删除策略只用了惰性删除，而 Redis 同时使用了惰性删除与定期删除。

相信看了上面的对比之后，我们已经没有什么理由可以选择使用 Memcached 来作为自己项目的分布式缓存了。

#### ⭐️为什么要用 Redis？

**1、访问速度更快**

传统数据库数据保存在磁盘，而 Redis 基于内存，内存的访问速度比磁盘快很多。引入 Redis 之后，我们可以把一些高频访问的数据放到 Redis 中，这样下次就可以直接从内存中读取，速度可以提升几十倍甚至上百倍。

**2、高并发**

一般像 MySQL 这类的数据库的 QPS 大概都在 4k 左右（4 核 8g），但是使用 Redis 缓存之后很容易达到 5w+，甚至能达到 10w+（就单机 Redis 的情况，Redis 集群的话会更高）。

> QPS（Query Per Second）：服务器每秒可以执行的查询次数；

由此可见，直接操作缓存能够承受的数据库请求数量是远远大于直接访问数据库的，所以我们可以考虑把数据库中的部分数据转移到缓存中去，这样用户的一部分请求会直接到缓存这里而不用经过数据库。进而，我们也就提高了系统整体的并发。

**3、功能全面**

Redis 除了可以用作缓存之外，还可以用于分布式锁、限流、消息队列、延时队列等场景，功能强大！

#### ⭐️为什么用 Redis 而不用本地缓存呢？

| 特性         | 本地缓存                             | Redis                            |
| ------------ | ------------------------------------ | -------------------------------- |
| 数据一致性   | 多服务器部署时存在数据不一致问题     | 数据一致                         |
| 内存限制     | 受限于单台服务器内存                 | 独立部署，内存空间更大           |
| 数据丢失风险 | 服务器宕机数据丢失                   | 可持久化，数据不易丢失           |
| 管理维护     | 分散，管理不便                       | 集中管理，提供丰富的管理工具     |
| 功能丰富性   | 功能有限，通常只提供简单的键值对存储 | 功能丰富，支持多种数据结构和功能 |

关于本地缓存、分布式缓存和多级缓存的详细介绍，可以看我写的这篇文章：[缓存基础常见面试题总结](https://javaguide.cn/database/redis/cache-basics.html)。

#### 常见的缓存读写策略有哪些？

关于常见的缓存读写策略的详细介绍，可以看我写的这篇文章：[3 种常用的缓存读写策略详解](https://javaguide.cn/database/redis/3-commonly-used-cache-read-and-write-strategies.html)。

#### 什么是 Redis Module？有什么用？

Redis 从 4.0 版本开始，支持通过 Module 来扩展其功能以满足特殊的需求。这些 Module 以动态链接库（so 文件）的形式被加载到 Redis 中，这是一种非常灵活的动态扩展功能的实现方式，值得借鉴学习！

我们每个人都可以基于 Redis 去定制化开发自己的 Module，比如实现搜索引擎功能、自定义分布式锁和分布式限流。

目前，被 Redis 官方推荐的 Module 有：

- [RediSearch](https://github.com/RediSearch/RediSearch)：用于实现搜索引擎的模块。
- [RedisJSON](https://github.com/RedisJSON/RedisJSON)：用于处理 JSON 数据的模块。
- [RedisGraph](https://github.com/RedisGraph/RedisGraph)：用于实现图形数据库的模块。
- [RedisTimeSeries](https://github.com/RedisTimeSeries/RedisTimeSeries)：用于处理时间序列数据的模块。
- [RedisBloom](https://github.com/RedisBloom/RedisBloom)：用于实现布隆过滤器的模块。
- [RedisAI](https://github.com/RedisAI/RedisAI)：用于执行深度学习/机器学习模型并管理其数据的模块。
- [RedisCell](https://github.com/brandur/redis-cell)：用于实现分布式限流的模块。
- ……

关于 Redis 模块的详细介绍，可以查看官方文档：。

### 【⭐️Redis 应用】

#### Redis 除了做缓存，还能做什么？

- **分布式锁**：通过 Redis 来做分布式锁是一种比较常见的方式。通常情况下，我们都是基于 Redisson 来实现分布式锁。关于 Redis 实现分布式锁的详细介绍，可以看我写的这篇文章：[分布式锁详解](https://javaguide.cn/distributed-system/distributed-lock.html)。
- **限流**：一般是通过 Redis + Lua 脚本的方式来实现限流。如果不想自己写 Lua 脚本的话，也可以直接利用 Redisson 中的 `RRateLimiter` 来实现分布式限流，其底层实现就是基于 Lua 代码+令牌桶算法。
- **消息队列**：Redis 自带的 List 数据结构可以作为一个简单的队列使用。Redis 5.0 中增加的 Stream 类型的数据结构更加适合用来做消息队列。它比较类似于 Kafka，有主题和消费组的概念，支持消息持久化以及 ACK 机制。
- **延时队列**：Redisson 内置了延时队列（基于 Sorted Set 实现的）。
- **分布式 Session**：利用 String 或者 Hash 数据类型保存 Session 数据，所有的服务器都可以访问。
- **复杂业务场景**：通过 Redis 以及 Redis 扩展（比如 Redisson）提供的数据结构，我们可以很方便地完成很多复杂的业务场景，比如通过 Bitmap 统计活跃用户、通过 Sorted Set 维护排行榜、通过 HyperLogLog 统计网站 UV 和 PV。
- ……

#### 如何基于 Redis 实现分布式锁？

关于 Redis 实现分布式锁的详细介绍，可以看我写的这篇文章：[分布式锁详解](https://javaguide.cn/distributed-system/distributed-lock-implementations.html)。

#### Redis 可以做消息队列么？怎么实现？

先说结论：

- **如果业务简单、量小、追求极致性能**，且能容忍极小概率的数据丢失，使用 **Redis Stream** 是最优解，因为它省去了部署维护 MQ 的成本，可以复用现有的 Redis 组件（大部分需要用到 MQ 的项目，通常都会需要 Redis）。
- **如果是金融级业务、海量数据、需要严格保证不丢消息**，必须选择 **Kafka、RabbitMQ** 等更成熟的 MQ。

这个问题还是挺重要，技术选型也能用上，我专门写了一篇文章详细介绍和分析，推荐时间充足的同学抽空认真看几遍，收藏一下：[Redis 能做消息队列吗？怎么实现？](https://javaguide.cn/database/redis/redis-stream-mq.html)。

#### 如何基于 Redis 实现延时任务？

> 类似的问题：
>
> - 订单在 10 分钟后未支付就失效，如何用 Redis 实现？
> - 红包 24 小时未被查收自动退还，如何用 Redis 实现？

基于 Redis 实现延时任务的功能无非就下面两种方案：

1. Redis 过期事件监听。
2. Redisson 内置的延时队列。

Redis 过期事件监听存在时效性较差、丢消息、多服务实例下消息重复消费等问题，不被推荐使用。

Redisson 内置的延时队列具备下面这些优势：

1. **减少了丢消息的可能**：DelayedQueue 中的消息会被持久化，即使 Redis 宕机了，根据持久化机制，也只可能丢失一点消息，影响不大。当然了，你也可以使用扫描数据库的方法作为补偿机制。
2. **消息不存在重复消费问题**：每个客户端都是从同一个目标队列中获取任务的，不存在重复消费的问题。

关于 Redis 实现延时任务的详细介绍，可以看我写的这篇文章：[如何基于 Redis 实现延时任务？](https://github.com/Snailclimb/JavaGuide/blob/main/docs/redis-delayed-task.md)。

### 【⭐️Redis 数据类型】

#### Redis 常用的数据类型有哪些？

Redis 中比较常见的数据类型有下面这些：

- **5 种基础数据类型**：String（字符串）、List（列表）、Set（集合）、Hash（散列）、Zset（有序集合）。
- **3 种特殊数据类型**：HyperLogLog（基数统计）、Bitmap （位图）、Geospatial (地理位置)。

除了上面提到的之外，还有一些其他的比如 [Bloom filter（布隆过滤器）](https://javaguide.cn/cs-basics/data-structure/bloom-filter.html)、Bitfield（位域）。

#### String 的应用场景有哪些？

String 是 Redis 中最简单同时也是最常用的一个数据类型。它是一种二进制安全的数据类型，可以用来存储任何类型的数据比如字符串、整数、浮点数、图片（图片的 base64 编码或者解码或者图片的路径）、序列化后的对象。

String 的常见应用场景如下：

- 常规数据（比如 Session、Token、序列化后的对象、图片的路径）的缓存；
- 计数比如用户单位时间的请求数（简单限流可以用到）、页面单位时间的访问数；
- 分布式锁（利用 `SETNX key value` 命令可以实现一个最简易的分布式锁）；
- ……

关于 String 的详细介绍请看这篇文章：[Redis 5 种基本数据类型详解](https://javaguide.cn/database/redis/redis-data-structures-01.html)。

#### String 还是 Hash 存储对象数据更好呢？

简单对比一下二者：

- **对象存储方式**：String 存储的是序列化后的对象数据，存放的是整个对象，操作简单直接。Hash 是对对象的每个字段单独存储，可以获取部分字段的信息，也可以修改或者添加部分字段，节省网络流量。如果对象中某些字段需要经常变动或者经常需要单独查询对象中的个别字段信息，Hash 就非常适合。
- **内存消耗**：Hash 通常比 String 更节省内存，特别是在字段较多且字段长度较短时。Redis 对小型 Hash 进行优化（如使用 ziplist 存储），进一步降低内存占用。
- **复杂对象存储**：String 在处理多层嵌套或复杂结构的对象时更方便，因为无需处理每个字段的独立存储和操作。
- **性能**：String 的操作通常具有 O(1) 的时间复杂度，因为它存储的是整个对象，操作简单直接，整体读写的性能较好。Hash 由于需要处理多个字段的增删改查操作，在字段较多且经常变动的情况下，可能会带来额外的性能开销。

总结：

- 在绝大多数情况下，**String** 更适合存储对象数据，尤其是当对象结构简单且整体读写是主要操作时。
- 如果你需要频繁操作对象的部分字段或节省内存，**Hash** 可能是更好的选择。

#### String 的底层实现是什么？

Redis 是基于 C 语言编写的，但 Redis 的 String 类型的底层实现并不是 C 语言中的字符串（即以空字符 `\0` 结尾的字符数组），而是自己编写了 [SDS](https://github.com/antirez/sds)（Simple Dynamic String，简单动态字符串）来作为底层实现。

SDS 最早是 Redis 作者为日常 C 语言开发而设计的 C 字符串，后来被应用到了 Redis 上，并经过了大量的修改完善以适合高性能操作。

Redis7.0 的 SDS 的部分源码如下（）：

```c
/* Note: sdshdr5 is never used, we just access the flags byte directly.
 * However is here to document the layout of type 5 SDS strings. */
struct __attribute__ ((__packed__)) sdshdr5 {
    unsigned char flags; /* 3 lsb of type, and 5 msb of string length */
    char buf[];
};
struct __attribute__ ((__packed__)) sdshdr8 {
    uint8_t len; /* used */
    uint8_t alloc; /* excluding the header and null terminator */
    unsigned char flags; /* 3 lsb of type, 5 unused bits */
    char buf[];
};
struct __attribute__ ((__packed__)) sdshdr16 {
    uint16_t len; /* used */
    uint16_t alloc; /* excluding the header and null terminator */
    unsigned char flags; /* 3 lsb of type, 5 unused bits */
    char buf[];
};
struct __attribute__ ((__packed__)) sdshdr32 {
    uint32_t len; /* used */
    uint32_t alloc; /* excluding the header and null terminator */
    unsigned char flags; /* 3 lsb of type, 5 unused bits */
    char buf[];
};
struct __attribute__ ((__packed__)) sdshdr64 {
    uint64_t len; /* used */
    uint64_t alloc; /* excluding the header and null terminator */
    unsigned char flags; /* 3 lsb of type, 5 unused bits */
    char buf[];
};
```

通过源码可以看出，SDS 共有五种实现方式：SDS_TYPE_5（并未用到）、SDS_TYPE_8、SDS_TYPE_16、SDS_TYPE_32、SDS_TYPE_64，其中只有后四种实际用到。Redis 会根据初始化的长度决定使用哪种类型，从而减少内存的使用。

| 类型     | 字节 | 位  |
| -------- | ---- | --- |
| sdshdr5  | < 1  | <8  |
| sdshdr8  | 1    | 8   |
| sdshdr16 | 2    | 16  |
| sdshdr32 | 4    | 32  |
| sdshdr64 | 8    | 64  |

对于后四种实现都包含了下面这 4 个属性：

- `len`：字符串的长度也就是已经使用的字节数。
- `alloc`：总共可用的字符空间大小，alloc-len 就是 SDS 剩余的空间大小。
- `buf[]`：实际存储字符串的数组。
- `flags`：低三位保存类型标志。

SDS 相比于 C 语言中的字符串有如下提升：

1. **可以避免缓冲区溢出**：C 语言中的字符串被修改（比如拼接）时，一旦没有分配足够长度的内存空间，就会造成缓冲区溢出。SDS 被修改时，会先根据 len 属性检查空间大小是否满足要求，如果不满足，则先扩展至所需大小再进行修改操作。
2. **获取字符串长度的复杂度较低**：C 语言中的字符串的长度通常是经过遍历计数来实现的，时间复杂度为 O(n)。SDS 的长度获取直接读取 len 属性即可，时间复杂度为 O(1)。
3. **减少内存分配次数**：为了避免修改（增加/减少）字符串时，每次都需要重新分配内存（C 语言的字符串是这样的），SDS 实现了空间预分配和惰性空间释放两种优化策略。当 SDS 需要增加字符串时，Redis 会为 SDS 分配好内存，并且根据特定的算法分配多余的内存，这样可以减少连续执行字符串增长操作所需的内存重分配次数。当 SDS 需要减少字符串时，这部分内存不会立即被回收，会被记录下来，等待后续使用（支持手动释放，有对应的 API）。
4. **二进制安全**：C 语言中的字符串以空字符 `\0` 作为字符串结束的标识，这存在一些问题，像一些二进制文件（比如图片、视频、音频）就可能包括空字符，C 字符串无法正确保存。SDS 使用 len 属性判断字符串是否结束，不存在这个问题。

🤐 多提一嘴，很多文章里 SDS 的定义是下面这样的：

```c
struct sdshdr {
    unsigned int len;
    unsigned int free;
    char buf[];
};
```

这个也没错，Redis 3.2 之前就是这样定义的。后来，由于这种方式的定义存在问题，`len` 和 `free` 的定义用了 4 个字节，造成了浪费。Redis 3.2 之后，Redis 改进了 SDS 的定义，将其划分为了现在的 5 种类型。

#### 购物车信息用 String 还是 Hash 存储更好呢?

由于购物车中的商品频繁修改和变动，购物车信息建议使用 Hash 存储：

- 用户 id 为 key
- 商品 id 为 field，商品数量为 value

![Hash维护简单的购物车信息](images/hash-shopping-cart-ba56bc6c.png)

那用户购物车信息的维护具体应该怎么操作呢？

- 用户添加商品就是往 Hash 里面增加新的 field 与 value；
- 查询购物车信息就是遍历对应的 Hash；
- 更改商品数量直接修改对应的 value 值（直接 set 或者做运算皆可）；
- 删除商品就是删除 Hash 中对应的 field；
- 清空购物车直接删除对应的 key 即可。

这里只是以业务比较简单的购物车场景举例，实际电商场景下，field 只保存一个商品 id 是没办法满足需求的。

#### 使用 Redis 实现一个排行榜怎么做？

Redis 中有一个叫做 `Sorted Set`（有序集合）的数据类型经常被用在各种排行榜的场景，比如直播间送礼物的排行榜、朋友圈的微信步数排行榜、王者荣耀中的段位排行榜、话题热度排行榜等等。

相关的一些 Redis 命令：`ZRANGE`（从小到大排序）、`ZREVRANGE`（从大到小排序）、`ZREVRANK`（指定元素排名）。

[《Java 面试指北》](https://javaguide.cn/zhuanlan/java-mian-shi-zhi-bei.html) 的「技术面试题篇」就有一篇文章详细介绍如何使用 Sorted Set 来设计制作一个排行榜，感兴趣的小伙伴可以看看。

#### Redis 的有序集合底层为什么要用跳表，而不用平衡树、红黑树或者 B+ 树？

这道面试题很多大厂比较喜欢问，难度还是有点大的。

- 平衡树 vs 跳表：平衡树的插入、删除和查询的时间复杂度和跳表一样都是 **O(log n)**。对于范围查询来说，平衡树也可以通过中序遍历的方式达到和跳表一样的效果。但是它的每一次插入或者删除操作都需要保证整颗树左右节点的绝对平衡，只要不平衡就要通过旋转操作来保持平衡，这个过程是比较耗时的。跳表诞生的初衷就是为了克服平衡树的一些缺点。跳表使用概率平衡而不是严格强制的平衡，因此，跳表中的插入和删除算法比平衡树的等效算法简单得多，速度也快得多。
- 红黑树 vs 跳表：相比较于红黑树来说，跳表的实现也更简单一些，不需要通过旋转和染色（红黑变换）来保证黑平衡。并且，按照区间来查找数据这个操作，红黑树的效率没有跳表高。
- B+ 树 vs 跳表：B+ 树更适合作为数据库和文件系统中常用的索引结构之一，它的核心思想是通过可能少的 IO 定位到尽可能多的索引来获得查询数据。对于 Redis 这种内存数据库来说，它对这些并不感冒，因为 Redis 作为内存数据库它不可能存储大量的数据，所以对于索引不需要通过 B+ 树这种方式进行维护，只需按照概率进行随机维护即可，节约内存。而且使用跳表实现 zset 时相较前者来说更简单一些，在进行插入时只需通过索引将数据插入到链表中合适的位置再随机维护一定高度的索引即可，也不需要像 B+ 树那样插入时发现失衡时还需要对节点分裂与合并。

另外，我还单独写了一篇文章从有序集合的基本使用到跳表的源码分析和实现，让你会对 Redis 的有序集合底层实现的跳表有着更深刻的理解和掌握：[Redis 为什么用跳表实现有序集合](https://javaguide.cn/database/redis/redis-skiplist.html)。如果只想先过一遍跳表的基础结构、复杂度和范围查询，可以看 [跳表面试题总结](https://javaguide.cn/cs-basics/data-structure/skip-list.html)。

#### Set 的应用场景是什么？

Redis 中 `Set` 是一种无序集合，集合中的元素没有先后顺序但都唯一，有点类似于 Java 中的 `HashSet` 。

`Set` 的常见应用场景如下：

- 存放的数据不能重复的场景：网站 UV 统计（数据量巨大的场景还是 `HyperLogLog` 更适合一些）、文章点赞、动态点赞等等。
- 需要获取多个数据源交集、并集和差集的场景：共同好友（交集）、共同粉丝（交集）、共同关注（交集）、好友推荐（差集）、音乐推荐（差集）、订阅号推荐（差集+交集）等等。
- 需要随机获取数据源中的元素的场景：抽奖系统、随机点名等等。

#### 使用 Set 实现抽奖系统怎么做？

如果想要使用 `Set` 实现一个简单的抽奖系统的话，直接使用下面这几个命令就可以了：

- `SADD key member1 member2 ...`：向指定集合添加一个或多个元素。
- `SPOP key count`：随机移除并获取指定集合中一个或多个元素，适合不允许重复中奖的场景。
- `SRANDMEMBER key count`：随机获取指定集合中指定数量的元素，适合允许重复中奖的场景。

#### 使用 Bitmap 统计活跃用户怎么做？

Bitmap 存储的是连续的二进制数字（0 和 1），通过 Bitmap，只需要一个 bit 位来表示某个元素对应的值或者状态，key 就是对应元素本身。我们知道 8 个 bit 可以组成一个 byte，所以 Bitmap 本身会极大的节省储存空间。

你可以将 Bitmap 看作是一个存储二进制数字（0 和 1）的数组，数组中每个元素的下标叫做 offset（偏移量）。

![img](images/image-20220720194154133-ab812d2d.png)

如果想要使用 Bitmap 统计活跃用户的话，可以使用日期（精确到天）作为 key，然后用户 ID 为 offset，如果当日活跃过就设置为 1。

初始化数据：

```bash
> SETBIT 20210308 1 1
(integer) 0
> SETBIT 20210308 2 1
(integer) 0
> SETBIT 20210309 1 1
(integer) 0
```

统计 20210308~20210309 总活跃用户数：

```bash
> BITOP and desk1 20210308 20210309
(integer) 1
> BITCOUNT desk1
(integer) 1
```

统计 20210308~20210309 在线活跃用户数：

```bash
> BITOP or desk2 20210308 20210309
(integer) 1
> BITCOUNT desk2
(integer) 2
```

#### HyperLogLog 适合什么场景？

HyperLogLog (HLL) 是一种非常巧妙的概率性数据结构，它专门解决一类非常棘手的大数据问题：在海量数据中，用极小的内存，估算一个集合中不重复元素的数量，也就是我们常说的基数（Cardinality）

HLL 做的最核心的权衡，就是用一点点精确度的损失，来换取巨大的内存空间节省。它给出的不是一个 100%精确的数字，而是一个带有很小标准误差（Redis 中默认是 0.81%）的近似值。

**基于这个核心权衡，HyperLogLog 最适合以下特征的场景：**

1. **数据量巨大，内存敏感：** 这是 HLL 的主战场。比如，要统计一个亿级日活 App 的每日独立访客数。如果用传统的 Set 来存储用户 ID，一个 ID 占几十个字节，上亿个 ID 可能需要几个 GB 甚至几十 GB 的内存，这在很多场景下是不可接受的。而 HLL，在 Redis 中只需要固定的 12KB 内存，就能处理天文数字级别的基数，这是一个颠覆性的优势。
2. **对结果的精确度要求不是 100%：** 这是使用 HLL 的前提。比如，产品经理想知道一个热门帖子的 UV（独立访客数）是大约 1000 万还是 1010 万，这个细微的差别通常不影响商业决策。但如果场景是统计一个交易系统的准确交易笔数，那 HLL 就完全不适用，因为金融场景要求 100%的精确。

**所以，HyperLogLog 具体的应用场景就非常清晰了：**

- **网站/App 的 UV（Unique Visitor）统计：** 比如统计首页每天有多少个不同的 IP 或用户 ID 访问过。
- **搜索引擎关键词统计：** 统计每天有多少个不同的用户搜索了某个关键词。
- **社交网络互动统计：** 比如统计一条微博被多少个不同的用户转发过。

在这些场景下，我们关心的是数量级和趋势，而不是个位数的差异。

最后，Redis 的实现还非常智能，它内部会根据基数的大小，在**稀疏矩阵**（占用空间更小）和**稠密矩阵**（固定的 12KB）之间自动切换，进一步优化了内存使用。总而言之，当您需要对海量数据进行去重计数，并且可以接受微小误差时，HyperLogLog 就是不二之选。

#### 使用 HyperLogLog 统计页面 UV 怎么做？

使用 HyperLogLog 统计页面 UV 主要需要用到下面这两个命令：

- `PFADD key element1 element2 ...`：添加一个或多个元素到 HyperLogLog 中。
- `PFCOUNT key1 key2`：获取一个或者多个 HyperLogLog 的唯一计数。

1、将访问指定页面的每个用户 ID 添加到 `HyperLogLog` 中。

```bash
PFADD PAGE_1:UV USER1 USER2 ...... USERn
```

2、统计指定页面的 UV。

```bash
PFCOUNT PAGE_1:UV
```

#### 如果我想判断一个元素是否不在海量元素集合中，用什么数据类型？

这是布隆过滤器的经典应用场景。布隆过滤器可以告诉你一个元素一定不存在或者可能存在，它也有极高的空间效率和一定的误判率，但绝不会漏报。也就是说，布隆过滤器说某个元素存在，小概率会误判。布隆过滤器说某个元素不在，那么这个元素一定不在。

Bloom Filter 的简单原理图如下：

![Bloom Filter 的简单原理示意图](images/bloom-filter-simple-schematic-diagram-ecf8f3d1.png)

当字符串存储要加入到布隆过滤器中时，该字符串首先由多个哈希函数生成不同的哈希值，然后将对应的位数组的下标设置为 1（当位数组初始化时，所有位置均为 0）。当第二次存储相同字符串时，因为先前的对应位置已设置为 1，所以很容易知道此值已经存在（去重非常方便）。

如果我们需要判断某个字符串是否在布隆过滤器中时，只需要对给定字符串再次进行相同的哈希计算，得到值之后判断位数组中的每个元素是否都为 1，如果值都为 1，那么说明这个值在布隆过滤器中，如果存在一个值不为 1，说明该元素不在布隆过滤器中。

关于布隆过滤器的误判、删除困难、Guava 和 RedisBloom 使用，可以继续看 [布隆过滤器详解](https://javaguide.cn/cs-basics/data-structure/bloom-filter.html)。

### 【⭐️Redis 持久化机制（重要）】

#### ⭐️Redis 持久化机制（重要）

Redis 持久化机制（RDB 持久化、AOF 持久化、RDB 和 AOF 的混合持久化）相关的问题比较多，也比较重要，于是我单独抽了一篇文章来总结 Redis 持久化机制相关的知识点和问题：[Redis 持久化机制详解](https://javaguide.cn/database/redis/redis-persistence.html)。

### 【⭐️Redis 线程模型（重要）】

#### Redis 单线程模型了解吗？

**Redis 基于 Reactor 模式设计开发了一套高效的事件处理模型**（Netty 的线程模型也基于 Reactor 模式，Reactor 模式不愧是高性能 IO 的基石），这套事件处理模型对应的是 Redis 中的文件事件处理器（file event handler）。由于文件事件处理器（file event handler）是单线程方式运行的，所以我们一般都说 Redis 是单线程模型。

《Redis 设计与实现》有一段话是这样介绍文件事件处理器的，我觉得写得挺不错。

> Redis 基于 Reactor 模式开发了自己的网络事件处理器：这个处理器被称为文件事件处理器（file event handler）。
>
> - 文件事件处理器使用 I/O 多路复用（multiplexing）程序来同时监听多个套接字，并根据套接字目前执行的任务来为套接字关联不同的事件处理器。
> - 当被监听的套接字准备好执行连接应答（accept）、读取（read）、写入（write）、关 闭（close）等操作时，与操作相对应的文件事件就会产生，这时文件事件处理器就会调用套接字之前关联好的事件处理器来处理这些事件。
>
> **虽然文件事件处理器以单线程方式运行，但通过使用 I/O 多路复用程序来监听多个套接字**，文件事件处理器既实现了高性能的网络通信模型，又可以很好地与 Redis 服务器中其他同样以单线程方式运行的模块进行对接，这保持了 Redis 内部单线程设计的简单性。

**既然是单线程，那怎么监听大量的客户端连接呢？**

Redis 通过 **IO 多路复用程序** 来监听来自客户端的大量连接（或者说是监听多个 socket），它会将感兴趣的事件及类型（读、写）注册到内核中并监听每个事件是否发生。

这样的好处非常明显：**I/O 多路复用技术的使用让 Redis 不需要额外创建多余的线程来监听客户端的大量连接，降低了资源的消耗**（和 NIO 中的 `Selector` 组件很像）。

文件事件处理器（file event handler）主要是包含 4 个部分：

- 多个 socket（客户端连接）
- IO 多路复用程序（支持多个客户端连接的关键）
- 文件事件分派器（将 socket 关联到相应的事件处理器）
- 事件处理器（连接应答处理器、命令请求处理器、命令回复处理器）

![文件事件处理器（file event handler）](images/redis-event-handler-2997bc21.png)

#### Redis6.0 之前为什么不使用多线程？

虽然说 Redis 是单线程模型，但实际上，**Redis 在 4.0 之后的版本中就已经加入了对多线程的支持。**

不过，Redis 4.0 增加的多线程主要是针对一些大键值对的删除操作的命令，使用这些命令就会使用主线程之外的其他线程来“异步处理”，从而减少对主线程的影响。

为此，Redis 4.0 之后新增了几个异步命令：

- `UNLINK`：可以看作是 `DEL` 命令的异步版本。
- `FLUSHALL ASYNC`：用于清空所有数据库的所有键，不限于当前 `SELECT` 的数据库。
- `FLUSHDB ASYNC`：用于清空当前 `SELECT` 数据库中的所有键。

![redis4.0 more thread](images/redis4.0-more-thread-0ffdad94.png)

总的来说，直到 Redis 6.0 之前，Redis 的主要操作仍然是单线程处理的。

**那 Redis6.0 之前为什么不使用多线程？** 我觉得主要原因有 3 点：

- 单线程编程容易并且更容易维护；
- Redis 的性能瓶颈不在 CPU，主要在内存和网络；
- 多线程就会存在死锁、线程上下文切换等问题，甚至会影响性能。

相关阅读：[为什么 Redis 选择单线程模型？](https://draveness.me/whys-the-design-redis-single-thread/)。

#### Redis6.0 之后为何引入了多线程？

**Redis6.0 引入多线程主要是为了提高网络 IO 读写性能**，因为这个算是 Redis 中的一个性能瓶颈（Redis 的瓶颈主要受限于内存和网络）。

虽然，Redis6.0 引入了多线程，但是 Redis 的多线程只是在网络数据的读写这类耗时操作上使用了，执行命令仍然是单线程顺序执行。因此，你也不需要担心线程安全问题。

Redis6.0 的多线程默认是禁用的，只使用主线程。如需开启需要设置 IO 线程数 > 1，需要修改 redis 配置文件 `redis.conf`：

```bash
io-threads 4 #设置1的话只会开启主线程，官网建议4核的机器建议设置为2或3个线程，8核的建议设置为6个线程
```

另外：

- io-threads 的个数一旦设置，不能通过 config 动态设置。
- 当设置 ssl 后，io-threads 将不工作。

开启多线程后，默认只会使用多线程进行 IO 写入 writes，即发送数据给客户端，如果需要开启多线程 IO 读取 reads，同样需要修改 redis 配置文件 `redis.conf`：

```bash
io-threads-do-reads yes
```

但是官网描述开启多线程读并不能有太大提升，因此一般情况下并不建议开启。

相关阅读：

- [Redis 6.0 新特性-多线程连环 13 问！](https://mp.weixin.qq.com/s/FZu3acwK6zrCBZQ_3HoUgw)
- [Redis 多线程网络模型全面揭秘](https://segmentfault.com/a/1190000039223696)（推荐）

#### Redis 后台线程了解吗？

我们虽然经常说 Redis 是单线程模型（主要逻辑是单线程完成的），但实际还有一些后台线程用于执行一些比较耗时的操作：

- 通过 `bio_close_file` 后台线程来释放 AOF / RDB 等过程中产生的临时文件资源。
- 通过 `bio_aof_fsync` 后台线程调用 `fsync` 函数将系统内核缓冲区还未同步到到磁盘的数据强制刷到磁盘（AOF 文件）。
- 通过 `bio_lazy_free` 后台线程释放大对象（已删除）占用的内存空间.

在`bio.h` 文件中有定义（Redis 6.0 版本，源码地址：）：

```java
#ifndef __BIO_H
#define __BIO_H

/* Exported API */
void bioInit(void);
void bioCreateBackgroundJob(int type, void *arg1, void *arg2, void *arg3);
unsigned long long bioPendingJobsOfType(int type);
unsigned long long bioWaitStepOfType(int type);
time_t bioOlderJobOfType(int type);
void bioKillThreads(void);

/* Background job opcodes */
#define BIO_CLOSE_FILE    0 /* Deferred close(2) syscall. */
#define BIO_AOF_FSYNC     1 /* Deferred AOF fsync. */
#define BIO_LAZY_FREE     2 /* Deferred objects freeing. */
#define BIO_NUM_OPS       3

#endif
```

关于 Redis 后台线程的详细介绍可以查看 [Redis 6.0 后台线程有哪些？](https://juejin.cn/post/7102780434739626014) 这篇就文章。

### 【⭐️Redis 内存管理】

#### Redis 给缓存数据设置过期时间有什么用？

一般情况下，我们设置保存的缓存数据的时候都会设置一个过期时间。为什么呢？

内存是有限且珍贵的，如果不对缓存数据设置过期时间，那内存占用就会一直增长，最终可能会导致 OOM 问题。通过设置合理的过期时间，Redis 会自动删除暂时不需要的数据，为新的缓存数据腾出空间。

Redis 自带了给缓存数据设置过期时间的功能，比如：

```bash
127.0.0.1:6379> expire key 60 # 数据在 60s 后过期
(integer) 1
127.0.0.1:6379> setex key 60 value # 数据在 60s 后过期 (setex:[set] + [ex]pire)
OK
127.0.0.1:6379> ttl key # 查看数据还有多久过期
(integer) 56
```

注意 ⚠️：Redis 中除了字符串类型有自己独有设置过期时间的命令 `setex` 外，其他方法都需要依靠 `expire` 命令来设置过期时间 。另外，`persist` 命令可以移除一个键的过期时间。

**过期时间除了有助于缓解内存的消耗，还有什么其他用么？**

很多时候，我们的业务场景就是需要某个数据只在某一时间段内存在，比如我们的短信验证码可能只在 1 分钟内有效，用户登录的 Token 可能只在 1 天内有效。

如果使用传统的数据库来处理的话，一般都是自己判断过期，这样更麻烦并且性能要差很多。

#### Redis 是如何判断数据是否过期的呢？

Redis 通过一个叫做过期字典（可以看作是 hash 表）来保存数据过期的时间。过期字典的键指向 Redis 数据库中的某个 key（键），过期字典的值是一个 long long 类型的整数，这个整数保存了 key 所指向的数据库键的过期时间（毫秒精度的 UNIX 时间戳）。

![Redis 过期字典](images/redis-expired-dictionary-28e28389.png)

过期字典是存储在 redisDb 这个结构里的：

```c
typedef struct redisDb {
    ...

    dict *dict;     //数据库键空间,保存着数据库中所有键值对
    dict *expires   // 过期字典,保存着键的过期时间
    ...
} redisDb;
```

在查询一个 key 的时候，Redis 首先检查该 key 是否存在于过期字典中（时间复杂度为 O(1)），如果不在就直接返回，在的话需要判断一下这个 key 是否过期，过期直接删除 key 然后返回 null。

#### Redis 过期 key 删除策略了解么？

如果假设你设置了一批 key 只能存活 1 分钟，那么 1 分钟后，Redis 是怎么对这批 key 进行删除的呢？

常用的过期数据的删除策略就下面这几种：

1. **惰性删除**：只会在取出/查询 key 的时候才对数据进行过期检查。这种方式对 CPU 最友好，但是可能会造成太多过期 key 没有被删除。
2. **定期删除**：周期性地随机从设置了过期时间的 key 中抽查一批，然后逐个检查这些 key 是否过期，过期就删除 key。相比于惰性删除，定期删除对内存更友好，对 CPU 不太友好。
3. **延迟队列**：把设置过期时间的 key 放到一个延迟队列里，到期之后就删除 key。这种方式可以保证每个过期 key 都能被删除，但维护延迟队列太麻烦，队列本身也要占用资源。
4. **定时删除**：每个设置了过期时间的 key 都会在设置的时间到达时立即被删除。这种方法可以确保内存中不会有过期的键，但是它对 CPU 的压力最大，因为它需要为每个键都设置一个定时器。

**Redis 采用的是那种删除策略呢？**

Redis 采用的是 **定期删除+惰性/懒汉式删除** 结合的策略，这也是大部分缓存框架的选择。定期删除对内存更加友好，惰性删除对 CPU 更加友好。两者各有千秋，结合起来使用既能兼顾 CPU 友好，又能兼顾内存友好。

下面是我们详细介绍一下 Redis 中的定期删除具体是如何做的。

Redis 的定期删除过程是随机的（周期性地随机从设置了过期时间的 key 中抽查一批），所以并不保证所有过期键都会被立即删除。这也就解释了为什么有的 key 过期了，并没有被删除。并且，Redis 底层会通过限制删除操作执行的时长和频率来减少删除操作对 CPU 时间的影响。

另外，定期删除还会受到执行时间和过期 key 的比例的影响：

- 执行时间已经超过了阈值，那么就中断这一次定期删除循环，以避免使用过多的 CPU 时间。
- 如果这一批过期的 key 比例超过一个比例，就会重复执行此删除流程，以更积极地清理过期 key。相应地，如果过期的 key 比例低于这个比例，就会中断这一次定期删除循环，避免做过多的工作而获得很少的内存回收。

Redis 7.2 版本的执行时间阈值是 **25ms**，过期 key 比例设定值是 **10%**。

```c
#define ACTIVE_EXPIRE_CYCLE_FAST_DURATION 1000 /* Microseconds. */
#define ACTIVE_EXPIRE_CYCLE_SLOW_TIME_PERC 25 /* Max % of CPU to use. */
#define ACTIVE_EXPIRE_CYCLE_ACCEPTABLE_STALE 10 /* % of stale keys after which
                                                   we do extra efforts. */
```

**每次随机抽查数量是多少？**

`expire.c` 中定义了每次随机抽查的数量，Redis 7.2 版本为 20，也就是说每次会随机选择 20 个设置了过期时间的 key 判断是否过期。

```c
#define ACTIVE_EXPIRE_CYCLE_KEYS_PER_LOOP 20 /* Keys for each DB loop. */
```

**如何控制定期删除的执行频率？**

在 Redis 中，定期删除的频率是由 **hz** 参数控制的。hz 默认为 10，代表每秒执行 10 次，也就是每秒钟进行 10 次尝试来查找并删除过期的 key。

hz 的取值范围为 1~500。增大 hz 参数的值会提升定期删除的频率。如果你想要更频繁地执行定期删除任务，可以适当增加 hz 的值，但这会增加 CPU 的使用率。根据 Redis 官方建议，hz 的值不建议超过 100，对于大部分用户使用默认的 10 就足够了。

下面是 hz 参数的官方注释，我翻译了其中的重要信息（Redis 7.2 版本）。

![redis.conf 对于 hz 的注释](images/redis.conf-hz-262948fc.png)

类似的参数还有一个 **dynamic-hz**，这个参数开启之后 Redis 就会在 hz 的基础上动态计算一个值。Redis 提供并默认启用了使用自适应 hz 值的能力，

这两个参数都在 Redis 配置文件 `redis.conf` 中：

```properties
# 默认为 10
hz 10
# 默认开启
dynamic-hz yes
```

多提一嘴，除了定期删除过期 key 这个定期任务之外，还有一些其他定期任务例如关闭超时的客户端连接、更新统计信息，这些定期任务的执行频率也是通过 hz 参数决定。

**为什么定期删除不是把所有过期 key 都删除呢？**

这样会对性能造成太大的影响。如果我们 key 数量非常庞大的话，挨个遍历检查是非常耗时的，会严重影响性能。Redis 设计这种策略的目的是为了平衡内存和性能。

**为什么 key 过期之后不立马把它删掉呢？这样不是会浪费很多内存空间吗？**

因为不太好办到，或者说这种删除方式的成本太高了。假如我们使用延迟队列作为删除策略，这样存在下面这些问题：

1. 队列本身的开销可能很大：key 多的情况下，一个延迟队列可能无法容纳。
2. 维护延迟队列太麻烦：修改 key 的过期时间就需要调整其在延迟队列中的位置，并且还需要引入并发控制。

#### 大量 key 集中过期怎么办？

当 Redis 中存在大量 key 在同一时间点集中过期时，可能会导致以下问题：

- **请求延迟增加**：Redis 在处理过期 key 时需要消耗 CPU 资源，如果过期 key 数量庞大，会导致 Redis 实例的 CPU 占用率升高，进而影响其他请求的处理速度，造成延迟增加。
- **内存占用过高**：过期的 key 虽然已经失效，但在 Redis 真正删除它们之前，仍然会占用内存空间。如果过期 key 没有及时清理，可能会导致内存占用过高，甚至引发内存溢出。

为了避免这些问题，可以采取以下方案：

1. **尽量避免 key 集中过期**：在设置键的过期时间时尽量随机一点。
2. **开启 lazy free 机制**：修改 `redis.conf` 配置文件，将 `lazyfree-lazy-expire` 参数设置为 `yes`，即可开启 lazy free 机制。开启 lazy free 机制后，Redis 会在后台异步删除过期的 key，不会阻塞主线程的运行，从而降低对 Redis 性能的影响。

#### Redis 内存淘汰策略了解么？

> 相关问题：MySQL 里有 2000w 数据，Redis 中只存 20w 的数据，如何保证 Redis 中的数据都是热点数据?

Redis 的内存淘汰策略只有在运行内存达到了配置的最大内存阈值时才会触发，这个阈值是通过 `redis.conf` 的 `maxmemory` 参数来定义的。64 位操作系统下，`maxmemory` 默认为 0，表示不限制内存大小。32 位操作系统下，默认的最大内存值是 3GB。

你可以使用命令 `config get maxmemory` 来查看 `maxmemory` 的值。

```bash
> config get maxmemory
maxmemory
0
```

Redis 提供了 6 种内存淘汰策略：

1. **volatile-lru（least recently used）**：从已设置过期时间的数据集（`server.db[i].expires`）中挑选最近最少使用的数据淘汰。
2. **volatile-ttl**：从已设置过期时间的数据集（`server.db[i].expires`）中挑选将要过期的数据淘汰。
3. **volatile-random**：从已设置过期时间的数据集（`server.db[i].expires`）中任意选择数据淘汰。
4. **allkeys-lru（least recently used）**：从数据集（`server.db[i].dict`）中移除最近最少使用的数据淘汰。
5. **allkeys-random**：从数据集（`server.db[i].dict`）中任意选择数据淘汰。
6. **no-eviction**（默认内存淘汰策略）：禁止驱逐数据，当内存不足以容纳新写入数据时，新写入操作会报错。

4.0 版本后增加以下两种：

7. **volatile-lfu（least frequently used）**：从已设置过期时间的数据集（`server.db[i].expires`）中挑选最不经常使用的数据淘汰。
8. **allkeys-lfu（least frequently used）**：从数据集（`server.db[i].dict`）中移除最不经常使用的数据淘汰。

`allkeys-xxx` 表示从所有的键值中淘汰数据，而 `volatile-xxx` 表示从设置了过期时间的键值中淘汰数据。

`config.c` 中定义了内存淘汰策略的枚举数组：

```c
configEnum maxmemory_policy_enum[] = {
    {"volatile-lru", MAXMEMORY_VOLATILE_LRU},
    {"volatile-lfu", MAXMEMORY_VOLATILE_LFU},
    {"volatile-random",MAXMEMORY_VOLATILE_RANDOM},
    {"volatile-ttl",MAXMEMORY_VOLATILE_TTL},
    {"allkeys-lru",MAXMEMORY_ALLKEYS_LRU},
    {"allkeys-lfu",MAXMEMORY_ALLKEYS_LFU},
    {"allkeys-random",MAXMEMORY_ALLKEYS_RANDOM},
    {"noeviction",MAXMEMORY_NO_EVICTION},
    {NULL, 0}
};
```

你可以使用 `config get maxmemory-policy` 命令来查看当前 Redis 的内存淘汰策略。

```bash
> config get maxmemory-policy
maxmemory-policy
noeviction
```

可以通过 `config set maxmemory-policy 内存淘汰策略` 命令修改内存淘汰策略，立即生效，但这种方式重启 Redis 之后就失效了。修改 `redis.conf` 中的 `maxmemory-policy` 参数不会因为重启而失效，不过，需要重启之后修改才能生效。

```properties
maxmemory-policy noeviction
```

关于淘汰策略的详细说明可以参考 Redis 官方文档：。

#### 参考

- 《Redis 开发与运维》
- 《Redis 设计与实现》
- 《Redis 核心原理与实战》
- Redis 命令手册：
- RedisSearch 终极使用指南，你值得拥有！：
- WHY Redis choose single thread (vs multi threads): [https://medium.com/@jychen7/sharing-redis-single-thread-vs-multi-threads-5870bd44d153](https://medium.com/@jychen7/sharing-redis-single-thread-vs-multi-threads-5870bd44d153)

<!-- @include: @article-footer.snippet.md -->

### 【Redis 事务】

#### 什么是 Redis 事务？

你可以将 Redis 中的事务理解为：**Redis 事务提供了一种将多个命令请求打包的功能。然后，再按顺序执行打包的所有命令，并且不会被中途打断。**

Redis 事务实际开发中使用的非常少，功能比较鸡肋，不要将其和我们平时理解的关系型数据库的事务混淆了。

Redis 事务不提供传统关系型数据库事务中的失败回滚机制，其持久性则依赖 Redis 自身的持久化机制。事务中的每条命令都会与 Redis 服务器进行网络交互，这些命令先在服务端排队，等执行 EXEC 时再按照顺序连续执行。

Redis 事务是不建议在日常开发中使用的。

#### 如何使用 Redis 事务？

Redis 可以通过 **`MULTI`、`EXEC`、`DISCARD` 和 `WATCH`** 等命令来实现事务（Transaction）功能。

```bash
> MULTI
OK
> SET PROJECT "JavaGuide"
QUEUED
> GET PROJECT
QUEUED
> EXEC
1) OK
2) "JavaGuide"
```

[`MULTI`](https://redis.io/commands/multi) 命令后可以输入多个命令，Redis 不会立即执行这些命令，而是将它们放到队列，当调用了 [`EXEC`](https://redis.io/commands/exec) 命令后，再执行所有的命令。

这个过程是这样的：

1. 开始事务（`MULTI`）；
2. 命令入队（批量操作 Redis 的命令，先进先出（FIFO）的顺序执行）；
3. 执行事务（`EXEC`）。

你也可以通过 [`DISCARD`](https://redis.io/commands/discard) 命令取消一个事务，它会清空事务队列中保存的所有命令。

```bash
> MULTI
OK
> SET PROJECT "JavaGuide"
QUEUED
> GET PROJECT
QUEUED
> DISCARD
OK
```

你可以通过[`WATCH`](https://redis.io/commands/watch) 命令监听指定的 Key，当调用 `EXEC` 命令执行事务时，如果一个被 `WATCH` 命令监视的 Key 被 **其他客户端/Session** 修改的话，整个事务都不会被执行。

```bash
# 客户端 1
> SET PROJECT "RustGuide"
OK
> WATCH PROJECT
OK
> MULTI
OK
> SET PROJECT "JavaGuide"
QUEUED

# 客户端 2
# 在客户端 1 执行 EXEC 命令提交事务之前修改 PROJECT 的值
> SET PROJECT "GoGuide"

# 客户端 1
# 修改失败，因为 PROJECT 的值被客户端2修改了
> EXEC
(nil)
> GET PROJECT
"GoGuide"
```

不过，如果 **WATCH** 与 **事务** 在同一个 Session 里，并且被 **WATCH** 监视的 Key 被修改的操作发生在事务内部，这个事务是可以被执行成功的（相关 issue：[WATCH 命令碰到 MULTI 命令时的不同效果](https://github.com/Snailclimb/JavaGuide/issues/1714)）。

事务内部修改 WATCH 监视的 Key：

```bash
> SET PROJECT "JavaGuide"
OK
> WATCH PROJECT
OK
> MULTI
OK
> SET PROJECT "JavaGuide1"
QUEUED
> SET PROJECT "JavaGuide2"
QUEUED
> SET PROJECT "JavaGuide3"
QUEUED
> EXEC
1) OK
2) OK
3) OK
127.0.0.1:6379> GET PROJECT
"JavaGuide3"
```

事务外部修改 WATCH 监视的 Key：

```bash
> SET PROJECT "JavaGuide"
OK
> WATCH PROJECT
OK
> SET PROJECT "JavaGuide2"
OK
> MULTI
OK
> GET USER
QUEUED
> EXEC
(nil)
```

Redis 官网相关介绍 [https://redis.io/topics/transactions](https://redis.io/topics/transactions) 如下：

![Redis 事务](images/redis-transactions-a08b8862.png)

#### Redis 事务支持原子性吗？

Redis 的事务和我们平时理解的关系型数据库的事务不同。我们知道事务具有四大特性：**1. 原子性**，**2. 隔离性**，**3. 持久性**，**4. 一致性**。

1. **原子性（Atomicity）**：事务是最小的执行单位，不允许分割。事务的原子性确保动作要么全部完成，要么完全不起作用；
2. **隔离性（Isolation）**：并发访问数据库时，一个用户的事务不被其他事务所干扰，各并发事务之间数据库是独立的；
3. **持久性（Durability）**：一个事务被提交之后。它对数据库中数据的改变是持久的，即使数据库发生故障也不应该对其有任何影响；
4. **一致性（Consistency）**：执行事务前后，数据保持一致，多个事务对同一个数据读取的结果是相同的。

Redis 事务在运行错误的情况下，除了执行过程中出现错误的命令外，其他命令都能正常执行。并且，Redis 事务是不支持回滚（roll back）操作的。因此，Redis 事务其实是不满足原子性的。

Redis 官网也解释了自己为啥不支持回滚。简单来说就是 Redis 开发者们觉得没必要支持回滚，这样更简单便捷并且性能更好。Redis 开发者觉得即使命令执行错误也应该在开发过程中就被发现而不是生产过程中。

![Redis 为什么不支持回滚](images/redis-rollback-b66d7587.png)

**相关 issue**：

- [issue#452: 关于 Redis 事务不满足原子性的问题](https://github.com/Snailclimb/JavaGuide/issues/452)。
- [Issue#491:关于 Redis 没有事务回滚？](https://github.com/Snailclimb/JavaGuide/issues/491)。

#### Redis 事务支持持久性吗？

Redis 不同于 Memcached 的很重要一点就是，Redis 支持持久化，而且支持 3 种持久化方式：

- 快照（snapshotting，RDB）；
- 只追加文件（append-only file，AOF）；
- RDB 和 AOF 的混合持久化（Redis 4.0 新增）。

与 RDB 持久化相比，AOF 持久化的实时性更好。在 Redis 的配置文件中存在三种不同的 AOF 持久化方式（`fsync` 策略），它们分别是：

```bash
appendfsync always    #每次有数据修改发生时，主线程直接调用fsync同步AOF文件（刷盘），fsync完成后返回。always由主线程执行而非后台线程，严重降低Redis性能
appendfsync everysec  #每秒钟调用fsync函数同步一次AOF文件
appendfsync no        #让操作系统决定何时进行同步，一般为30秒一次
```

AOF 持久化的 `fsync` 策略为 no、everysec 时都会存在数据丢失的情况。always 下可以基本是可以满足持久性要求的，但性能太差，实际开发过程中不会使用。

因此，Redis 事务的持久性也是没办法保证的。

#### 如何解决 Redis 事务的缺陷？

Redis 从 2.6 版本开始支持执行 Lua 脚本，它的功能和事务非常类似。我们可以利用 Lua 脚本来批量执行多条 Redis 命令，这些 Redis 命令会被提交到 Redis 服务器一次性执行完成，大幅减小了网络开销。

一段 Lua 脚本可以视作一条命令执行，一段 Lua 脚本执行过程中不会有其他脚本或 Redis 命令同时执行，保证了操作不会被其他指令插入或打扰。

不过，如果 Lua 脚本运行时出错并中途结束，出错之后的命令是不会被执行的。并且，出错之前执行的命令是无法被撤销的，无法实现类似关系型数据库执行失败可以回滚的那种原子性效果。因此，**严格来说的话，通过 Lua 脚本来批量执行 Redis 命令实际也是不完全满足原子性的。**

如果想要让 Lua 脚本中的命令全部执行，必须保证语句语法和命令都是对的。

另外，Redis 7.0 新增了 [Redis functions](https://redis.io/docs/latest/develop/programmability/functions-intro/) 特性，你可以将 Redis functions 看作是比 Lua 更强大的脚本。

### 【⭐️Redis 性能优化（重要）】

#### 使用批量操作减少网络传输

一个 Redis 命令的执行可以简化为以下 4 步：

1. 发送命令；
2. 命令排队；
3. 命令执行；
4. 返回结果。

其中，第 1 步和第 4 步耗费时间之和称为 **Round Trip Time（RTT，往返时间）**，也就是数据在网络上传输的时间。

使用批量操作可以减少网络传输次数，进而有效减小网络开销，大幅减少 RTT。

另外，除了能减少 RTT 之外，发送一次命令的 socket I/O 成本也比较高（涉及上下文切换，存在 `read()` 和 `write()` 系统调用），批量操作还可以减少 socket I/O 成本。这个在官方对 pipeline 的介绍中有提到：。

#### 原生批量操作命令

Redis 中有一些原生支持批量操作的命令，比如：

- `MGET`（获取一个或多个指定 key 的值）、`MSET`（设置一个或多个指定 key 的值）、
- `HMGET`（获取指定哈希表中一个或者多个指定字段的值）、`HMSET`（同时将一个或多个 field-value 对设置到指定哈希表中）、
- `SADD`（向指定集合添加一个或多个元素）
- ……

不过，在 Redis 官方提供的分片集群解决方案 Redis Cluster 下，使用这些原生批量操作命令可能会存在一些小问题需要解决。就比如说 `MGET` 无法保证所有的 key 都在同一个 **hash slot（哈希槽）** 上，`MGET`可能还是需要多次网络传输，原子操作也无法保证了。不过，相较于非批量操作，还是可以节省不少网络传输次数。

整个步骤的简化版如下（通常由 Redis 客户端实现，无需我们自己再手动实现）：

1. 找到 key 对应的所有 hash slot；
2. 分别向对应的 Redis 节点发起 `MGET` 请求获取数据；
3. 等待所有请求执行结束，重新组装结果数据，保持跟入参 key 的顺序一致，然后返回结果。

如果想要解决这个多次网络传输的问题，比较常用的办法是自己维护 key 与 slot 的关系。不过这样不太灵活，虽然带来了性能提升，但同样让系统复杂性提升。

> Redis Cluster 并没有使用一致性哈希，采用的是 **哈希槽分区**，每一个键值对都属于一个 **hash slot（哈希槽）**。当客户端发送命令请求的时候，需要先根据 key 通过上面的计算公式找到的对应的哈希槽，然后再查询哈希槽和节点的映射关系，即可找到目标 Redis 节点。
>
> 我在 [Redis 集群详解（付费）](https://javaguide.cn/database/redis/redis-cluster.html) 这篇文章中详细介绍了 Redis Cluster 这部分的内容，感兴趣地可以看看。

#### pipeline

对于不支持批量操作的命令，我们可以利用 **pipeline（流水线）** 将一批 Redis 命令封装成一组，这些 Redis 命令会被一次性提交到 Redis 服务器，只需要一次网络传输。不过，需要注意控制一次批量操作的 **元素个数**（例如 500 以内，实际也和元素字节数有关），避免网络传输的数据量过大。

与 `MGET`、`MSET` 等原生批量操作命令一样，pipeline 同样在 Redis Cluster 上使用会存在一些小问题。原因类似，无法保证所有的 key 都在同一个 **hash slot（哈希槽）** 上。如果想要使用的话，客户端需要自己维护 key 与 slot 的关系。

原生批量操作命令和 pipeline 的是有区别的，使用的时候需要注意：

- 原生批量操作命令是原子操作，pipeline 是非原子操作。
- pipeline 可以打包不同的命令，原生批量操作命令不可以。
- 原生批量操作命令是 Redis 服务端支持实现的，而 pipeline 需要服务端和客户端的共同实现。

顺带补充一下 pipeline 和 Redis 事务的对比：

- 事务是原子操作，pipeline 是非原子操作。两个不同的事务不会同时运行，而 pipeline 可以同时以交错方式执行。
- Redis 事务中每个命令都需要发送到服务端，而 Pipeline 只需要发送一次，请求次数更少。

> 事务可以看作是一个原子操作，但其实并不满足原子性。当我们提到 Redis 中的原子操作时，主要指的是这个操作（比如事务、Lua 脚本）不会被其他操作（比如其他事务、Lua 脚本）打扰，并不能完全保证这个操作中的所有写命令要么都执行要么都不执行。这主要也是因为 Redis 是不支持回滚操作。

另外，pipeline 不适用于执行顺序有依赖关系的一批命令。就比如说，你需要将前一个命令的结果给后续的命令使用，pipeline 就没办法满足你的需求了。对于这种需求，我们可以使用 **Lua 脚本**。

#### Lua 脚本

Lua 脚本同样支持批量操作多条命令。一段 Lua 脚本可以视作一条命令执行，可以看作是 **原子操作**。也就是说，一段 Lua 脚本执行过程中不会有其他脚本或 Redis 命令同时执行，保证了操作不会被其他指令插入或打扰，这是 pipeline 所不具备的。

并且，Lua 脚本中支持一些简单的逻辑处理比如使用命令读取值并在 Lua 脚本中进行处理，这同样是 pipeline 所不具备的。

不过， Lua 脚本依然存在下面这些缺陷：

- 如果 Lua 脚本运行时出错并中途结束，之后的操作不会进行，但是之前已经发生的写操作不会撤销，所以即使使用了 Lua 脚本，也不能实现类似数据库回滚的原子性。
- Redis Cluster 下 Lua 脚本的原子操作也无法保证了，原因同样是无法保证所有的 key 都在同一个 **hash slot（哈希槽）** 上。

#### 大量 key 集中过期问题

我在前面提到过：对于过期 key，Redis 采用的是 **定期删除+惰性/懒汉式删除** 策略。

定期删除执行过程中，如果突然遇到大量过期 key 的话，客户端请求必须等待定期清理过期 key 任务线程执行完成，因为这个这个定期任务线程是在 Redis 主线程中执行的。这就导致客户端请求没办法被及时处理，响应速度会比较慢。

**如何解决呢？** 下面是两种常见的方法：

1. 给 key 设置随机过期时间。
2. 开启 lazy-free（惰性删除/延迟释放）。lazy-free 特性是 Redis 4.0 开始引入的，指的是让 Redis 采用异步方式延迟释放 key 使用的内存，将该操作交给单独的子线程处理，避免阻塞主线程。

个人建议不管是否开启 lazy-free，我们都尽量给 key 设置随机过期时间。

#### Redis bigkey（大 Key）

#### 什么是 bigkey？

简单来说，如果一个 key 对应的 value 所占用的内存比较大，那这个 key 就可以看作是 bigkey。具体多大才算大呢？有一个不是特别精确的参考标准：

- String 类型的 value 超过 1MB
- 复合类型（List、Hash、Set、Sorted Set 等）的 value 包含的元素超过 5000 个（不过，对于复合类型的 value 来说，不一定包含的元素越多，占用的内存就越多）。

![bigkey 判定标准](images/bigkey-criterion-e36d656b.png)

#### bigkey 是怎么产生的？有什么危害？

bigkey 通常是由于下面这些原因产生的：

- 程序设计不当，比如直接使用 String 类型存储较大的文件对应的二进制数据。
- 对于业务的数据规模考虑不周到，比如使用集合类型的时候没有考虑到数据量的快速增长。
- 未及时清理垃圾数据，比如哈希中冗余了大量的无用键值对。

bigkey 除了会消耗更多的内存空间和带宽，还会对性能造成比较大的影响。

在 [Redis 常见阻塞原因总结](https://github.com/Snailclimb/JavaGuide/blob/main/docs/redis-common-blocking-problems-summary.md) 这篇文章中我们提到：大 key 还会造成阻塞问题。具体来说，主要体现在下面三个方面：

1. 客户端超时阻塞：由于 Redis 执行命令是单线程处理，然后在操作大 key 时会比较耗时，那么就会阻塞 Redis，从客户端这一视角看，就是很久很久都没有响应。
2. 网络阻塞：每次获取大 key 产生的网络流量较大，如果一个 key 的大小是 1 MB，每秒访问量为 1000，那么每秒会产生 1000MB 的流量，这对于普通千兆网卡的服务器来说是灾难性的。
3. 工作线程阻塞：如果使用 del 删除大 key 时，会阻塞工作线程，这样就没办法处理后续的命令。

大 key 造成的阻塞问题还会进一步影响到主从同步和集群扩容。

综上，大 key 带来的潜在问题是非常多的，我们应该尽量避免 Redis 中存在 bigkey。

#### 如何发现 bigkey？

**1、使用 Redis 自带的 `--bigkeys` 参数来查找。**

```bash
# redis-cli -p 6379 --bigkeys

# Scanning the entire keyspace to find biggest keys as well as
# average sizes per key type.  You can use -i 0.1 to sleep 0.1 sec
# per 100 SCAN commands (not usually needed).

[00.00%] Biggest string found so far '"ballcat:oauth:refresh_auth:f6cdb384-9a9d-4f2f-af01-dc3f28057c20"' with 4437 bytes
[00.00%] Biggest list   found so far '"my-list"' with 17 items

-------- summary -------

Sampled 5 keys in the keyspace!
Total key length in bytes is 264 (avg len 52.80)

Biggest   list found '"my-list"' has 17 items
Biggest string found '"ballcat:oauth:refresh_auth:f6cdb384-9a9d-4f2f-af01-dc3f28057c20"' has 4437 bytes

1 lists with 17 items (20.00% of keys, avg size 17.00)
0 hashs with 0 fields (00.00% of keys, avg size 0.00)
4 strings with 4831 bytes (80.00% of keys, avg size 1207.75)
0 streams with 0 entries (00.00% of keys, avg size 0.00)
0 sets with 0 members (00.00% of keys, avg size 0.00)
0 zsets with 0 members (00.00% of keys, avg size 0.00
```

从这个命令的运行结果，我们可以看出：这个命令会扫描（Scan）Redis 中的所有 key，会对 Redis 的性能有一点影响。并且，这种方式只能找出每种数据结构 top 1 bigkey（占用内存最大的 String 数据类型，包含元素最多的复合数据类型）。然而，一个 key 的元素多并不代表占用内存也多，需要我们根据具体的业务情况来进一步判断。

在线上执行该命令时，为了降低对 Redis 的影响，需要指定 `-i` 参数控制扫描的频率。`redis-cli -p 6379 --bigkeys -i 3` 表示扫描过程中每次扫描后休息的时间间隔为 3 秒。

**2、使用 Redis 自带的 SCAN 命令**

`SCAN` 命令可以按照一定的模式和数量返回匹配的 key。获取了 key 之后，可以利用 `STRLEN`、`HLEN`、`LLEN` 等命令返回其长度或成员数量。

| 数据结构   | 命令   | 复杂度 | 结果（对应 key）   |
| ---------- | ------ | ------ | ------------------ |
| String     | STRLEN | O(1)   | 字符串值的长度     |
| Hash       | HLEN   | O(1)   | 哈希表中字段的数量 |
| List       | LLEN   | O(1)   | 列表元素数量       |
| Set        | SCARD  | O(1)   | 集合元素数量       |
| Sorted Set | ZCARD  | O(1)   | 有序集合的元素数量 |

对于集合类型还可以使用 `MEMORY USAGE` 命令（Redis 4.0+），这个命令会返回键值对占用的内存空间。

**3、借助开源工具分析 RDB 文件。**

通过分析 RDB 文件来找出 big key。这种方案的前提是你的 Redis 采用的是 RDB 持久化。

网上有现成的代码/工具可以直接拿来使用：

- [redis-rdb-tools](https://github.com/sripathikrishnan/redis-rdb-tools)：Python 语言写的用来分析 Redis 的 RDB 快照文件用的工具。
- [rdb_bigkeys](https://github.com/weiyanwei412/rdb_bigkeys)：Go 语言写的用来分析 Redis 的 RDB 快照文件用的工具，性能更好。

**4、借助公有云的 Redis 分析服务。**

如果你用的是公有云的 Redis 服务的话，可以看看其是否提供了 key 分析功能（一般都提供了）。

这里以阿里云 Redis 为例说明，它支持 bigkey 实时分析、发现，文档地址：。

![阿里云Key分析](images/aliyun-key-analysis-0a8d83ea.png)

#### 如何处理 bigkey？

bigkey 的常见处理以及优化办法如下（这些方法可以配合起来使用）：

- **分割 bigkey**：将一个 bigkey 分割为多个小 key。例如，将一个含有上万字段数量的 Hash 按照一定策略（比如二次哈希）拆分为多个 Hash。
- **手动清理**：Redis 4.0+ 可以使用 `UNLINK` 命令来异步删除一个或多个指定的 key。Redis 4.0 以下可以考虑使用 `SCAN` 命令结合 `DEL` 命令来分批次删除。
- **采用合适的数据结构**：例如，文件二进制数据不使用 String 保存、使用 HyperLogLog 统计页面 UV、Bitmap 保存状态信息（0/1）。
- **开启 lazy-free（惰性删除/延迟释放）**：lazy-free 特性是 Redis 4.0 开始引入的，指的是让 Redis 采用异步方式延迟释放 key 使用的内存，将该操作交给单独的子线程处理，避免阻塞主线程。

#### Redis hotkey（热 Key）

#### 什么是 hotkey？

如果一个 key 的访问次数比较多且明显多于其他 key 的话，那这个 key 就可以看作是 **hotkey（热 Key）**。例如在 Redis 实例的每秒处理请求达到 5000 次，而其中某个 key 的每秒访问量就高达 2000 次，那这个 key 就可以看作是 hotkey。

hotkey 出现的原因主要是某个热点数据访问量暴增，如重大的热搜事件、参与秒杀的商品。

#### hotkey 有什么危害？

处理 hotkey 会占用大量的 CPU 和带宽，影响同一实例上其他请求的延迟。超过处理能力时，通常先表现为请求排队、超时和吞吐下降，并不意味着 Redis 一定会直接宕机。如果应用在超时后无节制地重试或回源，还可能把压力传递给数据库。

排查时不能只看访问次数：高频执行复杂命令更容易耗尽 CPU，频繁读取大 value 则可能先打满带宽。还要区分**读热点与写热点**，本地缓存主要能分担读请求，不能直接解决集中写入同一个 key 的问题。

因此，hotkey 很可能成为系统性能的瓶颈点，需要单独对其进行优化，以确保系统的高可用性和稳定性。

#### 如何发现 hotkey？

**1、使用 Redis 自带的 `--hotkeys` 参数来查找。**

`redis-cli --hotkeys` 通过 `SCAN` 遍历 key，并读取 `OBJECT FREQ` 来寻找频率值较高的候选 key。**返回的 counter 是 LFU 的近似频率值，不是实际访问次数，也不能直接换算成 QPS。**

使用该方案的前提条件是 Redis Server 的 `maxmemory-policy` 设置为 `allkeys-lfu` 或 `volatile-lfu`，否则会出现如下错误：

```bash
# redis-cli -p 6379 --hotkeys

# Scanning the entire keyspace to find hot keys as well as
# average sizes per key type.  You can use -i 0.1 to sleep 0.1 sec
# per 100 SCAN commands (not usually needed).

Error: ERR An LFU maxmemory policy is not selected, access frequency not tracked. Please note that when switching between policies at runtime LRU and LFU data will take some time to adjust.
```

Redis 中有两种基于 LFU 的淘汰策略：

1. **volatile-lfu（least frequently used）**：从已设置过期时间的数据集（`server.db[i].expires`）中挑选最不经常使用的数据淘汰。
2. **allkeys-lfu（least frequently used）**：当内存不足以容纳新写入数据时，在键空间中，移除最不经常使用的 key。

不要仅为了排查热点就直接修改生产实例的淘汰策略，这会改变内存达到上限时的行为。如果实例已经使用 LFU，可以限制扫描节奏：

```bash
redis-cli -h 127.0.0.1 -p 6379 --hotkeys -i 0.1
```

LFU 计数采用概率递增，并按配置随时间衰减，适合比较近期访问热度。扫描也需要时间和额外请求，不是某个瞬间的完整流量快照，可能错过短暂热点。集群排查还要明确节点范围；从节点上的统计不能直接代表主节点的读流量。机制说明见 [OBJECT FREQ](https://redis.io/docs/latest/commands/object-freq/)、[LFU 淘汰策略](https://redis.io/docs/latest/develop/reference/eviction/#lfu-eviction) 和 [Redis CLI 文档](https://redis.io/docs/latest/develop/tools/cli/)。

**2、使用 `MONITOR` 命令。**

`MONITOR` 可以实时输出服务器处理的命令，用于短时采集并按 key 统计；它不是完整的审计日志，部分命令不会被记录。

由于该命令对 Redis 性能的影响比较大，因此禁止长时间开启 `MONITOR`（生产环境中建议谨慎使用该命令）。

```bash
# redis-cli
127.0.0.1:6379> MONITOR
OK
1683638260.637378 [0 172.17.0.1:61516] "ping"
1683638267.144236 [0 172.17.0.1:61518] "smembers" "mySet"
1683638268.941863 [0 172.17.0.1:61518] "smembers" "mySet"
1683638269.551671 [0 172.17.0.1:61518] "smembers" "mySet"
1683638270.646256 [0 172.17.0.1:61516] "ping"
1683638270.849551 [0 172.17.0.1:61518] "smembers" "mySet"
1683638271.926945 [0 172.17.0.1:61518] "smembers" "mySet"
1683638274.276599 [0 172.17.0.1:61518] "smembers" "mySet2"
1683638276.327234 [0 172.17.0.1:61518] "smembers" "mySet"
```

需要短时诊断时，可以限定采集时长和文件大小，结束采集后再离线统计。它只能看到开启期间的请求，无法还原此前已经消失的热点；输出还可能包含业务参数，应控制访问权限。性能影响可参考 [MONITOR 官方说明](https://redis.io/docs/latest/commands/monitor/)。

**3、借助开源项目。**

京东零售的 [hotkey](https://gitee.com/jd-platform-opensource/hotkey) 这个项目不光支持 hotkey 的发现，还支持 hotkey 的处理。

![京东零售开源的 hotkey](images/jd-hotkey-76fb6236.png)

**4、根据业务情况提前预估。**

可以根据业务情况来预估一些 hotkey，比如参与秒杀活动的商品数据等。不过，我们无法预估所有 hotkey 的出现，比如突发的热点新闻事件等。

**5、在客户端或代理层采集。**

可以在统一 SDK 或 Proxy 中按时间窗口记录 key 的读写次数，再汇总多个实例的数据。单个实例只能看到自身流量；如果要得到全局热点，需要统一统计口径和窗口，并注意本地缓存命中后的业务访问量不等于 Redis 收到的请求量。

这种方式适合持续观测，但需要维护采集与聚合逻辑。可以用采样、有界计数结构控制开销，不要无上限保存每个 key 的统计，也不要把所有原始 key 都作为监控指标标签。

**6、借助公有云的 Redis 分析服务。**

如果你用的是公有云的 Redis 服务的话，可以看看其是否提供了 key 分析功能（一般都提供了）。

这里以阿里云 Redis 为例说明，它支持 hotkey 实时分析、发现，文档地址：。

![阿里云Key分析](images/aliyun-key-analysis-0a8d83ea.png)

**7、在服务端统计热点。**

服务端能集中观察到达该节点的请求。需要定制统计能力时，可以使用容量受限的记录结构统计一个时间窗口内的访问，分别记录读写热点，并提供查询与通知接口。这类扩展需要维护服务端代码，还要评估与 Redis 版本升级的兼容性。

有界统计结构可以控制内存占用，但记录被淘汰或采样时，结果就未必覆盖全部访问。评估方案时应明确统计窗口、采样率、记录容量、通知开销和漏报情况，不能把“单次统计很快”等同于“整体没有成本”。

**版本补充：Redis Open Source 8.6.0 起提供原生 `HOTKEYS` 命令族。** 它在指定观测时段内按 CPU 时间或网络字节识别热点，与依赖 LFU 的 `redis-cli --hotkeys` 统计口径不同。例如，在支持该命令且具有相应权限的实例上，可以执行：

```bash
# 采集 30 秒，按 CPU 和网络流量分别保留 Top 10；SAMPLE 10 表示按 1/10 概率采样
redis-cli HOTKEYS START METRICS 2 CPU NET COUNT 10 DURATION 30 SAMPLE 10
# 采集期间或结束后查看结果
redis-cli HOTKEYS GET
```

采样会影响精度；结果也只对应指定的观测范围，不能用来查询从未采集过的历史热点。参数与返回值见 [HOTKEYS START](https://redis.io/docs/latest/commands/hotkeys-start/) 和 [HOTKEYS GET](https://redis.io/docs/latest/commands/hotkeys-get/)。

选择探测方案时，可以先用已有监控确定高负载节点及异常时间段，再用适合当前版本的热点工具缩小范围。网络抓包也能辅助分析明文 RESP 流量，但需要处理协议解析、采集开销和 TLS 加密等限制，通常不作为首选的持续监控方式。

#### 如何解决 hotkey？

hotkey 的常见处理以及优化办法如下（这些方法可以配合起来使用）：

- **读热点优先分担读请求**：将稳定、读多写少的数据放入 JVM 本地缓存（如 Caffeine）或代理缓存，并设置容量上限、TTL 和失效机制；缓存失效时合并并发回源请求。
- **读写分离**：客户端将可接受旧数据的读请求路由到从节点，但要考虑异步复制延迟；增加从节点不能分摊对同一个 key 的写入。
- **区分多个热点与单个热点**：Redis Cluster 可以把不同 key 分散到不同分片，但一个 key 仍只对应一个槽，正常服务时由一个主节点负责。仅增加分片不能拆散这个 key 的负载。可结合 [Cluster 规范](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/) 理解槽与节点的关系。
- **按业务语义拆分写热点**：例如允许延迟汇总的计数可以拆为多个子计数再聚合，但必须重新评估读取成本、原子性和一致性。库存扣减等需要统一约束的操作，不能直接套用计数分片。
- **控制过载传播**：结合限流、降级、请求合并和有限重试，避免 Redis 超时后所有请求同时冲向数据库。

如果为读热点创建多份不同 key 的数据副本，还需要保证它们实际分布到不同分片，并处理所有副本的更新或失效。给副本使用相同的 hash tag 会让它们落在同一个槽，无法分散分片负载。多级缓存的通知与一致性边界可继续阅读 [缓存基础](https://github.com/Snailclimb/JavaGuide/blob/main/docs/cache-basics.md)。

除了这些方法之外，如果你使用的公有云的 Redis 服务话，还可以留意其提供的开箱即用的解决方案。

这里以阿里云 Redis 为例说明，它支持通过代理查询缓存功能（Proxy Query Cache）优化热点 Key 问题。

![通过阿里云的Proxy Query Cache优化热点Key问题](images/aliyun-hotkey-proxy-query-cache-5a9f16f3.png)

#### 慢查询命令

#### 为什么会有慢查询命令？

我们知道一个 Redis 命令的执行可以简化为以下 4 步：

1. 发送命令；
2. 命令排队；
3. 命令执行；
4. 返回结果。

Redis 慢查询统计的是命令执行这一步骤的耗时，慢查询命令也就是那些命令执行时间较长的命令。

Redis 为什么会有慢查询命令呢？

Redis 中的大部分命令都是 O(1) 时间复杂度，但也有少部分 O(n) 时间复杂度的命令，例如：

- `KEYS *`：会返回所有符合规则的 key。
- `HGETALL`：会返回一个 Hash 中所有的键值对。
- `LRANGE`：会返回 List 中指定范围内的元素。
- `SMEMBERS`：返回 Set 中的所有元素。
- `SINTER`/`SUNION`/`SDIFF`：计算多个 Set 的交集/并集/差集。
- ……

由于这些命令时间复杂度是 O(n)，有时候也会全表扫描，随着 n 的增大，执行耗时也会越长。不过， 这些命令并不是一定不能使用，但是需要明确 N 的值。另外，有遍历的需求可以使用 `HSCAN`、`SSCAN`、`ZSCAN` 代替。

除了这些 O(n) 时间复杂度的命令可能会导致慢查询之外，还有一些时间复杂度可能在 O(N) 以上的命令，例如：

- `ZRANGE`/`ZREVRANGE`：返回指定 Sorted Set 中指定排名范围内的所有元素。时间复杂度为 O(log(n)+m)，n 为所有元素的数量，m 为返回的元素数量，当 m 和 n 相当大时，O(n) 的时间复杂度更小。
- `ZREMRANGEBYRANK`/`ZREMRANGEBYSCORE`：移除 Sorted Set 中指定排名范围/指定 score 范围内的所有元素。时间复杂度为 O(log(n)+m)，n 为所有元素的数量，m 被删除元素的数量，当 m 和 n 相当大时，O(n) 的时间复杂度更小。
- ……

#### 如何找到慢查询命令？

Redis 提供了一个内置的**慢查询日志 (Slow Log)** 功能，专门用来记录执行时间超过指定阈值的命令。这对于排查性能瓶颈、找出导致 Redis 阻塞的“慢”操作非常有帮助，原理和 MySQL 的慢查询日志类似。

在 `redis.conf` 文件中，我们可以使用 `slowlog-log-slower-than` 参数设置耗时命令的阈值，并使用 `slowlog-max-len` 参数设置耗时命令的最大记录条数。

当 Redis 服务器检测到执行时间超过 `slowlog-log-slower-than` 阈值的命令时，就会将该命令记录在慢查询日志（slow log）中，这点和 MySQL 记录慢查询语句类似。当慢查询日志超过设定的最大记录条数之后，Redis 会把最早的执行命令依次舍弃。

⚠️ 注意：由于慢查询日志会占用一定内存空间，如果设置最大记录条数过大，可能会导致内存占用过高的问题。

`slowlog-log-slower-than` 和 `slowlog-max-len` 的默认配置如下（可以自行修改）：

```properties
# The following time is expressed in microseconds, so 1000000 is equivalent
# to one second. Note that a negative number disables the slow log, while
# a value of zero forces the logging of every command.
slowlog-log-slower-than 10000

# There is no limit to this length. Just be aware that it will consume memory.
# You can reclaim memory used by the slow log with SLOWLOG RESET.
slowlog-max-len 128
```

除了修改配置文件之外，你也可以直接通过 `CONFIG` 命令直接设置：

```bash
# 命令执行耗时超过 10000 微妙（即10毫秒）就会被记录
CONFIG SET slowlog-log-slower-than 10000
# 只保留最近 128 条耗时命令
CONFIG SET slowlog-max-len 128
```

获取慢查询日志的内容很简单，直接使用 `SLOWLOG GET` 命令即可。

```bash
127.0.0.1:6379> SLOWLOG GET #慢日志查询
 1) 1) (integer) 5
   2) (integer) 1684326682
   3) (integer) 12000
   4) 1) "KEYS"
      2) "*"
   5) "172.17.0.1:61152"
   6) ""
  // ...
```

慢查询日志中的每个条目都由以下六个值组成：

1. **唯一 ID**: 日志条目的唯一标识符。
2. **时间戳 (Timestamp)**: 命令执行完成时的 Unix 时间戳。
3. **耗时 (Duration)**: 命令执行所花费的时间，单位是**微秒**。
4. **命令及参数 (Command)**: 执行的具体命令及其参数数组。
5. **客户端信息 (Client IP:Port)**: 执行命令的客户端地址和端口。
6. **客户端名称 (Client Name)**: 如果客户端设置了名称 (CLIENT SETNAME)。

`SLOWLOG GET` 命令默认返回最近 10 条的慢查询命令，你也自己可以指定返回的慢查询命令的数量 `SLOWLOG GET N`。

下面是其他比较常用的慢查询相关的命令：

```bash
# 返回慢查询命令的数量
127.0.0.1:6379> SLOWLOG LEN
(integer) 128
# 清空慢查询命令
127.0.0.1:6379> SLOWLOG RESET
OK
```

#### Redis 内存碎片

**相关问题**：

1. 什么是内存碎片？为什么会有 Redis 内存碎片？
2. 如何清理 Redis 内存碎片？

**参考答案**：[Redis 内存碎片详解](https://javaguide.cn/database/redis/redis-memory-fragmentation.html)。

### 【⭐️Redis 生产问题（重要）】

#### 缓存穿透

#### 什么是缓存穿透？

缓存穿透说简单点就是大量请求的 key 是不合理的，**根本不存在于缓存中，也不存在于数据库中**。这就导致这些请求直接到了数据库上，根本没有经过缓存这一层，对数据库造成了巨大的压力，可能直接就被这么多请求弄宕机了。

![缓存穿透](images/redis-cache-penetration-c8f04a78.png)

举个例子：某个黑客故意制造一些非法的 key 发起大量请求，导致大量请求落到数据库，结果数据库上也没有查到对应的数据。也就是说这些请求最终都落到了数据库上，对数据库造成了巨大的压力。

#### 有哪些解决办法？

最基本的就是首先做好参数校验，一些不合法的参数请求直接抛出异常信息返回给客户端。比如查询的数据库 id 不能小于 0、传入的邮箱格式不对的时候直接返回错误消息给客户端等等。

**1）缓存无效 key**

如果缓存和数据库都查不到某个 key 的数据，就写一个到 Redis 中去并设置过期时间，具体命令如下：`SET key value EX 10086`。这种方式可以解决请求的 key 变化不频繁的情况，如果黑客恶意攻击，每次构建不同的请求 key，会导致 Redis 中缓存大量无效的 key。很明显，这种方案并不能从根本上解决此问题。如果非要用这种方式来解决穿透问题的话，尽量将无效的 key 的过期时间设置短一点，比如 1 分钟。

另外，这里多说一嘴，一般情况下我们是这样设计 key 的：`表名:列名:主键名:主键值`。

如果用 Java 代码展示的话，差不多是下面这样的：

```java
public Object getObjectInclNullById(Integer id) {
    // 从缓存中获取数据
    Object cacheValue = cache.get(id);
    // 缓存为空
    if (cacheValue == null) {
        // 从数据库中获取
        Object storageValue = storage.get(key);
        // 缓存空对象
        cache.set(key, storageValue);
        // 如果存储数据为空，需要设置一个过期时间(300秒)
        if (storageValue == null) {
            // 必须设置过期时间，否则有被攻击的风险
            cache.expire(key, 60 * 5);
        }
        return storageValue;
    }
    return cacheValue;
}
```

**2）布隆过滤器**

布隆过滤器是一个非常神奇的数据结构，通过它我们可以非常方便地判断一个给定数据是否存在于海量数据中。我们可以把它看作由二进制向量（或者说位数组）和一系列随机映射函数（哈希函数）两部分组成的数据结构。相比于我们平时常用的 List、Map、Set 等数据结构，它占用空间更少并且效率更高，但是缺点是其返回的结果是概率性的，而不是非常准确的。理论情况下添加到集合中的元素越多，误报的可能性就越大。并且，存放在布隆过滤器的数据不容易删除。

![Bloom Filter 的简单原理示意图](images/bloom-filter-simple-schematic-diagram-ecf8f3d1.png)

Bloom Filter 会使用一个较大的 bit 数组来保存所有的数据，数组中的每个元素都只占用 1 bit ，并且每个元素只能是 0 或者 1（代表 false 或者 true），这也是 Bloom Filter 节省内存的核心所在。这样来算的话，申请一个 100w 个元素的位数组只占用 1000000Bit / 8 = 125000 Byte = 125000/1024 KB ≈ 122KB 的空间。

![位数组](images/bloom-filter-bit-table-b8f56b57.png)

具体是这样做的：把所有可能存在的请求的值都存放在布隆过滤器中，当用户请求过来，先判断用户发来的请求的值是否存在于布隆过滤器中。不存在的话，直接返回请求参数错误信息给客户端，存在的话才会走下面的流程。

加入布隆过滤器之后的缓存处理流程图如下：

![加入布隆过滤器之后的缓存处理流程图](images/redis-cache-penetration-bloom-filter-878a8a50.png)

更多关于布隆过滤器的详细介绍可以看看我的这篇原创：[不了解布隆过滤器？一文给你整的明明白白！](https://javaguide.cn/cs-basics/data-structure/bloom-filter.html)，强烈推荐。

**3）接口限流**

根据用户或者 IP 对接口进行限流，对于异常频繁的访问行为，还可以采取黑名单机制，例如将异常 IP 列入黑名单。

后面提到的缓存击穿和雪崩都可以配合接口限流来解决，毕竟这些问题的关键都是有很多请求落到了数据库上造成数据库压力过大。

限流的具体方案可以参考这篇文章：[服务限流详解](https://javaguide.cn/high-availability/limit-request.html)。

#### 缓存击穿

#### 什么是缓存击穿？

缓存击穿中，请求的 key 对应的是 **热点数据**，该数据 **存在于数据库中，但不存在于缓存中（通常是因为缓存中的那份数据已经过期）**。这就可能会导致瞬时大量的请求直接打到了数据库上，对数据库造成了巨大的压力，可能直接就被这么多请求弄宕机了。

![缓存击穿](images/redis-cache-breakdown-1a847904.png)

举个例子：秒杀进行过程中，缓存中的某个秒杀商品的数据突然过期，这就导致瞬时大量对该商品的请求直接落到数据库上，对数据库造成了巨大的压力。

#### 有哪些解决办法？

1. **永不过期**（不推荐）：设置热点数据永不过期或者过期时间比较长。
2. **提前预热**（推荐）：针对热点数据提前预热，将其存入缓存中并设置合理的过期时间比如秒杀场景下的数据在秒杀结束之前不过期。
3. **加锁**（看情况）：在缓存失效后，通过设置互斥锁确保只有一个请求去查询数据库并更新缓存。

#### 缓存穿透和缓存击穿有什么区别？

缓存穿透中，请求的 key 既不存在于缓存中，也不存在于数据库中。

缓存击穿中，请求的 key 对应的是 **热点数据** ，该数据 **存在于数据库中，但不存在于缓存中（通常是因为缓存中的那份数据已经过期）** 。

#### 缓存雪崩

#### 什么是缓存雪崩？

我发现缓存雪崩这名字起的有点意思，哈哈。

实际上，缓存雪崩描述的就是这样一个简单的场景：**缓存在同一时间大面积的失效，导致大量的请求都直接落到了数据库上，对数据库造成了巨大的压力。** 这就好比雪崩一样，摧枯拉朽之势，数据库的压力可想而知，可能直接就被这么多请求弄宕机了。

另外，缓存服务宕机也会导致缓存雪崩现象，导致所有的请求都落到了数据库上。

![缓存雪崩](images/redis-cache-avalanche-2585e3bd.png)

举个例子：缓存中的大量数据在同一时间过期，这个时候突然有大量的请求需要访问这些过期的数据。这就导致大量的请求直接落到数据库上，对数据库造成了巨大的压力。

#### 有哪些解决办法？

**针对 Redis 服务不可用的情况**：

1. **Redis 集群**：采用 Redis 集群，避免单机出现问题整个缓存服务都没办法使用。Redis Cluster 和 Redis Sentinel 是两种最常用的 Redis 集群实现方案，详细介绍可以参考：[Redis 集群详解(付费)](https://javaguide.cn/database/redis/redis-cluster.html)。
2. **多级缓存**：设置多级缓存，例如本地缓存+Redis 缓存的二级缓存组合，当 Redis 缓存出现问题时，还可以从本地缓存中获取到部分数据。

**针对大量缓存同时失效的情况**：

1. **设置随机失效时间**（可选）：为缓存设置随机的失效时间，例如在固定过期时间的基础上加上一个随机值，这样可以避免大量缓存同时到期，从而减少缓存雪崩的风险。
2. **提前预热**（推荐）：针对热点数据提前预热，将其存入缓存中并设置合理的过期时间，比如秒杀场景下的数据在秒杀结束之前不过期。
3. **持久缓存策略**（看情况）：虽然一般不推荐设置缓存永不过期，但对于某些关键性和变化不频繁的数据，可以考虑这种策略。

#### 缓存预热如何实现？

常见的缓存预热方式有两种：

1. 使用定时任务，比如 xxl-job，来定时触发缓存预热的逻辑，将数据库中的热点数据查询出来并存入缓存中。
2. 使用消息队列，比如 Kafka，来异步地进行缓存预热，将数据库中的热点数据的主键或者 ID 发送到消息队列中，然后由缓存服务消费消息队列中的数据，根据主键或者 ID 查询数据库并更新缓存。

#### 缓存雪崩和缓存击穿有什么区别？

缓存雪崩和缓存击穿比较像，但缓存雪崩导致的原因是缓存中的大量或者所有数据失效，缓存击穿导致的原因主要是某个热点数据不存在于缓存中（通常是因为缓存中的那份数据已经过期）。

#### 如何保证缓存和数据库数据的一致性？

缓存和数据库一致性是个挺常见的技术挑战。引入缓存主要是为了提升性能、减轻数据库压力，但确实会带来数据不一致的风险。绝对的一致性往往意味着更高的系统复杂度和性能开销，所以实践中我们通常会根据业务场景选择合适的策略，在性能和一致性之间找到一个平衡点。

下面单独对 **Cache Aside Pattern（旁路缓存模式）** 来聊聊。这是非常常用的一种缓存读写策略，它的读写逻辑是这样的：

- **读操作**：
  1. 先尝试从缓存读取数据。
  2. 如果缓存命中，直接返回数据。
  3. 如果缓存未命中，从数据库查询数据，将查到的数据放入缓存并返回数据。
- **写操作**：
  1. 先更新数据库并提交事务。
  2. 提交成功后，再删除缓存中对应的数据。

图解如下：

这个顺序仍需处理以下问题：

- **删除失败**：通过可恢复的任务重试失效操作；如果用 MQ，需要考虑“DB 已提交、消息尚未发出”时宕机的缺口，必要时使用事务消息表或 CDC 衔接，并监控补偿任务。
- **旧值回填**：读请求可能在更新前读到旧值，却在删除完成后才回填。延迟双删只能降低部分风险，不能保证覆盖任意长的延迟；读从库、长事务快照也可能带来旧数据。
- **过期兜底**：设置符合业务容忍度的 TTL，但过期后的回源必须能够得到足够新的数据；TTL 本身不能提供强一致性。
- **读端能力与多级副本**：删除缓存要求未命中后有回源或明确的降级方案。若还有 JVM 本地缓存，需要另外处理各实例的失效通知。

各类并发时序、事务提交和重试边界见 [3 种常用的缓存读写策略详解](https://github.com/Snailclimb/JavaGuide/blob/main/docs/3-commonly-used-cache-read-and-write-strategies.md)，多级缓存的回源与通知问题见 [缓存基础](https://github.com/Snailclimb/JavaGuide/blob/main/docs/cache-basics.md)。

相关文章推荐：[缓存和数据库一致性问题，看这篇就够了 - 水滴与银弹](https://mp.weixin.qq.com/s?__biz=MzIyOTYxNDI5OA==&mid=2247487312&idx=1&sn=fa19566f5729d6598155b5c676eee62d&chksm=e8beb8e5dfc931f3e35655da9da0b61c79f2843101c130cf38996446975014f958a6481aacf1&scene=178&cur_album_id=1699766580538032128#rd)。

#### 哪些情况可能会导致 Redis 阻塞？

常见的导致 Redis 阻塞原因有：

- `O(n)` 复杂度命令执行（如 `KEYS *`、`HGETALL`、`LRANGE`、`SMEMBERS` 等），随着数据量增大导致执行时间过长。
- 执行 `SAVE` 命令生成 RDB 快照时同步阻塞主线程，而 `BGSAVE` 通过 `fork` 子进程避免阻塞。
- AOF 记录日志在主线程中进行，可能因命令执行后写日志而阻塞后续命令。
- AOF 刷盘（fsync）时后台线程同步到磁盘，磁盘压力大导致 `fsync` 阻塞，进而阻塞主线程 `write` 操作，尤其在 `appendfsync always` 或 `everysec` 配置下明显。
- AOF 重写过程中将重写缓冲区内容追加到新 AOF 文件时产生阻塞。
- 操作大 key（string > 1MB 或复合类型元素 > 5000）导致客户端超时、网络阻塞和工作线程阻塞。
- 使用 `flushdb` 或 `flushall` 清空数据库时涉及大量键值对删除和内存释放，造成主线程阻塞。
- 集群扩容缩容时数据迁移为同步操作，大 key 迁移导致两端节点长时间阻塞，可能触发故障转移
- 内存不足触发 Swap，操作系统将 Redis 内存换出到硬盘，读写性能急剧下降。
- 其他进程过度占用 CPU 导致 Redis 吞吐量下降。
- 网络问题如连接拒绝、延迟高、网卡软中断等导致 Redis 阻塞。

详细介绍可以阅读这篇文章：[Redis 常见阻塞原因总结](https://javaguide.cn/database/redis/redis-common-blocking-problems-summary.html)。

### 【Redis 集群】

#### Redis 集群

**Redis Sentinel**：

1. 什么是 Sentinel？ 有什么用？
2. Sentinel 如何检测节点是否下线？主观下线与客观下线的区别？
3. Sentinel 是如何实现故障转移的？
4. 为什么建议部署多个 sentinel 节点（哨兵集群）？
5. Sentinel 如何选择出新的 master（选举机制）？
6. 如何从 Sentinel 集群中选择出 Leader？
7. Sentinel 可以防止脑裂吗？

**Redis Cluster**：

1. 为什么需要 Redis Cluster？解决了什么问题？有什么优势？
2. Redis Cluster 是如何分片的？
3. 为什么 Redis Cluster 的哈希槽是 16384 个？
4. 如何确定给定 key 的应该分布到哪个哈希槽中？
5. Redis Cluster 支持重新分配哈希槽吗？
6. Redis Cluster 扩容缩容期间可以提供服务吗？
7. Redis Cluster 中的节点是怎么进行通信的？

**参考答案**：[Redis 集群详解（付费）](https://javaguide.cn/database/redis/redis-cluster.html)。

### 【Redis 使用规范】

#### Redis 使用规范

实际使用 Redis 的过程中，我们尽量要准守一些常见的规范，比如：

1. 使用连接池：避免频繁创建关闭客户端连接。
2. 尽量不使用 O(n) 指令，使用 O(n) 命令时要关注 n 的数量：像 `KEYS *`、`HGETALL`、`LRANGE`、`SMEMBERS`、`SINTER`/`SUNION`/`SDIFF` 等 O(n) 命令并非不能使用，但是需要明确 n 的值。另外，有遍历的需求可以使用 `HSCAN`、`SSCAN`、`ZSCAN` 代替。
3. 使用批量操作减少网络传输：原生批量操作命令（比如 `MGET`、`MSET` 等等）、pipeline、Lua 脚本。
4. 尽量不使用 Redis 事务：Redis 事务实现的功能比较鸡肋，可以使用 Lua 脚本代替。
5. 禁止长时间开启 monitor：对性能影响比较大。
6. 控制 key 的生命周期：避免 Redis 中存放了太多不经常被访问的数据。
7. ……

#### 参考

- 《Redis 开发与运维》
- 《Redis 设计与实现》
- Redis Transactions：
- What is Redis Pipeline：
- 一文详解 Redis 中 BigKey、HotKey 的发现与处理：
- Bigkey 问题的解决思路与方式探索：
- Redis 延迟问题全面排障指南：

<!-- @include: @article-footer.snippet.md -->

## MySQL 与索引

> 索引原理、事务与 MVCC、锁、优化——会话与知识库的落库基础（55 题）

### 【MySQL 基础】

#### 什么是关系型数据库？

顾名思义，关系型数据库（RDB，Relational Database）就是一种建立在关系模型的基础上的数据库。关系模型表明了数据库中所存储的数据之间的联系（一对一、一对多、多对多）。

关系型数据库中，我们的数据都被存放在了各种表中（比如用户表），表中的每一行就存放着一条数据（比如一个用户的信息）。

![关系型数据库表关系](images/5e3c1a71724a38245aa43b02_99bf70d46cc247be878de9d3a88f0c44-25cda5c4.png)

大部分关系型数据库都使用 SQL 来操作数据库中的数据。并且，大部分关系型数据库都支持事务的四大特性(ACID)。

**有哪些常见的关系型数据库呢？**

MySQL、PostgreSQL、Oracle、SQL Server、SQLite（微信本地的聊天记录的存储就是用的 SQLite） ……。

#### 什么是 SQL？

SQL 是一种结构化查询语言(Structured Query Language)，专门用来与数据库打交道，目的是提供一种从数据库中读写数据的简单有效的方法。

几乎所有的主流关系数据库都支持 SQL ，适用性非常强。并且，一些非关系型数据库也兼容 SQL 或者使用的是类似于 SQL 的查询语言。

SQL 可以帮助我们：

- 新建数据库、数据表、字段；
- 在数据库中增加，删除，修改，查询数据；
- 新建视图、函数、存储过程；
- 对数据库中的数据进行简单的数据分析；
- 搭配 Hive，Spark SQL 做大数据；
- 搭配 SQLFlow 做机器学习；
- ……

#### 什么是 MySQL？

**MySQL 是一种关系型数据库，主要用于持久化存储我们的系统中的一些数据比如用户信息。**

由于 MySQL 是开源免费并且比较成熟的数据库，因此，MySQL 被大量使用在各种系统中。任何人都可以在 GPL(General Public License) 的许可下下载并根据个性化的需要对其进行修改。MySQL 的默认端口号是**3306**。

#### ⭐️MySQL 有什么优点？

这个问题本质上是在问 MySQL 如此流行的原因。

MySQL 成功可以归功于在**生态、功能和运维**这三个层面上的综合优势。

**第一，从生态和成本角度看，它的护城河非常深。**

- **开源免费：** 这是它得以广泛普及的基石。任何公司和个人都可以免费使用，极大地降低了技术门槛和初期成本。
- **社区庞大，生态完善：** 经过几十年的发展，MySQL 拥有极其活跃的社区和丰富的生态系统。这意味着无论你遇到什么问题，几乎都能在网上找到解决方案；同时，市面上所有的主流编程语言、框架、ORM 工具、监控系统都对 MySQL 有完美的支持。它的文档也非常丰富，学习资源唾手可得。

**第二，从核心技术功能上看，它非常强大且均衡。**

- **强大的事务支持：** 这是它作为关系型数据库的立身之本。值得一提的是，InnoDB 默认的可重复读（REPEATABLE-READ）隔离级别，通过 MVCC 和 Next-Key Lock 机制，很大程度上避免了幻读问题，这在很多其他数据库中都需要更高的隔离级别才能做到，兼顾了性能和一致性。详细介绍可以阅读笔者写的这篇文章：[MySQL 事务隔离级别详解](https://javaguide.cn/database/mysql/transaction-isolation-level.html)。
- **优秀的性能和可扩展性：** MySQL 本身经过了海量互联网业务的严酷考验，单机性能非常出色。更重要的是，它围绕着水平扩展，形成了一套非常成熟的架构方案，比如主从复制、读写分离、以及通过中间件实现的分库分表。这让它能够支撑从初创公司到大型互联网平台的各种规模的业务。

**第三，从运维和使用角度看，它非常‘亲民’。**

- **开箱即用，上手简单：** 相比于 Oracle 等大型商业数据库，MySQL 的安装、配置和日常使用都非常简单直观，学习曲线平缓，对于开发者和初级 DBA 非常友好。
- **维护成本低：** 由于其简单性和庞大的社区，找到相关的运维人才和解决方案都相对容易，整体的维护成本也更低。

值得一提的是最近几年，PostgreSQL 的势头很猛，甚至压过了 MySQL。网上出现了很多抨击诋毁 MySQL 的文章，笔者认为任何无脑抨击其中一方或者吹捧另外一方的行为都是不可取的。

笔者也写过一篇文章分享对这两个关系型数据库代表的看法，感兴趣的可以看看：[MySQL 被干成老二了？](https://mp.weixin.qq.com/s/APWD-PzTcTqGUuibAw7GGw)。

### 【MySQL 字段类型】

#### ⭐️整数类型的 UNSIGNED 属性有什么用？

MySQL 中的整数类型可以使用可选的 UNSIGNED 属性来表示不允许负值的无符号整数。使用 UNSIGNED 属性可以将正整数的上限提高一倍，因为它不需要存储负数值。

例如， TINYINT UNSIGNED 类型的取值范围是 0 ~ 255，而普通的 TINYINT 类型的值范围是 -128 ~ 127。INT UNSIGNED 类型的取值范围是 0 ~ 4,294,967,295，而普通的 INT 类型的值范围是 -2,147,483,648 ~ 2,147,483,647。

对于从 0 开始递增的 ID 列，使用 UNSIGNED 属性可以非常适合，因为不允许负值并且可以拥有更大的上限范围，提供了更多的 ID 值可用。

#### CHAR 和 VARCHAR 的区别是什么？

CHAR 和 VARCHAR 是最常用到的字符串类型，两者的主要区别在于：**CHAR 是定长字符串，VARCHAR 是变长字符串。**

CHAR 在存储时会在右边填充空格以达到指定的长度，检索时会去掉空格；VARCHAR 在存储时需要使用 1 或 2 个额外字节记录字符串的长度，检索时不需要处理。

CHAR 更适合存储长度较短或者长度都差不多的字符串，例如 Bcrypt 算法、MD5 算法加密后的密码、身份证号码。VARCHAR 类型适合存储长度不确定或者差异较大的字符串，例如用户昵称、文章标题等。

CHAR(M) 和 VARCHAR(M) 的 M 都代表能够保存的字符数的最大值，无论是字母、数字还是中文，每个都只占用一个字符。

#### VARCHAR(100)和 VARCHAR(10)的区别是什么？

VARCHAR(100)和 VARCHAR(10)都是变长类型，表示能存储最多 100 个字符和 10 个字符。因此，VARCHAR (100) 可以满足更大范围的字符存储需求，有更好的业务拓展性。而 VARCHAR(10)存储超过 10 个字符时，就需要修改表结构才可以。

虽说 VARCHAR(100)和 VARCHAR(10)能存储的字符范围不同，但二者存储相同的字符串，所占用磁盘的存储空间其实是一样的，这也是很多人容易误解的一点。

不过，VARCHAR(100) 会消耗更多的内存。这是因为 VARCHAR 类型在内存中操作时，通常会分配固定大小的内存块来保存值，即使用字符类型中定义的长度。例如在进行排序的时候，VARCHAR(100)是按照 100 这个长度来进行的，也就会消耗更多内存。

#### DECIMAL 和 FLOAT/DOUBLE 的区别是什么？

DECIMAL 和 FLOAT 的区别是：**DECIMAL 是定点数，FLOAT/DOUBLE 是浮点数。DECIMAL 可以存储精确的小数值，FLOAT/DOUBLE 只能存储近似的小数值。**

DECIMAL 用于存储具有精度要求的小数，例如与货币相关的数据，可以避免浮点数带来的精度损失。

在 Java 中，MySQL 的 DECIMAL 类型对应的是 Java 类 `java.math.BigDecimal`。

#### 为什么不推荐使用 TEXT 和 BLOB？

TEXT 类型类似于 CHAR（0-255 字节）和 VARCHAR（0-65,535 字节），但可以存储更长的字符串，即长文本数据，例如博客内容。

| 类型       | 可存储大小           | 用途           |
| ---------- | -------------------- | -------------- |
| TINYTEXT   | 0-255 字节           | 一般文本字符串 |
| TEXT       | 0-65,535 字节        | 长文本字符串   |
| MEDIUMTEXT | 0-16,772,150 字节    | 较大文本数据   |
| LONGTEXT   | 0-4,294,967,295 字节 | 极大文本数据   |

BLOB 类型主要用于存储二进制大对象，例如图片、音视频等文件。

| 类型       | 可存储大小 | 用途                     |
| ---------- | ---------- | ------------------------ |
| TINYBLOB   | 0-255 字节 | 短文本二进制字符串       |
| BLOB       | 0-65KB     | 二进制字符串             |
| MEDIUMBLOB | 0-16MB     | 二进制形式的长文本数据   |
| LONGBLOB   | 0-4GB      | 二进制形式的极大文本数据 |

在日常开发中，很少使用 TEXT 类型，但偶尔会用到，而 BLOB 类型则基本不常用。如果预期长度范围可以通过 VARCHAR 来满足，建议避免使用 TEXT。

数据库规范通常不推荐使用 BLOB 和 TEXT 类型，这两种类型具有一些缺点和限制，例如：

- 不能有默认值。
- 在使用临时表时无法使用内存临时表，只能在磁盘上创建临时表（《高性能 MySQL》书中有提到）。
- 检索效率较低。
- 不能直接创建索引，需要指定前缀长度。
- 可能会消耗大量的网络和 IO 带宽。
- 可能导致表上的 DML 操作变慢。
- ……

#### ⭐️DATETIME 和 TIMESTAMP 的区别是什么？如何选择？

DATETIME 类型没有时区信息，TIMESTAMP 和时区有关。

TIMESTAMP 只需要使用 4 个字节的存储空间，但是 DATETIME 需要耗费 8 个字节的存储空间。但是，这样同样造成了一个问题，Timestamp 表示的时间范围更小。

- DATETIME：'1000-01-01 00:00:00.000000' 到 '9999-12-31 23:59:59.999999'
- Timestamp：'1970-01-01 00:00:01.000000' UTC 到 '2038-01-19 03:14:07.999999' UTC

`TIMESTAMP` 的核心优势在于其内建的时区处理能力。数据库负责 UTC 存储和基于会话时区的自动转换，简化了需要处理多时区应用的开发。如果应用需要处理多时区，或者希望数据库能自动管理时区转换，`TIMESTAMP` 是自然的选择（注意其时间范围限制，也就是 2038 年问题）。

如果应用场景不涉及时区转换，或者希望应用程序完全控制时区逻辑，并且需要表示 2038 年之后的时间，`DATETIME` 是更稳妥的选择。

关于两者的详细对比以及日期存储类型选择建议，请参考我写的这篇文章： [MySQL 时间类型数据存储建议](https://github.com/Snailclimb/JavaGuide/blob/main/docs/some-thoughts-on-database-storage-time.md)。

#### NULL 和 '' 的区别是什么？

`NULL` 和 `''` (空字符串) 是两个完全不同的值，它们分别表示不同的含义，并在数据库中有着不同的行为。`NULL` 代表缺失或未知的数据，而 `''` 表示一个已知存在的空字符串。它们的主要区别如下：

1. **含义**:
   - `NULL` 代表一个不确定的值，它不等于任何值，包括它自身。因此，`SELECT NULL = NULL` 的结果是 `NULL`，而不是 `true` 或 `false`。 `NULL` 意味着缺失或未知的信息。虽然 `NULL` 不等于任何值，但在某些操作中，数据库系统会将 `NULL` 值视为相同的类别进行处理，例如：`DISTINCT`,`GROUP BY`,`ORDER BY`。需要注意的是，这些操作将 `NULL` 值视为相同的类别进行处理，并不意味着 `NULL` 值之间是相等的。 它们只是在特定操作中被特殊处理，以保证结果的正确性和一致性。 这种处理方式是为了方便数据操作，而不是改变了 `NULL` 的语义。
   - `''` 表示一个空字符串，它是一个已知的值。
2. **存储空间**:
   - `NULL` 的存储空间占用取决于数据库的实现，通常需要一些空间来标记该值为空。
   - `''` 的存储空间占用通常较小，因为它只存储一个空字符串的标志，不需要存储实际的字符。
3. **比较运算**:
   - 任何值与 `NULL` 进行比较（例如 `=`, `!=`, `>`, `<` 等）的结果都是 `NULL`，表示结果不确定。要判断一个值是否为 `NULL`，必须使用 `IS NULL` 或 `IS NOT NULL`。
   - `''` 可以像其他字符串一样进行比较运算。例如，`'' = ''` 的结果是 `true`。
4. **聚合函数**:
   - 大多数聚合函数（例如 `SUM`, `AVG`, `MIN`, `MAX`）会忽略 `NULL` 值。
   - `COUNT(*)` 会统计所有行数，包括包含 `NULL` 值的行。`COUNT(列名)` 会统计指定列中非 `NULL` 值的行数。
   - 空字符串 `''` 会被聚合函数计算在内。例如，`SUM` 会将其视为 0，`MIN` 和 `MAX` 会将其视为一个空字符串。

看了上面的介绍之后，相信你对另外一个高频面试题：“为什么 MySQL 不建议使用 `NULL` 作为列默认值？”也有了答案。

#### ⭐️Boolean 类型如何表示？

MySQL 中没有专门的布尔类型，`BOOL` 和 `BOOLEAN` 是 `TINYINT(1)` 的同义词，通常用 0 表示 false、非 0 表示 true。`BIT(1)` 是位字段类型，也可以存储 0 或 1，但它并不是 `BOOL`/`BOOLEAN` 的实际映射。

#### ⭐️手机号存储用 INT 还是 VARCHAR？

存储手机号，**强烈推荐使用 VARCHAR 类型**，而不是 INT 或 BIGINT。主要原因如下：

1. **格式兼容性与完整性：**
   - 手机号可能包含前导零（如某些地区的固话区号）、国家代码前缀（'+'），甚至可能带有分隔符（'-' 或空格）。INT 或 BIGINT 这种数字类型会自动丢失这些重要的格式信息（比如前导零会被去掉，'+' 和 '-' 无法存储）。
   - VARCHAR 可以原样存储各种格式的号码，无论是国内的 11 位手机号，还是带有国家代码的国际号码，都能完美兼容。
2. **非算术性：** 手机号虽然看起来是数字，但我们从不对它进行数学运算（比如求和、平均值）。它本质上是一个标识符，更像是一个字符串。用 VARCHAR 更符合其数据性质。
3. **查询灵活性：**
   - 业务中常常需要根据号段（前缀）进行查询，例如查找所有 "138" 开头的用户。使用 VARCHAR 类型配合 `LIKE '138%'` 这样的 SQL 查询既直观又高效。
   - 如果使用数字类型，进行类似的前缀匹配通常需要复杂的函数转换（如 CAST 或 SUBSTRING），或者使用范围查询（如 `WHERE phone >= 13800000000 AND phone < 13900000000`），这不仅写法繁琐，而且可能无法有效利用索引，导致性能下降。
4. **加密存储的要求（非常关键）：**
   - 出于数据安全和隐私合规的要求，手机号这类敏感个人信息通常必须加密存储在数据库中。
   - 加密后的数据（密文）是一长串字符串（通常由字母、数字、符号组成，或经过 Base64/Hex 编码），INT 或 BIGINT 类型根本无法存储这种密文。只有 VARCHAR、TEXT 或 BLOB 等类型可以。

**关于 VARCHAR 长度的选择：**

- **如果不加密存储（强烈不推荐！）：** 考虑到国际号码和可能的格式符，VARCHAR(20) 到 VARCHAR(32) 通常是一个比较安全的范围，足以覆盖全球绝大多数手机号格式。VARCHAR(15) 可能对某些带国家码和格式符的号码来说不够用。
- **如果进行加密存储（推荐的标准做法）：** 长度必须根据所选加密算法产生的密文最大长度，以及可能的编码方式（如 Base64 会使长度增加约 1/3）来精确计算和设定。通常会需要更长的 VARCHAR 长度，例如 VARCHAR(128), VARCHAR(256) 甚至更长。

最后，来一张表格总结一下：

| 对比维度         | VARCHAR 类型（推荐）              | INT/BIGINT 类型（不推荐）    | 说明/备注                                                                   |
| ---------------- | --------------------------------- | ---------------------------- | --------------------------------------------------------------------------- |
| **格式兼容性**   | ✔ 能存前导零、"+"、"-"、空格等   | ✘ 自动丢失前导零，不能存符号 | VARCHAR 能原样存储各种手机号格式，INT/BIGINT 只支持单纯数字，且前导零会消失 |
| **完整性**       | ✔ 不丢失任何格式信息             | ✘ 丢失格式信息               | 例如 "013800012345" 存进 INT 会变成 13800012345，"+" 也无法存储             |
| **非算术性**     | ✔ 适合存储“标识符”               | ✘ 只适合做数值运算           | 手机号本质是字符串标识符，不做数学运算，VARCHAR 更贴合实际用途              |
| **查询灵活性**   | ✔ 支持 `LIKE '138%'` 等          | ✘ 查询前缀不方便或性能差     | 使用 VARCHAR 可高效按号段/前缀查询，数字类型需转为字符串或其他复杂处理      |
| **加密存储支持** | ✔ 可存储加密密文（字母、符号等） | ✘ 无法存储密文               | 加密手机号后密文是字符串/二进制，只有 VARCHAR、TEXT、BLOB 等能兼容          |
| **长度设置建议** | 15~20（未加密），加密视情况而定   | 无意义                       | 不加密时 VARCHAR(15~20) 通用，加密后长度取决于算法和编码方式                |

### 【MySQL 基础架构】

#### MySQL 基础架构

> 建议配合 [SQL 语句在 MySQL 中的执行过程](https://github.com/Snailclimb/JavaGuide/blob/main/docs/how-sql-executed-in-mysql.md) 这篇文章来理解 MySQL 基础架构。另外，“一个 SQL 语句在 MySQL 中的执行流程”也是面试中比较常问的一个问题。

下图是 MySQL 的一个简要架构图，从下图你可以很清晰的看到客户端的一条 SQL 语句在 MySQL 内部是如何执行的。

从上图可以看出， MySQL 主要由下面几部分构成：

- **连接器：** 身份认证和权限相关(登录 MySQL 的时候)。
- **查询缓存：** 执行查询语句的时候，会先查询缓存（MySQL 8.0 版本后移除，因为这个功能不太实用）。
- **分析器：** 没有命中缓存的话，SQL 语句就会经过分析器，分析器说白了就是要先看你的 SQL 语句要干嘛，再检查你的 SQL 语句语法是否正确。
- **优化器：** 按照 MySQL 认为最优的方案去执行。
- **执行器：** 执行语句，然后从存储引擎返回数据。 执行语句之前会先判断是否有权限，如果没有权限的话，就会报错。
- **插件式存储引擎**：主要负责数据的存储和读取，采用的是插件式架构，支持 InnoDB、MyISAM、Memory 等多种存储引擎。InnoDB 是 MySQL 的默认存储引擎，绝大部分场景使用 InnoDB 就是最好的选择。

### 【MySQL 存储引擎】

#### MySQL 支持哪些存储引擎？默认使用哪个？

MySQL 支持多种存储引擎，你可以通过 `SHOW ENGINES` 命令来查看 MySQL 支持的所有存储引擎。

![查看 MySQL 提供的所有存储引擎](images/image-20220510105408703-1ff77737.png)

从上图我们可以查看出， MySQL 当前默认的存储引擎是 InnoDB。并且，所有的存储引擎中只有 InnoDB 是事务性存储引擎，也就是说只有 InnoDB 支持事务。

我这里使用的 MySQL 版本是 8.x，不同的 MySQL 版本之间可能会有差别。

MySQL 5.5.5 之前，MyISAM 是 MySQL 的默认存储引擎。5.5.5 版本之后，InnoDB 是 MySQL 的默认存储引擎。

你可以通过 `SELECT VERSION()` 命令查看你的 MySQL 版本。

```bash
mysql> SELECT VERSION();
+-----------+
| VERSION() |
+-----------+
| 8.0.27    |
+-----------+
1 row in set (0.00 sec)
```

你也可以通过 `SHOW VARIABLES LIKE '%storage_engine%'` 命令直接查看 MySQL 当前默认的存储引擎。

```bash
mysql> SHOW VARIABLES  LIKE '%storage_engine%';
+---------------------------------+-----------+
| Variable_name                   | Value     |
+---------------------------------+-----------+
| default_storage_engine          | InnoDB    |
| default_tmp_storage_engine      | InnoDB    |
| disabled_storage_engines        |           |
| internal_tmp_mem_storage_engine | TempTable |
+---------------------------------+-----------+
4 rows in set (0.00 sec)
```

如果你想要深入了解每个存储引擎以及它们之间的区别，推荐你去阅读以下 MySQL 官方文档对应的介绍(面试不会问这么细，了解即可)：

- InnoDB 存储引擎详细介绍： 。
- 其他存储引擎详细介绍： 。

#### MySQL 存储引擎架构了解吗？

MySQL 存储引擎采用的是 **插件式架构** ，支持多种存储引擎，我们甚至可以为不同的数据库表设置不同的存储引擎以适应不同场景的需要。**存储引擎是基于表的，而不是数据库。**

下图展示了具有可插拔存储引擎的 MySQL 架构：

![MySQL architecture diagram showing connectors, interfaces, pluggable storage engines, the file system with files and logs.](images/mysql-architecture-a9cf127e.png)

你还可以根据 MySQL 定义的存储引擎实现标准接口来编写一个属于自己的存储引擎。这些非官方提供的存储引擎可以称为第三方存储引擎，区别于官方存储引擎。像目前最常用的 InnoDB 其实刚开始就是一个第三方存储引擎，后面由于过于优秀，其被 Oracle 直接收购了。

MySQL 官方文档也有介绍到如何编写一个自定义存储引擎，地址： 。

#### ⭐️MyISAM 和 InnoDB 有什么区别？

MySQL 5.5 之前，MyISAM 引擎是 MySQL 的默认存储引擎，可谓是风光一时。

虽然，MyISAM 的性能还行，各种特性也还不错（比如全文索引、压缩、空间函数等）。但是，MyISAM 不支持事务和行级锁，而且最大的缺陷就是崩溃后无法安全恢复。

MySQL 5.5 版本之后，InnoDB 是 MySQL 的默认存储引擎。

言归正传！咱们下面还是来简单对比一下两者：

**1、是否支持行级锁**

MyISAM 只有表级锁(table-level locking)，而 InnoDB 支持行级锁(row-level locking)和表级锁,默认为行级锁。

也就说，MyISAM 一锁就是锁住了整张表，这在并发写的情况下是多么滴憨憨啊！这也是为什么 InnoDB 在并发写的时候，性能更牛皮了！

**2、是否支持事务**

MyISAM 不提供事务支持。

InnoDB 提供事务支持，实现了 SQL 标准定义了四个隔离级别，具有提交(commit)和回滚(rollback)事务的能力。并且，InnoDB 默认使用的 REPEATABLE-READ（可重读）隔离级别是可以解决幻读问题发生的（基于 MVCC 和 Next-Key Lock）。

关于 MySQL 事务的详细介绍，可以看看我写的这篇文章：[MySQL 事务隔离级别详解](https://github.com/Snailclimb/JavaGuide/blob/main/docs/transaction-isolation-level.md)。

**3、是否支持外键**

MyISAM 不支持，而 InnoDB 支持。

外键对于维护数据一致性非常有帮助，但是对性能有一定的损耗。因此，通常情况下，我们是不建议在实际生产项目中使用外键的，在业务代码中进行约束即可！

阿里的《Java 开发手册》也是明确规定禁止使用外键的。

不过，在代码中进行约束的话，对程序员的能力要求更高，具体是否要采用外键还是要根据你的项目实际情况而定。

总结：一般我们也是不建议在数据库层面使用外键的，应用层面可以解决。不过，这样会对数据的一致性造成威胁。具体要不要使用外键还是要根据你的项目来决定。

**4、是否支持数据库异常崩溃后的安全恢复**

MyISAM 不支持，而 InnoDB 支持。

使用 InnoDB 的数据库在异常崩溃后，数据库重新启动的时候会保证数据库恢复到崩溃前的状态。这个恢复的过程依赖于 `redo log` 。

**5、是否支持 MVCC**

MyISAM 不支持，而 InnoDB 支持。

讲真，这个对比有点废话，毕竟 MyISAM 连行级锁都不支持。MVCC 可以看作是行级锁的一个升级，可以有效减少加锁操作，提高性能。

**6、索引实现不一样。**

虽然 MyISAM 引擎和 InnoDB 引擎都是使用 B+Tree 作为索引结构，但是两者的实现方式不太一样。

InnoDB 引擎中，其数据文件本身就是索引文件。相比 MyISAM，索引文件和数据文件是分离的，其表数据文件本身就是按 B+Tree 组织的一个索引结构，树的叶节点 data 域保存了完整的数据记录。

详细区别，推荐你看看我写的这篇文章：[MySQL 索引详解](https://github.com/Snailclimb/JavaGuide/blob/main/docs/mysql-index.md)。

**7、性能有差别。**

InnoDB 的性能比 MyISAM 更强大，不管是在读写混合模式下还是只读模式下，随着 CPU 核数的增加，InnoDB 的读写能力呈线性增长。MyISAM 因为读写不能并发，它的处理能力跟核数没关系。

![InnoDB 和 MyISAM 性能对比](images/innodb-myisam-performance-comparison-c12f5364.png)

**8、数据缓存策略和机制实现不同。**

InnoDB 使用缓冲池（Buffer Pool）缓存数据页和索引页，MyISAM 使用键缓存（Key Cache）仅缓存索引页而不缓存数据页。

**总结**：

- InnoDB 支持行级别的锁粒度，MyISAM 不支持，只支持表级别的锁粒度。
- MyISAM 不提供事务支持。InnoDB 提供事务支持，实现了 SQL 标准定义了四个隔离级别。
- MyISAM 不支持外键，而 InnoDB 支持。
- MyISAM 不支持 MVCC，而 InnoDB 支持。
- 虽然 MyISAM 引擎和 InnoDB 引擎都是使用 B+Tree 作为索引结构，但是两者的实现方式不太一样。
- MyISAM 不支持数据库异常崩溃后的安全恢复，而 InnoDB 支持。
- InnoDB 的性能比 MyISAM 更强大。

最后，再分享一张图片给你，这张图片详细对比了常见的几种 MySQL 存储引擎。

![常见的几种 MySQL 存储引擎对比](images/comparison-of-common-mysql-storage-engines-5d055dea.png)

#### MyISAM 和 InnoDB 如何选择？

大多数时候我们使用的都是 InnoDB 存储引擎，在某些读密集的情况下，使用 MyISAM 也是合适的。不过，前提是你的项目不介意 MyISAM 不支持事务、崩溃恢复等缺点（可是~我们一般都会介意啊）。

《MySQL 高性能》上面有一句话这样写到:

> 不要轻易相信“MyISAM 比 InnoDB 快”之类的经验之谈，这个结论往往不是绝对的。在很多我们已知场景中，InnoDB 的速度都可以让 MyISAM 望尘莫及，尤其是用到了聚簇索引，或者需要访问的数据都可以放入内存的应用。

因此，对于咱们日常开发的业务系统来说，你几乎找不到什么理由使用 MyISAM 了，老老实实用默认的 InnoDB 就可以了！

### 【⭐️MySQL 索引】

#### 索引是什么？

**索引是一种用于快速查询和检索数据的数据结构，其本质可以看成是一种排序好的数据结构。**

索引的作用就相当于书的目录。打个比方：我们在查字典的时候，如果没有目录，那我们就只能一页一页地去找我们需要查的那个字，速度很慢；如果有目录了，我们只需要先去目录里查找字的位置，然后直接翻到那一页就行了。

索引底层数据结构存在很多种类型，常见的索引结构有：B 树、 B+ 树 和 Hash、红黑树。在 MySQL 中，无论是 Innodb 还是 MyISAM，都使用了 B+ 树作为索引结构。

**索引的优点：**

1. **查询速度起飞 (主要目的)**：通过索引，数据库可以**大幅减少需要扫描的数据量**，直接定位到符合条件的记录，从而显著加快数据检索速度，减少磁盘 I/O 次数。
2. **保证数据唯一性**：通过创建**唯一索引 (Unique Index)**,可以确保表中的某一列（或几列组合）的值是独一无二的，比如用户 ID、邮箱等。主键本身就是一种唯一索引。
3. **加速排序和分组**：如果查询中的 ORDER BY 或 GROUP BY 子句涉及的列建有索引，数据库往往可以直接利用索引已经排好序的特性，避免额外的排序操作，从而提升性能。

**索引的缺点：**

1. **创建和维护耗时**：创建索引本身需要时间，特别是对大表操作时。更重要的是，当对表中的数据进行**增、删、改 (DML 操作)** 时，不仅要操作数据本身，相关的索引也必须动态更新和维护，这会**降低这些 DML 操作的执行效率**。
2. **占用存储空间**：索引本质上也是一种数据结构，需要以物理文件（或内存结构）的形式存储，因此会**额外占用一定的磁盘空间**。索引越多、越大，占用的空间也就越多。
3. **可能被误用或失效**：如果索引设计不当，或者查询语句写得不好，数据库优化器可能不会选择使用索引（或者选错索引），反而导致性能下降。

**那么，用了索引就一定能提高查询性能吗？**

**不一定。** 大多数情况下，合理使用索引确实比全表扫描快得多。但也有例外：

- **数据量太小**：如果表里的数据非常少（比如就几百条），全表扫描可能比通过索引查找更快，因为走索引本身也有开销。
- **查询结果集占比过大**：如果要查询的数据占了整张表的大部分（比如超过 20%-30%），优化器可能会认为全表扫描更划算，因为通过索引多次回表（随机 I/O）的成本可能高于一次顺序的全表扫描。
- **索引维护不当或统计信息过时**：导致优化器做出错误判断。

#### 索引为什么快？

索引之所以快，核心原因是它**大大减少了磁盘 I/O 的次数**。

它的本质是一种**排好序的数据结构**，就像书的目录，让我们不用一页一页地翻（全表扫描）。

在 MySQL 中，这个数据结构是**B+树**。B+树结构主要从两方面做了优化：

1. B+树的特点是“矮胖”，一个千万数据的表，索引树的高度可能只有 3-4 层。这意味着，最多只需要**3-4 次磁盘 I/O**，就能精确定位到我想要的数据，而全表扫描可能需要成千上万次，所以速度极快。
2. B+树的叶子节点是**用链表连起来的**。找到开头后，就能顺着链表**顺序读**下去，这对磁盘非常友好，还能触发预读。

#### MySQL 索引底层数据结构是什么？

在 MySQL 中，MyISAM 引擎和 InnoDB 引擎都是使用 B+Tree 作为索引结构，详细介绍可以参考笔者写的这篇文章：[MySQL 索引详解](https://javaguide.cn/database/mysql/mysql-index.html)。

#### 为什么 InnoDB 没有使用哈希作为索引的数据结构？

> 我发现很多求职者甚至是面试官对这个问题都有误解，他们想当然的认为 MySQL 底层并没有使用哈希或者 B 树作为索引的数据结构。
>
> 实际上，不论是提问还是回答这个问题都要区分好存储引擎。像 MEMORY 引擎就同时支持哈希和 B 树。

哈希索引的底层是哈希表。它的优点是，在进行**精确的等值查询**时，理论上时间复杂度是 **O(1)** ，速度极快。比如 `WHERE id = 123`。

但是，它有几个对于通用数据库来说是致命的缺点：

1. **不支持范围查询:** 这是最主要的原因。哈希函数的一个特点是它会把相邻的输入值（比如 `id=100` 和 `id=101`）映射到哈希表中完全不相邻的位置。这种顺序的破坏，使得我们无法处理像 `WHERE age > 30` 或 `BETWEEN 100 AND 200`这样的范围查询。要完成这种查询，哈希索引只能退化为全表扫描。
2. **不支持排序:** 同理，因为哈希值是无序的，所以我们无法利用哈希索引来优化 `ORDER BY` 子句。
3. **不支持部分索引键查询:** 对于联合索引，比如`(col1, col2)`，哈希索引必须使用所有索引列进行查询，它无法单独利用 `col1` 来加速查询。
4. **哈希冲突问题:** 当不同的键产生相同的哈希值时，需要额外的链表或开放寻址来解决，这会降低性能。

鉴于数据库查询中范围查询和排序是极其常见的操作，一个不支持这些功能的索引结构，显然不能作为默认的、通用的索引类型。

#### 为什么 InnoDB 没有使用 B 树作为索引的数据结构？

B 树和 B+树都是优秀的多路平衡搜索树，非常适合磁盘存储，因为它们都很“矮胖”，能最大化地利用每一次磁盘 I/O。

但 B+树是 B 树的一个增强版，它针对数据库场景做了几个关键优化：

1. **I/O 效率更高:** 在 B+树中，只有叶子节点才存储数据（或数据指针），而非叶子节点只存储索引键。因为非叶子节点不存数据，所以它们可以容纳更多的索引键。这意味着 B+树的“扇出”更大，在同样的数据量下，B+树通常会比 B 树更矮，也就意味着查找数据所需的磁盘 I/O 次数更少。
2. **查询性能更稳定:** 在 B+树中，任何一次查询都必须从根节点走到叶子节点才能找到数据，所以查询路径的长度是固定的。而在 B 树中，如果运气好，可能在非叶子节点就找到了数据，但运气不好也得走到叶子，这导致查询性能不稳定。
3. **对范围查询极其友好:** 这是 B+树最核心的优势。它的所有叶子节点之间通过一个双向链表连接。当我们执行一个范围查询（比如 `WHERE id > 100`）时，只需要通过树形结构找到 `id=100` 的叶子节点，然后就可以沿着链表向后顺序扫描，而无需再回溯到上层节点。这使得范围查询的效率大大提高。

#### 什么是覆盖索引？

如果一个索引包含（或者说覆盖）所有需要查询的字段的值，我们就称之为 **覆盖索引（Covering Index）**。

在 InnoDB 存储引擎中，非主键索引的叶子节点包含的是主键的值。这意味着，当使用非主键索引进行查询时，数据库会先找到对应的主键值，然后再通过主键索引来定位和检索完整的行数据。这个过程被称为“回表”。

**覆盖索引即需要查询的字段正好是索引的字段，那么直接根据该索引，就可以查到数据了，而无需回表查询。**

#### 请解释一下 MySQL 的联合索引及其最左前缀原则

使用表中的多个字段创建索引，就是 **联合索引**，也叫 **组合索引** 或 **复合索引**。

以 `score` 和 `name` 两个字段建立联合索引：

```sql
ALTER TABLE `cus_order` ADD INDEX id_score_name(score, name);
```

最左前缀匹配原则指的是在使用联合索引时，MySQL 会根据索引中的字段顺序，从左到右依次匹配查询条件中的字段。如果查询条件与索引中的最左侧字段相匹配，那么 MySQL 就会使用索引来过滤数据，这样可以提高查询效率。

最左匹配原则会一直向右匹配，直到遇到范围查询（如 >、<）为止。对于 >=、<=、BETWEEN 以及前缀匹配 LIKE 的范围查询，不会停止匹配（相关阅读：[联合索引的最左匹配原则全网都在说的一个错误结论](https://mp.weixin.qq.com/s/8qemhRg5MgXs1So5YCv0fQ)）。

假设有一个联合索引 `(column1, column2, column3)`，其从左到右的所有前缀为 `(column1)`、`(column1, column2)`、`(column1, column2, column3)`（创建 1 个联合索引相当于创建了 3 个索引），包含这些列的所有查询都会走索引而不会全表扫描。

我们在使用联合索引时，可以将区分度高的字段放在最左边，这也可以过滤更多数据。

我们这里简单演示一下最左前缀匹配的效果。

1、创建一个名为 `student` 的表，这张表只有 `id`、`name`、`class` 这 3 个字段。

```sql
CREATE TABLE `student` (
  `id` int NOT NULL,
  `name` varchar(100) DEFAULT NULL,
  `class` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `name_class_idx` (`name`,`class`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

2、下面我们分别测试三条不同的 SQL 语句。

```sql
# 可以命中索引
SELECT * FROM student WHERE name = 'Anne Henry';
EXPLAIN SELECT * FROM student WHERE name = 'Anne Henry' AND class = 'lIrm08RYVk';
# 无法命中索引
SELECT * FROM student WHERE class = 'lIrm08RYVk';
```

再来看一个常见的面试题：如果有索引 `联合索引（a，b，c）`，查询 `a=1 AND c=1` 会走索引么？`c=1` 呢？`b=1 AND c=1` 呢？ `b = 1 AND a = 1 AND c = 1` 呢？

先不要往下看答案，给自己 3 分钟时间想一想。

1. 查询 `a=1 AND c=1`：根据最左前缀匹配原则，查询可以使用索引的前缀部分。因此，该查询仅在 `a=1` 上使用索引，然后对结果进行 `c=1` 的过滤。
2. 查询 `c=1`：由于查询中不包含最左列 `a`，根据最左前缀匹配原则，整个索引都无法被使用。
3. 查询 `b=1 AND c=1`：和第二种一样的情况，整个索引都不会使用。
4. 查询 `b=1 AND a=1 AND c=1`：这个查询是可以用到索引的。查询优化器分析 SQL 语句时，对于联合索引，会对查询条件进行重排序，以便用到索引。会将 `b=1` 和 `a=1` 的条件进行重排序，变成 `a=1 AND b=1 AND c=1`。

MySQL 8.0.13 版本引入了索引跳跃扫描（Index Skip Scan，简称 ISS），它可以在某些索引查询场景下提高查询效率。在没有 ISS 之前，不满足最左前缀匹配原则的联合索引查询中会执行全表扫描。而 ISS 允许 MySQL 在某些情况下避免全表扫描，即使查询条件不符合最左前缀。不过，这个功能比较鸡肋， 和 Oracle 中的没法比，MySQL 8.0.31 还报告了一个 bug：[Bug #109145 Using index for skip scan cause incorrect result](https://bugs.mysql.com/bug.php?id=109145)（后续版本已经修复）。个人建议知道有这个东西就好，不需要深究，实际项目也不一定能用上。

#### SELECT \* 会导致索引失效吗？

`SELECT *` 不会直接导致索引失效（如果不走索引大概率是因为 where 查询范围过大导致的），但它可能会带来一些其他的性能问题比如造成网络传输和数据处理的浪费、无法使用索引覆盖。

#### 哪些字段适合创建索引？

- **不为 NULL 的字段**：索引字段的数据应该尽量不为 NULL，因为对于数据为 NULL 的字段，数据库较难优化。如果字段频繁被查询，但又避免不了为 NULL，建议使用 0,1,true,false 这样语义较为清晰的短值或短字符作为替代。
- **被频繁查询的字段**：我们创建索引的字段应该是查询操作非常频繁的字段。
- **被作为条件查询的字段**：被作为 WHERE 条件查询的字段，应该被考虑建立索引。
- **频繁需要排序的字段**：索引已经排序，这样查询可以利用索引的排序，加快排序查询时间。
- **被经常频繁用于连接的字段**：经常用于连接的字段可能是一些外键列，对于外键列并不一定要建立外键，只是说该列涉及到表与表的关系。对于频繁被连接查询的字段，可以考虑建立索引，提高多表连接查询的效率。

#### 索引失效的原因有哪些？

1. 创建了组合索引，但查询条件未遵守最左匹配原则;
2. 在索引列上进行计算、函数、类型转换等操作;
3. 以 % 开头的 LIKE 查询比如 `LIKE '%abc';`;
4. 查询条件中使用 OR，且 OR 的前后条件中有一个列没有索引，涉及的索引都不会被使用到;
5. IN 的取值范围较大时会导致索引失效，走全表扫描(NOT IN 和 IN 的失效场景相同);
6. 发生[隐式转换](https://javaguide.cn/database/mysql/index-invalidation-caused-by-implicit-conversion.html "隐式转换");

### 【MySQL 查询缓存】

#### MySQL 查询缓存

MySQL 查询缓存是查询结果缓存。执行查询语句的时候，会先查询缓存，如果缓存中有对应的查询结果，就会直接返回。

`my.cnf` 加入以下配置，重启 MySQL 开启查询缓存

```properties
query_cache_type=1
query_cache_size=600000
```

MySQL 执行以下命令也可以开启查询缓存

```properties
set global  query_cache_type=1;
set global  query_cache_size=600000;
```

查询缓存会在同样的查询条件和数据情况下，直接返回缓存中的结果。但需要注意的是，查询缓存的匹配条件非常严格，任何细微的差异都会导致缓存无法命中。这里的查询条件包括查询语句本身、当前使用的数据库、以及其他可能影响结果的因素，如客户端协议版本号等。

**查询缓存不命中的情况：**

1. 任何两个查询在任何字符上的不同都会导致缓存不命中。
2. 如果查询中包含任何用户自定义函数、存储函数、用户变量、临时表、MySQL 库中的系统表，其查询结果也不会被缓存。
3. 缓存建立之后，MySQL 的查询缓存系统会跟踪查询中涉及的每张表，如果这些表（数据或结构）发生变化，那么和这张表相关的所有缓存数据都将失效。

**缓存虽然能够提升数据库的查询性能，但是缓存同时也带来了额外的开销，每次查询后都要做一次缓存操作，失效后还要销毁。** 因此，开启查询缓存要谨慎，尤其对于写密集的应用来说更是如此。如果开启，要注意合理控制缓存空间大小，一般来说其大小设置为几十 MB 比较合适。此外，还可以通过 `sql_cache` 和 `sql_no_cache` 来控制某个查询语句是否需要缓存：

```sql
SELECT sql_no_cache COUNT(*) FROM usr;
```

MySQL 5.6 开始，查询缓存已默认禁用。MySQL 8.0 开始，已经不再支持查询缓存了（具体可以参考这篇文章：[MySQL 8.0: Retiring Support for the Query Cache](https://dev.mysql.com/blog-archive/mysql-8-0-retiring-support-for-the-query-cache/)）。

![MySQL 8.0: Retiring Support for the Query Cache](images/mysql8.0-retiring-support-for-the-query-cache-56234f85.png)

### 【⭐️MySQL 日志】

#### ⭐️MySQL 日志

上诉问题的答案可以在[《Java 面试指北》(付费，点击链接领取优惠卷)](https://javaguide.cn/zhuanlan/java-mian-shi-zhi-bei.html) 的 **「技术面试题篇」** 中找到。

![《Java 面试指北》技术面试题篇](images/technical-interview-questions-41fe5561.png)

文章地址： （密码获取：）。

### 【⭐️MySQL 事务】

#### 什么是事务？

我们设想一个场景，这个场景中我们需要插入多条相关联的数据到数据库，不幸的是，这个过程可能会遇到下面这些问题：

- 数据库中途突然因为某些原因挂掉了。
- 客户端突然因为网络原因连接不上数据库了。
- 并发访问数据库时，多个线程同时写入数据库，覆盖了彼此的更改。
- ……

上面的任何一个问题都可能会导致数据的不一致性。为了保证数据的一致性，系统必须能够处理这些问题。事务就是我们抽象出来简化这些问题的首选机制。事务的概念起源于数据库，目前，已经成为一个比较广泛的概念。

**何为事务？** 一言蔽之，**事务是逻辑上的一组操作，要么都执行，要么都不执行。**

事务最经典也经常被拿出来说例子就是转账了。假如小明要给小红转账 1000 元，这个转账会涉及到两个关键操作，这两个操作必须都成功或者都失败。

1. 将小明的余额减少 1000 元
2. 将小红的余额增加 1000 元。

事务会把这两个操作就可以看成逻辑上的一个整体，这个整体包含的操作要么都成功，要么都要失败。这样就不会出现小明余额减少而小红的余额却并没有增加的情况。

![事务示意图](images/_E4_BA_8B_E5_8A_A1_E7_A4_BA_E6_84_8F_E5_9B_BE-a0059ccb.png)

#### 什么是数据库事务？

大多数情况下，我们在谈论事务的时候，如果没有特指**分布式事务**，往往指的就是**数据库事务**。

数据库事务在我们日常开发中接触的最多了。如果你的项目属于单体架构的话，你接触到的往往就是数据库事务了。

**那数据库事务有什么作用呢？**

简单来说，数据库事务可以保证多个对数据库的操作（也就是 SQL 语句）构成一个逻辑上的整体。构成这个逻辑上的整体的这些数据库操作遵循：**要么全部执行成功,要么全部不执行** 。

```sql
# 开启一个事务
START TRANSACTION;
# 多条 SQL 语句
SQL1,SQL2...
# 提交事务
COMMIT;
```

![数据库事务示意图](images/_E6_95_B0_E6_8D_AE_E5_BA_93_E4_BA_8B_E5_8A_A1_E7_A4_BA_E6_84-34ac1d2d.png)

另外，关系型数据库（例如：`MySQL`、`SQL Server`、`Oracle` 等）事务都有 **ACID** 特性：

![ACID](images/ACID-ad1efa4f.png)

1. **原子性**（`Atomicity`）：事务是最小的执行单位，不允许分割。事务的原子性确保动作要么全部完成，要么完全不起作用；
2. **一致性**（`Consistency`）：执行事务前后，数据保持一致，例如转账业务中，无论事务是否成功，转账者和收款人的总额应该是不变的；
3. **隔离性**（`Isolation`）：并发访问数据库时，一个用户的事务不被其他事务所干扰，各并发事务之间数据库是独立的；
4. **持久性**（`Durability`）：一个事务被提交之后。它对数据库中数据的改变是持久的，即使数据库发生故障也不应该对其有任何影响。

🌈 这里要额外补充一点：**只有保证了事务的持久性、原子性、隔离性之后，一致性才能得到保障。也就是说 A、I、D 是手段，C 是目的！** 想必大家也和我一样，被 ACID 这个概念被误导了很久! 我也是看周志明老师的公开课[《周志明的软件架构课》](https://time.geekbang.org/opencourse/intro/100064201)才搞清楚的（多看好书！！！）。

![AID->C](images/AID-_3EC-78c67e55.png)

另外，DDIA 也就是 [《Designing Data-Intensive Application（数据密集型应用系统设计）》](https://book.douban.com/subject/30329536/) 的作者在他的这本书中如是说：

> Atomicity, isolation, and durability are properties of the database, whereas consis‐
> tency (in the ACID sense) is a property of the application. The application may rely
> on the database’s atomicity and isolation properties in order to achieve consistency,
> but it’s not up to the database alone.
>
> 翻译过来的意思是：原子性，隔离性和持久性是数据库的属性，而一致性（在 ACID 意义上）是应用程序的属性。应用可能依赖数据库的原子性和隔离属性来实现一致性，但这并不仅取决于数据库。因此，字母 C 不属于 ACID 。

《Designing Data-Intensive Application（数据密集型应用系统设计）》这本书强推一波，值得读很多遍！豆瓣有接近 90% 的人看了这本书之后给了五星好评。另外，中文翻译版本已经在 GitHub 开源，地址：[https://github.com/Vonng/ddia](https://github.com/Vonng/ddia) 。

#### 并发事务带来了哪些问题?

在典型的应用程序中，多个事务并发运行，经常会操作相同的数据来完成各自的任务（多个用户对同一数据进行操作）。并发虽然是必须的，但可能会导致以下的问题。

#### 脏读（Dirty read）

一个事务读取数据并且对数据进行了修改，这个修改对其他事务来说是可见的，即使当前事务没有提交。这时另外一个事务读取了这个还未提交的数据，但第一个事务突然回滚，导致数据并没有被提交到数据库，那第二个事务读取到的就是脏数据，这也就是脏读的由来。

例如：事务 1 读取某表中的数据 A=20，事务 1 修改 A=A-1，事务 2 读取到 A = 19,事务 1 回滚导致对 A 的修改并未提交到数据库， A 的值还是 20。

![脏读](images/concurrency-consistency-issues-dirty-reading-25db2e8b.png)

#### 丢失修改（Lost to modify）

在一个事务读取一个数据时，另外一个事务也访问了该数据，那么在第一个事务中修改了这个数据后，第二个事务也修改了这个数据。这样第一个事务内的修改结果就被丢失，因此称为丢失修改。

例如：事务 1 读取某表中的数据 A=20，事务 2 也读取 A=20，事务 1 先修改 A=A-1，事务 2 后来也修改 A=A-1，最终结果 A=19，事务 1 的修改被丢失。

![丢失修改](images/concurrency-consistency-issues-missing-modifications-daf6a627.png)

#### 不可重复读（Unrepeatable read）

指在一个事务内多次读同一数据。在这个事务还没有结束时，另一个事务也访问该数据。那么，在第一个事务中的两次读数据之间，由于第二个事务的修改导致第一个事务两次读取的数据可能不太一样。这就发生了在一个事务内两次读到的数据是不一样的情况，因此称为不可重复读。

例如：事务 1 读取某表中的数据 A=20，事务 2 也读取 A=20，事务 1 修改 A=A-1，事务 2 再次读取 A =19，此时读取的结果和第一次读取的结果不同。

![不可重复读](images/concurrency-consistency-issues-unrepeatable-read-66118df3.png)

#### 幻读（Phantom read）

幻读与不可重复读类似。它发生在一个事务读取了几行数据，接着另一个并发事务插入了一些数据时。在随后的查询中，第一个事务就会发现多了一些原本不存在的记录，就好像发生了幻觉一样，所以称为幻读。

例如：事务 2 读取某个范围的数据，事务 1 在这个范围插入了新的数据，事务 2 再次读取这个范围的数据发现相比于第一次读取的结果多了新的数据。

![幻读](images/concurrency-consistency-issues-phantom-read-96030f2a.png)

#### 不可重复读和幻读有什么区别？

- 不可重复读：同一事务内，同一条记录被其他事务修改或删除，导致再次读取时记录内容或存在性发生变化。
- 幻读：同一事务内，同一个范围条件查询多次执行时，符合条件的记录集合发生变化，出现新增或消失的记录。

幻读其实可以看作是不可重复读的一种特殊情况，单独把幻读区分出来的原因主要是解决幻读和不可重复读的方案不一样。

举个例子：执行 `delete` 和 `update` 操作的时候，可以直接对记录加锁，保证事务安全。而执行 `insert` 操作的时候，由于记录锁（Record Lock）只能锁住已经存在的记录，为了避免插入新记录，需要依赖间隙锁（Gap Lock）。也就是说执行 `insert` 操作的时候需要依赖 Next-Key Lock（Record Lock+Gap Lock） 进行加锁来保证不出现幻读。

#### 并发事务的控制方式有哪些？

MySQL 中并发事务的控制方式无非就两种：**锁** 和 **MVCC**。锁可以看作是悲观控制的模式，多版本并发控制（MVCC，Multiversion concurrency control）可以看作是乐观控制的模式。

**锁** 控制方式下会通过锁来显式控制共享资源而不是通过调度手段，MySQL 中主要是通过 **读写锁** 来实现并发控制。

- **共享锁（S 锁）**：又称读锁，事务在读取记录的时候获取共享锁，允许多个事务同时获取（锁兼容）。
- **排他锁（X 锁）**：又称写锁/独占锁，事务在修改记录的时候获取排他锁，不允许多个事务同时获取。如果一个记录已经被加了排他锁，那其他事务不能再对这条记录加任何类型的锁（锁不兼容）。

读写锁可以做到读读并行，但是无法做到写读、写写并行。另外，根据根据锁粒度的不同，又被分为 **表级锁(table-level locking)** 和 **行级锁(row-level locking)** 。InnoDB 不光支持表级锁，还支持行级锁，默认为行级锁。行级锁的粒度更小，仅对相关的记录上锁即可（对一行或者多行记录加锁），所以对于并发写入操作来说， InnoDB 的性能更高。不论是表级锁还是行级锁，都存在共享锁（Share Lock，S 锁）和排他锁（Exclusive Lock，X 锁）这两类。

**MVCC** 是多版本并发控制方法，即对一份数据会存储多个版本，通过事务的可见性来保证事务能看到自己应该看到的版本。通常会有一个全局的版本分配器来为每一行数据设置版本号，版本号是唯一的。

MVCC 在 MySQL 中实现所依赖的手段主要是: **隐藏字段、read view、undo log**。

- undo log : undo log 用于记录某行数据的多个版本的数据。
- read view 和 隐藏字段 : 用来判断当前版本数据的可见性。

关于 InnoDB 对 MVCC 的具体实现可以看这篇文章：[InnoDB 存储引擎对 MVCC 的实现](https://github.com/Snailclimb/JavaGuide/blob/main/docs/innodb-implementation-of-mvcc.md) 。

#### SQL 标准定义了哪些事务隔离级别?

SQL 标准定义了四种事务隔离级别，用来平衡事务的隔离性（Isolation）和并发性能。级别越高，数据一致性越好，但并发性能可能越低。这四个级别是：

- **READ-UNCOMMITTED(读取未提交)** ：最低的隔离级别，允许读取尚未提交的数据变更，可能会导致脏读、幻读或不可重复读。这种级别在实际应用中很少使用，因为它对数据一致性的保证太弱。
- **READ-COMMITTED(读取已提交)** ：允许读取并发事务已经提交的数据，可以阻止脏读，但是幻读或不可重复读仍有可能发生。这是大多数数据库（如 Oracle, SQL Server）的默认隔离级别。
- **REPEATABLE-READ(可重复读)** ：对同一字段的多次读取结果都是一致的，除非数据是被本身事务自己所修改，可以阻止脏读和不可重复读，但幻读仍有可能发生。MySQL InnoDB 存储引擎的默认隔离级别正是 REPEATABLE READ。并且，InnoDB 在此级别下通过 MVCC（多版本并发控制） 和 Next-Key Locks（间隙锁+行锁） 机制，在很大程度上解决了幻读问题。
- **SERIALIZABLE(可串行化)** ：最高的隔离级别，完全服从 ACID 的隔离级别。所有的事务依次逐个执行，这样事务之间就完全不可能产生干扰，也就是说，该级别可以防止脏读、不可重复读以及幻读。

| 隔离级别         | 脏读 (Dirty Read) | 不可重复读 (Non-Repeatable Read) | 幻读 (Phantom Read)    |
| ---------------- | ----------------- | -------------------------------- | ---------------------- |
| READ UNCOMMITTED | √                 | √                                | √                      |
| READ COMMITTED   | ×                 | √                                | √                      |
| REPEATABLE READ  | ×                 | ×                                | √ (标准) / ≈× (InnoDB) |
| SERIALIZABLE     | ×                 | ×                                | ×                      |

#### MySQL 的默认隔离级别是什么?

MySQL InnoDB 存储引擎的默认隔离级别是 **REPEATABLE READ**。可以通过以下命令查看：

- MySQL 8.0 之前：`SELECT @@tx_isolation;`
- MySQL 8.0 及之后：`SELECT @@transaction_isolation;`

```sql
mysql> SELECT @@tx_isolation;
+-----------------+
| @@tx_isolation  |
+-----------------+
| REPEATABLE-READ |
+-----------------+
```

关于 MySQL 事务隔离级别的详细介绍，可以看看我写的这篇文章：[MySQL 事务隔离级别详解](https://github.com/Snailclimb/JavaGuide/blob/main/docs/transaction-isolation-level.md)。

#### MySQL 的隔离级别是基于锁实现的吗？

MySQL 的隔离级别基于锁和 MVCC 机制共同实现的。

SERIALIZABLE 隔离级别是通过锁来实现的，READ-COMMITTED 和 REPEATABLE-READ 隔离级别是基于 MVCC 实现的。不过， SERIALIZABLE 之外的其他隔离级别可能也需要用到锁机制，就比如 REPEATABLE-READ 在当前读情况下需要使用加锁读来保证不会出现幻读。

### 【MySQL 锁】

#### 表级锁和行级锁了解吗？有什么区别？

MyISAM 仅仅支持表级锁(table-level locking)，一锁就锁整张表，这在并发写的情况下性非常差。InnoDB 不光支持表级锁(table-level locking)，还支持行级锁(row-level locking)，默认为行级锁。

行级锁的粒度更小，仅对相关的记录上锁即可（对一行或者多行记录加锁），所以对于并发写入操作来说， InnoDB 的性能更高。

**表级锁和行级锁对比**：

- **表级锁：** MySQL 中锁定粒度最大的一种锁（全局锁除外），是针对非索引字段加的锁，对当前操作的整张表加锁，实现简单，资源消耗也比较少，加锁快，不会出现死锁。不过，触发锁冲突的概率最高，高并发下效率极低。表级锁和存储引擎无关，MyISAM 和 InnoDB 引擎都支持表级锁。
- **行级锁：** MySQL 中锁定粒度最小的一种锁，是 **针对索引字段加的锁** ，只针对当前操作的行记录进行加锁。 行级锁能大大减少数据库操作的冲突。其加锁粒度最小，并发度高，但加锁的开销也最大，加锁慢，会出现死锁。行级锁和存储引擎有关，是在存储引擎层面实现的。

#### 行级锁的使用有什么注意事项？

InnoDB 的行锁是针对索引字段加的锁，表级锁是针对非索引字段加的锁。当我们执行 `UPDATE`、`DELETE` 语句时，如果 `WHERE`条件中字段没有命中唯一索引或者索引失效的话，就会导致扫描全表对表中的所有行记录进行加锁。这个在我们日常工作开发中经常会遇到，一定要多多注意！！！

不过，很多时候即使用了索引也有可能会走全表扫描，这是因为 MySQL 优化器的原因。

#### InnoDB 有哪几类行锁？

InnoDB 行锁是通过对索引数据页上的记录加锁实现的，MySQL InnoDB 支持三种行锁定方式：

- **记录锁（Record Lock）**：属于单个行记录上的锁。
- **间隙锁（Gap Lock）**：锁定一个范围，不包括记录本身。
- **临键锁（Next-Key Lock）**：Record Lock+Gap Lock，锁定一个范围，包含记录本身，主要目的是为了解决幻读问题（MySQL 事务部分提到过）。记录锁只能锁住已经存在的记录，为了避免插入新记录，需要依赖间隙锁。

**在 InnoDB 默认的隔离级别 REPEATABLE-READ 下，行锁默认使用的是 Next-Key Lock。但是，如果操作的索引是唯一索引或主键，InnoDB 会对 Next-Key Lock 进行优化，将其降级为 Record Lock，即仅锁住索引本身，而不是范围。**

#### 共享锁和排他锁呢？

不论是表级锁还是行级锁，都存在共享锁（Share Lock，S 锁）和排他锁（Exclusive Lock，X 锁）这两类：

- **共享锁（S 锁）**：又称读锁，事务在读取记录的时候获取共享锁，允许多个事务同时获取（锁兼容）。
- **排他锁（X 锁）**：又称写锁/独占锁，事务在修改记录的时候获取排他锁，不允许多个事务同时获取。如果一个记录已经被加了排他锁，那其他事务不能再对这条事务加任何类型的锁（锁不兼容）。

排他锁与任何的锁都不兼容，共享锁仅和共享锁兼容。

|      | S 锁   | X 锁 |
| :--- | :----- | :--- |
| S 锁 | 不冲突 | 冲突 |
| X 锁 | 冲突   | 冲突 |

由于 MVCC 的存在，对于一般的 `SELECT` 语句，InnoDB 不会加任何锁。不过， 你可以通过以下语句显式加共享锁或排他锁。

```sql
# 共享锁 可以在 MySQL 5.7 和 MySQL 8.0 中使用
SELECT ... LOCK IN SHARE MODE;
# 共享锁 可以在 MySQL 8.0 中使用
SELECT ... FOR SHARE;
# 排他锁
SELECT ... FOR UPDATE;
```

#### 意向锁有什么作用？

如果需要用到表锁的话，如何判断表中的记录没有行锁呢，一行一行遍历肯定是不行，性能太差。我们需要用到一个叫做意向锁的东东来快速判断是否可以对某个表使用表锁。

意向锁是表级锁，共有两种：

- **意向共享锁（Intention Shared Lock，IS 锁）**：事务有意向对表中的某些记录加共享锁（S 锁），加共享锁前必须先取得该表的 IS 锁。
- **意向排他锁（Intention Exclusive Lock，IX 锁）**：事务有意向对表中的某些记录加排他锁（X 锁），加排他锁之前必须先取得该表的 IX 锁。

**意向锁是由数据引擎自己维护的，用户无法手动操作意向锁，在为数据行加共享/排他锁之前，InnoDB 会先获取该数据行所在在数据表的对应意向锁。**

意向锁之间是互相兼容的。

|       | IS 锁 | IX 锁 |
| ----- | ----- | ----- |
| IS 锁 | 兼容  | 兼容  |
| IX 锁 | 兼容  | 兼容  |

意向锁和共享锁和排它锁互斥（这里指的是表级别的共享锁和排他锁，意向锁不会与行级的共享锁和排他锁互斥）。

|      | IS 锁 | IX 锁 |
| ---- | ----- | ----- |
| S 锁 | 兼容  | 互斥  |
| X 锁 | 互斥  | 互斥  |

《MySQL 技术内幕 InnoDB 存储引擎》这本书对应的描述应该是笔误了。

#### 当前读和快照读有什么区别？

**快照读**（一致性非锁定读）就是单纯的 `SELECT` 语句，但不包括下面这两类 `SELECT` 语句：

```sql
# 排他锁，可以在 MySQL 5.7 和 MySQL 8.0 中使用
SELECT ... FOR UPDATE
# 共享锁，可以在 MySQL 5.7 和 MySQL 8.0 中使用
SELECT ... LOCK IN SHARE MODE;
# 共享锁，可以在 MySQL 8.0 中使用
SELECT ... FOR SHARE;
```

快照即记录的历史版本，每行记录可能存在多个历史版本（多版本技术）。

快照读的情况下，如果读取的记录正在执行 UPDATE/DELETE 操作，读取操作不会因此去等待记录上 X 锁的释放，而是会去读取行的一个快照。

只有在事务隔离级别 RC(读取已提交) 和 RR（可重读）下，InnoDB 才会使用一致性非锁定读：

- 在 RC 级别下，对于快照数据，一致性非锁定读总是读取被锁定行的最新一份快照数据。
- 在 RR 级别下，对于快照数据，一致性非锁定读总是读取本事务开始时的行数据版本。

快照读比较适合对于数据一致性要求不是特别高且追求极致性能的业务场景。

**当前读** （一致性锁定读）就是给行记录加 X 锁或 S 锁。

当前读的一些常见 SQL 语句类型如下：

```sql
# 对读的记录加一个X锁
SELECT...FOR UPDATE
# 对读的记录加一个S锁
SELECT...LOCK IN SHARE MODE
# 对读的记录加一个S锁
SELECT...FOR SHARE
# 对修改的记录加一个X锁
INSERT...
UPDATE...
DELETE...
```

#### 自增锁有了解吗？

> 不太重要的一个知识点，简单了解即可。

关系型数据库设计表的时候，通常会有一列作为自增主键。InnoDB 中的自增主键会涉及一种比较特殊的表级锁— **自增锁（AUTO-INC Locks）** 。

```sql
CREATE TABLE `sequence_id` (
  `id` BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
  `stub` CHAR(10) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`),
  UNIQUE KEY `stub` (`stub`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

更准确点来说，不仅仅是自增主键，`AUTO_INCREMENT`的列都会涉及到自增锁，毕竟非主键也可以设置自增长。

如果一个事务正在插入数据到有自增列的表时，会先获取自增锁，拿不到就可能会被阻塞住。这里的阻塞行为只是自增锁行为的其中一种，可以理解为自增锁就是一个接口，其具体的实现有多种。具体的配置项为 `innodb_autoinc_lock_mode` （MySQL 5.1.22 引入），可以选择的值如下：

| innodb_autoinc_lock_mode | 介绍                           |
| :----------------------- | :----------------------------- |
| 0                        | 传统模式                       |
| 1                        | 连续模式（MySQL 8.0 之前默认） |
| 2                        | 交错模式(MySQL 8.0 之后默认)   |

交错模式下，所有的“INSERT-LIKE”语句（所有的插入语句，包括：`INSERT`、`REPLACE`、`INSERT…SELECT`、`REPLACE…SELECT`、`LOAD DATA`等）都不使用表级锁，使用的是轻量级互斥锁实现，多条插入语句可以并发执行，速度更快，扩展性也更好。

不过，如果你的 MySQL 数据库有主从同步需求并且 Binlog 存储格式为 Statement 的话，不要将 InnoDB 自增锁模式设置为交叉模式，不然会有数据不一致性问题。这是因为并发情况下插入语句的执行顺序就无法得到保障。

> 如果 MySQL 采用的格式为 Statement ，那么 MySQL 的主从同步实际上同步的就是一条一条的 SQL 语句。

最后，再推荐一篇文章：[为什么 MySQL 的自增主键不单调也不连续](https://draveness.me/whys-the-design-mysql-auto-increment/) 。

### 【⭐️MySQL 性能优化】

#### 能用 MySQL 直接存储文件（比如图片）吗？

可以是可以，直接存储文件对应的二进制数据即可。不过，还是建议不要在数据库中存储文件，会严重影响数据库性能，消耗过多存储空间。

可以选择使用云服务厂商提供的开箱即用的文件存储服务，成熟稳定，价格也比较低。

也可以选择自建文件存储服务，实现起来也不难，基于 FastDFS、MinIO（推荐） 等开源项目就可以实现分布式文件服务。

**数据库只存储文件地址信息，文件由文件存储服务负责存储。**

#### MySQL 如何存储 IP 地址？

可以将 IP 地址转换成整形数据存储，性能更好，占用空间也更小。

MySQL 提供了两个方法来处理 ip 地址

- `INET_ATON()`：把 ip 转为无符号整型 (4-8 位)
- `INET_NTOA()` :把整型的 ip 转为地址

插入数据前，先用 `INET_ATON()` 把 ip 地址转为整型，显示数据时，使用 `INET_NTOA()` 把整型的 ip 地址转为地址显示即可。

#### 有哪些常见的 SQL 优化手段？

[《Java 面试指北》(付费)](https://javaguide.cn/zhuanlan/java-mian-shi-zhi-bei.html) 的 **「技术面试题篇」** 有一篇文章详细介绍了常见的 SQL 优化手段，非常全面，清晰易懂！

![常见的 SQL 优化手段](images/javamianshizhibei-sql-optimization-3cdc5f03.png)

文章地址：https://www.yuque.com/snailclimb/mf2z3k/abc2sv （密码获取：）。

#### 如何分析 SQL 的性能？

我们可以使用 `EXPLAIN` 命令来分析 SQL 的 **执行计划** 。执行计划是指一条 SQL 语句在经过 MySQL 查询优化器的优化会后，具体的执行方式。

`EXPLAIN` 并不会真的去执行相关的语句，而是通过 **查询优化器** 对语句进行分析，找出最优的查询方案，并显示对应的信息。

`EXPLAIN` 适用于 `SELECT`, `DELETE`, `INSERT`, `REPLACE`, 和 `UPDATE`语句，我们一般分析 `SELECT` 查询较多。

我们这里简单来演示一下 `EXPLAIN` 的使用。

`EXPLAIN` 的输出格式如下：

```sql
mysql> EXPLAIN SELECT `score`,`name` FROM `cus_order` ORDER BY `score` DESC;
+----+-------------+-----------+------------+------+---------------+------+---------+------+--------+----------+----------------+
| id | select_type | table     | partitions | type | possible_keys | key  | key_len | ref  | rows   | filtered | Extra          |
+----+-------------+-----------+------------+------+---------------+------+---------+------+--------+----------+----------------+
|  1 | SIMPLE      | cus_order | NULL       | ALL  | NULL          | NULL | NULL    | NULL | 997572 |   100.00 | Using filesort |
+----+-------------+-----------+------------+------+---------------+------+---------+------+--------+----------+----------------+
1 row in set, 1 warning (0.00 sec)
```

各个字段的含义如下：

| **列名**      | **含义**                                     |
| ------------- | -------------------------------------------- |
| id            | SELECT 查询的序列标识符                      |
| select_type   | SELECT 关键字对应的查询类型                  |
| table         | 用到的表名                                   |
| partitions    | 匹配的分区，对于未分区的表，值为 NULL        |
| type          | 表的访问方法                                 |
| possible_keys | 可能用到的索引                               |
| key           | 实际用到的索引                               |
| key_len       | 所选索引的长度                               |
| ref           | 当使用索引等值查询时，与索引作比较的列或常量 |
| rows          | 预计要读取的行数                             |
| filtered      | 按表条件过滤后，留存的记录数的百分比         |
| Extra         | 附加信息                                     |

篇幅问题，我这里只是简单介绍了一下 MySQL 执行计划，详细介绍请看：[SQL 的执行计划](https://github.com/Snailclimb/JavaGuide/blob/main/docs/mysql-query-execution-plan.md)这篇文章。

#### 读写分离和分库分表了解吗？

读写分离和分库分表相关的问题比较多，于是，我单独写了一篇文章来介绍：[读写分离和分库分表详解](https://github.com/Snailclimb/JavaGuide/blob/main/docs/high-performance/read-and-write-separation-and-library-subtable.md)。

#### 深度分页如何优化？

[深度分页介绍及优化建议](https://github.com/Snailclimb/JavaGuide/blob/main/docs/high-performance/deep-pagination-optimization.md)

#### 数据冷热分离如何做？

[数据冷热分离详解](https://github.com/Snailclimb/JavaGuide/blob/main/docs/high-performance/data-cold-hot-separation.md)

#### MySQL 性能怎么优化？

MySQL 性能优化是一个系统性工程，涉及多个方面，在面试中不可能面面俱到。因此，建议按照“点-线-面”的思路展开，从核心问题入手，再逐步扩展，展示出你对问题的思考深度和解决能力。

**1. 抓住核心：慢 SQL 定位与分析**

性能优化的第一步永远是找到瓶颈。面试时，建议先从 **慢 SQL 定位和分析** 入手，这不仅能展示你解决问题的思路，还能体现你对数据库性能监控的熟练掌握：

- **监控工具：** 介绍常用的慢 SQL 监控工具，如 **MySQL 慢查询日志**、**Performance Schema** 等，说明你对这些工具的熟悉程度以及如何通过它们定位问题。
- **EXPLAIN 命令：** 详细说明 `EXPLAIN` 命令的使用，分析查询计划、索引使用情况，可以结合实际案例展示如何解读分析结果，比如执行顺序、索引使用情况、全表扫描等。

**2. 由点及面：索引、表结构和 SQL 优化**

定位到慢 SQL 后，接下来就要针对具体问题进行优化。 这里可以重点介绍索引、表结构和 SQL 编写规范等方面的优化技巧：

- **索引优化：** 这是 MySQL 性能优化的重点，可以介绍索引的创建原则、覆盖索引、最左前缀匹配原则等。如果能结合你项目的实际应用来说明如何选择合适的索引，会更加分一些。
- **表结构优化：** 优化表结构设计，包括选择合适的字段类型、避免冗余字段、合理使用范式和反范式设计等等。
- **SQL 优化：** 避免使用 `SELECT *`、尽量使用具体字段、使用连接查询代替子查询、合理使用分页查询、批量操作等，都是 SQL 编写过程中需要注意的细节。

**3. 进阶方案：架构优化**

当面试官对基础优化知识比较满意时，可能会深入探讨一些架构层面的优化方案。以下是一些常见的架构优化策略：

- **读写分离：** 将读操作和写操作分离到不同的数据库实例，提升数据库的并发处理能力。
- **分库分表：** 将数据分散到多个数据库实例或数据表中，降低单表数据量，提升查询效率。但要权衡其带来的复杂性和维护成本，谨慎使用。
- **数据冷热分离**：根据数据的访问频率和业务重要性，将数据分为冷数据和热数据，冷数据一般存储在低成本、低性能的介质中，热数据存储在高性能存储介质中。
- **缓存机制：** 使用 Redis 等缓存中间件，将热点数据缓存到内存中，减轻数据库压力。这个非常常用，提升效果非常明显，性价比极高！

**4. 其他优化手段**

除了慢 SQL 定位、索引优化和架构优化，还可以提及一些其他优化手段，展示你对 MySQL 性能调优的全面理解：

- **连接池配置：** 配置合理的数据库连接池（如 **连接池大小**、**超时时间** 等），能够有效提升数据库连接的效率，避免频繁的连接开销。
- **硬件配置：** 提升硬件性能也是优化的重要手段之一。使用高性能服务器、增加内存、使用 **SSD** 硬盘等硬件升级，都可以有效提升数据库的整体性能。

**5.总结**

在面试中，建议按优先级依次介绍慢 SQL 定位、[索引优化](https://github.com/Snailclimb/JavaGuide/blob/main/docs/mysql-index.md)、表结构设计和 [SQL 优化](https://github.com/Snailclimb/JavaGuide/blob/main/docs/high-performance/sql-optimization.md)等内容。架构层面的优化，如[读写分离和分库分表](https://github.com/Snailclimb/JavaGuide/blob/main/docs/high-performance/read-and-write-separation-and-library-subtable.md)、[数据冷热分离](https://github.com/Snailclimb/JavaGuide/blob/main/docs/high-performance/data-cold-hot-separation.md) 应作为最后的手段，除非在特定场景下有明显的性能瓶颈，否则不应轻易使用，因其引入的复杂性会带来额外的维护成本。

### 【MySQL 学习资料推荐】

#### MySQL 学习资料推荐

[**书籍推荐**](https://github.com/Snailclimb/JavaGuide/blob/main/docs/books/database.md#mysql) 。

**文章推荐** :

- [一树一溪的 MySQL 系列教程](https://mp.weixin.qq.com/mp/appmsgalbum?__biz=Mzg3NTc3NjM4Nw==&action=getalbum&album_id=2372043523518300162&scene=173&from_msgid=2247484308&from_itemidx=1&count=3&nolastread=1#wechat_redirect)
- [Yes 的 MySQL 系列教程](https://mp.weixin.qq.com/mp/appmsgalbum?__biz=MzkxNTE3NjQ3MA==&action=getalbum&album_id=1903249596194095112&scene=173&from_msgid=2247490365&from_itemidx=1&count=3&nolastread=1#wechat_redirect)
- [写完这篇 我的 SQL 优化能力直接进入新层次 - 变成派大星 - 2022](https://juejin.cn/post/7161964571853815822)
- [两万字详解！InnoDB 锁专题！ - 捡田螺的小男孩 - 2022](https://juejin.cn/post/7094049650428084232)
- [MySQL 的自增主键一定是连续的吗？ - 飞天小牛肉 - 2022](https://mp.weixin.qq.com/s/qci10h9rJx_COZbHV3aygQ)
- [深入理解 MySQL 索引底层原理 - 腾讯技术工程 - 2020](https://zhuanlan.zhihu.com/p/113917726)

#### 参考

- 《高性能 MySQL》第 7 章 MySQL 高级特性
- 《MySQL 技术内幕 InnoDB 存储引擎》第 6 章 锁
- Relational Database：
- 一篇文章看懂 mysql 中 varchar 能存多少汉字、数字，以及 varchar(100)和 varchar(10)的区别：
- 技术分享 | 隔离级别：正确理解幻读：
- MySQL Server Logs - MySQL 5.7 Reference Manual：
- Redo Log - MySQL 5.7 Reference Manual：
- Locking Reads - MySQL 5.7 Reference Manual：
- 深入理解数据库行锁与表锁 
- 详解 MySQL InnoDB 中意向锁的作用：
- 深入剖析 MySQL 自增锁：
- 在数据库中不可重复读和幻读到底应该怎么分？：

<!-- @include: @article-footer.snippet.md -->

## 消息队列

> Kafka / RocketMQ / RabbitMQ 的可靠性、顺序、幂等与选型（77 题）

### 【Kafka 基础】

#### Kafka 是什么？主要应用场景有哪些？

Kafka 是一个分布式流式处理平台。这到底是什么意思呢？

流平台具有三个关键功能：

1. **消息队列**：发布和订阅消息流，这个功能类似于消息队列，这也是 Kafka 也被归类为消息队列的原因。
2. **容错的持久方式存储记录消息流**：Kafka 会把消息持久化到磁盘，有效避免了消息丢失的风险。
3. **流式处理平台：** 在消息发布的时候进行处理，Kafka 提供了一个完整的流式处理类库。

Kafka 主要有两大应用场景：

1. **消息队列**：建立实时流数据管道，以可靠地在系统或应用程序之间获取数据。
2. **数据处理：** 构建实时的流数据处理程序来转换或处理数据流。

#### 和其他消息队列相比,Kafka 的优势在哪里？

我们现在经常提到 Kafka 的时候就已经默认它是一个非常优秀的消息队列了，我们也会经常拿它跟 RocketMQ、RabbitMQ 对比。我觉得 Kafka 相比其他消息队列主要的优势如下：

1. **极致的性能**：基于 Scala 和 Java 语言开发，设计中大量使用了批量处理和异步的思想，最高可以每秒处理千万级别的消息。
2. **生态系统兼容性无可匹敌**：Kafka 与周边生态系统的兼容性是最好的没有之一，尤其在大数据和流计算领域。

实际上在早期的时候 Kafka 并不是一个合格的消息队列，早期的 Kafka 在消息队列领域就像是一个衣衫褴褛的孩子一样，功能不完备并且有一些小问题比如丢失消息、不保证消息可靠性等等。当然，这也和 LinkedIn 最早开发 Kafka 用于处理海量的日志有很大关系，哈哈哈，人家本来最开始就不是为了作为消息队列滴，谁知道后面误打误撞在消息队列领域占据了一席之地。

随着后续的发展，这些短板都被 Kafka 逐步修复完善。所以，**Kafka 作为消息队列不可靠这个说法已经过时！**

#### 队列模型了解吗？Kafka 的消息模型知道吗？

> 题外话：早期的 JMS 和 AMQP 属于消息服务领域权威组织所做的相关的标准，我在 [JavaGuide](https://github.com/Snailclimb/JavaGuide)的 [《消息队列其实很简单》](https://github.com/Snailclimb/JavaGuide#%E6%95%B0%E6%8D%AE%E9%80%9A%E4%BF%A1%E4%B8%AD%E9%97%B4%E4%BB%B6)这篇文章中介绍过。但是，这些标准的进化跟不上消息队列的演进速度，这些标准实际上已经属于废弃状态。所以，可能存在的情况是：不同的消息队列都有自己的一套消息模型。

#### 队列模型：早期的消息模型

![队列模型](images/_E9_98_9F_E5_88_97_E6_A8_A1_E5_9E_8B23-109f70ce.png)

**使用队列（Queue）作为消息通信载体，满足生产者与消费者模式，一条消息只能被一个消费者使用，未被消费的消息在队列中保留直到被消费或超时。** 比如：我们生产者发送 100 条消息的话，两个消费者来消费一般情况下两个消费者会按照消息发送的顺序各自消费一半（也就是你一个我一个的消费。）

**队列模型存在的问题：**

假如我们存在这样一种情况：我们需要将生产者产生的消息分发给多个消费者，并且每个消费者都能接收到完整的消息内容。

这种情况，队列模型就不好解决了。很多比较杠精的人就说：我们可以为每个消费者创建一个单独的队列，让生产者发送多份。这是一种非常愚蠢的做法，浪费资源不说，还违背了使用消息队列的目的。

#### 发布-订阅模型:Kafka 消息模型

发布-订阅模型主要是为了解决队列模型存在的问题。

![发布订阅模型](images/_E5_8F_91_E5_B8_83_E8_AE_A2_E9_98_85_E6_A8_A1_E5_9E_8B-4648478c.png)

发布订阅模型（Pub-Sub） 使用**主题（Topic）** 作为消息通信载体，类似于**广播模式**；发布者发布一条消息，该消息通过主题传递给所有的订阅者，**在一条消息广播之后才订阅的用户则是收不到该条消息的**。

**在发布 - 订阅模型中，如果只有一个订阅者，那它和队列模型就基本是一样的了。所以说，发布 - 订阅模型在功能层面上是可以兼容队列模型的。**

**Kafka 采用的就是发布 - 订阅模型。**

> **RocketMQ 的消息模型和 Kafka 基本是完全一样的。唯一的区别是 Kafka 中没有队列这个概念，与之对应的是 Partition（分区）。**

### 【Kafka 核心概念】

#### 什么是 Producer、Consumer、Broker、Topic、Partition？

Kafka 将生产者发布的消息发送到 **Topic（主题）** 中，需要这些消息的消费者可以订阅这些 **Topic（主题）**，如下图所示：

上面这张图也为我们引出了，Kafka 比较重要的几个概念：

1. **Producer（生产者）** : 产生消息的一方。
2. **Consumer（消费者）** : 消费消息的一方。
3. **Broker（代理）** : 可以看作是一个独立的 Kafka 实例。多个 Kafka Broker 组成一个 Kafka Cluster。

同时，你一定也注意到每个 Broker 中又包含了 Topic 以及 Partition 这两个重要的概念：

- **Topic（主题）** : Producer 将消息发送到特定的主题，Consumer 通过订阅特定的 Topic(主题) 来消费消息。
- **Partition（分区）** : Partition 属于 Topic 的一部分。一个 Topic 可以有多个 Partition ，并且同一 Topic 下的 Partition 可以分布在不同的 Broker 上，这也就表明一个 Topic 可以横跨多个 Broker 。这正如我上面所画的图一样。

> 划重点：**Kafka 中的 Partition（分区） 实际上可以对应成为消息队列中的队列。这样是不是更好理解一点？**

#### Kafka 的多副本机制了解吗？带来了什么好处？

还有一点我觉得比较重要的是 Kafka 为分区（Partition）引入了多副本（Replica）机制。分区（Partition）中的多个副本之间会有一个叫做 leader 的家伙，其他副本称为 follower。我们发送的消息会被发送到 leader 副本，然后 follower 副本才能从 leader 副本中拉取消息进行同步。

> 生产者和消费者只与 leader 副本交互。你可以理解为其他副本只是 leader 副本的拷贝，它们的存在只是为了保证消息存储的安全性。当 leader 副本发生故障时会从 follower 中选举出一个 leader,但是 follower 中如果有和 leader 同步程度达不到要求的参加不了 leader 的竞选。

**Kafka 的多分区（Partition）以及多副本（Replica）机制有什么好处呢？**

1. Kafka 通过给特定 Topic 指定多个 Partition, 而各个 Partition 可以分布在不同的 Broker 上, 这样便能提供比较好的并发能力（负载均衡）。
2. Partition 可以指定对应的 Replica 数, 这也极大地提高了消息存储的安全性, 提高了容灾能力，不过也相应的增加了所需要的存储空间。

### 【ZooKeeper 和 Kafka】

#### ZooKeeper 在 Kafka 中的作用是什么？

> 要想搞懂 zookeeper 在 Kafka 中的作用 一定要自己搭建一个 Kafka 环境然后自己进 zookeeper 去看一下有哪些文件夹和 Kafka 有关，每个节点又保存了什么信息。 一定不要光看不实践，这样学来的也终会忘记！这部分内容参考和借鉴了这篇文章： 。

下图就是我的本地 ZooKeeper，它成功和我本地的 Kafka 关联上（以下文件夹结构借助 idea 插件 ZooKeeper tool 实现）。

![ZooKeeper 中与 Kafka 相关的节点信息](images/zookeeper-kafka-cb4e2468.jpg)

ZooKeeper 主要为 Kafka 提供元数据的管理的功能。

从图中我们可以看出，ZooKeeper 主要为 Kafka 做了下面这些事情：

1. **Broker 注册**：在 ZooKeeper 上会有一个专门**用来进行 Broker 服务器列表记录**的节点。每个 Broker 在启动时，都会到 ZooKeeper 上进行注册，即到 `/brokers/ids` 下创建属于自己的节点。每个 Broker 就会将自己的 IP 地址和端口等信息记录到该节点中去
2. **Topic 注册**：在 Kafka 中，同一个**Topic 的消息会被分成多个分区**并将其分布在多个 Broker 上，**这些分区信息及与 Broker 的对应关系**也都是由 ZooKeeper 在维护。比如我创建了一个名字为 my-topic 的主题并且它有两个分区，对应到 ZooKeeper 中会创建这些文件夹：`/brokers/topics/my-topic/Partitions/0`、`/brokers/topics/my-topic/Partitions/1`
3. **负载均衡**：上面也说过了 Kafka 通过给特定 Topic 指定多个 Partition, 而各个 Partition 可以分布在不同的 Broker 上, 这样便能提供比较好的并发能力。 对于同一个 Topic 的不同 Partition，Kafka 会尽力将这些 Partition 分布到不同的 Broker 服务器上。当生产者产生消息后也会尽量投递到不同 Broker 的 Partition 里面。当 Consumer 消费的时候，ZooKeeper 可以根据当前的 Partition 数量以及 Consumer 数量来实现动态负载均衡。
4. ……

#### 使用 Kafka 能否不引入 ZooKeeper？

在 Kafka 2.8 之前，Kafka 最被大家诟病的就是其重度依赖于 ZooKeeper。Kafka 2.8 引入了基于 Raft 协议的 KRaft 模式，但当时还属于 Early Access；Kafka 3.3.x 开始，KRaft 面向新集群被标记为生产可用；Kafka 4.0 起，ZooKeeper 模式已经移除，Kafka 只支持 KRaft 模式。

不过，要提示一下：老集群从 ZooKeeper 模式迁移到 KRaft 模式需要按官方迁移流程执行，不能简单改配置重启。新集群建议优先按官方当前推荐模式部署。

### 【Kafka 消费顺序、消息丢失和重复消费】

#### Kafka 如何保证消息的消费顺序？

我们在使用消息队列的过程中经常有业务场景需要严格保证消息的消费顺序，比如我们同时发了 2 个消息，这 2 个消息对应的操作分别对应的数据库操作是：

1. 更改用户会员等级。
2. 根据会员等级计算订单价格。

假如这两条消息的消费顺序不一样造成的最终结果就会截然不同。

我们知道 Kafka 中 Partition(分区)是真正保存消息的地方，我们发送的消息都被放在了这里。而我们的 Partition(分区) 又存在于 Topic(主题) 这个概念中，并且我们可以给特定 Topic 指定多个 Partition。

每次添加消息到 Partition(分区) 的时候都会采用尾加法，如上图所示。 **Kafka 只能为我们保证 Partition(分区) 中的消息有序。**

> 消息在被追加到 Partition(分区)的时候都会分配一个特定的偏移量（offset）。Kafka 通过偏移量（offset）来保证消息在分区内的顺序性。

所以，我们就有一种很简单的保证消息消费顺序的方法：**1 个 Topic 只对应一个 Partition**。这样当然可以解决问题，但是破坏了 Kafka 的设计初衷。

Kafka 中发送 1 条消息的时候，可以指定 topic, partition, key,data（数据） 4 个参数。如果你发送消息的时候指定了 Partition 的话，所有消息都会被发送到指定的 Partition。并且，同一个 key 的消息可以保证只发送到同一个 partition，这个我们可以采用表/对象的 id 来作为 key 。

总结一下，对于如何保证 Kafka 中消息消费的顺序，有了下面两种方法：

1. 1 个 Topic 只对应一个 Partition。
2. （推荐）发送消息的时候指定 key/Partition。

当然不仅仅只有上面两种方法，上面两种方法是我觉得比较好理解的。

顺序消费还要注意两个边界：

- **只能保证同一分区内有序**：多个分区之间天然并行，不保证全局顺序。
- **失败重试可能打乱业务效果**：如果某条消息处理失败，而后续消息已经被处理，业务层仍然需要状态机或版本号兜底。

所以，生产上通常是“同一业务 key 进同一分区 + 单分区内顺序消费 + 消费端幂等/状态机校验”一起使用。

#### Kafka 如何保证消息不丢失？

#### 生产者丢失消息的情况

生产者(Producer) 调用`send`方法发送消息之后，消息可能因为网络问题并没有发送过去。

所以，我们不能默认在调用`send`方法发送消息之后消息发送成功了。为了确定消息是发送成功，我们要判断消息发送的结果。但是要注意的是 Kafka 生产者(Producer) 使用 `send` 方法发送消息实际上是异步的操作，我们可以通过 `get()`方法获取调用结果，但是这样也让它变为了同步操作，示例代码如下：

> **详细代码见我的这篇文章：[Kafka 系列第三篇！10 分钟学会如何在 Spring Boot 程序中使用 Kafka 作为消息队列?](https://mp.weixin.qq.com/s?__biz=Mzg2OTA0Njk0OA==&mid=2247486269&idx=2&sn=ec00417ad641dd8c3d145d74cafa09ce&chksm=cea244f6f9d5cde0c8eb233fcc4cf82e11acd06446719a7af55230649863a3ddd95f78d111de&token=1633957262&lang=zh_CN#rd)**

```java
SendResult sendResult = kafkaTemplate.send(topic, o).get();
if (sendResult.getRecordMetadata() != null) {
  logger.info("生产者成功发送消息到" + sendResult.getProducerRecord().topic() + "-> " + sendRe
              sult.getProducerRecord().value().toString());
}
```

但是一般不推荐这么做！可以采用为其添加回调函数的形式，示例代码如下：

```java
        ListenableFuture> future = kafkaTemplate.send(topic, o);
        future.addCallback(result -> logger.info("生产者成功发送消息到topic:{} partition:{}的消息", result.getRecordMetadata().topic(), result.getRecordMetadata().partition()),
                ex -> logger.error("生产者发送消失败，原因：{}", ex.getMessage()));
```

如果消息发送失败的话，我们检查失败的原因之后重新发送即可！

另外，这里推荐为 Producer 的`retries`（重试次数）设置一个比较合理的值，一般是 3 ，但是为了保证消息不丢失的话一般会设置比较大一点。设置完成之后，当出现网络问题之后能够自动重试消息发送，避免消息丢失。另外，建议还要设置重试间隔，因为间隔太小的话重试的效果就不明显了，网络波动一次你 3 次一下子就重试完了。

#### 消费者丢失消息的情况

我们知道消息在被追加到 Partition(分区)的时候都会分配一个特定的偏移量（offset）。偏移量（offset)表示 Consumer 当前消费到的 Partition(分区)的所在的位置。Kafka 通过偏移量（offset）可以保证消息在分区内的顺序性。

![kafka offset](images/kafka-offset-c3444a1d.jpg)

当消费者拉取到了分区的某个消息之后，消费者会自动提交了 offset。自动提交的话会有一个问题，试想一下，当消费者刚拿到这个消息准备进行真正消费的时候，突然挂掉了，消息实际上并没有被消费，但是 offset 却被自动提交了。

**解决办法也比较粗暴，我们手动关闭自动提交 offset，每次在真正消费完消息之后再自己手动提交 offset 。** 但是，细心的朋友一定会发现，这样会带来消息被重新消费的问题。比如你刚刚消费完消息之后，还没提交 offset，结果自己挂掉了，那么这个消息理论上就会被消费两次。

#### Kafka 弄丢了消息

我们知道 Kafka 为分区（Partition）引入了多副本（Replica）机制。分区（Partition）中的多个副本之间会有一个叫做 leader 的家伙，其他副本称为 follower。我们发送的消息会被发送到 leader 副本，然后 follower 副本才能从 leader 副本中拉取消息进行同步。生产者和消费者只与 leader 副本交互。你可以理解为其他副本只是 leader 副本的拷贝，它们的存在只是为了保证消息存储的安全性。

**试想一种情况：假如 leader 副本所在的 broker 突然挂掉，那么就要从 follower 副本重新选出一个 leader ，但是 leader 的数据还有一些没有被 follower 副本的同步的话，就会造成消息丢失。**

**设置 acks = all**

解决办法就是我们设置 **acks = all**。acks 是 Kafka 生产者(Producer) 很重要的一个参数。

acks 的默认值即为 1，代表我们的消息被 leader 副本接收之后就算被成功发送。当我们配置 **acks = all** 表示只有所有 ISR 列表的副本全部收到消息时，生产者才会接收到来自服务器的响应. 这种模式是最高级别的，也是最安全的，可以确保不止一个 Broker 接收到了消息. 该模式的延迟会很高.

**设置 replication.factor >= 3**

为了保证 leader 副本能有 follower 副本能同步消息，我们一般会为 topic 设置 **replication.factor >= 3**。这样就可以保证每个 分区(partition) 至少有 3 个副本。虽然造成了数据冗余，但是带来了数据的安全性。

**设置 min.insync.replicas > 1**

一般情况下我们还需要设置 **min.insync.replicas> 1** ，这样配置代表消息至少要被写入到 2 个副本才算是被成功发送。**min.insync.replicas** 的默认值为 1 ，在实际生产中应尽量避免默认值 1。

但是，为了保证整个 Kafka 服务的高可用性，你需要确保 **replication.factor > min.insync.replicas** 。为什么呢？设想一下假如两者相等的话，只要是有一个副本挂掉，整个分区就无法正常工作了。这明显违反高可用性！一般推荐设置成 **replication.factor = min.insync.replicas + 1**。

**设置 unclean.leader.election.enable = false**

> **Kafka 0.11.0.0 版本开始 unclean.leader.election.enable 参数的默认值由原来的 true 改为 false**

我们最开始也说了我们发送的消息会被发送到 leader 副本，然后 follower 副本才能从 leader 副本中拉取消息进行同步。多个 follower 副本之间的消息同步情况不一样，当我们配置了 **unclean.leader.election.enable = false** 的话，当 leader 副本发生故障时就不会从 follower 副本中和 leader 同步程度达不到要求的副本中选择出 leader ，这样降低了消息丢失的可能性。

生产环境还建议同时关注生产者端配置：

- 开启幂等生产者，避免生产者重试导致重复写入同一分区。
- 合理设置 `delivery.timeout.ms`、`request.timeout.ms` 和 `linger.ms`，在可靠性、延迟和吞吐之间取舍。
- 对关键业务消息记录发送失败日志或本地消息表，方便后续补偿。

Kafka 的可靠性不是某一个参数决定的，而是 Topic 副本、ISR、Producer ACK、Consumer offset 提交时机和业务幂等一起决定的。

#### Kafka 如何保证消息不重复消费？

**kafka 出现消息重复消费的原因：**

- 服务端侧已经消费的数据没有成功提交 offset（根本原因）。
- Kafka 侧 由于服务端处理业务时间长或者网络链接等等原因让 Kafka 认为服务假死，触发了分区 rebalance。

**解决方案：**

- 消费消息服务做幂等校验，比如 Redis 的 set、MySQL 的主键等天然的幂等功能。这种方法最有效。
- 将 **`enable.auto.commit`** 参数设置为 false，关闭自动提交，开发者在代码中手动提交 offset。那么这里会有个问题：**什么时候提交 offset 合适？**
  - 处理完消息再提交：依旧有消息重复消费的风险，和自动提交一样
  - 拉取到消息即提交：会有消息丢失的风险。允许消息延时的场景，一般会采用这种方式。然后，通过定时任务在业务不繁忙（比如凌晨）的时候做数据兜底。

### 【Rebalance 有什么风险？如何减少影响？】

#### Rebalance 有什么风险？如何减少影响？

Consumer Group 中消费者数量变化、订阅 Topic 变化、消费者长时间没有发送心跳，都可能触发 Rebalance。Rebalance 期间，分区会被重新分配，部分消费者会暂停消费，严重时会造成消费抖动和重复消费。

常见优化思路：

- 控制消费者实例的频繁上下线，发布时尽量滚动、分批。
- 合理设置 `max.poll.interval.ms`，避免单批消息处理太久导致消费者被踢出组。
- 控制单次拉取数量，避免一次拉太多导致处理时间超过心跳或 poll 间隔。
- 使用静态成员或更平滑的分区分配策略，减少不必要的分区迁移。
- 消费端必须幂等，因为 Rebalance 前后 offset 提交和业务处理之间仍然可能出现重复。

面试里如果被问到 Rebalance，不要只说“消费者重新分配分区”。更关键的是讲清楚它会带来短暂停顿、重复消费风险，以及如何通过参数、发布策略和幂等设计降低影响。

### 【Kafka 重试机制】

#### 消费失败会怎么样？

在消费过程中，当其中一个消息消费异常时，会不会卡住后续队列消息的消费？这样业务岂不是卡住了？

生产者代码：

```Java
 for (int i = 0; i < 10; i++) {
   kafkaTemplate.send(KafkaConst.TEST_TOPIC, String.valueOf(i))
 }
```

消费者消代码：

```Java
   @KafkaListener(topics = {KafkaConst.TEST_TOPIC},groupId = "apple")
   private void customer(String message) throws InterruptedException {
       log.info("kafka customer:{}",message);
       Integer n = Integer.parseInt(message);
       if (n%5==0){
           throw new  RuntimeException();
       }
   }
```

在默认配置下，当消费异常会进行重试，重试多次后会跳过当前消息，继续进行后续消息的消费，不会一直卡在当前消息。下面是一段消费的日志，可以看出当 `test-0@95` 重试多次后会被跳过。

```Java
2023-08-10 12:03:32.918 DEBUG 9700 --- [ntainer#0-0-C-1] o.s.kafka.listener.DefaultErrorHandler   : Skipping seek of: test-0@95
2023-08-10 12:03:32.918 TRACE 9700 --- [ntainer#0-0-C-1] o.s.kafka.listener.DefaultErrorHandler   : Seeking: test-0 to: 96
2023-08-10 12:03:32.918  INFO 9700 --- [ntainer#0-0-C-1] o.a.k.clients.consumer.KafkaConsumer     : [Consumer clientId=consumer-apple-1, groupId=apple] Seeking to offset 96 for partition test-0

```

因此，即使某个消息消费异常，Kafka 消费者仍然能够继续消费后续的消息，不会一直卡在当前消息，保证了业务的正常进行。

#### 默认会重试多少次？

默认配置下，消费异常会进行重试，重试次数是多少, 重试是否有时间间隔？

看源码 `FailedRecordTracker` 类有个 `recovered` 函数，返回 Boolean 值判断是否要进行重试，下面是这个函数中判断是否重试的逻辑：

```java
	@Override
	public boolean recovered(ConsumerRecord<?, ?> record, Exception exception,
	    @Nullable MessageListenerContainer container,
	    @Nullable Consumer<?, ?> consumer) throws InterruptedException {

	    if (this.noRetries) {
         // 不支持重试
	        attemptRecovery(record, exception, null, consumer);
	        return true;
	    }
     // 取已经失败的消费记录集合
	    Map < TopicPartition, FailedRecord > map = this.failures.get();
	    if (map == null) {
	        this.failures.set(new HashMap < > ());
	        map = this.failures.get();
	    }
     //  获取消费记录所在的Topic和Partition
	    TopicPartition topicPartition = new TopicPartition(record.topic(), record.partition());
	    FailedRecord failedRecord = getFailedRecordInstance(record, exception, map, topicPartition);
     // 通知注册的重试监听器，消息投递失败
	    this.retryListeners.forEach(rl - >
	        rl.failedDelivery(record, exception, failedRecord.getDeliveryAttempts().get()));
	    // 获取下一次重试的时间间隔
    long nextBackOff = failedRecord.getBackOffExecution().nextBackOff();
	    if (nextBackOff != BackOffExecution.STOP) {
	        this.backOffHandler.onNextBackOff(container, exception, nextBackOff);
	        return false;
	    } else {
	        attemptRecovery(record, exception, topicPartition, consumer);
	        map.remove(topicPartition);
	        if (map.isEmpty()) {
	            this.failures.remove();
	        }
	        return true;
	    }
	}
```

其中， `BackOffExecution.STOP` 的值为 -1。

```java
@FunctionalInterface
public interface BackOffExecution {

	long STOP = -1;
	long nextBackOff();

}
```

`nextBackOff` 的值调用 `BackOff` 类的 `nextBackOff()` 函数。如果当前执行次数大于最大执行次数则返回 `STOP`，既超过这个最大执行次数后才会停止重试。

```Java
public long nextBackOff() {
  this.currentAttempts++;
  if (this.currentAttempts <= getMaxAttempts()) {
    return getInterval();
  }
  else {
    return STOP;
  }
}
```

那么这个 `getMaxAttempts` 的值又是多少呢？回到最开始，当执行出错会进入 `DefaultErrorHandler` 。`DefaultErrorHandler` 默认的构造函数是：

```Java
public DefaultErrorHandler() {
  this(null, SeekUtils.DEFAULT_BACK_OFF);
}
```

`SeekUtils.DEFAULT_BACK_OFF` 定义的是:

```Java
public static final int DEFAULT_MAX_FAILURES = 10;

public static final FixedBackOff DEFAULT_BACK_OFF = new FixedBackOff(0, DEFAULT_MAX_FAILURES - 1);
```

`DEFAULT_MAX_FAILURES` 的值是 10，`currentAttempts` 从 0 到 9，所以总共会执行 10 次，每次重试的时间间隔为 0。

最后，简单总结一下：Kafka 消费者在默认配置下会进行最多 10 次 的重试，每次重试的时间间隔为 0，即立即进行重试。如果在 10 次重试后仍然无法成功消费消息，则不再进行重试，消息将被视为消费失败。

#### 如何自定义重试次数以及时间间隔?

从上面的代码可以知道，默认错误处理器的重试次数以及时间间隔是由 `FixedBackOff` 控制的，`FixedBackOff` 是 `DefaultErrorHandler` 初始化时默认的。所以自定义重试次数以及时间间隔，只需要在 `DefaultErrorHandler` 初始化的时候传入自定义的 `FixedBackOff` 即可。重新实现一个 `KafkaListenerContainerFactory` ，调用 `setCommonErrorHandler` 设置新的自定义的错误处理器就可以实现。

```Java
@Bean
public KafkaListenerContainerFactory kafkaListenerContainerFactory(ConsumerFactory consumerFactory) {
    ConcurrentKafkaListenerContainerFactory factory = new ConcurrentKafkaListenerContainerFactory();
    // 自定义重试时间间隔以及次数
    FixedBackOff fixedBackOff = new FixedBackOff(1000, 5);
    factory.setCommonErrorHandler(new DefaultErrorHandler(fixedBackOff));
    factory.setConsumerFactory(consumerFactory);
    return factory;
}
```

#### 如何在重试失败后进行告警?

自定义重试失败后逻辑，需要手动实现，以下是一个简单的例子，重写 `DefaultErrorHandler` 的 `handleRemaining` 函数，加上自定义的告警等操作。

```Java
@Slf4j
public class DelErrorHandler extends DefaultErrorHandler {

    public DelErrorHandler(FixedBackOff backOff) {
        super(null,backOff);
    }

    @Override
    public void handleRemaining(Exception thrownException, List> records, Consumer<?, ?> consumer, MessageListenerContainer container) {
        super.handleRemaining(thrownException, records, consumer, container);
        log.info("重试多次失败");
        // 自定义操作
    }
}
```

`DefaultErrorHandler` 只是默认的一个错误处理器，Spring Kafka 还提供了 `CommonErrorHandler` 接口。手动实现 `CommonErrorHandler` 就可以实现更多的自定义操作，有很高的灵活性。例如根据不同的错误类型，实现不同的重试逻辑以及业务逻辑等。

#### 重试失败后的数据如何再次处理?

当达到最大重试次数后，数据会直接被跳过，继续向后进行。当代码修复后，如何重新消费这些重试失败的数据呢？

**死信队列（Dead Letter Queue，简称 DLQ）** 是消息中间件中的一种特殊队列。它主要用于处理无法被消费者正确处理的消息，通常是因为消息格式错误、处理失败、消费超时等情况导致的消息被“丢弃”或“死亡”的情况。当消息进入队列后，消费者会尝试处理它。如果处理失败，或者超过一定的重试次数仍无法被成功处理，消息可以发送到死信队列中，而不是被永久性地丢弃。在死信队列中，可以进一步分析、处理这些无法正常消费的消息，以便定位问题、修复错误，并采取适当的措施。

`@RetryableTopic` 是 Spring Kafka 中的一个注解,它用于配置某个 Topic 支持消息重试，更推荐使用这个注解来完成重试。

```Java
// 重试 5 次，重试间隔 100 毫秒,最大间隔 1 秒
@RetryableTopic(
        attempts = "5",
        backoff = @Backoff(delay = 100, maxDelay = 1000)
)
@KafkaListener(topics = {KafkaConst.TEST_TOPIC}, groupId = "apple")
private void customer(String message) {
    log.info("kafka customer:{}", message);
    Integer n = Integer.parseInt(message);
    if (n % 5 == 0) {
        throw new RuntimeException();
    }
    System.out.println(n);
}
```

当达到最大重试次数后，如果仍然无法成功处理消息，消息会被发送到对应的死信队列中。对于死信队列的处理，既可以用 `@DltHandler` 处理，也可以使用 `@KafkaListener` 重新消费。

#### 参考

- Kafka 官方文档：
- 极客时间—《Kafka 核心技术与实战》第 11 节：无消息丢失配置怎么实现？

<!-- @include: @article-footer.snippet.md -->

### 【消息队列扫盲】

#### 消息队列为什么会出现？

单体应用里，接口之间直接调用最省事；系统拆成多个服务后，调用链一长，同步调用就会把响应时间、故障和流量峰值一起传递下去。消息队列插在中间，先把消息存起来，让下游按自己的节奏消费。

#### 消息队列能用来干什么？

#### 异步

你可能会问，应用之间的通信又不是只能由消息队列解决，为什么中间非要插一个消息队列？直接进行通信不行吗？

这就引出了另一个概念——**同步通信**。比如业界使用较多的 Dubbo 就是一个适用于各个系统之间同步通信的 RPC 框架。

以购票系统为例，需求是用户在购买完成之后能接收到购买完成的短信通知。

我们省略中间的网络通信时间消耗，假如购票系统处理需要 150ms ，短信系统处理需要 200ms ，那么整个处理流程的时间消耗就是 150ms + 200ms = 350ms。

当然，乍看没什么问题。但仔细分析会发现问题：用户购票在购票系统处理完成时就已经完成了购买动作，而现在通过同步调用非要让整个请求时间变长。短信系统只是一个辅助功能，用于增强用户体验感，并非核心业务。整个调用流程显得 **头重脚轻**——购票是一个不太耗时的流程，但因为同步调用，必须等待发送短信这个较耗时的操作完成才能返回结果。如果再加一个发送邮件的需求呢？

这样整个系统的调用链又变长了，整个时间就变成了 550ms。

当我们在食堂排队打饭时，我们和食堂工作人员之间就是一个同步模型。

我们需要告诉工作人员：“请帮我加个鸡腿，再加个酸辣土豆丝，多打点饭”。

然后工作人员帮我们打饭配菜，我们需要等待这个过程完成。

最终我们从工作人员手中接过饭菜然后去寻找座位。

回想一下，我们在传达需求之后是 **同步等待工作人员配好饭菜** 的。如果增加更多菜品，工作人员打饭配菜的流程就会变长，我们等待的时间也会相应增加。

而在餐厅用餐时，我们告诉服务员来一碗牛肉面加个荷包蛋 **(传达一个消息)** ，然后可以在餐桌上做自己的事情 **(干自己其他事情)** ，等到牛肉面上桌我们再开始用餐。虽然做面的时间没有变短，但是我们只需要传达一个消息就可以干其他事情了，这就是 **异步** 的概念。

所以，为了解决这一个问题，聪明的程序员在中间也加了个类似于服务员的中间件——消息队列。这个时候我们就可以把模型给改造了。

这样，我们在将消息存入消息队列之后我们就可以直接返回了(我们告诉服务员我们要吃什么然后玩手机)，所以整个耗时只是 150ms + 10ms = 160ms。

> 但是你需要注意的是，整个流程的时长是没变的，就像你仅仅告诉服务员要吃什么是不会影响到做面的速度的。

#### 解耦

回到最初同步调用的过程，我们写个伪代码简单概括一下。

那么第二步，我们又添加了一个发送邮件，我们就得重新去修改代码，如果我们又加一个需求：用户购买完还需要给他加积分，这个时候我们是不是又得改代码？

如果还觉得可以接受，那么当需要移除发送邮件服务时，是不是又得改代码、又得重启应用？

这样频繁改动代码显然很麻烦，此时可以 **使用消息队列进行解耦** 。需要注意的是，后面的发送短信、发送邮件、添加积分等操作都依赖于 `result`，即购票的处理结果（如订单号、用户账号等），也就是说后续服务都需要相同的消息来进行处理。因此可以通过 **“广播消息”** 模式来实现。

这里所说的“广播”并不是真正的广播，而是下游系统作为消费者去 **订阅** 特定的主题。比如主题可以命名为 `订票`，购买系统作为生产者将消息发送到消息队列，消费者订阅该主题后，从消息队列中拉取消息并消费。在生产者端只需要关注 **生产消息到指定主题** ，**消费者只需要关注从指定主题中拉取消息** 。

> 如果没有消息队列，每当一个新的业务接入，我们都要在主系统调用新接口、或者当我们取消某些业务，我们也得在主系统删除某些接口调用。有了消息队列，我们只需要关心消息是否送达了队列，至于谁希望订阅，接下来收到消息如何处理，是下游的事情，无疑极大地减少了开发和联调的工作量。

#### 削峰

回到同步调用系统的场景，思考一下：如果此时有大量用户请求购票，整个系统会变成什么样？

假设有一万个请求进入购票系统，运行主业务的服务器配置通常较好，购票系统可以承受这一万个用户请求。但这意味着同时也会产生一万个调用短信服务的请求。短信系统并非主要业务，配备的硬件资源不会太高。此时短信系统能否承受这一万的峰值？很可能系统会 **直接崩溃** 。

短信业务并非主业务，能否 **折中处理** ？如果我们把购买完成的信息发送到消息队列中，而短信系统 **尽自己所能地去消息队列中取消息和消费消息** ，即使处理速度慢一点也无所谓，只要系统没有崩溃就可以接受。

系统可用性是最重要的，验证码短信的延迟几秒到达用户手机，通常是可以接受的。

#### 消息队列能带来什么好处？

总结起来就是三个关键词：**异步、解耦、削峰**。这不仅是消息队列的核心价值，更是分布式架构设计的重要思想。

```mermaid
flowchart LR
    subgraph MQ["消息队列三大应用场景"]
        style MQ fill:#F0F2F5,stroke:#E0E6ED,stroke-width:1.5px
        Async["异步处理"]
        Decouple["解耦"]
        Peak["削峰"]
    end

    Async --> A1["提高响应速度"]
    Async --> A2["提升用户体验"]

    Decouple --> D1["降低系统耦合"]
    Decouple --> D2["提高扩展性"]

    Peak --> P1["缓解系统压力"]
    Peak --> P2["保证系统稳定"]

    classDef app fill:#4CA497,color:#fff,rx:10,ry:10
    classDef benefit fill:#00838F,color:#fff,rx:10,ry:10

    class Async,Decouple,Peak app
    class A1,A2,D1,D2,P1,P2 benefit

    linkStyle default stroke-width:1.5px,opacity:0.8
```

#### 消息队列会带来副作用吗？

没有哪一门技术是“银弹”，消息队列也有它的副作用。

比如，本来好好的两个系统之间的调用，我中间加了个消息队列，如果消息队列挂了怎么办呢？是不是 **降低了系统的可用性** ？

那这样是不是要保证 HA(高可用)？是不是要搞集群？那么我 **整个系统的复杂度是不是上升了** ？

抛开上面的问题不讲，万一我发送方发送失败了，然后执行重试，这样就可能产生重复的消息。

或者我消费端处理失败了，请求重发，这样也会产生重复的消息。

对于一些微服务来说，消费重复消息会带来更大的麻烦，比如增加积分，这个时候我加了多次是不是对其他用户不公平？

那么，又 **如何解决重复消费消息的问题** 呢？

如果我们此时的消息需要保证严格的顺序性怎么办呢？比如生产者生产了一系列的有序消息(对一个 id 为 1 的记录进行删除增加修改)，但是我们知道在发布订阅模型中，对于主题是无顺序的，那么这个时候就会导致对于消费者消费消息的时候没有按照生产者的发送顺序消费，比如这个时候我们消费的顺序为修改删除增加，如果该记录涉及到金额的话是不是会出大事情？

那么，又 **如何解决消息的顺序消费问题** 呢？

就拿我们上面所讲的分布式系统来说，用户购票完成之后是不是需要增加账户积分？在同一个系统中我们一般会使用事务来进行解决，如果用 `Spring` 的话我们在上面伪代码中加入 `@Transactional` 注解就好了。但是在不同系统中如何保证事务呢？总不能这个系统我扣钱成功了你那积分系统积分没加吧？或者说我这扣钱明明失败了，你那积分系统给我加了积分。

那么，又如何 **解决分布式事务问题** 呢？

我们刚刚说了，消息队列可以进行削峰操作，那如果我的消费者如果消费很慢或者生产者生产消息很快，这样是不是会将消息堆积在消息队列中？

那么，又如何 **解决消息堆积的问题** 呢？

可用性降低、复杂度上升，同时还带来重复消费、顺序消费、分布式事务、消息堆积等一系列问题。这些问题如何解决？

下面我们逐一讨论这些问题的解决方案。

### 【RocketMQ 是什么？】

#### RocketMQ 是什么？

![RocketMQ 官网介绍](images/16ef383014430799-3c55e73e.jpg)

在讨论上述问题的解决方案之前，我们先来了解一下 RocketMQ 的内部构造。建议带着问题去阅读和了解。

RocketMQ 是一个基于 **Topic 的发布订阅消息系统**，Topic 下可以包含多个 MessageQueue，MessageQueue 是消息存储和传输的最小队列单元。它具有**高性能、高可靠、高实时、分布式** 的特点，采用 Java 语言开发，由阿里巴巴团队在 2016 年底贡献给 Apache，成为 Apache 顶级项目。在阿里内部，RocketMQ 很好地服务了集团大大小小上千个应用，在每年的双十一当天，更有万亿级消息通过 RocketMQ 流转。

RocketMQ 具备高吞吐、低延迟、高可用的特点，经过了双十一等大规模场景的验证。

从 RocketMQ 5.x 开始，官方更强调云原生架构：Proxy 层支持 gRPC、多语言 SDK 和多协议接入，Broker 更专注消息存储和高可用。这意味着新项目选型时，除了看传统的 NameServer、Broker、Producer、Consumer，也要关注是否需要 Proxy、gRPC SDK、Kubernetes 部署和云原生可观测能力。

### 【队列模型和主题模型是什么？】

#### 队列模型

就像我们理解队列一样，消息中间件的队列模型就真的只是一个队列。

队列模型的特点：**一个消息只能被一个消费者消费**。

```mermaid
flowchart LR
    P["生产者"] --> Q["队列"]
    Q --> C1["消费者1"]
    Q --> C2["消费者2"]

    classDef producer fill:#4CA497,color:#fff,rx:10,ry:10
    classDef queue fill:#E99151,color:#fff,rx:10,ry:10
    classDef consumer fill:#00838F,color:#fff,rx:10,ry:10

    class P producer
    class Q queue
    class C1,C2 consumer

    linkStyle default stroke-width:1.5px,opacity:0.8
```

在一开始我跟你提到了一个 **“广播”** 的概念，也就是说如果我们此时我们需要将一个消息发送给多个消费者(比如此时我需要将信息发送给短信系统和邮件系统)，这个时候单个队列即不能满足需求了。

当然你可以让 Producer 生产消息放入多个队列中，然后每个队列去对应每一个消费者。问题是可以解决，创建多个队列并且复制多份消息是会很影响资源和性能的。而且，这样子就会导致生产者需要知道具体消费者个数然后去复制对应数量的消息队列，这就违背我们消息中间件的 **解耦** 这一原则。

#### 主题模型

那么有没有好的方法去解决这一个问题呢？有，那就是 **主题模型** 或者可以称为 **发布订阅模型** 。

> 感兴趣的同学可以去了解一下设计模式里面的观察者模式并且手动实现一下，我相信你会有所收获的。

在主题模型中，消息的生产者称为 **发布者(Publisher)** ，消息的消费者称为 **订阅者(Subscriber)** ，存放消息的容器称为 **主题(Topic)** 。

其中，发布者将消息发送到指定主题中，订阅者需要 **提前订阅主题** 才能接受特定主题的消息。

主题模型的特点：**一个 Topic 可以被多个消费者组订阅，每个消费者组都有独立的消费进度**。在集群消费模式下，同一消费者组内通常只由一个消费者实例处理某条消息；在广播消费模式下，同一消费者组内的每个消费者都会收到消息。

```mermaid
flowchart LR
    P1["发布者1"] --> T["主题"]
    P2["发布者2"] --> T
    T --> S1["订阅者1"]
    T --> S2["订阅者2"]
    T --> S3["订阅者3"]

    classDef publisher fill:#4CA497,color:#fff,rx:10,ry:10
    classDef topic fill:#E99151,color:#fff,rx:10,ry:10
    classDef subscriber fill:#00838F,color:#fff,rx:10,ry:10

    class P1,P2 publisher
    class T topic
    class S1,S2,S3 subscriber

    linkStyle default stroke-width:1.5px,opacity:0.8
```

#### RocketMQ 中的消息模型

RocketMQ 中的消息模型就是按照 **主题模型** 所实现的。那么 **主题** 到底是怎么实现的呢？

其实对于主题模型的实现来说每个消息中间件的底层设计都是不一样的，就比如 Kafka 中的 **分区** ，RocketMQ 中的 **队列** ，RabbitMQ 中的 Exchange 。我们可以理解为 **主题模型/发布订阅模型** 就是一个标准，那些中间件只不过照着这个标准去实现而已。

所以，RocketMQ 中的 **主题模型** 到底是如何实现的呢？先看一张图：

我们可以看到在整个图中有 `Producer Group`、Topic、`Consumer Group` 三个角色。这个图更接近早期和兼容模型，理解 5.x 时要记住：新版领域模型里生产者本身是轻量、匿名的，生产者组不再是重点概念。

- `Producer Group` 生产者组：在早期客户端和兼容场景中代表某一类生产者，比如我们有多个秒杀系统作为生产者，这多个合在一起就是一个 `Producer Group` 生产者组，它们一般生产相同的消息。
- `Consumer Group` 消费者组：代表某一类的消费者，比如我们有多个短信系统作为消费者，这多个合在一起就是一个 `Consumer Group` 消费者组，它们一般消费相同的消息。
- Topic 主题：代表一类消息，比如订单消息，物流消息等等。

你可以看到图中生产者组中的生产者会向主题发送消息，而 **主题中存在多个队列**，生产者每次生产消息之后会把消息发送到指定主题下的某个队列。

每个主题中都有多个队列(分布在不同的 Broker 中，如果是集群的话，Broker 又分布在不同的服务器中)，集群消费模式下，一个消费者集群多台机器共同消费一个 `topic` 的多个队列。

**负载均衡策略对比**

下面对比的是**同一消费者组内的集群消费（共享消费）**。负载均衡粒度取决于客户端类型和消费协议，不能只看 Broker 的版本：传统 3.x/4.x Remoting SDK 的消费者采用队列粒度；5.x 新版 SDK 的 PushConsumer、SimpleConsumer 采用消息粒度；PullConsumer 仍采用队列粒度。

```mermaid
flowchart TB
    subgraph Queue["队列粒度：3 个队列，4 个消费者"]
        style Queue fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        direction TB
        Q1["队列1"] --> C1["消费者1"]
        Q2["队列2"] --> C2["消费者2"]
        Q3["队列3"] --> C3["消费者3"]
        C4["消费者4(无队列可分配)"]
    end

    subgraph Message["消息粒度：同一队列的不同普通消息由组内消费者分担"]
        style Message fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        direction TB
        MQ1["队列1"] --> MC1["消费者1消费消息1"]
        MQ1 --> MC2["消费者2消费消息2"]
        MQ1 --> MC3["消费者3消费消息3"]
    end

    classDef queue fill:#4CA497,color:#fff,rx:10,ry:10
    classDef consumer4x fill:#E99151,color:#fff,rx:10,ry:10
    classDef consumer5x fill:#00838F,color:#fff,rx:10,ry:10

    class Q1,Q2,Q3,MQ1 queue
    class C1,C2,C3,C4 consumer4x
    class MC1,MC2,MC3 consumer5x

    linkStyle default stroke-width:1.5px,opacity:0.8
```

- **队列粒度负载均衡**：在分配稳定时，同一消费者组内，一个队列只分配给一个消费者实例；一个消费者可以分到多个队列。如果某个消费者挂掉，会通过重平衡把它的队列分配给组内其他消费者。如果消费者数多于队列数，就会有消费者分不到队列。这种模式容易出现负载不均：某个消费者处理速度较慢，或者分到的队列消息较多，就可能出现该消费者积压、其他消费者空闲的情况。不同消费者组可以分别消费同一个队列，不受组内独占分配的限制。
- **消息粒度负载均衡**：5.x 新版 SDK 的 PushConsumer、SimpleConsumer 可以让同一消费者组内的多个消费者分担同一个队列中的不同消息。图中只是一次分配示例，消息不会固定绑定到某个消费者。消息被取走后，在不可见时间内不会再投递给**同组**其他消费者；消费失败或超时仍可能触发重试，因此不代表绝不会重复消费。这种方式可以缓解队列分配不均和消费者处理能力差异造成的积压，但不能消除业务处理慢等所有瓶颈。顺序消息还受消息组顺序约束，不能把同一消息组内的消息任意并行处理。

下面这张图仅适用于**队列粒度负载均衡**。消费者个数小于队列个数并不是问题，一个消费者可以消费多个队列；如果希望扩容后的消费者都能分到队列，就需要有足够的队列。消息粒度负载均衡下，消费者实例数则不受队列数的直接限制。

**为什么不同消费者组要分别记录每个队列的消费进度？**

因为不同消费者组订阅同一个 Topic 时，需要各自消费这些消息，消费速度也可能不同。以传统队列粒度的集群消费为例，消费位点按 **消费者组 + Topic + 队列** 分别记录，组内消费者共享该进度；发生重平衡时，接手队列的消费者可以从已提交的位点继续消费。

消费位点（ConsumerOffset）表示该组在该队列上下一次继续消费的位置。它不是消息 ID，也不是整个 Topic 共用的序号。下面假设两个组订阅同一个 Topic，没有过滤和重试，消息按队列顺序消费并已提交位点：

| 消费者组 | 队列 Q0 的消费进度                        | 队列 Q1 的消费进度                        |
| -------- | ----------------------------------------- | ----------------------------------------- |
| Group A  | offset 为 3：已消费 0～2，下一条从 3 开始 | offset 为 1：已消费 0，下一条从 1 开始    |
| Group B  | offset 为 1：已消费 0，下一条从 1 开始    | offset 为 4：已消费 0～3，下一条从 4 开始 |

Q0 和 Q1 的 offset 分别在各自队列内递增。Group A 推进 Q0 的位点，不会改变 Group B 的位点，也不会改变自身 Q1 的位点。

**位点更新不能简单理解为“每成功一条就加一”，也不能保证不重复消费。** 批量拉取、并发处理、消息过滤和位点提交都会影响进度的推进；例如前面的消息还没处理完，后面的消息即使先完成，也不能直接越过前面的消息提交进度。消费已成功但位点尚未持久化时发生故障，就可能再次消费。5.x 新版 SDK 的 PushConsumer、SimpleConsumer 通过逐条消息确认，由服务端管理消费状态，也不能套用“客户端每成功一条就将 offset 加一”的解释。

消息被某个组消费成功后不会立即从存储中删除，也不是必须等所有组都消费完才删除。RocketMQ 按保存时间、存储空间等清理策略回收消息，未消费的消息也可能被清理。消费进度管理、消息保留和业务幂等是不同的问题。

参考官方文档：[消费者负载均衡](https://rocketmq.apache.org/zh/docs/featureBehavior/08consumerloadbalance/)、[消费进度管理](https://rocketmq.apache.org/zh/docs/featureBehavior/09consumerprogress/)、[消息存储和清理机制](https://rocketmq.apache.org/zh/docs/featureBehavior/11messagestorepolicy/)。

可能你还有一个问题，**为什么一个主题中需要维护多个队列** ？

答案是 **提高并发能力**。每个主题中只存在一个队列也是可行的，不同消费者组仍可以分别订阅它，并维护各自的消费进度。下图展示的是队列粒度负载均衡下的单队列场景。

只有一个队列时，生产者的消息都写入这个队列，无法利用多个队列分散到不同 Broker。在队列粒度负载均衡下，同组也只有一个消费者实例能分到该队列，其他实例无法分担；这是队列分配策略的限制，不是维护消费位点必然导致的。消息粒度负载均衡允许组内多个消费者分担单队列中的不同消息，多队列仍有利于存储和读写负载的分散。

所以总结来说，RocketMQ 通过**使用在一个 Topic 中配置多个队列并且每个队列维护每个消费者组的消费位置** 实现了 **主题模式/发布订阅模式** 。

### 【RocketMQ 架构】

#### 核心组件要点

| 组件           | 技术要点                                 |
| -------------- | ---------------------------------------- |
| **NameServer** | 轻量级注册中心，各节点无数据同步         |
| **Broker**     | 消息存储与投递，支持主从部署             |
| **Proxy**      | 5.0 新增，协议适配与计算卸载（可选组件） |
| **Producer**   | 同步、异步、单向多种发送方式             |
| **Consumer**   | Push/Pull/Simple 三种消费模式            |

#### NameServer（注册中心）

NameServer 负责元数据的存储，扮演着集群“中枢神经系统”的角色，其核心作用是为生产者和消费者提供路由信息，帮助它们找到对应的 Broker 地址。

**核心功能：**

1. **Broker 管理**：Broker 启动时主动连接 NameServer，上报元数据信息。
2. **路由信息管理**：生产者和消费者从 NameServer 获取 Broker 路由表。

**心跳机制：**

```mermaid
flowchart LR
    subgraph Heartbeat["心跳机制"]
        style Heartbeat fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        direction TB
        BK["Broker"] -->|启动时| Reg["注册元数据"]
        BK -->|每隔30秒| HB["发送心跳包"]
        HB --> NS["NameServer更新路由表"]
        NS -->|每隔10秒检查| Check["检查心跳(120秒超时)"]
        Check -->|超时| Down["标记Broker宕机"]
    end

    classDef broker fill:#4CA497,color:#fff,rx:10,ry:10
    classDef ns fill:#E99151,color:#fff,rx:10,ry:10
    classDef check fill:#FFC107,color:#333,rx:10,ry:10
    classDef down fill:#EF5350,color:#fff,rx:10,ry:10
    classDef default fill:#4CA497,color:#fff,rx:10,ry:10

    class BK broker
    class NS ns
    class Check check
    class Down down
    class Reg,HB default

    linkStyle default stroke-width:1.5px,opacity:0.8
```

**元数据包含：**

- Broker 的地址、名称、BrokerId
- 主节点地址
- 该 Broker 上的所有 Topic 的队列配置

#### Broker（消息存储）

Broker 负责消息的存储、投递和查询以及服务高可用保证。

**存储机制：**

1. **消息写入**：收到消息后顺序追加到 CommitLog 文件
2. **文件分割**：文件超过固定大小（默认 1G）生成新文件
3. **逻辑分片**：MessageQueue 是逻辑分片，ConsumeQueue 是消息索引

**一个 Topic 分布在多个 Broker 上，一个 Broker 可以配置多个 Topic ，它们是多对多的关系**。

如果某个 Topic 消息量很大，应该给它多配置几个队列(上文中提到了提高并发能力)，并且 **尽量多分布在不同 Broker 上，以减轻某个 Broker 的压力** 。

Topic 消息量都比较均匀的情况下，如果某个 Broker 上的队列越多，则该 Broker 压力越大。

#### Producer（生产者）

**发送流程：**

```mermaid
flowchart TB
    subgraph ProducerFlow["生产者发送流程"]
        direction TB
        style ProducerFlow fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px

        P["Producer 启动"] -->|1.建立长连接| NS1["连接 NameServer获取路由表"]
        NS1 -->|2.选择队列| LB["负载均衡算法选择 MessageQueue"]
        LB -->|3.建立连接| BK["与 Broker 建立长连接"]
        BK -->|4.发送消息| MSG["发送消息到MessageQueue"]
    end

    classDef producer fill:#00838F,color:#fff,rx:10,ry:10
    classDef ns fill:#E99151,color:#fff,rx:10,ry:10
    classDef lb fill:#FFC107,color:#333,rx:10,ry:10
    classDef broker fill:#4CA497,color:#fff,rx:10,ry:10
    classDef msg fill:#7E57C2,color:#fff,rx:10,ry:10

    class P producer
    class NS1 ns
    class LB lb
    class BK broker
    class MSG msg

    linkStyle default stroke-width:1.5px,opacity:0.8
```

**三种发送方式：**

- **单向发送（Oneway）**：发送后立即返回，不关心是否成功
- **同步发送（Sync）**：发送后等待响应
- **异步发送（Async）**：发送后立即返回，在回调方法中处理响应

#### Consumer（消费者）

**消费流程：**

```mermaid
flowchart TB
    subgraph ConsumerFlow["消费者消费流程"]
        direction TB
        style ConsumerFlow fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px

        C["Consumer 启动"] -->|1.建立长连接| NS2["连接 NameServer获取路由表"]
        NS2 -->|2.建立连接| BK2["与 Broker 建立连接"]
        BK2 -->|3.消费消息| CONS["开始消费消息"]
        CONS -->|4.提交位点| OFFSET["提交消费位点保存消费进度"]
    end

    classDef consumer fill:#7E57C2,color:#fff,rx:10,ry:10
    classDef ns fill:#E99151,color:#fff,rx:10,ry:10
    classDef broker fill:#4CA497,color:#fff,rx:10,ry:10
    classDef consume fill:#00838F,color:#fff,rx:10,ry:10
    classDef offset fill:#FFC107,color:#333,rx:10,ry:10

    class C consumer
    class NS2 ns
    class BK2 broker
    class CONS consume
    class OFFSET offset

    linkStyle default stroke-width:1.5px,opacity:0.8
```

**三种消费模式：**

- **拉取模式（Pull）**：消费者主动向 Broker 发送拉取请求
- **推模式（Push）**：长轮询机制，Broker 有消息时才返回
- **无状态模式（Pop）**：RocketMQ 5.0 新增，服务端管理重平衡和位点

#### 网络协议

RocketMQ 目前常见的是 Remoting 和 gRPC 两类接入方式：

| 对比项     | Remoting（传统协议）                | gRPC（5.x 新版 SDK）                      |
| ---------- | ----------------------------------- | ----------------------------------------- |
| **成熟度** | Java 生态使用时间长，路径短         | 适合多语言和云原生接入，通常经 Proxy 接入 |
| **扩展性** | 多语言接入需要分别适配              | 基于标准协议，客户端生态和网关治理更友好  |
| **取舍**   | 适合已有 4.x 客户端和内部高性能链路 | 链路多一层 Proxy 时，要额外关注延迟和容量 |

#### 网络模块（基于 Netty）

RocketMQ 的 RPC 通信采用 Netty 作为底层通信库，基于 Reactor 多线程模型进行了深度扩展和优化。

**线程模型总结：**

- **Reactor 主线程**：1 个，负责监听连接
- **Reactor 线程池**：默认 3 个，负责网络数据处理
- **业务线程池**：动态调整，根据 CPU 核心数

#### Proxy（代理层，5.0 新增）

RocketMQ 5.0 引入了 **Proxy** 组件，这是 **计算与存储分离** 架构的核心体现。Proxy 作为客户端与 Broker 之间的代理层，将客户端协议适配、权限管理、消费管理等计算逻辑从 Broker 中剥离出来，使 Broker 更专注于消息存储和高可用。这种设计对于云原生架构非常重要，使得计算层可以独立弹性扩展。

**两种部署模式：**

| 模式             | 说明                                            | 适用场景                                 |
| ---------------- | ----------------------------------------------- | ---------------------------------------- |
| **Local 模式**   | Proxy 和 Broker 同进程部署，只需新增 Proxy 配置 | 从旧版本平滑升级，或无特殊需求的场景     |
| **Cluster 模式** | Proxy 和 Broker 分别独立部署                    | 需要弹性扩展或对协议适配有定制需求的场景 |

**核心作用：**

- **协议适配**：支持 gRPC 协议接入，方便多语言客户端接入
- **计算卸载**：将认证鉴权、消费管理等计算逻辑从 Broker 剥离，降低 Broker 负载
- **弹性扩展**：Proxy 无状态，可独立水平扩展

> **注意**：在 5.0 版本中，使用新版 SDK（gRPC 协议）的客户端需要通过 Proxy 接入，而旧版 SDK（Remoting 协议）仍然可以直连 Broker。

Proxy 的价值不只是“多一层代理”。在云原生场景下，它可以把协议接入、认证鉴权、流量治理、消费管理这类计算逻辑从 Broker 中剥离出来，让 Broker 更稳定地承担存储职责。代价是链路多了一跳，需要额外关注 Proxy 的水平扩容、延迟、限流和监控。

#### 为什么必须要 NameServer？

先看一个简单的架构模型：

你可能会发现一个问题：NameServer 是做什么的？直接让 Producer、Consumer 和 Broker 进行生产和消费消息不行吗？

Broker 需要保证高可用，如果整个系统仅靠一个 Broker 来维持，压力会非常大，所以需要使用多个 Broker 来保证 **负载均衡**。如果消费者和生产者直接和多个 Broker 相连，当 Broker 变更时会牵连每个生产者和消费者，产生耦合问题。NameServer 注册中心就是用来解决这个问题的。

**NameServer 的设计哲学：**

NameServer 是 **无状态的、各节点之间互不通信** 的。这与 ZooKeeper 的强一致性（需要选举机制）形成了鲜明对比，体现了 RocketMQ 追求 **极致性能和简单架构** 的设计哲学。每个 Broker 与所有 NameServer 保持长连接，定期上报自身信息，即使某个 NameServer 节点宕机，也不会影响整个集群的可用性。

下面是官网的架构图：

和前面的简化架构图相比，主要是一些细节上的差别：

第一、Broker **做了集群并且还进行了主从部署** ，由于消息分布在各个 Broker 上，一旦某个 Broker 宕机，则该 Broker 上的消息读写都会受到影响。所以 RocketMQ 提供了 `master/slave` 的结构，`slave` 定时从 `master` 同步数据(同步刷盘或者异步刷盘)，如果 `master` 宕机，**则 `slave` 提供消费服务，但是不能写入消息** (后面还会详细说明)。

第二、为了保证 HA，NameServer 也做了集群部署，但它是 **去中心化** 的。也就意味着它没有主节点，可以明显看出 NameServer 的所有节点之间没有进行 `Info Replicate`。在 RocketMQ 中，**单个 Broker 和所有 NameServer 保持长连接**，并且 **每隔 30 秒** Broker 会向所有 NameServer 发送心跳，心跳包含了自身的 Topic 配置信息。NameServer **每隔 10 秒** 检查一次心跳，如果某个 Broker **超过 120 秒** 没有心跳，则认为该 Broker 已宕机。

第三、在生产者需要向 Broker 发送消息的时候，**需要先从 NameServer 获取关于 Broker 的路由信息**，然后通过 **轮询** 的方法去向每个队列中生产数据以达到 **负载均衡** 的效果。

第四、消费者通过 NameServer 获取所有 Broker 的路由信息后，向 Broker 发送 `Pull` 请求来获取消息数据。Consumer 可以以两种模式启动—— **广播（Broadcast）和集群（Cluster）**。广播模式下，一条消息会发送给 **同一个消费组中的所有消费者** ，集群模式下消息只会发送给一个消费者。

### 【RocketMQ 消息】

#### 普通消息

普通消息一般应用于微服务解耦、事件驱动、数据集成等场景，这些场景大多数要求数据传输通道具有可靠传输的能力，且对消息的处理时机、处理顺序没有特别要求。以在线的电商交易场景为例，上游订单系统将用户下单支付这一业务事件封装成独立的普通消息并发送至 RocketMQ 服务端，下游按需从服务端订阅消息并按照本地消费逻辑处理下游任务。每个消息之间都是相互独立的，且不需要产生关联。另外还有日志系统，以离线的日志收集场景为例，通过埋点组件收集前端应用的相关操作日志，并转发到 RocketMQ 。

**普通消息生命周期**

```mermaid
  flowchart LR
      N1["初始化"] --> N2["待消费"] --> N3["消费中"] --> N4["消费提交"] --> N5["消息删除"]

      classDef default fill:#4CA497,color:#fff,rx:10,ry:10
      classDef final fill:#00838F,color:#fff,rx:10,ry:10

      class N1,N2,N3,N4 default
      class N5 final

      linkStyle default stroke-width:1.5px,opacity:0.8
```

- 初始化：消息被生产者构建并完成初始化，待发送到服务端的状态。
- 待消费：消息被发送到服务端，对消费者可见，等待消费者消费的状态。
- 消费中：消息被消费者获取，并按照消费者本地的业务逻辑进行处理的过程。 此时服务端会等待消费者完成消费并提交消费结果，如果一定时间后没有收到消费者的响应，RocketMQ 会对消息进行重试处理。
- 消费提交：消费者完成消费处理，并向服务端提交消费结果；如果消费失败或超时，消息会按重试策略重新投递，超过最大重试次数后可能进入死信队列。RocketMQ 不会因为某个消费组消费成功就立即删除消息，而是按照消息保存机制滚动清理，消息在保存时间到期或存储空间不足被删除前，消费者仍然可以回溯消息重新消费。
- 消息删除：RocketMQ 按照消息保存机制滚动清理最早的消息数据，将消息从物理文件中删除。

#### 定时/延时消息

> **备注：定时消息和延时消息本质相同，都是服务端根据消息设置的定时时间在某一固定时刻将消息投递给消费者消费。**

在分布式定时调度触发、任务超时处理等场景，需要实现精准、可靠的定时事件触发。使用 RocketMQ 的定时消息可以简化定时调度任务的开发逻辑，实现高性能、可扩展、高可靠的定时触发能力。

**典型场景一：分布式定时调度**

在分布式定时调度场景下，需要实现各类精度的定时任务，例如每天 5 点执行文件清理，每隔 2 分钟触发一次消息推送等需求。传统基于数据库的定时调度方案在分布式场景下，性能不高，实现复杂。

**典型场景二：任务超时处理**

以电商交易场景为例，订单下单后暂未支付，此时不可以直接关闭订单，而是需要等待一段时间后才能关闭订单。使用 RocketMQ 定时消息可以实现超时任务的检查触发。

基于定时消息的超时任务处理具备如下优势：

- **精度更灵活、开发门槛低**：5.x 不再只依赖固定延迟等级，可以按时间戳设置投递时间；但默认投递粒度仍是秒级，不能理解为严格毫秒级准时触发。
- **高性能可扩展**：传统的数据库扫描方式较为复杂，需要频繁调用接口扫描，容易产生性能瓶颈。RocketMQ 的定时消息具有高并发和水平扩展的能力。

**定时时间设置原则**

RocketMQ 定时消息设置的定时时间是一个预期触发的系统时间戳，延时时间也需要转换成当前系统时间后的某一个时间戳，而不是一段延时时长。

- **时间格式**：毫秒级的 Unix 时间戳
- **定时时长最大值**：默认为 24 小时，不支持自定义修改
- **定时时间必须设置在当前时间之后**，否则定时不生效，服务端会立即投递消息

**示例**：

- 定时消息：当前系统时间为 2022-06-09 17:30:00，希望消息在 19:20:00 投递，则定时时间戳为 1654773600000
- 延时消息：当前系统时间为 2022-06-09 17:30:00，希望延时 1 小时后投递，则定时时间戳为 1654770600000

**4.x 版本与 5.x 版本的区别**

- **4.x 版本**：只支持延时消息，默认分为 18 个等级（1s 5s 10s 30s 1m 2m 3m 4m 5m 6m 7m 8m 9m 10m 20m 30m 1h 2h），也可以在配置文件中增加自定义的延时等级和时长。
- **5.x 版本**：支持通过毫秒级 Unix 时间戳设置投递时间，相比 4.x 固定延迟等级更灵活；但默认定时粒度为 1000ms，实际投递还会受服务端负载、存储恢复等因素影响，不能理解为严格毫秒级准时触发。

**定时消息生命周期**

```mermaid
  flowchart LR
      T1["初始化"] --> T2["定时中"] --> T3["待消费"] --> T4["消费中"] --> T5["消费提交"] --> T6["消息删除"]

      classDef default fill:#E99151,color:#fff,rx:10,ry:10
      classDef final fill:#00838F,color:#fff,rx:10,ry:10

      class T1,T2,T3,T4,T5 default
      class T6 final

      linkStyle default stroke-width:1.5px,opacity:0.8
```

- **初始化**：消息被生产者构建并完成初始化，待发送到服务端的状态。
- **定时中**：消息被发送到服务端，和普通消息不同的是，服务端不会直接构建消息索引，而是会将定时消息**单独存储在定时存储系统中**，等待定时时刻到达。
- **待消费**：定时时刻到达后，服务端将消息重新写入普通存储引擎，对下游消费者可见，等待消费者消费的状态。
- **消费中**：消息被消费者获取，并按照消费者本地的业务逻辑进行处理的过程。此时服务端会等待消费者完成消费并提交消费结果，如果一定时间后没有收到消费者的响应，RocketMQ 会对消息进行重试处理。
- **消费提交**：消费者完成消费处理，并向服务端提交消费结果；如果消费失败或超时，消息会按重试策略重新投递，超过最大重试次数后可能进入死信队列。RocketMQ 不会因为某个消费组消费成功就立即删除消息，而是按照消息保存机制滚动清理。
- **消息删除**：Apache RocketMQ 按照消息保存机制滚动清理最早的消息数据，将消息从物理文件中删除。

**使用限制**

1. **消息类型一致性**：定时消息仅支持在 MessageType 为 Delay 的主题内使用
2. **定时精度约束**：定时时长参数精确到毫秒级，但默认精度为 1000ms（秒级精度）

**使用建议**

定时消息的实现逻辑需要先经过定时存储等待触发，定时时间到达后才会被投递给消费者。因此，如果将大量定时消息的定时时间设置为同一时刻，则到达该时刻后会有大量消息同时需要被处理，会造成系统压力过大，导致消息分发延迟，影响定时精度。

#### 顺序消息

**什么是顺序消息**

顺序消息是 Apache RocketMQ 提供的一种高级消息类型，支持消费者按照发送消息的先后顺序获取消息，从而实现业务场景中的顺序处理。

**应用场景**

在有序事件处理、撮合交易、数据实时增量同步等场景下，异构系统间需要维持强一致的状态同步，上游的事件变更需要按照顺序传递到下游进行处理。

- **撮合交易**：以证券、股票交易撮合场景为例，对于出价相同的交易单，坚持按照先出价先交易的原则，下游处理订单的系统需要严格按照出价顺序来处理订单。
- **数据实时增量同步**：以数据库变更增量同步场景为例，上游源端数据库按需执行增删改操作，将二进制操作日志作为消息，通过 RocketMQ 传输到下游搜索系统，下游系统按顺序还原消息数据，实现状态数据按序刷新。

**如何保证消息的顺序性**

RocketMQ 的消息顺序性分为两部分：**生产顺序性**和**消费顺序性**。

**生产顺序性**

如需保证消息生产的顺序性，则必须满足以下条件：

1. **单一生产者**：消息生产的顺序性仅支持单一生产者
2. **串行发送**：生产者使用多线程并行发送时，不同线程间产生的消息将无法判定其先后顺序

满足以上条件的生产者，将顺序消息发送至 RocketMQ 后，会保证设置了同一**消息组**的消息，按照发送顺序存储在同一队列中。

**消息组（MessageGroup）**

RocketMQ 顺序消息的顺序关系通过消息组（MessageGroup）判定和识别，发送顺序消息时需要为每条消息设置归属的消息组。

- **相同消息组**的多条消息之间遵循先进先出的顺序关系
- **不同消息组**、无消息组的消息之间不涉及顺序性

基于消息组的顺序判定逻辑，支持按照业务逻辑做细粒度拆分，可以在满足业务局部顺序的前提下提高系统的并行度和吞吐能力。

```mermaid
flowchart TB
    subgraph Order["订单系统"]
        style Order fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        O1["订单A消息组: orderA"]
        O2["订单B消息组: orderB"]
        O3["订单C消息组: orderC"]
    end

    subgraph Queue["队列"]
        style Queue fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        Q["队列1(混合存储不同消息组)"]
    end

    subgraph Storage["存储顺序"]
        style Storage fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        direction LR
        S1["orderA-M1↓"]
        S2["orderB-M1↓"]
        S3["orderA-M2↓"]
        S4["orderC-M1↓"]
        S5["orderB-M2↓"]
    end

    O1 --> Q
    O2 --> Q
    O3 --> Q
    Q --> Storage

    classDef orderA fill:#4CA497,color:#fff,rx:10,ry:10
    classDef orderB fill:#E99151,color:#fff,rx:10,ry:10
    classDef orderC fill:#7E57C2,color:#fff,rx:10,ry:10
    classDef queue fill:#00838F,color:#fff,rx:10,ry:10
    classDef storage fill:#FFC107,color:#333,rx:10,ry:10

    class O1 orderA
    class O2 orderB
    class O3 orderC
    class Q queue
    class S1,S2,S3,S4,S5 storage

    linkStyle default stroke-width:1.5px,opacity:0.8
```

**说明**：

- orderA 消息组的 M1、M2 保持顺序
- orderB 消息组的 M1、M2 保持顺序
- 不同消息组可以混合存储在同一个队列中

**消费顺序性**

如需保证消息消费的顺序性，则必须满足以下条件：

1. **投递顺序**：RocketMQ 通过客户端 SDK 和服务端通信协议保障消息按照服务端存储顺序投递
2. **有限重试**：顺序消息投递仅在重试次数限定范围内，超过最大重试次数后将不再重试，跳过这条消息消费

**消费者类型对顺序消费的影响**

- **PushConsumer**：RocketMQ 保证消息按照存储顺序一条一条投递给消费者
- **SimpleConsumer**：消费者可能一次拉取多条消息，此时消息消费的顺序性需要由业务方自行保证

**生产顺序性和消费顺序性组合**

| 生产顺序                     | 消费顺序 | 顺序性效果                               |
| ---------------------------- | -------- | ---------------------------------------- |
| 设置消息组，保证消息顺序发送 | 顺序消费 | 按照消息组粒度，严格保证消息顺序         |
| 设置消息组，保证消息顺序发送 | 并发消费 | 并发消费，尽可能按时间顺序处理           |
| 未设置消息组，消息乱序发送   | 顺序消费 | 只能保证队列存储顺序，不保证业务发送顺序 |
| 未设置消息组，消息乱序发送   | 并发消费 | 并发消费，尽可能按照时间顺序处理         |

**使用限制**

1. **消息类型一致性**：顺序消息仅支持在 MessageType 为 FIFO 的主题内使用；RocketMQ 5.x 中还要为有序消息设置 MessageGroup，并把消费者组配置为顺序投递，否则仍可能按并发方式投递
2. 顺序消息消费失败进行消费重试时，为保障消息的顺序性，后续消息不可被消费，必须等待前面的消息消费完成后才能被处理

**使用建议**

1. **串行消费**：消息消费建议串行处理，避免一次消费多条消息导致乱序
2. **消息组尽可能打散**：建议将业务以消息组粒度进行拆分，例如将订单 ID、用户 ID 作为消息组关键字，可实现同一终端用户的消息按照顺序处理，不同用户的消息无需保证顺序

#### 事务消息

**什么是事务消息**

事务消息是 Apache RocketMQ 提供的一种高级消息类型，支持在分布式场景下保障消息生产和本地事务的最终一致性。简单来讲，就是将本地事务（数据库的 DML 操作）与发送消息合并在同一个事务中。

**应用场景**

在分布式系统调用的特点为一个核心业务逻辑的执行，同时需要调用多个下游业务进行处理。如何保证核心业务和多个下游业务的执行结果完全一致，是分布式事务需要解决的主要问题。

以电商交易场景为例，用户支付订单这一核心操作的同时会涉及到下游物流发货、积分变更、购物车状态清空等多个子系统的变更：

- **主分支订单系统状态更新**：由未支付变更为支付成功
- **物流系统状态新增**：新增待发货物流记录，创建订单物流记录
- **积分系统状态变更**：变更用户积分，更新用户积分表
- **购物车系统状态变更**：清空购物车，更新用户购物车记录

**传统方案的问题**

- **传统 XA 事务方案**：基于 XA 协议的分布式事务系统可以实现一致性，但多分支环境下资源锁定范围大，并发度低
- **基于普通消息方案**：普通消息和订单事务无法保证一致，容易出现消息发送成功但订单没有执行成功、订单执行成功但消息没有发送成功等情况

**RocketMQ 事务消息方案**

RocketMQ 事务消息的方案，具备高性能、可扩展、业务开发简单的优势，支持二阶段的提交能力，将二阶段提交和本地事务绑定，实现 **本地事务和消息发送** 的最终一致性。

**事务消息处理流程**

```mermaid
flowchart TB
    subgraph Phase1["阶段一: 发送半事务消息"]
        direction TB
        style Phase1 fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        M1["生产者构建消息"] --> M2["发送至服务端"]
        M2 --> M3["服务端持久化消息"]
        M3 --> M4["返回 Ack 确认"]
        M4 --> M5["消息标记为'暂不能投递'(半事务消息)"]
    end

    subgraph Phase2["阶段二: 执行本地事务"]
        direction TB
        style Phase2 fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        L1["生产者开始执行本地事务逻辑"] --> L2{"本地事务执行结果"}
        L2 -->|Commit| L3["提交二次确认 Commit"]
        L2 -->|Rollback| L4["提交二次确认 Rollback"]
        L2 -->|Unknown| L5["等待事务回查"]
    end

    subgraph Phase3["阶段三: 事务回查机制"]
        direction TB
        style Phase3 fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        C1["服务端未收到确认或收到 Unknown"] --> C2["固定时间后发起消息回查"]
        C2 --> C3["生产者检查本地事务最终状态"]
        C3 --> C4["再次提交二次确认"]
    end

    subgraph Result["最终处理"]
        style Result fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
        direction TB
        R1["Commit: 消息投递给消费者"]
        R2["Rollback: 回滚事务不投递消息"]
    end

    Phase1 --> Phase2
    L3 --> R1
    L4 --> R2
    L5 --> Phase3
    C4 --> R1

    classDef normal fill:#4CA497,color:#fff,rx:10,ry:10
    classDef decision fill:#E99151,color:#fff,rx:10,ry:10
    classDef result fill:#00838F,color:#fff,rx:10,ry:10

    class M1,M2,M3,M4,M5,L1,C1,C2,C3,C4 normal
    class L2,L3,L4,L5 decision
    class R1,R2 result

    linkStyle default stroke-width:1.5px,opacity:0.8
```

1. 生产者将消息发送至 RocketMQ 服务端
2. 服务端将消息持久化成功之后，向生产者返回 Ack 确认消息已经发送成功，此时消息被标记为“暂不能投递”，这种状态下的消息即为**半事务消息**
3. 生产者开始执行本地事务逻辑
4. 生产者根据本地事务执行结果向服务端提交二次确认结果（Commit 或 Rollback）
5. 如果服务端未收到二次确认结果，或收到的结果为 Unknown，经过固定时间后，服务端将对消息生产者发起**消息回查**
6. 生产者收到消息回查后，需要检查对应消息的本地事务执行的最终结果
7. 生产者根据检查到的本地事务的最终状态再次提交二次确认

**事务消息生命周期**

- **初始化**：半事务消息被生产者构建并完成初始化，待发送到服务端的状态
- **事务待提交**：半事务消息被发送到服务端后会被持久化到事务相关的存储中，但不会直接进入普通可消费状态；它需要等待第二阶段本地事务返回 Commit 或 Rollback 后再决定是否投递。此时消息对下游消费者不可见
- **消息回滚**：第二阶段如果事务执行结果明确为回滚，服务端会将半事务消息回滚，该事务消息流程终止
- **提交待消费**：第二阶段如果事务执行结果明确为提交，服务端会将半事务消息重新存储到普通存储系统中，此时消息对下游消费者可见
- **消费中**：消息被消费者获取，并按照消费者本地的业务逻辑进行处理的过程
- **消费提交**：消费者完成消费处理，并向服务端提交消费结果；如果消费失败或超时，仍会进入重试、死信或补偿流程
- **消息删除**：RocketMQ 按照消息保存机制滚动清理最早的消息数据

**使用限制**

1. **消息类型一致性**：事务消息仅支持在 MessageType 为 Transaction 的主题内使用
2. **消费事务性**：RocketMQ 事务消息保证本地主分支事务和下游消息发送事务的一致性，但不保证消息消费结果和上游事务的一致性
3. **中间状态可见性**：事务消息为最终一致性，即消息提交到下游消费端处理完成之前，下游分支和上游事务之间的状态会不一致
4. **事务超时机制**：事务消息的生命周期存在超时机制，半事务消息被生产者发送服务端后，如果在指定时间内服务端无法确认提交或者回滚状态，则消息默认会被回滚
5. **事务回查机制**：服务端默认 **每隔 60 秒** 对未确认的半事务消息发起回查；半事务消息默认最大超时时间为 **4 小时**，超时后会被强制回滚。老版本或部分云厂商实现可能还会暴露最大回查次数参数，面试和生产配置时要按实际版本确认。

**使用建议**

1. **避免大量未决事务导致超时**：生产者应该尽量避免本地事务返回未知结果，大量的事务检查会导致系统性能受损
2. **正确处理“进行中”的事务**：消息回查时，对于正在进行中的事务不要返回 Rollback 或 Commit 结果，应继续保持 Unknown 的状态
3. **本地事务状态要可查询**：事务回查依赖生产者查询本地事务最终状态，建议落库或写可靠存储，不要只放进进程内存。
4. **下游消费仍需幂等**：事务消息解决的是“本地事务和消息发送”的一致性，不保证消费者业务一定成功，消费端仍然要有重试、幂等和补偿。

#### 关于发送消息

#### 不建议单一进程创建大量生产者

Apache RocketMQ 的生产者和主题是多对多的关系，支持同一个生产者向多个主题发送消息。对于生产者的创建和初始化，建议遵循够用即可、最大化复用原则，如果有需要发送消息到多个主题的场景，无需为每个主题都创建一个生产者。

#### 不建议频繁创建和销毁生产者

Apache RocketMQ 的生产者是可以重复利用的底层资源，类似数据库的连接池。因此不需要在每次发送消息时动态创建生产者，且在发送结束后销毁生产者。这样频繁的创建销毁会在服务端产生大量短连接请求，严重影响系统性能。

正确示例：

```java
Producer p = ProducerBuilder.build();
for (int i =0;i<n;i++){
    Message m= MessageBuilder.build();
    p.send(m);
 }
p.shutdown();
```

### 【消费者分类】

#### PushConsumer（推模式消费者）

**核心特点：**

高度封装的消费者类型，消费消息仅仅通过消费监听器监听并返回结果。消息的获取、消费状态提交以及消费重试都通过 RocketMQ 的客户端 SDK 完成。

**适用场景：**

- 消息处理时间可预估
- 无异步化、高级定制需求
- 希望快速开发的场景

**使用示例：**

```java
public static void main(String[] args) throws InterruptedException, MQClientException {
    // 创建 Push 模式消费者
    DefaultMQPushConsumer consumer = new DefaultMQPushConsumer("CID_JODIE_1");

    // 订阅主题
    consumer.subscribe("TopicTest", "*");

    // 设置从哪里开始消费
    consumer.setConsumeFromWhere(ConsumeFromWhere.CONSUME_FROM_FIRST_OFFSET);

    // 注册消息监听器
    consumer.registerMessageListener(new MessageListenerConcurrently() {
        @Override
        public ConsumeConcurrentlyStatus consumeMessage(
                List msgs,
                ConsumeConcurrentlyContext context) {
            System.out.printf("Receive New Messages: %s %n", msgs);
            // 业务处理逻辑
            return ConsumeConcurrentlyStatus.CONSUME_SUCCESS;
        }
    });

    consumer.start();
}
```

**消费监听器执行结果：**

- **返回消费成功**：表示该消息处理成功，服务端按照消费结果更新消费进度
- **返回消费失败**：表示该消息处理失败，需要根据消费重试逻辑判断是否进行重试消费
- **抛出异常**：按消费失败处理，需要根据消费重试逻辑判断是否进行重试消费

**使用注意事项：**

PushConsumer 消费时，不允许使用以下方式处理消息：

1. **错误方式一**：消息还未处理完成，就提前返回消费成功结果。此时如果消息消费失败，RocketMQ 服务端是无法感知的，因此不会进行消费重试。

2. **错误方式二**：在消费监听器内将消息再次分发到自定义的其他线程，消费监听器提前返回消费结果。此时如果消息消费失败，RocketMQ 服务端同样无法感知，因此也不会进行消费重试。

**传统 Remoting SDK 的 Push 模式工作原理（对应上面的 DefaultMQPushConsumer 示例）：**

1. **负载均衡**：RebalanceService 线程根据队列数量和消费者个数做负载均衡，将分配到的队列发布 pullRequest 到 pullRequestQueue
2. **消息拉取**：PullMessageService 线程不断从 pullRequestQueue 获取 pullRequest，从 Broker 拉取消息并缓存到 ProcessQueue
3. **消息消费**：ConsumeMessageService 线程从 ProcessQueue 获取消息，调用监听器处理业务逻辑
4. **位点提交**：消费完成后自动提交消费位点
5. **流控保护**：拉取前检查缓存阈值（1000 消息或 100M），超过则延迟拉取

#### SimpleConsumer

SimpleConsumer 是一种接口原子型的消费者类型，消息的获取、消费状态提交以及消费重试都是通过消费者业务逻辑主动发起调用完成。

**消息不可见时间（Invisible Time）：**

SimpleConsumer 的核心机制是 **消息不可见时间**。当消费者获取消息后，该消息在指定的不可见时间内对其他消费者不可见。如果在不可见时间内完成消费并提交 ACK，消息被标记为已消费；如果超时未提交 ACK，消息会重新变为可见状态，可被其他消费者获取。这与 PushConsumer 的定时重试队列机制不同，SimpleConsumer 通过动态修改不可见时间来实现更灵活的重试控制。

一个来自官网的例子：

```java
// 消费示例：使用 SimpleConsumer 消费普通消息，主动获取消息处理并提交。
ClientServiceProvider provider = ClientServiceProvider.loadService();
String topic = "YourTopic";
FilterExpression filterExpression = new FilterExpression("YourFilterTag", FilterExpressionType.TAG);
SimpleConsumer simpleConsumer = provider.newSimpleConsumerBuilder()
        // 设置消费者分组。
        .setConsumerGroup("YourConsumerGroup")
        // 设置接入点。
        .setClientConfiguration(ClientConfiguration.newBuilder().setEndpoints("YourEndpoint").build())
        // 设置预绑定的订阅关系。
        .setSubscriptionExpressions(Collections.singletonMap(topic, filterExpression))
        // 设置从服务端接受消息的最大等待时间
        .setAwaitDuration(Duration.ofSeconds(1))
        .build();
try {
    // SimpleConsumer 需要主动获取消息，并处理。
    List messageViewList = simpleConsumer.receive(10, Duration.ofSeconds(30));
    messageViewList.forEach(messageView -> {
        System.out.println(messageView);
        // 消费处理完成后，需要主动调用 ACK 提交消费结果。
        try {
            simpleConsumer.ack(messageView);
        } catch (ClientException e) {
            logger.error("Failed to ack message, messageId={}", messageView.getMessageId(), e);
        }
    });
} catch (ClientException e) {
    // 如果遇到系统流控等原因造成拉取失败，需要重新发起获取消息请求。
    logger.error("Failed to receive message", e);
}
```

SimpleConsumer 适用于以下场景：

- 消息处理时长不可控：如果消息处理时长无法预估，经常有长时间耗时的消息处理情况。建议使用 SimpleConsumer 消费类型，可以在消费时自定义消息的预估处理时长，若实际业务中预估的消息处理时长不符合预期，也可以通过接口提前修改。
- 需要异步化、批量消费等高级定制场景：SimpleConsumer 在 SDK 内部没有复杂的线程封装，完全由业务逻辑自由定制，可以实现异步分发、批量消费等高级定制场景。
- 需要自定义消费速率：SimpleConsumer 是由业务逻辑主动调用接口获取消息，因此可以自由调整获取消息的频率，自定义控制消费速率。

**SimpleConsumer 工作原理：**

1. **主动获取消息**：业务方调用 receive() 接口主动获取消息
2. **业务处理**：获取到的消息由业务方自行处理
3. **主动提交 ACK**：消费处理完成后，业务方主动调用 ack() 接口提交消费结果
4. **高可控性**：业务方可完全控制消息处理时机和消费速率

#### PullConsumer（拉模式消费者）

**核心特点：**

Pull 模式下，**应用程序对消息的拉取过程参与度高，可控性强**，可以自主决定何时进行消息拉取，从什么位置 offset 拉取消息。

**与 Push 模式的对比：**

| 特性           | Push 模式            | Pull 模式        |
| -------------- | -------------------- | ---------------- |
| **控制权**     | 客户端 SDK 自动拉取  | 应用程序主动拉取 |
| **可控性**     | 可控性不足           | 可控性高         |
| **开发复杂度** | 简单，只需实现监听器 | 需要管理拉取过程 |
| **适用场景**   | 消息处理可预估       | 需要精细控制拉取 |

**使用示例（DefaultMQPullConsumer）：**

```java
@Test
public void testPullConsumer() throws Exception {
    DefaultMQPullConsumer consumer = new DefaultMQPullConsumer("group1_pull");
    consumer.setNamesrvAddr(this.nameServer);
    String topic = "topic1";
    consumer.start();

    // 获取 Topic 对应的消息队列
    Set messageQueues = consumer.fetchSubscribeMessageQueues(topic);
    int maxNums = 10; // 每次拉取消息的最大数量

    while (true) {
        boolean found = false;
        for (MessageQueue messageQueue : messageQueues) {
            // 获取消费位置
            long offset = consumer.fetchConsumeOffset(messageQueue, false);
            // 拉取消息
            PullResult pullResult = consumer.pull(messageQueue, "tag8", offset, maxNums);

            switch (pullResult.getPullStatus()) {
                case FOUND:
                    found = true;
                    List msgs = pullResult.getMsgFoundList();
                    System.out.println("收到消息，数量----" + msgs.size());
                    // 处理消息
                    for (MessageExt msg : msgs) {
                        System.out.println("处理消息——" + msg.getMsgId());
                    }
                    // 更新消费位置
                    long nextOffset = pullResult.getNextBeginOffset();
                    consumer.updateConsumeOffset(messageQueue, nextOffset);
                    break;
                case NO_NEW_MSG:
                    System.out.println("没有新消息");
                    break;
                case NO_MATCHED_MSG:
                    System.out.println("没有匹配的消息");
                    break;
                case OFFSET_ILLEGAL:
                    System.err.println("offset 错误");
                    break;
            }
        }
        if (!found) {
            // 没有队列中有新消息，则暂停一会
            TimeUnit.MILLISECONDS.sleep(5000);
        }
    }
}
```

**使用示例（DefaultLitePullConsumer - 推荐）：**

```java
DefaultLitePullConsumer litePullConsumer =
        new DefaultLitePullConsumer("lite_pull_consumer_test");
litePullConsumer.setConsumeFromWhere(ConsumeFromWhere.CONSUME_FROM_FIRST_OFFSET);
litePullConsumer.subscribe("TopicTest", "*");
litePullConsumer.start();

try {
    while (running) {
        // 应用程序主动调用 poll 方法拉取消息
        List messageExts = litePullConsumer.poll();
        System.out.printf("%s%n", messageExts);
    }
} finally {
    litePullConsumer.shutdown();
}
```

**适用场景：**

- **需要精细控制拉取时机**：可以根据业务需求自主决定何时拉取消息
- **需要控制消费速率**：可以灵活调整拉取频率
- **批量消费场景**：可以一次性拉取大量消息进行批量处理
- **特殊消费需求**：如需要从特定 offset 开始消费、需要暂停消费等

**Pull 模式工作原理：**

1. **负载均衡**：RebalanceService 线程发现消费快照发生变化时，启动消息拉取线程
2. **消息拉取**：PullTaskImpl 拉取到消息后，把消息放到 consumeRequestCache
3. **消息消费**：应用程序调用 poll 方法，不停地从 consumeRequestCache 拉取消息进行业务处理

#### 三种消费者类型对比

| 对比项         | PushConsumer                                                             | SimpleConsumer                                       | PullConsumer                                       |
| -------------- | ------------------------------------------------------------------------ | ---------------------------------------------------- | -------------------------------------------------- |
| 接口方式       | 使用监听器回调接口返回消费结果，消费者仅允许在监听器范围内处理消费逻辑。 | 业务方自行实现消息处理，并主动调用接口返回消费结果。 | 业务方自行按队列拉取消息，并可选择性地提交消费结果 |
| 消费并发度管理 | 由 SDK 管理消费并发度。                                                  | 由业务方消费逻辑自行管理消费线程。                   | 由业务方消费逻辑自行管理消费线程。                 |
| 负载均衡粒度   | 5.x SDK 默认是消息粒度，早期版本是队列粒度                               | 5.x SDK 默认是消息粒度                               | 队列粒度，吞吐攒批性能更好，但容易不均衡           |
| 接口灵活度     | 高度封装，不够灵活。                                                     | 原子接口，可灵活自定义。                             | 原子接口，可灵活自定义。                           |
| 适用场景       | 适用于无自定义流程的业务消息开发场景。                                   | 适用于需要高度自定义业务流程的业务开发场景。         | 仅推荐在流处理框架场景下集成使用                   |

**选择建议：**

- **普通场景**：优先使用 **PushConsumer**，开发简单，SDK 自动管理拉取和提交
- **消息处理时长不可控**：使用 **SimpleConsumer**，可以自定义处理时长
- **需要精细控制**：使用 **PullConsumer**，完全自主控制拉取过程

**注意**：生产环境中相同的 ConsumerGroup 下严禁混用 PullConsumer 和其他两种消费者，否则会导致消息消费异常。

### 【消费者分组和生产者分组】

#### 生产者分组

RocketMQ 5.x 新版领域模型里，**生产者是轻量、匿名的运行实体**，一般不再需要像早期版本那样重点管理生产者分组（ProducerGroup）。不过在 3.x/4.x 客户端、Spring 生态或兼容模式里，仍可能看到 ProducerGroup 配置，迁移时不要简单删除，要按实际客户端版本确认。

#### 消费者分组

消费者分组是多个消费行为一致的消费者的负载均衡分组。消费者分组不是具体实体而是一个逻辑资源。通过消费者分组实现消费性能的水平扩展以及高可用容灾。

**消费者组的核心作用：**

```mermaid
flowchart TB
    subgraph ConsumerGroup["消费者组概念"]
        direction TB
        style ConsumerGroup fill:#F0F2F5,stroke:#E0E6ED,stroke-width:1.5px

        subgraph Cluster["集群消费模式（以队列粒度为例）"]
            direction TB
            style Cluster fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
            CG["消费者组"] --> C1["消费者1消费队列1"]
            CG --> C2["消费者2消费队列2"]
            CG --> C3["消费者3空闲"]
            Note1["任意一条消息只需被消费组内任意一个消费者处理"]
        end

        subgraph Broadcast["广播消费模式"]
            direction TB
            style Broadcast fill:#F5F7FA,stroke:#E0E6ED,stroke-width:1.5px
            BG["消费者组"] --> B1["消费者1消费所有消息"]
            BG --> B2["消费者2消费所有消息"]
            BG --> B3["消费者3消费所有消息"]
            Note2["每条消息推送给消费组所有消费者"]
        end

        %% 优化：调整注释连线，避免跨子图渲染异常
        C1 -.-> Note1
        C2 -.-> Note1
        C3 -.-> Note1
        B1 -.-> Note2
        B2 -.-> Note2
        B3 -.-> Note2
    end

    classDef cg fill:#4CA497,color:#fff,rx:10,ry:10
    classDef consumer fill:#E99151,color:#fff,rx:10,ry:10
    classDef note fill:#00838F,color:#fff,rx:10,ry:10

    class CG,BG cg
    class C1,C2,C3,B1,B2,B3 consumer
    class Note1,Note2 note

    linkStyle default stroke-width:1.5px,opacity:0.8
```

消费者分组中的订阅关系、投递顺序性、消费重试策略是一致的。

- 订阅关系：Apache RocketMQ 以消费者分组的粒度管理订阅关系，实现订阅关系的管理和追溯。
- 投递顺序性：Apache RocketMQ 的服务端将消息投递给消费者消费时，支持顺序投递和并发投递，投递方式在消费者分组中统一配置。
- 消费重试策略： 消费者消费消息失败时的重试策略，包括重试次数、死信队列设置等。

RocketMQ 服务端 5.x 版本：上述消费者的消费行为从关联的消费者分组中统一获取，因此，同一分组内所有消费者的消费行为必然是一致的，客户端无需关注。

RocketMQ 服务端 3.x/4.x 历史版本：上述消费逻辑由消费者客户端接口定义，因此，您需要自己在消费者客户端设置时保证同一分组下的消费者的消费行为一致。(来自官方网站)

**两种消费模式对比：**

| 对比维度     | 集群消费模式                                   | 广播消费模式                         |
| ------------ | ---------------------------------------------- | ------------------------------------ |
| **消息消费** | 任意一条消息只需被消费组内的任意一个消费者处理 | 每条消息推送给消费组所有消费者       |
| **扩缩容**   | 可通过扩缩消费者数量来提升或降低消费能力       | 扩缩消费者数量无法提升或降低消费能力 |
| **适用场景** | 需要提升消费能力、避免重复消费                 | 需要所有消费者都收到消息             |

### 【如何解决顺序消费和重复消费？】

#### 顺序消费

在上面的技术架构介绍中，我们已经知道了 **RocketMQ 在主题上是无序的、它只有在队列层面才是保证有序** 的。

这又扯到两个概念——**普通顺序** 和 **严格顺序** 。

所谓普通顺序是指 消费者通过 **同一个消费队列收到的消息是有顺序的** ，不同消息队列收到的消息则可能是无顺序的。普通顺序消息在 Broker **重启情况下不会保证消息顺序性** (短暂时间) 。

所谓严格顺序是指 消费者收到的 **所有消息** 均是有顺序的。严格顺序消息 **即使在异常情况下也会保证消息的顺序性** 。

但是，严格顺序看起来虽好，实现它可会付出巨大的代价。如果你使用严格顺序模式，Broker 集群中只要有一台机器不可用，则整个集群都不可用。你还用啥？现在主要场景也就在 `binlog` 同步。

一般而言，我们的 `MQ` 都是能容忍短暂的乱序，所以推荐使用普通顺序模式。

那么，我们现在使用了 **普通顺序模式** ，我们从上面学习知道了在 Producer 生产消息的时候会进行轮询(取决你的负载均衡策略)来向同一主题的不同消息队列发送消息。那么如果此时我有几个消息分别是同一个订单的创建、支付、发货，在轮询的策略下这 **三个消息会被发送到不同队列** ，因为在不同的队列此时就无法使用 RocketMQ 带来的队列有序特性来保证消息有序性了。

那么，怎么解决呢？

其实很简单，我们需要处理的仅仅是将同一语义下的消息放入同一个队列(比如这里是同一个订单)，那我们就可以使用 **Hash 取模法** 来保证同一个订单在同一个队列中就行了。

**4.x 版本：使用 MessageQueueSelector**

RocketMQ 4.x 版本通过继承 `MessageQueueSelector` 来实现自定义队列选择逻辑：

```java
SendResult sendResult = producer.send(msg, new MessageQueueSelector() {
    @Override
    public MessageQueue select(List mqs, Message msg, Object arg) {
        //根据订单ID等业务关键字计算队列索引
        Long orderId = (Long) arg;
        int index = Math.floorMod(Long.hashCode(orderId), mqs.size());
        return mqs.get(index);
    }
}, orderId);
```

**5.x 版本：使用消息组（MessageGroup）**

RocketMQ 5.x 版本引入了**消息组**的概念，通过设置消息组来保证同一组内消息的顺序性：

```java
Message message = messageBuilder.setTopic("topic")
        .setTag("messageTag")
        //设置顺序消息的排序分组
        .setMessageGroup("fifoGroup001")  // 比如使用订单ID作为消息组
        .setBody("messageBody".getBytes())
        .build();
```

**队列选择算法**

RocketMQ 实现了两种队列选择算法：

- **轮询算法**（默认）：向消息指定的 topic 所在队列中依次发送消息，保证消息均匀分布
- **最小投递延迟算法**：每次消息投递的时候统计消息投递的延迟，选择队列时优先选择消息延时小的队列

```java
// 启用最小投递延迟算法
producer.setSendLatencyFaultEnable(true);
```

#### 特殊情况处理

#### 发送异常

选择队列后会与 Broker 建立连接，通过网络请求将消息发送到 Broker 上，如果 Broker 挂了或者网络波动发送消息超时此时 RocketMQ 会进行重试。

重新选择其他 Broker 中的消息队列进行发送，默认重试两次，可以手动设置。

```java
producer.setRetryTimesWhenSendFailed(5);
```

#### 消息过大

这里要区分两个限制：客户端可以配置消息体超过某个阈值后压缩（例如 Java 4.x 客户端常见默认值是 4KB），而 RocketMQ 5.x 官方参数里默认最大消息体是 4MB，且这个大小不包含压缩后的额外效果。大文件不建议直接塞进消息体，通常把文件放到对象存储或文件系统里，MQ 里只传业务 ID 和文件地址。

#### 重复消费

RocketMQ 和大多数消息队列一样，工程上通常按 **至少一次投递** 来设计：只要出现消费失败、超时、客户端重启、网络抖动等情况，同一条业务消息就可能再次投递。因此，解决重复消费的核心思路就是两个字—— **幂等** 。在编程中，一个*幂等*操作的特点是其任意多次执行所产生的影响均与一次执行的影响相同。比如说，这个时候我们有一个订单的处理积分的系统，每当来一个消息的时候它就负责为创建这个订单的用户的积分加上相应的数值。可是有一次，消息队列发送给订单系统 FrancisQ 的订单信息，其要求是给 FrancisQ 的积分加上 500。但是积分系统在收到 FrancisQ 的订单信息处理完成之后返回给消息队列处理成功的信息的时候出现了网络波动(当然还有很多种情况，比如 Broker 意外重启等等)，这条回应没有发送成功。

那么，消息队列没收到积分系统的回应会不会尝试重发这个消息？问题就来了，我再发这个消息，万一它又给 FrancisQ 的账户加上 500 积分怎么办呢？

所以我们需要给我们的消费者实现 **幂等** ，也就是对同一个消息的处理结果，执行多少次都不变。

那么如何给业务实现幂等呢？这个还是需要结合具体的业务的。Redis 的 `SETNX` 可以做短期去重或弱幂等控制，但不要把它当成所有场景的唯一依据；订单、支付、库存这类强一致场景，更推荐使用 **数据库唯一键、幂等表或业务状态机** 来兜底，保证重复消息不会造成重复写入或重复扣减。

不过最主要的还是需要 **根据特定场景使用特定的解决方案** ，你要知道你的消息消费是否是完全不可重复消费还是可以忍受重复消费的，然后再选择强校验和弱校验的方式。毕竟在 CS 领域还是很少有技术银弹的说法。

RocketMQ 消费端幂等可以优先按业务唯一键设计，而不是只依赖消息 ID。比如订单支付消息用支付单号或订单号做唯一键，库存扣减消息用业务流水号做唯一键。这样即使消息重试、补偿或重新投递，只要业务唯一键不变，就能避免重复写入。

而在整个互联网领域，幂等不仅仅适用于消息队列的重复消费问题，这些实现幂等的方法，也同样适用于，**在其他场景中来解决重复请求或者重复调用的问题** 。比如将 HTTP 服务设计成幂等的，**解决前端或者 APP 重复提交表单数据的问题** ，也可以将一个微服务设计成幂等的，解决 RPC 框架自动重试导致的 **重复调用问题** 。

### 【RocketMQ 如何实现分布式事务？】

#### RocketMQ 如何实现分布式事务？

如何解释分布式事务呢？事务大家都知道吧？**要么都执行要么都不执行** 。在同一个系统中我们可以轻松地实现事务，但是在分布式架构中，我们有很多服务是部署在不同系统之间的，而不同服务之间又需要进行调用。比如此时我下订单然后增加积分，如果保证不了分布式事务的话，就会出现 A 系统下了订单，但是 B 系统增加积分失败或者 A 系统没有下订单，B 系统却增加了积分。前者对用户不友好，后者对运营商不利，这是我们都不愿意见到的。

那么，如何去解决这个问题呢？

如今比较常见的分布式事务实现有 2PC、TCC 和事务消息(half 半消息机制)。每一种实现都有其特定的使用场景，但是也有各自的问题，**都不是完美的解决方案**。

在 RocketMQ 中使用的是 **事务消息加上事务反查机制** 来解决分布式事务问题的。我画了张图，大家可以对照着图进行理解。

**事务消息处理流程详解**

1. **发送半事务消息**：生产者将消息发送至 RocketMQ 服务端
2. **服务端确认**：服务端将消息持久化成功之后，向生产者返回 Ack 确认消息已经发送成功，此时消息被标记为“暂不能投递”，这种状态下的消息即为**半事务消息**
3. **执行本地事务**：生产者开始执行本地事务逻辑
4. **提交二次确认**：生产者根据本地事务执行结果向服务端提交二次确认结果（Commit 或 Rollback）
5. **事务回查**：如果服务端未收到二次确认结果，或收到的结果为 Unknown，经过固定时间后，服务端将对消息生产者发起**消息回查**
6. **检查本地事务**：生产者收到消息回查后，需要检查对应消息的本地事务执行的最终结果
7. **再次提交确认**：生产者根据检查到的本地事务的最终状态再次提交二次确认

在第一步发送的 half 消息 ，它的意思是 **在事务提交之前，对于消费者来说，这个消息是不可见的** 。

> 那么，如何做到写入消息但是对用户不可见呢？RocketMQ 事务消息的做法是：如果消息是 half 消息，将备份原消息的主题与消息消费队列，然后 **改变主题** 为 RMQ_SYS_TRANS_HALF_TOPIC。由于消费组未订阅该主题，故消费端无法消费 half 类型的消息，**然后 RocketMQ 会开启一个定时任务，从 Topic 为 RMQ_SYS_TRANS_HALF_TOPIC 中拉取消息进行消费**，根据生产者组获取一个服务提供者发送回查事务状态请求，根据事务状态来决定是提交或回滚消息。

你可以试想一下，如果没有从第 5 步开始的 **事务回查机制** ，如果出现网路波动第 4 步没有发送成功，这样就会产生 MQ 不知道是不是需要给消费者消费的问题。在 RocketMQ 中就是使用的上述的事务回查来解决的，而在 Kafka 中通常是直接抛出一个异常让用户来自行解决。

你还需要注意的是，在 `MQ Server` 指向系统 B 的操作已经和系统 A 不相关了，也就是说在消息队列中的分布式事务是——**本地事务和存储消息到消息队列才是同一个事务**。这样也就产生了事务的**最终一致性**，因为整个过程是异步的，**每个系统只要保证它自己那一部分的事务就行了**。

实践中会遇到的问题：事务消息需要一个事务监听器来监听本地事务是否成功，并且事务监听器接口只允许被实现一次。那就意味着需要把各种事务消息的本地事务都写在一个接口方法里面，必将会产生大量的耦合和类型判断。采用函数 Function 接口来包装整个业务过程，作为一个参数传递到监听器的接口方法中。再调用 Function 的 apply() 方法来执行业务，事务也会在 apply() 方法中执行。让监听器与业务之间实现解耦，使之具备了真实生产环境中的可行性。

另外，事务回查时不要只查 Redis。事务最终状态应该以和本地事务同库提交的事务表、业务表状态为准，Redis 最多作为缓存或加速查询的副本。下面示例保留 Redis 写法是为了演示思路，生产环境要把本地事务状态落到可靠存储，并用业务唯一键或数据库约束保证消费端幂等。

1.模拟一个添加用户浏览记录的需求

```java
@PostMapping("/add")
@ApiOperation("添加用户浏览记录")
public Result add(Long userId, Long forecastLogId) {

        // 函数式编程:浏览记录入库
        Function function = transactionId -> viewHistoryHandler.addViewHistory(transactionId, userId, forecastLogId);

        Map hashMap = new HashMap<>();
        hashMap.put("userId", userId);
        hashMap.put("forecastLogId", forecastLogId);
        String jsonString = JSON.toJSONString(hashMap);

        // 发送事务消息;将本地的事务操作,用函数Function接口接收,作为一个参数传入到方法中
        TransactionSendResult transactionSendResult = mqProducerService.sendTransactionMessage(jsonString, MQDestination.TAG_ADD_VIEW_HISTORY, function);
        return Result.success(transactionSendResult);
}
```

2.发送事务消息的方法

```java
/**
 * 发送事务消息
 *
 * @param msgBody
 * @param tag
 * @param function
 * @return
 */
public TransactionSendResult sendTransactionMessage(String msgBody, String tag, Function function) {
    // 构建消息体
    Message message = buildMessage(msgBody);

    // 构建消息投递信息
    String destination = buildDestination(tag);

    TransactionSendResult result = rocketMQTemplate.sendMessageInTransaction(destination, message, function);
    return result;
}
```

3.生产者消息监听器,只允许一个类去实现该监听器

```java
@Slf4j
@RocketMQTransactionListener
public class TransactionMsgListener implements RocketMQLocalTransactionListener {

    @Autowired
    private RedisService redisService; // 示例缓存，生产环境不要作为事务状态唯一来源

    /**
     * 执行本地事务（在发送消息成功时执行）
     *
     * @param message
     * @param o
     * @return commit or rollback or unknown
     */
    @Override
    public RocketMQLocalTransactionState executeLocalTransaction(Message message, Object o) {

        // 1、获取事务ID
        String transactionId = null;
        try {
            transactionId = message.getHeaders().get("rocketmq_TRANSACTION_ID").toString();
            // 2、判断传入函数对象是否为空，如果为空代表没有要执行的业务直接抛弃消息
            if (o == null) {
                //返回ROLLBACK状态的消息会被丢弃
                log.info("事务消息回滚，没有需要处理的业务 transactionId={}", transactionId);
                return RocketMQLocalTransactionState.ROLLBACK;
            }
            // 将Object o转换成Function对象
            Function function = (Function) o;
            // 执行业务 事务也会在function.apply中执行
            Boolean apply = function.apply(transactionId);
            if (apply) {
                log.info("事务提交，消息正常处理 transactionId={}", transactionId);
                //返回COMMIT状态的消息会立即被消费者消费到
                return RocketMQLocalTransactionState.COMMIT;
            }
        } catch (Exception e) {
            log.info("出现异常 返回ROLLBACK transactionId={}", transactionId);
            return RocketMQLocalTransactionState.ROLLBACK;
        }
        return RocketMQLocalTransactionState.ROLLBACK;
    }

    /**
     * 事务回查机制，检查本地事务的状态
     *
     * @param message
     * @return
     */
    @Override
    public RocketMQLocalTransactionState checkLocalTransaction(Message message) {

        String transactionId = message.getHeaders().get("rocketmq_TRANSACTION_ID").toString();

        // 示例里查 Redis；生产环境建议查询本地事务表或业务表最终状态
        MqTransaction mqTransaction = redisService.getCacheObject("mqTransaction:" + transactionId);
        if (Objects.isNull(mqTransaction)) {
            return RocketMQLocalTransactionState.ROLLBACK;
        }
        return RocketMQLocalTransactionState.COMMIT;
    }
}
```

4.模拟的业务场景,这里的方法必须提取出来,放在别的类里面.如果调用方与被调用方在同一个类中,会发生事务失效的问题.

```java
@Component
public class ViewHistoryHandler {

    @Autowired
    private IViewHistoryService viewHistoryService;

    @Autowired
    private IMqTransactionService mqTransactionService;

    @Autowired
    private RedisService redisService; // 示例缓存，事务状态仍应以数据库为准

    /**
     * 浏览记录入库
     *
     * @param transactionId
     * @param userId
     * @param forecastLogId
     * @return
     */
    @Transactional
    public Boolean addViewHistory(String transactionId, Long userId, Long forecastLogId) {
        // 构建浏览记录
        ViewHistory viewHistory = new ViewHistory();
        viewHistory.setUserId(userId);
        viewHistory.setForecastLogId(forecastLogId);
        viewHistory.setCreateTime(LocalDateTime.now());
        boolean save = viewHistoryService.save(viewHistory);

        // 本地事务信息
        MqTransaction mqTransaction = new MqTransaction();
        mqTransaction.setTransactionId(transactionId);
        mqTransaction.setCreateTime(new Date());
        mqTransaction.setStatus(MqTransaction.StatusEnum.VALID.getStatus());

        // 事务状态应和本地业务数据在同一个事务中落库
        mqTransactionService.save(mqTransaction);

        // Redis 只能作为缓存副本，不能作为事务状态的唯一来源
        redisService.setCacheObject("mqTransaction:" + transactionId, mqTransaction, 4L, TimeUnit.HOURS);

        // 放开注释,模拟异常,事务回滚
        // int i = 10 / 0;

        return save;
    }
}
```

5.消费消息,以及幂等处理

```java
@Service
@RocketMQMessageListener(topic = MQDestination.TOPIC, selectorExpression = MQDestination.TAG_ADD_VIEW_HISTORY, consumerGroup = MQDestination.TAG_ADD_VIEW_HISTORY)
public class ConsumerAddViewHistory implements RocketMQListener {
    // 监听到消息就会执行此方法
    @Override
    public void onMessage(Message message) {
        // 幂等校验
        String transactionId = message.getTransactionId();

        // 示例里查 Redis；强一致场景建议用业务唯一键、幂等表或数据库约束兜底
        MqTransaction mqTransaction = redisService.getCacheObject("mqTransaction:" + transactionId);

        // 不存在事务记录
        if (Objects.isNull(mqTransaction)) {
            return;
        }

        // 已消费
        if (Objects.equals(mqTransaction.getStatus(), MqTransaction.StatusEnum.CONSUMED.getStatus())) {
            return;
        }

        String msg = new String(message.getBody());
        Map map = JSON.parseObject(msg, new TypeReference>() {
        });
        Long userId = map.get("userId");
        Long forecastLogId = map.get("forecastLogId");

        // 下游的业务处理
        // TODO 记录用户喜好,更新用户画像

        // TODO 更新'证券预测文章'的浏览量,重新计算文章的曝光排序

        // 更新状态为已消费
        mqTransaction.setUpdateTime(new Date());
        mqTransaction.setStatus(MqTransaction.StatusEnum.CONSUMED.getStatus());
        redisService.setCacheObject("mqTransaction:" + transactionId, mqTransaction, 4L, TimeUnit.HOURS);
        log.info("监听到消息：msg={}", JSON.toJSONString(map));
    }
}
```

### 【如何解决消息堆积问题？】

#### 如何解决消息堆积问题？

在上面我们提到了消息队列一个很重要的功能——**削峰** 。那么如果这个峰值太大了导致消息堆积在队列中怎么办呢？

其实这个问题可以将它广义化，因为产生消息堆积的根源其实就只有两个——生产者生产太快或者消费者消费太慢。

我们可以从多个角度去思考解决这个问题，当流量到峰值的时候是因为生产者生产太快，我们可以使用一些 **限流降级** 的方法，当然你也可以增加多个消费者实例去水平扩展增加消费能力来匹配生产的激增。如果消费者消费过慢的话，我们可以先检查 **是否是消费者出现了大量的消费错误** ，或者打印一下日志查看是否是哪一个线程卡死，出现了锁资源不释放等等的问题。

> 增加消费者实例通常能缓解消费能力不足造成的堆积，但是否需要增加队列，要看负载均衡策略和现有队列数量。
>
> **注意**：传统 Remoting SDK 的队列粒度负载均衡下，**同组内一个队列只分配给一个消费者实例**。只有扩容后的消费者数超过可分配队列数时，才会出现部分消费者没有队列可消费的情况。
>
> RocketMQ 5.x 的 PushConsumer 和 SimpleConsumer 默认使用**消息粒度负载均衡策略**，同一消费者分组内的多个消费者可以按照消息粒度共同消费同一个队列中的消息，因此即使消费者数量多于队列数量，仍能提升消费并行度。PullConsumer 仍是队列粒度，扩容时还是要关注队列数。

生产排查消息堆积时，可以按这个顺序来：

1. **先确认堆积范围**：是单个 Topic、单个队列，还是整个 Broker 都堆积。
2. **看生产速度和消费速度**：生产突增要限流或削峰，消费下降要查消费者。
3. **查消费者耗时**：重点看慢 SQL、外部接口、锁竞争、线程池和批量大小。
4. **看队列和消费者匹配关系**：4.x 和 PullConsumer 需要关注队列数是否限制了并发，5.x PushConsumer/SimpleConsumer 还要关注消息粒度负载均衡策略。
5. **做临时扩容和补偿**：必要时临时扩容消费者、增加队列、拆分 Topic，历史积压用批处理任务慢慢追。

不要只盯着“加消费者”。如果单队列顺序消费卡住，或者业务处理本身很慢，加消费者也不会明显改善。

### 【什么是回溯消费？】

#### 什么是回溯消费？

回溯消费是指 Consumer 已经消费成功的消息，由于业务上需求需要重新消费，在 RocketMQ 中， Broker 在向 Consumer 投递成功消息后，**消息仍然需要保留** 。并且重新消费一般是按照时间维度，例如由于 Consumer 系统故障，恢复后需要重新消费 1 小时前的数据，那么 Broker 要提供一种机制，可以按照时间维度来回退消费进度。RocketMQ 支持按照时间回溯消费，时间维度精确到毫秒。

### 【RocketMQ 如何保证高性能读写】

#### 传统 IO 方式

传统的 IO 读写其实就是 read + write 的操作，整个过程会分为如下几步

- 用户调用 read()方法，开始读取数据，此时发生一次上下文从用户态到内核态的切换，也就是图示的切换 1
- 将磁盘数据通过 DMA 拷贝到内核缓存区
- 将内核缓存区的数据拷贝到用户缓冲区，这样用户，也就是我们写的代码就能拿到文件的数据
- read()方法返回，此时就会从内核态切换到用户态，也就是图示的切换 2
- 当我们拿到数据之后，就可以调用 write()方法，此时上下文会从用户态切换到内核态，即图示切换 3
- CPU 将用户缓冲区的数据拷贝到 Socket 缓冲区
- 将 Socket 缓冲区数据拷贝至网卡
- write()方法返回，上下文重新从内核态切换到用户态，即图示切换 4

整个过程发生了 4 次上下文切换和 4 次数据的拷贝，这在高并发场景下肯定会严重影响读写性能故引入了零拷贝技术

#### 零拷贝技术

#### mmap

mmap（memory map）是一种内存映射文件的方法，即将一个文件或者其它对象映射到进程的地址空间，实现文件磁盘地址和进程虚拟地址空间中一段虚拟地址的一一对映关系。

简单地说就是内核缓冲区和应用缓冲区共享，从而减少了从读缓冲区到用户缓冲区的一次 CPU 拷贝。基于此上述架构图可变为：

基于 mmap IO 读写其实就变成 mmap + write 的操作，也就是用 mmap 替代传统 IO 中的 read 操作。

当用户发起 mmap 调用时，内核主要是建立文件和进程虚拟地址空间的映射关系，并不会在这一步就把全部文件内容拷贝进内存。真正访问映射区域时，如果对应页还不在 Page Cache 中，才会触发缺页中断并把磁盘数据加载到内存；随后用户调用 write，仍需要把数据从内核缓冲区写到 Socket 缓冲区。

发生 4 次上下文切换和 3 次 IO 拷贝操作，在 Java 中的实现：

```java
FileChannel fileChannel = new RandomAccessFile("test.txt", "rw").getChannel();
MappedByteBuffer mappedByteBuffer = fileChannel.map(FileChannel.MapMode.READ_WRITE, 0, fileChannel.size());
```

#### sendfile

sendfile()跟 mmap()一样，也会减少一次 CPU 拷贝，但是它同时也会减少两次上下文切换。

如图，用户在发起 sendfile()调用时会发生切换 1，之后数据通过 DMA 拷贝到内核缓冲区，再由内核把数据发送到 Socket 相关缓冲区，最后写入网卡，sendfile()返回，发生切换 2。不同操作系统和网卡能力下具体拷贝次数会有差异，但核心收益是减少用户态和内核态之间的数据拷贝与上下文切换。Java 也提供了相应 api：

```java
FileChannel channel = FileChannel.open(Paths.get("./test.txt"), StandardOpenOption.WRITE, StandardOpenOption.CREATE);
//调用transferTo方法向目标数据传输
channel.transferTo(position, len, target);
```

在如上代码中，并没有文件的读写操作，而是直接将文件的数据传输到 target 目标缓冲区，也就是说，sendfile 是无法知道文件的具体的数据的；但是 mmap 不一样，他是可以修改内核缓冲区的数据的。假设如果需要对文件的内容进行修改之后再传输，只有 mmap 可以满足。

通过上面的一些介绍，结论是基于零拷贝技术，可以减少 CPU 拷贝和上下文切换，从而提升文件读写和网络传输效率。

RocketMQ 快不只是因为 mmap。更关键的是 CommitLog 顺序追加写、Page Cache、ConsumeQueue 定长索引，以及刷盘和复制策略之间的取舍。mmap 主要降低文件读写路径上的额外拷贝和系统调用成本，是其中一个重要环节。

### 【RocketMQ 的刷盘机制】

#### 同步刷盘和异步刷盘

如上图所示，在同步刷盘中需要等待一个刷盘成功的 ACK ，同步刷盘对 `MQ` 消息可靠性来说是一种不错的保障，但是 **性能上会有较大影响** ，一般地适用于金融等特定业务场景。

而异步刷盘往往是开启一个线程去异步地执行刷盘操作。消息刷盘采用后台异步线程提交的方式进行， **降低了读写延迟** ，提高了 `MQ` 的性能和吞吐量，一般适用于如发验证码等对于消息保证要求不太高的业务场景。

一般地，**异步刷盘只有在 Broker 意外宕机的时候会丢失部分数据**，你可以设置 Broker 的参数 `FlushDiskType` 来调整你的刷盘策略(ASYNC_FLUSH 或者 SYNC_FLUSH)。

#### 同步复制和异步复制

上面的同步刷盘和异步刷盘是在单个节点层面的，而同步复制和异步复制主要是指 `Broker` 主从模式下，主节点返回消息给客户端的时候是否需要同步从节点。

- 同步复制：也叫 “同步双写”，也就是说，**只有消息同步双写到主从节点上时才返回写入成功** 。
- 异步复制：**消息写入主节点之后就直接返回写入成功** 。

然而，很多事情是没有完美的方案的，就比如我们进行消息写入的节点越多就更能保证消息的可靠性，但是随之的性能也会下降，所以需要程序员根据特定业务场景去选择适应的主从复制方案。

那么，**异步复制会不会也像异步刷盘那样影响消息的可靠性呢？**

答案是会影响。刷盘策略决定消息是否落到本机磁盘，复制策略决定消息是否已经同步到副本。异步复制下，主节点返回成功时消息可能还没有复制到从节点；如果主节点此时宕机且数据无法恢复，从节点就可能缺少这部分消息。因此，要求更高可靠性时，通常会选择同步刷盘 + 同步复制，或者使用 DLedger 这类多数派复制方案。

比如采用异步复制时，主节点已经向生产者返回成功，但这部分消息还没来得及同步到从节点。如果主节点只是短暂不可用，恢复后仍可能继续补齐复制；如果主节点数据丢失或发生不可逆故障，从节点就可能永远少这部分消息。这里影响的不只是可用性，也包括可靠性。

在单主从架构中，如果一个主节点挂掉了，那么整个系统就不能再生产消息了。那么这个可用性的问题能否解决呢？**可以通过多主从架构来解决**，在最初的架构图中，每个 Topic 是分布在不同 Broker 中的。

但是这种复制方式同样也会带来一个问题，那就是无法保证 **严格顺序** 。在上文中我们提到了如何保证的消息顺序性是通过将一个语义的消息发送在同一个队列中，使用 Topic 下的队列来保证顺序性的。如果此时我们主节点 A 负责的是订单 A 的一系列语义消息，然后它挂了，这样其他节点是无法代替主节点 A 的，如果我们任意节点都可以存入任何消息，那就没有顺序性可言了。

而在 RocketMQ 中采用了 DLedger 解决这个问题。DLedger 要求在写入消息的时候，**至少消息复制到半数以上的节点之后**，才给客户端返回写入成功，并且支持通过选举来动态切换主节点。

> DLedger 也不是完美的方案：在选举过程中是无法提供服务的；必须使用三个节点或以上；如果多数节点同时挂掉也无法保证可用性；要求消息复制到半数以上节点的效率和直接异步复制还是有一定差距的。

#### 存储机制

至此，刷盘和复制的问题已经解决了。

接下来讨论 **队列是以什么样的形式存在的？队列中的消息又是如何进行存储持久化的？** 这涉及到 RocketMQ 的存储结构设计。首先介绍 RocketMQ 消息存储架构中的三大角色——CommitLog、ConsumeQueue 和 IndexFile。

**存储架构三大组件：**

- **CommitLog**：**消息主体以及元数据的存储主体**，存储 Producer 端写入的消息主体内容，消息内容不是定长的。单个文件大小默认 **1G**，文件名长度为 20 位，左边补零，剩余为起始偏移量，比如 00000000000000000000 代表第一个文件，起始偏移量为 0；当第一个文件写满后，第二个文件为 00000000001073741824，起始偏移量为 1073741824，以此类推。消息主要是 **顺序写入日志文件**，当文件满了，写入下一个文件。
- **ConsumeQueue**：指定 Topic 下某个 MessageQueue 的物理索引文件，**引入的目的主要是提高消息消费的性能**。由于 RocketMQ 是基于 Topic 的订阅模式，如果要遍历 CommitLog 文件根据 Topic 和队列检索消息是非常低效的。ConsumeQueue 保存了消息在 CommitLog 中的 **起始物理偏移量 offset**、消息大小 size 和消息 Tag 的 HashCode 值。ConsumeQueue 文件夹的组织方式为：topic/queue/file 三层组织结构，具体存储路径为：`$HOME/store/consumequeue/{topic}/{queueId}/{fileName}`。ConsumeQueue 文件采取定长设计，每一个条目共 **20 个字节**（8 字节 commitlog 物理偏移量 + 4 字节消息长度 + 8 字节 tag hashcode），单个文件由 **30 万个条目** 组成，每个 ConsumeQueue 文件大小约 **5.72M**。
- **IndexFile**：索引文件，提供了一种可以通过 key 或时间区间来查询消息的方法。

总结来说，整个消息存储的结构，最主要的就是 `CommitLog` 和 ConsumeQueue。MessageQueue 是 Topic 下的逻辑队列，ConsumeQueue 是这个逻辑队列对应的物理索引文件，不要把两者完全等同。

RocketMQ 采用的是 **混合型的存储结构** ，即 Broker 单个实例下所有的队列共用一个日志数据文件（CommitLog）来存储消息。而 Kafka 会为每个分区（Partition）分配一个独立的存储文件。

RocketMQ 这么做的原因是 **提高数据的写入效率** ，不分 Topic 意味着有更大的几率获取 **成批** 的消息进行顺序写入，但也带来一个问题：读取消息时如果遍历整个 CommitLog 文件，效率很低。

所以，RocketMQ 使用 ConsumeQueue 作为每个队列的索引文件来 **提升读取消息的效率**。可以直接根据队列的消息序号，计算出索引的全局位置（索引序号 × 索引固定长度 20），然后直接读取这条索引，再根据索引中记录的消息的全局位置找到消息。

下面结合架构图来理解存储结构：

> 如果上面没看懂的读者一定要认真看下面的流程分析！

首先，在图的最上面可以把 `ConsumeQueue` 理解为某个 MessageQueue 的索引文件，而不是消息主体本身。

在图中最左边说明了红色方块代表被写入的消息，虚线方块代表等待被写入的消息。左边的生产者发送消息会指定 Topic、`QueueId` 和具体消息内容，而在 Broker 中不区分消息类型，直接 **全部顺序存储到 CommitLog**。根据生产者指定的 Topic 和 `QueueId`，将这条消息在 CommitLog 中的偏移量（offset）、消息大小和 tag 的 hash 值存入对应的 ConsumeQueue 索引文件中。

在每个队列中都保存了 `ConsumeOffset` 即每个消费者组的消费位置，消费者拉取消息进行消费时只需要根据 `ConsumeOffset` 获取下一个未被消费的消息即可。

以上就是 RocketMQ 存储架构的核心原理。

最后留一个思考题：**为什么 CommitLog 文件要设计成固定大小的长度呢？** 提示：与 **内存映射机制（mmap）** 有关。

### 【总结】

#### 总结

本文系统地介绍了 RocketMQ 的核心知识点，以下是关键内容回顾：

**消息队列核心价值**

- **异步**：提升系统响应速度，非核心流程异步化处理
- **解耦**：降低系统间耦合度，通过发布订阅模式实现松耦合
- **削峰**：缓解瞬时流量压力，保护下游系统不被冲垮

**RocketMQ 架构要点**

| 组件           | 核心职责                                     |
| -------------- | -------------------------------------------- |
| **NameServer** | 无状态注册中心，各节点互不通信，追求简单高效 |
| **Broker**     | 消息存储与投递，支持主从架构和 DLedger 模式  |
| **Proxy**      | 5.0 新增，计算与存储分离，支持 gRPC 协议     |
| **Producer**   | 消息生产者，支持同步、异步、单向发送         |
| **Consumer**   | 消息消费者，支持 Push、Pull、Simple 三种模式 |

**消息类型对比**

| 消息类型     | 适用场景             | 关键特性                 |
| ------------ | -------------------- | ------------------------ |
| **普通消息** | 微服务解耦、事件驱动 | 无顺序要求，消息相互独立 |
| **顺序消息** | 订单处理、数据同步   | 同一消息组内严格有序     |
| **定时消息** | 延迟任务、超时处理   | 5.x 支持按时间戳设置投递 |
| **事务消息** | 分布式事务           | 半消息机制 + 事务回查    |

**5.x 版本核心升级**

- **消息粒度负载均衡**：5.x PushConsumer/SimpleConsumer 默认使用，缓解队列粒度负载不均
- **计算与存储分离**：Proxy 组件承担协议适配和计算逻辑，Broker 专注存储
- **定时消息增强**：不再只受限于固定延迟等级，可按毫秒级时间戳设置投递时间，默认粒度为秒级
- **gRPC 多语言 SDK**：降低多语言客户端接入成本，更适合云原生和多协议场景

**高性能设计**

- **顺序写**：CommitLog 采用顺序写入，充分利用磁盘顺序 IO 的高性能
- **零拷贝**：结合 mmap、Page Cache 等机制，减少数据拷贝和系统调用成本
- **索引设计**：ConsumeQueue 作为消息索引，避免遍历 CommitLog

**可靠性保障**

- **刷盘策略**：同步刷盘提升本机持久化可靠性，异步刷盘提升性能
- **主从复制**：同步复制提升副本可靠性，异步复制提升吞吐但可能丢失未复制消息
- **DLedger**：基于 Raft 协议实现自动主从切换，提升高可用能力

<!-- @include: @article-footer.snippet.md -->

### 【RabbitMQ 是什么？】

#### RabbitMQ 是什么？

RabbitMQ 是用 Erlang 编写的开源消息中间件，最常用的是 AMQP 0-9-1，同时也支持 AMQP 1.0、MQTT、STOMP 等协议。

它在系统中扮演 Broker 角色：生产者把消息发到交换器，交换器按照绑定规则把消息路由到队列，消费者再从队列取走消息。RabbitMQ 的优势主要体现在路由能力、确认机制、插件体系和多语言客户端生态上。

### 【RabbitMQ 特点】

#### RabbitMQ 特点

- **可靠性**：支持消息持久化、消费者手动 Ack、Publisher Confirms、死信交换器等机制。
- **灵活的路由**：消息先进入交换器，再由交换器根据路由键和绑定关系投递到队列。常见路由用内置交换器就够了，复杂场景也可以组合多个交换器或使用插件。
- **扩展性**：多个 RabbitMQ 节点可以组成集群，队列副本能力由队列类型决定，不能只看“集群”两个字。
- **高可用性**：Quorum Queue 基于 Raft 协议复制数据；Streams 也是复制型数据结构，更适合日志和回放场景。
- **多种协议**：RabbitMQ 除了原生支持 AMQP 协议，还支持 STOMP、MQTT 等多种消息中间件协议。
- **多语言客户端**：RabbitMQ 几乎支持所有常用语言，比如 Java、Python、Ruby、PHP、C#、JavaScript 等。
- **管理界面**：Management UI 可以查看队列、连接、Channel、Exchange、节点状态和常见运行指标。
- **插件机制**：RabbitMQ 通过插件扩展 MQTT、STOMP、Prometheus 监控等能力。

### 【RabbitMQ 有哪些重要概念？】

#### Producer(生产者) 和 Consumer(消费者)

- **Producer(生产者)** :生产消息的一方（邮件投递者）
- **Consumer(消费者)** :消费消息的一方（邮件收件人）

消息一般由 2 部分组成：**消息头**（或者说是标签 Label）和 **消息体**。消息体也可以称为 **payload**，消息体是不透明的，而消息头则由一系列的可选属性组成，这些属性包括 routing-key（路由键）、priority（相对于其他消息的优先权）、delivery-mode（指出该消息可能需要持久性存储）等。生产者把消息交由 RabbitMQ 后，RabbitMQ 会根据消息头把消息发送给感兴趣的 Consumer(消费者)。

#### Exchange(交换器)

在 RabbitMQ 中，消息并不是直接被投递到 **Queue(消息队列)** 中的，中间还必须经过 **Exchange(交换器)** 这一层，**Exchange(交换器)** 会把我们的消息分配到对应的 **Queue(消息队列)** 中。

**Exchange(交换器)** 用来接收生产者发送的消息，再把消息路由到一个或多个队列。如果路由不到，消息可能被返回给生产者，也可能进入备用交换器，或者直接被丢弃，具体取决于发布参数和交换器配置。

**RabbitMQ 的 Exchange(交换器) 有 4 种类型，不同的类型对应着不同的路由策略**：**direct**，**fanout**, **topic**, 和 **headers**，不同类型的 Exchange 转发消息的策略有所区别。这个会在介绍 **Exchange Types(交换器类型)** 的时候介绍到。

> 注意：AMQP 0-9-1 里有一个默认交换器（Default Exchange），它是预声明的 direct 交换器，名称为空字符串 `""`。创建业务交换器时，需要显式指定交换器类型。

生产者将消息发给交换器的时候，一般会指定一个 **RoutingKey(路由键)**，用来指定这个消息的路由规则，而这个 **RoutingKey 需要与交换器类型和绑定键(BindingKey)联合使用才能最终生效**。

RabbitMQ 中通过 **Binding(绑定)** 将 **Exchange(交换器)** 与 **Queue(消息队列)** 关联起来。绑定时通常会指定一个 **BindingKey(绑定键)**，RabbitMQ 根据它判断消息应该进入哪个队列。一个绑定可以理解为一条路由规则，Exchange 和 Queue 可以是多对多关系。

生产者将消息发送给交换器时，通常会带上 RoutingKey。当 BindingKey 和 RoutingKey 按当前交换器类型匹配时，消息会被路由到对应队列。同一个交换器可以绑定多个队列，也允许多个绑定使用相同的 BindingKey。BindingKey 是否参与匹配取决于交换器类型，比如 fanout 交换器会忽略 BindingKey，把消息投递到所有绑定队列。

#### Queue(消息队列)

**Queue(消息队列)** 用来保存消息直到发送给消费者。它是消息的容器，也是消息的终点。一个消息可投入一个或多个队列。消息一直在队列里面，等待消费者连接到这个队列将其取走。

**RabbitMQ** 在经典架构中，消息只能存储在 **队列** 中，这一点和 **Kafka** 这种消息中间件相反。Kafka 将消息存储在 **topic（主题）** 这个逻辑层面，而相对应的队列逻辑只是 topic 实际存储文件中的位移标识。RabbitMQ 的生产者生产消息并最终投递到队列中，消费者可以从队列中获取消息并消费。

> RabbitMQ 3.9 开始提供 Streams。Streams 采用 append-only 日志：消息消费后不会从日志里删除，消费者可以按 offset 回放历史消息。事件溯源、日志分发、大量消息堆积这类场景更适合 Streams；普通异步任务仍然优先看 Classic Queue 或 Quorum Queue。

**多个消费者可以订阅同一个队列**，队列中的消息会分发给其中一个消费者处理，而不是每个消费者都收到一份。

> 注意：实际分发效果受 `prefetch_count` 影响。在 AMQP 0-9-1 中，`prefetch_count=0` 表示不限制未确认消息数量，消费者可能一次拿到很多消息。业务处理耗时不稳定时，建议给消费者设置合适的 prefetch 值，避免消息都堆在某个消费者本地。

**RabbitMQ** 不支持队列层面的广播消费。如果希望每个消费者都收到一份消息，通常做法是给每个消费者准备独立队列，再把这些队列绑定到同一个 fanout 或 topic 交换器。

#### Broker（消息中间件的服务节点）

对于 RabbitMQ 来说，一个 RabbitMQ Broker 可以简单地看作一个 RabbitMQ 服务节点，或者 RabbitMQ 服务实例。大多数情况下也可以将一个 RabbitMQ Broker 看作一台 RabbitMQ 服务器。

#### Exchange Types(交换器类型)

RabbitMQ 常用的 Exchange Type 有 **fanout**、**direct**、**topic**、**headers** 这四种（AMQP 规范里还提到两种 Exchange Type，分别为 system 与自定义，这里不予以描述）。

![RabbitMQ Exchange 四种类型对比](images/rabbitmq-exchange-types-7f9832f1.png)

| 类型    | 路由规则                                           | 常见场景                                     |
| ------- | -------------------------------------------------- | -------------------------------------------- |
| fanout  | 忽略 RoutingKey，发给所有绑定队列                  | 配置刷新、缓存失效、日志同时分发到多个消费者 |
| direct  | BindingKey 和 RoutingKey 完全匹配                  | 按级别、业务类型或服务名精确分发             |
| topic   | RoutingKey 按 `.` 分段，BindingKey 支持 `*` 和 `#` | 按地域、业务模块、事件类型做多级过滤         |
| headers | 按消息 headers 匹配，支持 `x-match=all` 和 `any`   | 很少使用，能用 topic 表达时一般不选 headers  |

topic 的两个通配符容易混：`*` 只匹配一个单词，`#` 可以匹配零个或多个单词。例如 `order.china.*` 可以匹配 `order.china.beijing`，不能匹配 `order.china.beijing.created`；`#.client.#` 可以匹配 `com.rabbitmq.client`。

### 【AMQP 是什么?】

#### AMQP 是什么?

RabbitMQ 最早围绕 AMQP 0-9-1 实现，生产者、交换器、队列、绑定、路由键这些概念都来自 AMQP 模型。RabbitMQ 还支持 AMQP 1.0、MQTT、STOMP 等协议，不同协议接入时的功能细节会有差异。

RabbitMQ 中的交换器、交换器类型、队列、绑定、路由键等都是遵循的 AMQP 协议中**相应**的概念。

> RabbitMQ 4.0 起原生支持 AMQP 1.0，默认启用，不再依赖旧版 AMQP 1.0 插件做协议转换。AMQP 0-9-1 仍然被继续支持，现有 Java、Spring AMQP 等生态大多还是围绕它展开。新项目是否选择 AMQP 1.0，要看客户端库成熟度、互操作需求以及 RabbitMQ 对 AMQP 1.0 功能的实际支持情况。

**AMQP 0-9-1 里需要区分 AMQ model 和协议层**：

- **AMQ model**：定义交换器、队列、绑定等核心对象，以及消息如何从生产者路由到消费者。
- **Functional Layer**：定义按逻辑类分组的协议命令，例如 exchange、queue、basic、tx 等。
- **Transport Layer**：负责帧处理、Channel 复用、心跳、错误处理和数据表示等。

**AMQP 模型的三大组件**：

- **交换器 (Exchange)**：消息代理服务器中用于把消息路由到队列的组件。
- **队列 (Queue)**：用来存储消息的数据结构，位于硬盘或内存中。
- **绑定 (Binding)**：一套规则，告知交换器消息应该将消息投递给哪个队列。

### 【说说生产者 Producer 和消费者 Consumer】

#### 说说生产者 Producer 和消费者 Consumer

**生产者**：

- 消息生产者，就是投递消息的一方。
- 消息一般包含两个部分：**消息体**（payload）和**消息头**（Label/Headers）。

**消费者**：

- 消费消息，也就是接收消息的一方。
- 消费者连接到 RabbitMQ 服务器并订阅队列。业务通常处理消息体；routing key、headers、delivery tag 等属于路由或投递元数据，可以用于日志、幂等和确认处理，但不应该被当成业务消息体本身。

### 【说说 Broker 服务节点、Queue 队列、Exchange 交换器？】

#### 说说 Broker 服务节点、Queue 队列、Exchange 交换器？

- **Broker**：可以看做 RabbitMQ 的服务节点。一般情况下一个 Broker 可以看做一个 RabbitMQ 服务器。
- **Queue**：RabbitMQ 的内部对象，用于存储消息。多个消费者可以订阅同一队列，这时队列中的消息会被平摊（轮询）给多个消费者进行处理。
- **Exchange**：生产者将消息发送到交换器，由交换器将消息路由到一个或者多个队列中。当路由不到时，或返回给生产者或直接丢弃。

### 【什么是死信队列？如何导致的？】

#### 什么是死信队列？如何导致的？

DLX，全称为 `Dead-Letter-Exchange`（死信交换器），当消息在一个队列中变成死信（`dead message`）之后，它能被重新发送到另一个交换器中，这个交换器就是 DLX，绑定 DLX 的队列就称之为死信队列。

**导致死信的常见原因**：

- 消息被拒（`Basic.Reject` 或 `Basic.Nack`）且 `requeue = false`。
- 消息 TTL 过期。
- 队列达到长度限制，消息被丢弃。
- Quorum Queue 中消息返回次数超过 `delivery-limit`。

### 【什么是延迟队列？RabbitMQ 怎么实现延迟队列？】

#### 什么是延迟队列？RabbitMQ 怎么实现延迟队列？

延迟队列保存的是延迟消息：消息已经发送到 RabbitMQ，但业务希望它过一段时间后再被消费者拿到。

RabbitMQ 本身是没有延迟队列的，要实现延迟消息，一般有两种方式：

1. 使用 TTL + DLX。消息先进入带 TTL 的队列，过期后被投递到死信交换器，再进入真正消费队列。缺点是容易受到队列头部阻塞影响；如果每种延迟时间都建一组队列，维护成本也会变高。
2. 使用 `rabbitmq-delayed-message-exchange` 插件。它提供 `x-delayed-message` 交换器，可以按消息设置延迟时间。官方 README 的定位是秒、分钟、小时级延迟，最多一两天；如果要做天、周、月级调度，或者要堆积十万、百万级延迟消息，应使用外部存储和调度系统。

也就是说，RabbitMQ 常见延迟消息不是普通队列的原生能力，TTL + DLX 和延迟插件都能做，但都要看延迟规模和可恢复性要求。

### 【什么是优先级队列？】

#### 什么是优先级队列？

RabbitMQ 支持的是消息优先级，队列本身没有优先级区分。优先级队列指同一个队列内部按照消息优先级投递，高优先级消息会更早交给消费者。

Classic Queue 可以通过 `x-max-priority` 参数声明优先级队列，Quorum Queue 也支持优先级。需要注意的是，如果消费速度一直大于生产速度，队列里没有堆积，优先级就很难体现出来。

### 【RabbitMQ 消息怎么传输？】

#### RabbitMQ 消息怎么传输？

由于 TCP 连接的创建和销毁开销较大（三次握手、慢启动等），并发连接数也受系统资源限制，RabbitMQ 使用信道（Channel）复用 TCP 连接。Channel 是建立在 TCP 连接上的虚拟通信通道。

> 注意：
>
> - 单个 TCP 连接可承载多个 Channel，但官方建议不超过 100-200 个/连接
> - 每个 Channel 有独立的编号，但共享同一 TCP 连接的流量控制
> - **Channel 不是线程安全的**，多线程应使用不同 Channel 实例

### 【如何保证消息的可靠性？】

#### 如何保证消息的可靠性？

![RabbitMQ 4.0 消息可靠性与队列架构全景图](images/rabbitmq-message-reliability-and-queue-architecture-overview-8c876432.png)

消息可能在三个环节出问题：生产者到 Broker、Broker 存储期间、Broker 到消费者。

**1. 生产者到 Broker**

生产者端通常同时处理“是否被 Broker 接收”和“是否成功路由到队列”这两件事：

- **Publisher Confirms**：确认消息是否被 Broker 接收。对于持久化消息路由到持久化队列，确认会等消息持久化；对于 Quorum Queue，确认会等多数副本接受。

  ```java
  channel.confirmSelect();
  channel.addConfirmListener((sequenceNumber, multiple) -> {
      // Broker 已处理该序号对应的消息
  }, (sequenceNumber, multiple) -> {
      // Broker 无法处理该消息，记录日志并按业务策略重试
  });
  ```

- **mandatory + Return Listener**：消息到达 Exchange 但没有匹配队列时，生产者可以收到 return。

  ```java
  channel.basicPublish("exchange", "routingKey",
      true,  // mandatory=true
      null,
      messageBody);

  channel.addReturnListener((replyCode, replyText, exchange, routingKey, properties, body) -> {
      // 消息到达 Exchange，但没有路由到任何队列
      log.error("Message returned: {}", replyText);
  });
  ```

只开 Confirm 不够。路由失败的消息也可能收到 `basic.ack`，因为 Broker 已经处理了这次发布；是否进入业务队列，要靠 mandatory return 或 Alternate Exchange 兜住。

- **事务机制**（不推荐）：同步阻塞，吞吐通常比 Publisher Confirms 差很多。
  - 注意：事务机制和 Confirm 机制是互斥的，两者不能共存

**2. Broker 存储期间**

- `delivery_mode=2`：消息按持久化消息处理。
- `durable=true`：队列元数据可在 Broker 重启后恢复。
- 复制型队列：RabbitMQ 4.x 中，镜像队列已移除；需要复制时主要考虑 Quorum Queue 或 Streams。

只设置持久化并不等于消息一定不丢。生产者还要等 Publisher Confirm，消费者也要使用手动 Ack；否则 Broker 宕机、连接断开、消费失败这些场景仍然可能丢数据或重复消费。

**3. Broker 到消费者**

- **手动 Ack**：`basicAck(deliveryTag, multiple)`，确保消费成功后再确认
- **重试机制**：消费失败时可以 `basicNack` 或 `basicReject`，再根据异常类型决定是否 `requeue`
- **死信队列**：达到最大重试次数或被拒绝后路由到 DLQ，后续再告警、补偿或人工处理
- **幂等性保障**：业务层实现，避免重复消费导致的数据不一致。幂等性具体实现方案参考这篇文章：[接口幂等方案总结](https://javaguide.cn/high-availability/idempotency.html)。

> 注意：Alternate Exchange（备用交换器）也能处理路由失败。配置了备用交换器后，无法路由的消息会被转发过去；如果备用交换器也无法路由，并且消息设置了 mandatory，生产者才会收到 return。

### 【如何保证 RabbitMQ 消息的顺序性？】

#### 如何保证 RabbitMQ 消息的顺序性？

RabbitMQ 的 FIFO 只在单个队列内成立，而且会受到消费者数量、prefetch、重试和重新入队影响。常见处理方式有三种：

**1. 单 Consumer 模式**：一个队列只绑定一个消费者。顺序最好保证，吞吐也最容易成为瓶颈。

**2. 分区有序**：按业务 key（如订单 ID）哈希到不同队列，每个队列由独立消费者处理。同一个业务 key 始终进入同一个队列，就能在提高吞吐的同时保留局部顺序。

分区方案有两个坑：队列扩缩容会改变哈希结果，同一个业务 key 的新老消息可能进不同队列；消费失败后重新入队也可能改变后续投递顺序。强顺序业务最好在业务表里加状态机、版本号或唯一约束，不要只依赖 MQ 投递顺序。

**3. 消费者内部排队**：单个消费者先拉消息，再按业务 key 分发到本地内存队列和 Worker 线程。这个方案要自己处理内存堆积、进程宕机丢失、Ack 时机和背压，生产环境慎用。

### 【如何保证 RabbitMQ 高可用的？】

#### 如何保证 RabbitMQ 高可用的？

RabbitMQ 的高可用要分两层看：集群只能让多个节点共同管理元数据和连接；队列里的消息是否复制，要看队列类型。

RabbitMQ 4.x 里，Classic Queue 是非复制队列；镜像队列已经移除；复制型数据结构主要是 Quorum Queue 和 Streams。还在使用 3.x 的老集群时，才会遇到镜像队列的维护问题。

网络分区也要单独处理。普通集群和旧镜像队列都可能受到网络抖动影响，常见策略是配置 `cluster_partition_handling = pause_minority`，让少数派节点暂停服务，避免两边各自继续写入。Quorum Queue 使用 Raft，一致性更明确，但它也需要多数副本可用，不能把它理解成“任何网络故障都能继续服务”。

**单机模式**

Demo 级别的，一般就是你本地启动了玩玩儿的，没人生产用单机模式。

**普通集群模式**

意思就是在多台机器上启动多个 RabbitMQ 实例，每个机器启动一个。你创建的 queue，只会放在一个 RabbitMQ 实例上，但是每个实例都同步 queue 的元数据（元数据可以认为是 queue 的一些配置信息，通过元数据，可以找到 queue 所在实例）。

你消费的时候，实际上如果连接到了另外一个实例，那么那个实例会从 queue 所在实例上拉取数据过来。这方案主要是提高吞吐量的，就是说让集群中多个节点来服务某个 queue 的读写操作。

**镜像集群模式**（Classic Queue Mirroring，已移除）

镜像队列已在 RabbitMQ 4.0 移除。RabbitMQ 3.8 引入 Quorum Queue 作为替代方案，3.13 版本仍能使用镜像队列，但已经废弃。新项目不要再选镜像队列。

这种模式是 RabbitMQ 早期版本的高可用方案。跟普通集群模式不一样的是，在镜像集群模式下，你创建的 queue，无论元数据还是 queue 里的消息都会存在于多个实例上，每个 RabbitMQ 节点都有这个 queue 的一个完整镜像，包含 queue 的全部数据。每次写消息到 queue 的时候，都会自动把消息同步到多个实例的 queue 上。

它的工作方式大致如下：

- Queue 主节点接收消息，同步到 N 个镜像节点
- 主节点宕机时，最老的镜像节点升级为主节点
- 通过管理控制台新增策略，指定数据同步到所有节点或指定数量的节点

优点：

- 任何机器宕机，其他节点包含该 queue 的完整数据
- Consumer 可以切换到其他节点继续消费

缺点：

- 性能开销大，消息需要同步到所有机器上
- 网络带宽压力和消耗重
- 不是真正的分布式架构，是主从复制

**Quorum Queue**（3.8+）

Quorum Queue 是基于 Raft 协议的复制队列，适合长期存在、对数据安全要求高的队列：

- **基于 Raft 协议**：通过日志复制和选举实现一致性
- **仲裁写入**：需要多数节点确认（N/2 + 1）才认为写入成功
- **复制语义更清楚**：比镜像队列更容易处理主节点故障和网络分区
- **适用场景**：订单、支付、库存扣减等不能轻易丢消息的业务链路

Quorum Queue 不适合所有场景。临时队列、高频创建删除队列、极低延迟、大量长期积压（尤其是百万级以上）、大规模 fanout 这类场景，要优先评估 Classic Queue 或 Streams。官方也建议无论队列数量多少，都要做升级和故障演练。

**声明方式（客户端）**：

Java：

```java
Map args = new HashMap<>();
args.put("x-queue-type", "quorum");
channel.queueDeclare("my-queue", true, false, false, args);
```

Python：

```python
channel.queue_declare(
    queue='my-queue',
    durable=True,
    arguments={'x-queue-type': 'quorum'}
)
```

> `x-queue-type` 必须在队列声明时提供，不能通过 Policy 后续修改。队列类型一旦确定，就不能把已有 classic queue 直接改成 quorum queue。

### 【如何解决消息队列的延时以及过期失效问题？】

#### 如何解决消息队列的延时以及过期失效问题？

RabbitMQ 可以设置消息过期时间（TTL）。如果消息在队列中停留时间超过 TTL，就会过期；配置了 DLX 时会进入死信交换器，否则会被丢弃。

如果数据能从数据库等源头恢复，可以用批量重导做补偿：

1. 高峰期先丢弃无法及时处理的数据，保住系统可用性。
2. 低峰期编写临时程序，从数据库查询缺失数据。
3. 把查到的数据重新发送到 MQ 中，让消费者补偿处理。

**示例场景**：

- 假设 1 万个订单积压在 MQ 中未处理
- 其中 1000 个订单因 TTL 过期被丢弃
- 处理方案：从数据库查询这 1000 个订单，重新发送到 MQ 补偿

这个方案有前提：数据库里必须有完整历史数据，补偿消费要做好幂等，消息积压也要有监控告警。否则临时补偿程序很容易把重复数据或脏数据再打一遍。

### 【生产环境要关注哪些指标？】

#### 生产环境要关注哪些指标？

**1. 内存水位线**

- 监控 `rabbitmq_memory_limit` 占比
- 告警阈值：默认高水位为 0.4（40%）
- 影响：达到高水位后，RabbitMQ 会阻塞发布连接，生产者写入会变慢甚至停住
- 建议配置：

  ```ini
  vm_memory_high_watermark.relative = 0.4
  vm_memory_high_watermark_paging_ratio = 0.5
  ```

**2. 文件句柄消耗**

- 监控 File Descriptors 使用率
- 连接数突增时，文件句柄耗尽会导致新连接失败，严重时会影响节点稳定性
- 高连接数环境要提前调大系统限制，例如 `ulimit -n 100000`

**3. Channel 创建和销毁速率**

- 监控信道的创建与销毁速率
- 高频创建销毁 Channel 会带来额外 CPU 和 Erlang 进程开销
- Channel 应复用，但也不要在单个连接上无限堆，通常控制在几十到一两百以内

**4. 消息积压深度**

- 监控 Queue 消息数量和 Consumer Lag
- 告警阈值：根据业务定义（如 > 10,000 条）
- 工具：RabbitMQ Management UI、Prometheus + Grafana

**5. 磁盘空间与 I/O**

- 监控磁盘剩余空间和 IOPS
- 告警阈值：磁盘剩余 < 20% 触发告警
- Quorum Queue 对磁盘 I/O 要求较高，建议使用 NVMe SSD

### 【RabbitMQ 使用中有哪些常见误区？】

#### RabbitMQ 使用中有哪些常见误区？

**误区 1：所有队列都用 Quorum Queue**

Quorum Queue 会把消息复制到多个副本，并且按 Raft 语义确认写入。它适合高可靠队列，但并不适合临时队列、极低延迟、大量短生命周期队列、超大积压和大规模 fanout。吞吐优先时，可以评估非复制 Classic Queue 或 Streams；可靠性优先时，再看 Quorum Queue。

**误区 2：Prefetch Count 越大越好**

Prefetch 太大时，消费者会提前拿走大量消息。服务端队列看起来不堆积，但消息都卡在消费者本地的 Unacked 状态，别的消费者接不到，客户端内存也可能被拖垮。

可以先给一个保守值，再按处理耗时和吞吐压测调整：

```java
channel.basicQos(20);
```

**误区 3：延迟队列插件可以当定时任务系统用**

`rabbitmq-delayed-message-exchange` 适合短时间延迟，不适合长期调度，也不适合堆积十万、百万级延迟消息。大规模延迟任务应该把调度状态放到数据库、Redis、时间轮或调度系统里，到点后再投递 MQ。

**误区 4：网络分区不会发生在我们环境**

跨机房部署、跨可用区部署、交换机抖动都可能触发网络分区。普通集群和旧镜像队列要配置分区恢复策略；需要复制队列时优先评估 Quorum Queue，但也要确认多数副本能落在可靠的可用区拓扑里。

**误区 5：开启事务机制后就不用 Publisher Confirms**

事务机制是同步阻塞模式，官方文档也明确提到它会明显降低吞吐。生产者侧通常优先使用 Publisher Confirms，再配合 mandatory return 或 Alternate Exchange 处理路由失败。

## 网络协议

> TCP/UDP、HTTP 演进、WebSocket 与长连接——Agent 流式输出必考（51 题）

### 【计算机网络基础】

#### 网络分层模型

#### OSI 七层模型是什么？每一层的作用是什么？

**OSI 七层模型** 是国际标准化组织提出的一个网络分层模型，其大体结构以及每一层提供的功能如下图所示：

![OSI 七层模型各层功能划分](images/osi-7-model-955bfdf5.png)

每一层都专注做一件事情，并且每一层都需要使用下一层提供的功能比如传输层需要使用网络层提供的路由和寻址功能，这样传输层才知道把数据传输到哪里去。

**OSI 的七层体系结构概念清楚，理论也很完整，但是它比较复杂而且不实用，而且有些功能在多个层中重复出现。**

上面这种图可能比较抽象，再来一个比较生动的图片。下面这个图片是我在国外的一个网站上看到的，非常赞！

![osi七层模型2](images/osi____2-8a5da370.png)

#### ⭐️ TCP/IP 四层模型是什么？每一层的作用是什么？

**TCP/IP 四层模型** 是目前被广泛采用的一种模型，我们可以将 TCP/IP 模型看作是 OSI 七层模型的精简版本，由以下 4 层组成：

1. 应用层
2. 传输层
3. 网络层
4. 网络接口层

需要注意的是，我们并不能将 TCP/IP 四层模型 和 OSI 七层模型完全精确地匹配起来，不过可以简单将两者对应起来，如下图所示：

![TCP/IP 四层模型与 OSI 模型的对应关系](images/tcp-ip-4-model-6284e045.png)

关于每一层作用的详细介绍，请看 [OSI 和 TCP/IP 网络分层模型详解（基础）](https://javaguide.cn/cs-basics/network/osi-and-tcp-ip-model.html) 这篇文章。

#### 为什么网络要分层？

说到分层，我们先从我们平时使用框架开发一个后台程序来说，我们往往会按照每一层做不同的事情的原则将系统分为三层（复杂的系统分层会更多）:

1. Repository（数据库操作）
2. Service（业务操作）
3. Controller（前后端数据交互）

**复杂的系统需要分层，因为每一层都需要专注于一类事情。网络分层的原因也是一样，每一层只专注于做一类事情。**

好了，再来说回：“为什么网络要分层？”。我觉得主要有 3 方面的原因：

1. **各层之间相互独立**：各层之间相互独立，各层之间不需要关心其他层是如何实现的，只需要知道自己如何调用下层提供好的功能就可以了（可以简单理解为接口调用）**。这个和我们对开发时系统进行分层是一个道理。**
2. **提高了灵活性和可替换性**：每一层都可以使用最适合的技术来实现，你只需要保证你提供的功能以及暴露的接口的规则没有改变就行了。并且，每一层都可以根据需要进行修改或替换，而不会影响到整个网络的结构。**这个和我们平时开发系统的时候要求的高内聚、低耦合的原则也是可以对应上的。**
3. **大问题化小**：分层可以将复杂的网络问题分解为许多比较小的、界线比较清晰简单的小问题来处理和解决。这样使得复杂的计算机网络系统变得易于设计，实现和标准化。 **这个和我们平时开发的时候，一般会将系统功能分解，然后将复杂的问题分解为容易理解的更小的问题是相对应的，这些较小的问题具有更好的边界（目标和接口）定义。**

我想到了计算机世界非常非常有名的一句话，这里分享一下：

> 计算机科学领域的任何问题都可以通过增加一个间接的中间层来解决，计算机整个体系从上到下都是按照严格的层次结构设计的。

#### 常见网络协议

#### ⭐️ 应用层有哪些常见的协议？

![应用层常见协议](images/application-layer-protocol-3c7d8468.png)

- **HTTP（Hypertext Transfer Protocol，超文本传输协议）**：是一种用于传输超文本和多媒体内容的应用层协议，主要为 Web 客户端与服务器之间的通信而设计。HTTP/1.x 和 HTTP/2 通常基于 TCP，HTTP/3 则运行在基于 UDP 的 QUIC 之上。
- **SMTP（Simple Mail Transfer Protocol，简单邮件发送协议）**：基于 TCP 协议，是一种用于发送电子邮件的协议。注意 ⚠️：SMTP 协议只负责邮件的发送，而不是接收。要从邮件服务器接收邮件，需要使用 POP3 或 IMAP 协议。
- **POP3/IMAP（邮件接收协议）**：基于 TCP 协议，两者都是负责邮件接收的协议。IMAP 协议是比 POP3 更新的协议，它在功能和性能上都更加强大。IMAP 支持邮件搜索、标记、分类、归档等高级功能，而且可以在多个设备之间同步邮件状态。几乎所有现代电子邮件客户端和服务器都支持 IMAP。
- **FTP（File Transfer Protocol，文件传输协议）**：基于 TCP 协议，是一种用于在计算机之间传输文件的协议，可以屏蔽操作系统和文件存储方式。注意 ⚠️：FTP 是一种不安全的协议，因为它在传输过程中不会对数据进行加密。建议在传输敏感数据时使用更安全的协议，如 SFTP。
- **Telnet（远程登陆协议）**：基于 TCP 协议，用于通过一个终端登陆到其他服务器。Telnet 协议的最大缺点之一是所有数据（包括用户名和密码）均以明文形式发送，这有潜在的安全风险。这就是为什么如今很少使用 Telnet，而是使用一种称为 SSH 的非常安全的网络传输协议的主要原因。
- **SSH（Secure Shell Protocol，安全的网络传输协议）**：基于 TCP 协议，通过加密和认证机制实现安全的访问和文件传输等业务
- **RTP（Real-time Transport Protocol，实时传输协议）**：通常基于 UDP 协议，但也支持 TCP 协议。它提供了端到端的实时传输数据的功能，但不包含资源预留存、不保证实时传输质量，这些功能由 WebRTC 实现。
- **DNS（Domain Name System，域名管理系统）**：通常基于 UDP 协议（端口 53），用于解决域名和 IP 地址的映射问题。当响应数据过大或进行区域传送时会改用 TCP。

关于这些协议的详细介绍请看 [应用层常见协议总结（应用层）](https://github.com/Snailclimb/JavaGuide/blob/main/docs/application-layer-protocol.md) 这篇文章。

#### 传输层有哪些常见的协议？

![传输层常见协议](images/transport-layer-protocol-77ea5f52.png)

- **TCP（Transmission Control Protocol，传输控制协议）**：提供 **面向连接** 的，**可靠** 的数据传输服务。
- **UDP（User Datagram Protocol，用户数据协议）**：提供 **无连接** 的，**尽最大努力** 的数据传输服务（不保证数据传输的可靠性），简单高效。

#### 网络层有哪些常见的协议？

![网络层常见协议](images/nerwork-layer-protocol.png)

- **IP（Internet Protocol，网际协议）**：TCP/IP 协议中最重要的协议之一，属于网络层的协议，主要作用是定义数据包的格式、对数据包进行路由和寻址，以便它们可以跨网络传播并到达正确的目的地。目前 IP 协议主要分为两种，一种是过去的 IPv4，另一种是较新的 IPv6，目前这两种协议都在使用，但后者已经被提议来取代前者。
- **ARP（Address Resolution Protocol，地址解析协议）**：ARP 协议解决的是网络层地址和链路层地址之间的转换问题。因为一个 IP 数据报在物理上传输的过程中，总是需要知道下一跳（物理上的下一个目的地）该去往何处，但 IP 地址属于逻辑地址，而 MAC 地址才是物理地址，ARP 协议解决了 IP 地址转 MAC 地址的一些问题。
- **ICMP（Internet Control Message Protocol，互联网控制报文协议）**：一种用于传输网络状态和错误消息的协议，常用于网络诊断和故障排除。例如，Ping 工具就使用了 ICMP 协议来测试网络连通性。
- **NAT（Network Address Translation，网络地址转换协议）**：NAT 协议的应用场景如同它的名称——网络地址转换，应用于内部网到外部网的地址转换过程中。具体地说，在一个小的子网（局域网，LAN）内，各主机使用的是同一个 LAN 下的 IP 地址，但在该 LAN 以外，在广域网（WAN）中，需要一个统一的 IP 地址来标识该 LAN 在整个 Internet 上的位置。
- **OSPF（Open Shortest Path First，开放式最短路径优先）**：一种内部网关协议（Interior Gateway Protocol，IGP），也是广泛使用的一种动态路由协议，基于链路状态算法，考虑了链路的带宽、延迟等因素来选择最佳路径。
- **RIP（Routing Information Protocol，路由信息协议）**：一种内部网关协议（Interior Gateway Protocol，IGP），也是一种动态路由协议，基于距离向量算法，使用固定的跳数作为度量标准，选择跳数最少的路径作为最佳路径。
- **BGP（Border Gateway Protocol，边界网关协议）**：一种用来在路由选择域之间交换网络层可达性信息（Network Layer Reachability Information，NLRI）的路由选择协议，具有高度的灵活性和可扩展性。

### 【HTTP】

#### ⭐️ 从输入 URL 到页面展示到底发生了什么？（非常重要）

> 类似的问题：打开一个网页，整个过程会使用哪些协议？

先来看一张图（来源于《图解 HTTP》）：

上图有一个错误需要注意：是 OSPF 不是 OPSF。OSPF（Open Shortest Path First，ospf）开放最短路径优先协议，是由 Internet 工程任务组开发的路由选择协议

总体来说分为以下几个步骤:

1. 在浏览器中输入指定网页的 URL。
2. 浏览器通过 DNS 协议，获取域名对应的 IP 地址。
3. 浏览器根据 IP 地址和端口号，向目标服务器发起一个 TCP 连接请求。
4. 浏览器在 TCP 连接上，向服务器发送一个 HTTP 请求报文，请求获取网页的内容。
5. 服务器收到 HTTP 请求报文后，处理请求，并返回 HTTP 响应报文给浏览器。
6. 浏览器收到 HTTP 响应报文后，解析响应体中的 HTML 代码，渲染网页的结构和样式，同时根据 HTML 中的其他资源的 URL（如图片、CSS、JS 等），再次发起 HTTP 请求，获取这些资源的内容，直到网页完全加载显示。
7. 浏览器在不需要和服务器通信时，可以主动关闭 TCP 连接，或者等待服务器的关闭请求。

详细介绍可以查看这篇文章：[访问网页的全过程（知识串联）](https://javaguide.cn/cs-basics/network/the-whole-process-of-accessing-web-pages.html)（强烈推荐）。

#### ⭐️ HTTP 状态码有哪些？

HTTP 状态码用于描述 HTTP 请求的结果，比如 2xx 就代表请求被成功处理。

![常见 HTTP 状态码](images/http-status-code-4a9382f4.png)

关于 HTTP 状态码更详细的总结，可以看我写的这篇文章：[HTTP 常见状态码总结（应用层）](https://javaguide.cn/cs-basics/network/http-status-codes.html)。

#### HTTP Header 中常见的字段有哪些？

| 请求头字段名        | 说明                                                                                                                                                                          | 示例                                                                             |
| :------------------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------- |
| Accept              | 能够接受的回应内容类型（Content-Types）。                                                                                                                                     | Accept: text/plain                                                               |
| Accept-Charset      | 能够接受的字符集                                                                                                                                                              | Accept-Charset: utf-8                                                            |
| Accept-Datetime     | 能够接受的按照时间来表示的版本                                                                                                                                                | Accept-Datetime: Thu, 31 May 2007 20:35:00 GMT                                   |
| Accept-Encoding     | 能够接受的编码方式列表。参考 HTTP 压缩。                                                                                                                                      | Accept-Encoding: gzip, deflate                                                   |
| Accept-Language     | 能够接受的回应内容的自然语言列表。                                                                                                                                            | Accept-Language: en-US                                                           |
| Authorization       | 用于超文本传输协议的认证的认证信息                                                                                                                                            | Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==                                |
| Cache-Control       | 用来指定在这次的请求/响应链中的所有缓存机制 都必须 遵守的指令                                                                                                                 | Cache-Control: no-cache                                                          |
| Connection          | 该浏览器想要优先使用的连接类型                                                                                                                                                | Connection: keep-alive                                                           |
| Content-Length      | 以八位字节数组（8 位的字节）表示的请求体的长度                                                                                                                                | Content-Length: 348                                                              |
| Content-MD5         | 请求体的内容的二进制 MD5 散列值，以 Base64 编码的结果                                                                                                                         | Content-MD5: Q2hlY2sgSW50ZWdyaXR5IQ==                                            |
| Content-Type        | 请求体的多媒体类型（用于 POST 和 PUT 请求中）                                                                                                                                 | Content-Type: application/x-www-form-urlencoded                                  |
| Cookie              | 之前由服务器通过 Set-Cookie（下文详述）发送的一个超文本传输协议 Cookie                                                                                                        | Cookie: $Version=1; Skin=new;                                                    |
| Date                | 发送该消息的日期和时间（按照 RFC 7231 中定义的“超文本传输协议日期”格式来发送）                                                                                                | Date: Tue, 15 Nov 1994 08:12:31 GMT                                              |
| Expect              | 表明客户端要求服务器做出特定的行为                                                                                                                                            | Expect: 100-continue                                                             |
| From                | 发起此请求的用户的邮件地址                                                                                                                                                    | From: `user@example.com`                                                         |
| Host                | 服务器的域名（用于虚拟主机），以及服务器所监听的传输控制协议端口号。如果所请求的端口是对应的服务的标准端口，则端口号可被省略。                                                | Host: en.wikipedia.org                                                           |
| If-Match            | 仅当客户端提供的实体与服务器上对应的实体相匹配时，才进行对应的操作。主要作用是用于像 PUT 这样的方法中，仅当从用户上次更新某个资源以来，该资源未被修改的情况下，才更新该资源。 | If-Match: "737060cd8c284d8af7ad3082f209582d"                                     |
| If-Modified-Since   | 允许服务器在请求的资源自指定的日期以来未被修改的情况下返回 `304 Not Modified` 状态码                                                                                          | If-Modified-Since: Sat, 29 Oct 1994 19:43:31 GMT                                 |
| If-None-Match       | 允许服务器在请求的资源的 ETag 未发生变化的情况下返回 `304 Not Modified` 状态码                                                                                                | If-None-Match: "737060cd8c284d8af7ad3082f209582d"                                |
| If-Range            | 如果该实体未被修改过，则向我发送我所缺少的那一个或多个部分；否则，发送整个新的实体                                                                                            | If-Range: "737060cd8c284d8af7ad3082f209582d"                                     |
| If-Unmodified-Since | 仅当该实体自某个特定时间以来未被修改的情况下，才发送回应。                                                                                                                    | If-Unmodified-Since: Sat, 29 Oct 1994 19:43:31 GMT                               |
| Max-Forwards        | 限制该消息可被代理及网关转发的次数。                                                                                                                                          | Max-Forwards: 10                                                                 |
| Origin              | 发起一个针对跨来源资源共享的请求。                                                                                                                                            | `Origin: http://www.example-social-network.com`                                  |
| Pragma              | 与具体的实现相关，这些字段可能在请求/回应链中的任何时候产生多种效果。                                                                                                         | Pragma: no-cache                                                                 |
| Proxy-Authorization | 用来向代理进行认证的认证信息。                                                                                                                                                | Proxy-Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==                          |
| Range               | 仅请求某个实体的一部分。字节偏移以 0 开始。参见字节服务。                                                                                                                     | Range: bytes=500-999                                                             |
| Referer             | 表示浏览器所访问的前一个页面，正是那个页面上的某个链接将浏览器带到了当前所请求的这个页面。                                                                                    | `Referer: http://en.wikipedia.org/wiki/Main_Page`                                |
| TE                  | 浏览器预期接受的传输编码方式：可使用回应协议头 Transfer-Encoding 字段中的值；                                                                                                 | TE: trailers, deflate                                                            |
| Upgrade             | 要求服务器升级到另一个协议。                                                                                                                                                  | Upgrade: HTTP/2.0, SHTTP/1.3, IRC/6.9, RTA/x11                                   |
| User-Agent          | 浏览器的浏览器身份标识字符串                                                                                                                                                  | User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:12.0) Gecko/20100101 Firefox/21.0 |
| Via                 | 向服务器告知，这个请求是由哪些代理发出的。                                                                                                                                    | Via: 1.0 fred, 1.1 example.com (Apache/1.1)                                      |
| Warning             | 一个一般性的警告，告知，在实体内容体中可能存在错误。                                                                                                                          | Warning: 199 Miscellaneous warning                                               |

#### ⭐️ HTTP 和 HTTPS 有什么区别？（重要）

![HTTP 和 HTTPS 对比](images/http-vs-https-99f29ca0.png)

- **端口号**：HTTP 默认是 80，HTTPS 默认是 443。
- **URL 前缀**：HTTP 的 URL 前缀是 `http://`，HTTPS 的 URL 前缀是 `https://`。
- **安全性和传输方式**：未使用 TLS 的 HTTP 默认不提供机密性、完整性和对端身份认证。HTTPS 使用 TLS 保护 HTTP；HTTP/1.1 和 HTTP/2 通常使用 TLS over TCP，HTTP/3 使用集成 TLS 1.3 的 QUIC。TLS 握手负责认证对端并建立流量密钥，后续数据由对称 AEAD 算法保护。证书主要用于身份认证，不能笼统地说“证书加密了对称密钥”。
- **SEO（搜索引擎优化）**：搜索引擎通常会更青睐使用 HTTPS 协议的网站，因为 HTTPS 能够提供更高的安全性和用户隐私保护。使用 HTTPS 协议的网站在搜索结果中可能会被优先显示，从而对 SEO 产生影响。

关于 HTTP 和 HTTPS 更详细的对比总结，可以看我写的这篇文章：[HTTP vs HTTPS（应用层）](https://javaguide.cn/cs-basics/network/http-vs-https.html)。

#### HTTPS 握手里的 RSA 和 ECDHE，到底差在哪？（应用层）

RSA 和 ECDHE 的核心区别在于：**会话密钥材料是“传过去的”，还是“协商出来的”**。

在 TLS 1.2 的静态 RSA 握手里，客户端生成 `PreMasterSecret`，用服务器证书里的 RSA 公钥加密后发给服务端，服务端再用 RSA 私钥解密。问题是，如果攻击者保存了当年的握手流量，后来服务器私钥又泄漏，就可能回头解出历史会话密钥，所以它没有前向安全。

ECDHE 不直接传输共享秘密。客户端和服务端各自生成临时密钥对，交换临时公钥后，双方本地算出同一个共享秘密。服务器证书私钥主要用于签名认证，证明临时参数没被中间人替换，而不是用来解密会话密钥。

所以一句话总结：**RSA 是客户端把秘密加密送过去；ECDHE 是双方用临时密钥协商出秘密。ECDHE 支持前向安全，也因此成为现代 HTTPS 的主流方向。**

详细介绍：[HTTPS 握手里的 RSA 和 ECDHE，到底差在哪？（应用层）](https://github.com/Snailclimb/JavaGuide/blob/main/docs/https-rsa-vs-ecdhe)

#### ⭐️ 有了 HTTP，为什么还要 RPC？

HTTP 和 RPC 不是谁取代谁的关系，也不是谁更高级的问题。

HTTP 能调服务，RPC 也能调服务。真正的区别在于，你是想把远程调用当成一次“资源访问”，还是当成一次“方法调用”。

如果是对外接口，比如 Web、App、第三方系统接入，HTTP 通常更合适。它通用、好调试、接入成本低，别人拿 Postman、curl 就能测。  
如果是公司内部服务互调，尤其是服务多、调用链长、接口频繁调用，还要考虑服务发现、超时、重试、负载均衡、链路追踪这些问题，RPC 会更顺手一些。它不是单纯为了快，而是把内部服务调用里的很多麻烦事一起处理掉。

所以，别再简单背“HTTP 对外，RPC 对内”了。

这句话可以帮助入门，但真做项目时，还得看你的调用对象、团队基础设施、排查成本、性能要求和后续维护成本。

系统规模不大，用 HTTP 已经跑得很稳，就别为了“看起来更微服务”强上 RPC。

内部调用越来越复杂，HTTP SDK、网关、监控、重试这些东西越补越多，那就可以认真考虑 RPC。

一句话：**HTTP 没那么弱，RPC 也没那么神。选哪个，主要看它能不能用更低成本解决你现在的问题。**

详细介绍：[⭐️有了HTTP，为什么还要RPC？](https://github.com/Snailclimb/JavaGuide/blob/main/docs/http-vs-rpc.md)

#### HTTP/1.0 和 HTTP/1.1 有什么区别？

![HTTP/1.0 和 HTTP/1.1 对比](images/http1.0-vs-http1.1-4e93892e.png)

- **连接方式**：HTTP/1.0 为短连接，HTTP/1.1 支持长连接。HTTP 协议的长连接和短连接，实质上是 TCP 协议的长连接和短连接。
- **状态响应码**：HTTP/1.1 中新加入了大量的状态码，光是错误响应状态码就新增了 24 种。比如说，`100 (Continue)`——允许客户端在发送较大请求体前确认服务器愿意继续接收，`206 (Partial Content)`——范围请求的标识码，`409 (Conflict)`——请求与当前资源的规定冲突，`410 (Gone)`——目标资源已不再可用，这种状态很可能是永久的，并且服务器不知道可用的转发地址。
- **缓存机制**：在 HTTP/1.0 中主要使用 Header 里的 If-Modified-Since,Expires 来做为缓存判断的标准，HTTP/1.1 则引入了更多的缓存控制策略例如 Entity tag，If-Unmodified-Since, If-Match, If-None-Match 等更多可供选择的缓存头来控制缓存策略。
- **带宽**：HTTP/1.0 中，存在一些浪费带宽的现象，例如客户端只是需要某个对象的一部分，而服务器却将整个对象送过来了，并且不支持断点续传功能，HTTP/1.1 则在请求头引入了 range 头域，它允许只请求资源的某个部分，即返回码是 206（Partial Content），这样就方便了开发者自由的选择以便于充分利用带宽和连接。
- **Host 头（Host Header）处理**：HTTP/1.1 引入了 Host 头字段，允许在同一 IP 地址上托管多个域名，从而支持虚拟主机的功能。而 HTTP/1.0 没有 Host 头字段，无法实现虚拟主机。

关于 HTTP/1.0 和 HTTP/1.1 更详细的对比总结，可以看我写的这篇文章：[HTTP/1.0 vs HTTP/1.1（应用层）](https://javaguide.cn/cs-basics/network/http1.0-vs-http1.1.html)。

#### ⭐️ HTTP/1.1 和 HTTP/2.0 有什么区别？

![HTTP/1.0 和 HTTP/1.1 对比](images/http1.1-vs-http2.0-c5f37e83.png)

- **多路复用（Multiplexing）**：HTTP/2.0 在同一连接上可以同时传输多个请求和响应（可以看作是 HTTP/1.1 中长链接的升级版本），互不干扰。HTTP/1.1 则使用串行方式，每个请求和响应都需要独立的连接，而浏览器为了控制资源会有 6-8 个 TCP 连接的限制。这使得 HTTP/2.0 在处理多个请求时更加高效，减少了网络延迟和提高了性能。
- **二进制帧（Binary Frames）**：HTTP/2.0 使用二进制帧进行数据传输，而 HTTP/1.1 则使用文本格式的报文。二进制帧更加紧凑和高效，减少了传输的数据量和带宽消耗。
- **队头阻塞**：HTTP/2 引入了多路复用技术，允许多个请求和响应在单个 TCP 连接上并行交错传输，解决了 HTTP/1.1 应用层的队头阻塞问题，但 HTTP/2 依然受到 TCP 层队头阻塞的影响。
- **头部压缩（Header Compression）**：HTTP/1.1 支持 `Body` 压缩，`Header` 不支持压缩。HTTP/2.0 支持对 `Header` 压缩，使用了专门为 `Header` 压缩而设计的 HPACK 算法，减少了网络开销。
- **服务器推送（Server Push）**：HTTP/2.0 支持服务器推送，可以在客户端请求一个资源时，将其他相关资源一并推送给客户端，从而减少了客户端的请求次数和延迟。而 HTTP/1.1 需要客户端自己发送请求来获取相关资源。

HTTP/2.0 多路复用效果图（图源： [HTTP/2 For Web Developers](https://blog.cloudflare.com/http-2-for-web-developers/)）：

![HTTP/2 在单个 TCP 连接上多路复用多个请求和响应](images/http2.0-multiplexing-5b8a007d.png)

可以看到，HTTP/2 的多路复用机制允许多个请求和响应共享一个 TCP 连接，从而避免了 HTTP/1.1 在应对并发请求时需要建立多个并行连接的情况，减少了重复连接建立和维护的额外开销。而在 HTTP/1.1 中，尽管支持持久连接，但为了缓解队头阻塞问题，浏览器通常会为同一域名建立多个并行连接。

#### HTTP/2.0 和 HTTP/3.0 有什么区别？

![HTTP/2.0 和 HTTP/3.0 对比](images/http2.0-vs-http3.0-6ad26f15.png)

- **传输协议**：HTTP/2 基于 TCP，HTTP/3 则把 HTTP 语义映射到 QUIC。QUIC 构建在 UDP 之上，在传输层实现可靠交付、拥塞控制、流量控制和 TLS 1.3 安全保护。
- **连接建立**：HTTP/2 的 HTTPS 连接需要先建立 TCP 连接，再完成 TLS 握手；HTTP/3 把传输参数协商和 TLS 1.3 握手结合在 QUIC 建连过程中。新的 QUIC 连接通常使用 1-RTT；0-RTT 只适用于客户端持有先前连接状态的恢复场景，而且早期数据存在重放风险。比较延迟时还要统一采用“何时可发送首个请求”或“何时收到首字节”等同一个指标。
- **头部压缩**：HTTP/2.0 使用 HPACK 算法进行头部压缩，而 HTTP/3.0 使用更高效的 QPACK 头压缩算法。
- **队头阻塞**：HTTP/2 的多个流复用同一个 TCP 连接，TCP 丢包会阻塞这条连接上的所有流。QUIC 在流之间提供独立的可靠有序交付；某个流的数据丢失后，该流会等待缺失数据恢复，但通常不会阻止其他流继续前进。
- **连接迁移**：QUIC 使用独立于 IP/端口四元组的 Connection ID 标识连接。Connection ID 不是固定 64 位：QUIC v1 可以使用零长度到 20 字节的 Connection ID，端点还可以签发和退役多个 Connection ID。网络地址变化后，端点可以验证新路径并维持同一逻辑连接。
- **错误恢复**：HTTP/3.0 具有更好的错误恢复机制，当出现丢包、延迟等网络问题时，可以更快地进行恢复和重传。而 HTTP/2.0 则需要依赖于 TCP 的错误恢复机制。
- **安全性**：HTTP/2 通常使用 TLS 保护 HTTP 头部和数据负载，但 IP、TCP 头以及 TLS 记录层的外部头字段仍然可见。QUIC 使用 TLS 派生的密钥保护报文载荷，并对包号和部分首字节字段做头部保护；IP/UDP 头和部分 QUIC 头字段仍然可见，Version Negotiation 等报文也不具备同样的密码学保护，因此不能说 QUIC 加密了整个数据包的全部报文头。

HTTP/1.0、HTTP/2.0 和 HTTP/3.0 的协议栈比较：

![HTTP/1、HTTP/2 和 HTTP/3 协议栈对比](images/http-3-implementation-ab73b085.png)

下图是一个更详细的 HTTP/2.0 和 HTTP/3.0 对比图：

![HTTP/2.0 和 HTTP/3.0 详细对比图](images/http2-and-http3-stacks-comparison-164f4e33.png)

从上图可以看出：

- **HTTP/2.0**：使用 TCP 作为传输协议、使用 HPACK 进行头部压缩、依赖 TLS 进行加密。
- **HTTP/3.0**：使用基于 UDP 的 QUIC 协议、使用更高效的 QPACK 进行头部压缩、在 QUIC 中直接集成了 TLS。QUIC 协议具备连接迁移、拥塞控制与避免、流量控制等特性。

关于 HTTP/1.0 -> HTTP/3.0 更详细的演进介绍，推荐阅读[HTTP1 到 HTTP3 的工程优化](https://dbwu.tech/posts/http_evolution/)。

#### HTTP/1.1 和 HTTP/2.0 的队头阻塞有什么不同？

HTTP/1.1 队头阻塞的主要原因是无法多路复用：

- 在一个 TCP 连接中，资源的请求和响应是按顺序处理的。如果一个大的资源（如一个大文件）正在传输，后续的小资源（如较小的 CSS 文件）需要等待前面的资源传输完成后才能被发送。
- 如果浏览器需要同时加载多个资源（如多个 CSS、JS 文件等），它通常会开启多个并行的 TCP 连接（一般限制为 6 个）。但每个连接仍然受限于顺序的请求-响应机制，因此仍然会发生 **应用层的队头阻塞**。

虽然 HTTP/2.0 引入了多路复用技术，允许多个请求和响应在单个 TCP 连接上并行交错传输，解决了 **HTTP/1.1 应用层的队头阻塞问题**，但 HTTP/2.0 依然受到 **TCP 层队头阻塞** 的影响：

- HTTP/2.0 通过帧（frame）机制将每个资源分割成小块，并为每个资源分配唯一的流 ID，这样多个资源的数据可以在同一 TCP 连接中交错传输。
- TCP 作为传输层协议，要求数据按顺序交付。如果某个数据包在传输过程中丢失，即使后续的数据包已经到达，也必须等待丢失的数据包重传后才能继续处理。这种传输层的顺序性导致了 **TCP 层的队头阻塞**。
- 举例来说，如果 HTTP/2 的一个 TCP 数据包中携带了多个资源的数据（例如 JS 和 CSS），而该数据包丢失了，那么后续数据包中的所有资源数据都需要等待丢失的数据包重传回来，导致所有流（streams）都被阻塞。

最后，来一张表格总结补充一下：

| **方面**       | **HTTP/1.1 的队头阻塞**                  | **HTTP/2.0 的队头阻塞**                                            |
| -------------- | ---------------------------------------- | ------------------------------------------------------------------ |
| **层级**       | 应用层（HTTP 协议本身的限制）            | 传输层（TCP 协议的限制）                                           |
| **根本原因**   | 无法多路复用，请求和响应必须按顺序传输   | TCP 要求数据包按顺序交付，丢包时阻塞整个连接                       |
| **受影响范围** | 单个 HTTP 请求/响应会阻塞后续请求/响应。 | 单个 TCP 包丢失会影响所有 HTTP/2.0 流（依赖于同一个底层 TCP 连接） |
| **缓解方法**   | 开启多个并行的 TCP 连接                  | 减少网络掉包或者使用基于 UDP 的 QUIC 协议                          |
| **影响场景**   | 每次都会发生，尤其是大文件阻塞小文件时。 | 丢包率较高的网络环境下更容易发生。                                 |

#### ⭐️ HTTP 是不保存状态的协议，如何保存用户状态？

HTTP 协议本身是 **无状态的（stateless）**。这意味着服务器默认情况下无法区分两个连续的请求是否来自同一个用户，或者同一个用户之前的操作是什么。这就像一个“健忘”的服务员，每次你跟他说话，他都不知道你是谁，也不知道你之前点过什么菜。

但在实际的 Web 应用中，比如网上购物、用户登录等场景，我们显然需要记住用户的状态（例如购物车里的商品、用户的登录信息）。为了解决这个问题，主要有以下几种常用机制：

**方案一：Session（会话）配合 Cookie（主流方式）：**

![Session 配合 Cookie 保存用户登录状态的流程](images/session-cookie-authentication-process-bd689be9.png)

这可以说是最经典也是最常用的方法了。基本流程是这样的：

1. 用户向服务器发送用户名、密码、验证码用于登陆系统。
2. 服务器验证通过后，会为这个用户创建一个专属的 Session 对象（可以理解为服务器上的一块内存，存放该用户的状态数据，如购物车、登录信息等）存储起来，并给这个 Session 分配一个唯一的 `SessionID`。
3. 服务器通过 HTTP 响应头中的 `Set-Cookie` 指令，把这个 `SessionID` 发送给用户的浏览器。
4. 浏览器接收到 `SessionID` 后，会将其以 Cookie 的形式保存在本地。当用户保持登录状态时，每次向该服务器发请求，浏览器都会自动带上这个存有 `SessionID` 的 Cookie。
5. 服务器收到请求后，从 Cookie 中拿出 `SessionID`，就能找到之前保存的那个 Session 对象，从而知道这是哪个用户以及他之前的状态了。

使用 Session 的时候需要注意下面几个点：

- **客户端 Cookie 支持**：依赖 Session 的核心功能要确保用户浏览器开启了 Cookie。
- **Session 过期管理**：合理设置 Session 的过期时间，平衡安全性和用户体验。
- **Session ID 安全**：为包含 `SessionID` 的 Cookie 设置 `HttpOnly` 标志可以防止客户端脚本（如 JavaScript）窃取，设置 Secure 标志可以保证 `SessionID` 只在 HTTPS 连接下传输，增加安全性。

Session 数据本身存储在服务器端。常见的存储方式有：

- **服务器内存**：实现简单，访问速度快，但服务器重启数据会丢失，且不利于多服务器间的负载均衡。这种方式适合简单且用户量不大的业务场景。
- **数据库（如 MySQL, PostgreSQL）**：数据持久化，但读写性能相对较低，一般不会使用这种方式。
- **分布式缓存（如 Redis）**：性能高，支持分布式部署，是目前大规模应用中非常主流的方案。

**方案二：当 Cookie 被禁用时：URL 重写（URL Rewriting）**

如果用户的浏览器禁用了 Cookie，或者某些情况下不便使用 Cookie，还有一种备选方案是 URL 重写。这种方式会将 `SessionID` 直接附加到 URL 的末尾，作为参数传递。例如：。服务器端会解析 URL 中的 `sessionid` 参数来获取 `SessionID`，进而找到对应的 Session 数据。

这种方法一般不会使用，存在以下缺点：

- URL 会变长且不美观；
- `SessionID` 暴露在 URL 中，安全性较低（容易被复制、分享或记录在日志中）；
- 对搜索引擎优化（SEO）可能不友好。

**方案三：Token-based 认证（如 JWT - JSON Web Tokens）**

这是一种越来越流行的无状态认证方式，尤其适用于前后端分离的架构和微服务。

![JWT 身份验证示意图](images/jwt-authentication_20process-c0784a69.png)

以 JWT 为例（普通 Token 方案也可以），简化后的步骤如下：

1. 用户向服务器发送用户名、密码以及验证码用于登陆系统。
2. 如果用户名、密码以及验证码校验正确的话，服务端会返回已经签名的 Token，也就是 JWT。
3. 客户端收到 Token 后自己保存起来（比如浏览器的 `localStorage`）。
4. 用户以后每次向后端发请求都在 Header 中带上这个 JWT。
5. 服务端检查 JWT 并从中获取用户相关信息。

JWT 详细介绍可以查看这两篇文章：

- [JWT 基础概念详解](https://javaguide.cn/system-design/security/jwt-intro.html)
- [JWT 身份认证优缺点分析](https://javaguide.cn/system-design/security/advantages-and-disadvantages-of-jwt.html)

总结来说，虽然 HTTP 本身是无状态的，但通过 Cookie + Session、URL 重写或 Token 等机制，我们能够有效地在 Web 应用中跟踪和管理用户状态。其中，**Cookie + Session 是最传统也最广泛使用的方式，而 Token-based 认证则在现代 Web 应用中越来越受欢迎。**

#### URI 和 URL 的区别是什么？

- URI（Uniform Resource Identifier）是统一资源标志符，可以唯一标识一个资源。
- URL（Uniform Resource Locator）是统一资源定位符，可以提供该资源的路径。它是一种具体的 URI，即 URL 可以用来标识一个资源，而且还指明了如何 locate 这个资源。

URI 的作用像身份证号一样，URL 的作用更像家庭住址一样。URL 是一种具体的 URI，它不仅唯一标识资源，而且还提供了定位该资源的信息。

#### Cookie 和 Session 有什么区别？

准确点来说，这个问题属于认证授权的范畴，你可以在 [认证授权基础概念详解](https://javaguide.cn/system-design/security/basis-of-authority-certification.html) 这篇文章中找到详细的答案。

#### ⭐️ GET 和 POST 的区别

这个问题在知乎上被讨论的挺火热的，地址：。

GET 和 POST 是 HTTP 协议中两种常用的请求方法，它们在不同的场景和目的下有不同的特点和用法。一般来说，可以从以下几个方面来区分二者（重点搞清两者在语义上的区别即可）：

- 语义（主要区别）：GET 通常用于获取或查询资源，而 POST 通常用于创建或修改资源。
- 幂等：GET 请求是幂等的，即多次重复执行不会改变资源的状态，而 POST 请求是不幂等的，即每次执行可能会产生不同的结果或影响资源的状态。
- 格式：GET 请求的参数通常放在 URL 中，形成查询字符串（querystring），而 POST 请求的参数通常放在请求体（body）中，可以有多种编码格式，如 application/x-www-form-urlencoded、multipart/form-data、application/json 等。GET 请求的 URL 长度受到浏览器和服务器的限制，而 POST 请求的 body 大小则没有明确的限制。不过，实际上 GET 请求也可以用 body 传输数据，只是并不推荐这样做，因为这样可能会导致一些兼容性或者语义上的问题。
- 缓存：由于 GET 请求是幂等的，它可以被浏览器或其他中间节点（如代理、网关）缓存起来，以提高性能和效率。而 POST 请求则不适合被缓存，因为它可能有副作用，每次执行可能需要实时的响应。
- 安全性：GET 请求和 POST 请求如果使用 HTTP 协议的话，那都不安全，因为 HTTP 协议本身是明文传输的，必须使用 HTTPS 协议来加密传输数据。另外，GET 请求相比 POST 请求更容易泄露敏感数据，因为 GET 请求的参数通常放在 URL 中。

再次提示，重点搞清两者在语义上的区别即可，实际使用过程中，也是通过语义来区分使用 GET 还是 POST。不过，也有一些项目所有的请求都用 POST，这个并不是固定的，项目组达成共识即可。

### 【WebSocket】

#### 什么是 WebSocket?

WebSocket 是一种基于 TCP 连接的全双工通信协议，即客户端和服务器可以同时发送和接收数据。

WebSocket 协议在 2008 年诞生，2011 年成为国际标准，几乎所有主流较新版本的浏览器都支持该协议。不过，WebSocket 不只能在基于浏览器的应用程序中使用，很多编程语言、框架和服务器都提供了 WebSocket 支持。

WebSocket 协议本质上是应用层的协议，用于弥补 HTTP 协议在持久通信能力上的不足。客户端和服务器仅需一次握手，两者之间就直接可以创建持久性的连接，并进行双向数据传输。

![WebSocket 建立持久连接实现双向通信](images/1460000042192394-99b6e344.png)

下面是 WebSocket 的常见应用场景：

- 视频弹幕
- 实时消息推送，详见[Web 实时消息推送详解](https://javaguide.cn/system-design/web-real-time-message-push.html)这篇文章
- 实时游戏对战
- 多用户协同编辑
- 社交聊天
- ……

#### ⭐️ WebSocket 和 HTTP 有什么区别？

WebSocket 和 HTTP 两者都是基于 TCP 的应用层协议，都可以在网络中传输数据。

下面是二者的主要区别：

- WebSocket 是一种双向实时通信协议，而 HTTP 是一种单向通信协议。并且，HTTP 协议下的通信只能由客户端发起，服务器无法主动通知客户端。
- WebSocket 使用 ws:// 或 wss://（使用 SSL/TLS 加密后的协议，类似于 HTTP 和 HTTPS 的关系）作为协议前缀，HTTP 使用 http:// 或 https:// 作为协议前缀。
- WebSocket 可以支持扩展，用户可以扩展协议，实现部分自定义的子协议，如支持压缩、加密等。
- WebSocket 通信数据格式比较轻量，用于协议控制的数据包头部相对较小，网络开销小，而 HTTP 通信每次都要携带完整的头部，网络开销较大（HTTP/2.0 使用二进制帧进行数据传输，还支持头部压缩，减少了网络开销）。

#### WebSocket 的工作过程是什么样的？

WebSocket 的工作过程可以分为以下几个步骤：

1. 客户端向服务器发送一个 HTTP 请求，请求头中包含 `Upgrade: websocket` 和 `Sec-WebSocket-Key` 等字段，表示要求升级协议为 WebSocket；
2. 服务器收到这个请求后，会进行升级协议的操作，如果支持 WebSocket，它将回复一个 HTTP 101 状态码，响应头中包含 `Connection: Upgrade` 和 `Sec-WebSocket-Accept: xxx` 等字段，表示成功升级到 WebSocket 协议。
3. 客户端和服务器之间建立了一个 WebSocket 连接，可以进行双向的数据传输。数据以帧（frames）的形式进行传送，WebSocket 的每条消息可能会被切分成多个数据帧（最小单位）。发送端会将消息切割成多个帧发送给接收端，接收端接收消息帧，并将关联的帧重新组装成完整的消息。
4. 客户端或服务器可以主动发送一个关闭帧，表示要断开连接。另一方收到后，也会回复一个关闭帧，然后双方关闭 TCP 连接。

另外，建立 WebSocket 连接之后，通过心跳机制来保持 WebSocket 连接的稳定性和活跃性。

#### ⭐️ WebSocket 与短轮询、长轮询的区别

这三种方式，都是为了解决“**客户端如何及时获取服务器最新数据，实现实时更新**”的问题。它们的实现方式和效率、实时性差异较大。

**1.短轮询（Short Polling）**

- **原理**：客户端每隔固定时间（如 5 秒）发起一次 HTTP 请求，询问服务器是否有新数据。服务器收到请求后立即响应。
- **优点**：实现简单，兼容性好，直接用常规 HTTP 请求即可。
- **缺点**：
  - **实时性一般**：消息可能在两次轮询间到达，用户需等到下次请求才知晓。
  - **资源浪费大**：反复建立/关闭连接，且大多数请求收到的都是“无新消息”，极大增加服务器和网络压力。

**2.长轮询（Long Polling）**

- **原理**：客户端发起请求后，若服务器暂时无新数据，则会保持连接，直到有新数据或超时才响应。客户端收到响应后立即发起下一次请求，实现“伪实时”。
- **优点**：
  - **实时性较好**：一旦有新数据可立即推送，无需等待下次定时请求。
  - **空响应减少**：减少了无效的空响应，提升了效率。
- **缺点**：
  - **服务器资源占用高**：需长时间维护大量连接，消耗服务器线程/连接数。
  - **资源浪费大**：每次响应后仍需重新建立连接，且依然基于 HTTP 单向请求-响应机制。

**3. WebSocket**

- **原理**：客户端与服务器通过一次 HTTP Upgrade 握手后，建立一条持久的 TCP 连接。之后，双方可以随时、主动地发送数据，实现真正的全双工、低延迟通信。
- **优点**：
  - **实时性强**：数据可即时双向收发，延迟极低。
  - **资源效率高**：连接持续，无需反复建立/关闭，减少资源消耗。
  - **功能强大**：支持服务端主动推送消息、客户端主动发起通信。
- **缺点**：
  - **使用限制**：需要服务器和客户端都支持 WebSocket 协议。对连接管理有一定要求（如心跳保活、断线重连等）。
  - **实现麻烦**：实现起来比短轮询和长轮询要更麻烦一些。

![WebSocket 与短轮询和长轮询的通信方式对比](images/1460000042192394-99b6e344.png)

#### ⭐️ SSE 与 WebSocket 有什么区别？

SSE（Server-Sent Events）和 WebSocket 都是用来实现服务器向浏览器实时推送消息的技术，让网页内容能自动更新，而不需要用户手动刷新。虽然目标相似，但它们在工作方式和适用场景上有几个关键区别：

1. **通信方式:**
   - **SSE:** **单向通信**。只有服务器能向客户端（浏览器）发送数据。客户端不能通过同一个连接向服务器发送数据（需要发起新的 HTTP 请求）。
   - **WebSocket:** **双向通信（全双工）**。客户端和服务器可以随时互相发送消息，实现真正的实时交互。
2. **底层协议:**
   - **SSE:** 基于**标准的 HTTP/HTTPS 协议**。它本质上是一个“长连接”的 HTTP 请求，服务器保持连接打开并持续发送事件流。不需要特殊的服务器或协议支持，现有的 HTTP 基础设施就能用。
   - **WebSocket:** 使用**独立的 ws:// 或 wss:// 协议**。它需要通过一个特定的 HTTP "Upgrade" 请求来建立连接，并且服务器需要明确支持 WebSocket 协议来处理连接和消息帧。
3. **实现复杂度和成本:**
   - **SSE:** **实现相对简单**，主要在服务器端处理。浏览器端有标准的 EventSource API，使用方便。开发和维护成本较低。
   - **WebSocket:** **稍微复杂一些**。需要服务器端专门处理 WebSocket 连接和协议，客户端也需要使用 WebSocket API。如果需要考虑兼容性、心跳、重连等，开发成本会更高。
4. **断线重连:**
   - **SSE:** **浏览器原生支持**。EventSource API 提供了自动断线重连的机制。
   - **WebSocket:** **需要手动实现**。开发者需要自己编写逻辑来检测断线并进行重连尝试。
5. **数据类型:**
   - **SSE:** **主要设计用来传输文本**（UTF-8 编码）。如果需要传输二进制数据，需要先进行 Base64 等编码转换成文本。
   - **WebSocket:** **原生支持传输文本和二进制数据**，无需额外编码。

为了提供更好的用户体验和利用其简单、高效、基于标准 HTTP 的特性，**Server-Sent Events（SSE）是目前大型语言模型 API（如 OpenAI、DeepSeek 等）实现流式响应的常用甚至可以说是标准的技术选择**。

这里以 DeepSeek 为例，我们发送一个请求并打开浏览器控制台验证一下：

![DeepSeek 响应标头](images/deepseek-sse-575a911b.png)

![DeepSeek SSE 响应使用 text/event-stream 持续传输事件](images/deepseek-sse-eventstream-f35c5785.png)

可以看到，响应头里包含了 `text/event-stream`，说明使用的确实是 SSE。并且，响应数据也确实是持续分块传输。

### 【PING】

#### PING 命令的作用是什么？

PING 命令是一种常用的网络诊断工具，经常用来测试网络中主机之间的连通性和网络延迟。

这里简单举一个例子，我们来 PING 一下百度。

```bash
# 发送4个PING请求数据包到 www.baidu.com
❯ ping -c 4 www.baidu.com

PING www.a.shifen.com (14.119.104.189): 56 data bytes
64 bytes from 14.119.104.189: icmp_seq=0 ttl=54 time=27.867 ms
64 bytes from 14.119.104.189: icmp_seq=1 ttl=54 time=28.732 ms
64 bytes from 14.119.104.189: icmp_seq=2 ttl=54 time=27.571 ms
64 bytes from 14.119.104.189: icmp_seq=3 ttl=54 time=27.581 ms

--- www.a.shifen.com ping statistics ---
4 packets transmitted, 4 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 27.571/27.938/28.732/0.474 ms
```

PING 命令的输出结果通常包括以下几部分信息：

1. **ICMP Echo Request（请求报文）信息**：序列号、TTL（Time to Live）值。
2. **目标主机的域名或 IP 地址**：输出结果的第一行。
3. **往返时间（RTT，Round-Trip Time）**：从发送 ICMP Echo Request（请求报文）到接收到 ICMP Echo Reply（响应报文）的总时间，用来衡量网络连接的延迟。
4. **统计结果（Statistics）**：包括发送的 ICMP 请求数据包数量、接收到的 ICMP 响应数据包数量、丢包率、往返时间（RTT）的最小、平均、最大和标准偏差值。

如果 PING 对应的目标主机无法得到正确的响应，则表明这两个主机之间的连通性存在问题（有些主机或网络管理员可能禁用了对 ICMP 请求的回复，这样也会导致无法得到正确的响应）。如果往返时间（RTT）过高，则表明网络延迟过高。

#### PING 命令的工作原理是什么？

PING 基于网络层的 **ICMP（Internet Control Message Protocol，互联网控制报文协议）**，其主要原理就是通过在网络上发送和接收 ICMP 报文实现的。

ICMP 报文中包含了类型字段，用于标识 ICMP 报文类型。ICMP 报文的类型有很多种，但大致可以分为两类：

- **查询报文类型**：向目标主机发送请求并期望得到响应。
- **差错报文类型**：向源主机发送错误信息，用于报告网络中的错误情况。

PING 用到的 ICMP Echo Request（类型为 8）和 ICMP Echo Reply（类型为 0）属于查询报文类型。

- PING 命令会向目标主机发送 ICMP Echo Request。
- 如果两个主机的连通性正常，目标主机会返回一个对应的 ICMP Echo Reply。

#### ⭐️ 能 Ping 通，TCP 就一定能连通吗？

先说结论：**不是**。

Ping 使用 ICMP（网络层），TCP 连接使用 TCP（传输层），两者可能经过同一条网络路径，但中间设备会按协议类型、端口、连接状态和安全策略分别处理。你能 Ping 通，只能说明 ICMP Echo 这条路径能往返，不等于目标 TCP 端口一定可达。

![ICMP与TCP路径差异](images/can-ping-but-tcp-may-not-connect-icmp-and-tcp-path-differenc-5e8a0530.png)

常见原因有这几种：

- **防火墙策略不同**：很多网络设备允许 ICMP（方便运维探测），但 TCP 端口规则收得更紧，可能只开放了 `22`、`80`、`443`，其他端口一律不放。
- **服务没启动或端口没监听**：主机能回 ICMP，但 Nginx 没启动、MySQL 没监听，Ping 通但 TCP 连不上。
- **中间有 NAT / 负载均衡 / 安全设备**：公网 IP 后面可能不是一台真实服务器，ICMP 响应可能来自中间设备，不能直接等同于后端服务可用。
- **HTTPS 还可能卡在 TLS 握手的 SNI**：TCP 三次握手可能成功了，但 `ClientHello` 里的 SNI 被中间设备识别并拦截，导致连接重置或卡住。

反过来也成立：**Ping 不通，不代表 TCP 一定不通**。有些服务器或云安全组直接禁 ICMP，但业务端口正常工作。

排查建议：先看 DNS（域名场景），再用 `ping` 看 ICMP，然后用 `nc` 测端口，最后用 `curl` 或 `openssl s_client` 看 HTTPS / TLS。别用一个命令过早下结论。

![HTTPS连接排查层次](images/can-ping-but-tcp-may-not-connect-https-connection-troublesho-3fcb5151.png)

详细介绍：[能 Ping 通，TCP 就一定能连通吗？](https://github.com/Snailclimb/JavaGuide/blob/main/docs/can-ping-but-tcp-may-not-connect.md)

### 【DNS】

#### DNS 的作用是什么？

DNS（Domain Name System）域名管理系统，是当用户使用浏览器访问网址之后，使用的第一个重要协议。DNS 要解决的是**域名和 IP 地址的映射问题**。

![DNS 将域名解析为 IP 地址的系统概览](images/dns-overview-4619e349.png)

在一台电脑上，可能存在浏览器 DNS 缓存，操作系统 DNS 缓存，路由器 DNS 缓存。如果以上缓存都查询不到，那么 DNS 就闪亮登场了。

目前 DNS 的设计采用的是分布式、层次数据库结构，**DNS 是应用层协议，它可以在 UDP 或 TCP 协议之上运行，端口为 53**。

#### DNS 服务器有哪些？根服务器有多少个？

DNS 可以从两个维度描述。权威层次包括根、顶级域和具体区域的权威服务器；查询侧则包括存根解析器、递归解析器和转发器等角色。同一套软件或同一台服务器也可能承担多个角色，因此这些类别不是互斥且穷尽的“服务器类型”。

- 根 DNS 服务器向查询方提供顶级域服务器的转介信息。
- 顶级域 DNS 服务器通常返回目标域权威服务器的转介信息。
- 权威 DNS 服务器保存一个或多个区域的数据，并对这些区域内的查询给出权威回答。
- 递归解析器接收客户端查询，先检查缓存，必要时再向根、TLD 和权威服务器逐级查询。它属于查询侧角色，不是权威 DNS 层次的一层。

根服务器系统逻辑上有 13 个命名的根服务器标识，从 `a.root-servers.net` 到 `m.root-servers.net`，由 12 个独立运营组织负责。每个标识背后可以通过 Anycast 部署多个物理实例，实例数量和地点会持续变化，应以 [Root-Servers.org](https://root-servers.org/) 的实时数据为准。不能把 13 个逻辑标识理解为全球只有 13 台物理服务器。

#### ⭐️ DNS 解析的过程是什么样的？

整个过程的步骤比较多，我单独写了一篇文章详细介绍：[DNS 域名系统详解（应用层）](https://javaguide.cn/cs-basics/network/dns.html)。

#### DNS 劫持了解吗？如何应对？

DNS 劫持是一种网络攻击，它通过修改 DNS 服务器的解析结果，使用户访问的域名指向错误的 IP 地址，从而导致用户无法访问正常的网站，或者被引导到恶意的网站。DNS 劫持有时也被称为 DNS 重定向、DNS 欺骗或 DNS 污染。

#### 参考

- 《图解 HTTP》
- 《计算机网络自顶向下方法》（第七版）
- 详解 HTTP/2.0 及 HTTPS 协议：
- HTTP 请求头字段大全| HTTP Request Headers：
- HTTP1、HTTP2、HTTP3：
- 如何看待 HTTP/3？ - 车小胖的回答 - 知乎: 

<!-- @include: @article-footer.snippet.md -->

### 【TCP 与 UDP】

#### ⭐️ TCP 与 UDP 的区别（重要）

1. **是否面向连接**：
   - TCP 是面向连接的。在传输数据之前，必须先通过“三次握手”建立连接；数据传输完成后，还需要通过“四次挥手”来释放连接。这保证了双方都准备好通信。
   - UDP 是无连接的。发送数据前不需要建立任何连接，直接把数据包（数据报）扔出去。
2. **是否是可靠传输**：
   - TCP 提供可靠的数据传输服务。它通过序列号、确认应答（ACK）、超时重传、流量控制、拥塞控制等一系列机制，来确保数据能够无差错、不丢失、不重复且按顺序地到达目的地。
   - UDP 提供不可靠的传输。它尽最大努力交付（best-effort delivery），但不保证数据一定能到达，也不保证到达的顺序，更不会自动重传。收到报文后，接收方也不会主动发确认。
3. **是否有状态**：
   - TCP 是有状态的。因为要保证可靠性，TCP 需要在连接的两端维护连接状态信息，比如序列号、窗口大小、哪些数据发出去了、哪些收到了确认等。
   - UDP 是无状态的。它不维护连接状态，发送方发出数据后就不再关心它是否到达以及如何到达，因此开销更小（**这很“渣男”！**）。
4. **传输效率**：
   - TCP 因为需要建立连接、发送确认、处理重传等，其开销较大，传输效率相对较低。
   - UDP 结构简单，没有复杂的控制机制，开销小，传输效率更高，速度更快。
5. **传输形式**：
   - TCP 是面向字节流（Byte Stream）的。它将应用程序交付的数据视为一连串无结构的字节流，可能会对数据进行拆分或合并。
   - UDP 是面向报文（Message Oriented）的。应用程序交给 UDP 多大的数据块，UDP 就照样发送，既不拆分也不合并，保留了应用程序消息的边界。
6. **首部开销**：
   - TCP 的头部至少需要 20 字节，如果包含选项字段，最多可达 60 字节。
   - UDP 的头部非常简单，固定只有 8 字节。
7. **是否提供广播或多播服务**：
   - TCP 只支持点对点（Point-to-Point）的单播通信。
   - UDP 支持一对一（单播）、一对多（多播/Multicast）和一对所有（广播/Broadcast）的通信方式。
8. ……

为了更直观地对比，可以看下面这个表格：

| 特性         | TCP                        | UDP                                 |
| ------------ | -------------------------- | ----------------------------------- |
| **连接性**   | 面向连接                   | 无连接                              |
| **可靠性**   | 可靠                       | 不可靠（尽力而为）                  |
| **状态维护** | 有状态                     | 无状态                              |
| **传输效率** | 较低                       | 较高                                |
| **传输形式** | 面向字节流                 | 面向数据报（报文）                  |
| **头部开销** | 20 - 60 字节               | 8 字节                              |
| **通信模式** | 点对点（单播）             | 单播、多播、广播                    |
| **常见应用** | HTTP/HTTPS, FTP, SMTP, SSH | DNS, DHCP, SNMP, TFTP, VoIP, 视频流 |

#### ⭐️ 什么时候选择 TCP，什么时候选 UDP?

选择 TCP 还是 UDP，主要取决于你的应用**对数据传输的可靠性要求有多高，以及对实时性和效率的要求有多高**。

当**数据准确性和完整性至关重要，一点都不能出错**时，通常选择 TCP。因为 TCP 提供了一整套机制（三次握手、确认应答、重传、流量控制等）来保证数据能够可靠、有序地送达。典型应用场景如下：

- **Web 浏览（HTTP/HTTPS）:** 网页内容、图片、脚本必须完整加载才能正确显示。
- **文件传输（FTP, SCP）:** 文件内容不允许有任何字节丢失或错序。
- **邮件收发（SMTP, POP3, IMAP）:** 邮件内容需要完整无误地送达。
- **远程登录（SSH, Telnet）:** 命令和响应需要准确传输。
- ……

当**实时性、速度和效率优先，并且应用能容忍少量数据丢失或乱序**时，通常选择 UDP。UDP 开销小、传输快，没有建立连接和保证可靠性的复杂过程。典型应用场景如下：

- **实时音视频通信（VoIP, 视频会议，直播）:** 偶尔丢失一两个数据包（可能导致画面或声音短暂卡顿）通常比因为等待重传（TCP 机制）导致长时间延迟更可接受。应用层可能会有自己的补偿机制。
- **在线游戏:** 需要快速传输玩家位置、状态等信息，对实时性要求极高，旧的数据很快就没用了，丢失少量数据影响通常不大。
- **DHCP（动态主机配置协议）:** 客户端在请求 IP 时自身没有 IP 地址，无法满足 TCP 建立连接的前提条件，并且 DHCP 有广播需求、交互模式简单以及自带可靠性机制。
- **物联网（IoT）数据上报:** 某些场景下，传感器定期上报数据，丢失个别数据点可能不影响整体趋势分析。
- ……

#### HTTP 基于 TCP 还是 UDP？

~~**HTTP 协议是基于 TCP 协议的**，所以发送 HTTP 请求之前首先要建立 TCP 连接也就是要经历 3 次握手。~~

🐛 修正（参见 [issue#1915](https://github.com/Snailclimb/JavaGuide/issues/1915)）：

HTTP/3.0 之前是基于 TCP 协议的，而 HTTP/3.0 将弃用 TCP，改用 **基于 UDP 的 QUIC 协议**：

- **HTTP/1.x 和 HTTP/2.0**：这两个版本的 HTTP 协议都明确建立在 TCP 之上。TCP 提供了可靠的、面向连接的传输，确保数据按序、无差错地到达，这对于网页内容的正确展示非常重要。发送 HTTP 请求前，需要先通过 TCP 的三次握手建立连接。
- **HTTP/3.0**：这是一个重大的改变。HTTP/3 弃用了 TCP，转而使用 QUIC 协议，而 QUIC 是构建在 UDP 之上的。

![HTTP/1、HTTP/2 和 HTTP/3 协议栈对比](images/http-3-implementation-ab73b085.png)

**为什么 HTTP/3 要做这个改变呢？主要有两大原因：**

1. 解决队头阻塞（Head-of-Line Blocking，简写：HOL blocking）问题。
2. 减少连接建立的延迟。

下面我们来详细介绍这两大优化。

在 HTTP/2 中，虽然可以在一个 TCP 连接上并发传输多个请求/响应流（多路复用），但 TCP 本身的特性（保证有序、可靠）意味着如果其中一个流的某个 TCP 报文丢失或延迟，整个 TCP 连接都会被阻塞，等待该报文重传。这会导致所有在这个 TCP 连接上的 HTTP/2 流都受到影响，即使其他流的数据包已经到达。**QUIC（运行在 UDP 上）解决了这个问题**。QUIC 内部实现了自己的多路复用和流控制机制。不同的 HTTP 请求/响应流在 QUIC 层面是真正独立的。如果一个流的数据包丢失，它只会阻塞该流，而不会影响同一 QUIC 连接上的其他流（本质上是多路复用+轮询），大大提高了并发传输的效率。

除了解决队头阻塞问题，HTTP/3.0 还可以减少握手过程的延迟。在 HTTP/2.0 中，如果要建立一个安全的 HTTPS 连接，需要经过 TCP 三次握手和 TLS 握手：

RTT 指报文从一端到对端再返回的往返时间，不是单程传输时间。TCP 握手的延迟必须说明测量终点：客户端在发送 SYN 后约 1 RTT 收到 SYN-ACK，随后可以发送最终 ACK 和应用请求；服务器收到该 ACK 和请求还需要一个单程延迟。比较 HTTP/2 和 HTTP/3 时，应统一采用“客户端何时可以发送首个请求”或“客户端何时收到首字节”等同一个指标。

HTTP/2 的 HTTPS 连接需要先建立 TCP 连接，再完成 TLS 握手。HTTP/3 把传输参数协商和 TLS 1.3 握手结合在 QUIC 建连过程中。新的 QUIC 连接通常使用 1-RTT；0-RTT 只适用于客户端持有先前连接状态的恢复场景，可以在首个报文中携带早期数据，但存在重放风险，只适合可安全重放的请求。

相关证明可以参考下面这两个链接：

- 
-

#### 为什么 TCP 是面向字节流，UDP 是面向报文？

![TCP 与 UDP 的消息边界](images/tcp-udp-byte-stream-tcp-udp-message-boundary-ff2c1ad3.png)

TCP 是面向字节流的。应用层写入的数据会进入内核缓冲区，TCP 只保证这些字节可靠、有序地到达对端，不保证一次 `send()` 对应一次 `recv()`，也不保留应用层消息边界。因此接收方可能一次读到多条消息，也可能只读到半条消息，这就是常说的粘包、拆包现象。
![TCP 粘包 / 拆包为什么会出现？](images/tcp-udp-byte-stream-tcp-sticky-split-causes-3dc840f6.png)

UDP 是面向报文的。应用层交给 UDP 的一次数据会作为一个 UDP 数据报发送，接收端也是按数据报读取，所以天然保留消息边界。不过 UDP 不保证可靠到达，也不保证顺序。

解决 TCP 粘包/拆包，本质是应用层协议自己定义消息边界。常见方案有固定长度、分隔符、长度头。工程里更常用长度头，因为它对二进制协议和变长消息更友好，但要处理字节序、最大长度限制、半包缓存和异常连接关闭等问题。

![应用层如何定义消息边界？](images/tcp-udp-byte-stream-tcp-message-boundary-solutions-86186610.png)

详细介绍：[为什么 TCP 是面向字节流，UDP 是面向报文？](https://github.com/Snailclimb/JavaGuide/blob/main/docs/tcp-byte-stream-udp-datagram.md)

#### 你知道哪些基于 TCP/UDP 的协议？

TCP（传输控制协议）和 UDP（用户数据报协议）是互联网传输层的两大核心协议，它们为各种应用层协议提供了基础的通信服务。以下是一些常见的、分别构建在 TCP 和 UDP 之上的应用层协议：

**运行于 TCP 协议之上的协议（强调可靠、有序传输）：**

| 中文全称（缩写）            | 英文全称                           | 主要用途                     | 说明与特性                                                                                                                  |
| --------------------------- | ---------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 超文本传输协议（HTTP）      | HyperText Transfer Protocol        | 传输网页、超文本、多媒体内容 | **HTTP/1.x 和 HTTP/2 基于 TCP**。早期版本不加密，是 Web 通信的基础。                                                        |
| 安全超文本传输协议（HTTPS） | HyperText Transfer Protocol Secure | 加密的网页传输               | 使用 TLS 保护 HTTP。HTTP/1.1 和 HTTP/2 通常使用 TLS over TCP，HTTP/3 使用集成 TLS 1.3 的 QUIC。                             |
| 文件传输协议（FTP）         | File Transfer Protocol             | 文件传输                     | 传统的 FTP **明文传输**，不安全。推荐使用其安全版本 **SFTP（SSH File Transfer Protocol）** 或 **FTPS (FTP over SSL/TLS)**。 |
| 简单邮件传输协议（SMTP）    | Simple Mail Transfer Protocol      | **发送**电子邮件             | 负责将邮件从客户端发送到服务器，或在邮件服务器之间传递。可通过 **STARTTLS** 升级到加密传输。                                |
| 邮局协议第 3 版（POP3）     | Post Office Protocol version 3     | **接收**电子邮件             | 通常将邮件从服务器**下载到本地设备后删除服务器副本**（可配置保留）。**POP3S** 是其 SSL/TLS 加密版本。                       |
| 互联网消息访问协议（IMAP）  | Internet Message Access Protocol   | **接收和管理**电子邮件       | 邮件保留在服务器，支持多设备同步邮件状态、文件夹管理、在线搜索等。**IMAPS** 是其 SSL/TLS 加密版本。现代邮件服务首选。       |
| 远程终端协议（Telnet）      | Teletype Network                   | 远程终端登录                 | **明文传输**所有数据（包括密码），安全性极差，基本已被 SSH 完全替代。                                                       |
| 安全外壳协议（SSH）         | Secure Shell                       | 安全远程管理、加密数据传输   | 提供了加密的远程登录和命令执行，以及安全的文件传输（SFTP）等功能，是 Telnet 的安全替代品。                                  |

**运行于 UDP 协议之上的协议（强调快速、低开销传输）：**

| 中文全称（缩写）         | 英文全称                              | 主要用途                   | 说明与特性                                                                                                         |
| ------------------------ | ------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| 超文本传输协议（HTTP/3） | HyperText Transfer Protocol version 3 | 新一代网页传输             | 基于 **QUIC** 协议（QUIC 本身构建于 UDP 之上），旨在减少延迟、缓解 TCP 队头阻塞；会话恢复时可使用 0-RTT 早期数据。 |
| 动态主机配置协议（DHCP） | Dynamic Host Configuration Protocol   | 动态分配 IP 地址及网络配置 | 客户端从服务器自动获取 IP 地址、子网掩码、网关、DNS 服务器等信息。                                                 |
| 域名系统（DNS）          | Domain Name System                    | 域名到 IP 地址的解析       | **通常使用 UDP** 进行快速查询。当响应数据包过大或进行区域传送（AXFR）时，会**切换到 TCP** 以保证数据完整性。       |
| 实时传输协议（RTP）      | Real-time Transport Protocol          | 实时音视频数据流传输       | 常用于 VoIP、视频会议、直播等。追求低延迟，允许少量丢包。通常与 RTCP 配合使用。                                    |
| RTP 控制协议（RTCP）     | RTP Control Protocol                  | RTP 流的质量监控和控制信息 | 配合 RTP 工作，提供丢包、延迟、抖动等统计信息，辅助流量控制和拥塞管理。                                            |
| 简单文件传输协议（TFTP） | Trivial File Transfer Protocol        | 简化的文件传输             | 功能简单，常用于局域网内无盘工作站启动、网络设备固件升级等小文件传输场景。                                         |
| 简单网络管理协议（SNMP） | Simple Network Management Protocol    | 网络设备的监控与管理       | 允许网络管理员查询和修改网络设备的状态信息。                                                                       |
| 网络时间协议（NTP）      | Network Time Protocol                 | 同步计算机时钟             | 用于在网络中的计算机之间同步时间，确保时间的一致性。                                                               |

**总结一下：**

- **TCP** 更适合那些对数据**可靠性、完整性和顺序性**要求高的应用，如网页浏览（HTTP/HTTPS）、文件传输（FTP/SFTP）、邮件收发（SMTP/POP3/IMAP）。
- **UDP** 则更适用于那些对**实时性要求高、能容忍少量数据丢失**的应用，如域名解析（DNS）、实时音视频（RTP）、在线游戏、网络管理（SNMP）等。

#### ⭐️ TCP Keepalive 和 HTTP Keep-Alive 有什么区别

| 对比维度          | HTTP Keep-Alive                                         | TCP Keepalive                                       |
| ----------------- | ------------------------------------------------------- | --------------------------------------------------- |
| **所属层**        | 应用层（HTTP 协议）                                     | 传输层（TCP 协议）                                  |
| **解决的问题**    | 复用 TCP 连接，减少重复建连、挥手、慢启动等开销         | 探测长时间空闲的 TCP 连接，对端失联后释放连接资源   |
| **默认行为**      | HTTP/1.0 默认短连接；HTTP/1.1 默认长连接                | 默认关闭，应用需要显式开启 `SO_KEEPALIVE`           |
| **控制粒度**      | 由 HTTP 客户端、Web 服务器或代理按连接策略控制          | 由操作系统内核控制，也可在部分平台逐 socket 调整    |
| **常见参数**      | `Connection`、`Keep-Alive: timeout/max`、服务器超时配置 | `tcp_keepalive_time/intvl/probes` 或平台对应参数    |
| **关闭触发**      | 到达空闲超时、请求次数上限，或任意一方主动关闭          | 空闲后发探测包，多次无响应或收到 RST 才关闭         |
| **对端在线时**    | 服务端仍可按配置主动回收空闲连接                        | 只要对端内核能回 ACK，连接通常继续维持              |
| **能否替代心跳**  | 不能判断业务是否健康，只能管理 HTTP 连接复用            | 不能判断应用线程池、事件循环、业务依赖是否正常      |
| **中间层影响**    | 代理、网关可独立管理前后两段 HTTP/TCP 连接              | NAT/LB/反向代理可能让你探测到的只是某一段 TCP 连接  |
| **HTTP/2/3 关系** | HTTP/2 禁用连接级头；HTTP/3/QUIC 不使用这套机制         | 只作用于 TCP；真正的 HTTP/3/QUIC 连接不受它直接影响 |

**不同 HTTP 版本里，Keep-Alive 的默认行为不一样**：

![不同 HTTP 版本里，Keep-Alive 的默认行为不一样](images/different-http-versions-have-different-default-keep-alive-be-f743d0f1.png)

如果从“谁来决定关连接”的角度看，两个机制的态度完全相反：

HTTP Keep-Alive 是“主动回收”——服务器到了超时或请求次数上限，就可以按自己的配置关闭连接，不需要先探测对方是否在线。它是一种比较主动的资源回收方式。

TCP Keepalive 是“被动回收”——它必须先发探测包去问“你还在吗？”。只要对方在线、能回 ACK，服务器就只能继续维持连接，刷新定时器。只有确认对方已经不在了，才能释放资源。这是一种温和的回收策略。

![TCP Keepalive 工作原理](images/tcp-keepalive-vs-http-keepalive-tcp-keepalive-working-princi-7f50afab.png)

![TCP Keepalive 探测机制](images/tcp-keepalive-vs-http-keepalive-tcp-keepalive-detection-mech-306c79b5.png)

实际项目中，两者经常同时在跑，各管各的。HTTP Keep-Alive 管的是“一条连接最多用多久、服务多少次请求”，TCP Keepalive 管的是“如果长时间没数据，检查一下对方是不是已经消失了”。两者互不干扰，也不能互相替代。

详细介绍：[TCP Keepalive 和 HTTP Keep-Alive 有什么区别？](https://github.com/Snailclimb/JavaGuide/blob/main/docs/tcp-keepalive-vs-http-keepalive.md)

#### ⭐️ TCP 三次握手和四次挥手（非常重要）

**相关面试题**：

- 为什么要三次握手？
- 第 2 次握手传回了 ACK，为什么还要传回 SYN？
- 为什么要四次挥手？
- 为什么不能把服务器发送的 ACK 和 FIN 合并起来，变成三次挥手？
- 如果第二次挥手时服务器的 ACK 没有送达客户端，会怎样？
- 为什么第四次挥手客户端需要等待 2\*MSL（报文段最长寿命）时间后才进入 CLOSED 状态？

**参考答案**：[TCP 三次握手和四次挥手（传输层）](https://javaguide.cn/cs-basics/network/tcp-connection-and-disconnection.html)。

#### TCP TIME_WAIT 到底在等什么？为什么要等？

**相关面试题**：

1. `TIME_WAIT` 到底在等什么？
2. `TIME_WAIT` 大量堆积会不会真的出问题？
3. `tcp_tw_reuse` 能不能随便开？
4. `TIME_WAIT` 和 `CLOSE_WAIT` 怎么区分？

**参考答案**： [TCP TIME_WAIT 详解：为什么要等、会不会出问题、能不能复用？](https://github.com/Snailclimb/JavaGuide/blob/main/docs/tcp-time-wait.md)。

#### ⭐️ TCP 如何保证传输的可靠性？（重要）

[TCP 传输可靠性保障（传输层）](https://javaguide.cn/cs-basics/network/tcp-reliability-guarantee.html)

#### TCP 和 UDP 可以使用同一个端口吗？

结论：**可以**。TCP 和 UDP 的端口绑定命名空间按传输层协议区分，同一个数字端口在不同协议下不冲突。

内核收到 IP 包后，会先看 IP 层的协议标识（TCP 协议号是 `6`，UDP 是 `17`），根据协议号把报文交给对应的 TCP 或 UDP 协议栈，然后再在各自协议栈内按地址和端口分发。所以 `TCP/8080` 和 `UDP/8080` 可以共存，内核压根不会把它们当成同一条通信。

![内核协议分发流程](images/can-tcp-and-udp-use-the-same-port-kernel-protocol-dispatchin-09d025cf.png)

真正容易冲突的是**同一协议**下的重复绑定，比如两个 TCP 服务通常不能同时监听同一个本地 IP 和端口；这时才涉及 `SO_REUSEADDR`、`SO_REUSEPORT` 这类 socket 复用选项。

经典例子：DNS 同时使用 `UDP/53`（日常查询）和 `TCP/53`（响应过大、区域传送）；HTTP/3 常见部署是 `UDP/443`（QUIC），可以和传统 HTTPS 的 `TCP/443` 同时存在。

![DNS 和 HTTP/3 同时使用 TCP 与 UDP 端口的实际案例](images/can-tcp-and-udp-use-the-same-port-practical-application-exam-ab70afb0.png)

详细介绍：[TCP 和 UDP 可以使用同一个端口吗？](https://github.com/Snailclimb/JavaGuide/blob/main/docs/can-tcp-and-udp-use-the-same-port.md)

#### ⭐️ 一台主机上只能保持最多 65535 个 TCP 连接吗？

结论：**不是**。`65535` 是最大端口号，不是连接数上限。

TCP 连接靠四元组区分：源 IP、源端口、目的 IP、目的端口。只要四元组不同，内核就识别为不同连接。服务端监听同一个端口时，只要客户端 IP 或客户端端口不同，连接就可以继续增加。

![TCP 连接靠四元组区分和真正的限制](images/maximum-number-of-tcp-connections-per-host-tcp-four-tuple-an-4d337232.png)

真正限制连接数的因素：

- **服务端**：主要受文件描述符、内存、CPU、网卡和应用处理能力限制，而不是端口数。
- **客户端**：连同一个目标时，源 IP 和目的 IP:Port 都固定，只剩源端口可变，更容易撞到临时端口上限（Linux 默认约 2.8 万个）。`TIME_WAIT` 堆积会加剧这个问题。
- **NAT 网关**：大量内网机器共享同一个公网 IP 访问同一个外部目标时，NAT 侧的公网源端口也会成为瓶颈。

生产环境最常见的坑不是端口不够，而是**连接池没配好导致短连接疯狂创建和销毁**，把临时端口耗光。排查时优先看连接池和 keep-alive 是否生效，不要一上来就改内核参数。

详细介绍：[一台主机上只能保持最多 65535 个 TCP 连接吗？](https://github.com/Snailclimb/JavaGuide/blob/main/docs/maximum-number-of-tcp-connections-per-host.md)

### 【IP】

#### IP 协议的作用是什么？

**IP（Internet Protocol，网际协议）** 是 TCP/IP 协议中最重要的协议之一，属于网络层的协议，主要作用是定义数据包的格式、对数据包进行路由和寻址，以便它们可以跨网络传播并到达正确的目的地。

目前 IP 协议主要分为两种，一种是过去的 IPv4，另一种是较新的 IPv6，目前这两种协议都在使用，但后者已经被提议来取代前者。

#### 什么是 IP 地址？IP 寻址如何工作？

IP 地址通常分配给网络接口，用于在特定作用域和路由上下文中标识通信端点。一个接口可以有多个地址，地址也可能动态变化；私有地址可以在不同网络中重复使用，Anycast 地址还可以分配给多个接口。IPv4 地址示例为 `192.168.1.1`，IPv6 地址示例为 `2001:0db8:85a3:0000:0000:8a2e:0370:7334`。

当网络设备发送 IP 数据包时，数据包中包含 **源 IP 地址** 和 **目的 IP 地址**。它们标识本次通信使用的源接口地址和目标地址，而不是设备永久不变的身份。

网络设备根据目的 IP 地址来判断数据包的目的地，并将数据包转发到正确的目的地网络或子网络，从而实现了设备间的通信。

这种基于 IP 地址的寻址方式是互联网通信的基础，它允许数据包在不同网络之间传递。地址是否唯一、能否全局路由取决于地址类型和作用域，不能笼统地把 IP 地址描述为每台设备全球唯一的身份证。

![IP 地址使数据包到达其目的地](images/internet_protocol_ip_address_diagram-ec6271a2.png)

#### 什么是 IP 地址过滤？

**IP 地址过滤（IP Address Filtering）** 简单来说就是限制或阻止特定 IP 地址或 IP 地址范围的访问。例如，你有一个图片服务突然被某一个 IP 地址攻击，那我们就可以禁止这个 IP 地址访问图片服务。

IP 地址过滤是一种简单的网络安全措施，实际应用中一般会结合其他网络安全措施，如认证、授权、加密等一起使用。单独使用 IP 地址过滤并不能完全保证网络的安全。

#### ⭐️ IPv4 和 IPv6 有什么区别？

**IPv4（Internet Protocol version 4）** 是目前广泛使用的 IP 地址版本，其格式是四组由点分隔的数字，例如：123.89.46.72。IPv4 使用 32 位地址作为其 Internet 地址，这意味着共有约 42 亿（2^32）个可用 IP 地址。

![IPv4 地址使用点分十进制格式表示 32 位地址](images/Figure-1-IPv4Addressformatwithdotteddecimalnotation-29c824f6-233c4843.png)

这么少当然不够用啦！为了解决 IP 地址耗尽的问题，最根本的办法是采用具有更大地址空间的新版本 IP 协议 - **IPv6（Internet Protocol version 6）**。IPv6 地址使用更复杂的格式，该格式使用由单或双冒号分隔的一组数字和字母，例如：2001:0db8:85a3:0000:0000:8a2e:0370:7334。IPv6 使用 128 位互联网地址，这意味着越有 2^128（3 开头的 39 位数字，恐怖如斯）个可用 IP 地址。

![IPv6 地址使用十六进制冒号分隔格式表示 128 位地址](images/Figure-2-IPv6Addressformatwithhexadecimalnotation-7da3a419bd-78d646ff.png)

除了更大的地址空间之外，IPv6 的优势还包括：

- **无状态地址自动配置（Stateless Address Autoconfiguration，简称 SLAAC）**：主机可以根据路由器通告的前缀和接口标识生成 IPv6 地址，不必依赖 DHCPv6 分配地址。地址使用前通常会执行重复地址检测（DAD），但 DAD 检查的是本链路内是否存在重复，而且检测并非完全可靠，不能据此声称地址得到“全球唯一”保证。
- **NAT（Network Address Translation，网络地址转换）成为可选项**：IPv6 地址资源充足，可以给全球每个设备一个独立的地址。
- **对标头结构进行了改进**：IPv6 基本头部简化了常见转发路径上的部分处理，但实际性能仍取决于硬件、扩展头、网络策略和具体实现，不能只凭头部结构保证整体性能一定提高。
- **可选的扩展头**：允许在 IPv6 标头中添加不同的扩展头（Extension Headers），用于实现不同类型的功能和选项。
- **ICMPv6（Internet Control Message Protocol for IPv6）**：IPv6 中的 ICMPv6 相较于 IPv4 中的 ICMP 有了一些改进，如邻居发现、路径 MTU 发现等功能的改进，从而提升了网络的可靠性和性能。
- ……

#### 如何获取客户端真实 IP？

获取客户端真实 IP 的方法有多种，主要分为应用层方法、传输层方法和网络层方法。

**应用层方法**：

`X-Forwarded-For` 是 HTTP 代理生态中广泛使用但未标准化的请求头；IETF 标准化的对应机制是 HTTP `Forwarded` 头。它们都属于 HTTP，不能直接套用于 SMTP 等其他应用层协议。业务服务也不能无条件信任客户端传入的 `X-Forwarded-For`：可信反向代理应覆盖或规范化外部传入值，服务端只解析由已知代理追加的部分。

**传输层方法**：

利用 TCP Options 字段承载真实源 IP 信息。这种方法适用于任何基于 TCP 的协议，不受应用层的限制。不过，这并非是 TCP 标准所支持的，所以需要通信双方都进行改造。也就是：对于发送方来说，需要有能力把真实源 IP 插入到 TCP Options 里面。对于接收方来说，需要有能力把 TCP Options 里面的 IP 地址读取出来。

也可以通过 Proxy Protocol 协议来传递客户端 IP 和 Port 信息。这种方法可以利用 Nginx 或者其他支持该协议的反向代理服务器来获取真实 IP 或者在业务服务器解析真实 IP。

**网络层方法**：

隧道 + DSR 模式。这种方法可以适用于任何协议，就是实施起来会比较麻烦，也存在一定限制，实际应用中一般不会使用这种方法。

#### NAT 的作用是什么？

**NAT（Network Address Translation，网络地址转换）** 主要用于在不同网络之间转换 IP 地址。它允许将私有 IP 地址（如在局域网中使用的 IP 地址）映射为公有 IP 地址（在互联网中使用的 IP 地址）或者反向映射，从而实现局域网内的多个设备通过单一公有 IP 地址访问互联网。

NAT 不光可以缓解 IPv4 地址资源短缺的问题，还会隐藏内部地址和拓扑。许多 NAT 设备的过滤行为使没有既有映射的外部流量难以直接到达内部主机，但决定哪些入站报文可以通过的是过滤策略，而不是地址转换本身。NAT 不能替代状态防火墙、访问控制和主机安全措施。

![NAT 实现 IP地址转换](images/network-address-translation-f95898ff.png)

相关阅读：[NAT 协议详解（网络层）](https://javaguide.cn/cs-basics/network/nat.html)。

### 【ARP】

#### 什么是 Mac 地址？

MAC 地址的全称是 **媒体访问控制地址（Media Access Control Address）**，用于标识链路层接口并在本地网络中传输数据帧。它属于网络接口，而不是整台设备的永久身份证；一台设备可以有多个网络接口，每个接口可以使用不同的 MAC 地址。

![路由器的背面就会注明 MAC 位址](images/router-back-will-indicate-mac-address-8fe99cd5.png)

MAC 地址也常被称为 LAN 地址、物理地址或以太网地址。与用于网络层路由的 IP 地址不同，MAC 地址主要在当前链路或广播域内使用。

> 还有一点要知道的是，不仅仅是网络资源才有 IP 地址，网络设备也有 IP 地址，比如路由器。但从结构上说，路由器等网络设备的作用是组成一个网络，而且通常是内网，所以它们使用的 IP 地址通常是内网 IP，内网的设备在与内网以外的设备进行通信时，需要用到 NAT 协议。

以太网常见的 MAC 地址是 6 字节（48 比特）的 EUI-48。IEEE 会分配 MA-L、MA-M、MA-S 等不同大小的地址块，由厂商继续分配全局管理地址；此外还存在本地管理地址，不需要由 IEEE 全局分配。操作系统可以修改或随机化 MAC 地址，因此地址并不保证永久不变，不同网络中也可能出现相同地址。

最后，记住，MAC 地址有一个特殊地址：FF-FF-FF-FF-FF-FF（全 1 地址），该地址表示广播地址。

#### ⭐️ ARP 协议解决了什么问题？

ARP 协议，全称 **地址解析协议（Address Resolution Protocol）**，它解决的是网络层地址和链路层地址之间的转换问题。因为一个 IP 数据报在物理上传输的过程中，总是需要知道下一跳（物理上的下一个目的地）该去往何处，但 IP 地址属于逻辑地址，而 MAC 地址才是物理地址，ARP 协议解决了 IP 地址转 MAC 地址的一些问题。

#### ARP 协议的工作原理？

[ARP 协议详解(网络层)](https://javaguide.cn/cs-basics/network/arp.html)

### 【复习建议】

#### 复习建议

非常推荐大家看一下 《图解 HTTP》这本书，这本书页数不多，但是内容很是充实，不管是用来系统的掌握网络方面的一些知识还是说纯粹为了应付面试都有很大帮助。下面的一些文章只是参考。大二学习这门课程的时候，我们使用的教材是 《计算机网络第七版》（谢希仁编著），不推荐大家看这本教材，书非常厚而且知识偏理论，不确定大家能不能心平气和的读完。

#### 参考

- 《图解 HTTP》
- 《计算机网络自顶向下方法》（第七版）
- 什么是 Internet 协议（IP）？：
- 透传真实源 IP 的各种方法 - 极客时间：
- What Is NAT and What Are the Benefits of NAT Firewalls?：

<!-- @include: @article-footer.snippet.md -->

## Java 并发

> 线程池、锁、JMM、并发容器——Java 服务端 Agent 的并发基础（89 题）

### 【线程】

#### ⭐️ 什么是线程和进程？

#### 何为进程？

进程是程序的一次执行过程，是系统运行程序的基本单位，因此进程是动态的。系统运行一个程序即是一个进程从创建，运行到消亡的过程。

在 Java 中，当我们启动 main 函数时其实就是启动了一个 JVM 的进程，而 main 函数所在的线程就是这个进程中的一个线程，也称主线程。

如下图所示，在 Windows 中通过查看任务管理器的方式，我们就可以清楚看到 Windows 当前运行的进程（`.exe` 文件的运行）。

![进程示例图片-Windows](images/_E8_BF_9B_E7_A8_8B_E7_A4_BA_E4_BE_8B_E5_9B_BE_E7_89_87-Windo-4993191f.png)

#### 何为线程？

线程与进程相似，但线程是一个比进程更小的执行单位。一个进程在其执行的过程中可以产生多个线程。与进程不同的是同类的多个线程共享进程的**堆**和**方法区**资源，但每个线程有自己的**程序计数器**、**虚拟机栈**和**本地方法栈**，所以系统在产生一个线程，或是在各个线程之间做切换工作时，负担要比进程小得多，也正因为如此，线程也被称为轻量级进程。

Java 程序天生就是多线程程序，我们可以通过 JMX 来看看一个普通的 Java 程序有哪些线程，代码如下。

```java
public class MultiThread {
	public static void main(String[] args) {
		// 获取 Java 线程管理 MXBean
	ThreadMXBean threadMXBean = ManagementFactory.getThreadMXBean();
		// 不需要获取同步的 monitor 和 synchronizer 信息，仅获取线程和线程堆栈信息
		ThreadInfo[] threadInfos = threadMXBean.dumpAllThreads(false, false);
		// 遍历线程信息，仅打印线程 ID 和线程名称信息
		for (ThreadInfo threadInfo : threadInfos) {
			System.out.println("[" + threadInfo.getThreadId() + "] " + threadInfo.getThreadName());
		}
	}
}
```

上述程序输出如下（输出内容可能不同，不用太纠结下面每个线程的作用，只用知道 main 线程执行 main 方法即可）：

```plain
[5] Attach Listener //添加事件
[4] Signal Dispatcher // 分发处理给 JVM 信号的线程
[3] Finalizer //调用对象 finalize 方法的线程
[2] Reference Handler //清除 reference 线程
[1] main //main 线程,程序入口
```

从上面的输出内容可以看出：**一个 Java 程序的运行是 main 线程和多个其他线程同时运行**。

#### Java 线程和操作系统的线程有啥区别？

早期 JDK 曾使用绿色线程（Green Threads）实现用户级线程。后来，HotSpot 中通过 `new Thread()` 创建的传统线程采用平台线程（Platform Thread）实现，平台线程通常以 1:1 方式映射到操作系统线程，由操作系统负责调度。Java 21 正式引入的虚拟线程（Virtual Thread）则由 JVM 调度，大量虚拟线程可以复用较少的平台线程作为载体，因此不能再把所有 Java 线程都等同于操作系统线程。

我们上面提到了用户线程和内核线程，考虑到很多读者不太了解二者的区别，这里简单介绍一下：

- 用户线程：由用户空间程序管理和调度的线程，运行在用户空间（专门给应用程序使用）。
- 内核线程：由操作系统内核管理和调度的线程，运行在内核空间（只有内核程序可以访问）。

顺便简单总结一下用户线程和内核线程的区别和特点：用户级线程通常由运行时在用户空间调度，创建和切换成本较低；能否利用多核取决于用户线程与内核线程之间的映射模型，多对一模型不能并行利用多核，多对多模型则可以。内核线程由操作系统调度，创建和切换成本通常更高，可以直接利用多核。

一句话概括 Java 线程和操作系统线程的关系：**平台线程通常映射到操作系统线程，而虚拟线程由 JVM 调度并挂载到平台线程上执行**。

线程模型是用户线程和内核线程之间的关联方式，常见的线程模型有这三种：

1. 一对一（一个用户线程对应一个内核线程）
2. 多对一（多个用户线程映射到一个内核线程）
3. 多对多（多个用户线程映射到多个内核线程）

![常见的三种线程模型](images/three-types-of-thread-models-6adf6f60.png)

在 Windows 和 Linux 等主流操作系统中，HotSpot 的平台线程通常采用一对一模型，也就是一个平台线程对应一个操作系统线程。虚拟线程不采用这种一对一映射，而是由 JVM 调度到一组平台线程上执行。

#### ⭐️ 请简要描述线程与进程的关系，区别及优缺点？

下图是 Java 内存区域，通过下图我们从 JVM 的角度来说一下线程和进程之间的关系。

![Java 运行时数据区域（JDK1.8 之后）](images/java-runtime-data-areas-jdk1.8-6401fdf0.png)

从上图可以看出：一个进程中可以有多个线程，多个线程共享进程的**堆**和**方法区（JDK1.8 之后的元空间）**资源，但是每个线程有自己的**程序计数器**、**虚拟机栈** 和 **本地方法栈**。

**总结：** 线程是进程划分成的更小的运行单位。线程和进程最大的不同在于基本上各进程是独立的，而各线程则不一定，因为同一进程中的线程极有可能会相互影响。线程执行开销小，但不利于资源的管理和保护；而进程正相反。

下面是该知识点的扩展内容！

下面来思考这样一个问题：为什么**程序计数器**、**虚拟机栈**和**本地方法栈**是线程私有的呢？为什么堆和方法区是线程共享的呢？

#### 程序计数器为什么是私有的？

程序计数器主要有下面两个作用：

1. 字节码解释器通过改变程序计数器来依次读取指令，从而实现代码的流程控制，如：顺序执行、选择、循环、异常处理。
2. 在多线程的情况下，程序计数器用于记录当前线程执行的位置，从而当线程被切换回来的时候能够知道该线程上次运行到哪儿了。

需要注意的是，如果执行的是 native 方法，那么程序计数器记录的是 undefined 地址，只有执行的是 Java 代码时程序计数器记录的才是下一条指令的地址。

所以，程序计数器私有主要是为了**线程切换后能恢复到正确的执行位置**。

#### 虚拟机栈和本地方法栈为什么是私有的？

- **虚拟机栈：** 每个 Java 方法在执行之前会创建一个栈帧用于存储局部变量表、操作数栈、常量池引用等信息。从方法调用直至执行完成的过程，就对应着一个栈帧在 Java 虚拟机栈中入栈和出栈的过程。
- **本地方法栈：** 和虚拟机栈所发挥的作用非常相似，区别是：**虚拟机栈为虚拟机执行 Java 方法（也就是字节码）服务，而本地方法栈则为虚拟机使用到的 Native 方法服务。** 在 HotSpot 虚拟机中和 Java 虚拟机栈合二为一。

所以，为了**保证线程中的局部变量不被别的线程访问到**，虚拟机栈和本地方法栈是线程私有的。

#### 一句话简单了解堆和方法区

堆和方法区是所有线程共享的资源，其中堆是进程中最大的一块内存，主要用于存放新创建的对象（几乎所有对象都在这里分配内存），方法区主要用于存放已被加载的类信息、常量、静态变量、即时编译器编译后的代码等数据。

#### 如何创建线程？

一般来说，创建线程有很多种方式，例如继承 `Thread` 类、实现 `Runnable` 接口、实现 `Callable` 接口、使用线程池、使用 `CompletableFuture` 类等等。

不过，这些方式其实并没有真正创建出线程。准确点来说，这些都属于是在 Java 代码中使用多线程的方法。

严格来说，Java 就只有一种方式可以创建线程，那就是通过 `new Thread().start()` 创建。不管是哪种方式，最终还是依赖于 `new Thread().start()`。

#### ⭐️ 说说线程的生命周期和状态？

Java 线程在运行的生命周期中的指定时刻只可能处于下面 6 种不同状态的其中一个状态：

- NEW: 初始状态，线程被创建出来但没有被调用 `start()`。
- RUNNABLE: 运行状态，线程被调用了 `start()` 等待运行的状态。
- BLOCKED：阻塞状态，需要等待锁释放。
- WAITING：等待状态，表示该线程需要等待其他线程做出一些特定动作（通知或中断）。
- TIMED_WAITING：超时等待状态，可以在指定的时间后自行返回而不是像 WAITING 那样一直等待。
- TERMINATED：终止状态，表示该线程已经运行完毕。

线程在生命周期中并不是固定处于某一个状态而是随着代码的执行在不同状态之间切换。

Java 线程状态变迁图(图源：[挑错 |《Java 并发编程的艺术》中关于线程状态的三处错误](https://mp.weixin.qq.com/s/0UTyrJpRKaKhkhHcQtXAiA))：

![Java 线程状态变迁图](images/640-8103777c.png)

由上图可以看出：线程创建之后它将处于 **NEW（新建）** 状态，调用 `start()` 方法后开始运行，线程这时候处于 **READY（可运行）** 状态。可运行状态的线程获得了 CPU 时间片（timeslice）后就处于 **RUNNING（运行）** 状态。

> 在操作系统层面，线程有 READY 和 RUNNING 状态；而在 JVM 层面，只能看到 RUNNABLE 状态（图源：[HowToDoInJava](https://howtodoinJava.com/ "HowToDoInJava")：[Java Thread Life Cycle and Thread States](https://howtodoinJava.com/Java/multi-threading/Java-thread-life-cycle-and-thread-states/ "Java Thread Life Cycle and Thread States")），所以 Java 系统一般将这两个状态统称为 **RUNNABLE（运行中）** 状态。
>
> **为什么 JVM 没有区分这两种状态呢？** Java 的 `Thread.State` 描述的是 JVM 层面的线程状态，不用于反映操作系统调度器的全部内部状态。具体调度策略、时间片长度和是否采用轮转方式都由操作系统及其配置决定，不能固定概括为 10～20 ms 的轮转调度。

![RUNNABLE-VS-RUNNING](images/RUNNABLE-VS-RUNNING-497c7636.png)

- 当线程执行 `wait()` 方法之后，线程进入 **WAITING（等待）** 状态。进入等待状态的线程需要依靠其他线程的通知才能够返回到运行状态。
- **TIMED_WAITING（超时等待）** 状态相当于在等待状态的基础上增加了超时限制，比如通过 `sleep（long millis）` 方法或 `wait（long millis）` 方法可以将线程置于 TIMED_WAITING 状态。当超时时间结束后，线程将会返回到 RUNNABLE 状态。
- 当线程进入 `synchronized` 方法/块或者调用 `wait` 后（被 `notify`）重新进入 `synchronized` 方法/块，但是锁被其它线程占有，这个时候线程就会进入 **BLOCKED（阻塞）** 状态。
- 线程在执行完了 `run()` 方法之后将会进入到 **TERMINATED（终止）** 状态。

#### 什么是线程上下文切换？

线程在执行过程中会有自己的运行条件和状态（也称上下文），比如上文所说到过的程序计数器，栈信息等。当出现如下情况的时候，线程会从占用 CPU 状态中退出。

- 主动让出 CPU，比如调用了 `sleep()`, `wait()` 等。
- 时间片用完，因为操作系统要防止一个线程或者进程长时间占用 CPU 导致其他线程或者进程饿死。
- 调用了阻塞类型的系统中断，比如请求 IO，线程被阻塞。
- 被终止或结束运行

这其中前三种都会发生线程切换，线程切换意味着需要保存当前线程的上下文，留待线程下次占用 CPU 的时候恢复现场。并加载下一个将要占用 CPU 的线程上下文。这就是所谓的 **上下文切换**。

上下文切换是现代操作系统的基本功能，因其每次需要保存信息恢复信息，这将会占用 CPU，内存等系统资源进行处理，也就意味着效率会有一定损耗，如果频繁切换就会造成整体效率低下。

#### Thread#sleep() 方法和 Object#wait() 方法对比

**共同点**：两者都可以暂停线程的执行。

**区别**：

- **`sleep()` 方法没有释放锁，而 `wait()` 方法释放了锁**。
- `wait()` 通常被用于线程间交互/通信，`sleep()` 通常被用于暂停执行。
- `wait()` 方法被调用后，线程不会自动苏醒，需要别的线程调用同一个对象上的 `notify()` 或者 `notifyAll()` 方法。`sleep()` 方法执行完成后，线程会自动苏醒，或者也可以使用 `wait(long timeout)` 超时后线程会自动苏醒。
- `sleep()` 是 `Thread` 类的静态本地方法，`wait()` 则是 `Object` 类的本地方法。为什么这样设计呢？下一个问题就会聊到。

#### 为什么 wait() 方法不定义在 Thread 中？

`wait()` 是让获得对象锁的线程实现等待，会自动释放当前线程占有的对象锁。每个对象（`Object`）都拥有对象锁，既然要释放当前线程占有的对象锁并让其进入 WAITING 状态，自然是要操作对应的对象（`Object`）而非当前的线程（`Thread`）。

类似的问题：**为什么 `sleep()` 方法定义在 `Thread` 中？**

因为 `sleep()` 是让当前线程暂停执行，不涉及到对象类，也不需要获得对象锁。

#### 可以直接调用 Thread 类的 run 方法吗？

这是另一个非常经典的 Java 多线程面试问题，而且在面试中会经常被问到。很简单，但是很多人都会答不上来！

new 一个 `Thread`，线程进入了新建状态。调用 `start()` 方法，会启动一个线程并使线程进入了就绪状态，当分配到时间片后就可以开始运行了。 `start()` 会执行线程的相应准备工作，然后自动执行 `run()` 方法的内容，这是真正的多线程工作。 但是，直接执行 `run()` 方法，会把 `run()` 方法当成一个普通方法在调用该方法的线程去执行，所以这并不是多线程工作。

**总结：调用 `start()` 方法方可启动线程并使线程进入就绪状态，直接执行 `run()` 方法的话不会以多线程的方式执行。**

### 【多线程】

#### 并发与并行的区别

- **并发**：两个及两个以上的作业在同一 **时间段** 内执行。
- **并行**：两个及两个以上的作业在同一 **时刻** 执行。

最关键的点是：是否是 **同时** 执行。

#### 同步和异步的区别

- **同步**：发出一个调用之后，在没有得到结果之前， 该调用就不可以返回，一直等待。
- **异步**：调用在发出之后，不用等待返回结果，该调用直接返回。

#### ⭐️ 为什么要使用多线程？

先从总体上来说：

- **从计算机底层来说：** 线程可以比作是轻量级的进程，是程序执行的最小单位，线程间的切换和调度的成本远远小于进程。另外，多核 CPU 时代意味着多个线程可以同时运行，这减少了线程上下文切换的开销。
- **从当代互联网发展趋势来说：** 现在的系统动不动就要求百万级甚至千万级的并发量，而多线程并发编程正是开发高并发系统的基础，利用好多线程机制可以大大提高系统整体的并发能力以及性能。

再深入到计算机底层来探讨：

- **单核时代**：在单核时代多线程主要是为了提高单进程利用 CPU 和 IO 系统的效率。 假设只运行了一个 Java 进程的情况，当我们请求 IO 的时候，如果 Java 进程中只有一个线程，此线程被 IO 阻塞则整个进程被阻塞。CPU 和 IO 设备只有一个在运行，那么可以简单地说系统整体效率只有 50%。当使用多线程的时候，一个线程被 IO 阻塞，其他线程还可以继续使用 CPU。从而提高了 Java 进程利用系统资源的整体效率。
- **多核时代**: 多核时代多线程主要是为了提高进程利用多核 CPU 的能力。举个例子：假如我们要计算一个复杂的任务，我们只用一个线程的话，不论系统有几个 CPU 核心，都只会有一个 CPU 核心被利用到。而创建多个线程，这些线程可以被映射到底层多个 CPU 核心上执行，在任务中的多个线程没有资源竞争的情况下，任务执行的效率会有显著性的提高，约等于（单核时执行时间/CPU 核心数）。

#### ⭐️ 单核 CPU 支持 Java 多线程吗？

单核 CPU 是支持 Java 多线程的。操作系统通过时间片轮转的方式，将 CPU 的时间分配给不同的线程。尽管单核 CPU 一次只能执行一个任务，但通过快速在多个线程之间切换，可以让用户感觉多个任务是同时进行的。

这里顺带提一下 Java 使用的线程调度方式。

操作系统主要通过两种线程调度方式来管理多线程的执行：

- **抢占式调度（Preemptive Scheduling）**：操作系统决定何时暂停当前正在运行的线程，并切换到另一个线程执行。这种切换通常是由系统时钟中断（时间片轮转）或其他高优先级事件（如 I/O 操作完成）触发的。这种方式存在上下文切换开销，但公平性和 CPU 资源利用率较好，不易阻塞。
- **协同式调度（Cooperative Scheduling）**：线程执行完毕后，主动通知系统切换到另一个线程。这种方式可以减少上下文切换带来的性能开销，但公平性较差，容易阻塞。

Java 使用的线程调度是抢占式的。也就是说，JVM 本身不负责线程的调度，而是将线程的调度委托给操作系统。操作系统通常会基于线程优先级和时间片来调度线程的执行，高优先级的线程通常获得 CPU 时间片的机会更多。

#### ⭐️ 单核 CPU 上运行多个线程效率一定会高吗？

单核 CPU 同时运行多个线程的效率是否会高，取决于线程的类型和任务的性质。一般来说，有两种类型的线程：

1. **CPU 密集型**：CPU 密集型的线程主要进行计算和逻辑处理，需要占用大量的 CPU 资源。
2. **IO 密集型**：IO 密集型的线程主要进行输入输出操作，如读写文件、网络通信等，需要等待 IO 设备的响应，而不占用太多的 CPU 资源。

在单核 CPU 上，同一时刻只能有一个线程在运行，其他线程需要等待 CPU 的时间片分配。如果线程是 CPU 密集型的，那么多个线程同时运行会导致频繁的线程切换，增加了系统的开销，降低了效率。如果线程是 IO 密集型的，那么多个线程同时运行可以利用 CPU 在等待 IO 时的空闲时间，提高了效率。

因此，对于单核 CPU 来说，如果任务是 CPU 密集型的，那么开很多线程会影响效率；如果任务是 IO 密集型的，那么开很多线程会提高效率。当然，这里的“很多”也要适度，不能超过系统能够承受的上限。

#### 使用多线程可能带来什么问题？

并发编程的目的就是为了能提高程序的执行效率进而提高程序的运行速度，但是并发编程并不总是能提高程序运行速度的，而且并发编程可能会遇到很多问题，比如：内存泄漏、死锁、线程不安全等等。

#### 如何理解线程安全和不安全？

线程安全和不安全是在多线程环境下对于同一份数据的访问是否能够保证其正确性和一致性的描述。

- 线程安全指的是在多线程环境下，对于同一份数据，不管有多少个线程同时访问，都能保证这份数据的正确性和一致性。
- 线程不安全则表示在多线程环境下，对于同一份数据，多个线程同时访问时可能会导致数据混乱、错误或者丢失。

### 【⭐️ 死锁】

#### 什么是线程死锁？

线程死锁描述的是这样一种情况：多个线程同时被阻塞，它们中的一个或者全部都在等待某个资源被释放。由于线程被无限期地阻塞，因此程序不可能正常终止。

如下图所示，线程 A 持有资源 2，线程 B 持有资源 1，他们同时都想申请对方的资源，所以这两个线程就会互相等待而进入死锁状态。

![死锁场景示意图：线程 A 持有 resource1 并等待 resource2，线程 B 持有 resource2 并等待 resource1，等待链形成闭环](images/dead-lock-deadlock-scenario-13be7e13.png)

下面通过一个例子来说明线程死锁，代码模拟了上图的死锁的情况（代码来源于《并发编程之美》）：

```java
public class DeadLockDemo {
    private static Object resource1 = new Object();//资源 1
    private static Object resource2 = new Object();//资源 2

    public static void main(String[] args) {
        new Thread(() -> {
            synchronized (resource1) {
                System.out.println(Thread.currentThread() + "get resource1");
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
                System.out.println(Thread.currentThread() + "waiting get resource2");
                synchronized (resource2) {
                    System.out.println(Thread.currentThread() + "get resource2");
                }
            }
        }, "线程 1").start();

        new Thread(() -> {
            synchronized (resource2) {
                System.out.println(Thread.currentThread() + "get resource2");
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
                System.out.println(Thread.currentThread() + "waiting get resource1");
                synchronized (resource1) {
                    System.out.println(Thread.currentThread() + "get resource1");
                }
            }
        }, "线程 2").start();
    }
}
```

Output

```plain
Thread[线程 1,5,main]get resource1
Thread[线程 2,5,main]get resource2
Thread[线程 1,5,main]waiting get resource2
Thread[线程 2,5,main]waiting get resource1
```

线程 A 通过 `synchronized (resource1)` 获得 `resource1` 的监视器锁，然后通过 `Thread.sleep(1000);` 让线程 A 休眠 1s，为的是让线程 B 得到执行然后获取到 resource2 的监视器锁。线程 A 和线程 B 休眠结束了都开始企图请求获取对方的资源，然后这两个线程就会陷入互相等待的状态，这也就产生了死锁。

上面的例子符合产生死锁的四个必要条件：

1. **互斥条件**：该资源任意一个时刻只由一个线程占用。
2. **请求与保持条件**：一个线程因请求资源而阻塞时，对已获得的资源保持不放。
3. **不剥夺条件**：线程已获得的资源在未使用完之前不能被其他线程强行剥夺，只有自己使用完毕后才释放资源。
4. **循环等待条件**：若干线程之间形成一种头尾相接的循环等待资源关系。

#### 如何检测死锁？

- 使用 `jstack ` 或 `jcmd  Thread.print -l` 查看线程栈和并发锁信息。如果检测到 Java 级别的死锁，输出中会列出相关线程及其持有、等待的锁。`jmap` 主要用于查看堆信息或生成堆转储，不是线程死锁诊断工具。
- 采用 VisualVM、JConsole 等工具进行排查。

这里以 JConsole 工具为例进行演示。

首先，我们要找到 JDK 的 bin 目录，找到 jconsole 并双击打开。

![jconsole](images/jdk-home-bin-jconsole-2cf07489.png)

对于 MAC 用户来说，可以通过 `/usr/libexec/java_home -V` 查看 JDK 安装目录，找到后通过 `open . + 文件夹地址` 打开即可。例如，我本地的某个 JDK 的路径是：

```bash
 open . /Users/guide/Library/Java/JavaVirtualMachines/corretto-1.8.0_252/Contents/Home
```

打开 jconsole 后，连接对应的程序，然后进入线程界面选择检测死锁即可！

![jconsole 检测死锁](images/jconsole-check-deadlock-29a7f927.png)

![jconsole 检测到死锁](images/jconsole-check-deadlock-done-3ff1d402.png)

#### 如何预防和避免线程死锁？

**如何预防死锁？** 破坏死锁的产生的必要条件即可：

1. **破坏请求与保持条件**：一次性申请所有的资源。
2. **破坏不剥夺条件**：占用部分资源的线程进一步申请其他资源时，如果申请不到，可以主动释放它占有的资源。
3. **破坏循环等待条件**：靠按序申请资源来预防。按某一顺序申请资源，释放资源则反序释放。破坏循环等待条件。

**如何避免死锁？**

避免死锁就是在资源分配时，借助于算法（比如银行家算法）对资源分配进行计算评估，使其进入安全状态。

> **安全状态** 指的是系统能够按照某种线程推进顺序（P1、P2、P3……Pn）来为每个线程分配所需资源，直到满足每个线程对资源的最大需求，使每个线程都可顺利完成。称  序列为安全序列。

我们对线程 2 的代码修改成下面这样就不会产生死锁了。

```java
new Thread(() -> {
            synchronized (resource1) {
                System.out.println(Thread.currentThread() + "get resource1");
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
                System.out.println(Thread.currentThread() + "waiting get resource2");
                synchronized (resource2) {
                    System.out.println(Thread.currentThread() + "get resource2");
                }
            }
        }, "线程 2").start();
```

输出：

```plain
Thread[线程 1,5,main]get resource1
Thread[线程 1,5,main]waiting get resource2
Thread[线程 1,5,main]get resource2
Thread[线程 2,5,main]get resource1
Thread[线程 2,5,main]waiting get resource2
Thread[线程 2,5,main]get resource2

Process finished with exit code 0
```

我们分析一下上面的代码为什么避免了死锁的发生？

线程 1 首先获得到 resource1 的监视器锁，这时候线程 2 就获取不到了。然后线程 1 再去获取 resource2 的监视器锁，可以获取到。然后线程 1 释放了对 resource1、resource2 的监视器锁的占用，线程 2 获取到就可以执行了。这样就破坏了循环等待条件，因此避免了死锁。

<!-- @include: @article-footer.snippet.md -->

### 【⭐️ JMM（Java 内存模型）】

#### ⭐️ JMM（Java 内存模型）

JMM（Java 内存模型）相关的问题比较多，也比较重要，于是我单独抽了一篇文章来总结 JMM 相关的知识点和问题：[JMM（Java 内存模型）详解](https://javaguide.cn/java/concurrent/jmm.html)。

### 【⭐️ volatile 关键字】

#### 如何保证变量的可见性？

在 Java 中，`volatile` 关键字可以保证变量的可见性。对某个 `volatile` 变量的写入 happens-before 于后续对同一变量的读取，因此读线程能够看到该写入以及写入前按 happens-before 传递过来的结果。这是 JMM 规定的语义，不等同于要求每次访问都绕过 CPU 缓存、直接读写物理主存。

![JMM(Java 内存模型)](images/jmm-36d9b6ac.png)

![JMM(Java 内存模型)强制在主存中进行读取](images/jmm2-a87c38b6.png)

`volatile` 关键字并非 Java 语言特有，但不同语言中的语义并不相同。Java 的 `volatile` 由 JMM 定义可见性和有序性保证，不能解释为“禁用 CPU 缓存”。

`volatile` 关键字能保证数据的可见性，但不能保证数据的原子性。`synchronized` 关键字两者都能保证。

#### 如何禁止指令重排序？

**在 Java 中，`volatile` 关键字除了可以保证变量的可见性，还有一个重要的作用就是防止 JVM 的指令重排序。** 如果我们将变量声明为 **`volatile`**，在对这个变量进行读写操作的时候，会通过插入特定的 **内存屏障** 的方式来禁止指令重排序。

在 Java 中，`Unsafe` 类提供了三个开箱即用的内存屏障相关的方法，屏蔽了操作系统底层的差异：

```java
public native void loadFence();
public native void storeFence();
public native void fullFence();
```

理论上来说，你通过这个三个方法也可以实现和 `volatile` 禁止重排序一样的效果，只是会麻烦一些。

#### 4 种内存屏障类型

在讲解 JVM 实现时，常用下面 4 类内存屏障来描述需要约束的重排序关系。它们是便于理解的实现层模型，并不是 JLS 对 JVM 必须逐条插入哪些具体屏障指令的规定：

| 屏障类型       | 指令示例                     | 说明                                                                                                                                                                                     |
| -------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **LoadLoad**   | `Load1; LoadLoad; Load2`     | 保证 `Load1` 的读取操作在 `Load2` 及其后续读取操作之前完成                                                                                                                               |
| **StoreStore** | `Store1; StoreStore; Store2` | 约束两个写操作的顺序，使 `Store1` 的效果不会晚于 `Store2` 对其他处理器可见                                                                                                               |
| **LoadStore**  | `Load1; LoadStore; Store2`   | 保证 `Load1` 的读取操作在 `Store2` 及其后续写入操作刷新到内存之前完成                                                                                                                    |
| **StoreLoad**  | `Store1; StoreLoad; Load2`   | 保证 `Store1` 的写入操作对其他处理器可见，先于 `Load2` 及其后续读取操作。`StoreLoad` 屏障的开销是四种屏障中最大的，它同时具有其他三种屏障的效果，因此也称为 **全能屏障（Full Barrier）** |

#### volatile 读写操作的内存屏障插入策略

下面是一种便于理解 `volatile` 语义的保守屏障插入策略。实际 JVM 会根据目标处理器的内存模型选择、合并或省略具体屏障，只要最终行为满足 JMM 即可：

**volatile 写操作的内存屏障插入策略：**

在每个 volatile 写操作的 **前面** 插入一个 `StoreStore` 屏障，在 **后面** 插入一个 `StoreLoad` 屏障。

```
StoreStore 屏障
volatile 写操作
StoreLoad 屏障
```

- 前面的 `StoreStore` 屏障：保证 `volatile` 写之前的普通写不会被重排序到该 `volatile` 写之后。
- 后面的 `StoreLoad` 屏障：保证 volatile 写之后，其写入的值对后续的 volatile 读/写操作可见。这是开销最大的屏障，但也是最关键的——它避免了 volatile 写与后面可能有的 volatile 读/写操作发生重排序。

**volatile 读操作的内存屏障插入策略：**

在每个 volatile 读操作的 **后面** 插入一个 `LoadLoad` 屏障和一个 `LoadStore` 屏障。

```
volatile 读操作
LoadLoad 屏障
LoadStore 屏障
```

- `LoadLoad` 屏障：保证 volatile 读之后的普通读操作不会被重排序到 volatile 读之前。
- `LoadStore` 屏障：保证 volatile 读之后的普通写操作不会被重排序到 volatile 读之前。

这样一来，volatile 写-读的组合就建立了一个类似于 **锁的释放-获取** 的语义：**volatile 写操作之前的所有操作结果，对于后续对该 volatile 变量的读操作之后的所有操作都是可见的。**

下面我以一个常见的面试题为例讲解一下 `volatile` 关键字禁止指令重排序的效果。

面试中面试官经常会说：“单例模式了解吗？来给我手写一下！给我解释一下双重检验锁方式实现单例模式的原理呗！”

**双重校验锁实现对象单例（线程安全）**：

```java
public class Singleton {

    private volatile static Singleton uniqueInstance;

    private Singleton() {
    }

    public static Singleton getUniqueInstance() {
       //先判断对象是否已经实例过，没有实例化过才进入加锁代码
        if (uniqueInstance == null) {
            //类对象加锁
            synchronized (Singleton.class) {
                if (uniqueInstance == null) {
                    uniqueInstance = new Singleton();
                }
            }
        }
        return uniqueInstance;
    }
}
```

`uniqueInstance` 采用 `volatile` 关键字修饰也是很有必要的， `uniqueInstance = new Singleton();` 这段代码其实是分为三步执行：

1. 为 `uniqueInstance` 分配内存空间
2. 初始化 `uniqueInstance`
3. 将 `uniqueInstance` 指向分配的内存地址

但是由于 JVM 具有指令重排的特性，执行顺序有可能变成 1->3->2。指令重排在单线程环境下不会出现问题，但是在多线程环境下会导致一个线程获得还没有初始化的实例。例如，线程 T1 执行了 1 和 3，此时 T2 调用 `getUniqueInstance`() 后发现 `uniqueInstance` 不为空，因此返回 `uniqueInstance`，但此时 `uniqueInstance` 还未被初始化。

#### 从内存屏障角度理解 DCL 必须使用 volatile

上面从指令重排序的角度解释了 DCL 单例中 `uniqueInstance` 为什么需要 `volatile` 修饰。下面从内存屏障的角度进一步分析 `volatile` 是如何解决这个问题的。

`uniqueInstance = new Singleton();` 这行代码的三个步骤（分配内存、初始化对象、赋值引用）中，如果不加 `volatile`，步骤 2 和步骤 3 可能会被重排序为 1→3→2。加了 `volatile` 之后，由于 `uniqueInstance` 是 volatile 变量，对它的写操作（步骤 3：将引用赋值给 `uniqueInstance`）会按照前面介绍的 volatile 写的内存屏障插入策略来处理：

1. 在 volatile 写 **之前** 插入 `StoreStore` 屏障：保证步骤 1（分配内存）和步骤 2（初始化对象）的写操作在步骤 3（赋值引用）之前完成，**禁止了步骤 2 和步骤 3 的重排序**。
2. 在 volatile 写 **之后** 插入 `StoreLoad` 屏障：约束该写与后续读写的重排序，并配合 `volatile` 读建立 JMM 要求的可见性。

这样，当线程 T2 读取 `uniqueInstance` 时（volatile 读），如果发现 `uniqueInstance != null`，那么可以保证该对象一定已经被完全初始化了。

#### volatile 与 happens-before 的关系

JMM 中的 happens-before 原则是判断数据是否存在竞争、线程是否安全的重要依据。`volatile` 变量的读写操作与 happens-before 原则有着密切的关系。

> 关于 happens-before 原则的详细介绍，可以参考 [JMM（Java 内存模型）详解](https://javaguide.cn/java/concurrent/jmm.html) 这篇文章。

happens-before 原则中与 `volatile` 直接相关的是 **volatile 变量规则**：

> **对一个 volatile 变量的写操作 happens-before 于后续对该 volatile 变量的读操作。**

也就是说，如果线程 A 写入了一个 volatile 变量，线程 B 随后读取了同一个 volatile 变量，那么线程 A 在写入 volatile 变量之前所做的所有修改（包括对非 volatile 变量的修改），对线程 B 都是可见的。

这个规则配合 happens-before 的 **传递性规则**（如果 A happens-before B，B happens-before C，那么 A happens-before C），可以实现一种轻量级的线程间通信。下面通过一个示例来说明：

```java
public class VolatileHappensBeforeDemo {
    private int a = 0;
    private int b = 0;
    private volatile boolean flag = false;

    // 线程 A 执行
    public void writer() {
        a = 1;           // 操作1：普通写
        b = 2;           // 操作2：普通写
        flag = true;     // 操作3：volatile 写
    }

    // 线程 B 执行
    public void reader() {
        if (flag) {      // 操作4：volatile 读
            int x = a;   // 操作5：普通读，x 一定等于 1
            int y = b;   // 操作6：普通读，y 一定等于 2
            System.out.println("x=" + x + ", y=" + y);
        }
    }
}
```

上面代码中，happens-before 关系链如下：

1. 操作 1、操作 2 happens-before 操作 3（**程序顺序规则**：同一线程中，前面的操作 happens-before 后面的操作）
2. 操作 3 happens-before 操作 4（**volatile 变量规则**：volatile 写 happens-before volatile 读）
3. 操作 4 happens-before 操作 5、操作 6（**程序顺序规则**）

根据 **传递性**：操作 1、操作 2 happens-before 操作 5、操作 6。

因此，当线程 B 在操作 4 读取到 `flag == true` 时，线程 A 在操作 3 之前对 `a` 和 `b` 的修改对线程 B 一定是可见的。这里的关键在于：**volatile 变量的写-读操作，不仅保证了 volatile 变量本身的可见性，还通过 happens-before 的传递性“顺带”保证了其前后普通变量的可见性。**

这也解释了为什么在实际开发中，`volatile` 经常被用作 **状态标志位**（如上面例子中的 `flag`），它可以在不使用锁的情况下，安全地在线程间传递状态信息，同时保证相关数据的可见性。

#### volatile 可以保证原子性么？

**`volatile` 关键字能保证变量的可见性，但不能保证对变量的操作是原子性的。**

我们通过下面的代码即可证明：

```java
/**
 * 微信搜 JavaGuide 回复"面试突击"即可免费领取个人原创的 Java 面试手册
 *
 * @author Guide哥
 * @date 2022/08/03 13:40
 **/
public class VolatileAtomicityDemo {
    public volatile static int inc = 0;

    public void increase() {
        inc++;
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService threadPool = Executors.newFixedThreadPool(5);
        VolatileAtomicityDemo volatileAtomicityDemo = new VolatileAtomicityDemo();
        for (int i = 0; i < 5; i++) {
            threadPool.execute(() -> {
                for (int j = 0; j < 500; j++) {
                    volatileAtomicityDemo.increase();
                }
            });
        }
        // 等待1.5秒，保证上面程序执行完成
        Thread.sleep(1500);
        System.out.println(inc);
        threadPool.shutdown();
    }
}
```

正常情况下，运行上面的代码理应输出 `2500`。但你真正运行了上面的代码之后，你会发现每次输出结果都小于 `2500`。

为什么会出现这种情况呢？不是说好了，`volatile` 可以保证变量的可见性嘛！

也就是说，如果 `volatile` 能保证 `inc++` 操作的原子性的话。每个线程中对 `inc` 变量自增完之后，其他线程可以立即看到修改后的值。5 个线程分别进行了 500 次操作，那么最终 inc 的值应该是 5\*500=2500。

很多人会误认为自增操作 `inc++` 是原子性的，实际上，`inc++` 其实是一个复合操作，包括三步：

1. 读取 inc 的值。
2. 对 inc 加 1。
3. 将 inc 的值写回内存。

`volatile` 是无法保证这三个操作是具有原子性的，有可能导致下面这种情况出现：

1. 线程 1 对 `inc` 进行读取操作之后，还未对其进行修改。线程 2 又读取了 `inc` 的值并对其进行修改（+1），再将 `inc` 的值写回内存。
2. 线程 2 操作完毕后，线程 1 对 `inc` 的值进行修改（+1），再将 `inc` 的值写回内存。

这也就导致两个线程分别对 `inc` 进行了一次自增操作后，`inc` 实际上只增加了 1。

其实，如果想要保证上面的代码运行正确也非常简单，利用 `synchronized`、`Lock` 或者 `AtomicInteger` 都可以。

使用 `synchronized` 改进：

```java
public synchronized void increase() {
    inc++;
}
```

使用 `AtomicInteger` 改进：

```java
public AtomicInteger inc = new AtomicInteger();

public void increase() {
    inc.getAndIncrement();
}
```

使用 `ReentrantLock` 改进：

```java
Lock lock = new ReentrantLock();
public void increase() {
    lock.lock();
    try {
        inc++;
    } finally {
        lock.unlock();
    }
}
```

### 【⭐️ 乐观锁和悲观锁】

#### 什么是悲观锁？

悲观锁总是假设最坏的情况，认为共享资源每次被访问的时候就会出现问题（比如共享数据被修改），所以每次在获取资源操作的时候都会上锁，这样其他线程想拿到这个资源就会阻塞直到锁被上一个持有者释放。也就是说，**共享资源每次只给一个线程使用，其它线程阻塞，用完后再把资源转让给其它线程**。

像 Java 中 `synchronized` 和 `ReentrantLock` 等独占锁就是悲观锁思想的实现。

```java
public void performSynchronisedTask() {
    synchronized (this) {
        // 需要同步的操作
    }
}

private Lock lock = new ReentrantLock();
lock.lock();
try {
   // 需要同步的操作
} finally {
    lock.unlock();
}
```

高并发的场景下，激烈的锁竞争会造成线程阻塞，大量阻塞线程会导致系统的上下文切换，增加系统的性能开销。并且，悲观锁还可能会存在死锁问题，影响代码的正常运行。

#### 什么是乐观锁？

乐观锁总是假设最好的情况，认为共享资源每次被访问的时候不会出现问题，线程可以不停地执行，无需加锁也无需等待，只是在提交修改的时候去验证对应的资源（也就是数据）是否被其它线程修改了（具体方法可以使用版本号机制或 CAS 算法）。

在 Java 中 `java.util.concurrent.atomic` 包下面的原子变量类（比如 `AtomicInteger`、`LongAdder`）就是使用了乐观锁的一种实现方式 **CAS** 实现的。
![JUC原子类概览](images/JUC_E5_8E_9F_E5_AD_90_E7_B1_BB_E6_A6_82_E8_A7_88-20230814005-8956b754.png)

```java
// LongAdder 在高并发场景下会比 AtomicInteger 和 AtomicLong 的性能更好
// 代价就是会消耗更多的内存空间（空间换时间）
LongAdder sum = new LongAdder();
sum.increment();
```

高并发的场景下，乐观锁相比悲观锁来说，不存在锁竞争造成线程阻塞，也不会有死锁的问题，在性能上往往会更胜一筹。但是，如果冲突频繁发生（写占比非常多的情况），会频繁失败和重试，这样同样会非常影响性能，导致 CPU 飙升。

不过，大量失败重试的问题也是可以解决的，像我们前面提到的 `LongAdder` 以空间换时间的方式就解决了这个问题。

理论上来说：

- 悲观锁通常多用于写比较多的情况（多写场景，竞争激烈），这样可以避免频繁失败和重试影响性能，悲观锁的开销是固定的。不过，如果乐观锁解决了频繁失败和重试这个问题的话（比如 `LongAdder`），也是可以考虑使用乐观锁的，要视实际情况而定。
- 乐观锁通常多用于写比较少的情况（多读场景，竞争较少），这样可以避免频繁加锁影响性能。不过，乐观锁主要针对的对象是单个共享变量（参考 `java.util.concurrent.atomic` 包下面的原子变量类）。

#### 如何实现乐观锁？

乐观锁一般会使用版本号机制或 CAS 算法实现，CAS 算法相对来说更多一些，这里需要格外注意。

#### 版本号机制

一般是在数据表中加上一个数据版本号 `version` 字段，表示数据被修改的次数。当数据被修改时，`version` 值会加一。当线程 A 要更新数据值时，在读取数据的同时也会读取 `version` 值，在提交更新时，若刚才读取到的 version 值为当前数据库中的 `version` 值相等时才更新，否则重试更新操作，直到更新成功。

**举一个简单的例子**：假设数据库中帐户信息表中有一个 version 字段，当前值为 1；而当前帐户余额字段（`balance`）为 ＄100。

1. 操作员 A 此时将其读出（`version`=1），并从其帐户余额中扣除 $50（$100-＄50）。
2. 在操作员 A 操作的过程中，操作员 B 也读入此用户信息（`version`=1），并从其帐户余额中扣除 $20（$100-＄20）。
3. 操作员 A 完成了修改工作，将数据版本号（`version`=1），连同帐户扣除后余额（`balance`=＄50），提交至数据库更新，此时由于提交数据版本等于数据库记录当前版本，数据被更新，数据库记录 `version` 更新为 2。
4. 操作员 B 完成了操作，也将版本号（`version`=1）试图向数据库提交数据（`balance`=＄80），但此时比对数据库记录版本时发现，操作员 B 提交的数据版本号为 1，数据库记录当前版本也为 2，不满足 “ 提交版本必须等于当前版本才能执行更新 ” 的乐观锁策略，因此，操作员 B 的提交被驳回。

这样就避免了操作员 B 用基于 `version`=1 的旧数据修改的结果覆盖操作员 A 的操作结果的可能。

#### CAS 算法

CAS 的全称是 **Compare And Swap（比较与交换）**，用于实现乐观锁，被广泛应用于各大框架中。CAS 的思想很简单，就是用一个预期值和要更新的变量值进行比较，两值相等才会进行更新。

CAS 是一个原子操作，底层依赖于一条 CPU 的原子指令。

> **原子操作** 即最小不可拆分的操作，也就是说操作一旦开始，就不能被打断，直到操作完成。

CAS 涉及到三个操作数：

- **V**：要更新的变量值(Var)
- **E**：预期值(Expected)
- **N**：拟写入的新值(New)

当且仅当 V 的值等于 E 时，CAS 通过原子方式用新值 N 来更新 V 的值。如果不等，说明已经有其它线程更新了 V，则当前线程放弃更新。

**举一个简单的例子**：线程 A 要修改变量 i 的值为 6，i 原值为 1（V = 1，E=1，N=6，假设不存在 ABA 问题）。

1. i 与 1 进行比较，如果相等， 则说明没被其他线程修改，可以被设置为 6。
2. i 与 1 进行比较，如果不相等，则说明被其他线程修改，当前线程放弃更新，CAS 操作失败。

当多个线程同时使用 CAS 操作一个变量时，只有一个会胜出，并成功更新，其余均会失败，但失败的线程并不会被挂起，仅是被告知失败，并且允许再次尝试，当然也允许失败的线程放弃操作。

Java 代码可以通过原子类、`VarHandle` 等 API 表达 CAS 语义。HotSpot 通常会把相关调用识别为 JVM 内部函数，再映射为目标处理器支持的原子指令或等价实现；这并不是 Java 规范固定要求的“JNI 调用 C++ 内联汇编”。

`sun.misc` 包下的 `Unsafe` 类提供了 `compareAndSwapObject`、`compareAndSwapInt`、`compareAndSwapLong` 方法来实现的对 `Object`、`int`、`long` 类型的 CAS 操作

```java
/**
  *  CAS
  * @param o         包含要修改field的对象
  * @param offset    对象中某field的偏移量
  * @param expected  期望值
  * @param update    更新值
  * @return          true | false
  */
public final native boolean compareAndSwapObject(Object o, long offset,  Object expected, Object update);

public final native boolean compareAndSwapInt(Object o, long offset, int expected,int update);

public final native boolean compareAndSwapLong(Object o, long offset, long expected, long update);
```

关于 `Unsafe` 类的详细介绍可以看这篇文章：[Java 魔法类 Unsafe 详解 - JavaGuide - 2022](https://javaguide.cn/java/basis/unsafe.html)。

#### Java 中 CAS 是如何实现的？

在 Java 中，实现 CAS（Compare-And-Swap, 比较并交换）操作的一个关键类是 `Unsafe`。

`Unsafe` 类位于 `sun.misc` 包下，是一个提供低级别、不安全操作的类。由于其强大的功能和潜在的危险性，它通常用于 JVM 内部或一些需要极高性能和底层访问的库中，而不推荐普通开发者在应用程序中使用。关于 `Unsafe` 类的详细介绍，可以阅读这篇文章：📌[Java 魔法类 Unsafe 详解](https://javaguide.cn/java/basis/unsafe.html)。

`sun.misc` 包下的 `Unsafe` 类提供了 `compareAndSwapObject`、`compareAndSwapInt`、`compareAndSwapLong` 方法来实现的对 `Object`、`int`、`long` 类型的 CAS 操作：

```java
/**
 * 以原子方式更新对象字段的值。
 *
 * @param o        要操作的对象
 * @param offset   对象字段的内存偏移量
 * @param expected 期望的旧值
 * @param x        要设置的新值
 * @return 如果值被成功更新，则返回 true；否则返回 false
 */
boolean compareAndSwapObject(Object o, long offset, Object expected, Object x);

/**
 * 以原子方式更新 int 类型的对象字段的值。
 */
boolean compareAndSwapInt(Object o, long offset, int expected, int x);

/**
 * 以原子方式更新 long 类型的对象字段的值。
 */
boolean compareAndSwapLong(Object o, long offset, long expected, long x);
```

JDK 8 中 `Unsafe` 的这些 CAS 方法是 `native` 方法。Java 代码通过它们表达原子比较并交换语义，HotSpot 通常会将相关调用作为 JVM 内部函数处理，并映射为目标处理器支持的原子指令或等价实现。具体实现依赖 JVM 和 CPU 架构，但不能简单概括为“通过 JNI 调用 C++ 内联汇编”。

`java.util.concurrent.atomic` 包提供了一些用于原子操作的类。这些类利用底层的原子指令，确保在多线程环境下的操作是线程安全的。

![JUC原子类概览](images/JUC_E5_8E_9F_E5_AD_90_E7_B1_BB_E6_A6_82_E8_A7_88-064976d1.png)

关于这些 Atomic 原子类的介绍和使用，可以阅读这篇文章：[Atomic 原子类总结](https://javaguide.cn/java/concurrent/atomic-classes.html)。

`AtomicInteger` 是 Java 的原子类之一，主要用于对 `int` 类型的变量进行原子操作，它利用 `Unsafe` 类提供的低级别原子操作方法实现无锁的线程安全性。

下面，我们通过解读 `AtomicInteger` 的核心源码（JDK1.8），来说明 Java 如何使用 `Unsafe` 类的方法来实现原子操作。

`AtomicInteger` 核心源码如下：

```java
// 获取 Unsafe 实例
private static final Unsafe unsafe = Unsafe.getUnsafe();
private static final long valueOffset;

static {
    try {
        // 获取“value”字段在AtomicInteger类中的内存偏移量
        valueOffset = unsafe.objectFieldOffset
            (AtomicInteger.class.getDeclaredField("value"));
    } catch (Exception ex) { throw new Error(ex); }
}
// 确保“value”字段的可见性
private volatile int value;

// 如果当前值等于预期值，则原子地将值设置为newValue
// 使用 Unsafe#compareAndSwapInt 方法进行CAS操作
public final boolean compareAndSet(int expect, int update) {
    return unsafe.compareAndSwapInt(this, valueOffset, expect, update);
}

// 原子地将当前值加 delta 并返回旧值
public final int getAndAdd(int delta) {
    return unsafe.getAndAddInt(this, valueOffset, delta);
}

// 原子地将当前值加 1 并返回加之前的值（旧值）
// 使用 Unsafe#getAndAddInt 方法进行CAS操作。
public final int getAndIncrement() {
    return unsafe.getAndAddInt(this, valueOffset, 1);
}

// 原子地将当前值减 1 并返回减之前的值（旧值）
public final int getAndDecrement() {
    return unsafe.getAndAddInt(this, valueOffset, -1);
}
```

`Unsafe#getAndAddInt` 源码：

```java
// 原子地获取并增加整数值
public final int getAndAddInt(Object o, long offset, int delta) {
    int v;
    do {
        // 以 volatile 方式获取对象 o 在内存偏移量 offset 处的整数值
        v = getIntVolatile(o, offset);
    } while (!compareAndSwapInt(o, offset, v, v + delta));
    // 返回旧值
    return v;
}
```

可以看到，`getAndAddInt` 使用了 `do-while` 循环：在 `compareAndSwapInt` 操作失败时，会不断重试直到成功。也就是说，`getAndAddInt` 方法会通过 `compareAndSwapInt` 方法来尝试更新 `value` 的值，如果更新失败（当前值在此期间被其他线程修改），它会重新获取当前值并再次尝试更新，直到操作成功。

由于 CAS 操作可能会因为并发冲突而失败，因此通常会与 `while` 循环搭配使用，在失败后不断重试，直到操作成功。这就是 **自旋锁机制**。

#### CAS 算法存在哪些问题？

ABA 问题是 CAS 算法最常见的问题。

#### ABA 问题

如果一个变量 V 初次读取的时候是 A 值，并且在准备赋值的时候检查到它仍然是 A 值，那我们就能说明它的值没有被其他线程修改过了吗？很明显是不能的，因为在这段时间它的值可能被改为其他值，然后又改回 A，那 CAS 操作就会误认为它从来没有被修改过。这个问题被称为 CAS 操作的 **"ABA"问题。**

ABA 问题的解决思路是在变量前面追加上**版本号或者时间戳**。JDK 1.5 以后的 `AtomicStampedReference` 类就是用来解决 ABA 问题的，其中的 `compareAndSet()` 方法就是首先检查当前引用是否等于预期引用，并且当前标志是否等于预期标志，如果全部相等，则以原子方式将该引用和该标志的值设置为给定的更新值。

```java
public boolean compareAndSet(V   expectedReference,
                             V   newReference,
                             int expectedStamp,
                             int newStamp) {
    Pair current = pair;
    return
        expectedReference == current.reference &&
        expectedStamp == current.stamp &&
        ((newReference == current.reference &&
          newStamp == current.stamp) ||
         casPair(current, Pair.of(newReference, newStamp)));
}
```

#### 循环时间长开销大

CAS 经常会用到自旋操作来进行重试，也就是不成功就一直循环执行直到成功。如果长时间不成功，会给 CPU 带来非常大的执行开销。

如果 JVM 能够支持处理器提供的 `pause` 指令，那么自旋操作的效率将有所提升。`pause` 指令有两个重要作用：

1. **延迟流水线执行指令**：`pause` 指令可以延迟指令的执行，从而减少 CPU 的资源消耗。具体的延迟时间取决于处理器的实现版本，在某些处理器上，延迟时间可能为零。
2. **避免内存顺序冲突**：在退出循环时，`pause` 指令可以避免由于内存顺序冲突而导致的 CPU 流水线被清空，从而提高 CPU 的执行效率。

#### 只能保证一个共享变量的原子操作

CAS 操作仅能对单个共享变量有效。当需要操作多个共享变量时，CAS 就显得无能为力。不过，从 JDK 1.5 开始，Java 提供了 `AtomicReference` 类，这使得我们能够保证引用对象之间的原子性。通过将多个变量封装在一个对象中，我们可以使用 `AtomicReference` 来执行 CAS 操作。

除了 `AtomicReference` 这种方式之外，还可以利用加锁来保证。

#### 总结

| **对比维度**    | **乐观锁 (Optimistic Locking)**             | **悲观锁 (Pessimistic Locking)**                                     |
| --------------- | ------------------------------------------- | -------------------------------------------------------------------- |
| **核心假设**    | 假设冲突很少发生，提交时才验证。            | 假设冲突必然发生，读取时就加锁。                                     |
| **常见实现**    | **CAS (Compare And Swap)** 或版本号机制。   | Java 监视器、`Lock` 或数据库锁等；具体实现可能包含自旋、排队和挂起。 |
| **竞争时行为**  | 更新失败后由业务逻辑决定重试、放弃或回退。  | 获取失败的线程可能自旋、排队或被挂起，取决于具体锁实现。             |
| **并发开销**    | **CPU 消耗**（高并发写时频繁自旋重试）。    | **上下文切换开销**（线程挂起与唤醒）。                               |
| **死锁风险**    | **无死锁**（因为不涉及持有锁的等待）。      | **有死锁风险**（多个锁相互等待）。                                   |
| **数据库实现**  | `UPDATE ... SET version = version + 1`      | `SELECT ... FOR UPDATE`                                              |
| **Java 代表类** | `AtomicInteger`、`LongAdder`、`StampedLock` | `synchronized`、`ReentrantLock`                                      |
| **适用场景**    | **多读少写**、并发冲突概率低的业务。        | **多写少读**、数据一致性要求极高的核心业务。                         |

### 【synchronized 关键字】

#### synchronized 是什么？有什么用？

`synchronized` 是 Java 中的一个关键字，翻译成中文是同步的意思，主要解决的是多个线程之间访问资源的同步性，可以保证被它修饰的方法或者代码块在任意时刻只能有一个线程执行。

在 Java 早期版本中，`synchronized` 属于 **重量级锁**，效率低下。这是因为监视器锁（monitor）是依赖于底层的操作系统的 `Mutex Lock` 来实现的，Java 的线程是映射到操作系统的原生线程之上的。如果要挂起或者唤醒一个线程，都需要操作系统帮忙完成，而操作系统实现线程之间的切换时需要从用户态转换到内核态，这个状态之间的转换需要相对比较长的时间，时间成本相对较高。

不过，在 Java 6 之后， `synchronized` 引入了大量的优化如自旋锁、适应性自旋锁、锁消除、锁粗化、偏向锁、轻量级锁等技术来减少锁操作的开销，这些优化让 `synchronized` 锁的效率提升了很多。因此， `synchronized` 还是可以在实际项目中使用的，像 JDK 源码、很多开源框架都大量使用了 `synchronized`。

关于偏向锁多补充一点：由于偏向锁增加了 JVM 的复杂性，同时也并没有为所有应用都带来性能提升。因此，在 JDK15 中，偏向锁被默认关闭（仍然可以使用 `-XX:+UseBiasedLocking` 启用偏向锁），在 JDK18 中，偏向锁已经被彻底废弃（无法通过命令行打开）。

#### 如何使用 synchronized？

`synchronized` 关键字的使用方式主要有下面 3 种：

1. 修饰实例方法
2. 修饰静态方法
3. 修饰代码块

**1、修饰实例方法**（锁当前对象实例）

给当前对象实例加锁，进入同步代码前要获得 **当前对象实例的锁**。

```java
synchronized void method() {
    //业务代码
}
```

**2、修饰静态方法**（锁当前类）

给当前类加锁，会作用于类的所有对象实例，进入同步代码前要获得 **当前 class 的锁**。

这是因为静态成员不属于任何一个实例对象，归整个类所有，不依赖于类的特定实例，被类的所有实例共享。

```java
synchronized static void method() {
    //业务代码
}
```

静态 `synchronized` 方法和非静态 `synchronized` 方法之间的调用互斥么？不互斥！如果一个线程 A 调用一个实例对象的非静态 `synchronized` 方法，而线程 B 需要调用这个实例对象所属类的静态 `synchronized` 方法，是允许的，不会发生互斥现象，因为访问静态 `synchronized` 方法占用的锁是当前类的锁，而访问非静态 `synchronized` 方法占用的锁是当前实例对象锁。

**3、修饰代码块**（锁指定对象/类）

对括号里指定的对象/类加锁：

- `synchronized(object)` 表示进入同步代码块前要获得 **给定对象的锁**。
- `synchronized(类.class)` 表示进入同步代码块前要获得 **给定 Class 的锁**

```java
synchronized(this) {
    //业务代码
}
```

**总结：**

- `synchronized` 关键字加到 `static` 静态方法和 `synchronized(class)` 代码块上都是是给 Class 类上锁；
- `synchronized` 关键字加到实例方法上是给对象实例上锁；
- 尽量不要使用 `synchronized(String a)` 因为 JVM 中，字符串常量池具有缓存功能。

#### 构造方法可以用 synchronized 修饰么？

构造方法不能使用 synchronized 关键字修饰。不过，可以在构造方法内部使用 synchronized 代码块。

另外，构造方法本身是线程安全的，但如果在构造方法中涉及到共享资源的操作，就需要采取适当的同步措施来保证整个构造过程的线程安全。

#### ⭐️ synchronized 底层原理了解吗？

synchronized 关键字底层原理属于 JVM 层面的东西。

#### synchronized 同步语句块的情况

```java
public class SynchronizedDemo {
    public void method() {
        synchronized (this) {
            System.out.println("synchronized 代码块");
        }
    }
}
```

通过 JDK 自带的 `javap` 命令查看 `SynchronizedDemo` 类的相关字节码信息：首先切换到类的对应目录执行 `javac SynchronizedDemo.java` 命令生成编译后的 .class 文件，然后执行 `javap -c -s -v -l SynchronizedDemo.class`。

![synchronized关键字原理](images/synchronized-principle-21da6a40.png)

从上面我们可以看出：**`synchronized` 同步语句块的实现使用的是 `monitorenter` 和 `monitorexit` 指令，其中 `monitorenter` 指令指向同步代码块的开始位置，`monitorexit` 指令则指明同步代码块的结束位置。**

上面的字节码中包含一个 `monitorenter` 指令以及两个 `monitorexit` 指令，这是为了保证锁在同步代码块代码正常执行以及出现异常的这两种情况下都能被正确释放。

当执行 `monitorenter` 指令时，线程试图获取锁也就是获取 **对象监视器 `monitor`** 的持有权。

> 在 Java 虚拟机(HotSpot)中，Monitor 是基于 C++实现的，由[ObjectMonitor](https://github.com/openjdk-mirror/jdk7u-hotspot/blob/50bdefc3afe944ca74c3093e7448d6b889cd20d1/src/share/vm/runtime/objectMonitor.cpp)实现的。每个对象中都内置了一个 `ObjectMonitor` 对象。
>
> 另外，`wait/notify` 等方法也依赖于 `monitor` 对象，这就是为什么只有在同步的块或者方法中才能调用 `wait/notify` 等方法，否则会抛出 `java.lang.IllegalMonitorStateException` 的异常的原因。

在执行 `monitorenter` 时，会尝试获取对象的锁，如果锁的计数器为 0 则表示锁可以被获取，获取后将锁计数器设为 1 也就是加 1。

![执行 monitorenter 获取锁](images/synchronized-get-lock-code-block-34a3fbdb.png)

对象锁的拥有者线程才可以执行 `monitorexit` 指令来释放锁。在执行 `monitorexit` 指令后，将锁计数器设为 0，表明锁被释放，其他线程可以尝试获取锁。

![执行 monitorexit 释放锁](images/synchronized-release-lock-block-2fb4fd02.png)

如果获取对象锁失败，那当前线程就要阻塞等待，直到锁被另外一个线程释放为止。

#### synchronized 修饰方法的情况

```java
public class SynchronizedDemo2 {
    public synchronized void method() {
        System.out.println("synchronized 方法");
    }
}

```

![synchronized关键字原理](images/synchronized_E5_85_B3_E9_94_AE_E5_AD_97_E5_8E_9F_E7_90_862-870792d9.png)

`synchronized` 修饰的方法并没有 `monitorenter` 指令和 `monitorexit` 指令，取而代之的是 `ACC_SYNCHRONIZED` 标识，该标识指明了该方法是一个同步方法。JVM 通过该 `ACC_SYNCHRONIZED` 访问标志来辨别一个方法是否声明为同步方法，从而执行相应的同步调用。

如果是实例方法，JVM 会尝试获取实例对象的锁。如果是静态方法，JVM 会尝试获取当前 class 的锁。

#### 总结

`synchronized` 同步语句块的实现使用的是 `monitorenter` 和 `monitorexit` 指令，其中 `monitorenter` 指令指向同步代码块的开始位置，`monitorexit` 指令则指明同步代码块的结束位置。

`synchronized` 修饰的方法并没有 `monitorenter` 指令和 `monitorexit` 指令，取而代之的是 `ACC_SYNCHRONIZED` 标识，该标识指明了该方法是一个同步方法。

**不过，两者的本质都是对对象监视器 monitor 的获取。**

相关推荐：[Java 锁与线程的那些事 - 有赞技术团队](https://tech.youzan.com/javasuo-yu-xian-cheng-de-na-xie-shi/)。

🧗🏻 进阶一下：学有余力的小伙伴可以抽时间详细研究一下对象监视器 `monitor`。

#### JDK1.6 之后的 synchronized 底层做了哪些优化？锁升级原理了解吗？

在 Java 6 之后， `synchronized` 引入了大量的优化如自旋锁、适应性自旋锁、锁消除、锁粗化、偏向锁、轻量级锁等技术来减少锁操作的开销，这些优化让 `synchronized` 锁的效率提升了很多（JDK18 中，偏向锁已经被彻底废弃，前面已经提到过了）。

锁主要存在四种状态，依次是：无锁状态、偏向锁状态、轻量级锁状态、重量级锁状态，他们会随着竞争的激烈而逐渐升级。注意锁可以升级不可降级，这种策略是为了提高获得锁和释放锁的效率。

`synchronized` 锁升级是一个比较复杂的过程，面试也很少问到，如果你想要详细了解的话，可以看看这篇文章：[浅析 synchronized 锁升级的原理与实现](https://www.cnblogs.com/star95/p/17542850.html)。

#### synchronized 的偏向锁为什么被废弃了？

Open JDK 官方声明：[JEP 374: Deprecate and Disable Biased Locking](https://openjdk.org/jeps/374)

在 JDK15 中，偏向锁被默认关闭（仍然可以使用 `-XX:+UseBiasedLocking` 启用偏向锁），在 JDK18 中，偏向锁已经被彻底废弃（无法通过命令行打开）。

在官方声明中，主要原因有两个方面：

- **性能收益不明显：**

偏向锁是 HotSpot 虚拟机的一项优化技术，可以提升单线程对同步代码块的访问性能。

受益于偏向锁的应用程序通常使用了早期的 Java 集合 API，例如 HashTable、Vector，在这些集合类中通过 synchronized 来控制同步，这样在单线程频繁访问时，通过偏向锁会减少同步开销。

随着 JDK 的发展，出现了 ConcurrentHashMap 高性能的集合类，在集合类内部进行了许多性能优化，此时偏向锁带来的性能收益就不明显了。

偏向锁仅仅在单线程访问同步代码块的场景中可以获得性能收益。

如果存在多线程竞争，就需要 **撤销偏向锁**，这个操作的性能开销是比较昂贵的。偏向锁的撤销需要等待进入到全局安全点（safe point），该状态下所有线程都是暂停的，此时去检查线程状态并进行偏向锁的撤销。

- **JVM 内部代码维护成本太高：**

偏向锁将许多复杂代码引入到同步子系统，并且对其他的 HotSpot 组件也具有侵入性。这种复杂性为理解代码、系统重构带来了困难，因此， OpenJDK 官方希望禁用、废弃并删除偏向锁。

#### ⭐️ synchronized 和 volatile 有什么区别？

`synchronized` 关键字和 `volatile` 关键字是两个互补的存在，而不是对立的存在！

- `volatile` 关键字是线程同步的轻量级实现，所以 `volatile` 性能肯定比 `synchronized` 关键字要好。但是 `volatile` 关键字只能用于变量而 `synchronized` 关键字可以修饰方法以及代码块。
- `volatile` 关键字能保证数据的可见性，但不能保证数据的原子性。`synchronized` 关键字两者都能保证。
- `volatile` 关键字主要用于解决变量在多个线程之间的可见性，而 `synchronized` 关键字解决的是多个线程之间访问资源的同步性。

#### volatile 与 synchronized 的性能对比

上面提到 `volatile` 是线程同步的轻量级实现，性能比 `synchronized` 要好。下面从底层原理的角度分析为什么 `volatile` 性能更好，以及在什么情况下应该选择哪个。

周志明在《深入理解 Java 虚拟机》中指出：

> volatile 变量的读操作的性能消耗与普通变量几乎没有什么差别，但是写操作则可能会慢上一些，因为它需要在本地代码中插入许多内存屏障指令来保证处理器不发生乱序执行。不过即便如此，大多数场景下 volatile 的总开销仍然要比锁来得更低。

二者性能差异的根本原因在于底层实现机制不同：

| 对比维度         | `volatile`                                                                 | `synchronized`                                                     |
| ---------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **实现层面**     | 通过插入内存屏障指令实现，不涉及线程阻塞和上下文切换                       | 依赖操作系统的互斥锁（Mutex Lock），涉及用户态与内核态的切换       |
| **读操作开销**   | 与普通变量几乎相同                                                         | 需要获取 monitor 锁，即使无竞争也有一定开销（偏向锁/轻量级锁 CAS） |
| **写操作开销**   | 需要插入 `StoreStore` + `StoreLoad` 内存屏障，有一定开销但不会导致线程阻塞 | 需要获取和释放 monitor 锁，有竞争时会导致线程阻塞和上下文切换      |
| **竞争时的表现** | 不会导致线程阻塞，始终是非阻塞的                                           | 线程竞争激烈时，会频繁发生阻塞和唤醒，上下文切换开销大             |
| **功能范围**     | 只能修饰变量，只保证可见性和有序性                                         | 可以修饰方法和代码块，同时保证可见性、有序性和原子性               |

**选择建议：**

- 如果只需要保证变量的可见性（如状态标志位、DCL 单例中的实例引用），优先使用 `volatile`，因为它的开销更小。
- 如果需要保证复合操作的原子性（如 `i++`、先检查后执行等），则必须使用 `synchronized`、`Lock` 或原子类，`volatile` 无法胜任。

### 【ReentrantLock】

#### ReentrantLock 是什么？

`ReentrantLock` 实现了 `Lock` 接口，是一个可重入且独占式的锁，和 `synchronized` 关键字类似。不过，`ReentrantLock` 更灵活、更强大，增加了轮询、超时、中断、公平锁和非公平锁等高级功能。

```java
public class ReentrantLock implements Lock, java.io.Serializable {}
```

`ReentrantLock` 里面有一个内部类 `Sync`，`Sync` 继承 AQS（`AbstractQueuedSynchronizer`），添加锁和释放锁的大部分操作实际上都是在 `Sync` 中实现的。`Sync` 有公平锁 `FairSync` 和非公平锁 `NonfairSync` 两个子类。

`ReentrantLock` 默认使用非公平锁，也可以通过构造器来显式的指定使用公平锁。

```java
// 传入一个 boolean 值，true 时为公平锁，false 时为非公平锁
public ReentrantLock(boolean fair) {
    sync = fair ? new FairSync() : new NonfairSync();
}
```

从上面的内容可以看出， `ReentrantLock` 的底层就是由 AQS 来实现的。关于 AQS 的相关内容推荐阅读 [AQS 详解](https://javaguide.cn/java/concurrent/aqs.html) 这篇文章。

#### 公平锁和非公平锁有什么区别？

- **公平锁** : 在存在竞争时，通常优先让等待时间最长的线程获得锁，但不保证操作系统的线程调度严格按时间顺序进行；`ReentrantLock` 的无参 `tryLock()` 也不会遵守公平设置。
- **非公平锁**：锁被释放之后，后申请的线程可能会先获取到锁，是随机或者按照其他优先级排序的。性能更好，但可能会导致某些线程永远无法获取到锁。

#### ⭐️ synchronized 和 ReentrantLock 有什么区别？

#### 两者都是可重入锁

**可重入锁** 也叫递归锁，指的是线程可以再次获取自己的内部锁。比如一个线程获得了某个对象的锁，此时这个对象锁还没有释放，当其再次想要获取这个对象的锁的时候还是可以获取的，如果是不可重入锁的话，就会造成死锁。

JDK 中常用的锁（如 synchronized、ReentrantLock、ReentrantReadWriteLock）是可重入的，但并不是所有 Lock 实现都支持可重入，例如 StampedLock 就是不可重入的。

在下面的代码中，`method1()` 和 `method2()` 都被 `synchronized` 关键字修饰，`method1()` 调用了 `method2()`。

```java
public class SynchronizedDemo {
    public synchronized void method1() {
        System.out.println("方法1");
        method2();
    }

    public synchronized void method2() {
        System.out.println("方法2");
    }
}
```

由于 `synchronized` 锁是可重入的，同一个线程在调用 `method1()` 时可以直接获得当前对象的锁，执行 `method2()` 的时候可以再次获取这个对象的锁，不会产生死锁问题。假如 `synchronized` 是不可重入锁的话，由于该对象的锁已被当前线程所持有且无法释放，这就导致线程在执行 `method2()` 时获取锁失败，会出现死锁问题。

#### synchronized 依赖于 JVM 而 ReentrantLock 依赖于 API

`synchronized` 是依赖于 JVM 实现的，前面我们也讲到了 虚拟机团队在 JDK1.6 为 `synchronized` 关键字进行了很多优化，但是这些优化都是在虚拟机层面实现的，并没有直接暴露给我们。

`ReentrantLock` 是 JDK 层面实现的（也就是 API 层面，需要 `lock()` 和 `unlock()` 方法配合 `try/finally` 语句块来完成），所以我们可以通过查看它的源代码，来看它是如何实现的。

#### ReentrantLock 比 synchronized 增加了一些高级功能

相比 `synchronized`，`ReentrantLock` 增加了一些高级功能。主要来说主要有三点：

- **等待可中断** : `ReentrantLock` 提供了一种能够中断等待锁的线程的机制，通过 `lock.lockInterruptibly()` 来实现这个机制。也就是说当前线程在等待获取锁的过程中，如果其他线程中断当前线程「 `interrupt()` 」，当前线程就会抛出 `InterruptedException` 异常，可以捕捉该异常进行相应处理。
- **可配置公平策略** : `ReentrantLock` 可以指定公平或非公平策略，默认是非公平的，可通过 `ReentrantLock(boolean fair)` 构造方法配置。`synchronized` 不提供公平性配置，也不承诺等待线程按先后顺序获得监视器。
- **通知机制更强大**：`ReentrantLock` 通过绑定多个 `Condition` 对象，可以实现分组唤醒和选择性通知。这解决了 `synchronized` 只能随机唤醒或全部唤醒的效率问题，为复杂的线程协作场景提供了强大的支持。
- **支持超时**：`ReentrantLock` 提供了 `tryLock(timeout)` 的方法，可以指定等待获取锁的最长等待时间，如果超过了等待时间，就会获取锁失败，不会一直等待。

如果你想使用上述功能，那么选择 `ReentrantLock` 是一个不错的选择。

关于 `Condition` 接口的补充：

> `Condition` 是 JDK1.5 之后才有的，它具有很好的灵活性，比如可以实现多路通知功能也就是在一个 `Lock` 对象中可以创建多个 `Condition` 实例（即对象监视器），**线程对象可以注册在指定的 `Condition` 中，从而可以有选择性的进行线程通知，在调度线程上更加灵活。 在使用 `notify()/notifyAll()` 方法进行通知时，被通知的线程是由 JVM 选择的，用 `ReentrantLock` 类结合 `Condition` 实例可以实现“选择性通知”**，这个功能非常重要，而且是 `Condition` 接口默认提供的。而 `synchronized` 关键字就相当于整个 `Lock` 对象中只有一个 `Condition` 实例，所有的线程都注册在它一个身上。如果执行 `notifyAll()` 方法的话就会通知所有处于等待状态的线程，这样会造成很大的效率问题。而 `Condition` 实例的 `signalAll()` 方法，只会唤醒注册在该 `Condition` 实例中的所有等待线程。

关于 **等待可中断** 的补充：

> `lockInterruptibly()` 会让获取锁的线程在阻塞等待的过程中可以响应中断，即当前线程在获取锁的时候，发现锁被其他线程持有，就会阻塞等待。
>
> 在阻塞等待的过程中，如果其他线程中断当前线程 `interrupt()`，就会抛出 `InterruptedException` 异常，可以捕获该异常，做一些处理操作。
>
> 为了更好理解这个方法，借用 Stack Overflow 上的一个案例，可以更好地理解 `lockInterruptibly()` 可以响应中断：
>

```JAVA
public class MyReentrantLock {
    Thread t = new Thread() {
        @Override
        public void run() {
            ReentrantLock r = new ReentrantLock();
            // 1.1、第一次尝试获取锁，可以获取成功
            r.lock();

            // 1.2、此时锁的重入次数为 1
            System.out.println("lock() : lock count :" + r.getHoldCount());

            // 2、中断当前线程，通过 Thread.currentThread().isInterrupted() 可以看到当前线程的中断状态为 true
            interrupt();
            System.out.println("Current thread is interrupted");

            // 3.1、尝试获取锁，可以成功获取
            r.tryLock();
            // 3.2、此时锁的重入次数为 2
            System.out.println("tryLock() on interrupted thread lock count :" + r.getHoldCount());
            try {
                // 4、打印线程的中断状态为 true，那么调用 lockInterruptibly() 方法就会抛出 InterruptedException 异常
                System.out.println("Current Thread isInterrupted:" + Thread.currentThread().isInterrupted());
                r.lockInterruptibly();
                System.out.println("lockInterruptibly() --NOt executable statement" + r.getHoldCount());
            } catch (InterruptedException e) {
                r.lock();
                System.out.println("Error");
            } finally {
                r.unlock();
            }

            // 5、打印锁的重入次数，可以发现 lockInterruptibly() 方法并没有成功获取到锁
            System.out.println("lockInterruptibly() not able to Acqurie lock: lock count :" + r.getHoldCount());

            r.unlock();
            System.out.println("lock count :" + r.getHoldCount());
            r.unlock();
            System.out.println("lock count :" + r.getHoldCount());
        }
    };
    public static void main(String str[]) {
        MyReentrantLock m = new MyReentrantLock();
        m.t.start();
    }
}
```

>
> 输出：
>

```BASH
lock() : lock count :1
Current thread is interrupted
tryLock() on interrupted thread lock count :2
Current Thread isInterrupted:true
Error
lockInterruptibly() not able to Acqurie lock: lock count :2
lock count :1
lock count :0
```

关于 **支持超时** 的补充：

> **为什么需要 `tryLock(timeout)` 这个功能呢？**
>
> `tryLock(timeout)` 方法尝试在指定的超时时间内获取锁。如果成功获取锁，则返回 `true`；如果在锁可用之前超时，则返回 `false`。此功能在以下几种场景中非常有用：
>
> - **防止死锁：** 在复杂的锁场景中，`tryLock(timeout)` 可以通过允许线程在合理的时间内放弃并重试来帮助防止死锁。
> - **提高响应速度：** 防止线程无限期阻塞。
> - **处理时间敏感的操作：** 对于具有严格时间限制的操作，`tryLock(timeout)` 允许线程在无法及时获取锁时继续执行替代操作。

#### 可中断锁和不可中断锁有什么区别？

它们的区别在于：**线程在获取锁的过程中被阻塞时，是否能够因为中断而提前放弃等待。**

- **不可中断锁**：线程在等待锁期间即使收到中断信号，也不会退出阻塞状态，而是一直等待直到获得锁。中断状态会被保留，但不会影响锁的获取过程。
  - `synchronized` 属于典型的不可中断锁。
  - `ReentrantLock#lock()` 也是不可中断的。
- **可中断锁**：线程在等待锁的过程中如果收到中断信号，会立即停止等待并抛出 `InterruptedException`，从而有机会进行取消或错误处理。
  - `ReentrantLock#lockInterruptibly()` 实现了可中断锁。
  - `ReentrantLock#tryLock(long time, TimeUnit unit)`（带超时的尝试获取）也是可中断的。

### 【ReentrantReadWriteLock】

#### ReentrantReadWriteLock 是什么？

`ReentrantReadWriteLock` 实现了 `ReadWriteLock`，是一个可重入的读写锁，既可以保证多个线程同时读的效率，同时又可以保证有写入操作时的线程安全。

```java
public class ReentrantReadWriteLock
        implements ReadWriteLock, java.io.Serializable{
}
public interface ReadWriteLock {
    Lock readLock();
    Lock writeLock();
}
```

- 一般锁进行并发控制的规则：读读互斥、读写互斥、写写互斥。
- 读写锁进行并发控制的规则：读读不互斥、读写互斥、写写互斥（只有读读不互斥）。

`ReentrantReadWriteLock` 其实是两把锁，一把是 `WriteLock`（写锁），一把是 `ReadLock`（读锁）。读锁是共享锁，写锁是独占锁。读锁可以被同时读，可以同时被多个线程持有，而写锁最多只能同时被一个线程持有。

和 `ReentrantLock` 一样，`ReentrantReadWriteLock` 底层也是基于 AQS 实现的。

`ReentrantReadWriteLock` 也支持公平锁和非公平锁，默认使用非公平锁，可以通过构造器来显式地指定。

```java
// 传入一个 boolean 值，true 时为公平锁，false 时为非公平锁
public ReentrantReadWriteLock(boolean fair) {
    sync = fair ? new FairSync() : new NonfairSync();
    readerLock = new ReadLock(this);
    writerLock = new WriteLock(this);
}
```

#### ReentrantReadWriteLock 适合什么场景？

由于 `ReentrantReadWriteLock` 既可以保证多个线程同时读的效率，同时又可以保证有写入操作时的线程安全。因此，在读多写少的情况下，使用 `ReentrantReadWriteLock` 能够明显提升系统性能。

#### 共享锁和独占锁有什么区别？

- **共享锁**：一把锁可以被多个线程同时获得。
- **独占锁**：一把锁只能被一个线程获得。

#### 线程持有读锁还能获取写锁吗？

- 在线程持有读锁的情况下，该线程不能取得写锁（因为获取写锁的时候，如果发现当前的读锁被占用，就马上获取失败，不管读锁是不是被当前线程持有）。
- 在线程持有写锁的情况下，该线程可以继续获取读锁（获取读锁时如果发现写锁被占用，只有写锁没有被当前线程占用的情况才会获取失败）。

读写锁的源码分析，推荐阅读 [聊聊 Java 的几把 JVM 级锁 - 阿里巴巴中间件](https://mp.weixin.qq.com/s/h3VIUyH9L0v14MrQJiiDbw) 这篇文章，写的很不错。

#### 读锁为什么不能升级为写锁？

写锁可以降级为读锁，但是 `ReentrantReadWriteLock` 不支持直接把读锁升级为写锁。关键原因是多个线程可能同时持有读锁：如果它们都在不释放读锁的情况下等待写锁，就会彼此等待而无法满足写锁的独占条件。需要升级时，应先释放读锁，再获取写锁，并在获得写锁后重新检查共享状态。

### 【StampedLock】

#### StampedLock 是什么？

`StampedLock` 是 JDK 1.8 引入的性能更好的读写锁，不可重入且不支持条件变量 `Condition`。

不同于一般的 `Lock` 类，`StampedLock` 并不是直接实现 `Lock` 或 `ReadWriteLock` 接口，而是基于 **CLH 锁** 独立实现的（AQS 也是基于这玩意）。

```java
public class StampedLock implements java.io.Serializable {
}
```

`StampedLock` 提供了三种模式的读写控制模式：读锁、写锁和乐观读。

- **写锁**：独占锁，一把锁只能被一个线程获得。当一个线程获取写锁后，其他请求读锁和写锁的线程必须等待。类似于 `ReentrantReadWriteLock` 的写锁，不过这里的写锁是不可重入的。
- **读锁**（悲观读）：共享锁，没有线程获取写锁的情况下，多个线程可以同时持有读锁。如果己经有线程持有写锁，则其他线程请求获取该读锁会被阻塞。类似于 `ReentrantReadWriteLock` 的读锁，不过这里的读锁是不可重入的。
- **乐观读**：允许多个线程获取乐观读以及读锁。同时允许一个写线程获取写锁。

另外，`StampedLock` 还支持这三种锁在一定条件下进行相互转换。

```java
long tryConvertToWriteLock(long stamp){}
long tryConvertToReadLock(long stamp){}
long tryConvertToOptimisticRead(long stamp){}
```

`StampedLock` 在获取锁的时候会返回一个 long 型的数据戳，该数据戳用于稍后的锁释放参数，如果返回的数据戳为 0 则表示锁获取失败。当前线程持有了锁再次获取锁时返回情况要看当前持有什么锁、再次申请什么锁，以及使用的是阻塞方法还是 `try` 方法：

- **当前线程持有写锁，再次获取写锁**：由于写锁是独占锁，第二次获取必须等待，但第一个写锁又要等待第二次调用返回后才能释放，于是当前线程把自己锁住了。结果就是一直阻塞，无法返回。
- **使用 `tryWriteLock()` 时，会返回 0**：`tryWriteLock()` 不会一直等待，它会立即尝试。当获取成功，则返回非 0 的数据戳；获取失败，则返回 0。
- **同一线程再次获取悲观读锁，会返回新的数据戳**：读锁是共享锁，读锁与读锁之间不冲突，所以正常返回数据戳。

真正的“可重入锁”会识别线程身份，虽然 `StampedLock` 这里同一个线程可以获取 2 次读锁，返回 2 个数据戳，但 `StampedLock` 不记录锁的线程所有权。判断是否可重入，重点看独占写锁。`StampedLock` 的写锁无法由同一个线程再次获取，所以它是不可重入的。

```java
// 写锁
public long writeLock() {
    long s, next;  // bypass acquireWrite in fully unlocked case only
    return ((((s = state) & ABITS) == 0L &&
             U.compareAndSwapLong(this, STATE, s, next = s + WBIT)) ?
            next : acquireWrite(false, 0L));
}
// 读锁
public long readLock() {
    long s = state, next;  // bypass acquireRead on common uncontended case
    return ((whead == wtail && (s & ABITS) < RFULL &&
             U.compareAndSwapLong(this, STATE, s, next = s + RUNIT)) ?
            next : acquireRead(false, 0L));
}
// 乐观读
public long tryOptimisticRead() {
    long s;
    return (((s = state) & WBIT) == 0L) ? (s & SBITS) : 0L;
}
```

#### StampedLock 的性能为什么更好？

相比于传统读写锁多出来的乐观读是 `StampedLock` 比 `ReadWriteLock` 性能更好的关键原因。`StampedLock` 的乐观读允许一个写线程获取写锁，所以不会导致所有写线程阻塞，也就是当读多写少的时候，写线程有机会获取写锁，减少了线程饥饿的问题，吞吐量大大提高。

#### StampedLock 适合什么场景？

和 `ReentrantReadWriteLock` 一样，`StampedLock` 同样适合读多写少的业务场景，可以作为 `ReentrantReadWriteLock` 的替代品，性能更好。

不过，需要注意的是 `StampedLock` 不可重入，不支持条件变量 `Condition`，对中断操作支持也不友好（使用不当容易导致 CPU 飙升）。如果你需要用到 `ReentrantLock` 的一些高级性能，就不太建议使用 `StampedLock` 了。

另外，`StampedLock` 性能虽好，但使用起来相对比较麻烦，一旦使用不当，就会出现生产问题。强烈建议你在使用 `StampedLock` 之前，看看 [StampedLock 官方文档中的案例](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/StampedLock.html)。

#### StampedLock 的底层原理了解吗？

`StampedLock` 不是直接实现 `Lock` 或 `ReadWriteLock` 接口，而是基于 **CLH 锁** 实现的（AQS 也是基于这玩意），CLH 锁是对自旋锁的一种改良，是一种隐式的链表队列。`StampedLock` 通过 CLH 队列进行线程的管理，通过同步状态值 `state` 来表示锁的状态和类型。

`StampedLock` 的原理和 AQS 原理比较类似，这里就不详细介绍了，感兴趣的可以看看下面这两篇文章：

- [AQS 详解](https://javaguide.cn/java/concurrent/aqs.html)
- [StampedLock 底层原理分析](https://segmentfault.com/a/1190000015808032)

如果你只是准备面试的话，建议多花点精力搞懂 AQS 原理即可，`StampedLock` 底层原理在面试中遇到的概率非常小。

#### 参考

- 《深入理解 Java 虚拟机》
- 《实战 Java 高并发程序设计》
- Guide to the Volatile Keyword in Java - Baeldung：
- 不可不说的 Java“锁”事 - 美团技术团队：
- 在 ReadWriteLock 类中读锁为什么不能升级为写锁？：
- 高性能解决线程饥饿的利器 StampedLock：
- 理解 Java 中的 ThreadLocal - 技术小黑屋：
- ThreadLocal (Java Platform SE 8 ) - Oracle Help Center：

<!-- @include: @article-footer.snippet.md -->

### 【ThreadLocal】

#### ThreadLocal 有什么用？

通常情况下，我们创建的变量可以被任何一个线程访问和修改。这在多线程环境中可能导致数据竞争和线程安全问题。那么，**如果想让每个线程都有自己的专属本地变量，该如何实现呢？**

JDK 中提供的 `ThreadLocal` 类正是为了解决这个问题。**`ThreadLocal` 类允许每个线程绑定自己的值**，可以将其形象地比喻为一个“存放数据的盒子”。每个线程都有自己独立的盒子，用于存储私有数据，确保不同线程之间的数据互不干扰。

当你创建一个 `ThreadLocal` 变量时，每个访问该变量的线程都会拥有一个独立的副本。这也是 `ThreadLocal` 名称的由来。线程可以通过 `get()` 方法获取自己线程的本地副本，或通过 `set()` 方法修改该副本的值，从而避免了线程安全问题。

举个简单的例子：假设有两个人去宝屋收集宝物。如果他们共用一个袋子，必然会产生争执；但如果每个人都有一个独立的袋子，就不会有这个问题。如果将这两个人比作线程，那么 `ThreadLocal` 就是用来避免这两个线程竞争同一个资源的方法。

```java
public class ThreadLocalExample {
    private static ThreadLocal threadLocal = ThreadLocal.withInitial(() -> 0);

    public static void main(String[] args) {
        Runnable task = () -> {
            int value = threadLocal.get();
            value += 1;
            threadLocal.set(value);
            System.out.println(Thread.currentThread().getName() + " Value: " + threadLocal.get());
        };

        Thread thread1 = new Thread(task, "Thread-1");
        Thread thread2 = new Thread(task, "Thread-2");

        thread1.start(); // 输出: Thread-1 Value: 1
        thread2.start(); // 输出: Thread-2 Value: 1
    }
}
```

#### ⭐️ ThreadLocal 原理了解吗？

从 `Thread` 类源代码入手。

```java
public class Thread implements Runnable {
    //......
    //与此线程有关的ThreadLocal值。由ThreadLocal类维护
    ThreadLocal.ThreadLocalMap threadLocals = null;

    //与此线程有关的InheritableThreadLocal值。由InheritableThreadLocal类维护
    ThreadLocal.ThreadLocalMap inheritableThreadLocals = null;
    //......
}
```

从上面 `Thread` 类 源代码可以看出 `Thread` 类中有一个 `threadLocals` 和 一个 `inheritableThreadLocals` 变量，它们都是 `ThreadLocalMap` 类型的变量，我们可以把 `ThreadLocalMap` 理解为 `ThreadLocal` 类实现的定制化的 `HashMap`。默认情况下这两个变量都是 null，只有当前线程调用 `ThreadLocal` 类的 `set` 或 `get` 方法时才创建它们，实际上调用这两个方法的时候，我们调用的是 `ThreadLocalMap` 类对应的 `get()`、`set()` 方法。

`ThreadLocal` 类的 `set()` 方法

```java
public void set(T value) {
    //获取当前请求的线程
    Thread t = Thread.currentThread();
    //取出 Thread 类内部的 threadLocals 变量(哈希表结构)
    ThreadLocalMap map = getMap(t);
    if (map != null)
        // 将需要存储的值放入到这个哈希表中
        map.set(this, value);
    else
        createMap(t, value);
}
ThreadLocalMap getMap(Thread t) {
    return t.threadLocals;
}
```

通过上面这些内容，我们足以通过猜测得出结论：**最终的变量是放在了当前线程的 `ThreadLocalMap` 中，并不是存在 `ThreadLocal` 上，`ThreadLocal` 可以理解为只是 `ThreadLocalMap` 的封装，传递了变量值。** `ThrealLocal` 类中可以通过 `Thread.currentThread()` 获取到当前线程对象后，直接通过 `getMap(Thread t)` 可以访问到该线程的 `ThreadLocalMap` 对象。

**每个 `Thread` 中都具备一个 `ThreadLocalMap`，而 `ThreadLocalMap` 可以存储以 `ThreadLocal` 为 key，Object 对象为 value 的键值对。**

```java
ThreadLocalMap(ThreadLocal<?> firstKey, Object firstValue) {
    //......
}
```

比如我们在同一个线程中声明了两个 `ThreadLocal` 对象的话， `Thread` 内部都是使用仅有的那个 `ThreadLocalMap` 存放数据的，`ThreadLocalMap` 的 key 就是 `ThreadLocal` 对象，value 就是 `ThreadLocal` 对象调用 `set` 方法设置的值。

`ThreadLocal` 数据结构如下图所示：

![ThreadLocal 数据结构](images/threadlocal-data-structure-8af53b95.png)

`ThreadLocalMap` 是 `ThreadLocal` 的静态内部类。

![ThreadLocal内部类](images/thread-local-inner-class-7a342442.png)

#### ⭐️ ThreadLocal 内存泄露问题是怎么导致的？

`ThreadLocal` 内存泄漏的根本原因在于其内部实现机制。

通过上面的内容我们已经知道：每个线程维护一个名为 `ThreadLocalMap` 的 map。 当你使用 `ThreadLocal` 存储值时，实际上是将值存储在当前线程的 `ThreadLocalMap` 中，其中 `ThreadLocal` 实例本身作为 key，而你要存储的值作为 value。

`ThreadLocal` 的 `set()` 方法源码如下：

```java
public void set(T value) {
    Thread t = Thread.currentThread(); // 获取当前线程
    ThreadLocalMap map = getMap(t);   // 获取当前线程的 ThreadLocalMap
    if (map != null) {
        map.set(this, value);         // 设置值
    } else {
        createMap(t, value);          // 创建新的 ThreadLocalMap
    }
}
```

`ThreadLocalMap` 的 `set()` 和 `createMap()` 方法中，并没有直接存储 `ThreadLocal` 对象本身，而是使用 `ThreadLocal` 的哈希值计算数组索引，最终存储于类型为 `static class Entry extends WeakReference>` 的数组中。

```java
int i = key.threadLocalHashCode & (len-1);
```

`ThreadLocalMap` 的 `Entry` 定义如下：

```java
static class Entry extends WeakReference> {
    Object value;

    Entry(ThreadLocal<?> k, Object v) {
        super(k);
        value = v;
    }
}
```

`ThreadLocalMap` 的 `key` 和 `value` 引用机制：

- **key 是弱引用**：`ThreadLocalMap` 中的 key 是 `ThreadLocal` 的弱引用 (`WeakReference>`)。 这意味着，如果 `ThreadLocal` 实例不再被任何强引用指向，垃圾回收器会在下次 GC 时回收该实例，导致 `ThreadLocalMap` 中对应的 key 变为 `null`。
- **value 是强引用**：即使 `key` 被 GC 回收，`value` 仍然被 `ThreadLocalMap.Entry` 强引用存在，无法被 GC 回收。

当 `ThreadLocal` 实例失去强引用后，其对应的 value 仍然存在于 `ThreadLocalMap` 中，因为 `Entry` 对象强引用了它。如果线程持续存活（例如线程池中的线程），`ThreadLocalMap` 也会一直存在，导致 key 为 `null` 的 entry 无法被垃圾回收，即会造成内存泄漏。

也就是说，内存泄漏的发生需要同时满足两个条件：

1. `ThreadLocal` 实例不再被强引用；
2. 线程持续存活，导致 `ThreadLocalMap` 长期存在。

虽然 `ThreadLocalMap` 在 `get()`, `set()` 和 `remove()` 操作时会尝试清理 key 为 null 的 entry，但这种清理机制是被动的，并不完全可靠。

**如何避免内存泄漏的发生？**

1. 在使用完 `ThreadLocal` 后，务必调用 `remove()` 方法。 这是最安全和最推荐的做法。 `remove()` 方法会从 `ThreadLocalMap` 中显式地移除对应的 entry，彻底解决内存泄漏的风险。 即使将 `ThreadLocal` 定义为 `static final`，也强烈建议在每次使用后调用 `remove()`。
2. 在线程池等线程复用的场景下，使用 `try-finally` 块可以确保即使发生异常，`remove()` 方法也一定会被执行。

#### 为什么 Entry 的 key 要设计为弱引用？

这是一个经典的面试追问。很多同学知道 `ThreadLocalMap` 的 key 是弱引用，但不清楚**为什么要这样设计**，以及如果换成强引用会怎样。

我们先来看完整的引用链路。当一个线程使用 `ThreadLocal` 时，涉及以下引用关系：

```
强引用（栈/静态变量）──→ ThreadLocal 实例
                              ↑
Thread ──→ ThreadLocalMap ──→ Entry ─── key（WeakReference）──┘
                              │
                              └─── value（强引用）──→ 实际存储的对象
```

理解了这条引用链路，我们来对比两种设计方案：

**假设 key 使用强引用（实际没有采用）：**

当业务代码中的 `ThreadLocal` 引用被置为 `null`（例如方法执行结束、对象被回收），此时虽然业务代码已经不再需要这个 `ThreadLocal`，但由于 `ThreadLocalMap` 的 Entry 对 key 持有**强引用**，`ThreadLocal` 实例仍然无法被 GC 回收。只要线程不终止，这个 `ThreadLocal` 和它对应的 value 都会一直存在于内存中，造成 key 和 value **都无法回收**的内存泄漏。

**key 使用弱引用（实际采用的方案）：**

当业务代码中的 `ThreadLocal` 引用被置为 `null` 后，由于 Entry 的 key 是弱引用，`ThreadLocal` 实例在下次 GC 时会被回收，key 变为 `null`。此时虽然 value 仍然存在（强引用），但 `ThreadLocalMap` 在执行 `get()`、`set()`、`remove()` 等操作时，会主动探测并清理这些 key 为 `null` 的 "stale entry"（过期条目），从而释放 value 对象。

也就是说，**弱引用的设计是一种“兜底”防御机制**——即便开发者忘记调用 `remove()`，JVM 的 GC 配合 `ThreadLocalMap` 的自清理逻辑，仍然有机会回收泄漏的数据。而如果使用强引用，一旦忘记 `remove()`，就完全没有任何补救机会了。

> 需要注意的是，这种自清理机制是**被动触发**的（只在 `get`/`set`/`remove` 操作时顺便清理），并不能保证所有过期条目都被及时清理。因此，**弱引用只是降低了内存泄漏的风险，并没有彻底消除它**，手动调用 `remove()` 仍然是必须的。

#### 线程池场景下的特殊风险

上面提到内存泄漏的条件之一是“线程持续存活”。在使用 `new Thread()` 创建线程的场景下，线程执行完毕后会被销毁，其持有的 `ThreadLocalMap` 也会随之被 GC 回收，泄漏的影响相对有限。

但在**线程池**场景下，问题会被严重放大。线程池中的核心线程默认不会被销毁，它们会被反复复用来执行不同的任务。这意味着：

1. **内存泄漏可能累积**：如果任务不断创建新的临时 `ThreadLocal`，或使用多个 `ThreadLocal` 却没有清理，失去强引用的 key 被回收后，对应 value 仍可能残留在复用线程的 `ThreadLocalMap` 中。对同一个仍可达的 `ThreadLocal` 反复调用 `set()` 通常会替换旧 value，但最新 value 仍会一直保留到被覆盖、移除、清理或线程终止。
2. **数据污染（脏数据）**：上一个任务设置的 `ThreadLocal` 值，如果没有被清理，下一个被分配到同一线程的任务就能读取到这个残留值。这可能导致严重的业务逻辑错误，比如用户 A 的请求读取到了用户 B 的身份信息。

**美团技术团队的真实事故案例：**

美团技术团队在[《Java 线程池实现原理及其在美团业务中的实践》](https://tech.meituan.com/2020/04/02/java-pooling-pratice-in-meituan.html)一文中就记录了一次因 `ThreadLocal` 使用不当引发的线上事故：在一个依赖 `ThreadLocal` 传递用户上下文的 Web 应用中，由于使用了线程池处理请求，且没有在请求结束后清理 `ThreadLocal`，导致**后续请求复用了同一线程时，读取到了前一个请求遗留的用户信息**，造成了用户数据串号的严重问题。

#### 阿里巴巴 Java 开发手册的强制规约

正因为线程池 + `ThreadLocal` 的组合如此容易踩坑，《阿里巴巴 Java 开发手册》在“并发处理”章节中对此做出了**强制**级别的要求：

> **【强制】** 必须回收自定义的 `ThreadLocal` 变量记录的当前线程的值，尤其在线程池场景下，线程经常会被复用，如果不清理自定义的 `ThreadLocal` 变量，可能会影响后续业务逻辑和造成内存泄露等问题。尽量在代理中使用 `try-finally` 块进行回收。

正确的使用模式如下：

```java
// 定义为 static final，避免重复创建 ThreadLocal 实例
private static final ThreadLocal userContextHolder = new ThreadLocal<>();

public void processRequest(HttpServletRequest request) {
    try {
        // 在 try 块中设置值
        UserContext context = buildUserContext(request);
        userContextHolder.set(context);

        // 执行业务逻辑
        doBusinessLogic();
    } finally {
        // 在 finally 块中必须清理，确保无论是否发生异常都会执行
        userContextHolder.remove();
    }
}
```

这里有三个关键要点：

1. **`ThreadLocal` 声明为 `static final`**：确保该字段对应的 `ThreadLocal` 实例不会在每次调用时重复创建，避免旧实例失去强引用后留下过期条目；这并不意味着整个应用只能有一个 `ThreadLocal` 实例。
2. **`try-finally` 保证 `remove()` 一定被执行**：即使业务逻辑抛出异常，`finally` 块也能确保 `ThreadLocal` 被清理。
3. **在使用完毕后立即清理，而不是依赖下次使用前覆盖**：对同一个 `ThreadLocal` 调用 `set()` 会替换旧 value，但在下一次任务到来前，旧值仍会被线程持有；如果代码改为使用其他 `ThreadLocal`，过期条目还可能长期残留。用完后在 `finally` 中调用 `remove()`，可以及时避免内存占用和数据污染。

#### ⭐️ 如何跨线程传递 ThreadLocal 的值？

**为什么 ThreadLocal 在异步场景下会失效？**

`ThreadLocal` 的值不在 `ThreadLocal` 对象中，而是存储在 `Thread` 里：

```java
Thread → ThreadLocalMap → Entry(ThreadLocal, value)
```

`ThreadLocal` 数据结构如下图所示：

![ThreadLocal 数据结构](images/threadlocal-data-structure-8af53b95.png)

异步执行往往意味着任务会从当前线程切换到另一个线程（例如线程池中的工作线程）执行。由于不同线程各自维护独立的 `ThreadLocalMap`，默认情况下 `ThreadLocal` 的上下文无法在异步执行中自动传递。

**如何跨线程传递 ThreadLocal 的值？**

为了解决这个问题，业界有两套主流的解决方案，一套是 JDK 原生的，另一套是阿里巴巴开源的。

1. `InheritableThreadLocal`：JDK1.2 提供的一个类，继承自 `ThreadLocal`。使用 `InheritableThreadLocal` 时，会在创建子线程时，令子线程继承父线程中的 `ThreadLocal` 值，但是无法支持线程池场景下的 `ThreadLocal` 值传递。
2. `TransmittableThreadLocal`： `TransmittableThreadLocal`（简称 TTL） 是阿里巴巴开源的工具类，继承并加强了 `InheritableThreadLocal` 类，可以在线程池的场景下支持 `ThreadLocal` 值传递。项目地址：。

#### InheritableThreadLocal 原理

`InheritableThreadLocal` 实现了创建异步线程时，继承父线程 `ThreadLocal` 值的功能。该类是 JDK 团队提供的，通过改造 JDK 源码包中的 `Thread` 类来实现创建线程时，`ThreadLocal` 值的传递。

**`InheritableThreadLocal` 的值存储在哪里？**

在 `Thread` 类中添加了一个新的 `ThreadLocalMap`，命名为 `inheritableThreadLocals`，该变量用于存储需要跨线程传递的 `ThreadLocal` 值。如下：

```JAVA
class Thread implements Runnable {
    ThreadLocal.ThreadLocalMap threadLocals = null;
    ThreadLocal.ThreadLocalMap inheritableThreadLocals = null;
}
```

**如何完成 `ThreadLocal` 值的传递？**

通过改造 `Thread` 类的构造方法来实现，在创建 `Thread` 线程时，拿到父线程的 `inheritableThreadLocals` 变量赋值给子线程即可。相关代码如下：

```JAVA
// Thread 的构造方法会调用 init() 方法
private void init(/* ... */) {
	// 1、获取父线程
    Thread parent = currentThread();
    // 2、将父线程的 inheritableThreadLocals 赋值给子线程
    if (inheritThreadLocals && parent.inheritableThreadLocals != null)
        this.inheritableThreadLocals =
        	ThreadLocal.createInheritedMap(parent.inheritableThreadLocals);
}
```

**`InheritableThreadLocal` 的方案有什么问题？**

这个方案的缺陷在于它的**一次性**，也就是它只在线程创建时发生一次复制。然而，现在的开发中，我们会大量使用线程池，但线程池里的线程是被复用的。

想象一下，任务 A 在线程 1 中执行，把它的 `ThreadLocal` 值传给了线程池里的子线程 2。任务 A 结束后，线程 1 去休息了。接着，任务 B 来了，它在线程 3 中执行，线程池又复用了刚才那个子线程 2 来执行任务 B 的一部分。此时，子线程 2 的 `ThreadLocal` 里还残留着任务 A 传给它的脏数据，而任务 B（在线程 3 里）的上下文却完全没有传递过来。这就导致了数据污染和上下文丢失。

#### TransmittableThreadLocal 原理

JDK 默认没有支持线程池场景下 `ThreadLocal` 值传递的功能，因此阿里巴巴开源了一套工具 `TransmittableThreadLocal` 来实现该功能。

由于阿里巴巴无法改动 JDK 源码，TTL 巧妙地利用了**装饰器模式**对任务（`Runnable`/`Callable`）或线程池（`Executor`）进行增强，将上下文的传递时机从“线程创建时”延迟到了“任务提交与执行时”。

TTL 的核心逻辑可以概括为三个阶段（CRR）：

- **Capture（捕获）**：在提交任务（如调用 `execute`）的一瞬间，`TtlRunnable` 会调用 `TransmittableThreadLocal.Transmitter.capture()`。它通过内部维护的 `holder` 集合，抓取当前父线程中所有活跃的 TTL 变量并存入快照。
- **Replay（回放）**：在线程池的工作线程执行 `run()` 方法前，调用 `replay()`。它将快照中的值 `set` 到当前工作线程中，并备份该线程原有的旧值。
- **Restore（恢复）**：任务执行结束后，调用 `restore()`。它根据备份将工作线程恢复到执行前的状态，防止上下文污染或内存泄漏。

这张图是 TTL 官方提供的 CRR 整个过程的时序图：

![TTL 官方提供的 CRR 整个过程的时序图](images/ttl-crr-timing-diagram-622e8efd.png)

不太好理解吧？可以看下我绘制的这张 CRR 时序图，更清晰直观一些：

```mermaid
sequenceDiagram
    participant P as 父线程（Submitter）
    participant W as TTL 包装器（TtlRunnable / Agent）
    participant C as 线程池工作线程（Worker）

    Note over P: 1. set context = "A"
    P->>W: 2. 提交任务（Capture）
    Note right of W: 捕获父线程中所有活跃的 TTL 变量快照

    W->>C: 3. 执行任务 run()
    Note over C: 4. Replay
    Note right of C: 备份工作线程原有 TTL 值并设置 Capture 得到的值

    Note over C: 5. 业务逻辑执行get context = "A"

    Note over C: 6. Restore
    Note right of C: 恢复工作线程原有 TTL 值防止上下文污染

    C-->>P: 7. 任务执行结束

```

也就是说，TTL 的本质是在任务提交时 Capture 上下文，在任务执行前 Replay 上下文，在任务结束后 Restore 线程状态，从而安全地支持线程池中的 `ThreadLocal` 传递。

TTL 提供了两种主要的接入方式，可根据侵入性要求和改造成本进行选择。

**1. 显式包装（手动接入）**

使用 `TtlRunnable.get(Runnable)` 或 `TtlCallable.get(Callable)` 对任务进行包装，使用 `TtlExecutors.getTtlExecutor(Executor)`、`getTtlExecutorService(...)` 对线程池进行包装。这种接入方式清晰可控，但需要业务代码配合，存在一定侵入性。

下面这段代码展示了 TTL 通过 CRR，在支持线程池复用和拒绝策略的前提下，安全地传递并隔离 `ThreadLocal` 上下文。

```java
public class TtlContextHolder {
    private static final Logger log = LoggerFactory.getLogger(TtlContextHolder.class);

    // 1. 使用 static final 确保 TTL 实例不被重复创建，防止内存泄漏
    // 重写 copy 方法（可选）：如果是引用类型，建议实现深拷贝
    private static final TransmittableThreadLocal CONTEXT = new TransmittableThreadLocal() {
        @Override
        public String copy(String parentValue) {
            // 默认是直接返回引用，如果是可变对象（如 Map），请在这里 new 新对象
            return parentValue;
        }
    };

    // 2. 线程池初始化：确保只被 TtlExecutors 包装一次
    private static final ExecutorService TTL_EXECUTOR_SERVICE;

    static {
        ExecutorService rawExecutor = new ThreadPoolExecutor(
                2, 4, 60L, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>(1000), (Runnable r) -> new Thread(r, "ttl-worker-" + r.hashCode()),
                new ThreadPoolExecutor.CallerRunsPolicy() // 关键：TTL 完美支持此拒绝策略
        );
        // 包装原始线程池
        TTL_EXECUTOR_SERVICE = TtlExecutors.getTtlExecutorService(rawExecutor);
    }

    public static void main(String[] args) throws Exception {
        try {
            // 3. 在父线程中设置上下文
            CONTEXT.set("value-set-in-parent");
            log.info("父线程上下文: {}", CONTEXT.get());

            // 4. 使用 Lambda 简化任务提交
            TTL_EXECUTOR_SERVICE.execute(() -> {
                log.info("异步任务(Runnable)读取上下文: {}", CONTEXT.get());
                // 模拟业务逻辑
                // 注意：子线程修改是否影响父线程，取决于 copy() 是否做了深拷贝
                CONTEXT.set("value-modified-in-child");
            });

            Future future = TTL_EXECUTOR_SERVICE.submit(() -> {
                log.info("异步任务(Callable)读取上下文: {}", CONTEXT.get());
                return "Success";
            });

            future.get();

            // 5. 验证父线程上下文是否被污染
            log.info("父线程最终上下文: {}", CONTEXT.get());

        } finally {
            // 6. 清理当前线程（父线程）的上下文，子线程的上下文由 TTL 的 Restore 机制自动恢复
            CONTEXT.remove();
        }
    }
}
```

输出：

```ba
09:06:31.438 INFO  [main] TtlContextHolder - 父线程上下文: value-set-in-parent
09:06:31.452 INFO  [ttl-worker-1663166483] TtlContextHolder - 异步任务(Runnable)读取上下文: value-set-in-parent
09:06:31.453 INFO  [ttl-worker-841283083] TtlContextHolder - 异步任务(Callable)读取上下文: value-set-in-parent
09:06:31.453 INFO  [main] TtlContextHolder - 父线程最终上下文: value-set-in-parent
```

如果你想要测试这段代码，记得引入 TTL 的 Maven 依赖；

```XML

    com.alibaba
    transmittable-thread-local
    2.14.4

```

**2. 无侵入接入（Java Agent）**

通过 Java Agent 在类加载阶段对线程池相关类进行 字节码增强，自动织入 TTL 的上下文传递逻辑，实现业务代码零改造的上下文透传。这种方式业务代码无需感知 TTL 的存在，但实现复杂度相对较高。

TTL Agent 默认修饰了以下 JDK 执行器组件：

1. **标准线程池**：`java.util.concurrent.ThreadPoolExecutor` 和 `java.util.concurrent.ScheduledThreadPoolExecutor`。
2. **ForkJoin 体系**：`java.util.concurrent.ForkJoinTask`（从而透明支持了 `CompletableFuture` 和 Java 8 并行流 `Stream`）。
3. **遗留组件**：`java.util.TimerTask`（自 v2.7.0 起支持，v2.11.2 起默认开启）。

在 Java 启动参数中加入 `-javaagent` 配置：

```bash
# 基础配置
java -javaagent:path/to/transmittable-thread-local-2.x.y.jar \
     -cp classes \
     com.your.app.Main
```

#### 应用场景

1. **压测流量标记**： 在压测场景中，使用 `ThreadLocal` 存储压测标记，用于区分压测流量和真实流量。如果标记丢失，可能导致压测流量被错误地当成线上流量处理。
2. **上下文传递**：在分布式系统中，传递链路追踪信息（如 Trace ID）或用户上下文信息。

#### 总结

`ThreadLocal` 的值默认是无法跨线程传递的，因为它的值是存在**每个 `Thread` 对象自己**的 `ThreadLocalMap` 里的，父子线程是两个不同的对象。

为了解决这个问题，主要有两种方案：

1. **JDK 的 InheritableThreadLocal**：它会在**创建子线程**的时候，把父线程的值**复制**一份给子线程。但它的问题是，在**线程池**场景下会失效。因为线程池会**复用**线程，这会导致线程拿到的可能是上一个任务传下来的**脏数据**。
2. **阿里的 TransmittableThreadLocal (TTL)**：这是我们项目里用的方案，它专门解决线程池的问题。它的原理是，在**提交任务**到线程池时，它会把父线程的 `ThreadLocal` 值**捕获**下来，和任务**绑定**在一起。等线程池里的某个线程要执行这个任务时，它再把捕获的值**设置**到这个线程上，任务执行完再**清理**掉。

简单说，**InheritableThreadLocal 是跟线程绑定的，只在创建时有效；而 TTL 是跟任务绑定的，完美支持线程池。**

### 【线程池】

#### 什么是线程池？

顾名思义，线程池就是管理一系列线程的资源池。当有任务要处理时，直接从线程池中获取线程来处理，处理完之后线程并不会立即被销毁，而是等待下一个任务。

#### ⭐️ 为什么要用线程池？

池化技术想必大家已经屡见不鲜了，线程池、数据库连接池、HTTP 连接池等等都是对这个思想的应用。池化技术的思想主要是为了减少每次获取资源的消耗，提高对资源的利用率。

线程池提供了一种限制和管理资源（包括执行一个任务）的方式。 每个线程池还维护一些基本统计信息，例如已完成任务的数量。使用线程池主要带来以下几个好处：

1. **降低资源消耗**：线程池里的线程是可以重复利用的。一旦线程完成了某个任务，它不会立即销毁，而是回到池子里等待下一个任务。这就避免了频繁创建和销毁线程带来的开销。
2. **提高响应速度**：因为线程池里通常会维护一定数量的核心线程（或者说“常驻工人”），任务来了之后，可以直接交给这些已经存在的、空闲的线程去执行，省去了创建线程的时间，任务能够更快地得到处理。
3. **提高线程的可管理性**：线程池允许我们统一管理池中的线程。我们可以配置线程池的大小（核心线程数、最大线程数）、任务队列的类型和大小、拒绝策略等。这样就能控制并发线程的总量，防止资源耗尽，保证系统的稳定性。同时，线程池通常也提供了监控接口，方便我们了解线程池的运行状态（比如有多少活跃线程、多少任务在排队等），便于调优。

#### 如何创建线程池？

在 Java 中，创建线程池主要有两种方式：

**方式一：通过 `ThreadPoolExecutor` 构造函数直接创建（推荐）**

图中的“默认线程工厂”和“默认拒绝策略”，指的是当前构造函数没有显式传入对应参数时，`ThreadPoolExecutor` 会使用默认实现，并不是方法和说明错位。

这是最推荐的方式，因为它允许开发者明确指定线程池的核心参数，对线程池的运行行为有更精细的控制，从而避免资源耗尽的风险。

**方式二：通过 `Executors` 工具类创建（不推荐用于生产环境）**

`Executors` 工具类提供的创建线程池的方法如下图所示：

可以看出，通过 `Executors` 工具类可以创建多种类型的线程池，包括：

- `FixedThreadPool`：正常运行时最多使用固定数量的工作线程。线程可以因异常终止后被替换，线程池关闭时也会退出，因此并非在整个生命周期中数量始终不变。当有一个新的任务提交时，线程池中若有空闲线程，则立即执行。若没有，则新的任务会被暂存在一个任务队列中，待有线程空闲时，便处理在任务队列中的任务。
- `SingleThreadExecutor`： 只有一个线程的线程池。若多余一个任务被提交到该线程池，任务会被保存在一个任务队列中，待线程空闲，按先入先出的顺序执行队列中的任务。
- `CachedThreadPool`： 可根据实际情况调整线程数量的线程池。线程池的线程数量不确定，但若有空闲线程可以复用，则会优先使用可复用的线程。若所有线程均在工作，又有新的任务提交，则会创建新的线程处理任务。所有线程在当前任务执行完毕后，将返回线程池进行复用。
- `ScheduledThreadPool`：给定的延迟后运行任务或者定期执行任务的线程池。

#### ⭐️ 为什么不推荐使用内置线程池？

在《阿里巴巴 Java 开发手册》“并发处理”这一章节，明确指出线程资源必须通过线程池提供，不允许在应用中自行显式创建线程。

**为什么呢？**

> 使用线程池的好处是减少在创建和销毁线程上所消耗的时间以及系统资源开销，解决资源不足的问题。如果不使用线程池，有可能会造成系统创建大量同类线程而导致消耗完内存或者“过度切换”的问题。

另外，《阿里巴巴 Java 开发手册》中强制线程池不允许使用 `Executors` 去创建，而是通过 `ThreadPoolExecutor` 构造函数的方式，这样的处理方式让写的同学更加明确线程池的运行规则，规避资源耗尽的风险

`Executors` 返回线程池对象的弊端如下（后文会详细介绍到）：

- `FixedThreadPool` 和 `SingleThreadExecutor`:使用的是阻塞队列 `LinkedBlockingQueue`，任务队列最大长度为 `Integer.MAX_VALUE`，可以看作是无界的，可能堆积大量的请求，从而导致 OOM。
- `CachedThreadPool`:使用的是同步队列 `SynchronousQueue`, 允许创建的线程数量为 `Integer.MAX_VALUE`，如果任务数量过多且执行速度较慢，可能会创建大量的线程，从而导致 OOM。
- `ScheduledThreadPool` 和 `SingleThreadScheduledExecutor`:使用的无界的延迟阻塞队列 `DelayedWorkQueue`，任务队列最大长度为 `Integer.MAX_VALUE`,可能堆积大量的请求，从而导致 OOM。

```java
public static ExecutorService newFixedThreadPool(int nThreads) {
    // LinkedBlockingQueue 的默认长度为 Integer.MAX_VALUE，可以看作是无界的
    return new ThreadPoolExecutor(nThreads, nThreads,0L, TimeUnit.MILLISECONDS,new LinkedBlockingQueue());

}

public static ExecutorService newSingleThreadExecutor() {
    // LinkedBlockingQueue 的默认长度为 Integer.MAX_VALUE，可以看作是无界的
    return new FinalizableDelegatedExecutorService (new ThreadPoolExecutor(1, 1,0L, TimeUnit.MILLISECONDS,new LinkedBlockingQueue()));

}

// 同步队列 SynchronousQueue，没有容量，最大线程数是 Integer.MAX_VALUE`
public static ExecutorService newCachedThreadPool() {

    return new ThreadPoolExecutor(0, Integer.MAX_VALUE,60L, TimeUnit.SECONDS,new SynchronousQueue());

}

// DelayedWorkQueue（延迟阻塞队列）
public static ScheduledExecutorService newScheduledThreadPool(int corePoolSize) {
    return new ScheduledThreadPoolExecutor(corePoolSize);
}
public ScheduledThreadPoolExecutor(int corePoolSize) {
    super(corePoolSize, Integer.MAX_VALUE, 0, NANOSECONDS,
          new DelayedWorkQueue());
}
```

#### ⭐️ 线程池常见参数有哪些？如何解释？

```java
    /**
     * 用给定的初始参数创建一个新的ThreadPoolExecutor。
     */
    public ThreadPoolExecutor(int corePoolSize,//线程池的核心线程数量
                              int maximumPoolSize,//线程池的最大线程数
                              long keepAliveTime,//当线程数大于核心线程数时，多余的空闲线程存活的最长时间
                              TimeUnit unit,//时间单位
                              BlockingQueue workQueue,//任务队列，用来储存等待执行任务的队列
                              ThreadFactory threadFactory,//线程工厂，用来创建线程，一般默认即可
                              RejectedExecutionHandler handler//拒绝策略，当提交的任务过多而不能及时处理时，我们可以定制策略来处理任务
                               ) {
        if (corePoolSize < 0 ||
            maximumPoolSize <= 0 ||
            maximumPoolSize < corePoolSize ||
            keepAliveTime < 0)
            throw new IllegalArgumentException();
        if (workQueue == null || threadFactory == null || handler == null)
            throw new NullPointerException();
        this.corePoolSize = corePoolSize;
        this.maximumPoolSize = maximumPoolSize;
        this.workQueue = workQueue;
        this.keepAliveTime = unit.toNanos(keepAliveTime);
        this.threadFactory = threadFactory;
        this.handler = handler;
    }
```

`ThreadPoolExecutor` 3 个最重要的参数：

- `corePoolSize`：默认情况下，即使空闲也会保留在线程池中的线程数量；未启用核心线程超时且工作线程少于该值时，新任务会优先触发创建线程。
- `maximumPoolSize`：线程池允许存在的最大工作线程数。
- `workQueue`：当工作线程数达到 `corePoolSize` 后，新任务会先尝试进入队列；只有入队失败且工作线程数小于 `maximumPoolSize` 时，线程池才会继续创建线程。

`ThreadPoolExecutor` 其他常见参数 :

- `keepAliveTime`:当线程池中的线程数量大于 `corePoolSize`，即有非核心线程（线程池中核心线程以外的线程）时，这些非核心线程空闲后不会立即销毁，而是会等待，直到等待的时间超过了 `keepAliveTime` 才会被回收销毁。
- `unit` : `keepAliveTime` 参数的时间单位。
- `threadFactory` :executor 创建新线程的时候会用到。
- `handler` :拒绝策略（后面会单独详细介绍一下）。

下面这张图可以加深你对线程池中各个参数的相互关系的理解（图片来源：《Java 性能调优实战》）：

![线程池各个参数的关系](images/relationship-between-thread-pool-parameters-8e02c62d.png)

#### 线程池的核心线程会被回收吗？

`ThreadPoolExecutor` 默认不会回收核心线程，即使它们已经空闲了。这是为了减少创建线程的开销，因为核心线程通常是要长期保持活跃的。但是，如果线程池是被用于周期性使用的场景，且频率不高（周期之间有明显的空闲时间），可以考虑将 `allowCoreThreadTimeOut(boolean value)` 方法的参数设置为 `true`，这样就会回收空闲（时间间隔由 `keepAliveTime` 指定）的核心线程了。

```java
public void allowCoreThreadTimeOut(boolean value) {
    // 核心线程的 keepAliveTime 必须大于 0 才能启用超时机制
    if (value && keepAliveTime <= 0) {
        throw new IllegalArgumentException("Core threads must have nonzero keep alive times");
    }
    // 设置 allowCoreThreadTimeOut 的值
    if (value != allowCoreThreadTimeOut) {
        allowCoreThreadTimeOut = value;
        // 如果启用了超时机制，清理所有空闲的线程，包括核心线程
        if (value) {
            interruptIdleWorkers();
        }
    }
}
```

#### 核心线程空闲时处于什么状态？

核心线程空闲时，其状态分为以下两种情况：

- **设置了核心线程的存活时间**：核心线程在空闲时，会处于 `WAITING` 状态，等待获取任务。如果阻塞等待的时间超过了核心线程存活时间，则该线程会退出工作，将该线程从线程池的工作线程集合中移除，线程状态变为 `TERMINATED` 状态。
- **没有设置核心线程的存活时间**：核心线程在空闲时，会一直处于 `WAITING` 状态，等待获取任务，核心线程会一直存活在线程池中。

当队列中有可用任务时，会唤醒被阻塞的线程，线程的状态会由 `WAITING` 状态变为 `RUNNABLE` 状态，之后去执行对应任务。

接下来通过相关源码，了解一下线程池内部是如何做的。

线程在线程池内部被抽象为了 `Worker`，当 `Worker` 被启动之后，会不断去任务队列中获取任务。

在获取任务的时候，会根据 `timed` 值来决定从任务队列（`BlockingQueue`）获取任务的行为。

如果「设置了核心线程的存活时间」或者「线程数量超过了核心线程数量」，则将 `timed` 标记为 `true`，表明获取任务时需要使用 `poll()` 指定超时时间。

- `timed == true`：使用 `poll(timeout, unit)` 来获取任务。使用 `poll(timeout, unit)` 方法获取任务超时的话，则当前线程会退出执行（`TERMINATED`），该线程从线程池中被移除。
- `timed == false`：使用 `take()` 来获取任务。使用 `take()` 方法获取任务会让当前线程一直阻塞等待（`WAITING`）。

源码如下：

```JAVA
// ThreadPoolExecutor
private Runnable getTask() {
    boolean timedOut = false;
    for (;;) {
        // ...

        // 1、如果「设置了核心线程的存活时间」或者是「线程数量超过了核心线程数量」，则 timed 为 true。
        boolean timed = allowCoreThreadTimeOut || wc > corePoolSize;
        // 2、扣减线程数量。
        // wc > maximuimPoolSize：线程池中的线程数量超过最大线程数量。其中 wc 为线程池中的线程数量。
        // timed && timeOut：timeOut 表示获取任务超时。
        // 分为两种情况：核心线程设置了存活时间 && 获取任务超时，则扣减线程数量；线程数量超过了核心线程数量 && 获取任务超时，则扣减线程数量。
        if ((wc > maximumPoolSize || (timed && timedOut))
            && (wc > 1 || workQueue.isEmpty())) {
            if (compareAndDecrementWorkerCount(c))
                return null;
            continue;
        }
        try {
            // 3、如果 timed 为 true，则使用 poll() 获取任务；否则，使用 take() 获取任务。
            Runnable r = timed ?
                workQueue.poll(keepAliveTime, TimeUnit.NANOSECONDS) :
                workQueue.take();
            // 4、获取任务之后返回。
            if (r != null)
                return r;
            timedOut = true;
        } catch (InterruptedException retry) {
            timedOut = false;
        }
    }
}
```

#### ⭐️ 线程池的拒绝策略有哪些？

如果当前同时运行的线程数量达到最大线程数量并且队列也已经被放满了任务时，`ThreadPoolExecutor` 定义一些策略:

- `ThreadPoolExecutor.AbortPolicy`：抛出 `RejectedExecutionException` 来拒绝新任务的处理。
- `ThreadPoolExecutor.CallerRunsPolicy`：调用执行者自己的线程运行任务，也就是直接在调用 `execute` 方法的线程中运行(`run`)被拒绝的任务，如果执行程序已关闭，则会丢弃该任务。因此这种策略会降低对于新任务提交速度，影响程序的整体性能。如果你的应用程序可以承受此延迟并且你要求任何一个任务请求都要被执行的话，你可以选择这个策略。
- `ThreadPoolExecutor.DiscardPolicy`：不处理新任务，直接丢弃掉。
- `ThreadPoolExecutor.DiscardOldestPolicy`：此策略将丢弃最早的未处理的任务请求。

举个例子：Spring 通过 `ThreadPoolTaskExecutor` 或者我们直接通过 `ThreadPoolExecutor` 的构造函数创建线程池的时候，当我们不指定 `RejectedExecutionHandler` 拒绝策略来配置线程池的时候，默认使用的是 `AbortPolicy`。在这种拒绝策略下，如果队列满了，`ThreadPoolExecutor` 将抛出 `RejectedExecutionException` 异常来拒绝新来的任务，这代表你将丢失对这个任务的处理。如果希望在线程池仍处于运行状态时避免直接丢弃任务，可以使用 `CallerRunsPolicy`，把任务回退给调用 `execute()` 的线程执行；如果线程池已经关闭，该策略仍会丢弃任务。

```java
public static class CallerRunsPolicy implements RejectedExecutionHandler {

        public CallerRunsPolicy() { }

        public void rejectedExecution(Runnable r, ThreadPoolExecutor e) {
            if (!e.isShutdown()) {
                // 直接主线程执行，而不是线程池中的线程执行
                r.run();
            }
        }
    }
```

#### 如果希望饱和时尽量不丢弃任务，应该选择哪个拒绝策略？

对于线程池仍在运行、并且调用线程可以接受同步执行任务的场景，可以考虑 `CallerRunsPolicy`。它不能提供“任何情况下都不丢任务”的保证：线程池关闭后任务会被丢弃，进程崩溃也无法靠内存中的拒绝策略恢复任务；需要强保证时应配合持久化或消息队列。

这里我们再来结合 `CallerRunsPolicy` 的源码来看看：

```java
public static class CallerRunsPolicy implements RejectedExecutionHandler {

        public CallerRunsPolicy() { }

        public void rejectedExecution(Runnable r, ThreadPoolExecutor e) {
            //只要当前程序没有关闭，就用执行execute方法的线程执行该任务
            if (!e.isShutdown()) {

                r.run();
            }
        }
    }
```

从源码可以看出，只要当前程序不关闭就会使用执行 `execute` 方法的线程执行该任务。

#### CallerRunsPolicy 拒绝策略有什么风险？如何解决？

我们上面也提到了：如果希望在线程池饱和时通过调用线程施加反压、尽量避免直接丢弃任务，`CallerRunsPolicy` 是一种可选方案。

不过，如果走到 `CallerRunsPolicy` 的任务是个非常耗时的任务，且处理提交任务的线程是主线程，可能会导致主线程阻塞，影响程序的正常运行。

这里简单举一个例子，该线程池限定了最大线程数为 2，阻塞队列大小为 1（这意味着第 4 个任务就会走到拒绝策略），`ThreadUtil` 为 Hutool 提供的工具类：

```java
public class ThreadPoolTest {

    private static final Logger log = LoggerFactory.getLogger(ThreadPoolTest.class);

    public static void main(String[] args) {
        // 创建一个线程池，核心线程数为1，最大线程数为2
        // 当线程数大于核心线程数时，多余的空闲线程存活的最长时间为60秒，
        // 任务队列为容量为1的ArrayBlockingQueue，饱和策略为CallerRunsPolicy。
        ThreadPoolExecutor threadPoolExecutor = new ThreadPoolExecutor(1,
                2,
                60,
                TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        // 提交第一个任务，由核心线程执行
        threadPoolExecutor.execute(() -> {
            log.info("核心线程执行第一个任务");
            ThreadUtil.sleep(1, TimeUnit.MINUTES);
        });

        // 提交第二个任务，由于核心线程被占用，任务将进入队列等待
        threadPoolExecutor.execute(() -> {
            log.info("非核心线程处理入队的第二个任务");
            ThreadUtil.sleep(1, TimeUnit.MINUTES);
        });

        // 提交第三个任务，由于核心线程被占用且队列已满，创建非核心线程处理
        threadPoolExecutor.execute(() -> {
            log.info("非核心线程处理第三个任务");
            ThreadUtil.sleep(1, TimeUnit.MINUTES);
        });

        // 提交第四个任务，由于核心线程和非核心线程都被占用，队列也满了，根据CallerRunsPolicy策略，任务将由提交任务的线程（即主线程）来执行
        threadPoolExecutor.execute(() -> {
            log.info("主线程处理第四个任务");
            ThreadUtil.sleep(2, TimeUnit.MINUTES);
        });

        // 提交第五个任务，主线程被第四个任务卡住，该任务必须等到主线程执行完才能提交
        threadPoolExecutor.execute(() -> {
            log.info("核心线程执行第五个任务");
        });

        // 关闭线程池
        threadPoolExecutor.shutdown();
    }
}

```

输出：

```bash
18:19:48.203 INFO  [pool-1-thread-1] c.j.concurrent.ThreadPoolTest - 核心线程执行第一个任务
18:19:48.203 INFO  [pool-1-thread-2] c.j.concurrent.ThreadPoolTest - 非核心线程处理第三个任务
18:19:48.203 INFO  [main] c.j.concurrent.ThreadPoolTest - 主线程处理第四个任务
18:20:48.212 INFO  [pool-1-thread-2] c.j.concurrent.ThreadPoolTest - 非核心线程处理入队的第二个任务
18:21:48.219 INFO  [pool-1-thread-2] c.j.concurrent.ThreadPoolTest - 核心线程执行第五个任务
```

从输出结果可以看出，因为 `CallerRunsPolicy` 这个拒绝策略，导致耗时的任务用了主线程执行，导致线程池阻塞，进而导致后续任务无法及时执行，严重的情况下很可能导致 OOM。

我们从问题的本质入手，调用者采用 `CallerRunsPolicy` 是希望所有的任务都能够被执行，暂时无法处理的任务又被保存在阻塞队列 `BlockingQueue` 中。这样的话，在内存允许的情况下，我们可以增加阻塞队列 `BlockingQueue` 的大小并调整堆内存以容纳更多的任务，确保任务能够被准确执行。

为了充分利用 CPU，我们还可以调整线程池的 `maximumPoolSize`（最大线程数）参数，这样可以提高任务处理速度，避免累计在 `BlockingQueue` 的任务过多导致内存用完。

![调整阻塞队列大小和最大线程数](images/threadpool-reject-2-threadpool-reject-01-fd0146c1.png)

如果服务器资源已达到可利用的极限，这就意味我们要在设计策略上改变线程池的调度了，我们都知道，导致主线程卡死的本质就是因为我们不希望任何一个任务被丢弃。换个思路，有没有办法既能保证任务不被丢弃且在服务器有余力时及时处理呢？

这里提供的一种**任务持久化**的思路，这里所谓的任务持久化，包括但不限于:

1. 设计一张任务表将任务存储到 MySQL 数据库中。
2. Redis 缓存任务。
3. 将任务提交到消息队列中。

这里以方案一为例，简单介绍一下实现逻辑：

1. 实现 `RejectedExecutionHandler` 接口自定义拒绝策略，自定义拒绝策略负责将线程池暂时无法处理（此时阻塞队列已满）的任务入库（保存到 MySQL 中）。注意：线程池暂时无法处理的任务会先被放在阻塞队列中，阻塞队列满了才会触发拒绝策略。
2. 继承 `BlockingQueue` 实现一个混合式阻塞队列，该队列包含 JDK 自带的 `ArrayBlockingQueue`。另外，该混合式阻塞队列需要修改取任务处理的逻辑，也就是重写 `take()` 方法，取任务时优先从数据库中读取最早的任务，数据库中无任务时再从 `ArrayBlockingQueue` 中去取任务。

![将一部分任务保存到MySQL中](images/threadpool-reject-2-threadpool-reject-02-e532728d.png)

整个实现逻辑还是比较简单的，核心在于自定义拒绝策略和阻塞队列。如此一来，一旦我们的线程池中线程达到满载时，我们就可以通过拒绝策略将最新任务持久化到 MySQL 数据库中，等到线程池有了有余力处理所有任务时，让其优先处理数据库中的任务以避免“饥饿”问题。

当然，对于这个问题，我们也可以参考其他主流框架的做法，以 Netty 为例，它的拒绝策略则是直接创建一个线程池以外的线程处理这些任务，为了保证任务的实时处理，这种做法可能需要良好的硬件设备且临时创建的线程无法做到准确的监控：

```java
private static final class NewThreadRunsPolicy implements RejectedExecutionHandler {
    NewThreadRunsPolicy() {
        super();
    }
    public void rejectedExecution(Runnable r, ThreadPoolExecutor executor) {
        try {
            //创建一个临时线程处理任务
            final Thread t = new Thread(r, "Temporary task executor");
            t.start();
        } catch (Throwable e) {
            throw new RejectedExecutionException(
                    "Failed to start a new thread", e);
        }
    }
}
```

ActiveMQ 则是尝试在指定的时效内尽可能的争取将任务入队，以保证最大交付：

```java
new RejectedExecutionHandler() {
                @Override
                public void rejectedExecution(final Runnable r, final ThreadPoolExecutor executor) {
                    try {
                        //限时阻塞等待，实现尽可能交付
                        executor.getQueue().offer(r, 60, TimeUnit.SECONDS);
                    } catch (InterruptedException e) {
                        throw new RejectedExecutionException("Interrupted waiting for BrokerService.worker");
                    }
                    throw new RejectedExecutionException("Timed Out while attempting to enqueue Task.");
                }
            });
```

#### 线程池常用的阻塞队列有哪些？

新任务来的时候会先判断当前运行的线程数量是否达到核心线程数，如果达到的话，新任务就会被存放在队列中。

不同的线程池会选用不同的阻塞队列，我们可以结合内置线程池来分析。

- 容量为 `Integer.MAX_VALUE` 的 `LinkedBlockingQueue`（无界阻塞队列）：`FixedThreadPool` 和 `SingleThreadExecutor`。`FixedThreadPool` 最多只能创建核心线程数的线程（核心线程数和最大线程数相等），`SingleThreadExecutor` 只能创建一个线程（核心线程数和最大线程数都是 1），二者的任务队列永远不会被放满。
- `SynchronousQueue`（同步队列）：`CachedThreadPool`。`SynchronousQueue` 没有容量，不存储元素，目的是保证对于提交的任务，如果有空闲线程，则使用空闲线程来处理；否则新建一个线程来处理任务。也就是说，`CachedThreadPool` 的最大线程数是 `Integer.MAX_VALUE`，可以理解为线程数是可以无限扩展的，可能会创建大量线程，从而导致 OOM。
- `DelayedWorkQueue`（延迟队列）：`ScheduledThreadPool` 和 `SingleThreadScheduledExecutor`。`DelayedWorkQueue` 的内部元素并不是按照放入的时间排序，而是会按照延迟的时间长短对任务进行排序，内部采用的是“堆”的数据结构，可以保证每次出队的任务都是当前队列中执行时间最靠前的。`DelayedWorkQueue` 是一个无界队列。其底层虽然是数组，但当数组容量不足时，它会自动进行扩容，因此队列永远不会被填满。当任务不断提交时，它们会全部被添加到队列中。这意味着线程池的线程数量永远不会超过其核心线程数，最大线程数参数对于使用该队列的线程池来说是无效的。
- `ArrayBlockingQueue`（有界阻塞队列）：底层由数组实现，容量一旦创建，就不能修改。

#### ⭐️ 线程池处理任务的流程了解吗？

![图解线程池实现原理](images/thread-pool-principle-aa009a67.png)

1. 如果当前运行的线程数小于核心线程数，那么就会新建一个线程来执行任务。
2. 如果当前运行的线程数等于或大于核心线程数，但是小于最大线程数，那么就把该任务放入到任务队列里等待执行。
3. 如果向任务队列投放任务失败（任务队列已经满了），但是当前运行的线程数是小于最大线程数的，就新建一个线程来执行任务。
4. 如果当前运行的线程数已经等同于最大线程数了，新建线程将会使当前运行的线程超出最大线程数，那么当前任务会被拒绝，拒绝策略会调用 `RejectedExecutionHandler.rejectedExecution()` 方法。

再提一个有意思的小问题：**线程池在提交任务前，可以提前创建线程吗？**

答案是可以的！`ThreadPoolExecutor` 提供了两个方法帮助我们在提交任务之前，完成核心线程的创建，从而实现线程池预热的效果：

- `prestartCoreThread()`:启动一个线程，等待任务，如果已达到核心线程数，这个方法返回 false，否则返回 true；
- `prestartAllCoreThreads()`:启动所有的核心线程，并返回启动成功的核心线程数。

#### ⭐️ 线程池中线程异常后，销毁还是复用？

直接说结论，需要分两种情况：

- **使用 `execute()` 提交任务**：当任务通过 `execute()` 提交到线程池并在执行过程中抛出异常时，如果这个异常没有在任务内被捕获，那么该异常会导致当前线程终止，并且异常会被打印到控制台或日志文件中。线程池会检测到这种线程终止，并创建一个新线程来替换它，从而保持配置的线程数不变。
- **使用 `submit()` 提交任务**：对于通过 `submit()` 提交的任务，如果在任务执行中发生异常，这个异常不会直接打印出来。相反，异常会被封装在由 `submit()` 返回的 `Future` 对象中。当调用 `Future.get()` 方法时，可以捕获到一个 `ExecutionException`。在这种情况下，线程不会因为异常而终止，它会继续存在于线程池中，准备执行后续的任务。

简单来说：使用 `execute()` 时，未捕获异常导致线程终止，线程池创建新线程替代；使用 `submit()` 时，异常被封装在 `Future` 中，线程继续复用。

这种设计允许 `submit()` 提供更灵活的错误处理机制，因为它允许调用者决定如何处理异常，而 `execute()` 则适用于那些不需要关注执行结果的场景。

具体的源码分析可以参考这篇：[线程池中线程异常后：销毁还是复用？ - 京东技术](https://mp.weixin.qq.com/s/9ODjdUU-EwQFF5PrnzOGfw)。

#### ⭐️ 如何给线程池命名？

初始化线程池的时候需要显示命名（设置线程池名称前缀），有利于定位问题。

默认情况下创建的线程名字类似 `pool-1-thread-n` 这样的，没有业务含义，不利于我们定位问题。

给线程池里的线程命名通常有下面两种方式：

**1、利用 guava 的 `ThreadFactoryBuilder`**

```java
ThreadFactory threadFactory = new ThreadFactoryBuilder()
                        .setNameFormat(threadNamePrefix + "-%d")
                        .setDaemon(true).build();
ExecutorService threadPool = new ThreadPoolExecutor(corePoolSize, maximumPoolSize, keepAliveTime, TimeUnit.MINUTES, workQueue, threadFactory);
```

**2、自己实现 `ThreadFactory`。**

```java
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 线程工厂，它设置线程名称，有利于我们定位问题。
 */
public final class NamingThreadFactory implements ThreadFactory {

    private final AtomicInteger threadNum = new AtomicInteger();
    private final String name;

    /**
     * 创建一个带名字的线程池生产工厂
     */
    public NamingThreadFactory(String name) {
        this.name = name;
    }

    @Override
    public Thread newThread(Runnable r) {
        Thread t = new Thread(r);
        t.setName(name + " [#" + threadNum.incrementAndGet() + "]");
        return t;
    }
}
```

#### 如何设定线程池的大小？

很多人甚至可能都会觉得把线程池配置过大一点比较好！我觉得这明显是有问题的。就拿我们生活中非常常见的一例子来说：**并不是人多就能把事情做好，增加了沟通交流成本。你本来一件事情只需要 3 个人做，你硬是拉来了 6 个人，会提升做事效率嘛？我想并不会。** 线程数量过多的影响也是和我们分配多少人做事情一样，对于多线程这个场景来说主要是增加了**上下文切换**成本。不清楚什么是上下文切换的话，可以看我下面的介绍。

> 上下文切换：
>
> 多线程编程中一般线程的个数都大于 CPU 核心的个数，而一个 CPU 核心在任意时刻只能被一个线程使用，为了让这些线程都能得到有效执行，CPU 采取的策略是为每个线程分配时间片并轮转的形式。当一个线程的时间片用完的时候就会重新处于就绪状态让给其他线程使用，这个过程就属于一次上下文切换。概括来说就是：当前任务在执行完 CPU 时间片切换到另一个任务之前会先保存自己的状态，以便下次再切换回这个任务时，可以再加载这个任务的状态。**任务从保存到再加载的过程就是一次上下文切换**。
>
> 上下文切换通常是计算密集型的。也就是说，它需要相当可观的处理器时间，在每秒几十上百次的切换中，每次切换都需要纳秒量级的时间。所以，上下文切换对系统来说意味着消耗大量的 CPU 时间，事实上，可能是操作系统中时间消耗最大的操作。
>
> Linux 相比与其他操作系统（包括其他类 Unix 系统）有很多的优点，其中有一项就是，其上下文切换和模式切换的时间消耗非常少。

类比于现实世界中的人类通过合作做某件事情，我们可以肯定的一点是线程池大小设置过大或者过小都会有问题，合适的才是最好。

- 如果我们设置的线程池数量太小的话，如果同一时间有大量任务/请求需要处理，可能会导致大量的请求/任务在任务队列中排队等待执行，甚至会出现任务队列满了之后任务/请求无法处理的情况，或者大量任务堆积在任务队列导致 OOM。这样很明显是有问题的，CPU 根本没有得到充分利用。
- 如果我们设置线程数量太大，大量线程可能会同时在争取 CPU 资源，这样会导致大量的上下文切换，从而增加线程的执行时间，影响了整体执行效率。

有一个简单并且适用面比较广的公式：

- **CPU 密集型任务(N+1)：** 这种任务消耗的主要是 CPU 资源，可以将线程数设置为 N（CPU 核心数）+1。比 CPU 核心数多出来的一个线程是为了防止线程偶发的缺页中断，或者其它原因导致的任务暂停而带来的影响。一旦任务暂停，CPU 就会处于空闲状态，而在这种情况下多出来的一个线程就可以充分利用 CPU 的空闲时间。
- **I/O 密集型任务(2N)：** 这种任务应用起来，系统会用大部分的时间来处理 I/O 交互，而线程在处理 I/O 的时间段内不会占用 CPU 来处理，这时就可以将 CPU 交出给其它线程使用。因此在 I/O 密集型任务的应用中，我们可以多配置一些线程，具体的计算方法是 2N。

**如何判断是 CPU 密集任务还是 IO 密集任务？**

CPU 密集型简单理解就是利用 CPU 计算能力的任务比如你在内存中对大量数据进行排序。但凡涉及到网络读取，文件读取这类都是 IO 密集型，这类任务的特点是 CPU 计算耗费时间相比于等待 IO 操作完成的时间来说很少，大部分时间都花在了等待 IO 操作完成上。

> 🌈 拓展一下（参见：[issue#1737](https://github.com/Snailclimb/JavaGuide/issues/1737)）：
>
> 线程数更严谨的计算的方法应该是：`最佳线程数 = N（CPU 核心数）∗（1+WT（线程等待时间）/ST（线程计算时间））`，其中 `WT（线程等待时间）=线程运行总时间 - ST（线程计算时间）`。
>
> 线程等待时间所占比例越高，需要越多线程。线程计算时间所占比例越高，需要越少线程。
>
> 我们可以通过 JDK 自带的工具 VisualVM 来查看 `WT/ST` 比例。
>
> CPU 密集型任务的 `WT/ST` 接近或者等于 0，因此， 线程数可以设置为 N（CPU 核心数）∗（1+0）= N，和我们上面说的 N（CPU 核心数）+1 差不多。
>
> IO 密集型任务下，几乎全是线程等待时间，从理论上来说，你就可以将线程数设置为 2N（按道理来说，WT/ST 的结果应该比较大，这里选择 2N 的原因应该是为了避免创建过多线程吧）。

公式也只是参考，具体还是要根据项目实际线上运行情况来动态调整。我在后面介绍的美团的线程池参数动态配置这种方案就非常不错，很实用！

#### ⭐️ 如何动态修改线程池的参数？

美团技术团队在[《Java 线程池实现原理及其在美团业务中的实践》](https://tech.meituan.com/2020/04/02/java-pooling-pratice-in-meituan.html)这篇文章中介绍到对线程池参数实现可自定义配置的思路和方法。

美团技术团队的思路是主要对线程池的核心参数实现自定义可配置。这三个核心参数是：

- **`corePoolSize`：** 默认情况下，即使空闲也会保留在线程池中的线程数量；工作线程少于该值时，新任务会优先触发创建线程。
- **`maximumPoolSize`：** 线程池允许存在的最大工作线程数。
- **`workQueue`：** 工作线程数达到 `corePoolSize` 后，新任务会先尝试进入队列；入队失败时才会在不超过 `maximumPoolSize` 的前提下继续创建线程。

**为什么是这三个参数？**

我在[Java 线程池详解](https://javaguide.cn/java/concurrent/java-thread-pool-summary.html) 这篇文章中就说过这三个参数是 `ThreadPoolExecutor` 最重要的参数，它们基本决定了线程池对于任务的处理策略。

**如何支持参数动态配置？** 且看 `ThreadPoolExecutor` 提供的下面这些方法。

格外需要注意的是 `corePoolSize`。运行期间调小该参数后，超过新核心线程数的现有线程会在下一次空闲时终止；调大时，如果队列中已有任务，线程池会按需启动新线程处理。

另外，你也看到了上面并没有动态指定队列长度的方法，美团的方式是自定义了一个叫做 `ResizableCapacityLinkedBlockingQueue` 的队列（主要就是把 `LinkedBlockingQueue` 的 capacity 字段的 final 关键字修饰给去掉了，让它变为可变的）。

最终实现的可动态修改线程池参数效果如下。👏👏👏

![动态配置线程池参数最终效果](images/meituan-dynamically-configuring-thread-pool-parameters-d0b95441.png)

还没看够？我在[《后端面试高频系统设计&场景题》](https://javaguide.cn/zhuanlan/back-end-interview-high-frequency-system-design-and-scenario-questions.html)中详细介绍了如何设计一个动态线程池，这也是面试中常问的一道系统设计题。

![《后端面试高频系统设计&场景题》](images/back-end-interview-high-frequency-system-design-and-scenario-d512d87a.png)

如果我们的项目也想要实现这种效果的话，可以借助现成的开源项目：

- **[Hippo4j](https://github.com/opengoofy/hippo4j)**：异步线程池框架，支持线程池动态变更&监控&报警，无需修改代码轻松引入。支持多种使用模式，轻松引入，致力于提高系统运行保障能力。
- **[Dynamic TP](https://github.com/dromara/dynamic-tp)**：轻量级动态线程池，内置监控告警功能，集成三方中间件线程池管理，基于主流配置中心（已支持 Nacos、Apollo，Zookeeper、Consul、Etcd，可通过 SPI 自定义实现）。

#### ⭐️ 如何设计一个能够根据任务的优先级来执行的线程池？

这是一个常见的面试问题，本质其实还是在考察求职者对于线程池以及阻塞队列的掌握。

我们上面也提到了，不同的线程池会选用不同的阻塞队列作为任务队列。`FixedThreadPool` 使用默认容量为 `Integer.MAX_VALUE` 的 `LinkedBlockingQueue`，通常将其视为无界队列；实际应用几乎无法填满，因此 `FixedThreadPool` 通常只会创建 `corePoolSize` 个工作线程。

假如我们需要实现一个优先级任务线程池的话，那可以考虑使用 `PriorityBlockingQueue`（优先级阻塞队列）作为任务队列（`ThreadPoolExecutor` 的构造函数有一个 `workQueue` 参数可以传入任务队列）。

![ThreadPoolExecutor构造函数](images/common-parameters-of-threadpool-workqueue-654c3310.jpg)

`PriorityBlockingQueue` 是一个支持优先级的无界阻塞队列，可以看作是线程安全的 `PriorityQueue`，两者底层都是使用小顶堆形式的二叉堆，即值最小的元素优先出队。不过，`PriorityQueue` 不支持阻塞操作。

要想让 `PriorityBlockingQueue` 实现对任务的排序，传入其中的任务必须是具备排序能力的，方式有两种：

1. 提交到线程池的任务实现 `Comparable` 接口，并重写 `compareTo` 方法来指定任务之间的优先级比较规则。
2. 创建 `PriorityBlockingQueue` 时传入一个 `Comparator` 对象来指定任务之间的排序规则（推荐）。

不过，这存在一些风险和问题，比如：

- `PriorityBlockingQueue` 是无界的，可能堆积大量的请求，从而导致 OOM。
- 可能会导致饥饿问题，即低优先级的任务长时间得不到执行。
- 由于需要对队列中的元素进行排序操作以及保证线程安全（并发控制采用的是可重入锁 `ReentrantLock`），因此会降低性能。

对于 OOM 这个问题的解决比较简单粗暴，就是继承 `PriorityBlockingQueue` 并重写一下 `offer` 方法（入队）的逻辑，当插入的元素数量超过指定值就返回 false。

饥饿问题这个可以通过优化设计来解决（比较麻烦），比如等待时间过长的任务会被移除并重新添加到队列中，但是优先级会被提升。

对于性能方面的影响，是没办法避免的，毕竟需要对任务进行排序操作。并且，对于大部分业务场景来说，这点性能影响是可以接受的。

### 【Future】

#### Future 接口有什么用？

`Future` 接口是异步思想的典型运用，主要用在一些需要执行耗时任务的场景，避免程序一直原地等待耗时任务执行完成，执行效率太低。具体来说是这样的：当我们执行某一耗时的任务时，可以将这个耗时任务交给一个子线程去异步执行，同时我们可以干点其他事情，不用傻傻等待耗时任务执行完成。等我们的事情干完后，我们再通过 `Future` 获取到耗时任务的执行结果。这样一来，程序的执行效率就明显提高了。

这其实就是多线程中经典的 **Future 模式**，你可以将其看作是一种设计模式，核心思想是异步调用，主要用在多线程领域，并非 Java 语言独有。

在 Java 中，`Future` 是一个泛型接口，位于 `java.util.concurrent` 包下。它有 5 个经典抽象方法，主要包括下面 4 类功能；JDK 19 起又增加了 `resultNow()`、`exceptionNow()` 和 `state()` 三个默认查询方法。

- 取消任务；
- 判断任务是否被取消;
- 判断任务是否已经执行完成;
- 获取任务执行结果。

```java
// V 代表了Future执行的任务返回值的类型
public interface Future {
    // 取消任务执行
    // 成功取消返回 true，否则返回 false
    boolean cancel(boolean mayInterruptIfRunning);
    // 判断任务是否被取消
    boolean isCancelled();
    // 判断任务是否已经执行完成
    boolean isDone();
    // 获取任务执行结果
    V get() throws InterruptedException, ExecutionException;
    // 指定时间内没有返回计算结果就抛出 TimeOutException 异常
    V get(long timeout, TimeUnit unit)

        throws InterruptedException, ExecutionException, TimeoutExceptio

}
```

简单理解就是：我有一个任务，提交给了 `Future` 来处理。任务执行期间我自己可以去做任何想做的事情。并且，在这期间我还可以取消任务以及获取任务的执行状态。一段时间之后，我就可以 `Future` 那里直接取出任务执行结果。

#### Callable 和 Future 有什么关系？

我们可以通过 `FutureTask` 来理解 `Callable` 和 `Future` 之间的关系。

`FutureTask` 提供了 `Future` 接口的基本实现，常用来封装 `Callable` 和 `Runnable`，具有取消任务、查看任务是否执行完成以及获取任务执行结果的方法。`ExecutorService.submit()` 方法返回的其实就是 `Future` 的实现类 `FutureTask`。

```java
 Future submit(Callable task);
Future<?> submit(Runnable task);
```

`FutureTask` 不光实现了 `Future` 接口，还实现了 `Runnable` 接口，因此可以作为任务直接被线程执行。

`FutureTask` 有两个构造函数，可传入 `Callable` 或者 `Runnable` 对象。实际上，传入 `Runnable` 对象也会在方法内部转换为 `Callable` 对象。

```java
public FutureTask(Callable callable) {
    if (callable == null)
        throw new NullPointerException();
    this.callable = callable;
    this.state = NEW;
}
public FutureTask(Runnable runnable, V result) {
    // 通过适配器RunnableAdapter来将Runnable对象runnable转换成Callable对象
    this.callable = Executors.callable(runnable, result);
    this.state = NEW;
}
```

`FutureTask` 相当于对 `Callable` 进行了封装，管理着任务执行的情况，存储了 `Callable` 的 `call` 方法的任务执行结果。

关于更多 `Future` 的源码细节，可以肝这篇万字解析，写的很清楚：[Java 是如何实现 Future 模式的？万字详解！](https://juejin.cn/post/6844904199625375757)。

#### CompletableFuture 类有什么用？

`Future` 在实际使用过程中存在一些局限性，比如不支持异步任务的编排组合、获取计算结果的 `get()` 方法为阻塞调用。

Java 8 才被引入 `CompletableFuture` 类可以解决 `Future` 的这些缺陷。`CompletableFuture` 除了提供了更为好用和强大的 `Future` 特性之外，还提供了函数式编程、异步任务编排组合（可以将多个异步任务串联起来，组成一个完整的链式调用）等能力。

下面我们来简单看看 `CompletableFuture` 类的定义。

```java
public class CompletableFuture implements Future, CompletionStage {
}
```

可以看到，`CompletableFuture` 同时实现了 `Future` 和 `CompletionStage` 接口。

`CompletionStage` 接口描述了一个异步计算的阶段。很多计算可以分成多个阶段或步骤，此时可以通过它将所有步骤组合起来，形成异步计算的流水线。

`CompletionStage` 接口中的方法比较多，`CompletableFuture` 的函数式能力就是这个接口赋予的。从这个接口的方法参数你就可以发现其大量使用了 Java8 引入的函数式编程。

#### ⭐️ 一个任务需要依赖另外两个任务执行完之后再执行，怎么设计？

这种任务编排场景非常适合通过 `CompletableFuture` 实现。这里假设要实现 T3 在 T2 和 T1 执行完后执行。

代码如下（这里为了简化代码，用到了 Hutool 的线程工具类 `ThreadUtil` 和日期时间工具类 `DateUtil`）：

```java
// T1
CompletableFuture futureT1 = CompletableFuture.runAsync(() -> {
    System.out.println("T1 is executing. Current time：" + DateUtil.now());
    // 模拟耗时操作
    ThreadUtil.sleep(1000);
});
// T2
CompletableFuture futureT2 = CompletableFuture.runAsync(() -> {
    System.out.println("T2 is executing. Current time：" + DateUtil.now());
    ThreadUtil.sleep(1000);
});

// 使用allOf()方法合并T1和T2的CompletableFuture，等待它们都完成
CompletableFuture bothCompleted = CompletableFuture.allOf(futureT1, futureT2);
// 当T1和T2都完成后，执行T3
bothCompleted.thenRunAsync(() -> System.out.println("T3 is executing after T1 and T2 have completed.Current time：" + DateUtil.now()));
// 等待所有任务完成，验证效果
ThreadUtil.sleep(3000);
```

`T1` 和 `T2` 在前面通过 `runAsync()` 启动，`allOf()` 只组合它们的完成状态：当二者都完成后，再执行 T3。是否并行取决于任务的创建方式和执行器，而不是 `allOf()` 本身。

#### ⭐️ 使用 CompletableFuture，有一个任务失败，如何处理异常？

使用 `CompletableFuture` 的时候一定要以正确的方式进行异常处理，避免异常丢失或者出现不可控问题。

下面是一些建议：

- `whenComplete` 会在阶段正常或异常完成时执行回调，适合观察结果和记录异常；它默认保留原阶段的结果或异常。
- `exceptionally` 只在阶段异常完成时执行，并用回调的返回值恢复为正常结果；如果需要继续传播异常，可以在回调中显式抛出异常。
- `handle` 无论阶段正常还是异常完成都会执行，并根据结果和异常生成一个新的结果。
- `CompletableFuture.allOf` 可以等待多个阶段全部完成；只要其中一个阶段异常完成，返回的 `CompletableFuture` 也会异常完成，但仍需分别检查各阶段才能获得每个任务的结果或异常。
- ……

#### ⭐️ 在使用 CompletableFuture 的时候为什么要自定义线程池？

在 `CompletableFuture` 的默认实现中，没有显式传入 `Executor` 的异步方法通常使用全局共享的 `ForkJoinPool.commonPool()`；子类可以通过重写 `defaultExecutor()` 改变非静态异步方法的默认执行器。这意味着使用默认实现的应用程序和库通常会共享同一个线程池。

虽然 `ForkJoinPool` 效率很高，但当同时提交大量任务时，可能会导致资源竞争和线程饥饿，进而影响系统性能。

为避免这些问题，建议为 `CompletableFuture` 提供自定义线程池，带来以下优势：

- 隔离性：为不同任务分配独立的线程池，避免全局线程池资源争夺。
- 资源控制：根据任务特性调整线程池大小和队列类型，优化性能表现。
- 异常处理：通过自定义 `ThreadFactory` 更好地处理线程中的异常情况。

```java
private ThreadPoolExecutor executor = new ThreadPoolExecutor(10, 10,
        0L, TimeUnit.MILLISECONDS,
        new LinkedBlockingQueue());

CompletableFuture.runAsync(() -> {
     //...
}, executor);
```

### 【AQS】

#### AQS 是什么？

AQS（`AbstractQueuedSynchronizer`，抽象队列同步器）是从 JDK1.5 开始提供的 Java 并发核心组件。

AQS 解决了开发者在实现同步器时的复杂性问题。它提供了一个通用框架，用于实现各种同步器，例如 **可重入锁**（`ReentrantLock`）、**信号量**（`Semaphore`）和 **倒计时器**（`CountDownLatch`）。通过封装底层的线程同步机制，AQS 将复杂的线程管理逻辑隐藏起来，使开发者只需专注于具体的同步逻辑。

简单来说，AQS 是一个抽象类，为同步器提供了通用的 **执行框架**。它定义了 **资源获取和释放的通用流程**，而具体的资源获取逻辑则由具体同步器通过重写模板方法来实现。 因此，可以将 AQS 看作是同步器的 **基础“底座”**，而同步器则是基于 AQS 实现的 **具体“应用”**。

#### ⭐️ AQS 的原理是什么？

> 说明：下面展示的 `waitStatus`、`Unsafe.compareAndSwapInt()` 等内部结构和源码片段基于 JDK 8。AQS 的内部实现后来持续演进：JDK 11 中仍保留了本文涉及的主要结构，JDK 17 及当前版本的节点字段和入队、等待实现则已有较大变化，但同步状态、等待队列和模板方法这些核心思想仍然适用。

AQS 核心思想是，如果被请求的共享资源空闲，则将当前请求资源的线程设置为有效的工作线程，并且将共享资源设置为锁定状态。如果被请求的共享资源被占用，那么就需要一套线程阻塞等待以及被唤醒时锁分配的机制，这个机制 AQS 是基于 **CLH 锁**（Craig, Landin, and Hagersten locks） 进一步优化实现的。

**CLH 锁** 对自旋锁进行了改进，是基于单链表的自旋锁。在多线程场景下，会将请求获取锁的线程组织成一个单向队列，每个等待的线程会通过自旋访问前一个线程节点的状态，前一个节点释放锁之后，当前节点才可以获取锁。**CLH 锁** 的队列结构如下图所示。

![CLH 锁的队列结构](images/clh-lock-queue-structure-229709df.png)

AQS 中使用的 **等待队列** 是 CLH 锁队列的变体（接下来简称为 CLH 变体队列）。

AQS 的 CLH 变体队列是一个双向队列，会暂时获取不到锁的线程将被加入到该队列中，CLH 变体队列和原本的 CLH 锁队列的区别主要有两点：

- 由 **自旋** 优化为 **自旋 + 阻塞**：自旋操作的性能很高，但大量的自旋操作比较占用 CPU 资源，因此在 CLH 变体队列中会先通过自旋尝试获取锁，如果失败再进行阻塞等待。
- 由 **单向队列** 优化为 **双向队列**：在 CLH 变体队列中，会对等待的线程进行阻塞操作，当队列前边的线程释放锁之后，需要对后边的线程进行唤醒，因此增加了 `next` 指针，成为了双向队列。

AQS 将每条请求共享资源的线程封装成一个 CLH 变体队列的一个结点（Node）来实现锁的分配。在 CLH 变体队列中，一个节点表示一个线程，它保存着线程的引用（thread）、 当前节点在队列中的状态（waitStatus）、前驱节点（prev）、后继节点（next）。

AQS 中的 CLH 变体队列结构如下图所示：

![CLH 变体队列结构](images/clh-queue-structure-bianti-877c7ae8.png)

AQS(`AbstractQueuedSynchronizer`)的核心原理图：

![CLH 变体队列](images/clh-queue-state-7830440b.png)

AQS 使用 **int 成员变量 `state` 表示同步状态**，通过内置的 **线程等待队列** 来完成获取资源线程的排队工作。

`state` 变量由 `volatile` 修饰，用于展示当前临界资源的获锁情况。

```java
// 共享变量，使用volatile修饰保证线程可见性
private volatile int state;
```

另外，状态信息 `state` 可以通过 `protected` 类型的 `getState()`、`setState()` 和 `compareAndSetState()` 进行操作。并且，这几个方法都是 `final` 修饰的，在子类中无法被重写。

```java
//返回同步状态的当前值
protected final int getState() {
     return state;
}
 // 设置同步状态的值
protected final void setState(int newState) {
     state = newState;
}
//原子地（CAS操作）将同步状态值设置为给定值update如果当前同步状态的值等于expect（期望值）
protected final boolean compareAndSetState(int expect, int update) {
      return unsafe.compareAndSwapInt(this, stateOffset, expect, update);
}
```

以 `ReentrantLock` 为例，`state` 初始值为 0，表示未锁定状态。A 线程 `lock()` 时，会调用 `tryAcquire()` 独占该锁并将 `state+1`。此后，其他线程再 `tryAcquire()` 时就会失败，直到 A 线程 `unlock()` 到 `state=`0（即释放锁）为止，其它线程才有机会获取该锁。当然，释放锁之前，A 线程自己是可以重复获取此锁的（`state` 会累加），这就是可重入的概念。但要注意，获取多少次就要释放多少次，这样才能保证 state 是能回到零态的。

再以 `CountDownLatch` 为例，`state` 初始化为 N，表示需要等待 N 次 `countDown()` 调用。N 表示事件数或计数次数，不要求与线程数一致；同一个线程可以调用多次，也可以由多个线程分别调用。当 `state` 变为 0 时，等待队列中因调用 `await()` 而阻塞的线程会被唤醒并继续执行。

#### Semaphore 有什么用？

`synchronized` 和 `ReentrantLock` 都是一次只允许一个线程访问某个资源，而 `Semaphore`（信号量）可以用来控制同时访问特定资源的线程数量。

Semaphore 的使用简单，我们这里假设有 N(N>5) 个线程来获取 `Semaphore` 中的共享资源，下面的代码表示同一时刻 N 个线程中只有 5 个线程能获取到共享资源，其他线程都会阻塞，只有获取到共享资源的线程才能执行。等到有线程释放了共享资源，其他阻塞的线程才能获取到。

```java
// 初始共享资源数量
final Semaphore semaphore = new Semaphore(5);
// 获取1个许可
semaphore.acquire();
// 释放1个许可
semaphore.release();
```

当许可证数量为 1 时，`Semaphore` 可以把并发访问数限制为 1，但它不同于互斥锁：信号量没有所有权约束，获取许可证的线程和释放许可证的线程可以不是同一个线程。

`Semaphore` 有两种模式：。

- **公平模式：** 存在竞争时，阻塞式 `acquire` 方法会在内部排队点按 FIFO 选择线程；无参的 `tryAcquire()` 不遵守公平设置，仍可能插队成功；
- **非公平模式：** 抢占式的。

`Semaphore` 对应的两个构造方法如下：

```java
public Semaphore(int permits) {
    sync = new NonfairSync(permits);
}

public Semaphore(int permits, boolean fair) {
    sync = fair ? new FairSync(permits) : new NonfairSync(permits);
}
```

**这两个构造方法，都必须提供许可的数量，第二个构造方法可以指定是公平模式还是非公平模式，默认非公平模式。**

`Semaphore` 通常用于那些资源有明确访问数量限制的场景比如限流（仅限于单机模式，实际项目中推荐使用 Redis +Lua 来做限流）。

#### Semaphore 的原理是什么？

`Semaphore` 是共享锁的一种实现，它默认构造 AQS 的 `state` 值为 `permits`，你可以将 `permits` 的值理解为许可证的数量，只有拿到许可证的线程才能执行。

调用 `semaphore.acquire()`，线程尝试获取许可证，如果 `state >= 0` 的话，则表示可以获取成功。如果获取成功的话，使用 CAS 操作去修改 `state` 的值 `state=state-1`。如果 `state<0` 的话，则表示许可证数量不足。此时会创建一个 Node 节点加入阻塞队列，挂起当前线程。

```java
/**
 *  获取1个许可证
 */
public void acquire() throws InterruptedException {
    sync.acquireSharedInterruptibly(1);
}
/**
 * 共享模式下获取许可证，获取成功则返回，失败则加入阻塞队列，挂起线程
 */
public final void acquireSharedInterruptibly(int arg)
    throws InterruptedException {
    if (Thread.interrupted())
      throw new InterruptedException();
        // 尝试获取许可证，arg为获取许可证个数，当可用许可证数减当前获取的许可证数结果小于0,则创建一个节点加入阻塞队列，挂起当前线程。
    if (tryAcquireShared(arg) < 0)
      doAcquireSharedInterruptibly(arg);
}
```

调用 `semaphore.release();`，线程尝试释放许可证，并使用 CAS 操作去修改 `state` 的值 `state=state+1`。释放许可证成功之后，同时会唤醒同步队列中的一个线程。被唤醒的线程会重新尝试去修改 `state` 的值 `state=state-1`，如果 `state>=0` 则获取令牌成功，否则重新进入阻塞队列，挂起线程。

```java
// 释放一个许可证
public void release() {
    sync.releaseShared(1);
}

// 释放共享锁，同时会唤醒同步队列中的一个线程。
public final boolean releaseShared(int arg) {
    //释放共享锁
    if (tryReleaseShared(arg)) {
      //唤醒同步队列中的一个线程
      doReleaseShared();
      return true;
    }
    return false;
}
```

#### CountDownLatch 有什么用？

`CountDownLatch` 允许任意数量的线程在 `await()` 处等待，直至发生 `count` 次 `countDown()` 调用。这个计数表示事件或操作次数，不一定对应 `count` 个不同线程。

`CountDownLatch` 是一次性的，计数器的值只能在构造方法中初始化一次，之后没有任何机制再次对其设置值，当 `CountDownLatch` 使用完毕后，它不能再次被使用。

#### CountDownLatch 的原理是什么？

`CountDownLatch` 是共享模式同步器的一种实现，它构造时将 AQS 的 `state` 设置为 `count`。每次调用 `countDown()` 都会通过 `tryReleaseShared` 将 `state` 减 1，直至为 0。调用 `await()` 时，如果 `state` 不为 0，当前线程就会等待：计数归零时，无参 `await()` 正常返回，带超时版本返回 `true`；等待期间被中断时会抛出 `InterruptedException`；带超时版本到期时返回 `false`。调用 `countDown()` 的次数与线程数量没有必然关系。

#### 用过 CountDownLatch 么？什么场景下用的？

`CountDownLatch` 的作用就是允许任意数量的线程在一个地方等待，直至发生 `count` 次 `countDown()` 调用。之前在项目中，有一个使用多线程读取多个文件处理的场景，我用到了 `CountDownLatch`。具体场景是下面这样的：

我们要读取处理 6 个文件，这 6 个任务都是没有执行顺序依赖的任务，但是我们需要返回给用户的时候将这几个文件的处理的结果进行统计整理。

为此我们定义了一个线程池和 count 为 6 的 `CountDownLatch` 对象。使用线程池处理读取任务，每一个线程处理完之后就将 count-1，调用 `CountDownLatch` 对象的 `countDown()` 方法，直到所有文件读取完之后，才会接着执行后面的逻辑。

伪代码是下面这样的：

```java
public class CountDownLatchExample1 {
    // 处理文件的数量
    private static final int threadCount = 6;

    public static void main(String[] args) throws InterruptedException {
        // 创建一个具有固定线程数量的线程池对象（推荐使用构造方法创建）
        ExecutorService threadPool = Executors.newFixedThreadPool(10);
        final CountDownLatch countDownLatch = new CountDownLatch(threadCount);
        for (int i = 0; i < threadCount; i++) {
            final int threadnum = i;
            threadPool.execute(() -> {
                try {
                    //处理文件的业务操作
                    //......
                } catch (InterruptedException e) {
                    e.printStackTrace();
                } finally {
                    //表示一个文件已经被完成
                    countDownLatch.countDown();
                }

            });
        }
        countDownLatch.await();
        threadPool.shutdown();
        System.out.println("finish");
    }
}
```

**有没有可以改进的地方呢？**

可以使用 `CompletableFuture` 类来改进！Java8 的 `CompletableFuture` 提供了很多对多线程友好的方法，使用它可以很方便地为我们编写多线程程序，什么异步、串行、并行或者等待所有线程执行完任务什么的都非常方便。

```java
CompletableFuture task1 =
    CompletableFuture.supplyAsync(()->{
        //自定义业务操作
    });
......
CompletableFuture task6 =
    CompletableFuture.supplyAsync(()->{
    //自定义业务操作
    });
......
CompletableFuture headerFuture=CompletableFuture.allOf(task1,.....,task6);

try {
    headerFuture.join();
} catch (Exception ex) {
    //......
}
System.out.println("all done. ");
```

上面的代码还可以继续优化，当任务过多的时候，把每一个 task 都列出来不太现实，可以考虑通过循环来添加任务。

```java
//文件夹位置
List filePaths = Arrays.asList(...)
// 异步处理所有文件
List> fileFutures = filePaths.stream()
    .map(filePath -> doSomeThing(filePath))
    .collect(Collectors.toList());
// 将他们合并起来
CompletableFuture allFutures = CompletableFuture.allOf(
    fileFutures.toArray(new CompletableFuture[fileFutures.size()])
);
```

#### CyclicBarrier 有什么用？

`CyclicBarrier` 和 `CountDownLatch` 非常类似，它也可以实现线程间的技术等待，但是它的功能比 `CountDownLatch` 更加复杂和强大。主要应用场景和 `CountDownLatch` 类似。

> `CountDownLatch` 的实现是基于 AQS 的，而 `CyclicBarrier` 是基于 `ReentrantLock`(`ReentrantLock` 也属于 AQS 同步器)和 `Condition` 的。

`CyclicBarrier` 的字面意思是可循环使用（Cyclic）的屏障（Barrier）。它要做的事情是：让一组线程到达一个屏障（也可以叫同步点）时被阻塞，直到最后一个线程到达屏障时，屏障才会开门，所有被屏障拦截的线程才会继续干活。

#### CyclicBarrier 的原理是什么？

`CyclicBarrier` 内部通过一个 `count` 变量作为计数器，`count` 的初始值为 `parties` 属性的初始化值，每当一个线程到了栅栏这里了，那么就将计数器减 1。如果 count 值为 0 了，表示这是这一代最后一个线程到达栅栏，就尝试执行我们构造方法中输入的任务。

```java
//每次拦截的线程数
private final int parties;
//计数器
private int count;
```

下面我们结合源码来简单看看。

1、`CyclicBarrier` 默认的构造方法是 `CyclicBarrier(int parties)`，其参数表示屏障拦截的线程数量，每个线程调用 `await()` 方法告诉 `CyclicBarrier` 我已经到达了屏障，然后当前线程被阻塞。

```java
public CyclicBarrier(int parties) {
    this(parties, null);
}

public CyclicBarrier(int parties, Runnable barrierAction) {
    if (parties <= 0) throw new IllegalArgumentException();
    this.parties = parties;
    this.count = parties;
    this.barrierCommand = barrierAction;
}
```

其中，`parties` 就代表了有拦截的线程的数量，当拦截的线程数量达到这个值的时候就打开栅栏，让所有线程通过。

2、当调用 `CyclicBarrier` 对象调用 `await()` 方法时，实际上调用的是 `dowait(false, 0L)` 方法。 `await()` 方法就像树立起一个栅栏的行为一样，将线程挡住了，当拦住的线程数量达到 `parties` 的值时，栅栏才会打开，线程才得以通过执行。

```java
public int await() throws InterruptedException, BrokenBarrierException {
  try {
      return dowait(false, 0L);
  } catch (TimeoutException toe) {
      throw new Error(toe); // cannot happen
  }
}
```

`dowait(false, 0L)` 方法源码分析如下：

```java
    // 当线程数量或者请求数量达到 count 时 await 之后的方法才会被执行。上面的示例中 count 的值就为 5。
    private int count;
    /**
     * Main barrier code, covering the various policies.
     */
    private int dowait(boolean timed, long nanos)
        throws InterruptedException, BrokenBarrierException,
               TimeoutException {
        final ReentrantLock lock = this.lock;
        // 锁住
        lock.lock();
        try {
            final Generation g = generation;

            if (g.broken)
                throw new BrokenBarrierException();

            // 如果线程中断了，抛出异常
            if (Thread.interrupted()) {
                breakBarrier();
                throw new InterruptedException();
            }
            // cout减1
            int index = --count;
            // 当 count 数量减为 0 之后说明最后一个线程已经到达栅栏了，也就是达到了可以执行await 方法之后的条件
            if (index == 0) {  // tripped
                boolean ranAction = false;
                try {
                    final Runnable command = barrierCommand;
                    if (command != null)
                        command.run();
                    ranAction = true;
                    // 将 count 重置为 parties 属性的初始化值
                    // 唤醒之前等待的线程
                    // 下一波执行开始
                    nextGeneration();
                    return 0;
                } finally {
                    if (!ranAction)
                        breakBarrier();
                }
            }

            // loop until tripped, broken, interrupted, or timed out
            for (;;) {
                try {
                    if (!timed)
                        trip.await();
                    else if (nanos > 0L)
                        nanos = trip.awaitNanos(nanos);
                } catch (InterruptedException ie) {
                    if (g == generation && ! g.broken) {
                        breakBarrier();
                        throw ie;
                    } else {
                        // We're about to finish waiting even if we had not
                        // been interrupted, so this interrupt is deemed to
                        // "belong" to subsequent execution.
                        Thread.currentThread().interrupt();
                    }
                }

                if (g.broken)
                    throw new BrokenBarrierException();

                if (g != generation)
                    return index;

                if (timed && nanos <= 0L) {
                    breakBarrier();
                    throw new TimeoutException();
                }
            }
        } finally {
            lock.unlock();
        }
    }
```

### 【虚拟线程】

#### 虚拟线程

虚拟线程在 Java 21 正式发布，这是一项重量级的更新。虽然目前面试中问的不多，但还是建议大家去简单了解一下。我写了一篇文章来总结虚拟线程常见的问题：[虚拟线程常见问题总结](https://javaguide.cn/java/concurrent/virtual-thread.html)，包含下面这些问题：

1. 什么是虚拟线程？
2. 虚拟线程和平台线程有什么关系？
3. 虚拟线程有什么优点和缺点？
4. 如何创建虚拟线程？
5. 虚拟线程的底层原理是什么？

#### 参考

- 《深入理解 Java 虚拟机》
- 《实战 Java 高并发程序设计》
- Java 线程池的实现原理及其在业务中的最佳实践：阿里云开发者：
- 带你了解下 SynchronousQueue（并发队列专题）：
- 阻塞队列 — DelayedWorkQueue 源码分析：
- Java 多线程（三）——FutureTask/CompletableFuture：
- Java 并发之 AQS 详解：
- Java 并发包基石-AQS 详解：

<!-- @include: @article-footer.snippet.md -->

## 出处与许可

- 原始仓库：[Snailclimb/JavaGuide](https://github.com/Snailclimb/JavaGuide)（★159k，持续维护，Apache-2.0）
- 收录范围：docs/database/redis、docs/database/mysql、docs/high-performance/message-queue、docs/cs-basics/network、docs/java/concurrent 下的问答式题集
- 本次整合只做章节归并与 frontmatter 清理，未改写任何问题与答案
- 原文中的配图已改为文字标注，避免离线阅读裂图
