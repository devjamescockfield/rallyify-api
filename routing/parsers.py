from io import BytesIO

from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.parsers import JSONParser


class RequestBodyTooLarge(APIException):
    status_code = 413
    default_detail = "Request body exceeds the configured size limit."
    default_code = "request_body_too_large"


class LimitedJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        limit = settings.DATA_UPLOAD_MAX_MEMORY_SIZE
        request = (parser_context or {}).get("request")
        content_length = request.META.get("CONTENT_LENGTH") if request else None

        try:
            declared_length = int(content_length) if content_length else None
        except (TypeError, ValueError):
            declared_length = None

        if declared_length is not None and declared_length > limit:
            raise RequestBodyTooLarge

        body = stream.read(limit + 1)
        if len(body) > limit:
            raise RequestBodyTooLarge

        return super().parse(
            BytesIO(body),
            media_type=media_type,
            parser_context=parser_context,
        )
