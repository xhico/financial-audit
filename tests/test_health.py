# Author: xhico
# Date: May 27, 2026
"""Tests for the project-level health endpoint."""

from django.urls import reverse


def test_health_ok(client):
    """
    The health endpoint returns 200 with a status payload.

    Args:
        client (django.test.Client): pytest-django test client

    Returns:
        None
    """

    # Hit the liveness endpoint
    response = client.get(reverse("health"))

    # It should report the service as alive
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
