"""批量导入接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.schemas import AuthUser
from app.modules.importer import service
from app.modules.importer.schemas import ImportReport
from app.modules.importer.template import build_template
from app.shared.enums import UserRole

router = APIRouter(prefix="/import", tags=["批量导入"])

WRITE_ROLES = (UserRole.RECORDER, UserRole.CANTEEN_ADMIN)

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/template", summary="下载导入模板", response_class=Response)
def download_template(
    _: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> Response:
    """下载 Excel 模板。固定用 ASCII 文件名，免得 Content-Disposition 里出现编码问题。"""
    return Response(
        content=build_template(),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="canteen-import-template.xlsx"'},
    )


@router.post("/dishes", response_model=ImportReport, summary="导入菜品与配方")
async def import_dishes(
    file: UploadFile = File(description="按模板填写的 .xlsx 文件"),
    dry_run: bool = Query(
        default=True,
        description="true 只校验并给出报告，不写库；确认无误后再传 false 真正导入",
    ),
    session: Session = Depends(get_session),
    actor: AuthUser = Depends(require_roles(*WRITE_ROLES)),
) -> ImportReport:
    content = await file.read()
    return service.run_import(
        session,
        content,
        actor_id=actor.id,
        actor_name=actor.display_name,
        dry_run=dry_run,
        file_name=file.filename,
    )
