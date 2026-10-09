"""Бизнес-правила варианта 1 - без базы данных и без HTTP."""
from datetime import date

import pytest

from app import rules

TODAY = date(2026, 10, 10)


def test_due_date_is_fourteen_days_after_issue():
    assert rules.due_date(date(2026, 10, 1)) == date(2026, 10, 15)


def test_no_overdue_when_returned_in_time():
    assert rules.overdue_days(date(2026, 10, 15), date(2026, 10, 15), TODAY) == 0


def test_overdue_counts_to_actual_return_date():
    assert rules.overdue_days(date(2026, 10, 1), date(2026, 10, 4), TODAY) == 3


def test_overdue_counts_to_today_while_book_on_hand():
    assert rules.overdue_days(date(2026, 10, 1), None, TODAY) == 9


def test_fine_is_ten_roubles_per_day():
    assert rules.fine(3) == 30
    assert rules.fine(0) == 0


def test_issue_refused_when_copy_is_busy():
    with pytest.raises(rules.IssueRefused, match="экземпляр уже выдан"):
        rules.check_issue(copy_is_busy=True, reader_overdue_loans=0)


def test_issue_refused_to_reader_with_overdue_loans():
    with pytest.raises(rules.IssueRefused, match="просроченные"):
        rules.check_issue(copy_is_busy=False, reader_overdue_loans=1)


def test_issue_allowed_for_free_copy_and_clean_reader():
    rules.check_issue(copy_is_busy=False, reader_overdue_loans=0)


def test_return_refused_twice():
    with pytest.raises(rules.IssueRefused, match="уже закрыта"):
        rules.check_return(date(2026, 10, 5), date(2026, 10, 1), TODAY)
