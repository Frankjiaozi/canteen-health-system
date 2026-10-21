# 前端说明性文案清理清单（临时）

> 2026-10-19：本文的 P0 已按清单清理完成；以下行号保留为清理前定位，便于回溯。
> 追加：一天三餐的采购口径说明条与“按餐次分别校验……”小字也已删除。

> 审查范围：`apps/web/src/features`、`apps/web/src/shared`、`apps/web/src/layouts` 中实际渲染到页面的文字，
> 以及由后端返回、前端直接展示的说明字段。  
> 不包含：代码注释、表单校验错误、接口报错原文、按钮/字段标签、表格列名。  
> 本文只做定位，不改代码。

覆盖页面：登录/注册、数据看板、食材库、菜品与配方、调味料库、每日采集、抽样纠偏、
明日菜单与采购、知味膳食助手、公开大屏、节假日日历，以及全局离线/更新/权限提示。

## 结论

- **P0 建议直接删除**：解释系统怎么运作、功能验证/待核实声明、AI 味的操作说明。用户截图中的四处都在这一类。
- **P1 建议压缩或移入帮助提示**：仍有信息价值，但不适合作为页面正文小字。
- **P2 建议保留**：合规声明、权限/错误提示、确认弹窗、空状态和数据来源标签；这些不是“AI 味”。

---

## 一、用户截图直接命中的文案（优先处理）

### 1. 一天三餐顶部说明

- `apps/web/src/features/menuplan/components/DailyPlanView.tsx:38-43` — **P0 删除**
  - 标题：`早餐、午餐、晚餐一次生成，采购单已合并`
  - 描述：`plan.notes` 拼接出的“早餐固定组合；午餐先排……采购单已把相同食材和调味料合并……同步时按餐次分别校验……”
  - 问题：解释系统内部流程，不是使用者需要读的页面说明。

### 2. 能量目标待核实 / 适用范围

- `apps/web/src/features/menuplan/components/RecommendedDishes.tsx:85-92` — **P0 删除**
  - 标题：`能量目标尚未核实`
  - 描述来自 `apps/api/app/modules/recommendation/targets.py:147`：
    `全天能量目标为待核验参考值，待核实：需以《学生餐营养指南》等标准原文替换`
- `apps/web/src/features/agent/components/ResultPanel.tsx:275-277` — **P0 删除**
  - 展示 `target_basis.scope_notice`，原文在 `apps/api/app/modules/recommendation/targets.py:157`：
    `当前能量与供能比例用于功能验证，尚未按服务人群完成标准适配。WS/T 554—2017 适用于6–17岁中小学生，不能直接用于认证大学食堂方案。`
  - 问题：两段都是产品内部的标准适配说明，像开发备注，不像上线产品文案。

### 3. 每日采集的计划供应提示

- `apps/api/app/modules/collection/service.py:100-101`，前端在 `apps/web/src/features/collection/components/DailyLogForm.tsx:124-127` 展示 — **P0 删除或改成短提示**
  - 原文：`这份菜单是「明日菜单与采购」排好的计划：标了「计划」的菜已经勾上，按实际供应核对——临时加了菜就顺手勾上，没做的取消勾选，保存即按实际覆盖。`
  - 问题：整段在解释两个页面怎么联动。页面已有“计划”标签和勾选框，不需要再讲一遍。

---

## 二、数据看板

- `apps/web/src/features/dashboard/pages/DashboardPage.tsx:46-51` — **P1 删除或只保留入口按钮**
  - `从今天的数据，到明天的一餐`
  - `对话安排菜单与采购，核查近期供应记录。每一版方案保留依据，由你确认。`
  - 问题：营销式开场，把看板变成了产品介绍页。
- `apps/web/src/features/dashboard/pages/DashboardPage.tsx:135-141` — **P1 删除**
  - `注：这里统计的是当餐全部就餐人次的总量，与「每人每日」的基准不是同一量纲，因此不在此图直接画目标线；达标判断以右侧「人均摄入与推荐值」为准。`
  - 问题：图表口径解释，适合帮助提示，不适合常驻小字。
