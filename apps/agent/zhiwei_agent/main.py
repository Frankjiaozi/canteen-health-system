import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .business import BusinessClient
from .config import Settings, get_settings
from .errors import AgentError
from .exports import purchase_csv, review_markdown
from .report import report_html
from .runner import event, run
from .schemas import AgentStatus, Conversation, MessageRequest, PublishRequest, SessionSummary
from .store import Store


@dataclass
class Access:
    user: dict
    business: BusinessClient


def create_app(settings: Settings | None = None, business_transport=None) -> FastAPI:
    cfg = settings or get_settings()
    store = Store(cfg.data_path)
    app = FastAPI(
        title="知味 Agent",
        version="0.1.0",
        docs_url="/agent-api/docs",
        openapi_url="/agent-api/openapi.json",
        redoc_url=None,
    )
    app.state.store = store

    @app.exception_handler(AgentError)
    async def agent_error(request: Request, exc: AgentError):
        return JSONResponse(exc.body(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {
                "code": "validation_error",
                "message": "请求参数有误，请检查日期、人数与预算",
                "details": [
                    {"field": ".".join(map(str, item["loc"])), "message": item["msg"]}
                    for item in exc.errors()
                ],
            },
            status_code=422,
        )

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        # Agent 的所有响应都含当前账号状态或方案，不能进入浏览器/网关共享缓存。
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (
                origin
                and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower()
            ):
                return JSONResponse(
                    {"code": "forbidden", "message": "不接受跨站操作", "details": None},
                    status_code=403,
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    async def access(request: Request):
        token = request.cookies.get(cfg.cookie_name)
        if not token:
            raise AgentError("请先登录知味系统", 401, "unauthorized")
        business = BusinessClient(cfg.business_api_url, cfg.cookie_name, token, business_transport)
        try:
            user = await business.current_user()
            yield Access(user=user, business=business)
        finally:
            await business.close()

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "zhiwei-agent"}

    @app.get("/agent-api/v1/status", response_model=AgentStatus)
    async def status(current: Access = Depends(access)):
        return {
            "mode": cfg.effective_mode,
            "model_name": cfg.model_name if cfg.effective_mode == "model" else None,
            "data_notice": cfg.data_notice,
            "can_plan": current.user["role"] in {"RECORDER", "CANTEEN_ADMIN"},
            "capabilities": [
                "menu_plan",
                "revision",
                "evidence",
                "review",
                "data_readiness",
                "dashboard",
                "menu_day",
                "dish_recipe",
                "ingredient_lookup",
                "holiday_calendar",
                "publish",
                "export",
            ],
        }

    @app.get("/agent-api/v1/dishes")
    async def dishes(current: Access = Depends(access)):
        return await current.business.request("GET", "dishes", params={"page_size": 100})

    @app.get("/agent-api/v1/sessions", response_model=list[SessionSummary])
    async def list_sessions(current: Access = Depends(access)):
        return store.list(str(current.user["id"]))

    @app.post("/agent-api/v1/sessions", status_code=201, response_model=Conversation)
    async def create_session(current: Access = Depends(access)):
        return store.create(str(current.user["id"])).model_dump(mode="json")

    @app.get("/agent-api/v1/sessions/{session_id}", response_model=Conversation)
    async def get_session(session_id: UUID, current: Access = Depends(access)):
        return store.get(str(session_id), str(current.user["id"])).model_dump(mode="json")

    @app.post("/agent-api/v1/sessions/{session_id}/messages")
    async def message(session_id: UUID, payload: MessageRequest, current: Access = Depends(access)):
        owner, sid = str(current.user["id"]), str(session_id)
        store.acquire(sid, owner)
        try:
            conversation = store.get(sid, owner)
            if str(payload.request_id) in conversation.completed_requests:
                fingerprint = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
                previous = conversation.request_fingerprints.get(str(payload.request_id))
                if previous is not None and fingerprint != previous:
                    raise AgentError(
                        "同一请求编号不能用于不同任务，请重新发送", 409, "idempotency_conflict"
                    )
                store.release(sid, owner)

                async def replay():
                    yield event("done", conversation=conversation.model_dump(mode="json"))

                return StreamingResponse(replay(), media_type="application/x-ndjson")
            if payload.expected_revision != conversation.revision:
                raise AgentError("方案已被其他页面更新，请刷新后再继续", 409, "revision_conflict")
            if len(conversation.messages) >= 200 or conversation.revision >= 40:
                raise AgentError("这个任务已保留较多记录，请新建任务后继续", 422, "session_limit")
        except BaseException:
            store.release(sid, owner)
            raise
        return StreamingResponse(
            run(store, conversation, owner, current.user["role"], current.business, cfg, payload),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no"},
        )

    @app.post("/agent-api/v1/sessions/{session_id}/publish", response_model=Conversation)
    async def publish(session_id: UUID, payload: PublishRequest, current: Access = Depends(access)):
        owner, sid = str(current.user["id"]), str(session_id)
        if current.user["role"] not in {"RECORDER", "CANTEEN_ADMIN"}:
            raise AgentError("当前账号没有发布菜单的权限", 403, "forbidden")
        store.acquire(sid, owner)
        try:
            conversation = store.get(sid, owner)
            if not conversation.plans or payload.revision != conversation.revision:
                raise AgentError("只能确认对话里的最新方案，请核对版本", 409, "revision_conflict")
            version = conversation.plans[-1]
            result = version.result
            receipt = await current.business.request(
                "POST",
                f"menu-plan/{result['suggestion_id']}/publish",
                json={
                    "snapshot_token": result["snapshot_token"],
                    "expected_menu_token": result["expected_menu_token"],
                },
            )
            version.publication = receipt
            store.save(conversation, owner)
            return conversation.model_dump(mode="json")
        finally:
            store.release(sid, owner)

    @app.post("/agent-api/v1/sessions/{session_id}/undo", response_model=Conversation)
    async def undo(session_id: UUID, current: Access = Depends(access)):
        """撤回最近一次发布：菜单恢复成发布前的样子，那一版方案回到待确认。

        与「发布」对称——同样不经过模型，同样以当前用户身份调业务接口。
        业务那边会核对发布时留下的快照凭据：这餐菜单在发布之后被别人改过、
        或者已经录了采集，都会拒绝，撤回不会去覆盖别人的改动。
        """
        owner, sid = str(current.user["id"]), str(session_id)
        if current.user["role"] not in {"RECORDER", "CANTEEN_ADMIN"}:
            raise AgentError("当前账号没有撤回菜单的权限", 403, "forbidden")
        store.acquire(sid, owner)
        try:
            conversation = store.get(sid, owner)
            published = [
                version
                for version in conversation.plans
                if version.publication and not version.undone
            ]
            if not published:
                raise AgentError("这个对话里没有可撤回的发布", 409, "nothing_to_undo")
            version = published[-1]
            receipt = await current.business.request(
                "POST", f"menu-plan/{version.result['suggestion_id']}/undo"
            )
            version.undone = receipt
            store.save(conversation, owner)
            return conversation.model_dump(mode="json")
        finally:
            store.release(sid, owner)

    @app.get("/agent-api/v1/sessions/{session_id}/purchase.csv")
    async def export_purchase(
        session_id: UUID, revision: int | None = None, current: Access = Depends(access)
    ):
        conversation = store.get(str(session_id), str(current.user["id"]))
        chosen = revision if revision is not None else conversation.revision
        if chosen < 1 or chosen > conversation.revision:
            raise AgentError("这版采购方案不存在", 404, "not_found")
        return Response(
            purchase_csv(conversation.plans[chosen - 1], cfg.data_notice),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="zhiwei-purchase-v{chosen}.csv"'
            },
        )

    @app.get("/agent-api/v1/sessions/{session_id}/review.md")
    async def export_review(session_id: UUID, current: Access = Depends(access)):
        conversation = store.get(str(session_id), str(current.user["id"]))
        if not conversation.review:
            raise AgentError("请先执行记录核查", 404, "not_found")
        return Response(
            review_markdown(conversation, cfg.data_notice),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="zhiwei-review.md"'},
        )

    @app.get("/agent-api/v1/sessions/{session_id}/report.html")
    async def export_plan_report(
        session_id: UUID,
        revision: int | None = None,
        download: bool = True,
        current: Access = Depends(access),
    ):
        conversation = store.get(str(session_id), str(current.user["id"]))
        chosen = revision if revision is not None else conversation.revision
        if chosen < 1 or chosen > conversation.revision:
            raise AgentError("这版方案报告不存在", 404, "not_found")
        return Response(
            report_html(conversation.plans[chosen - 1], cfg.data_notice),
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": f'{"attachment" if download else "inline"}; filename="zhiwei-plan-v{chosen}.html"',
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return app


app = create_app()
