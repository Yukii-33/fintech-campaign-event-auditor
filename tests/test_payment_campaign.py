from decimal import Decimal

from campaign_auditor.payment_campaign import decide_payment_action


def test_bounce_holds_a_high_value_payment_action() -> None:
    decision = decide_payment_action(Decimal("12500.00"), ["delivered", "bounced"])

    assert decision.action == "hold"
    assert decision.observed_events == ("bounced", "delivered")


def test_open_allows_high_value_payment_to_continue_to_review() -> None:
    decision = decide_payment_action(Decimal("12500.00"), ["delivered", "opened"])

    assert decision.action == "allow_review"

