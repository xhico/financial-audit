# Author: xhico
# Date: May 27, 2026
"""URL configuration for the finance dashboard API."""

from django.urls import path

from finance.api import (
    AccountsView,
    CashflowView,
    ExpensesView,
    IncomeView,
    InvestmentsView,
    NetWorthView,
    OverviewView,
    TransactionListView,
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
]
