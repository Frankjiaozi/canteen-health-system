"""导出 Agent 契约，不启动 HTTP 服务。"""

import json
import sys
from pathlib import Path

from .main import app

if __name__ == "__main__":
    Path(sys.argv[1]).write_text(json.dumps(app.openapi(), ensure_ascii=False), encoding="utf-8")
