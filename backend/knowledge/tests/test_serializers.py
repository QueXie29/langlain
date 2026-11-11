from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from knowledge.serializers import DocumentUploadSerializer, QuestionSerializer


class SerializerTests(SimpleTestCase):
    def test_rejects_unsupported_extension(self):
        serializer = DocumentUploadSerializer(
            data={"file": SimpleUploadedFile("data.exe", b"content")}
        )
        self.assertFalse(serializer.is_valid())

    @override_settings(MAX_UPLOAD_SIZE_MB=1)
    def test_rejects_large_file(self):
        serializer = DocumentUploadSerializer(
            data={"file": SimpleUploadedFile("data.txt", b"x" * (1024 * 1024 + 1))}
        )
        self.assertFalse(serializer.is_valid())

    def test_question_is_trimmed(self):
        serializer = QuestionSerializer(data={"question": "  文档说了什么？  "})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["question"], "文档说了什么？")

