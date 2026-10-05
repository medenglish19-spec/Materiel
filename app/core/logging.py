"""
core/logging.py
---------------
طبقة تسجيل غير حظري (Asynchronous) وبسيطة.

التصميم:
- سجل واحد على الـ root logger عبر QueueHandler => كل استدعاء log() في مسار
  الطلب يضع السجل في طابور في الذاكرة فقط (put_nowait) ولا ينتظر أي I/O.
- خيط (QueueListener) واحد يستهلك الطابور ويكتب إلى stderr + ملف دوّار.
- المستويات: DEBUG / INFO / WARNING / ERROR فقط.
- الاستهلاك لا يُوقف الطابور مرتين، وإعادة التشغيل آمنة.

الاستخدام:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("...")
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from queue import Queue
from typing import Optional

from app.core.config import settings

__all__ = ["get_logger", "configure_logging", "shutdown_logging"]

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_QUEUE: Optional[Queue] = None
_LISTENER: Optional[QueueListener] = None
# المُعالجات تُبنى مرة واحدة وتُعاد استخدامها عبر دورات configure/shutdown
# (كل دورة يفتحها جديداً كان سيُسجّل تسريب مقابض ملفات على Windows).
_OUTPUT_HANDLERS: Optional[list] = None


class _SafeQueueHandler(QueueHandler):
    """QueueHandler لا يُسقط أبداً استثناء داخل مسار الطلب."""

    def enqueue(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            self.queue.put_nowait(record)
        except Exception:  # pragma: no cover - safety net
            pass


def get_logger(name: str) -> logging.Logger:
    """إرجاع مسجّل بالاسم. آمن قبل configure_logging()."""
    return logging.getLogger(name)


class _TolerantRotatingFileHandler(RotatingFileHandler):
    """دوران السجل بقدر الإمكان: فشل التدوير لا يُسقط السجل.

    ``doRollover()`` يعيد تسمية ``app.log`` إلى ``app.log.1``، وعلى ويندوز يفشل
    ذلك بـ ``PermissionError`` متى كان أي عملية أخرى تمسك الملف مفتوحاً — وهو
    الحال الطبيعي هنا، إذ قد يعمل أكثر من خادم على الملف نفسه. الصنف الأصلي
    يترك الخطأ يخرج من ``emit()``: تضيع السجلات المكتوبة في تلك اللحظة،
    ويُطبع ``--- Logging error ---`` على stderr فيخفي ما حدث بدل أن يعلنه.

    فقدان الدوران أمرٌ محتمل، وفقدان السجلات مع traceback فوقه لا. لذا يُبتلع
    الفشل وتُعاد فتح اللغة على الملف نفسه لتستمر الكتابة.
    """

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError:
            # لم يُدوَّر شيء، لكن المقبض المفتوح ما زال هو السجل الحالي.
            # إعادة فتحه تُبقي السجلات تجري بدل أن تضيع.
            try:
                if self.stream:
                    self.stream.close()
                self.stream = self._open()
            except OSError:  # pragma: no cover - لا سبيل للتبليغ من هنا
                pass


def _build_output_handlers() -> list:
    level = getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO)

    stream = logging.StreamHandler(stream=sys.stderr)
    stream.setFormatter(logging.Formatter(_LOG_FORMAT))
    stream.setLevel(level)

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = _TolerantRotatingFileHandler(
        log_dir / "app.log",
        maxBytes=1_000_000,  # 1 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    file_handler.setLevel(level)

    return [stream, file_handler]


def _build_listener() -> QueueListener:
    global _OUTPUT_HANDLERS
    if _OUTPUT_HANDLERS is None:
        _OUTPUT_HANDLERS = _build_output_handlers()
    return QueueListener(
        _QUEUE,  # type: ignore[arg-type]
        *_OUTPUT_HANDLERS,
        respect_handler_level=True,
    )


def configure_logging() -> None:
    """تهيئة الطبقة مرة واحدة؛ استدعاء متكرر لا يضاعف المُعالجات."""
    global _QUEUE, _LISTENER
    if _LISTENER is not None:
        return

    level = getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # إزالة أي QueueHandler قديم (بعد shutdown) حتى لا يتراكم.
    for handler in [
        h for h in list(root.handlers) if isinstance(h, QueueHandler)
    ]:
        root.removeHandler(handler)

    _QUEUE = Queue(-1)
    queue_handler = _SafeQueueHandler(_QUEUE)
    queue_handler.setLevel(level)
    root.addHandler(queue_handler)

    _LISTENER = _build_listener()
    _LISTENER.start()


def shutdown_logging() -> None:
    """تفريغ الطابور وإيقاف خيط الكتابة عند إغلاق التطبيق."""
    global _QUEUE, _LISTENER
    if _LISTENER is None:
        return
    _LISTENER.stop()  # يستهلك ما تبقّى ثم ينتهي
    _LISTENER = None
    _QUEUE = None
    root = logging.getLogger()
    for handler in [h for h in list(root.handlers) if isinstance(h, QueueHandler)]:
        root.removeHandler(handler)
