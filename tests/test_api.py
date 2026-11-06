from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "NAVER WORKS Custom API & MCP Server"
    assert data["status"] == "online"


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mcp_tools_list():
    response = client.get("/mcp/tools")
    assert response.status_code == 200
    tools = response.json().get("tools", [])
    assert len(tools) >= 14
    tool_names = [t["name"] for t in tools]
    assert "set_user_cookie" in tool_names
    assert "get_auth_status" in tool_names
    assert "login_naverworks" in tool_names  # multi_user 모드에서는 수동 로그인 안내 도구로 노출
    assert "list_spaces" in tool_names
    assert "list_projects" in tool_names
    assert "get_project" in tool_names
    assert "list_tasks" in tool_names


def test_mcp_rpc_ping():
    response = client.post(
        "/mcp/rpc",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"}
    )
    assert response.status_code == 200
    assert response.json() == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_mcp_rpc_initialize():
    response = client.post(
        "/mcp/rpc",
        json={"jsonrpc": "2.0", "id": 2, "method": "initialize"}
    )
    assert response.status_code == 200
    res = response.json().get("result", {})
    assert res.get("serverInfo", {}).get("name") == "naverworks-custom-fastapi"


def test_spaces_list():
    response = client.get("/api/v1/spaces")
    assert response.status_code in [200, 401]
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, (list, dict))


def test_projects_list():
    response = client.get("/api/v1/projects?space_id=s-123456789-00000000-0000-0000-0000-000000000000")
    assert response.status_code in [200, 401]
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)


def test_mcp_sse_endpoint():
    with client.stream("GET", "/sse") as response:
        assert response.status_code == 200
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 2:
                break
        assert "event: endpoint" in lines[0]
        assert "/messages?" in lines[1]


def test_mcp_initialized_notification():
    response = client.post(
        "/mcp/rpc",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert response.status_code == 202






def test_dashboard_served_from_static_file():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text.lstrip().startswith("<!DOCTYPE html>")
    assert "/api/v1/spaces" in response.text
