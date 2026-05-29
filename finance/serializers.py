# Author: xhico
# Date: May 27, 2026
"""Serializers for the finance API."""

from rest_framework import serializers

from finance.models import Account, Category, PortfolioSnapshot, Transaction


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

    - Used by the transactions list endpoint and the detail PATCH endpoint
    - Embeds the related account and category as read-only nested objects so
      the frontend renders without extra requests
    - Exposes category_id as the writable handle for changing the category
    """

    account = AccountBriefSerializer(read_only=True)
    category = CategoryBriefSerializer(read_only=True)
    # Writable category by primary key; null clears the category
    category_id = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=Category.objects.all(),
        write_only=True,
        allow_null=True,
        required=False,
    )

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
            "category_id",
            "statement_id",
        )


class PortfolioSnapshotSerializer(serializers.ModelSerializer):
    """
    Read/write serializer for a manually-recorded portfolio market value.

    - Embeds the brokerage account as a read-only brief so the dashboard can
      label the row
    - Accepts account_id on write, restricted to brokerage-kind accounts so a
      caller cannot accidentally attach a snapshot to a current account
    """

    account = AccountBriefSerializer(read_only=True)
    account_id = serializers.PrimaryKeyRelatedField(
        source="account",
        queryset=Account.objects.filter(kind=Account.Kind.BROKERAGE),
        write_only=True,
    )

    class Meta:
        model = PortfolioSnapshot
        fields = ("id", "account", "account_id", "as_of", "market_value", "note", "created_at")
        read_only_fields = ("id", "created_at")
        # The view treats POST as an upsert on (account, as_of). The database
        # still enforces the unique constraint; we just need the serializer to
        # stop rejecting a repeat submission as a uniqueness violation.
        validators = []
