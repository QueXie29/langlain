from typing import Any

from django.conf import settings
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document as RetrievedDocument
from langchain_core.retrievers import BaseRetriever
from pgvector.django import CosineDistance

from knowledge.models import Document, DocumentChunk


class UserDocumentRetriever(BaseRetriever):
    """Adapt the existing owner-scoped pgvector query to LangChain Documents."""

    user: Any
    client: Any

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[RetrievedDocument]:
        query_embedding = self.client.embed_query(query)
        matches = (
            DocumentChunk.objects.filter(
                document__owner=self.user,
                document__status=Document.Status.READY,
                metadata__embedding_model=settings.QWEN_EMBED_MODEL,
                metadata__embedding_dimension=settings.EMBEDDING_DIMENSION,
            )
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .filter(distance__lte=1.0 - settings.RAG_MIN_SIMILARITY)
            .select_related("document")
            .order_by("distance")[: max(settings.RAG_RETRIEVAL_K, settings.RAG_TOP_K)]
        )
        candidates = [
            RetrievedDocument(
                page_content=chunk.content,
                metadata={
                    "document_id": chunk.document_id,
                    "document_name": chunk.document.original_name,
                    "chunk_index": chunk.chunk_index,
                    "similarity": round(1.0 - float(chunk.distance), 4),
                },
            )
            for chunk in matches
        ]
        if not candidates:
            return []
        ranking = self.client.rerank(query, [doc.page_content for doc in candidates], settings.RAG_TOP_K)
        results = []
        for index, score in ranking:
            doc = candidates[index]
            doc.metadata["rerank_score"] = round(score, 4)
            results.append(doc)
        return results
