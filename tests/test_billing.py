from datetime import date

from app.billing import monthly_equivalent, next_charge, nth_charge


def test_month_end_does_not_drift():
    a = date(2026, 1, 31)
    assert [nth_charge(a, "month", 1, k) for k in range(4)] == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)
    ]


def test_leap_year_yearly():
    assert nth_charge(date(2024, 2, 29), "year", 1, 1) == date(2025, 2, 28)
    assert nth_charge(date(2024, 2, 29), "year", 1, 4) == date(2028, 2, 29)


def test_next_charge_future_anchor():
    assert next_charge(date(2026, 12, 1), "month", 1, date(2026, 10, 14)) == date(2026, 12, 1)


def test_next_charge_today_counts():
    assert next_charge(date(2026, 1, 14), "month", 1, date(2026, 10, 14)) == date(2026, 10, 14)


def test_next_charge_far_past_months_exact():
    # проверяем перебором, что оценка k не перескакивает
    anchor = date(2000, 1, 31)
    for today in [date(2026, 10, 14), date(2026, 3, 1), date(2010, 2, 28)]:
        k = 0
        while nth_charge(anchor, "month", 3, k) < today:
            k += 1
        assert next_charge(anchor, "month", 3, today) == nth_charge(anchor, "month", 3, k)


def test_next_charge_weeks_days():
    assert next_charge(date(2026, 10, 1), "week", 2, date(2026, 10, 14)) == date(2026, 10, 15)
    assert next_charge(date(2026, 10, 1), "day", 10, date(2026, 10, 14)) == date(2026, 10, 21)


def test_monthly_equivalent():
    assert monthly_equivalent(120, "year", 1) == 10
    assert monthly_equivalent(30, "month", 3) == 10
