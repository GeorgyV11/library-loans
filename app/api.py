"""Программный интерфейс /api - контракт сервиса (см. README.md)."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from . import repo
from .auth import authenticate, current_user
from .db import get_db
from .rules import IssueRefused

router = APIRouter(prefix="/api")


class LoginIn(BaseModel):
    login: str
    password: str


class IssueIn(BaseModel):
    reader_id: int
    copy_id: int


class ReturnIn(BaseModel):
    returned_on: date | None = None


@router.post("/login")
def login(body: LoginIn, request: Request, db=Depends(get_db)):
    user = authenticate(db, body.login, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="неверный логин или пароль")
    request.session["user"] = {"id": user["id"], "login": user["login"], "name": user["full_name"]}
    return request.session["user"]


@router.post("/logout", status_code=204)
def logout(request: Request):
    request.session.clear()
    return Response(status_code=204)


@router.get("/loans")
def loans(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Literal["all", "active", "overdue", "returned"] = "all",
    reader: str | None = None,
    user=Depends(current_user),
    db=Depends(get_db),
):
    return repo.list_loans(db, page, size, status, reader)


@router.get("/loans/{loan_id}")
def loan(loan_id: int, user=Depends(current_user), db=Depends(get_db)):
    try:
        return repo.get_loan(db, loan_id)
    except repo.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/loans", status_code=201)
def issue(body: IssueIn, user=Depends(current_user), db=Depends(get_db)):
    try:
        return repo.issue_loan(db, body.reader_id, body.copy_id, user["id"])
    except repo.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except IssueRefused as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/loans/{loan_id}/return")
def return_(loan_id: int, body: ReturnIn | None = None, user=Depends(current_user), db=Depends(get_db)):
    try:
        return repo.return_loan(db, loan_id, body.returned_on if body else None)
    except repo.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except IssueRefused as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/readers/{reader_id}")
def reader(
    reader_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    try:
        return repo.get_reader(db, reader_id, page, size)
    except repo.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/summary")
def summary(user=Depends(current_user), db=Depends(get_db)):
    return repo.summary(db)
