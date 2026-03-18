from decimal import Decimal


class InstitutionalValidationService:
    """
    Institutional validation rules enforced before committing valuations.
    """

    @staticmethod
    def validate_capital_conservation(
        *,
        expected_end_total: Decimal,
        actual_end_total: Decimal,
        tolerance: Decimal = Decimal("0.05"),
    ) -> None:
        """
        Capital Conservation Rule:
        For a closed epoch, the sum of ledger end balances should match the
        accounting identity:

          expected_end_total = start_total + deposits - withdrawals + profit

        We validate that expected_end_total ~= actual_end_total within tolerance.
        """
        diff = (expected_end_total - actual_end_total).copy_abs()
        if diff > tolerance:
            raise ValueError(
                f"Capital conservation failed: expected_end_total={expected_end_total} "
                f"actual_end_total={actual_end_total} diff={diff} (tolerance={tolerance})"
            )

