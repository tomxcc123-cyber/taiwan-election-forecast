# HB-TLEF v5.0 Public Beta 1

版本：`2026.09-HB-TLEF-v5.0-public-beta.1`

状态：**Public Beta / Research Preview**，不是 Stable，也不是官方预测。

## 1. 这一版改变了什么

v5.0 不再沿用 v4.1 的“结构模型通过 reliability gate 后才接管，否则退回另一套 candidate fundamentals”的双中心结构。新的 2026 pre-poll prior 统一为：

`R4 结构基本盘 -> Candidate residual offset -> T3 非蓝绿票池 -> 非蓝绿候选人内部配置 -> 联合民调 likelihood -> 强碎片化完整名单民调 gate`

其中：

- R4 继续负责 KMT-DPP 的结构性县市基本盘；
- 候选人历史只学习 R4 未解释的 logit residual，并以 ridge 强收缩后直接写回同一个 prior；
- T3 独立预测第三党／无党籍总票池，避免地方选举被强迫归一成蓝绿两党竞争；
- legacy candidate fundamentals 只在非蓝绿票池内部决定分配，不再作为另一套中心与 R4 互相切换；
- 当前民调仍然只在 prior 之后进入 likelihood，不进入结构标签；
- 强第三方／无党籍竞争继续使用 v4.1 已冻结的完整名单 TVBS fragmentation gate。

## 2. 候选人 residual offset

候选人层采用四个历史信号：

1. `repeat_candidate_signal`
2. `prior_winner_signal`
3. `previous_candidate_share_signal`
4. `previous_party_pool_signal`

候选人层不是直接重新拟合结构基本盘，而是学习：

`logit(实际蓝绿条件票) - logit(R4 结构预测)`

因此它只能解释 R4 留下的 residual，而不能把结构层重新训练掉。

特征范围仅用 2018 开发周期选择；`O4_party_pool` 被选中后冻结，再用于 2022 评分。

2018：

- R4 MAE：7.357pp
- Candidate residual offset：7.210pp

2022：

- R4 MAE：5.909pp
- Candidate residual offset：4.847pp
- 高可靠样本：5.547pp -> 4.236pp
- 蓝绿条件票赢家判断：15/19 -> 16/19

需要强调：虽然 v5.2 的特征范围没有用 2022 选择，但整个项目在更早开发阶段已经查看过 2022，因此不能把它宣传为“项目层面的全新盲测”。

## 3. 完整候选人层回测

在相同的第三方票池与 fragmentation 机制下，2022 开发诊断为：

| 指标 | v4.1 对应开发架构 | v5.0 integrated | 变化 |
| --- | ---: | ---: | ---: |
| Candidate MAE | 4.850pp | **4.625pp** | -0.225pp |
| Race-balanced MAE | 4.979pp | **4.597pp** | -0.382pp |
| 赢家判断 | 16/22 | **17/22** | +1 |
| Winner accuracy | 72.7% | **77.3%** | +4.6pp |
| Margin MAE | 10.437pp | **9.637pp** | -0.800pp |

这组数字属于 **development diagnostic**，不是 pristine confirmatory holdout。原因不是 candidate offset 本身，而是 fragmentation 架构曾在检查较早 2022 误差后形成。

保留的确认性参考仍为更早冻结的 v4.0 RC3：2022 race-balanced MAE 5.981pp，赢家 14/22。

## 4. 为什么没有把 turnout 强行放进去

v5.0 早期实验曾把候选人变量、R4 与 lagged turnout 一起放入统一 ridge。该版本在 2022 出现异常大的改善，但后续发现 `turnout_available` 与选举周期高度重合，存在把“资料可得性／年代”编码进模型的风险。

移除 availability proxy，并把 turnout 改成相对同轮平均投票率后，2022 MAE 改善只剩约 0.02pp，且没有更早独立周期可证明效果稳定。因此正式 v5.0：

- **不把 aggregate turnout 放入得票中心**；
- 不把县市总投票率解释为 KMT/DPP 动员率；
- turnout 未来只能在有更长历史或更细粒度资料后作为独立 Turnout Model 再验证。

## 5. 第三方与地方派系

T3 继续使用上一轮非主要政党票、议员独立票、乡镇市长独立票、乡镇资料可得性、地方派系倾向、候选人名单类型等变量预测 non-major mass。

v5 与 v4 的差异在于：只要存在唯一一名 DPP 与 KMT 候选人，T3 的票池就直接进入统一 composition，不再因为另一个 reliability fallback 而被整套 candidate fundamentals 覆盖。

因此澎湖等地方派系／无党籍占比长期较高的县市，在 v5 中会出现比 v4.1 更明显的结构性重定价。这不是人工县市调参，而是 non-major mass 真正进入 prior 的结果。

## 6. Fragmentation Gate

规则保持 v4.1 冻结值，不因 v5 调参：

- 只看已经通过现有民调审计的完整名单 TVBS 波次；
- 非 KMT/DPP 决定票占比 >= 40% 时触发；
- 触发后用完整候选人 poll vector 在 CLR 空间重定 posterior draw cloud；
- partial ballot、名册不匹配或其他 pollster 不做 hard override，继续使用一般 joint polling likelihood。

这个 gate 的 2022 改善属于开发证据，不是新的 blind holdout。

## 7. 2026 production-isomorphic shadow

使用与线上 v4.1 完全相同的 `data/polls.json` 截面（2026-09-12T04:35:30Z）和 2000 次联合模拟测试：

- v4.1 与 v5 shadow 当时都没有新的 strong-fragmentation trigger；
- 22 县市只有 1 个均值得票首位者翻转：高雄市由柯志恩转为赖瑞隆；
- 最大单一候选人均值得票重定价约 11.254pp，出现在澎湖，主要来自恢复高 non-major mass；
- 桃园、基隆、台南、台北、云林等出现约 2–5pp 的实质变化；
- 原本结构一致性较高的县市多数只移动约 0–1pp。

这些变化用于验证生产行为是否符合架构预期，不作为模型准确度证据。

## 8. 数据链条

当前可审计候选人历史链条为：

`2009/2010 -> 2014 -> 2018 -> 2022 -> 2026 roster`

2006 原始县市长资料目前没有进入仓库中的可审计数据层，因此本版本**不宣称已经直接融合 2006**。

2014/2018/2022 使用已核对的中选会资料；2009/2010 仍存在原始工作簿 hash 尚未完成的限制。

2026 地方组织变量目前继续使用公开标示的 2022 organization bridge。

## 9. 概率解释

页面中的胜率来自联合 Monte Carlo candidate-share simulation。它表示在当前模型、名单、结构 prior、民调与误差假设下的条件概率，不是“真实概率”的直接观测。

本版本仍未完成跨多个独立选举周期的概率校准，因此：

- 可以展示胜率；
- 必须保留 Public Beta / 未校准提示；
- 不得称为 Stable；
- 不应把 60% 与 40% 解释为已经经过长期频率校准的真实事件概率。

## 10. 当前发布结论

v5.0 满足进入 Public Beta 的工程与开发验证条件，但仍不满足 Stable 条件。

Stable 至少仍需要：新的架构盲时间 holdout（最好是未来 2026 实际结果或更早可完整重建周期）、跨届胜率校准、2006/更早历史资料的可审计补齐，以及 2026 议员／乡镇组织特征不再依赖 bridge。
