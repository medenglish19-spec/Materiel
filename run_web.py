"""
run_web.py
-----------
نقطة تشغيل واحدة للمشروع. الموظفون على الشبكة الداخلية يدخلون عبر:
    http://<عنوان-السيرفر>:8000

للتشغيل:
    python run_web.py
"""

import uvicorn

from app.core.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "web.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.UVICORN_RELOAD,
    )
