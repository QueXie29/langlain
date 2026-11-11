from django.core.management.base import BaseCommand, CommandError

from knowledge.models import Document
from knowledge.services.ingestion import IngestionError, ingest_document
from knowledge.services.parsers import DocumentParseError
from knowledge.services.qwen import ModelServiceError, QwenClient


class Command(BaseCommand):
    help = "使用当前千问向量模型重新索引本库文档，保留用户、文档记录和源文件。"

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, help="仅重建指定用户的文档；默认重建全部文档。")

    def handle(self, *args, **options):
        documents = Document.objects.order_by("pk")
        if options["user_id"] is not None:
            documents = documents.filter(owner_id=options["user_id"])
        if not documents.exists():
            self.stdout.write("没有需要重新索引的文档。")
            return
        try:
            client = QwenClient()
        except ModelServiceError as exc:
            raise CommandError(str(exc)) from None
        succeeded = failed = 0
        for document in documents.iterator():
            document.status = Document.Status.PROCESSING
            document.error_message = ""
            document.save(update_fields=["status", "error_message", "updated_at"])
            try:
                ingest_document(document, client)
            except (IngestionError, DocumentParseError, ModelServiceError) as exc:
                document.status = Document.Status.FAILED
                document.error_message = str(exc)[:500]
                document.save(update_fields=["status", "error_message", "updated_at"])
                failed += 1
                self.stderr.write(f"文档 {document.pk} 失败：{document.error_message}")
            else:
                succeeded += 1
                self.stdout.write(f"文档 {document.pk} 已重建，共 {document.chunks_count} 个片段。")
        self.stdout.write(f"完成：成功 {succeeded}，失败 {failed}。")
        if failed:
            raise CommandError("部分文档重建失败，修复错误后可以再次运行此命令。")
