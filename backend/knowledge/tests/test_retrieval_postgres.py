from unittest import skipUnless
from unittest.mock import Mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings

from knowledge.models import Document, DocumentChunk
from knowledge.services.retrieval import UserDocumentRetriever


@skipUnless(connection.vendor == "postgresql", "需要真实 PostgreSQL/pgvector")
@override_settings(RAG_RETRIEVAL_K=2, RAG_TOP_K=1, RAG_MIN_SIMILARITY=0.45)
class PostgreSQLRetrievalTests(TestCase):
    def test_only_current_owner_model_ready_and_relevant_chunks_reach_reranker(self):
        owner = get_user_model().objects.create_user("retriever-owner")
        other = get_user_model().objects.create_user("retriever-other")
        identity = {
            "embedding_model": settings.QWEN_EMBED_MODEL,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
        }

        def vector(x, y=0):
            return [x, y] + [0.0] * (settings.EMBEDDING_DIMENSION - 2)

        def chunk(name, embedding, user=owner, state=Document.Status.READY, metadata=None):
            document = Document.objects.create(
                owner=user, original_name=name, file=f"documents/{name}",
                file_type="txt", file_size=10, status=state, chunks_count=1,
            )
            return DocumentChunk.objects.create(
                document=document, chunk_index=0, content=name, embedding=embedding,
                metadata=identity if metadata is None else metadata,
            )

        chunk("first.txt", vector(1))
        selected = chunk("second.txt", vector(0.8, 0.6))
        chunk("other-user.txt", vector(1), user=other)
        chunk("failed.txt", vector(1), state=Document.Status.FAILED)
        chunk("legacy.txt", vector(1), metadata={})
        chunk("other-model.txt", vector(1), metadata={**identity, "embedding_model": "old-model"})
        chunk("other-dimension.txt", vector(1), metadata={**identity, "embedding_dimension": 3})
        chunk("irrelevant.txt", vector(-1))
        client = Mock()
        client.embed_query.return_value = vector(1)
        client.rerank.return_value = [(1, 0.97)]

        documents = UserDocumentRetriever(user=owner, client=client).invoke("问题")

        client.rerank.assert_called_once_with("问题", ["first.txt", "second.txt"], 1)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata["document_id"], selected.document_id)
        self.assertEqual(documents[0].metadata["similarity"], 0.8)
        self.assertEqual(documents[0].metadata["rerank_score"], 0.97)
