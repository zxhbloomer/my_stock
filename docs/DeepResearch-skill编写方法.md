# DeepResearch 类 Skill 编写方法

## 1. 文档目标

本文用于说明：如何参考 MiroThinker 一类 AI 搜索工程的方法，把一个“会搜”的 prompt，设计成一个“可审计、可复用、可验证”的 Deep Research 类 skill。

目标不是让 skill 只会输出长报告，而是让它在执行搜索任务时，具备以下能力：
- 事实可核查
- 搜索广度可保证
- 信源可交叉验证
- 冲突证据可显式处理
- 结论能指导下一步行动

本文同时结合了对现有 `deep-research` skill 的增强实践，避免理论和实际落地脱节。

## 2. 先明确：Deep Research Skill 不是什么

Deep Research 类 skill 不是：
- 一组更长的搜索提示词
- 一个只会堆链接的“资料汇总器”
- 一个只擅长写漂亮报告的总结器
- 一个只靠模型主观判断“应该已经搜够了”的自动化脚本

如果 skill 只有“多搜几轮”和“多写几段”，但没有覆盖面约束、来源独立性约束和验证门禁，那么它本质上仍然只是搜索 prompt，不是研究型工程资产。

## 3. Deep Research Skill 的分层设计

参考 MiroThinker 一类搜索工程时，最重要的不是照搬具体实现，而是抽出其分层思想。

建议把 Deep Research 类 skill 设计成四层：

### 3.1 任务定义层

负责回答：
- 研究对象是什么
- 要回答什么问题
- 不回答什么问题
- 时间范围是什么
- 成功标准是什么

这层决定后续搜索深度和范围。

如果对象、时间范围、比较维度会改变方案选择，就应最小澄清；否则把不确定点写入“假设（待确认）”。

### 3.2 搜索执行层

负责回答：
- 应该搜哪些关键词
- 应该覆盖哪些子问题
- 是否需要找反向证据
- 是否需要拉时间基线
- 是否需要并行探索

这层不应只有 query matrix，还必须有 coverage matrix。

### 3.3 证据治理层

负责回答：
- 每条关键结论有哪些支持来源
- 这些来源是否彼此独立
- 是否存在冲突来源
- 哪些是事实，哪些是推断
- 哪些结论证据不足

这层至少需要：
- source rubric
- claim ledger
- independence_group 规则
- 冲突证据记录规范

### 3.4 输出验证层

负责回答：
- 结论是否能回链到来源
- 高影响结论是否满足独立来源要求
- 是否遗漏了重要 coverage gap
- 是否把转载当成独立来源
- 是否把聚合页当成核心证据

这层至少需要一个最小 gate，而不是只靠人工阅读报告。

## 4. 参考 MiroThinker 时，真正值得借鉴的东西

MiroThinker 一类 AI 搜索工程真正值得借鉴的，不是品牌名或某个特定 UI，而是以下几个工程思想。

### 4.1 把搜索当成迭代式研究，不是一次性检索

搜索不是“搜一次 -> 总结一次”。

更合理的循环应是：
- 形成初始问题分解
- 执行一轮搜索
- 基于证据发现缺口和冲突
- 修正下一轮搜索方向
- 直到 coverage 达标或证据边际收益明显下降

这意味着 skill 设计里要显式写出：
- 主问题
- 子问题
- 反向验证问题
- 时间敏感问题
- 高影响结论点

### 4.2 把过程可观测性当成一等公民

好的搜索类 skill 不应该只留下最终报告，还应尽量留下：
- 查询词
- 命中的 coverage cell
- 放弃的方向
- 为什么放弃
- 为什么认为可以停止

如果没有这些过程信息，团队很难复盘“是没搜到，还是搜到了但没纳入”。

### 4.3 把来源独立性显式结构化

“两个来源”不等于“两条独立证据”。

如果两篇报道都在转述同一份官方公告，它们只能算一个证据簇，不应算两个独立支持来源。

因此应为来源定义规则化的 `independence_group`，例如：
- `official:openai`
- `media:reuters`
- `paper:arxiv-xxxx`
- `aggregator:example`

### 4.4 把“停止搜索”定义成门禁，而不是感觉

搜索类 skill 常见失败模式之一，就是“觉得差不多了”。

更稳的做法是定义停止条件，例如：
- coverage 已达标
- 未达标项已被记录为证据缺口
- 新查询主要重复命中已有 coverage cell
- 高影响结论已满足独立来源要求

