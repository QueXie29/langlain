from django.conf import settings
from django.db import transaction

from knowledge.models import Document, DocumentChunk

from .chunking import chunk_text
from .qwen import QwenClient
from .parsers import DocumentParseError, parse_document


class IngestionError(Exception):
    pass


def ingest_document(document: Document, client: QwenClient | None = None) -> None:
    client = client or QwenClient()
    try:
        text = parse_document(document.file.path, f".{document.file_type}")
        if len(text) > settings.MAX_EXTRACTED_CHARS:
            raise IngestionError(
                f"文档提取文本超过 {settings.MAX_EXTRACTED_CHARS} 字符，请拆分后上传。"
            )
        chunks = chunk_text(text, settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP)
        if not chunks:
            raise IngestionError("文档中没有可提取的文字；扫描版 PDF 请先进行 OCR。")

        embeddings: list[list[float]] = []
        batch_size = 16
        for start in range(0, len(chunks), batch_size):
            embeddings.extend(client.embed(chunks[start : start + batch_size]))

        with transaction.atomic():
            document.chunks.all().delete()
            DocumentChunk.objects.bulk_create(
                [
                    DocumentChunk(
                        document=document,
                        chunk_index=index,
                        content=content,
                        embedding=embeddings[index],
                        metadata={
                            "filename": document.original_name,
                            "embedding_model": settings.QWEN_EMBED_MODEL,
                            "embedding_dimension": settings.EMBEDDING_DIMENSION,
                        },
                    )
                    for index, content in enumerate(chunks)
                ]
            )
            document.status = Document.Status.READY
            document.chunks_count = len(chunks)
            document.error_message = ""
            document.save(update_fields=["status", "chunks_count", "error_message", "updated_at"])
    except (DocumentParseError, IngestionError):
        raise
    except Exception as exc:
        raise IngestionError(str(exc)) from exc
