from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import pgvector.django.vector
import pgvector.django.extensions


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        pgvector.django.extensions.VectorExtension(),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_name", models.CharField(max_length=255)),
                ("file", models.FileField(upload_to="documents/%Y/%m/")),
                ("file_type", models.CharField(max_length=16)),
                ("file_size", models.PositiveBigIntegerField()),
                ("status", models.CharField(choices=[("processing", "处理中"), ("ready", "可用"), ("failed", "失败")], default="processing", max_length=16)),
                ("chunks_count", models.PositiveIntegerField(default=0)),
                ("error_message", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DocumentChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chunk_index", models.PositiveIntegerField()),
                ("content", models.TextField()),
                ("embedding", pgvector.django.vector.VectorField(dimensions=1024)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="knowledge.document")),
            ],
            options={"ordering": ["chunk_index"]},
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["owner", "status"], name="knowledge_d_owner_i_5d08a6_idx"),
        ),
        migrations.AddConstraint(
            model_name="documentchunk",
            constraint=models.UniqueConstraint(fields=("document", "chunk_index"), name="unique_document_chunk"),
        ),
    ]

