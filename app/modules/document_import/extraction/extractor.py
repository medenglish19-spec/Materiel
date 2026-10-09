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
            from docling.document_converter import DocumentConverter  # type: ignore

            try:
                conv = DocumentConverter()
                res = conv.convert(str(p))
                doc = res.document
                try:
                    text_parts.append(doc.export_to_text())
                except Exception:
                    pass
                try:
                    for t in getattr(doc, "tables", []) or []:
                        rows = []
                        try:
                            for r in t.data:
                                rows.append([getattr(c, "text", str(c)) for c in r])
                        except Exception:
                            pass
                        if rows:
                            tables.append(ExtractedTable(rows=rows))
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass

        if not text_parts:
            try:
                from pypdf import PdfReader

                reader = PdfReader(str(p))
                for i, pg in enumerate(reader.pages, start=1):
                    try:
                        x = pg.extract_text() or ""
                    except Exception:
                        x = ""
                    if x:
                        text_parts.append(f"PAGE {i}:\n{x}")
            except Exception:
                pass

        txt = "\n\n".join(text_parts)
        if len(txt.strip()) < 50:
            try:
                from paddleocr import PaddleOCR  # type: ignore

                ocr = PaddleOCR(use_angle_cls=False, lang="en")
                try:
                    res = ocr.ocr(str(p), cls=False)
                except TypeError:
                    res = ocr.ocr(str(p))
                lines = []
                for pr in (res if isinstance(res, list) else [res]):
                    if not pr:
                        continue
                    for it in pr:
                        if not it:
                            continue
                        try:
                            _, ti, _ = it
                        except Exception:
                            continue
                        if ti:
                            lines.append(str(ti))
                if lines:
                    txt = txt + "\n\n[OCR]\n" + "\n".join(lines)
                    ocr_used = True
                    ocr_engine = "paddleocr"
            except Exception:
                pass
        return ExtractedDocument(text=txt, tables=tables, ocr_used=ocr_used, ocr_engine=ocr_engine)

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