"""사용자별 동시성 제한 검증: 한 사용자의 대량 요청이 다른 사용자를 지연시키지 않아야 합니다."""

import asyncio
import gc
import time
from collections import defaultdict

import httpx
import pytest

from app.core import client as nw_client
from app.main import app

HEAVY = "WORKS_SES=heavy-user-session-000000001"
LIGHT = "WORKS_SES=light-user-session-000000002"
UPSTREAM_DELAY = 0.05


@pytest.fixture
def slow_upstream(monkeypatch):
    """업스트림 응답을 지연시키고 사용자별/전체 동시 처리 수의 최댓값을 기록"""
    stats = {"inflight": defaultdict(int), "max": defaultdict(int), "total": 0, "max_total": 0, "done": defaultdict(list)}

    async def handler(request: httpx.Request) -> httpx.Response:
        c = request.headers.get("cookie")
        stats["inflight"][c] += 1
        stats["total"] += 1
        stats["max"][c] = max(stats["max"][c], stats["inflight"][c])
        stats["max_total"] = max(stats["max_total"], stats["total"])
        await asyncio.sleep(UPSTREAM_DELAY)
        stats["inflight"][c] -= 1
        stats["total"] -= 1
        stats["done"][c].append(time.monotonic())
        return httpx.Response(200, json=[])

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    return stats


async def _call(c, cookie, i):
    # 캐시를 피하기 위해 요청마다 다른 인자 사용
    return await c.post("/mcp/call", json={"name": "get_task", "arguments": {"taskId": f"t-{i}"}},
                        headers={"X-Naverworks-Cookie": cookie})


@pytest.mark.anyio
async def test_heavy_user_is_capped_and_does_not_block_others(slow_upstream):
    limit = nw_client.PER_USER_MAX_CONCURRENCY
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        heavy = [asyncio.create_task(_call(c, HEAVY, i)) for i in range(limit * 5)]
        await asyncio.sleep(UPSTREAM_DELAY / 5)  # 무거운 사용자가 먼저 몰려든 상황
        t0 = time.monotonic()
        light = await _call(c, LIGHT, 0)
        light_latency = time.monotonic() - t0
        await asyncio.gather(*heavy)

    assert light.json()["isError"] is False
    assert slow_upstream["max"][HEAVY] == limit
    # 가벼운 사용자는 무거운 사용자의 대기열(5라운드) 뒤에 줄 서지 않고 약 1회 지연 안에 응답
    assert light_latency < UPSTREAM_DELAY * 2.5, light_latency
    assert slow_upstream["done"][LIGHT][0] < max(slow_upstream["done"][HEAVY])


@pytest.mark.anyio
async def test_global_cap_still_applies_across_users(slow_upstream, monkeypatch):
    monkeypatch.setattr(nw_client, "UPSTREAM_MAX_CONCURRENCY", 6)
    monkeypatch.setattr(nw_client, "_upstream_semaphore", None)
    users = [f"WORKS_SES=user-{i:02d}-session-0000000000" for i in range(5)]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        results = await asyncio.gather(*(_call(c, u, i) for u in users for i in range(4)))
    assert all(r.json()["isError"] is False for r in results)
    assert slow_upstream["max_total"] <= 6
    monkeypatch.setattr(nw_client, "_upstream_semaphore", None)


@pytest.mark.anyio
async def test_user_semaphores_are_released_after_use(slow_upstream):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        await asyncio.gather(*(_call(c, f"WORKS_SES=transient-{i:03d}-abcdefghijkl", i) for i in range(30)))
    gc.collect()
    assert len(nw_client._user_semaphores) == 0, "사용이 끝난 사용자 세마포어가 메모리에 남아 있음"
