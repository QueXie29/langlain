import math
from collections.abc import Callable, Sequence
from contextlib import contextmanager

import httpx
from django.conf import settings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field


class ModelServiceError(Exception):
    """A safe, user-facing error from the configured model provider."""


def _http_error(status: int) -> ModelServiceError:
    hints = {
        400: "请检查模型名称、输入长度和请求参数。",
        401: "请检查 DASHSCOPE_API_KEY 及其所属地域/业务空间。",
        403: "请检查模型调用权限、账户额度及业务空间。",
        404: "请检查接口地址和模型名称。",
        429: "请求过于频繁或额度不足，请稍后重试并检查账户额度。",
    }
    return ModelServiceError(f"千问请求失败（HTTP {status}）。" + hints.get(status, "请稍后重试。"))


@contextmanager
def _translate_errors():
    try:
        yield
    except httpx.TimeoutException as exc:
        raise ModelServiceError("千问请求超时，请稍后重试。") from exc
    except httpx.RequestError as exc:
        raise ModelServiceError("无法连接千问服务，请检查接口地址和网络。") from exc
    except httpx.HTTPStatusError as exc:
        raise _http_error(exc.response.status_code) from exc
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        # 不将上游原始响应/异常回传浏览器，避免包含凭据或文档原文。
        raise ModelServiceError("千问返回的数据格式不正确。") from exc


class QwenChatModel(BaseChatModel):
    """LangChain chat adapter for DashScope MultiModalConversation's HTTP API."""

    request: Callable = Field(exclude=True, repr=False)
    model_name: str

    @property
    def _llm_type(self) -> str:
        return "qwen-dashscope"

    @property
    def _identifying_params(self) -> dict:
        return {"model_name": self.model_name}

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        roles = {"system": "system", "human": "user", "ai": "assistant"}
        with _translate_errors():
            native_messages = []
            for message in messages:
                if message.type not in roles or not isinstance(message.content, str):
                    raise ModelServiceError("当前知识库问答仅支持文本消息。")
                native_messages.append({
                    "role": roles[message.type], "content": [{"text": message.content}],
                })
            parameters = {
                "temperature": 0.1, "max_tokens": settings.QWEN_MAX_TOKENS,
                "enable_thinking": False,
            }
            if stop:
                parameters["stop"] = stop
            data = self.request("services/aigc/multimodal-generation/generation", {
                "model": self.model_name, "input": {"messages": native_messages}, "parameters": parameters,
            })
            content = data["output"]["choices"][0]["message"]["content"]
            if not isinstance(content, list):
                raise ModelServiceError("千问返回的回答格式不正确。")
            answer = "".join(block["text"] for block in content if "text" in block)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer))])


class QwenEmbeddings(Embeddings):
    """LangChain embedding interface with DashScope document/query semantics."""

    def __init__(self, request):
        self._request = request

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]

    def _embed(self, texts: list[str], text_type: str) -> list[list[float]]:
        vectors = []
        # qwen3.7-text-embedding-flash 每次最多 20 条，保留原来的 16 条批量大小。
        for start in range(0, len(texts), 16):
            batch = texts[start : start + 16]
            data = self._request("services/embeddings/text-embedding/text-embedding", {
                "model": settings.QWEN_EMBED_MODEL,
                "input": {"texts": batch},
                "parameters": {
                    "text_type": text_type,
                    "dimension": settings.EMBEDDING_DIMENSION,
                },
            })
            with _translate_errors():
                rows = data["output"]["embeddings"]
                if not isinstance(rows, list) or len(rows) != len(batch):
                    raise ModelServiceError("千问返回的向量数量不正确。")
                # 当前 Flash 接口返回 index，较早的 DashScope 接口返回 text_index。
                indices = [row["text_index"] if "text_index" in row else row["index"] for row in rows]
                if any(type(index) is not int for index in indices) or sorted(indices) != list(range(len(batch))):
                    raise ModelServiceError("千问返回的向量索引不正确。")
                embeddings = [row["embedding"] for _, row in sorted(zip(indices, rows), key=lambda item: item[0])]
                for vector in embeddings:
                    expected = settings.EMBEDDING_DIMENSION
                    if not isinstance(vector, list) or len(vector) != expected:
                        actual = len(vector) if isinstance(vector, list) else 0
                        raise ModelServiceError(f"向量维度应为 {expected}，实际为 {actual}，请检查模型与数据库配置。")
                    if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
                        raise ModelServiceError("千问返回的向量包含无效数值。")
                vectors.extend(embeddings)
        return vectors


class QwenClient:
    """LangChain model interfaces backed by the three native DashScope APIs."""

    def __init__(self, *, http_client: httpx.Client | None = None):
        if not settings.DASHSCOPE_API_KEY:
            raise ModelServiceError("请先在 langlain/.env 中配置 DASHSCOPE_API_KEY。")
        self._http_client = http_client
        self.embeddings = QwenEmbeddings(self._post)
        self.chat_model = QwenChatModel(request=self._post, model_name=settings.QWEN_CHAT_MODEL)

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{settings.DASHSCOPE_BASE_URL}/{path}"
        headers = {"Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}"}
        with _translate_errors():
            if self._http_client is None:
                with httpx.Client(timeout=settings.QWEN_TIMEOUT, trust_env=settings.QWEN_TRUST_ENV) as client:
                    response = client.post(url, headers=headers, json=payload)
            else:
                response = self._http_client.post(url, headers=headers, json=payload, timeout=settings.QWEN_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("code"):
                raise ModelServiceError("千问服务返回错误，请检查模型配置和调用权限。")
            return data

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embeddings.embed_documents(list(texts))

    def embed_query(self, question: str) -> list[float]:
        return self.embeddings.embed_query(question)

    def rerank(self, question: str, texts: Sequence[str], top_n: int) -> list[tuple[int, float]]:
        if not texts or top_n <= 0:
            return []
        limit = min(top_n, len(texts))
        data = self._post("services/rerank/text-rerank/text-rerank", {
            "model": settings.QWEN_RERANK_MODEL,
            "input": {"query": question, "documents": list(texts)},
            "parameters": {"top_n": limit},
        })
        with _translate_errors():
            rows = data["output"]["results"]
            if not isinstance(rows, list):
                raise ModelServiceError("千问返回的重排序结果格式不正确。")
            results, seen = [], set()
            for row in rows:
                index, score = row["index"], row["relevance_score"]
                if type(index) is not int or not 0 <= index < len(texts) or index in seen:
                    raise ModelServiceError("千问返回的重排序索引不正确。")
                if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ModelServiceError("千问返回的重排序分数不正确。")
                seen.add(index)
                results.append((index, float(score)))
            return sorted(results, key=lambda item: item[1], reverse=True)[:limit]

    def generate(self, prompt: ChatPromptTemplate, values: dict[str, str]) -> str:
        chain = prompt | self.chat_model | StrOutputParser()
        with _translate_errors():
            answer = chain.invoke(values).strip()
        if not answer:
            raise ModelServiceError("千问没有返回回答内容。")
        return answer