- `apps/web/src/features/dashboard/pages/DashboardPage.tsx:152` — **P1 删除**
  - 直接展示 `perCapita.data.basis_note`，原文在 `apps/api/app/modules/analytics/service.py:56-60`：
    `人均营养摄入取每道菜当日证据最强的一份……食盐、烹调油与添加糖的对照基于当日实际投料量除以就餐人次。两者来源不同，不宜混读……`
  - 问题：长段数据口径说明占据“人均摄入与推荐值”卡片顶部。

---

## 三、每日采集

- `apps/web/src/features/collection/pages/DailyLogPage.tsx:40-43` — **P1 删除**
  - `每天只需要填几个数字：勾出今天供应的菜、份数、人次、油盐糖实际用量、剩餐。保存后当餐营养立即重算，公开大屏随即可见。`
  - 问题：操作教学文案。
- `apps/web/src/features/collection/components/DailyLogForm.tsx:113-115` — **P1 删除**
  - `油、盐、糖是校准模型的关键输入，按当日实际投放量填到克；其余靠配方推导。`
  - 问题：解释算法输入。
- `apps/web/src/features/collection/components/DailyLogForm.tsx:121` — **P1 删除**
  - `勾选即写入当天菜单日`
  - 问题：解释数据落点；勾选框本身已经表达动作。
- `apps/web/src/features/collection/components/DailyLogForm.tsx:256` — **P1 删除或移入字段提示**
  - `标了异常的日子不参与预测的历史序列`
  - 问题：解释预测模型。
- `apps/web/src/features/collection/components/DailyLogForm.tsx:283-285` — **P0 删除**
  - `（由校准校验写入，把用量改对之后重跑校准会自动撤掉）`
  - 问题：明显的内部实现说明。
- `apps/web/src/features/collection/components/DailyLogForm.tsx:306-308` — **P1 删除或压缩为“只读账号”**
  - `学校管理方是只读的观察者，采集由食堂录入员或管理员填写。`
- `apps/web/src/features/collection/components/PendingQueue.tsx:70` — **P1 压缩**
  - `多半是数据本身被服务端拒绝了。切到对应日期核对并重新保存，或放弃这条记录。`
  - 建议只保留动作：`请核对对应日期并重新保存，或放弃这条记录。`
- `apps/web/src/features/collection/pages/DailyLogPage.tsx:52` — **P1 压缩**
  - `请确认后端服务可用，或换一个日期再试。`
  - 问题：把“后端服务”这种开发术语暴露给使用者。

---

## 四、抽样纠偏

- `apps/web/src/features/calibration/pages/SamplingPage.tsx:55-61` — **P1 删除**
  - `每周挑三到五道菜称重实测。实测只修正**调味料的贡献**，食材部分来自配方、保持不变；三个值（理论 / 校准 / 实测）并存，便于对照与回溯。当前已有 N 道菜记过实测，最近一次修正见下表。`
  - 问题：算法说明 + 周操作建议。
- `apps/web/src/features/calibration/components/SampleDrawer.tsx:87-93` — **P0 删除或压成一句**
  - `食材按配方称重是可信的，差额全部归给调味料`
  - `系统用「(实测能量 − 食材能量) ÷ 配方调味料能量」反推调味料该乘多少。实测值与推算值差距过大时不会硬套系数，只留证据并提示核对配方。`
  - 问题：公式和内部策略直接展示在录入抽屉里。
- `apps/web/src/features/calibration/components/SampleDrawer.tsx:157` — **P1 删除或移入帮助**
  - `称的是哪一道菜就改哪一道；同一类做法普遍偏，才选整类烹饪方式`

---

## 五、食材库

- `apps/web/src/features/ingredient/components/IngredientFormDrawer.tsx:144-146` — **P1 删除或移入字段提示**
  - `营养成分按每 100 克可食部填写；成分表里缺项的留空即可，不要填 0。`
- `apps/web/src/features/ingredient/components/IngredientFormDrawer.tsx:180` — **P1 删除或压缩**
  - `任何营养数据都要能点开看到来源，这一条是硬性要求`
  - 建议只保留字段要求：`请填写可核对的来源`。
