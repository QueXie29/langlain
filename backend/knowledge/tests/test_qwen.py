import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

import httpx
from django.test import SimpleTestCase, override_settings
from langchain_core.prompts import ChatPromptTemplate

from knowledge.services.qwen import ModelServiceError, QwenClient


@override_settings(
    DASHSCOPE_API_KEY="test-key",
    DASHSCOPE_BASE_URL="https://qwen.test/api/v1",
    QWEN_CHAT_MODEL="qwen3.8-flash",
    QWEN_EMBED_MODEL="qwen3.7-text-embedding-flash",
    QWEN_RERANK_MODEL="qwen3.7-text-rerank",
    EMBEDDING_DIMENSION=3, QWEN_TIMEOUT=7, QWEN_MAX_TOKENS=700,
)
class LangChainQwenTests(SimpleTestCase):
    """Exercise real LangChain chains and all three native DashScope envelopes."""

    def setUp(self):
        self.requests = []
        self.embedding_response = None
        self.rerank_response = {"output": {"results": [
            {"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2},
        ]}}
        self.answer = "答案。[资料1]"
        self.status = 200
        self.error = None
        http_client = httpx.Client(transport=httpx.MockTransport(self.handle_request))
        self.addCleanup(http_client.close)
        self.client = QwenClient(http_client=http_client)

    def handle_request(self, request):
        payload = json.loads(request.content)
        self.requests.append((request.url.path, payload))
        self.assertEqual(request.headers["authorization"], "Bearer test-key")
        if self.error:
            raise self.error
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "secret test-key", "type": "test"}})
        if "/embeddings/" in request.url.path:
            data = self.embedding_response
            if data is None:
                data = {"output": {"embeddings": [
                    {"text_index": i, "embedding": [i + 0.1, 0.2, 0.3]}
                    for i in reversed(range(len(payload["input"]["texts"])))
                ]}}
            return httpx.Response(200, json=data)
        if "/rerank/" in request.url.path:
            return httpx.Response(200, json=self.rerank_response)
        return httpx.Response(200, json={"output": {"choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": [{"text": self.answer}]}},
        ]}})

    def test_document_and_query_embeddings_use_correct_text_types(self):
        self.assertEqual(self.client.embed(["文档一", "文档二"]), [[0.1, 0.2, 0.3], [1.1, 0.2, 0.3]])
        self.assertEqual(self.client.embed_query("问题"), [0.1, 0.2, 0.3])
        self.assertEqual(self.requests[0][0], "/api/v1/services/embeddings/text-embedding/text-embedding")
        self.assertEqual(self.requests[0][1]["model"], "qwen3.7-text-embedding-flash")
        self.assertEqual(self.requests[0][1]["input"], {"texts": ["文档一", "文档二"]})
        self.assertEqual(self.requests[0][1]["parameters"], {"text_type": "document", "dimension": 3})
        self.assertEqual(self.requests[1][1]["parameters"]["text_type"], "query")

    def test_large_batches_respect_provider_limit(self):
        self.assertEqual(len(self.client.embed(["文档"] * 35)), 35)
        self.assertEqual([len(payload["input"]["texts"]) for _, payload in self.requests], [16, 16, 3])

    def test_flash_index_field_preserves_document_order(self):
        self.embedding_response = {"output": {"embeddings": [
            {"index": 1, "type": "dense", "embedding": [0.4, 0.5, 0.6]},
            {"index": 0, "type": "dense", "embedding": [0.1, 0.2, 0.3]},
        ]}}
        self.assertEqual(self.client.embed(["甲", "乙"]), [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        self.embedding_response["output"]["embeddings"] = [self.embedding_response["output"]["embeddings"][1]]
        self.assertEqual(self.client.embed_query("问题"), [0.1, 0.2, 0.3])

    def test_flash_invalid_indices_are_rejected(self):
        for indices in ([0, 0], [0, 2], [0, True], [0, None]):
            with self.subTest(indices=indices):
                self.embedding_response = {"output": {"embeddings": [
                    {"index": index, "embedding": [0.1, 0.2, 0.3]} for index in indices
                ]}}
                with self.assertRaises(ModelServiceError):
                    self.client.embed(["甲", "乙"])

    def test_empty_inputs_do_not_call_models(self):
        self.assertEqual(self.client.embed([]), [])
        self.assertEqual(self.client.rerank("问题", [], 5), [])
        self.assertEqual(self.requests, [])

    def test_invalid_embedding_count_dimension_and_indices_are_rejected(self):
        for rows in (
            [], [{"text_index": 0, "embedding": [0.1]}],
            [{"text_index": 1, "embedding": [0.1, 0.2, 0.3]}],
            [{"text_index": 0, "embedding": ["bad", 0.2, 0.3]}],
        ):
            with self.subTest(rows=rows):
                self.embedding_response = {"output": {"embeddings": rows}}
                with self.assertRaises(ModelServiceError):
                    self.client.embed(["文档"])

    def test_prompt_chain_preserves_braces_and_qwen_options(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", "只能使用资料。"), ("human", "{context}\n问题：{question}"),
        ])
        answer = self.client.generate(prompt, {"context": '{"key": "value"}', "question": "{问题}"})
        self.assertEqual(answer, self.answer)
        path, payload = self.requests[0]
        self.assertEqual(path, "/api/v1/services/aigc/multimodal-generation/generation")
        self.assertEqual(payload["model"], "qwen3.8-flash")
        self.assertEqual(payload["input"]["messages"][1]["content"], [{"text": '{"key": "value"}\n问题：{问题}'}])
        self.assertFalse(payload["parameters"]["enable_thinking"])
        self.assertEqual(payload["parameters"]["max_tokens"], 700)

    def test_rerank_uses_native_envelope_and_returns_original_indices(self):
        self.assertEqual(self.client.rerank("问题", ["甲", "乙"], 1), [(1, 0.9)])
        path, payload = self.requests[0]
        self.assertEqual(path, "/api/v1/services/rerank/text-rerank/text-rerank")
        self.assertEqual(payload, {
            "model": "qwen3.7-text-rerank", "input": {"query": "问题", "documents": ["甲", "乙"]},
            "parameters": {"top_n": 1},
        })

    def test_bad_rerank_indices_and_scores_are_rejected(self):
        for rows in (
            [{"index": -1, "relevance_score": 0.8}],
            [{"index": 2, "relevance_score": 0.8}],
            [{"index": 0, "relevance_score": 0.8}] * 2,
            [{"index": 0, "relevance_score": 1.2}],
            [{"index": True, "relevance_score": 0.8}],
        ):
            with self.subTest(rows=rows):
                self.rerank_response = {"output": {"results": rows}}
                with self.assertRaises(ModelServiceError):
                    self.client.rerank("问题", ["甲", "乙"], 2)

    def test_empty_answer_is_an_upstream_error(self):
        self.answer = "  "
        with self.assertRaisesRegex(ModelServiceError, "没有返回回答"):
            self.client.generate(ChatPromptTemplate.from_template("{question}"), {"question": "问题"})

    def test_transport_errors_are_translated_for_native_and_chat_calls(self):
        for error, expected in (
            (httpx.ConnectError("offline"), "无法连接"), (httpx.ReadTimeout("slow"), "请求超时"),
        ):
            for operation in (
                lambda: self.client.embed_query("问题"),
                lambda: self.client.generate(ChatPromptTemplate.from_template("{question}"), {"question": "问题"}),
            ):
                with self.subTest(error=error, operation=operation):
                    self.error = error
                    with self.assertRaisesRegex(ModelServiceError, expected):
                        operation()

    def test_http_errors_do_not_expose_upstream_body(self):
        for status in (401, 403, 404, 429, 500):
            self.status = status
            for operation in (
                lambda: self.client.embed_query("问题"),
                lambda: self.client.rerank("问题", ["甲"], 1),
                lambda: self.client.generate(ChatPromptTemplate.from_template("{question}"), {"question": "问题"}),
            ):
                with self.subTest(status=status, operation=operation):
                    with self.assertRaises(ModelServiceError) as caught:
                        operation()
                    self.assertIn(str(status), str(caught.exception))
                    self.assertNotIn("test-key", str(caught.exception))

    @override_settings(DASHSCOPE_API_KEY="")
    def test_missing_key_is_actionable(self):
        with self.assertRaisesRegex(ModelServiceError, "DASHSCOPE_API_KEY"):
            QwenClient()


@override_settings(DASHSCOPE_API_KEY="test-key", QWEN_TIMEOUT=2)
class QwenProxyRoutingTests(SimpleTestCase):
    def test_direct_mode_works_when_environment_proxy_fails(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                # 代理请求携带完整 URL；直接请求只携带路径。
                if self.path.startswith("http://"):
                    self.send_error(502, "Test proxy unavailable")
                    return
                body = json.dumps({"output": {"results": [{"index": 0, "relevance_score": 0.9}]}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}"
            proxy_env = {
                "HTTP_PROXY": endpoint, "HTTPS_PROXY": endpoint, "ALL_PROXY": endpoint, "NO_PROXY": "",
                "http_proxy": endpoint, "https_proxy": endpoint, "all_proxy": endpoint, "no_proxy": "",
            }
            with patch.dict(os.environ, proxy_env), override_settings(DASHSCOPE_BASE_URL=endpoint + "/api/v1"):
                with override_settings(QWEN_TRUST_ENV=False):
                    self.assertEqual(QwenClient().rerank("问题", ["文档"], 1), [(0, 0.9)])
                with override_settings(QWEN_TRUST_ENV=True):
                    with self.assertRaisesRegex(ModelServiceError, "HTTP 502"):
                        QwenClient().rerank("问题", ["文档"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
