from django.contrib.auth import get_user_model
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APITestCase

from knowledge.models import Document
from knowledge.services.qwen import ModelServiceError


class AuthenticationAPITests(APITestCase):
    def test_register_returns_user_and_tokens(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "new_user",
                "email": "new@example.com",
                "password": "A-strong-personal-pass-284!",
                "password_confirm": "A-strong-personal-pass-284!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["username"], "new_user")
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_returns_authenticated_user(self):
        get_user_model().objects.create_user("existing", password="A-good-pass-284!")

        response = self.client.post(
            "/api/auth/login/",
            {"username": "existing", "password": "A-good-pass-284!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["username"], "existing")
        self.assertNotIn("password", response.data["user"])


class DocumentIsolationAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.alice = user_model.objects.create_user("alice", password="pass")
        self.bob = user_model.objects.create_user("bob", password="pass")
        self.alice_document = Document.objects.create(
            owner=self.alice,
            original_name="alice.md",
            file="documents/alice.md",
            file_type="md",
            file_size=20,
            status=Document.Status.READY,
        )
        self.bob_document = Document.objects.create(
            owner=self.bob,
            original_name="bob.md",
            file="documents/bob.md",
            file_type="md",
            file_size=20,
            status=Document.Status.READY,
        )
        self.client.force_authenticate(self.alice)

    def test_list_only_contains_current_users_documents(self):
        response = self.client.get("/api/documents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["original_name"] for item in response.data], ["alice.md"])

    def test_user_cannot_delete_another_users_document(self):
        response = self.client.delete(f"/api/documents/{self.bob_document.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Document.objects.filter(pk=self.bob_document.id).exists())

    def test_anonymous_user_cannot_list_documents(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/documents/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("knowledge.views.answer_question", side_effect=ModelServiceError("千问请求超时"))
    def test_model_failure_returns_502(self, answer):
        response = self.client.post("/api/ask/", {"question": "我的文档讲了什么？"})
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(str(response.data["detail"]), "千问请求超时")
