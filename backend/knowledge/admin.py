from django.contrib import admin

from .models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "owner", "status", "chunks_count", "created_at")
    list_filter = ("status", "file_type")
    search_fields = ("original_name", "owner__username")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_index", "created_at")
    search_fields = ("document__original_name", "content")

