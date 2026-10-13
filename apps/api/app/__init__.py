"""食堂健康管理系统后端应用包。

分层约定（详见 docs/architecture.md）：

- `app.core`    —— 配置、安全、通用依赖、异常与日志等横切能力
- `app.db`      —— 引擎与会话、声明基类、迁移、种子数据
- `app.modules` —— 按业务域垂直切分的模块化单体

依赖方向固定为 `router → service → repository → db`，跨业务域只允许调用对方的
service，禁止直接引用对方的 ORM 模型。
"""

__version__ = "0.1.0"
