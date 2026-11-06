"""응답 경량화 함수가 실제 네이버웍스 응답 구조(2026-11-07 확인)를 올바르게 처리하는지 검증"""

from app.core.mcp_spec import _slim_task, _slim_tasks, _slim_project

REAL_GET_TASK = {
    "task": {
        "taskId": "t-1", "title": "제목", "parentTaskId": None, "subTaskIds": ["t-2"],
        "status": {"taskStatusType": "OPEN", "lastModified": 1},
        "content": {"htmlText": "<p>본문</p>", "plainText": "본문", "mentionedUserIds": [], "inlineImages": [], "editorVersion": 2},
        "due": None, "created": 1, "modified": 2, "assignees": [], "taskFiles": [],
    },
    "relatedUserIds": ["u-1"],
}


def test_slim_task_unwraps_real_get_task_response():
    t = _slim_task(REAL_GET_TASK)
    assert t["taskId"] == "t-1"
    assert t["title"] == "제목"
    assert t["status"] == "OPEN"
    assert t["content"] == "본문"
    assert t["subTaskIds"] == ["t-2"]


def test_slim_task_still_accepts_flat_shape():
    assert _slim_task(REAL_GET_TASK["task"])["title"] == "제목"


def test_slim_tasks_real_list_shape():
    rows = _slim_tasks({"projectTasks": [REAL_GET_TASK["task"]], "relatedUserIds": []})
    assert rows == [{"taskId": "t-1", "title": "제목", "status": "OPEN", "due": None, "parentTaskId": None, "contentPreview": "본문"}]


def test_slim_project_unwraps_project_key():
    assert _slim_project({"project": {"projectId": "p-1", "projectName": "P"}})["projectName"] == "P"
