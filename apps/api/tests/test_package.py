"""应用包的基础自检：确保包可导入、版本号可读。

真正的业务测试从「后端核心骨架」模块开始按域添加。
"""

import app


def test_package_is_importable() -> None:
    assert app.__version__ == "0.1.0"
