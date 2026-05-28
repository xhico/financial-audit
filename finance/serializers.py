# Author: xhico
# Date: May 27, 2026
"""Serializers for the finance API."""

from rest_framework import serializers

from finance.models import Account, Category, Transaction


class CategoryBriefSerializer(serializers.ModelSerializer):
    """
    Slim serializer for embedding a category inside a transaction.

    - Carries only the fields a dashboard needs to render the chip
    """

    class Meta:
        model = Category
        fields = ("id", "name", "kind")


class AccountBriefSerializer(serializers.ModelSerializer):
    """
    Slim serializer for embedding an account inside a transaction.

    - Includes the scope so dashboards can colour personal vs business
    """

    class Meta:
        model = Account
        fields = ("id", "name", "bank", "scope", "iban")


class TransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for a single transaction, with embedded account and category.

    - Used by the transactions list endpoint
    - Embeds related rows so the frontend renders without extra requests
    """

    account = AccountBriefSerializer(read_only=True)
    category = CategoryBriefSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = (
            "id",
            "date",
            "value_date",
            "description",
            "amount",
            "balance",
            "account",
            "category",
            "statement_id",
        )
