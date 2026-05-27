# Author: xhico
# Date: May 27, 2026
"""
Read-only dashboard endpoints for the finance app.

These aggregate the imported data for the income and savings dashboards: income
is summed from transactions categorised as income, while savings and net worth
come from the monthly balance snapshots.
"""

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from rest_framework.response import Response
from rest_framework.views import APIView

from finance.models import BalanceSnapshot, Category, Transaction


def _quarter(month):
    """
    Return the calendar quarter label for a month.

    Args:
        month (datetime.date): The first day of the month

    Returns:
        str: A label such as "2026-Q2"
    """

    return f"{month.year}-Q{(month.month - 1) // 3 + 1}"


class IncomeView(APIView):
    """
    Monthly and quarterly income over time.

    - Sums transactions in income-kind categories by month
    - Rolls the months up into calendar quarters
    """

    def get(self, request):
        """
        Return the income series.

        Args:
            request (Request): The incoming request

        Returns:
            Response: Monthly and quarterly income totals
        """

        rows = (
            Transaction.objects.filter(category__kind=Category.Kind.INCOME)
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )

        monthly = [{"period": r["month"].strftime("%Y-%m"), "income": float(r["total"])} for r in rows]

        # Roll the monthly totals up into calendar quarters
        quarters = {}
        for r in rows:
            quarters[_quarter(r["month"])] = quarters.get(_quarter(r["month"]), 0.0) + float(r["total"])
        quarterly = [{"period": q, "income": total} for q, total in sorted(quarters.items())]

        return Response({"monthly": monthly, "quarterly": quarterly})


class NetWorthView(APIView):
    """
    Savings and net worth over time from the balance snapshots.

    - Reports the headline balances captured each month
    - Computes net worth as assets minus the mortgage balance
    """

    def get(self, request):
        """
        Return the net-worth series.

        Args:
            request (Request): The incoming request

        Returns:
            Response: One entry per snapshot, oldest first
        """

        series = []
        for snap in BalanceSnapshot.objects.order_by("as_of"):
            current = float(snap.current_total or 0)
            savings = float(snap.savings_total or 0)
            investments = float(snap.investments_total or 0)
            mortgage = float(snap.mortgage_balance or 0)
            series.append(
                {
                    "as_of": snap.as_of.isoformat(),
                    "current": current,
                    "savings": savings,
                    "investments": investments,
                    "mortgage": mortgage,
                    "net_worth": current + savings + investments - mortgage,
                }
            )

        return Response(series)
