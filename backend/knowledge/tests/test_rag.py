from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from knowledge.services.rag import REFUSAL, answer_question
from knowledge.services.retrieval import UserDocumentRetriever
from knowledge.services.qwen import ModelServiceError


class FakeQuerySet:
    def __init__(self, values):
        self.values = values

    def annotate(self, **kwargs):
        return self

    def filter(self, **kwargs):
        return self

    def select_related(self, *args):
        return self

    def order_by(self, *args):
        return self

    def __getitem__(self, item):
        return FakeQuerySet(self.values[item]) if isinstance(item, slice) else self.values[item]

    def __iter__(self):
        return iter(self.values)


class FakeClient:
    def __init__(self, answer=""):
        self.answer = answer
        self.chat_called = False
        self.rerank_called = False
        self.ranking = None

    def embed_query(self, question):
        return [0.1] * 1024

    def generate(self, prompt, values):
        self.chat_called = True
        self.messages = prompt.invoke(values).to_messages()
        return self.answer

    def rerank(self, question, texts, top_n):
        self.rerank_called = True
        self.rerank_texts = texts
        return self.ranking if self.ranking is not None else [(i, 0.9 - i * 0.1) for i in range(min(top_n, len(texts)))]


@override_settings(RAG_MIN_SIMILARITY=0.45, RAG_TOP_K=5, RAG_RETRIEVAL_K=20)
class RAGGuardrailTests(SimpleTestCase):
    @patch("knowledge.services.retrieval.DocumentChunk.objects.filter")
    def test_no_match_refuses_without_calling_chat_model(self, mock_filter):
        mock_filter.return_value = FakeQuerySet([])
        client = FakeClient("不应被调用")

        result = answer_question(SimpleNamespace(id=1), "资料外的问题", client)

        self.assertTrue(result.refused)
        self.assertEqual(result.answer, REFUSAL)
        self.assertFalse(client.chat_called)
        self.assertFalse(client.rerank_called)

    @patch("knowledge.services.retrieval.DocumentChunk.objects.filter")
    def test_answer_without_citation_is_rejected(self, mock_filter):
        chunk = self._chunk()
        mock_filter.return_value = FakeQuerySet([chunk])

        result = answer_question(SimpleNamespace(id=1), "问题", FakeClient("一个没有引用的回答"))

        self.assertTrue(result.refused)
        self.assertEqual(result.answer, REFUSAL)

    @patch("knowledge.services.retrieval.DocumentChunk.objects.filter")
    def test_valid_citation_returns_only_cited_source(self, mock_filter):
        chunk = self._chunk()
        mock_filter.return_value = FakeQuerySet([chunk])

        result = answer_question(SimpleNamespace(id=1), "问题", FakeClient("答案。[资料1]"))

        self.assertFalse(result.refused)
        self.assertEqual(result.sources[0]["document_name"], "说明.md")
        self.assertEqual(result.sources[0]["similarity"], 0.8)

    @patch("knowledge.services.retrieval.DocumentChunk.objects.filter")
    def test_invalid_citations_and_explicit_refusal_are_rejected(self, mock_filter):
        mock_filter.return_value = FakeQuerySet([self._chunk()])
        for answer in ("答案。[资料0]", "答案。[资料2]", "答案。[资料1][资料9]", REFUSAL, ""):
            with self.subTest(answer=answer):
                result = answer_question(SimpleNamespace(id=1), "问题", FakeClient(answer))
                self.assertTrue(result.refused)
                self.assertEqual(result.sources, [])

    @patch("knowledge.services.retrieval.DocumentChunk.objects.filter")
    def test_only_cited_document_is_returned_and_context_is_literal(self, mock_filter):
        first, second = self._chunk(), self._chunk()
        second.document_id = 10
        second.content = '{"资料": "这是内容"}'
        mock_filter.return_value = FakeQuerySet([first, second])
        client = FakeClient("答案。[资料2]")
        result = answer_question(SimpleNamespace(id=1), "{问题}", client)
        self.assertEqual([s["document_id"] for s in result.sources], [10])
        self.assertEqual(result.sources[0]["index"], 2)
        self.assertIn(second.content, client.messages[1].content)
        self.assertIn("{问题}", client.messages[1].content)

    @patch("knowledge.services.retrieval.DocumentChunk.objects.filter")
    def test_retriever_scopes_owner_status_threshold_and_limit(self, mock_filter):
        query = MagicMock()
        query.annotate.return_value = query
        query.filter.return_value = query
        query.select_related.return_value = query
        query.order_by.return_value = query
        query.__getitem__.return_value = [self._chunk()]
        mock_filter.return_value = query
        user = SimpleNamespace(id=42)
        docs = UserDocumentRetriever(user=user, client=FakeClient()).invoke("问题")
        mock_filter.assert_called_once_with(
            document__owner=user, document__status="ready",
            metadata__embedding_model=settings.QWEN_EMBED_MODEL,
            metadata__embedding_dimension=settings.EMBEDDING_DIMENSION,
        )
        query.filter.assert_called_once_with(distance__lte=0.55)
        query.order_by.assert_called_once_with("distance")
        query.__getitem__.assert_called_once_with(slice(None, 20))
        self.assertEqual(docs[0].page_content, self._chunk().content)
        self.assertEqual(docs[0].metadata["document_id"], 9)

    @override_settings(RAG_TOP_K=1)
    @patch("knowledge.services.retrieval.DocumentChunk.objects.filter")
    def test_reranking_changes_context_and_citation_order(self, mock_filter):
        first, second = self._chunk(), self._chunk()
        first.content = "较不相关的片段。"
        second.document_id = 10
        second.content = "重排序选中的答案。"
        mock_filter.return_value = FakeQuerySet([first, second])
        client = FakeClient("答案。[资料1]")
        client.ranking = [(1, 0.95)]
        result = answer_question(SimpleNamespace(id=1), "问题", client)
        self.assertEqual(client.rerank_texts, [first.content, second.content])
        self.assertEqual(result.sources[0]["document_id"], 10)
        self.assertEqual(result.sources[0]["rerank_score"], 0.95)
        self.assertIn(second.content, client.messages[1].content)
        self.assertNotIn(first.content, client.messages[1].content)

    @patch("knowledge.services.retrieval.DocumentChunk.objects.filter")
    def test_empty_reranking_refuses_without_generation(self, mock_filter):
        mock_filter.return_value = FakeQuerySet([self._chunk()])
        client = FakeClient()
        client.ranking = []
        self.assertTrue(answer_question(SimpleNamespace(id=1), "问题", client).refused)
        self.assertFalse(client.chat_called)

    @patch("knowledge.services.retrieval.DocumentChunk.objects.filter")
    def test_rerank_failure_is_not_silently_bypassed(self, mock_filter):
        mock_filter.return_value = FakeQuerySet([self._chunk()])
        client = FakeClient()
        with patch.object(client, "rerank", side_effect=ModelServiceError("千问请求超时")):
            with self.assertRaises(ModelServiceError):
                answer_question(SimpleNamespace(id=1), "问题", client)
        self.assertFalse(client.chat_called)

    @staticmethod
    def _chunk():
        document = SimpleNamespace(original_name="说明.md")
        return SimpleNamespace(
            document=document,
            document_id=9,
            chunk_index=0,
            content="这里是可验证的资料内容。",
            distance=0.2,
        )