- `apps/web/src/features/ingredient/pages/IngredientListPage.tsx:116` — **P2 保留**
  - `历史营养结果会保留，但新配方不能再选它。`
  - 这是停用确认的必要说明，不建议删。

---

## 六、菜品、配方与调味料

- `apps/web/src/features/dish/components/DishFormDrawer.tsx:268-271` — **P1 删除**
  - `配方是全系统营养计算的唯一基准。用量的单位统一是克，食材按市品重量填写，计算时再按可食部比例折算。`
  - 问题：解释数据模型。
- `apps/web/src/features/dish/components/DishFormDrawer.tsx:341` — **P1 删除或压缩为“未填配方，暂不计算营养”**
  - `还没有配方，这道菜暂时算不出营养值，也就不会出现在公开大屏上。`
- `apps/web/src/features/dish/components/DishFormDrawer.tsx:258` — **P1 压缩为字段提示**
  - `勾上之后这道菜每天都是早餐的一部分（早餐不走每日选菜），并且不再出现在午餐与晚餐里`
  - 建议：`早餐每天固定供应；不参与午晚餐选菜`
- `apps/web/src/features/dish/pages/SeasoningListPage.tsx:324` — **P1 删除**
  - `食盐的钠含量约 39311 毫克/100 克，它是校准模型的锚点`
- `apps/web/src/features/dish/pages/SeasoningListPage.tsx:337` — **P1 删除或压缩**
  - `写清是哪一条：条目名 + 条目 ID。只写「查过成分表」等于没写。`
  - 建议：`填写条目名与条目 ID`
- `apps/web/src/features/dish/components/ImportDrawer.tsx:87-89` — **P1 压缩**
  - `先下载模板，按里面的四个 sheet 填写。名称已存在的按更新处理，菜品配方会被整体替换。`
- `apps/web/src/features/dish/components/ImportDrawer.tsx:92-94` — **P1 删除或压成一句**
  - `先点「校验」看逐行报告；报告里有错误时一行都不会写库，改完再点「确认导入」。`
- `apps/web/src/features/dish/components/ImportDrawer.tsx:136` — **P2 保留**
  - `已同步重算 N 条营养结果。`
  - 这是操作结果反馈，不是说明文。

---

## 七、明日菜单与采购

### 单餐模式

- `apps/web/src/features/menuplan/pages/MenuPlanPage.tsx:169-173` — **P1 删除**
  - `一次生成三件事：在营养目标下选出做哪几道菜 → 按同星期历史与节假日日历预测每道菜做多少份 → 按各菜配方算出要买多少料。份数只有一套，采购量就是用它乘出来的。`
- `apps/web/src/features/menuplan/pages/MenuPlanPage.tsx:177-179` — **P1 删除**
  - 直接展示 `plan.notes`，内容包含早餐固定、午餐先排、晚餐避让、份数来源等整段说明。
- `apps/web/src/features/menuplan/components/RecommendedDishes.tsx:85-92` — **P0 删除**（见第一节）
- `apps/web/src/features/menuplan/components/RecommendedDishes.tsx:146-152` — **P1 压缩**
  - 同步确认弹窗里解释“每日采集会怎么勾、公开大屏会怎么显示、采集提交后计划不覆盖实际”的整段话。
- `apps/web/src/features/menuplan/components/RecommendedDishes.tsx:173` — **P1 删除或只保留“已同步”**
  - `每日采集的「当日供应菜品」已按这份菜单勾好，公开大屏也看得到。临时换菜在采集页改，保存即按实际供应覆盖。`
- `apps/web/src/features/menuplan/components/RecommendedDishes.tsx:183` — **P1 删除**
  - `它会被用来改进后续推荐。`
- `apps/web/src/features/menuplan/components/RecommendedDishes.tsx:274-276` — **P1 删除或压缩**
  - `写清原因——需求里写明它会被用来改进后续推荐，只留一句「不合适」等于没记。`
- `apps/web/src/features/menuplan/components/PurchaseList.tsx:69-75` — **P1 删除**
  - `plan.servings_note` + `summary.note` / `用料由各菜配方按份数汇总，按金额从大到小排。`
