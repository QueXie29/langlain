from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITransactionTestCase

from knowledge.models import Document
from knowledge.services.qwen import ModelServiceError
from knowledge.services.parsers import DocumentParseError


class DocumentUploadFailureAPITests(APITransactionTestCase):
    def setUp(self):
        # Use real commits/rollbacks and isolate uploaded files from user data.
        media_directory = TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=media_directory.name))
        self.qwen = self.enterContext(
            patch("knowledge.services.ingestion.QwenClient")
        ).return_value
        self.user = get_user_model().objects.create_user("uploader")
        self.client.force_authenticate(self.user)
        self.client.raise_request_exception = False

    def assert_failed_upload(self, response, filename):
        document = Document.objects.get(owner=self.user, original_name=filename)
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertTrue(document.error_message)
        self.assertEqual(document.chunks_count, 0)
        self.assertFalse(document.chunks.exists())
        self.assertTrue(document.file.storage.exists(document.file.name))
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

        listing = self.client.get("/api/documents/")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        listed_document = next(item for item in listing.data if item["id"] == document.id)
        self.assertEqual(listed_document["status"], Document.Status.FAILED)
        self.assertEqual(listed_document["error_message"], document.error_message)
        return document

    def test_corrupt_files_are_retained_as_failed(self):
        for filename in ("broken.pdf", "broken.docx"):
            with self.subTest(filename=filename):
                response = self.client.post(
                    "/api/documents/",
                    {"file": SimpleUploadedFile(filename, b"not a valid document")},
                    format="multipart",
                )

                document = self.assert_failed_upload(response, filename)
                self.assertTrue(document.error_message.startswith("解析文件失败："))
                self.assertEqual(str(response.data["detail"]), document.error_message)
                self.qwen.embed.assert_not_called()

    def test_parse_error_message_is_truncated_when_saved(self):
        message = "解析文件失败：" + "错误" * 300
        with patch(
            "knowledge.services.ingestion.parse_document",
            side_effect=DocumentParseError(message),
        ):
            response = self.client.post(
                "/api/documents/",
                {"file": SimpleUploadedFile("broken.txt", b"content")},
                format="multipart",
            )

        document = self.assert_failed_upload(response, "broken.txt")
        self.assertEqual(document.error_message, message[:500])
        self.qwen.embed.assert_not_called()

    def test_qwen_failure_retains_failed_document(self):
        self.qwen.embed.side_effect = ModelServiceError("千问请求超时")
        response = self.client.post(
            "/api/documents/",
            {"file": SimpleUploadedFile("timeout.txt", b"some text")},
            format="multipart",
        )

        document = self.assert_failed_upload(response, "timeout.txt")
        self.assertEqual(document.error_message, "千问请求超时")

    def test_chunk_write_failure_rolls_back_chunks_but_retains_failed_document(self):
        self.qwen.embed.return_value = [[0.0] * settings.EMBEDDING_DIMENSION]

        def partially_write_chunks(chunks):
            chunks[0].save(force_insert=True)
            raise IntegrityError("chunk write failed")

        with patch(
            "knowledge.services.ingestion.DocumentChunk.objects.bulk_create",
            side_effect=partially_write_chunks,
        ):
            response = self.client.post(
                "/api/documents/",
                {"file": SimpleUploadedFile("rollback.txt", b"some text")},
                format="multipart",
            )

        document = self.assert_failed_upload(response, "rollback.txt")
        self.assertEqual(document.error_message, "chunk write failed")
