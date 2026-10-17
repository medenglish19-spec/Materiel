"""
Local document extraction (offline). Supports PDF/DOCX/XLSX.
Tries Docling if available; falls back to pypdf/python-docx/openpyxl.
Scanned PDF: if extracted text < threshold, tries PaddleOCR (local) if installed.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class ExtractedTable:
    def __init__(self, rows: List[List[str]] | None = None, name: Optional[str] = None, page: Optional[int] = None):
        self.rows = rows or []
        self.name = name
        self.page = page


class ExtractionError(ValueError):
    """A user-correctable error while reading an uploaded document."""

    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message
        super().__init__(message)


class ExtractedDocument:
    def __init__(self, text: str = "", tables: List[ExtractedTable] | None = None, metadata: Dict[str, Any] | None = None, ocr_used: bool = False, ocr_engine: Optional[str] = None):
        self.text = text or ""
        self.tables = tables or []
        self.metadata = metadata or {}
        self.ocr_used = ocr_used
        self.ocr_engine = ocr_engine


def extract_document(path: Union[str, Path], **kwargs) -> ExtractedDocument:
    p = Path(path)
    ext = p.suffix.lower()
    text_parts: List[str] = []
    tables: List[ExtractedTable] = []
    ocr_used = False
    ocr_engine = None

    if ext == ".pdf":
        try:
            with p.open("rb") as source:
                signature = source.read(1024)
        except OSError as exc:
            raise ExtractionError("pdf_corrupt", "تعذر قراءة ملف PDF.") from exc
        if b"%PDF-" not in signature:
            raise ExtractionError("pdf_corrupt", "ملف PDF تالف أو غير صالح.")

        # Docling is optional; use it for richer tables when installed.
        try:
            from docling.document_converter import DocumentConverter  # type: ignore
        except ImportError:
            pass
        else:
            try:
                converted = DocumentConverter().convert(str(p)).document
                text = converted.export_to_text()
                if text:
                    text_parts.append(text)
                for table in getattr(converted, "tables", []) or []:
                    rows = []
                    try:
                        for row in table.data:
                            rows.append([getattr(cell, "text", str(cell)) for cell in row])
                    except (AttributeError, TypeError, ValueError):
                        rows = []
                    if rows:
                        tables.append(ExtractedTable(rows=rows))
            except Exception:
                # Fall back to pypdf when Docling cannot process this file.
                pass

        try:
            from pypdf import PdfReader
        except ImportError:
            PdfReader = None

        if PdfReader is not None:
            try:
                reader = PdfReader(str(p), strict=False)
                if reader.is_encrypted:
                    try:
                        unlocked = reader.decrypt("")
                    except Exception:
                        unlocked = 0
                    if not unlocked:
                        raise ExtractionError(
                            "pdf_encrypted",
                            "ملف PDF محمي بكلمة مرور. أزل الحماية ثم أعد المحاولة.",
                        )
                if not text_parts:
                    for page_number, page in enumerate(reader.pages, start=1):
                        try:
                            page_text = page.extract_text() or ""
                        except Exception:
                            page_text = ""
                        if page_text.strip():
                            text_parts.append(f"PAGE {page_number}:\n{page_text}")
            except ExtractionError:
                raise
            except Exception as exc:
                if not text_parts and not tables:
                    raise ExtractionError("pdf_corrupt", "ملف PDF تالف أو غير صالح.") from exc

        text = "\n\n".join(text_parts)
        if not text.strip():
            try:
                from paddleocr import PaddleOCR  # type: ignore

                ocr = PaddleOCR(use_angle_cls=False, lang="en")
                try:
                    result = ocr.ocr(str(p), cls=False)
                except TypeError:
                    result = ocr.ocr(str(p))
                lines = []
                for page_result in (result if isinstance(result, list) else [result]):
                    if not page_result:
                        continue
                    for item in page_result:
                        if not item:
                            continue
                        try:
                            _, detected_text, _ = item
                        except (TypeError, ValueError):
                            continue
                        if detected_text:
                            lines.append(str(detected_text))
                if lines:
                    text = text + "\n\n[OCR]\n" + "\n".join(lines)
                    ocr_used = True
                    ocr_engine = "paddleocr"
            except ImportError:
                pass
            except Exception:
                # OCR is optional; report a clear no-text error below.
                pass

        if not text.strip() and not tables:
            raise ExtractionError(
                "pdf_no_text",
                "لم يُعثر على نص قابل للاستخراج. قد يكون الملف ممسوحًا ضوئيًا؛ استخدم ملفًا نصيًا أو فعّل OCR.",
            )
        return ExtractedDocument(text=text, tables=tables, ocr_used=ocr_used, ocr_engine=ocr_engine)

    if ext == ".docx":
        try:
            from docx import Document  # type: ignore

            d = Document(str(p))
            for para in d.paragraphs:
                if para.text:
                    text_parts.append(para.text)
            for t in d.tables:
                rows = []
                for tr in t.rows:
                    rows.append([tc.text for tc in tr.cells])
                if rows:
                    tables.append(ExtractedTable(rows=rows))
        except Exception:
            pass
        return ExtractedDocument(text="\n".join(text_parts), tables=tables)

    if ext == ".xlsx":
        try:
            import openpyxl  # type: ignore

            wb = openpyxl.load_workbook(str(p), data_only=True, read_only=True)
            for ws in wb.worksheets:
                rows = []
                for r in ws.iter_rows(values_only=True):
                    rows.append(["" if v is None else str(v) for v in r])
                if rows:
                    tables.append(ExtractedTable(rows=rows, name=ws.title))
            wb.close()
        except Exception:
            pass
        tp = []
        for tb in tables:
            tp.append(f"SHEET: {tb.name or ''}")
            for r in tb.rows[:400]:
                tp.append("\t".join(r))
        return ExtractedDocument(text="\n".join(tp), tables=tables)

    try:
        return ExtractedDocument(text=p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return ExtractedDocument()