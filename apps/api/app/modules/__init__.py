"""业务域层：每个子目录是一个独立的业务域。

每个业务域固定包含 `models.py / schemas.py / repository.py / service.py / router.py` 五件套，
依赖方向为 `router → service → repository → db`。
跨业务域只允许调用对方的 service，禁止 import 对方的 models 或 repository。
"""
