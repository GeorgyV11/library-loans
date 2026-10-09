"""Наполнение базы: python -m app.seed small|work

Воспроизводимо: генератор случайных чисел с фиксированным зерном и фиксированная
опорная дата, поэтому повторный запуск даёт те же строки. Схема пересоздаётся.
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg

from .auth import hash_password
from .config import settings
from .rules import LOAN_DAYS

SIZES = {
    #        читатели книги экземпляры выдачи
    "small": (50, 100, 200, 300),
    "work": (3_000, 10_000, 30_000, 100_000),
}
ANCHOR = date(2026, 10, 9)          # «сегодня» для генерации истории
SEED = 2026

LAST = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов",
        "Новиков", "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров",
        "Павлов", "Козлов", "Степанов", "Николаев", "Орлов", "Андреев", "Макаров", "Никитин"]
FIRST = ["Александр", "Дмитрий", "Максим", "Сергей", "Андрей", "Алексей", "Иван", "Евгений",
         "Михаил", "Артём", "Никита", "Павел", "Роман", "Олег", "Георгий", "Кирилл"]
MIDDLE = ["Александрович", "Дмитриевич", "Сергеевич", "Андреевич", "Иванович", "Михайлович",
          "Петрович", "Николаевич", "Олегович", "Павлович"]
WORDS1 = ["Тихий", "Последний", "Белый", "Далёкий", "Северный", "Забытый", "Красный", "Старый",
          "Новый", "Тёмный", "Золотой", "Морской", "Лесной", "Вечный", "Чужой", "Звёздный"]
WORDS2 = ["дом", "берег", "город", "сад", "путь", "остров", "ветер", "край", "мост", "лес",
          "огонь", "свет", "час", "след", "голос", "сон", "рассвет", "маяк", "перевал", "архив"]


def zipf_weights(n, rnd, s=1.0):
    weights = [1 / (i + 1) ** s for i in range(n)]
    rnd.shuffle(weights)
    return weights


def generate(size):
    n_readers, n_books, n_copies, n_loans = SIZES[size]
    rnd = random.Random(SEED)

    readers = []
    for i in range(1, n_readers + 1):
        name = f"{rnd.choice(LAST)} {rnd.choice(FIRST)} {rnd.choice(MIDDLE)}"
        readers.append((i, name, f"reader{i}@library.test", f"+7 900 {i:07d}",
                        ANCHOR - timedelta(days=rnd.randint(30, 2000))))

    books = []
    for i in range(1, n_books + 1):
        title = f"{rnd.choice(WORDS1)} {rnd.choice(WORDS2)}"
        if rnd.random() < 0.4:
            title += f" {rnd.randint(2, 9)}"
        author = f"{rnd.choice(LAST)} {rnd.choice(FIRST)[0]}. {rnd.choice(MIDDLE)[0]}."
        books.append((i, title, author, rnd.randint(1950, 2025), f"978-5-{rnd.randint(1000, 9999)}-{i:05d}"))

    # каждый экземпляр принадлежит книге; у каждой книги минимум один экземпляр
    copy_book = list(range(1, n_books + 1)) + [rnd.randint(1, n_books) for _ in range(n_copies - n_books)]
    copies = [(i, b, f"ИНВ-{i:06d}", f"{rnd.randint(1, 40)}-{rnd.randint(1, 8)}")
              for i, b in enumerate(copy_book, 1)]

    # популярность книг - по закону Ципфа, выдачи распределяются по экземплярам
    book_w = zipf_weights(n_books, rnd, 0.8)
    reader_w = zipf_weights(n_readers, rnd, 0.5)
    copy_w = [book_w[b - 1] * rnd.uniform(0.5, 1.5) for b in copy_book]
    total_w = sum(copy_w)
    per_copy = [int(w / total_w * n_loans) for w in copy_w]
    for i in rnd.sample(range(n_copies), n_loans - sum(per_copy)):
        per_copy[i] += 1

    reader_ids = [r[0] for r in readers]
    loans = []
    for copy_id, count in enumerate(per_copy, 1):
        # история экземпляра - от опорной даты назад, выдачи не пересекаются
        end = ANCHOR - timedelta(days=rnd.randint(0, 20))
        active = rnd.random() < 0.15
        for k in range(count):
            hold = rnd.randint(3, 30)
            issued = end - timedelta(days=hold)
            returned = None if (k == 0 and active) else end
            if returned is None:   # на руках: обычно в пределах срока, четверть - просрочена
                late = rnd.random() < 0.25
                issued = ANCHOR - timedelta(days=rnd.randint(15, 60) if late else rnd.randint(0, 13))
            reader_id = rnd.choices(reader_ids, reader_w)[0]
            loans.append((copy_id, reader_id, issued, issued + timedelta(days=LOAN_DAYS), returned))
            end = issued - timedelta(days=rnd.randint(0, 25))
    loans.sort(key=lambda l: (l[2], l[0]))
    return readers, books, copies, loans


def main(size):
    readers, books, copies, loans = generate(size)
    schema = settings.db_schema
    ddl = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8").replace("{schema}", schema)
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(ddl)
        conn.execute(f"SET search_path TO {schema}")
        conn.execute(
            "INSERT INTO app_user (login, password_hash, full_name) VALUES (%s, %s, %s)",
            ("librarian", hash_password("library"), "Библиотекарь Демо"),
        )
        with conn.cursor() as cur:
            with cur.copy("COPY reader (id, full_name, email, phone, registered_on) FROM STDIN") as cp:
                for r in readers:
                    cp.write_row(r)
            with cur.copy("COPY book (id, title, author, year, isbn) FROM STDIN") as cp:
                for b in books:
                    cp.write_row(b)
            with cur.copy("COPY copy (id, book_id, inventory_no, shelf) FROM STDIN") as cp:
                for c in copies:
                    cp.write_row(c)
            with cur.copy("COPY loan (copy_id, reader_id, issued_on, due_on, returned_on) FROM STDIN") as cp:
                for l in loans:
                    cp.write_row(l)
            for table in ("reader", "book", "copy"):
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")
        conn.execute("ANALYZE")
        conn.commit()
        print(f"наполнение {size}, схема {schema}:")
        for table in ("app_user", "reader", "book", "copy", "loan"):
            n = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"  {table:<9} {n}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SIZES:
        sys.exit("использование: python -m app.seed small|work")
    main(sys.argv[1])
