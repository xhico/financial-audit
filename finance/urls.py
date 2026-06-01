# Author: xhico
# Date: May 27, 2026
"""URL configuration for the finance dashboard API."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from finance.api import (
    AccountsView,
    CashflowView,
    CategoriseBulkView,
    CategoriseMatchingView,
    CategoryRuleViewSet,
    CategoryViewSet,
    ExpensesView,
    IgnoreRuleViewSet,
    IncomeView,
    InvestmentsView,
    NetWorthView,
    OverviewView,
    PortfolioSnapshotView,
    ResetView,
    SeedView,
    TransactionDetailView,
    TransactionListView,
    UploadView,
)

app_name = "finance"

# A DRF router gives every viewset the standard list/create/retrieve/update/
# destroy URLs without manually wiring each path. The trailing slash is
# kept to match the rest of the API.
router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"category-rules", CategoryRuleViewSet, basename="category-rules")
router.register(r"ignore-rules", IgnoreRuleViewSet, basename="ignore-rules")

urlpatterns = [
    path("dashboard/overview/", OverviewView.as_view(), name="overview"),
    path("dashboard/income/", IncomeView.as_view(), name="income"),
    path("dashboard/expenses/", ExpensesView.as_view(), name="expenses"),
    path("dashboard/cashflow/", CashflowView.as_view(), name="cashflow"),
    path("dashboard/net-worth/", NetWorthView.as_view(), name="net-worth"),
    path("dashboard/investments/", InvestmentsView.as_view(), name="investments"),
    path("dashboard/accounts/", AccountsView.as_view(), name="accounts"),
    path("transactions/", TransactionListView.as_view(), name="transactions"),
    path(
        "transactions/categorise-matching/",
        CategoriseMatchingView.as_view(),
        name="transactions-categorise-matching",
    ),
    path(
        "transactions/categorise-bulk/",
        CategoriseBulkView.as_view(),
        name="transactions-categorise-bulk",
    ),
    path("transactions/<int:pk>/", TransactionDetailView.as_view(), name="transaction-detail"),
    path("upload/", UploadView.as_view(), name="upload"),
    path("portfolio-snapshots/", PortfolioSnapshotView.as_view(), name="portfolio-snapshots"),
    path("reset/", ResetView.as_view(), name="reset"),
    path("seed/", SeedView.as_view(), name="seed"),
    path("", include(router.urls)),
]