## 5. 搜索类 Skill 必须补上的三个关键契约

结合本次对 `deep-research` skill 的实际增强，Deep Research 类 skill 至少要补齐下面三类契约。

### 5.1 Coverage Contract

这是保证搜索广度的核心契约。

不能只规定“怎么搜”，还要规定“哪些面必须被覆盖”。

建议最小 coverage matrix 至少包含：
- `subtopic`
- `source_type`
- `stance`
- `time_window`
- `entity_scope`

说明：
- `subtopic`：是否覆盖主问题拆出的所有关键子问题
- `source_type`：是否覆盖官方、一手、二手、社区线索
- `stance`：是否覆盖支持、反向、不确定证据
- `time_window`：是否覆盖当前窗口和必要历史基线
- `entity_scope`：比较对象或关键主体是否都覆盖

没有 coverage contract，搜索广度就只能靠经验，无法稳定复现。

### 5.2 Independence Contract

这是保证“交叉验证不是假交叉验证”的核心契约。

至少应明确：
- 什么叫独立来源
- 什么叫同源转载
- 聚合页是否可单独支撑结论
- 高影响结论最低需要多少独立来源组

推荐规则：
- 同一官方公告的多篇转述，不算多个独立来源
- 同一研究报告的多篇解读，不算多个独立来源
- 同一媒体集团重复转载，不默认算独立
- 聚合页只能提供线索，不能单独支撑 `supported`

### 5.3 Verification Gate Contract

这是保证 skill 不会“写得像真研究，但其实不可审计”的核心契约。

最小 gate 至少应检查：
- 结论是否可回链到 `References`
- 是否存在统一章节结构
- 是否出现 coverage 检查
- 是否出现来源独立性说明
- 高影响结论是否含至少一个 official 支持来源
- 高影响结论是否跨独立来源组
- 是否缺规范化主日期 `date`
- 是否把聚合页或纯二手来源当作高影响结论支撑

## 6. 结构化资产建议

一个可维护的 Deep Research 类 skill，建议至少有以下资产。

### 6.1 SKILL.md

只保留核心流程和刚性规则，避免冗长背景介绍。

建议写入：
- 触发条件
- 阶段化流程
- coverage / independence / gate 规则
- 并行探索启用条件
- 输出结构
- 失败与降级策略

### 6.2 report-template.md

用于约束最终研究报告最小结构。

推荐结构：
1. 结论
2. 事实
3. 假设（待确认）
4. 研究范围与方法
5. 覆盖面检查
6. 关键依据
7. 来源独立性说明
8. 分析
9. 冲突证据与解释
10. 风险与边界
11. 可执行建议
12. References
13. 研究日志

说明：
- Lite 任务可简写，但建议保留统一骨架
- Research / Research-Parallel 默认输出研究日志

### 6.3 source-rubric.md

用于定义来源分级、独立性判断和高风险结论约束。

至少包含：
- 一级 / 二级 / 三级来源定义
- authority / freshness / specificity / verifiability / conflict_risk / independence
- 常见误判
- 高影响结论最低要求

### 6.4 claim-ledger-schema.md

用于把“结论 -> 来源 -> 支持 / 反驳”结构化，而不是只在自然语言中隐含存在。

建议来源字段至少包含：
- `title`
- `url`
- `publisher`
- `original_url`
- `derived_from`
- `independence_group`
- `evidence_role`
- `source_type`
- `date`
- `published_at`
- `updated_at`
- `claim`
- `relation`
- `confidence`
- `notes`

### 6.5 verify_report.py

用于做最小自动校验，不追求完全审计，但至少能拦住明显错误。

应优先拦截：
- 假引用编号
- 缺失关键章节
- 缺来源独立性说明
- 缺 coverage 检查
- 高影响结论无 official 支持源
- 高影响结论独立来源组不足
- 缺规范化主日期 `date`
- 只靠 aggregator 得出 `supported`

## 7. 并行搜索如何设计才不空转

Deep Research 类 skill 不应为了“多代理”而多代理。

并行启用的前提应是：
- 搜索范围足够大
- 子问题可拆分
- 汇总成本小于并行收益
- 主代理能定义统一输出契约

### 7.1 推荐拆分优先级

优先按 coverage 空白格拆分，而不是默认按来源类型平分。

