# Author: xhico
# Date: May 27, 2026
"""
Project-wide pytest fixtures and configuration.

Swaps the manifest-backed static-files storage for the plain storage during
tests, so {% static %} resolves without a prior `collectstatic` run.
"""

from django.conf import settings


def pytest_configure(config):
    """
    Override Django settings for the whole test session.

    Args:
        config (pytest.Config): The pytest configuration

    Returns:
        None
    """

    # Plain static-files storage skips the manifest lookup we don't need in tests
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
