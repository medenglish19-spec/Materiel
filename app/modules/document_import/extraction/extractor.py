"""
Local document extraction (offline). Supports PDF/DOCX/XLSX.
Tries Docling if available; falls back to pypdf/python-docx/openpyxl.
Scanned PDF: if extracted text < threshold, tries PaddleOCR (local) if installed.
"""
from __future__ import annotations
from pathlib import Path
import re
import zlib
import zipfile
from xml.etree import ElementTree
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


def _simple_pdf_text(path: Path) -> str:
    """Best-effort fallback for uncompressed text-only PDF content streams.

    Full parsing is delegated to pypdf/Docling when installed. This fallback
    handles ordinary literal-string Tj/TJ operators and does not perform OCR.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > 25 * 1024 * 1024:
        return ""
    pages = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
        stream = match.group(1)
        prefix = data[max(0, match.start() - 512):match.start()]
        if b"/FlateDecode" in prefix:
            try:
                stream = zlib.decompress(stream)
            except zlib.error:
                continue
        pieces = []
        literal_pattern = re.compile(rb"\(((?:\\.|[^\\)])*)\)")
        operators = re.finditer(rb"(\((?:\\.|[^\\)])*\)\s*Tj|\[(.*?)\]\s*TJ)", stream, re.DOTALL)
        for operator in operators:
            payload = operator.group(1) if operator.group(2) is None else operator.group(2)
            for literal in literal_pattern.findall(payload):
                def unescape(match):
                    token = match.group(1)
                    if len(token) == 3 and all(byte in b"01234567" for byte in token):
                        return bytes([int(token, 8)])
                    return {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(token, token)
                decoded = re.sub(rb"\\(\\|\(|\)|[nrtbf]|[0-7]{3})", unescape, literal)
                pieces.append(decoded.decode("latin-1", errors="replace"))
        if pieces:
            pages.append("".join(pieces))
    return "\n\n".join(f"PAGE {index}:\n{text}" for index, text in enumerate(pages, start=1))


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

        if PdfReader is None and not text_parts and not tables:
            if b"/Encrypt" in p.read_bytes()[-4096:]:
                raise ExtractionError("pdf_encrypted", "ملف PDF محمي؛ أزل كلمة المرور أو ثبّت pypdf لدعم الملفات المحمية.")
            fallback = _simple_pdf_text(p)
            if fallback:
                text_parts.append(fallback)

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
        # Read Office Open XML directly: no macros are executed, and the
        # importer remains usable when the optional python-docx package is absent.
        try:
            with zipfile.ZipFile(p) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ExtractionError("docx_invalid", "الملف لا يحتوي مستند Word صالحًا.")
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for paragraph in document.iter(namespace + "p"):
                text = "".join(node.text or "" for node in paragraph.iter(namespace + "t"))
                if text:
                    text_parts.append(text)
            for table in document.iter(namespace + "tbl"):
                rows = []
                for row in table.findall(namespace + "tr"):
                    rows.append(["".join(node.text or "" for node in cell.iter(namespace + "t")) for cell in row.findall(namespace + "tc")])
                if rows:
                    tables.append(ExtractedTable(rows=rows))
        except ExtractionError:
            raise
        except (OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise ExtractionError("docx_corrupt", "ملف DOCX تالف أو غير صالح.") from exc
        if not text_parts and not tables:
            raise ExtractionError("docx_no_content", "لم يُعثر على نص أو جداول قابلة للاستخراج في DOCX.")
        return ExtractedDocument(text="\n".join(text_parts), tables=tables)

    if ext == ".xls":
        try:
            import xlrd  # type: ignore
        except ImportError as exc:
            raise ExtractionError("xls_dependency", "ملفات XLS القديمة تحتاج إلى xlrd؛ احفظ الملف بصيغة XLSX أو CSV.") from exc
        try:
            workbook = xlrd.open_workbook(str(p), on_demand=True)
            for sheet in workbook.sheets():
                rows = [[str(sheet.cell_value(row, col)) for col in range(sheet.ncols)] for row in range(sheet.nrows)]
                rows = [row for row in rows if any(cell.strip() for cell in row)]
                if rows:
                    tables.append(ExtractedTable(rows=rows, name=sheet.name))
            workbook.release_resources()
        except Exception as exc:
            raise ExtractionError("xls_corrupt", "ملف XLS تالف أو غير صالح.") from exc
        if not tables:
            raise ExtractionError("xls_no_content", "لم يُعثر على بيانات قابلة للاستخراج في ملف XLS.")
        return ExtractedDocument(tables=tables)

    if ext == ".xlsx":
        wb = None
        try:
            import openpyxl  # type: ignore

            wb = openpyxl.load_workbook(str(p), data_only=True, read_only=True)
            for ws in wb.worksheets:
                rows = []
                for r in ws.iter_rows(values_only=True):
                    values = ["" if v is None else str(v) for v in r]
                    if any(value.strip() for value in values):
                        rows.append(values)
                if rows:
                    tables.append(ExtractedTable(rows=rows, name=ws.title))
        except ImportError as exc:
            raise ExtractionError("xlsx_dependency", "تعذر قراءة XLSX؛ مكتبة قراءة الجداول غير متاحة.") from exc
        except Exception as exc:
            raise ExtractionError("xlsx_corrupt", "ملف XLSX تالف أو غير صالح.") from exc
        finally:
            if wb is not None:
                wb.close()
        tp = []
        for tb in tables:
            tp.append(f"SHEET: {tb.name or ''}")
            for r in tb.rows[:400]:
                tp.append("\t".join(r))
        if not tables:
            raise ExtractionError("xlsx_no_content", "لم يُعثر على بيانات قابلة للاستخراج في ملف XLSX.")
        return ExtractedDocument(text="\n".join(tp), tables=tables)

    try:
        return ExtractedDocument(text=p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return ExtractedDocument()
