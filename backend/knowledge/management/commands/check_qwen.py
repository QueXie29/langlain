from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from langchain_core.prompts import ChatPromptTemplate

from knowledge.services.qwen import ModelServiceError, QwenClient


class Command(BaseCommand):
    help = "使用固定测试文本检查千问聊天、向量和重排序接口（不需要连接数据库，会产生少量 API 用量）。"

    def handle(self, *args, **options):
        try:
            client = QwenClient()
            vector = client.embed(["知屿用于文档问答。"])[0]
            client.embed_query("知屿有什么用途？")
            self.stdout.write(self.style.SUCCESS(
                f"向量 OK: {settings.QWEN_EMBED_MODEL}, {len(vector)} 维（文档/查询均通过）"
            ))
            ranking = client.rerank("知屿有什么用途？", ["知屿用于文档问答。", "今天下雨了。"], 1)
            if not ranking:
                raise ModelServiceError("重排序接口未返回测试结果。")
            self.stdout.write(self.style.SUCCESS(f"重排序 OK: {settings.QWEN_RERANK_MODEL}"))
            client.generate(ChatPromptTemplate.from_template("{question}"), {"question": "请只回答：连接成功"})
            self.stdout.write(self.style.SUCCESS(f"大语言模型 OK: {settings.QWEN_CHAT_MODEL}"))
        except ModelServiceError as exc:
            raise CommandError(str(exc)) from None
