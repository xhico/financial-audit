# Author: xhico
# Date: May 27, 2026
"""Root URL configuration for the FinancialAudit project."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def health(request):
    """
    Return a simple liveness response for container health checks.

    Args:
        request (HttpRequest): Incoming request

    Returns:
        JsonResponse: {"status": "ok"} with HTTP 200
    """

    # Report the service as alive
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
]
