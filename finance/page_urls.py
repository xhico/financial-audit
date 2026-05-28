# Author: xhico
# Date: May 27, 2026
"""URL configuration for the server-rendered dashboard pages."""

from django.urls import path

from finance import views

app_name = "pages"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("income/", views.income, name="income"),
    path("expenses/", views.expenses, name="expenses"),
    path("cashflow/", views.cashflow, name="cashflow"),
    path("net-worth/", views.net_worth, name="net-worth"),
    path("investments/", views.investments, name="investments"),
    path("accounts/", views.accounts, name="accounts"),
    path("transactions/", views.transactions, name="transactions"),
]
