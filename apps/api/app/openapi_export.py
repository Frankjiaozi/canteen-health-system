"""把 FastAPI 应用的 OpenAPI 文档导出到文件。

供 `scripts/gen-api-client.mjs` 生成前端 TypeScript 类型使用。直接读内存中的应用对象、
不启动 HTTP 服务，因此 CI 里也能跑。

用法：
    python -m app.openapi_export [输出路径]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.main import app

DEFAULT_OUTPUT = Path("openapi.json")


def export_openapi(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    document = json.dumps(app.openapi(), ensure_ascii=False, indent=2)
    output.write_text(f"{document}\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    output = Path(args[0]) if args else DEFAULT_OUTPUT
    written = export_openapi(output)
    print(f"OpenAPI 文档已导出：{written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