推荐顺序：
- 先按 `subtopic / entity_scope / time_window / stance` 中最缺覆盖的维度拆
- 只有在主要矛盾是来源可信度冲突时，才按“官方 / 二手 / 反向证据”拆

### 7.2 不要犯的错误

- 三个子代理搜的是同一个主题，只是站点不同
- 三个子代理都在搜支持证据，没人查反例
- 明明核心依赖一条连续证据链，却强行并行
- 子代理直接产出最终答案，主代理只做拼接

正确做法应是：
- 子代理只负责局部证据发现和 coverage 补齐
- 主代理负责去重、统一日期、冲突解释和最终结论

## 8. Deep Research 类 Skill 的最小验收标准

一个搜索类 skill 至少应达到以下标准，才值得在团队里复用。

### 8.1 事实可核查

- 每条关键结论都能回链到具体来源
- 至少能从 `References` 和 `关键依据` 复盘结论出处

### 8.2 广度可解释

- 能说明覆盖了哪些子问题和来源类型
- 能说明还没覆盖哪些面，以及为什么停止

### 8.3 独立性可说明

- 能说明支持来源是否独立
- 能说明是否存在同源转载

### 8.4 冲突可解释

- 冲突来源不会被静默删除
- 冲突会进入“冲突证据与解释”段落

### 8.5 证据不足时不强行下结论

- 会明确写“暂不能确认”
- 会列出缺失证据和下一步补查方向

## 9. 本次 `deep-research` skill 增强实践的启示

这次对现有 `deep-research` skill 的增强，验证了一个很实际的结论：

如果没有工程约束，Deep Research skill 很容易变成“写作型 skill”；
只有把 coverage、independence、gate 一起补齐，它才会逐渐变成“研究型 skill”。

本次实践中补强的重点包括：
- 引入 coverage matrix 和停止条件
- 引入规则化 `independence_group`
- 强化 claim ledger schema
- 强化 verify_report gate
- 要求高影响结论至少有一个 official 支持源
- 要求高影响结论跨独立来源组
- 要求结论引用可真实回链

这些改动的价值，不在于“让报告更好看”，而在于：
- 让失败模式更早暴露
- 让研究过程更可复盘
- 让团队更容易迭代 skill 本身

## 10. 编写 Deep Research 类 Skill 的推荐顺序

建议按以下顺序落地：

1. 明确目标问题与使用场景
2. 设计统一报告骨架
3. 设计 source rubric
4. 设计 claim ledger schema
5. 加入 coverage contract
6. 加入 independence contract
7. 加入 verification gate
8. 最后再考虑并行探索和高级自动化

不要一开始就追求：
- 全自动多代理
- 超复杂 trace 系统
- 巨量扩展字段
- 过重的 orchestrator

先把最小闭环做稳，再迭代增强。

## 11. 推荐写法总结

如果要用一句话概括 Deep Research 类 skill 的编写方法，可以写成：

> 把“搜索”设计成一个有覆盖面约束、有独立来源约束、有结论台账、有最小门禁的研究流程，而不是一段更长的搜索 prompt。

真正稳定可复用的搜索类 skill，依赖的不是模型“更聪明”，而是：
- 规则更清楚
- 过程更可追溯
- 证据结构更稳定
- 输出更可审计

## 12. 可直接复用的检查清单

在发布一个 Deep Research 类 skill 前，至少自查：

- 是否定义了任务对象、时间范围和成功标准
- 是否同时设计了 query matrix 和 coverage matrix
- 是否明确定义独立来源判定
- 是否能区分官方、二手、聚合、反向证据
- 是否有 claim ledger 结构
- 是否有冲突证据记录位置
- 是否有最小自动 gate
- 是否能处理“证据不足”而不是强行给结论
- 是否保留了研究日志或等价过程信息
- 是否明确写了停止搜索的条件

满足这些条件后，这个 skill 才更像“可复用研究工程”，而不是“长 prompt 模板”。

## 13. 外部资料补充：MiroThinker / MiroFlow 与其它 Deep Research 实践

本节补充一手资料与可借鉴点，重点不是做产品罗列，而是说明这些外部实践分别能反哺 skill 的哪一层设计。

以下资料核验时间为 **2026 年 5 月 12 日**。

### 13.1 MiroThinker：把“交互深度”视为独立的能力扩展轴

