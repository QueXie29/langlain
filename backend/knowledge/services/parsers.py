from pathlib import Path


class DocumentParseError(Exception):
    pass


def parse_document(path: str, extension: str) -> str:
    extension = extension.lower()
    try:
        if extension in {".txt", ".md"}:
            return _read_text(Path(path))
        if extension == ".pdf":
            return _read_pdf(Path(path))
        if extension == ".docx":
            return _read_docx(Path(path))
    except DocumentParseError:
        raise
    except Exception as exc:
        raise DocumentParseError(f"解析文件失败：{exc}") from exc
    raise DocumentParseError(f"不支持的文件格式：{extension}")


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError("无法识别文本文件编码，请转换为 UTF-8 后重试。")


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise DocumentParseError("暂不支持有密码的 PDF。") from exc
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)  # 逐页提取 PDF 文本 → 无文本页面用空字符串代替 → 所有页面合并成一个字符串。


def _read_docx(path: Path) -> str:
    from docx import Document as DocxDocument

    document = DocxDocument(str(path))
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells]
            if any(values):
                paragraphs.append(" | ".join(values))
    return "\n\n".join(paragraphs)