- `apps/web/src/features/menuplan/components/PurchaseList.tsx:91-94` — **P1 删除或移入表格提示**
  - `金额按「元/公斤市品」单价计。缺单价的项金额为空，合计因此偏低。`

### 一天三餐

- `apps/web/src/features/menuplan/components/DailyPlanView.tsx:38-43` — **P0 删除**（见第一节）
- `apps/web/src/features/menuplan/components/DailyPlanView.tsx:93-95` — **P0 删除**
  - `按餐次分别校验；某餐已经录过采集时会跳过该餐，其余餐次继续写入。`
- `apps/web/src/features/menuplan/components/DailyPlanView.tsx:123-129` — **P1 删除**
  - `plan.servings_note` 与 `summary.note` / `相同食材与调味料已合并，按金额从大到小排。`
- `apps/web/src/features/menuplan/components/DailyPlanView.tsx:139-141` — **P1 删除**
  - `金额按「元/公斤市品」单价计。缺单价的项金额为空，合计因此偏低。`
- `apps/web/src/features/menuplan/components/BatchPlanner.tsx:87-92` — **P1 删除**
  - `一次排一段，最长 31 天。每天的菜由推荐选出……生成只是算出来，确认无误后点下面的「一键导入当日菜单」才写进各天的当日数据……`
- `apps/web/src/features/menuplan/components/BatchPlanner.tsx:113-117` — **P1 删除或只保留状态行**
  - `这些天的每日采集已经按菜单勾好，公开大屏也看得到了。` / `这一步还没有写进当日数据：点下面的「一键导入当日菜单」才会生效。`
- `apps/web/src/features/menuplan/components/BatchPlanner.tsx:194-197` — **P1 删除**
  - `导入会把这段区间里最近生成的那一版菜单写进各天的当日数据；已经录过采集的日子会跳过并说明原因。`

### 后端直接进入页面的说明字段

- `apps/api/app/modules/menuplan/service.py:236-261` — **P0 删除或移入折叠依据**
  - `一键生成早、午、晚三餐：早餐固定组合；午餐先排……`
  - `三餐各自使用系统预测的就餐人次与份数；采购单已把相同食材和调味料合并。`
  - `同步时按餐次分别校验：已录采集的那一餐跳过，其余餐次继续写入当日数据。`
  - `就餐人次使用系统预计：N 人（……）；可在任务条件中修改后重新计算。`
- `apps/api/app/modules/menuplan/service.py:287-289` — **P1 删除或移入依据**
  - `采购量 = 推荐选出的菜 × 该菜明天的预测份数；预测不出来时退回「每人一份」估算并逐行标注。`
- `apps/api/app/modules/menuplan/service.py:339-357` — **P1 删除或移入依据**
  - 三餐说明与合并采购说明。
- `apps/api/app/modules/recommendation/targets.py:147,157` — **P0 删除**
  - 能量目标功能验证/待核实说明、WS/T 554 适用范围说明。
- `apps/api/app/modules/menuplan/readiness.py:289` — **P1 删除或移入帮助**
  - `仅检查当前数据的结构与计算准备情况，不认证来源真实性、不保证求解有解或营养全部达标……`

---

## 八、知味膳食助手

- `apps/web/src/features/agent/components/TaskPanel.tsx:54` — **P1 删除**
  - `随时可调整`
- `apps/web/src/features/agent/components/TaskPanel.tsx:107-111` — **P1 压缩**
  - `系统预测 922 人 · 参考区间 777–1067 人 · 同星期几中位数`
  - 建议只保留输入框和一个小“系统预测”标签，不展开依据。
- `apps/web/src/features/agent/components/TaskPanel.tsx:137` — **P1 删除**
  - `计算用当前条件。对话中可更改人数、每人预算或菜品；换菜会排除此菜并重算整餐。`
- `apps/web/src/features/agent/components/TaskPanel.tsx:140` — **P1 删除或压缩**
  - `当前账号可核查记录；菜单安排与发布由食堂负责。`
