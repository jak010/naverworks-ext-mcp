from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class MCPJsonRpcRequest(BaseModel):
    jsonrpc: str = Field(default="2.0")
    id: Optional[Any] = None
    method: str
    params: Optional[Dict[str, Any]] = Field(default_factory=dict)

