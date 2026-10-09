"""Бизнес-правила выдачи книг. Чистые функции: без базы и без HTTP."""
from datetime import date, timedelta

LOAN_DAYS = 14        # срок выдачи
FINE_PER_DAY = 10     # штраф за сутки просрочки, руб.


class IssueRefused(Exception):
    """Выдача невозможна по правилам библиотеки."""


def due_date(issued_on: date) -> date:
    return issued_on + timedelta(days=LOAN_DAYS)


def overdue_days(due_on: date, returned_on: date | None, today: date) -> int:
    """Просрочка: от срока возврата до фактической даты (или до сегодня, если книга на руках)."""
    end = returned_on or today
    return max(0, (end - due_on).days)


def fine(days_overdue: int) -> int:
    return days_overdue * FINE_PER_DAY


def is_overdue(due_on: date, returned_on: date | None, today: date) -> bool:
    return returned_on is None and due_on < today


def check_issue(copy_is_busy: bool, reader_overdue_loans: int) -> None:
    """Экземпляр выдаётся, если он свободен и у читателя нет просроченных выдач."""
    if copy_is_busy:
        raise IssueRefused("экземпляр уже выдан")
    if reader_overdue_loans > 0:
        raise IssueRefused("у читателя есть просроченные выдачи")


def check_return(returned_on: date | None, issued_on: date, return_on: date) -> None:
    if returned_on is not None:
        raise IssueRefused("выдача уже закрыта")
    if return_on < issued_on:
        raise IssueRefused("дата возврата раньше даты выдачи")
