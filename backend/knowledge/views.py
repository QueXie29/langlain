from pathlib import Path

from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from .models import Document
from .serializers import (
    DocumentSerializer,
    DocumentUploadSerializer,
    LogoutSerializer,
    QuestionSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services.ingestion import IngestionError, ingest_document
from .services.qwen import ModelServiceError
from .services.parsers import DocumentParseError
from .services.rag import answer_question


class UpstreamServiceError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "upstream_service_error"


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TokenObtainPairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({**serializer.validated_data, "user": UserSerializer(serializer.user).data})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LogoutView(APIView):
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentListCreateView(generics.ListAPIView):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)

    def post(self, request, *args, **kwargs):
        upload_serializer = DocumentUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)
        uploaded_file = upload_serializer.validated_data["file"]
        extension = Path(uploaded_file.name).suffix.lower()
        document = Document.objects.create(
            owner=request.user,
            original_name=Path(uploaded_file.name).name[:255],
            file=uploaded_file,
            file_type=extension.lstrip("."),
            file_size=uploaded_file.size,
        )
        try:
            ingest_document(document)
        except (DocumentParseError, IngestionError, ModelServiceError) as exc:
            document.status = Document.Status.FAILED
            document.error_message = str(exc)[:500]
            document.save(update_fields=["status", "error_message", "updated_at"])
            raise UpstreamServiceError(str(exc)) from exc
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class DocumentDetailView(generics.DestroyAPIView):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        stored_file = instance.file
        instance.delete()
        stored_file.delete(save=False)


class AskView(APIView):
    def post(self, request):
        serializer = QuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = answer_question(request.user, serializer.validated_data["question"])
        except ModelServiceError as exc:
            raise UpstreamServiceError(str(exc)) from exc
        return Response(
            {"answer": result.answer, "sources": result.sources, "refused": result.refused}
        )
