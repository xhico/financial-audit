# Author: xhico
# Date: May 27, 2026
"""URL configuration for the finance dashboard API."""

from django.urls import path

from finance.api import (
    AccountsView,
    CashflowView,
    CategoriseMatchingView,
    CategoryListView,
    ExpensesView,
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
    path("transactions/<int:pk>/", TransactionDetailView.as_view(), name="transaction-detail"),
    path("categories/", CategoryListView.as_view(), name="categories"),
    path("upload/", UploadView.as_view(), name="upload"),
    path("portfolio-snapshots/", PortfolioSnapshotView.as_view(), name="portfolio-snapshots"),
    path("reset/", ResetView.as_view(), name="reset"),
    path("seed/", SeedView.as_view(), name="seed"),
]
