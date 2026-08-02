from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF

from app.utils.file_validation import document_extension


_UNABLE_TO_PARSE = (
    "Unable to parse document. Upload a text-based PDF, Word (.doc/.docx), or TXT file "
    "(scanned or image-only PDFs are not supported)."
)


def extract_text_from_document(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, Word, or plain-text uploads."""
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    ext = document_extension(filename)
    try:
        if ext == ".pdf":
            return extract_text_from_pdf(file_bytes)
        if ext == ".docx":
            return extract_text_from_docx(file_bytes)
        if ext == ".doc":
            return extract_text_from_doc(file_bytes)
        if ext == ".txt":
            return extract_text_from_txt(file_bytes)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(_UNABLE_TO_PARSE) from exc

    raise ValueError(
        "Unsupported file type. Use PDF, Word (.doc/.docx), or plain text (.txt)."
    )


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF file using PyMuPDF."""
    if not pdf_bytes:
        raise ValueError("Uploaded PDF is empty.")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # pragma: no cover - external parser errors
        raise ValueError(
            "Unable to parse document - the PDF appears corrupt or invalid."
        ) from exc

    try:
        parts: list[str] = []
        for page in doc:
            text = page.get_text("text")
            if text:
                parts.append(text.strip())
        extracted = "\n\n".join(part for part in parts if part)
        if not extracted.strip():
            raise ValueError(_UNABLE_TO_PARSE)
        return extracted.strip()
    finally:
        doc.close()


def extract_text_from_docx(docx_bytes: bytes) -> str:
    """Extract plain text from a .docx file using python-docx."""
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "DOCX support is unavailable. Install python-docx on the server."
        ) from exc

    try:
        doc = Document(io.BytesIO(docx_bytes))
    except Exception as exc:
        raise ValueError(
            "Unable to parse document - the Word document appears corrupt or invalid."
        ) from exc

    parts = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
    extracted = "\n".join(parts).strip()
    if not extracted:
        raise ValueError(_UNABLE_TO_PARSE)
    return extracted


def extract_text_from_doc(doc_bytes: bytes) -> str:
    """
    Extract plain text from legacy binary .doc files.

    Uses antiword when installed; otherwise falls back to a best-effort OLE parse.
    """
    antiword = shutil.which("antiword")
    if antiword:
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
            tmp.write(doc_bytes)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                [antiword, tmp_path],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            text = result.stdout.strip()
            if text:
                return text
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    text = _extract_doc_text_via_ole(doc_bytes)
    if text.strip():
        return text.strip()

    raise ValueError(
        "Unable to parse document from this .doc file. "
        "Convert it to .docx or PDF, or upload a TXT file."
    )


def _extract_doc_text_via_ole(doc_bytes: bytes) -> str:
    """Best-effort .doc text extraction without external binaries."""
    try:
        import olefile
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "Legacy .doc support requires olefile or antiword on the server."
        ) from exc

    if not olefile.isOleFile(io.BytesIO(doc_bytes)):
        raise ValueError("Invalid or corrupted .doc file.")

    ole = olefile.OleFileIO(io.BytesIO(doc_bytes))
    try:
        if not ole.exists("WordDocument"):
            return ""

        raw = ole.openstream("WordDocument").read()
        chunks: list[str] = []

        utf16 = raw.decode("utf-16-le", errors="ignore")
        utf16 = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", utf16)
        chunks.extend(re.findall(r"[\w\s.,;:!?/'\"()-]{4,}", utf16))

        ascii_text = raw.decode("latin-1", errors="ignore")
        ascii_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", ascii_text)
        chunks.extend(re.findall(r"[\w\s.,;:!?/'\"()-]{4,}", ascii_text))

        cleaned = "\n".join(dict.fromkeys(chunk.strip() for chunk in chunks if chunk.strip()))
        return cleaned
    finally:
        ole.close()


def extract_text_from_txt(txt_bytes: bytes) -> str:
    """Read plain text uploads with common encodings."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = txt_bytes.decode(encoding).strip()
            if text:
                return text
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode the text file. Use UTF-8 encoding.")