MiroThinker 官网和论文最值得借鉴的，不是某个具体模型参数，而是它明确提出：除了参数规模和上下文长度之外，**交互深度（interactive scaling）** 也是研究型 agent 的重要扩展轴。

可核查信息：
- 官网将 MiroThinker定义为“search-centric research agent”，强调“形成假设、检索证据、根据新证据迭代修正、直到收敛”的研究循环。
- 官网还明确把 MiroFlow 定义为“用于运行、评测、复现实验并提供 observability 的编排框架”。
- MiroThinker 论文将这种思路概括为：模型在更深、更频繁的 agent-environment 交互中，研究性能会持续改善。

可直接转化为 skill 设计的要点：
- 不把搜索视为单次 retrieval，而要设计“假设 -> 搜索 -> 修正 -> 再搜索”的循环。
- 在 `SKILL.md` 中显式写出“反向验证问题”“高影响结论点”“停止条件”。
- 把 coverage gap 视为驱动下一轮搜索的主要信号，而不是只依赖关键词扩展。

### 13.2 MiroFlow：把“可复现”和“可观测”当作框架能力

MiroFlow 论文强调的问题非常贴近 skill 工程：
- 许多 agent framework 存在 naive workflow、稳定性不足、跨 benchmark 泛化有限、强依赖昂贵闭源 API 等问题。
- MiroFlow 的回应是：用 agent graph 做更灵活的 orchestration，并把 robust workflow execution、stable and reproducible performance 作为目标。

对 skill 编写最有价值的启示：
- 研究类 skill 不应只有“输出模板”，还应考虑“同一流程是否可复跑、可比较、可定位失败点”。
- 即使不做完整 agent graph，也应至少留下：
  - 查询日志
  - coverage summary
  - claim ledger
  - stop reason
- 如果未来要扩展到多代理，主代理和子代理之间必须有稳定输出契约，而不是自由文本拼接。

### 13.3 MiroThinker-H1：把 verification 前移到推理过程中

MiroThinker-H1 论文的核心补充是：**verification 不应只发生在最终答案阶段**，还可以进入中间推理与整体轨迹审计。

可核查信息：
- 论文明确写到，它把 verification 融入了 local 和 global 两层：
  - 局部推理步骤可被评估和修正
  - 整体轨迹可被审计，以确保最终答案有一致的证据链支撑

这对搜索类 skill 的直接启示是：
- 不要把验证只放在“报告写完后的最后一步”
- 在搜索阶段就应做中途检查，例如：
  - 这条线索是否只是聚合转述
  - 这个 claim 是否已出现独立来源
  - 这个方向是否仍值得继续投入搜索轮次
- 如果未来继续增强 skill，可以考虑在 `verify_report.py` 之外，再增加更细粒度的“中途 tripwire”

### 13.4 OpenAI Deep Research：把“来源控制 + 研究计划 + 进度可视化”做成产品一等能力

OpenAI 的 deep research 官方资料虽然是产品文档，但其中几个设计点很值得参考：
- 用户先描述目标，再选择可用来源
- 系统会先生成 proposed research plan，允许用户在研究开始前修改
- 研究过程中可查看进度，也可以中途打断并调整方向
- 输出是带 citation 的结构化报告

这些设计可直接映射到 skill：
- 用户输入不应只是“问题”，还应包含“目标产物与来源范围”
- 搜索前最好有一个显式的 plan 阶段
- 允许在研究过程中重定向，而不是只能“一次启动跑到底”
- 结果文档必须天然带 citation 和验证入口

进一步可借鉴的工程点：
- OpenAI 官方还把 deep research 的限制写得很明确，例如 hallucination、权威性判断不足、置信度校准问题
- 这提醒我们：skill 文档中必须保留“风险与边界”以及“证据不足”的写法，不能只写成功路径

### 13.5 OpenAI Evals / Guardrails：把质量与边界条件工程化

如果要找“如何把研究型 skill 做成可持续迭代资产”的官方工程实践，OpenAI 的 evals 与 guardrails 文档很值得参考。

可核查信息：
- OpenAI 明确建议：对 agent workflow，要使用 traces、graders、datasets、eval runs 来持续发现回归和 failure modes。
- 官方还明确区分：
  - input guardrails
  - output guardrails
  - tool guardrails
- 并强调多代理系统不应先天上复杂化，是否拆成 multi-agent 应由 evals 驱动。

