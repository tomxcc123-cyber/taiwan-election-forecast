# HB-TLEF v4.1 Public Beta 2 模型卡

更新日期：2026-09-12

## 1. 发布状态

HB-TLEF v4.1 Public Beta 2 是 2026 台湾县市长选举网站的公开研究版本。该版本可以用于线上研究展示与滚动预测，但**不是 Stable 版本**，也不应将模型胜率解释为已经完成跨届校准的真实概率。

本版正式接管线上 2026 候选人预测核心。相较 v4.0 Public Beta 1，主要新增一项：对强第三方／无党籍竞逐，加入一个极窄的 `Fragmentation Poll Gate`。

## 2. 模型架构

生产链条为：

`Partisan Baseline R4 → selective two-party/compositional center → joint polling likelihood → strong-fragmentation full-field poll gate → Monte Carlo candidate shares`

其中：

- **Partisan Baseline R4**：以历届地方首长蓝绿结构、总统相对倾向、议员组织盘、乡镇市长组织盘与地方派系代理变量构成结构中心。
- **Two-party stack**：在可比蓝绿竞逐中，以 logit 空间 90% R4 + 10% legacy fundamentals 形成蓝绿条件比例。
- **Third-party / non-major mass**：继续使用冻结的 T3 roster-type 模型与上届非主要政党票池混合，并保留 reliability fallback。
- **Joint polling layer**：候选人层民调以候选人匹配后的联合高斯近似进入，不把同源重叠波次当作独立样本。
- **Fragmentation Poll Gate**：仅在已经通过原有资料审计的、完整列出当前候选人的 TVBS 民调中启用；若该波次的非 KMT/DPP 候选人占“已决定具名候选支持”至少 40%，则以该完整民调向量重新居中该县市 posterior draw cloud，同时保留原有 draw shape 与不确定性。

Partial-ballot 民调、其他机构民调、名单不一致民调、低于 40% 的第三方票池均**不会**触发 hard gate，仍走原有联合民调更新。

## 3. 为什么增加 Fragmentation Gate

旧式“先预测蓝绿两党比例，再估计第三方总票池”的方法，在强三方或地方型候选人选举中会出现结构性失败。2022 新竹市是最典型案例：如果仍把高虹安视为普通第三方票池的一部分，模型会错误地保留过强的蓝绿结构约束。

v3 研究 challenger 因此将强第三方竞逐改为“完整候选人民调向量优先”。该方案同时修复了 2022 新竹市与苗栗县的胜者方向。

## 4. 历史验证

### 4.1 可确认的旧核心基准

v4.0 selective RC3 在 2022 的冻结验证为：

- 22 县市全覆盖
- race-balanced MAE：**5.981 个百分点**
- 胜者命中：**14/22（63.6%）**
- margin MAE：**11.277 个百分点**
- Brier：**0.501**

这仍是 v4.1 对外报告时最重要的确认性参考，因为其架构在 2022 诊断前已经冻结。

### 4.2 Fragmentation v3 开发诊断

在加入强第三方完整民调向量规则后，2022 开发诊断结果为：

- 22 县市全覆盖
- candidate MAE：**4.850 个百分点**
- race-balanced MAE：**4.979 个百分点**
- 胜者命中：**16/22（72.7%）**
- margin MAE：**10.437 个百分点**

这一组数值**不是新的确认性 holdout**。hard-fragmentation 架构是在查看更早一版 2022 challenger 的错误后提出，因此只能作为开发证据，不能宣称“未来选举也会达到约 5pp”。

## 5. 苗栗资料修复

2022 苗栗 TVBS 波次曾因字形问题被排除：原始 PDF 使用“謝褔弘”，中选会正式名单使用“謝福弘”。研究验证采用显式、可审计的：

`謝褔弘 → 謝福弘`

映射，并保留 raw name、canonical name 与修复原因。正式原始历史资料文件不被静默重写。

该波次属于敏感性纳入：报告总样本规模足够，但支持度题目的子样本 N 未单列，因此不会被伪装成严格 A 级确认性样本。

## 6. 当前 2026 线上行为

截至本版本冻结时，公开民调资料的最新可用波次仍早于当前基线 cutoff，因此 Fragmentation Gate 可能显示 `triggered_count = 0`。这并不代表功能没有上线，而是意味着当前没有符合全部触发条件的新波次。

未来自动抓取到新的合格完整 TVBS 候选人调查后，系统会按冻结阈值自动判断，不允许为了某一县市临时修改 40% 阈值。

## 7. 不确定性与限制

1. 胜选概率尚未完成多届独立选举的概率校准。
2. Fragmentation v3 的 2022 改善属于开发诊断，而非架构盲确认性 holdout。
3. 2009/2010 历史资料虽已人工交叉核对，但原始工作簿 hash 验证仍未完全补齐。
4. hard gate 目前只外推到已审计、完整候选名单的 TVBS 波次，不自动推广到其他机构。
5. 地方派系、背书与组织网络主要以可观察代理变量表示，不等同于因果效果估计。
6. 当前候选人登记状态仍可能随资格审定、退选或政党提名变化而更新。

## 8. 发布治理

本版本的规则是：

- 版本号、生成时间、资料 hash 与候选名单版本必须公开；
- 线上民调只能经既有审计 pipeline 接入；
- 不得针对 2022 或某一县市继续手工调参；
- Fragmentation Gate 的 40% 阈值冻结；
- 开发验证与确认性验证必须分开展示；
- 在新的独立周期证据出现前，不得标记为 Stable。

## 9. 版本

模型 ID：`HB-TLEF-v4.1-public-beta.2`

正式上线日期：2026-09-12
