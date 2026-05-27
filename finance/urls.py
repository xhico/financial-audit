# Author: xhico
# Date: May 27, 2026
"""URL configuration for the finance dashboard API."""

from django.urls import path

from finance.api import IncomeView, NetWorthView

app_name = "finance"

urlpatterns = [
    path("dashboard/income/", IncomeView.as_view(), name="income"),
    path("dashboard/net-worth/", NetWorthView.as_view(), name="net-worth"),
]
