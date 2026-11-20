# AI Infra 与大模型后训练的秋招实况

截至 2026 年 11 月 20 日，AI Infra 已有能核到岗位和城市的本届录用自报，也有同一人走完三面仍在等、同一人笔试后等约两个月才获一面的记录。后训练可核到的本届案例主要是业务算法面试、基模岗位简历受阻和实习转正失败。在本次检到的公开样本里，明确写出公司、纯后训练岗位和正式 offer 的记录集中在 **2026 届**。这给本届后训练的录用判断留下了证据缺口。[中兴与字节的不同结果](https://www.nowcoder.com/discuss/945319845942329344?sourceSSR=post) · [百度 Infra 三面后等待](https://www.nowcoder.com/feed/main/detail/341d6dd5d7f246d584be64ac69c0c172?sourceSSR=post) · [27 届大模型岗位日记](https://onlyar.site/2026/08/11/NLP-Interview-Knowkedge/) · [26 届混元后训练 offer](https://www.nowcoder.com/feed/main/detail/ad2063d009ae4df6a04efe62623d13a6?sourceSSR=post)

## 岗位和结果能对应到哪一步

| 方向与候选人 | 已经发生的事 | 截至发帖或更新时的状态 |
| --- | --- | --- |
| 训推基础设施，LUZJIE | 有三段相关实习。中兴天津大模型训推 10 月 20 日发 offer，字节豆包北京 10 月 8 日面完 HR、12 日发意向；快手 GenAI 异构计算二面未过 | 中兴写明发 offer，字节还在审批，腾讯云智算底座二面后等待。[10 月 29 日原帖](https://www.nowcoder.com/discuss/945319845942329344?sourceSSR=post) |
| GPU 算子，镜子Miracoln | 10 月 29 日比较北京寒武纪和深圳沐曦；11 月 3 日说明已拒沐曦。寒武纪经历了一面、二面与 HR 面 | 作者明确寒武纪尚无书面 offer。标题中的“offer 帮选”不能替代其更新。[条件比较](https://www.nowcoder.com/feed/main/detail/4264b38cb250423d98b20ce1693c33e5?sourceSSR=post) · [11 月 3 日更新](https://www.nowcoder.com/feed/main/detail/d852c978e3424390a01fbd30a9ea7ec6?sourceSSR=post) |
| AI Infra，许愿offerrrrrrof | 同时考虑长沙沐曦 AI Infra 与杭州字节 Agent 研发，自己已有软件开发和后训练经验 | 9 月 22 日两边都是意向，仅沐曦属于 Infra。帖子中的月薪是个人预估。[候选人原帖](https://www.nowcoder.com/feed/main/detail/52dd9d70e0e44b3bbc0ef1b329a0dfee?sourceSSR=post) |
| 基模、后训练/RL，Timoris | 传统数据挖掘方向本博，6 篇 A 会一作，较早参与过预训练实习；9 月记录了多家模型公司止于简历 | 11 月更新有四项选择，分别来自创业公司、国企、自驾和高校。没有一项被明确写成基模后训练。[投递记录与本人回帖](https://linux.do/t/topic/3032146?tl=en) · [11 月的选择清单](https://linux.do/t/topic/3156909) |
| VLM 强化学习及业务算法，Only(AR) | 字节抖音 AI 搜一面通过、8 月 17 日二面未过；淘天供给智能沿着 PEFT 实验、SFT 和 RL 经历连续追问 | 淘天 9 月 3 日到第四轮 HR，作者记录为等通知。两条流程属于同一人。[个人面试日记](https://onlyar.site/2026/08/11/NLP-Interview-Knowkedge/) |
| 训练 Infra、后训练研究，两位受访者 | 西木有训推框架实习，字节四面后无结果；井景选择基模实习并搭过训练流程，8 月得知不能转正 | 两人 10 月 21 日受访时都没有 offer。分别是秋招未落地与实习转正未成，只在发表时点成立。[白鲸实验室对当事人的采访](https://www.36kr.com/p/4034999504721033) |

2027 届一名作者还给出了自己的完整投递分母。从 8 月底到 10 月 16 日，投 97 家，21 家给过面试机会，已面 45 场，两项意向。阿里的交叉二面集中问模型训推 Infra，结果未过。**21/97 是一名候选人在混合岗位中的获面企业比例**，45 是场数，两项意向没有披露岗位。另一位候选人在 11 月 19 日才参加科大讯飞算子一面，称笔试已过约两个月；同一时间截面里的“没有反馈”还可能变化。[97 家原帖](https://www.nowcoder.com/feed/main/detail/72218f6595fc412f82372474d873526e?sourceSSR=post) · [11 月 19 日算子一面](https://www.nowcoder.com/feed/main/detail/018754ed1e144a33a5f0a1616ba45859?sourceSSR=post)

## 面试官怎样检验候选人做过的工作

| 面试 | 岗位实际追问 | 能从题目看到的差异 |
| --- | --- | --- |
| 字节后端 AI Infra、阿里云推理性能优化，同一人 9 月 14 日 | 字节让作者排查 MPI 通信拖慢、解释跨机部署指标，现场实现带过期的缓存。阿里云问 CUDA 算子迁到海光 DCU 的工作量、FlashAttention 及个人算子项目 | 相同的候选人和日期，前者兼顾互联与在线服务，后者深挖异构算子适配。[字节一面](https://www.nowcoder.com/feed/main/detail/a1ce24c561874141abe6ba18a466f982?sourceSSR=post) · [阿里云一面](https://www.nowcoder.com/feed/main/detail/40f786c658f44730876703db3b1504ac?sourceSSR=post) |
| 清微智能高性能二面、科大讯飞算子一面 | 清微要求说明提速来自访存、算力还是减少计算量。讯飞要求区分计算、通信和访存瓶颈，再解释自写 GEMM 的比较基线及换代硬件后的优化 | 只报一次加速比很难覆盖这些追问。两场都要求说清怎么测、同谁比、收益来自什么变化。[清微二面](https://www.nowcoder.com/feed/main/detail/79895ee3bdef411aac31f8cbc6bebf1d?sourceSSR=post) · [讯飞一面](https://www.nowcoder.com/feed/main/detail/018754ed1e144a33a5f0a1616ba45859?sourceSSR=post) |
| 拼多多搜广推大模型、阿里云政企 AI Infra，同一人 | 拼多多从蒸馏深入至 KL 方向和 PPO 截断目标。阿里云限 40 分钟从三道按简历出的题里做两道，再问多轮 RL 的奖励、模拟用户、业务评估和 veRL | 后训练问题既出现在业务算法岗，也出现在服务企业客户、支持 Agentic RL 的工程岗位。岗位名不足以判断考哪一层。[拼多多一面](https://www.nowcoder.com/discuss/906953010406772736?sourceSSR=post) · [阿里云政企一面](https://www.nowcoder.com/discuss/921086976030150656?sourceSSR=post) |
| 科大讯飞飞星、阿里淘天供给智能 | 飞星从本人研究追问奖励函数落地、GRPO 及训练异常，询问更想做后训练还是 Agent。淘天让候选人重新审视实验公平性，解释模型大小、数据量及超参数分别贡献了什么 | 前者关注把研究变成训练信号，后者追问实验能否支撑个人结论。二者都在核查已有项目。[飞星一面](https://www.nowcoder.com/feed/main/detail/7cf04851be3b46c3bb0e4c21e512e52d?sourceSSR=post) · [淘天原始记录](https://onlyar.site/2026/08/11/NLP-Interview-Knowkedge/) |

一位 2027 届作者把近三个月 20 余场后训练与 Agent 面试归纳在同一篇笔记。可作练习的情境包括 SFT 损失下降但业务效果退化、GRPO 组内奖励完全相同，以及离线基准、自动评委与线上指标不一致。作者未分岗位、公司和场次，也说明用了 AI 整理答题思路，无法据此得出某题出现的市场频率。[跨场原帖](https://www.nowcoder.com/feed/main/detail/e4351ac7f6c54337befa9ed94e833c14?sourceSSR=post)

## 实习与往届给出的对照

- **后训练实习能看到真实结果。** 一位 2027 届作者在 2026 年春季参加上海百度文心后训练实习二面，需要描述 GRPO 的不同策略分布并写 Qwen2 的 SFT 训练程序。其蔚来后训练实习走到 HRBP，他因匹配度拒了 offer。2028 届的华为后训练实习候选人则从 6 月等到 10 月底才获面，随后官网进入主管环节。[百度二面](https://www.nowcoder.com/discuss/864605093486682112?sourceSSR=post) · [蔚来 HRBP](https://www.nowcoder.com/discuss/864607523058311168?sourceSSR=post) · [华为实习一面](https://www.nowcoder.com/feed/main/detail/bd8dc3f838c541bfbf8c5689f2fc2bac?sourceSSR=post)
- **上届在基模和业务后训练两端都有录用自报。** 2026 届一名作者列出去深圳做腾讯混元基模后训练的选择；另一名在 2026 年 3 月列出北京京东物流 LLM 后训练 offer。两帖均未给出最终签约，可以用来识别部门与岗位，不足以推断今年人数增减。[混元深圳](https://www.nowcoder.com/feed/main/detail/ad2063d009ae4df6a04efe62623d13a6?sourceSSR=post) · [京东物流北京](https://www.nowcoder.com/feed/main/detail/74c95f2c97c74e0fb87f5a7981b14838?sourceSSR=post)
- **核对原帖能改变岗位归属。** 8 月 22 日百川候选人记下医疗后训练、医院信息系统和排序代码校验，仍在等下一轮。9 月 7 日一个付费专栏把相近场景、相同医院接口和相同校验任务写成阶跃星辰并称已挂。这里保留较早的候选人原帖，未把后一篇算为独立公司面试。百度后训练的热门三面帖也出自主页标为 2020、提供算法求职辅导的账号，未作为 27 届本人样本。[百川较早原帖](https://www.nowcoder.com/feed/main/detail/d209892dc2cf43c6859a776c5e526eca?sourceSSR=post) · [后出的阶跃专栏](https://www.nowcoder.com/discuss/926273007276814336?sourceSSR=post) · [辅导账号主页](https://www.nowcoder.com/users/287626420)

## 样本口径

证据表含 **26 条记录、25 个不同主链接**。本届主样本有 14 条，另有两条本届混合岗位记录，16 条合计对应 11 个候选人标识。其余是同一篇记者采访中的两位本季求职者、6 条实习或实习语境记录、2 条 2026 届对照。候选人按署名或作者主页归并，同一人不同公司的面试仍保留。岗位城市只取候选人明确写出的工作地点，发帖 IP 和学校地址均不作工作地。

个人帖子适合回答“某岗位确实走到了哪一步，问过什么”，公开样本缺少申请人数、面试邀请和书面录用的全量同口径数据。跨方向投递分母、个人多轮面试、实习 offer、意向、转正和正式校招分开记录。文中日期指原帖公开或更新时点，补记的面试日期另列。复核时，25 个主链接中有 24 个通过直接网页请求返回了对应标题，LINUX DO 的原帖、作者回帖和 11 月后续已在网页检索中读到，直接脚本请求会触发站点验证。
