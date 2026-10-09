"""Операции сервиса поверх базы данных. Ими пользуются и API, и HTML-страницы."""
from datetime import date

from . import rules

STATUSES = ("all", "active", "overdue", "returned")

STATUS_SQL = {
    "all": "TRUE",
    "active": "l.returned_on IS NULL",
    "overdue": "l.returned_on IS NULL AND l.due_on < current_date",
    "returned": "l.returned_on IS NOT NULL",
}


class NotFound(Exception):
    pass


def _loan_view(row, today=None):
    today = today or date.today()
    days = rules.overdue_days(row["due_on"], row["returned_on"], today)
    return {
        **row,
        "overdue": rules.is_overdue(row["due_on"], row["returned_on"], today),
        "overdue_days": days,
        "fine": rules.fine(days),
    }


def list_loans(db, page=1, size=20, status="all", reader=None):
    where = [STATUS_SQL[status]]
    params = {}
    if reader:
        where.append("r.full_name ILIKE %(reader)s")
        params["reader"] = f"%{reader}%"
    base = f"""
        FROM loan l
        JOIN copy c ON c.id = l.copy_id
        JOIN book b ON b.id = c.book_id
        JOIN reader r ON r.id = l.reader_id
        WHERE {' AND '.join(where)}
    """
    total = db.scalar(f"SELECT count(*) {base}", params)
    rows = db.execute(
        f"""
        SELECT l.id, l.issued_on, l.due_on, l.returned_on,
               r.id AS reader_id, r.full_name AS reader_name,
               c.id AS copy_id, c.inventory_no,
               b.id AS book_id, b.title, b.author
        {base}
        ORDER BY l.issued_on DESC, l.id DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {**params, "limit": size, "offset": (page - 1) * size},
    )
    return {"items": [_loan_view(r) for r in rows], "total": total, "page": page, "size": size}


def get_loan(db, loan_id):
    loan = db.one(
        """
        SELECT l.id, l.issued_on, l.due_on, l.returned_on, l.copy_id, l.reader_id,
               u.full_name AS issued_by
        FROM loan l LEFT JOIN app_user u ON u.id = l.issued_by
        WHERE l.id = %s
        """,
        (loan_id,),
    )
    if loan is None:
        raise NotFound("выдача не найдена")
    reader = db.one("SELECT * FROM reader WHERE id = %s", (loan["reader_id"],))
    copy = db.one("SELECT * FROM copy WHERE id = %s", (loan["copy_id"],))
    book = db.one("SELECT * FROM book WHERE id = %s", (copy["book_id"],))
    reader["loans_on_hand"] = db.scalar(
        "SELECT count(*) FROM loan WHERE reader_id = %s AND returned_on IS NULL",
        (reader["id"],),
    )
    return {**_loan_view(loan), "reader": reader, "copy": copy, "book": book}


def get_reader(db, reader_id):
    reader = db.one("SELECT * FROM reader WHERE id = %s", (reader_id,))
    if reader is None:
        raise NotFound("читатель не найден")
    loans = db.execute(
        """
        SELECT l.id, l.issued_on, l.due_on, l.returned_on, c.inventory_no, b.title, b.author
        FROM loan l
        JOIN copy c ON c.id = l.copy_id
        JOIN book b ON b.id = c.book_id
        WHERE l.reader_id = %s
        ORDER BY l.issued_on DESC
        """,
        (reader_id,),
    )
    loans = [_loan_view(l) for l in loans]
    return {
        **reader,
        "loans": loans,
        "on_hand": sum(1 for l in loans if l["returned_on"] is None),
        "has_overdue": any(l["overdue"] for l in loans),
    }


def issue_loan(db, reader_id, copy_id, user_id, today=None):
    today = today or date.today()
    if db.one("SELECT id FROM reader WHERE id = %s", (reader_id,)) is None:
        raise NotFound("читатель не найден")
    if db.one("SELECT id FROM copy WHERE id = %s", (copy_id,)) is None:
        raise NotFound("экземпляр не найден")
    busy = db.one(
        "SELECT id FROM loan WHERE copy_id = %s AND returned_on IS NULL", (copy_id,)
    ) is not None
    overdue = db.scalar(
        """SELECT count(*) FROM loan
           WHERE reader_id = %s AND returned_on IS NULL AND due_on < %s""",
        (reader_id, today),
    )
    rules.check_issue(busy, overdue)
    row = db.one(
        """INSERT INTO loan (copy_id, reader_id, issued_on, due_on, issued_by)
           VALUES (%s, %s, %s, %s, %s)
           RETURNING id, copy_id, reader_id, issued_on, due_on, returned_on""",
        (copy_id, reader_id, today, rules.due_date(today), user_id),
    )
    db.conn.commit()
    return _loan_view(row, today)


def return_loan(db, loan_id, return_on=None):
    return_on = return_on or date.today()
    loan = db.one("SELECT * FROM loan WHERE id = %s", (loan_id,))
    if loan is None:
        raise NotFound("выдача не найдена")
    rules.check_return(loan["returned_on"], loan["issued_on"], return_on)
    row = db.one(
        """UPDATE loan SET returned_on = %s WHERE id = %s
           RETURNING id, copy_id, reader_id, issued_on, due_on, returned_on""",
        (return_on, loan_id),
    )
    db.conn.commit()
    return _loan_view(row, return_on)


def summary(db, top=10):
    on_hand = db.scalar("SELECT count(*) FROM loan WHERE returned_on IS NULL")
    overdue = db.scalar(
        "SELECT count(*) FROM loan WHERE returned_on IS NULL AND due_on < current_date"
    )
    top_books = db.execute(
        """
        SELECT b.id AS book_id, b.title, b.author, count(*) AS loans
        FROM loan l
        JOIN copy c ON c.id = l.copy_id
        JOIN book b ON b.id = c.book_id
        GROUP BY b.id, b.title, b.author
        ORDER BY loans DESC, b.id
        LIMIT %s
        """,
        (top,),
    )
    return {
        "on_hand": on_hand,
        "overdue": overdue,
        "overdue_share": round(overdue / on_hand, 4) if on_hand else 0.0,
        "top_books": top_books,
    }