- `apps/web/src/features/agent/components/TaskPanel.tsx:169` — **P1 删除**
  - `任务会随账号保存，刷新后可继续。`
- `apps/web/src/features/agent/components/ConversationView.tsx:134-138` — **P1 删除或压缩**
  - `从菜单到采购，把依据摊开看。你提出条件，知味调用现有数据计算，最后由你确认。`
- `apps/web/src/features/agent/components/ConversationView.tsx:18-59` — **P1 删除或压缩**
  - 8 个项目卡片下的 hint：`按人数、预算和供餐记录计算`、`配方、单价和供餐历史是否准备好`、`找出需要人工核对的记录` 等。
- `apps/web/src/features/agent/components/ConversationView.tsx:181` — **P1 删除**
  - `选择后才会继续；你也可以直接回复。`
- `apps/web/src/features/agent/components/ConversationView.tsx:210` — **P2 保留或删除**
  - `还可以这样问`
- `apps/web/src/features/agent/components/ConversationView.tsx:234` — **P1 压缩**
  - `等待补充条件，尚未执行新的安排`
- `apps/web/src/features/agent/components/ReadinessResult.tsx:31` — **P1 删除**
  - `按检查时的排除条件核对。`
- `apps/web/src/features/agent/components/ReadinessResult.tsx:78-83` — **P1 删除或移入帮助**
  - `历史范围……最近有效人次……`
- `apps/web/src/features/agent/components/ReadinessResult.tsx:105` — **P1 删除**
  - `本次检查未发现结构缺口，仍需核对来源与实际供餐背景。`
- `apps/web/src/features/agent/components/ReadinessResult.tsx:118` — **P1 删除**
  - `report.note` 的整段检查口径。
- `apps/web/src/features/agent/components/ReadinessResult.tsx:120` — **P1 删除或压缩**
  - `检查时间：……。数据变化后请重新体检。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:26-27` — **P1 删除或压缩**
  - `保留每一次调整` / `修改人数、预算或排除一道菜后重算，便可查看菜品和采购金额的变化。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:68` — **P1 删除**
  - `两版计算快照均保留。人数和预算不同时，采购金额的增减不代表节约或浪费。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:91` — **P1 删除**
  - `review.note`
- `apps/web/src/features/agent/components/ResultPanel.tsx:115-116` — **P1 删除或压缩**
  - `这不代表所有数据都正确，仍需结合人工记录判断。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:181-191` — **P1 删除或压缩**
  - `菜单与采购，会在这里展开` + `先告诉知味供餐安排……` + 三条 bullet。
- `apps/web/src/features/agent/components/ResultPanel.tsx:272-274` — **P1 删除**
  - `供给量不等于实际摄入量。建议目标未必全部满足，请结合差距决定是否修改。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:286` — **P1 删除**
  - `plan.servings_note`
- `apps/web/src/features/agent/components/ResultPanel.tsx:315-317` — **P1 删除**
  - `单价口径：元 / 公斤市品。未录单价的项目不计入合计，导出与当前快照一致。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:337-377` — **P1 压缩**
  - `这版是怎样算出的`、`目标与数据口径`、`快照记录`、`数字来自业务服务；解释不能替代实际配方、称重与人工核对。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:398-402` — **P1 压缩**
  - `本次检查针对……上方仍为第 N 版……检查不会改变已有菜单。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:484` — **P2 保留**
  - `有 N 项偏离建议目标，请核对营养差距后决定是否调整。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:508` — **P2 保留**
  - `菜单已恢复成发布前的样子；要再排一版请重新计算。`
- `apps/web/src/features/agent/components/ResultPanel.tsx:531` — **P1 删除或压缩**
  - `核对菜品、金额和差距，确认后写入这餐菜单。`
- `apps/web/src/features/agent/AgentPage.tsx:194-197` — **P1 压缩**
  - 发布确认弹窗的两段解释。
- `apps/web/src/features/agent/AgentPage.tsx:232-233` — **P1 删除或压缩**
  - `发布之后菜单要是被别人改过、或者这餐已经录了采集，系统会拒绝撤回——它不会覆盖别人的改动。`
