# Author: xhico
# Date: May 27, 2026
"""
Server-rendered dashboard pages for the finance app.

These pages are thin shells: each one renders a template that fetches its data
from the matching /api/ endpoint via fetch() and draws charts with Chart.js.
Pages require an authenticated user; unauthenticated requests redirect to the
Django admin login page.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def overview(request):
    """
    Render the dashboard homepage.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered overview page
    """

    return render(request, "finance/overview.html")


@login_required
def income(request):
    """
    Render the income dashboard page.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered income page
    """

    return render(request, "finance/income.html")


@login_required
def expenses(request):
    """
    Render the expenses dashboard page.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered expenses page
    """

    return render(request, "finance/expenses.html")


@login_required
def cashflow(request):
    """
    Render the cashflow dashboard page.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered cashflow page
    """

    return render(request, "finance/cashflow.html")


@login_required
def net_worth(request):
    """
    Render the net-worth dashboard page.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered net-worth page
    """

    return render(request, "finance/net_worth.html")


@login_required
def investments(request):
    """
    Render the investments dashboard page.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered investments page
    """

    return render(request, "finance/investments.html")


@login_required
def accounts(request):
    """
    Render the accounts dashboard page.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered accounts page
    """

    return render(request, "finance/accounts.html")


@login_required
def transactions(request):
    """
    Render the filterable transactions page.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered transactions page
    """

    return render(request, "finance/transactions.html")


@login_required
def upload(request):
    """
    Render the file-upload page used to import statements via the browser.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered upload page
    """

    return render(request, "finance/upload.html")


@login_required
def seed(request):
    """
    Render the seed-configuration page.

    The page lets the user download a JSON snapshot of the current
    categories, rules and ignore patterns, and upload a replacement that
    is applied via the same code path as the seed_finance command.

    Args:
        request (HttpRequest): The incoming request

    Returns:
        HttpResponse: The rendered seed page
    """

    return render(request, "finance/seed.html")