对 skill 编写的启示：
- 不要只做最终输出 gate，还应考虑输入边界、工具调用边界和输出边界。
- `verify_report.py` 只是最小起点，长期应演化为：
  - report gate
  - ledger gate
  - trace gate
- 多代理不是默认答案，应先用 evals 证明单代理已成为瓶颈，再引入多代理复杂度。

### 13.6 Gemini Deep Research：把“来源选择”和“可编辑研究计划”前置

Google Gemini Deep Research 的官方帮助文档有两个设计点尤其值得吸收：
- 默认带 Google Search，但允许用户显式增删来源，甚至限制为特定来源集
- 在真正开始 research 之前，系统会先生成 research plan，并允许用户修改

这对 Deep Research skill 的启发很直接：
- 可在 skill intake 阶段加入“来源边界确认”
- coverage matrix 不应只覆盖主题，还应覆盖来源域
- 在高风险场景下，可以主动要求“trusted sites only”或“只使用给定来源集”

## 14. 如何把这些外部实践转写成 Skill 条目

外部资料最容易出的问题，是“看起来很先进，但无法落到本地 skill 文件”。因此建议按下面方式转写。

### 14.1 来自 MiroThinker 的内容，优先写进 `SKILL.md`

适合写进主流程的内容：
- 交互式研究循环
- coverage 驱动的下一轮搜索
- 反向验证问题
- 停止条件

不建议直接抄进 `SKILL.md` 的内容：
- 大量 benchmark 数字
- 模型参数细节
- 与具体发布版本强绑定的实现描述

原则：
- 保留方法，不绑定某个模型版本

### 14.2 来自 MiroFlow 的内容，优先写进 `workflow.md` 或未来 trace 资产

适合下沉到参考件的内容：
- orchestration 结构
- reproducibility 要求
- observability 维度
- 失败后如何复盘

原则：
- 把“框架能力”翻译成“流程约束”和“输出契约”

### 14.3 来自 OpenAI Evals / Guardrails 的内容，优先转化为 gate

适合写进脚本或规则的内容：
- 哪些检查应在输入前做
- 哪些检查应在工具调用前后做
- 哪些检查应在最终输出后做
- 哪些错误应 fail，哪些只 warn

原则：
- 尽量把“最佳实践”转成可执行校验，而不是说明性段落

### 14.4 来自 Gemini / OpenAI Deep Research 产品的内容，优先转化为交互设计

适合写进 skill 入口或模板的内容：
- 研究计划可编辑
- 来源范围可配置
- 运行过程可打断
- 报告生成后带 citation 和结构化输出

原则：
- 借鉴交互与约束，不照搬产品功能表

## 15. 建议继续收集的资料类型

如果后续还要继续强化这篇方法文档，优先继续补以下类型的一手资料：
- 开源 research agent 的技术报告与框架论文
- 官方 agent eval / guardrail / trace 文档
- 官方 deep research 产品文档中的限制条件与 source control 设计
- 真实社区 issue 中暴露出的失败模式，而不是只看宣传帖

推荐优先方向：
- 更系统的 agent observability / telemetry 资料
- 更明确的 search stopping / verification 论文
- 更具体的 source trust / citation quality 评测方法

## 16. 参考资料

以下为本次补充中直接参考的一手资料：

- MiroThinker 官网  
  https://mirothinker.io/
- MiroThinker 论文：*MiroThinker: Pushing the Performance Boundaries of Open-Source Research Agents via Model, Context, and Interactive Scaling*  
  https://arxiv.org/abs/2511.11793
- MiroFlow 论文：*MiroFlow: Towards High-Performance and Robust Open-Source Agent Framework for General Deep Research Tasks*  
  https://arxiv.org/abs/2602.22808
- MiroThinker-H1 论文：*MiroThinker-1.7 & H1: Towards Heavy-Duty Research Agents via Verification*  
  https://arxiv.org/abs/2603.15726
- OpenAI deep research 官方介绍  
  https://openai.com/index/introducing-deep-research/
- OpenAI agent evals 官方文档  
  https://developers.openai.com/api/docs/guides/agent-evals
- OpenAI Agents SDK guardrails 官方文档  
  https://openai.github.io/openai-agents-python/guardrails/
- Gemini Deep Research 官方帮助文档  
  https://support.google.com/gemini/answer/15719111
- AgentTrace 论文：*AgentTrace: A Structured Logging Framework for Agent System Observability*  
  https://arxiv.org/abs/2602.10133
