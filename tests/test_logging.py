"""M1 — طبقة الـ Logging غير الحظري: عقد قابل للتحقق."""

from __future__ import annotations

import logging
from logging.handlers import QueueHandler
from pathlib import Path
from queue import Full, Queue

from app.core.logging import (
    _SafeQueueHandler,
    configure_logging,
    get_logger,
    shutdown_logging,
)

ROOT = Path(__file__).resolve().parents[1]


def _queue_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if isinstance(h, QueueHandler)]


def test_configure_logging_is_idempotent_and_queue_backed():
    """استدعاء مزدوج لا يضاعف المُعالجات، والطبقة queue-backed."""
    try:
        configure_logging()
        first = _queue_handlers()
        assert len(first) == 1, "يجب أن يضبط configure_logging معالجاً واحداً"

        configure_logging()  # استدعاء ثانٍ
        assert _queue_handlers() == first, "الاستدعاء الثاني يجب ألّا يضيف معالجاً"
    finally:
        shutdown_logging()

    assert _queue_handlers() == [], "shutdown_logging يزيل معالج الطابور"


def test_get_logger_emits_without_raising():
    """التسجيل عبر الطابور لا يُسقط استثناء ولا يُوقف المسار."""
    try:
        configure_logging()
        logger = get_logger("materiel.test.logging")
        assert logger.name == "materiel.test.logging"

        logger.debug("debug record")
        logger.info("info record")
        logger.warning("warning record")
        logger.error("error record")
        # التسجيل استدعاء fire-and-forget: أي استثناء هنا فشل في العقد
        assert logger.getEffectiveLevel() <= logging.ERROR
    finally:
        shutdown_logging()


def test_queue_handler_never_raises_on_full_queue():
    """الشبكة الأمان: queue ممتلئ لا يُسقط استثناء داخل مسار الطلب."""

    class _FullQueue(Queue):
        def put_nowait(self, item):  # noqa: D102
            raise Full("queue is full")

    handler = _SafeQueueHandler(_FullQueue())
    handler.enqueue(
        logging.LogRecord("x", logging.INFO, __file__, 1, "m", None, None)
    )  # يجب ألا ترمي


def test_app_modules_do_not_use_print():
    """عقد مصدري: لا print() في app/ — كل شيء عبر get_logger()."""
    offenders: list[str] = []
    for py_file in sorted((ROOT / "app").rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        for lineno, line in enumerate(
            py_file.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if line.strip().startswith("print("):
                offenders.append(f"{py_file.relative_to(ROOT)}:{lineno}")
    assert offenders == [], f"print() غير مسموح في app/: {offenders}"
