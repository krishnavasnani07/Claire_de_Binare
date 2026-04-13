from unittest.mock import MagicMock, patch

import pytest

from services.reports.daily_orders_summary import fetch_summary, format_email_body, send_email


@pytest.mark.unit
def test_fetch_summary_maps_positive_trade_metrics():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (12, 9, 1, 1, 1, 1234.5, 4, 3, 75.0, 2.5)
    cursor.fetchall.return_value = [("risk_limit", 1)]

    summary = fetch_summary(conn, hours=24)

    assert summary["total_trades"] == 4
    assert summary["positive_trades"] == 3
    assert summary["positive_trade_rate"] == 75.0
    assert summary["total_fees"] == 2.5


@pytest.mark.unit
def test_format_email_body_includes_positive_trade_metrics():
    html = format_email_body(
        {
            "total_orders": 12,
            "filled": 9,
            "rejected": 1,
            "cancelled": 1,
            "pending": 1,
            "notional": 1234.5,
            "total_trades": 4,
            "positive_trades": 3,
            "positive_trade_rate": 75.0,
            "total_fees": 2.5,
            "rejections": [],
        },
        __import__("datetime").datetime(2026, 4, 8, 0, 0),
        __import__("datetime").datetime(2026, 4, 9, 0, 0),
    )

    assert "Trades Made:</strong> 4" in html
    assert "Positive Trades:</strong> 3" in html
    assert "Positive Trade Rate:</strong> 75.0%" in html


@pytest.mark.unit
def test_send_email_success_log_does_not_contain_recipient(capsys):
    """Regression: success log must not expose recipient address (#1652 CodeQL fix)."""
    recipient = "private_recipient@example.com"
    with patch("services.reports.daily_orders_summary.read_secret") as mock_secret, \
         patch("services.reports.daily_orders_summary.smtplib.SMTP") as mock_smtp:
        mock_secret.side_effect = ["user@smtp.com", "pass", "from@smtp.com", recipient]
        smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=smtp_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = send_email("Subject", "<html/>")

    captured = capsys.readouterr()
    assert result is True
    assert recipient not in captured.out


@pytest.mark.unit
def test_send_email_error_log_exposes_only_exception_type(capsys):
    """Regression: error log must contain only exception type, not raw details (#1652 CodeQL fix)."""
    sensitive_detail = "smtp_password_leak_xyz_secret"
    with patch("services.reports.daily_orders_summary.read_secret") as mock_secret, \
         patch("services.reports.daily_orders_summary.smtplib.SMTP") as mock_smtp:
        mock_secret.side_effect = ["user@smtp.com", "pass", "from@smtp.com", "to@example.com"]
        mock_smtp.side_effect = Exception(sensitive_detail)

        result = send_email("Subject", "<html/>")

    captured = capsys.readouterr()
    assert result is False
    assert sensitive_detail not in captured.out
    assert "Exception" in captured.out
