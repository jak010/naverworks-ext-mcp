from fastapi import APIRouter, Depends
from app.api.deps import bind_request_cookie
from app.api.v1.spaces import router as spaces_router
from app.api.v1.projects import router as projects_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.mail import router as mail_router

v1_router = APIRouter(prefix="/api/v1", dependencies=[Depends(bind_request_cookie)])
v1_router.include_router(spaces_router)
v1_router.include_router(projects_router)
v1_router.include_router(tasks_router)
v1_router.include_router(mail_router)


