# 架构说明

## 一、总体形态

单仓多包（pnpm workspace）+ 前后端分离 + 模块化单体后端。

```
浏览器
  ├── /           管理端（需登录）
  └── /display    公开大屏（免登录）
        │
        │  /api/v1/**（同源，nginx 反代 / Vite 代理）
        ▼
   FastAPI 模块化单体
        │
        ▼
   PostgreSQL
```

前端与后端同源部署，因此登录凭证用 httpOnly Cookie 传递，前端代码不接触 token。

## 二、后端分层

依赖方向严格单向，**不允许反向或跨层引用**：

```
router  →  service  →  repository  →  db
（HTTP）   （业务）     （数据访问）    （引擎/会话）
```

- `app/core/` 配置、安全、通用依赖、领域异常与统一异常处理器、日志。
- `app/db/` 引擎与会话、声明基类与审计 mixin、迁移、种子数据。
- `app/modules/<域>/` 每个业务域固定五件套：
  - `models.py` —— SQLAlchemy ORM 模型
  - `schemas.py` —— Pydantic 请求/响应模型
  - `repository.py` —— 数据访问，只做查询与持久化，不含业务规则
  - `service.py` —— 业务规则与事务边界
  - `router.py` —— HTTP 层，只做参数校验与调用 service

### 跨域协作规则

跨业务域只允许调用对方的 **service**，禁止 import 对方的 `models.py` 或 `repository.py`。
这条规则保证了业务域可以独立演进，也是「模块化单体」相比传统按类型分层最重要的收益。

### 唯一的例外：营养域的跨域读模型装配

`app/modules/nutrition/repository.py` 可以引用其它域的 ORM 模型，这是全项目唯一一处例外。

原因是营养计算天然要横向读取五个域的数据（菜品与配方、食材成分、调味料、菜单日、每日记录），
把它们拼成引擎的输入。为此给每个输入都单独造一层 DTO，只会增加间接层而并不隔离任何真实变化——
计算逻辑与这些字段本来就是天然绑定的。

边界仍然清楚：**只读**。任何写入都走各域自己的 service，营养域不修改别的域的数据。

### 模块清单

| 域 | 职责 | 本次范围 |
| --- | --- | --- |
| `auth` | 登录、当前用户、角色校验 | 完整闭环 |
| `ingredient` | 食材库与营养成分数据 | 完整闭环（示例模块） |
| `public` | 公开大屏聚合接口（免登录） | 完整闭环 |
| `dish` | 菜品与标准配方 | 完整闭环（含配方整体替换与写后重算） |
| `seasoning` | 调味料库 | 完整闭环 |
| `importer` | Excel 批量导入（菜品、配方、食材、调味料） | 完整闭环，无自有数据表 |
| `menu` | 菜单轮换与菜单日 | 仅建模型 |
| `collection` | 每日采集与剩餐反馈 | 仅建模型 |
| `nutrition` | 三层校准营养计算引擎 | 第一层（理论值） |
| `forecast` | 消耗量预测 | 仅建模型 |
| `recommendation` | 菜单组合优化 | 仅建模型 |
| `analytics` | 管理端看板聚合 | 完整闭环 |
| `audit` | 操作留痕 | 横切能力 |

## 三、算法与 IO 分离

`nutrition/engine.py`、`forecast/strategy.py`、`recommendation/solver.py` 一律写成**纯函数**：
输入是普通 dataclass，输出是结果对象，不接触数据库、不读全局状态。

调用方（service）负责把 ORM 数据装配成 dataclass，再把结果落库。这样做的两个好处：

1. 算法可以脱离数据库单测，验收标准里的「5 道菜偏差不超过 15%」「MAPE 回测」可以直接写成断言。
2. 算法实现可以替换（比如启发式换成整数规划）而不影响业务代码。

## 四、前端结构

```
src/
├── app/          路由表、Provider、全局装配
├── features/<域>/  每个业务域内聚 api hooks、组件、页面、路由片段
├── layouts/      AdminLayout（手机可用）、DisplayLayout（大屏自适应）
└── shared/       UI 组件、hooks、工具、常量（膳食指南基准等）
```

状态分层：

- **服务端状态**一律走 TanStack Query，不在业务代码里手写 loading/error 状态机。
- **客户端状态**（当前用户、离线标记等）走 Zustand，且只放真正跨组件共享的部分。

路由级懒加载，每个业务域导出自己的路由片段，由 `src/app/router.tsx` 汇总挂载。

## 五、接口约定

- 原生 REST：用 HTTP 状态码表意，不做 `{code, message, data}` 全包。
- 错误体统一为 `{code, message, details}`。
- 分页统一为 `{items, total, page, page_size}`。
- 业务日期用 `DATE`（不含时间），时间戳用 `timestamptz`，时区统一 `Asia/Shanghai`。
- 前端类型由 OpenAPI 生成，`packages/api-client/src/schema.d.ts` 是唯一真源。

## 六、口径分离（本系统最容易出错的地方）

营养值有两个互相独立的口径维度，**禁止混用**：

| 维度 | 取值 | 含义 |
| --- | --- | --- |
| `caliber` | 单份 / 人均 | 一道菜一份的营养 vs 当日总营养 ÷ 就餐人次 |
| `value_type` | 理论 / 校准 / 抽样 | 配方推算值 vs 当日闭环校准值 vs 抽样实测值 |

单份营养服务大屏与菜品查询，人均摄入服务看板与政策对标。把两者混用会得出完全错误的结论。

## 七、可追溯与留痕

- `dish_nutritions.computation_trace` 保存配方快照、所用校准系数与公式版本，任何数值都能回溯到来源与计算过程。
- 食材营养数据逐条记录来源与版本。
- 配方与菜单的修改通过 `audit_logs` 记录操作人、时间与前后值。

## 八、部署形态

面向**学校内网自部署**：`infra/docker-compose.yml` 一条命令拉起数据库、后端与前端，
只对外暴露前端端口；`/api` 由 nginx 反代到后端，前后端同源——登录凭证是 httpOnly Cookie，
同源才走得通，也就不需要为跨域凭证另做配置。数据库迁移随后端容器启动自动执行。

完整说明见 [deployment.md](./deployment.md)。
