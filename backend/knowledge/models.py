from django.conf import settings
from django.db import models
from pgvector.django import VectorField


class Document(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "处理中"
        READY = "ready", "可用"
        FAILED = "failed", "失败"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    original_name = models.CharField(max_length=255)  #用户上传时的原始文件名
    file = models.FileField(upload_to="documents/%Y/%m/")   # 文件存储路径
    file_type = models.CharField(max_length=16)             # 文件类型
    file_size = models.PositiveBigIntegerField()            # 文件大小
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROCESSING)
    chunks_count = models.PositiveIntegerField(default=0)       # 块数量
    error_message = models.CharField(max_length=500, blank=True)  # 错误信息
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "status"], name="knowledge_d_owner_i_5d08a6_idx")]

    def __str__(self):
        return self.original_name


class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSION)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["chunk_index"]
        constraints = [
            models.UniqueConstraint(fields=["document", "chunk_index"], name="unique_document_chunk")
        ]
