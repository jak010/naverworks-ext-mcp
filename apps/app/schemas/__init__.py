from app.schemas.space import SpaceCreateRequest
from app.schemas.project import ProjectCreateRequest
from app.schemas.task import TaskCreateRequest, TaskContentUpdateRequest
from app.schemas.mail import MailMoveRequest
from app.schemas.mcp import MCPJsonRpcRequest

__all__ = [
    "SpaceCreateRequest",
    "ProjectCreateRequest",
    "TaskCreateRequest",
    "TaskContentUpdateRequest",
    "MailMoveRequest",
    "MCPJsonRpcRequest",
]

