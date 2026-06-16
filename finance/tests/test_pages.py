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
    "/investments/",
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
    # @login_required redirects (302) to LOGIN_URL when not authenticated.
    # Project ships its own dashboard-styled login at /login/, not the
    # default /admin/login/.
    assert response.status_code == 302
    assert "/login/" in response["Location"]


@pytest.mark.django_db
def test_login_page_renders_custom_template():
    """
    GET /login/ serves the project's custom login template, not the
    Django admin login. The page should mention FinancialAudit and the
    Sign in heading, and must NOT use admin/login.html.

    Args:
        None

    Returns:
        None
    """

    response = Client().get("/login/")

    assert response.status_code == 200
    template_names = {t.name for t in response.templates if t.name}
    assert "registration/login.html" in template_names
    # Sanity-check: the bento tile class and brand string are in the body
    body = response.content.decode("utf-8")
    assert "FinancialAudit" in body
    assert "Sign in" in body


@pytest.mark.django_db
def test_logout_view_requires_post():
    """
    The logout endpoint accepts POST (Django 5 deprecated GET-based
    logout), so the sidebar wraps the Sign out control in a form.

    Args:
        None

    Returns:
        None
    """

    User.objects.create_user(username="bye", password="pw")
    client = Client()
    client.login(username="bye", password="pw")

    # GET on /logout/ is rejected with 405 since Django 5
    response = client.get("/logout/")
    assert response.status_code == 405

    response = client.post("/logout/")
    # next_page="login" -> redirected to /login/ after a successful logout
    assert response.status_code == 302
    assert "/login/" in response["Location"]


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
