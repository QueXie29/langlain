from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from knowledge.models import Document, DocumentChunk
from knowledge.services.ingestion import ingest_document
from knowledge.services.qwen import ModelServiceError


class ReindexDocumentTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=media.name))
        self.model_client = self.enterContext(
            patch("knowledge.management.commands.reindex_documents.QwenClient")
        ).return_value
        self.model_client.embed.return_value = [[0.1] * settings.EMBEDDING_DIMENSION]
        self.owner = get_user_model().objects.create_user("index-owner")
        self.document = self.make_document(self.owner)

    def make_document(self, owner):
        document = Document.objects.create(
            owner=owner, original_name="note.txt", file_type="txt", file_size=12,
            status=Document.Status.READY, chunks_count=1,
        )
        document.file.save("note.txt", ContentFile("这是一份知识库测试文档。".encode("utf-8")))
        DocumentChunk.objects.create(
            document=document, chunk_index=0, content="旧片段",
            embedding=[0.2] * settings.EMBEDDING_DIMENSION, metadata={"filename": "note.txt"},
        )
        return document

    def test_ingestion_records_embedding_identity_and_preserves_document(self):
        old_name = self.document.file.name
        ingest_document(self.document, self.model_client)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.READY)
        self.assertEqual(self.document.file.name, old_name)
        self.assertEqual(self.document.chunks_count, 1)
        chunk = self.document.chunks.get()
        self.assertNotEqual(chunk.content, "旧片段")
        self.assertEqual(chunk.metadata["embedding_model"], settings.QWEN_EMBED_MODEL)
        self.assertEqual(chunk.metadata["embedding_dimension"], settings.EMBEDDING_DIMENSION)

    def test_reindex_user_filter_does_not_change_another_users_documents(self):
        other = self.make_document(get_user_model().objects.create_user("other-owner"))
        call_command("reindex_documents", user_id=self.owner.pk, stdout=StringIO())
        self.assertIn("embedding_model", self.document.chunks.get().metadata)
        self.assertNotIn("embedding_model", other.chunks.get().metadata)
        self.assertEqual(other.chunks.get().content, "旧片段")

    def test_failed_reindex_retains_source_and_old_chunks_but_disables_document(self):
        self.model_client.embed.side_effect = ModelServiceError("千问请求超时")
        with self.assertRaises(CommandError):
            call_command("reindex_documents", stdout=StringIO(), stderr=StringIO())
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.FAILED)
        self.assertIn("千问请求超时", self.document.error_message)
        self.assertTrue(self.document.file.storage.exists(self.document.file.name))
        self.assertEqual(self.document.chunks.get().content, "旧片段")