- `apps/web/src/features/agent/AgentPage.tsx:329` — **P1 压缩**
  - `请启动 Agent 与业务服务后点击刷新结果。`

---

## 九、公开大屏

- `apps/web/src/features/display/pages/DisplayPage.tsx:68-70` — **P2 保留但压缩**
  - `data.disclaimer`，原文在 `apps/api/app/modules/public/service.py:34-37`：
    `本屏只展示菜品级营养与群体级供给数据，不针对任何个人，也不构成任何医疗建议；对照基准引自《中国居民膳食指南（2022）》。`
  - 这是合规声明，不建议完全删除；可以缩短到一行。
- `apps/web/src/features/display/pages/DisplayPage.tsx:218` — **P1 删除或移入帮助**
  - `部分成分缺失，数值区间已相应放宽`
- `apps/web/src/features/display/pages/DisplayPage.tsx:51` — **P1 压缩**
  - `暂时读不到今日数据，请稍后自动重试`

---

## 十、节假日日历

- `apps/web/src/features/forecast/components/HolidayTable.tsx:25` — **P1 删除或压缩**
  - `放假当天下调份数、调休上班的周末按工作日算。以国务院办公厅通知为唯一依据。`
- `apps/web/src/features/forecast/components/HolidayTable.tsx:77-80` — **P1 删除**
  - `核对时请同时确认「放假区间」与「调休上班日」——目前内置的只有节日当天，连休与调休需要按通知补进来。`
- `apps/web/src/features/forecast/lib/format.ts:70-75` — **P1 压缩**
  - `还有 N 条日历未核对（……）。这些日期已经在参与预测修正，请对照国务院办公厅通知确认后再标记为已核对`

---

## 十一、全局提示与错误状态（多数建议保留）

- `apps/web/src/shared/components/OfflineNotice.tsx:27-29` — **P2 保留，可压缩**
  - `采集页的录入会先存在本机，现有 N 条待同步，恢复网络后自动补交。其他页面的修改暂时提交不了。`
- `apps/web/src/shared/components/UpdatePrompt.tsx:51` — **P2 保留**
  - `新版本已就绪。刷新后生效；填了一半还没提交的录入会丢失。`
- `apps/web/src/features/auth/components/RequireAuth.tsx:38` — **P2 保留或压缩**
  - `服务恢复后可以重新连接，无需反复输入口令。`
- `apps/web/src/features/auth/pages/RegisterPage.tsx:51-53` — **P2 保留**
  - `注册成为食堂录入员，维护食材并记录每日供餐数据。`
- `apps/web/src/layouts/AdminLayout.tsx:167` — **P2 保留**
  - `营养核算 · 采购预测 · 决策支持`
- `apps/web/src/layouts/AdminLayout.tsx:172` — **P2 保留（仅功能验证模式显示）**
  - `独立开发 · 合成数据`

---

## 十二、建议保留的功能性文案

以下类型不建议按“AI 味”处理，否则会损害可用性或合规性：

- 表单校验错误，例如“请输入就餐人次”“密码至少 8 个字符”。
- 权限提示，例如“当前账号没有访问该页面的权限”。
- 操作确认，例如“停用该食材？”“放弃这条记录？”。
- 数据缺失提示，例如“未录入单价”“暂无数据”。
- 公开大屏的合规免责声明。
- 后端返回的真实异常/阻塞原因，例如“这一天已经录过采集”“菜名有歧义”。
- 「计算依据」「依据与校验」「数据体检」等已经折叠或单独成 tab 的审计内容；
  它们是排错依据，不建议按页面正文小字处理。

---

## 建议的第一批清理顺序

1. 先删第一节的四处截图命中文案，并删掉 `RecommendedDishes` / `DailyPlanView` 顶部整块 Alert。
2. 再删各页面顶部 `Typography.Paragraph` 式操作教学（看板、采集、抽样、单餐、批量）。
3. 最后处理技术口径小字：`basis_note`、`servings_note`、`readiness.note`、`scope_notice`，统一移入折叠帮助或直接删。
4. 保留错误、权限、确认和合规声明，避免把“说明文字”清理成“信息缺失”。
