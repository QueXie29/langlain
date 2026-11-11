from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Document


User = get_user_model()
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("username", "email", "password", "password_confirm")

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "两次输入的密码不一致。"})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = (
            "id",
            "original_name",
            "file_type",
            "file_size",
            "status",
            "chunks_count",
            "error_message",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(write_only=True)

    def validate_file(self, value):
        extension = Path(value.name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            allowed = "、".join(sorted(SUPPORTED_EXTENSIONS))
            raise serializers.ValidationError(f"仅支持 {allowed} 文件。")
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if value.size > max_bytes:
            raise serializers.ValidationError(f"文件不能超过 {settings.MAX_UPLOAD_SIZE_MB} MB。")
        if value.size == 0:
            raise serializers.ValidationError("不能上传空文件。")
        return value


class QuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000, trim_whitespace=True)

    def validate_question(self, value):
        if not value.strip():
            raise serializers.ValidationError("问题不能为空。")
        return value.strip()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

