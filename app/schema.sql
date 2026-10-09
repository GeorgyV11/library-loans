-- Схема сервиса выдачи книг. Индексы сверх первичных ключей не создаются (ДЗ 1).
DROP SCHEMA IF EXISTS {schema} CASCADE;
CREATE SCHEMA {schema};
SET search_path TO {schema};

CREATE TABLE app_user (
    id            serial PRIMARY KEY,
    login         text NOT NULL,
    password_hash text NOT NULL,
    full_name     text NOT NULL
);

CREATE TABLE reader (
    id            serial PRIMARY KEY,
    full_name     text NOT NULL,
    email         text,
    phone         text,
    registered_on date NOT NULL
);

CREATE TABLE book (
    id     serial PRIMARY KEY,
    title  text NOT NULL,
    author text NOT NULL,
    year   integer,
    isbn   text
);

CREATE TABLE copy (
    id           serial PRIMARY KEY,
    book_id      integer NOT NULL REFERENCES book (id),
    inventory_no text NOT NULL,
    shelf        text
);

CREATE TABLE loan (
    id          serial PRIMARY KEY,
    copy_id     integer NOT NULL REFERENCES copy (id),
    reader_id   integer NOT NULL REFERENCES reader (id),
    issued_on   date NOT NULL,
    due_on      date NOT NULL,
    returned_on date,
    issued_by   integer REFERENCES app_user (id)
);
