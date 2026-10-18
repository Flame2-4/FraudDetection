"""Basic AI fraud detection starter."""

from dataclasses import dataclass


@dataclass
class Transaction:
    amount: float
    transactions_last_hour: int
    is_foreign: bool


def assess_transaction(transaction: Transaction) -> dict:
    """Flag transactions using simple example rules."""
    risk_score = 0
    reasons = []

    if transaction.amount >= 5000:
        risk_score += 40
        reasons.append("Unusually large transaction")

    if transaction.transactions_last_hour >= 5:
        risk_score += 30
        reasons.append("High transaction frequency")

    if transaction.is_foreign:
        risk_score += 20
        reasons.append("Foreign transaction")

    return {
        "risk_score": min(risk_score, 100),
        "flagged": risk_score >= 50,
        "reasons": reasons,
    }


if __name__ == "__main__":
    example = Transaction(
        amount=6500,
        transactions_last_hour=6,
        is_foreign=True,
    )
    print(assess_transaction(example))
