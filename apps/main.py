import os
import uvicorn
from app.config import HOST, PORT

if __name__ == "__main__":
    port = int(os.getenv("PORT", PORT))
    host = os.getenv("HOST", HOST)
    # 코드 변경 시 자동 재시작은 개발용(RELOAD=true, run.sh 기본값)에서만 사용. Docker/운영에서는 꺼짐.
    reload = os.getenv("RELOAD", "").strip().lower() in ("1", "true", "yes")
    print(f"🚀 NAVER WORKS FastAPI 서버 실행 중: http://{host}:{port} (문서: http://{host}:{port}/docs)")
    apps_dir = os.path.dirname(os.path.abspath(__file__))
    uvicorn.run("app.main:app", host=host, port=port, reload=reload, app_dir=apps_dir,
                reload_dirs=[apps_dir] if reload else None)
