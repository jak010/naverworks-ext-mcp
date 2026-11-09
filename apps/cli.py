#!/usr/bin/env python3
"""
NAVER WORKS CLI Tool
터미널에서 직접 네이버웍스 Spaces, Projects, Tasks를 빠르게 조회하고 관리할 수 있는 CLI 도구입니다.
"""

import os
import sys
import json
import asyncio
import argparse

# CLI는 본인 PC에서 실행하는 단일 사용자 도구이므로 로컬 모드가 기본입니다. (app import 전에 설정)
os.environ.setdefault("NAVERWORKS_AUTH_MODE", "local")

from app.core import (
    api_request,
    refresh_cookie_jar,
    ensure_cookie_jar,
    login_via_browser,
)
from app.config import (
    DEFAULT_INSTANCE_CODE,
    COOKIE_JAR_PATH,
    MAIL_BASE_URL,
)
from app.core.ids import DomainIdUnknown, ensure_domain_id, resolve_mail_u
from app.core.payloads import build_mail_move_payload



def format_json(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


def cmd_login(args):
    print("🌐 브라우저를 열어 네이버웍스 로그인을 진행합니다...")
    res = login_via_browser(timeout_seconds=args.timeout, force=args.force)
    if res.get("success"):
        print(f"✅ {res.get('message')}")
    else:
        print(f"❌ {res.get('message')}")


def cmd_refresh_cookies(args):
    print("🔑 Chrome 키체인에서 네이버웍스 쿠키를 추출하여 갱신합니다...")
    ok = refresh_cookie_jar()
    if ok:
        print(f"✅ 쿠키 갱신 완료: {COOKIE_JAR_PATH}")
    else:
        print("❌ 쿠키 갱신 실패. Chrome에 네이버웍스 로그인이 되어 있는지 확인하세요.")


def cmd_list_spaces(args):
    ensure_cookie_jar()
    res = api_request("GET", f"/rd/{args.domain_id}/api/v1/spaces")
    if res.get("status") == 200:
        data = res.get("data", {})
        spaces = data if isinstance(data, list) else data.get("spaces", [])
        print(f"📁 총 {len(spaces)}개의 스페이스:")
        for s in spaces:
            print(f" • [{s.get('spaceId')}] {s.get('spaceName')} (컬러: {s.get('spaceColor')})")
    else:
        print(f"❌ 오류 ({res.get('status')}): {res.get('error')}")


def cmd_get_space(args):
    ensure_cookie_jar()
    res = api_request("GET", f"/rd/{args.domain_id}/api/v1/spaces/{args.space_id}")
    if res.get("status") == 200:
        print(format_json(res.get("data")))
    else:
        print(f"❌ 오류 ({res.get('status')}): {res.get('error')}")


def cmd_list_projects(args):
    ensure_cookie_jar()
    res = api_request("GET", f"/rd/{args.domain_id}/api/v1/projects?spaceId={args.space_id}")
    if res.get("status") == 200:
        projects = res.get("data", [])
        print(f"🚀 스페이스 ({args.space_id})의 총 {len(projects)}개 프로젝트:")
        for p in projects:
            print(f" • [{p.get('projectId')}] {p.get('projectName')} (컬러: {p.get('projectColor')})")
    else:
        print(f"❌ 오류 ({res.get('status')}): {res.get('error')}")


def cmd_get_project(args):
    ensure_cookie_jar()
    res = api_request("GET", f"/rl/{args.instance_code}/api/v1/projects/{args.project_id}")
    if res.get("status") == 200:
        print(format_json(res.get("data")))
    else:
        print(f"❌ 오류 ({res.get('status')}): {res.get('error')}")


def cmd_list_tasks(args):
    ensure_cookie_jar()
    res = api_request("GET", f"/rd/{args.domain_id}/api/v1/tasks?projectId={args.project_id}")
    if res.get("status") == 200:
        data = res.get("data", {})
        if isinstance(data, dict):
            tasks = data.get("projectTasks") or data.get("tasks") or []
        elif isinstance(data, list):
            tasks = data
        else:
            tasks = []
        print(f"✅ 프로젝트 ({args.project_id})의 총 {len(tasks)}개 태스크:")
        for t in tasks:
            status_val = t.get("taskStatusType") or t.get("status")
            if isinstance(status_val, dict):
                status_val = status_val.get("taskStatusType")
            print(f" • [{t.get('taskId')}] ({status_val}) {t.get('title')}")
    else:
        print(f"❌ 오류 ({res.get('status')}): {res.get('error')}")


def cmd_get_task(args):
    ensure_cookie_jar()
    res = api_request("GET", f"/rd/{args.domain_id}/api/v1/tasks/{args.task_id}")
    if res.get("status") == 200:
        print(format_json(res.get("data")))
    else:
        print(f"❌ 오류 ({res.get('status')}): {res.get('error')}")


def cmd_move_mail(args):
    ensure_cookie_jar()
    u = resolve_mail_u(args.u)
    if not u:
        print("❌ 메일 사용자 식별자(u)를 알 수 없습니다. --u 옵션으로 전달해 주세요 (예: --u 100000000000000).")
        sys.exit(1)

    form_payload = build_mail_move_payload(
        u=u,
        mail_sn_list=args.mail_sn_list,
        target_folder_sn=args.target_folder_sn,
        folder_sn=args.folder_sn,
        emails=args.emails,
        auto_move=args.auto_move,
        folder_name=args.folder_name,
    )
    res = api_request(
        method="POST",
        path="/json/select/move",
        base_url=MAIL_BASE_URL,
        form_data=form_payload,
    )
    if res.get("status") == 200:
        print(f"✅ 메일 ({args.mail_sn_list})을 메일함({args.target_folder_sn})으로 성공적으로 이동했습니다.")
        if res.get("data"):
            print(format_json(res.get("data")))
    else:
        print(f"❌ 이동 실패 ({res.get('status')}): {res.get('error')}")



def main():
    parser = argparse.ArgumentParser(description="NAVER WORKS 빠른 관리 CLI")
    subparsers = parser.add_subparsers(dest="command", help="사용 가능한 명령어")

    # login
    p_login = subparsers.add_parser("login", help="브라우저를 열어 네이버웍스 로그인 및 쿠키 자동 연동")
    p_login.add_argument("--timeout", type=int, default=90, help="대기 시간(초)")
    p_login.add_argument("--force", action="store_true", help="강제 브라우저 오픈")
    p_login.set_defaults(func=cmd_login)

    # cookies
    p_cookie = subparsers.add_parser("refresh-cookie", help="Chrome에서 쿠키 최신화")
    p_cookie.set_defaults(func=cmd_refresh_cookies)

    # spaces
    p_spaces = subparsers.add_parser("spaces", help="스페이스 목록 조회")
    p_spaces.add_argument("--domain-id", default=None, help="도메인 ID (생략 시 ID 또는 로그인한 계정에서 자동 확인)")
    p_spaces.set_defaults(func=cmd_list_spaces)

    # space detail
    p_space = subparsers.add_parser("space", help="스페이스 상세 조회")
    p_space.add_argument("space_id", help="Space ID")
    p_space.add_argument("--domain-id", default=None, help="도메인 ID (생략 시 ID 또는 로그인한 계정에서 자동 확인)")
    p_space.set_defaults(func=cmd_get_space)

    # projects list by space
    p_projects = subparsers.add_parser("projects", help="스페이스 하위 프로젝트 목록 조회")
    p_projects.add_argument("space_id", help="Space ID")
    p_projects.add_argument("--domain-id", default=None, help="도메인 ID (생략 시 ID 또는 로그인한 계정에서 자동 확인)")
    p_projects.set_defaults(func=cmd_list_projects)

    # project detail
    p_proj = subparsers.add_parser("project", help="프로젝트 상세 조회")
    p_proj.add_argument("project_id", help="Project ID")
    p_proj.add_argument("--instance-code", default=DEFAULT_INSTANCE_CODE, help="Relay 코드")
    p_proj.set_defaults(func=cmd_get_project)

    # tasks
    p_tasks = subparsers.add_parser("tasks", help="태스크 목록 조회")
    p_tasks.add_argument("project_id", help="Project ID")
    p_tasks.add_argument("--domain-id", default=None, help="도메인 ID (생략 시 ID 또는 로그인한 계정에서 자동 확인)")
    p_tasks.set_defaults(func=cmd_list_tasks)

    # task detail
    p_task = subparsers.add_parser("task", help="태스크 상세 조회")
    p_task.add_argument("task_id", help="Task ID")
    p_task.add_argument("--domain-id", default=None, help="도메인 ID (생략 시 ID 또는 로그인한 계정에서 자동 확인)")
    p_task.set_defaults(func=cmd_get_task)

    # mail move
    p_mail_move = subparsers.add_parser("mail-move", help="메일을 특정 메일함으로 이동")
    p_mail_move.add_argument("mail_sn_list", help="이동할 메일 일련번호 (콤마 구분 또는 단일 SN, 예: c203)")
    p_mail_move.add_argument("target_folder_sn", help="이동 대상 메일함 번호 (예: 101)")
    p_mail_move.add_argument("--folder-sn", default="0", help="현재 메일함 번호 (기본값: 0 - 받은편지함)")
    p_mail_move.add_argument("--u", default=None, help="네이버웍스 메일 사용자 식별자 (예: 100000000000000)")
    p_mail_move.add_argument("--emails", default="", help="이메일 주소 목록")
    p_mail_move.add_argument("--auto-move", default="0", help="자동 이동 여부 (기본값: 0)")
    p_mail_move.add_argument("--folder-name", default="", help="메일함 이름")
    p_mail_move.set_defaults(func=cmd_move_mail)


    args = parser.parse_args()
    if hasattr(args, "domain_id") and not args.domain_id:
        ensure_cookie_jar()
        ids = [getattr(args, k, None) for k in ("space_id", "project_id", "task_id")]
        try:
            args.domain_id = asyncio.run(ensure_domain_id(None, *ids))
        except DomainIdUnknown as e:
            print(f"❌ {e} (예: --domain-id 123456)")
            sys.exit(1)
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

