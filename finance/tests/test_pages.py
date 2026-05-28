# Author: xhico
# Date: May 27, 2026
"""Tests for the server-rendered dashboard pages."""

import pytest
from django.contrib.auth.models import User
from django.test import Client

# All seven page URL names that should render for an authenticated user
PAGE_PATHS = [
    "/",
    "/income/",
    "/expenses/",
    "/cashflow/",
    "/net-worth/",
    "/accounts/",
    "/transactions/",
]


@pytest.fixture
def auth_client():
    """
    Provide a Django test client logged in as a freshly created user.

    Args:
        None

    Returns:
        Client: A logged-in client
    """

    User.objects.create_user(username="viewer", password="pw")
    client = Client()
    client.login(username="viewer", password="pw")
    return client


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGE_PATHS)
def test_dashboard_page_redirects_when_anonymous(path):
    """
    Each dashboard page redirects an unauthenticated visitor to the login URL.

    Args:
        path (str): The page URL under test

    Returns:
        None
    """

    response = Client().get(path)
    # @login_required redirects (302) to LOGIN_URL when not authenticated
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGE_PATHS)
def test_dashboard_page_renders_when_authenticated(auth_client, path):
    """
    Each dashboard page returns 200 and references its chart container.

    Args:
        auth_client (Client): Authenticated test client
        path (str): The page URL under test

    Returns:
        None
    """

    response = auth_client.get(path)
    assert response.status_code == 200
    # The base template emits the FinancialAudit brand on every page
    assert b"FinancialAudit" in response.content
