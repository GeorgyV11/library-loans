"""HTML-страницы (клиентская часть): формируются сервером из тех же операций, что и API."""
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import repo
from .auth import authenticate
from .config import settings
from .db import get_db
from .rules import IssueRefused

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["prefix"] = settings.db_schema


def page(request, name, **ctx):
    return templates.TemplateResponse(request, name, {"user": request.session.get("user"), **ctx})


def need_login(request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)
    return None


@router.get("/", response_class=HTMLResponse)
def index():
    return RedirectResponse("/loans", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return page(request, "login.html", error=None)


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, login: str = Form(...), password: str = Form(...), db=Depends(get_db)):
    user = authenticate(db, login, password)
    if user is None:
        return page(request, "login.html", error="Неверный логин или пароль")
    request.session["user"] = {"id": user["id"], "login": user["login"], "name": user["full_name"]}
    return RedirectResponse("/loans", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/loans", response_class=HTMLResponse)
def loans(request: Request, page_no: int = 1, status: str = "all", reader: str = "", db=Depends(get_db)):
    if r := need_login(request):
        return r
    status = status if status in repo.STATUSES else "all"
    data = repo.list_loans(db, max(page_no, 1), 20, status, reader or None)
    pages = max(1, -(-data["total"] // 20))
    return page(request, "loans.html", data=data, status=status, reader=reader, pages=pages)


@router.get("/loans/new", response_class=HTMLResponse)
def issue_form(request: Request):
    if r := need_login(request):
        return r
    return page(request, "issue.html", error=None, reader_id="", copy_id="")


@router.post("/loans/new", response_class=HTMLResponse)
def issue(request: Request, reader_id: int = Form(...), copy_id: int = Form(...), db=Depends(get_db)):
    if r := need_login(request):
        return r
    try:
        loan = repo.issue_loan(db, reader_id, copy_id, request.session["user"]["id"])
    except (repo.NotFound, IssueRefused) as e:
        return page(request, "issue.html", error=str(e), reader_id=reader_id, copy_id=copy_id)
    return RedirectResponse(f"/loans/{loan['id']}", status_code=303)


@router.get("/loans/{loan_id}", response_class=HTMLResponse)
def loan(request: Request, loan_id: int, db=Depends(get_db)):
    if r := need_login(request):
        return r
    try:
        data = repo.get_loan(db, loan_id)
    except repo.NotFound:
        return page(request, "error.html", message="Выдача не найдена")
    return page(request, "loan.html", loan=data, error=request.query_params.get("error"))


@router.post("/loans/{loan_id}/return")
def return_(request: Request, loan_id: int, db=Depends(get_db)):
    if r := need_login(request):
        return r
    try:
        repo.return_loan(db, loan_id)
    except (repo.NotFound, IssueRefused) as e:
        return RedirectResponse(f"/loans/{loan_id}?error={e}", status_code=303)
    return RedirectResponse(f"/loans/{loan_id}", status_code=303)


@router.get("/readers/{reader_id}", response_class=HTMLResponse)
def reader(request: Request, reader_id: int, db=Depends(get_db)):
    if r := need_login(request):
        return r
    try:
        data = repo.get_reader(db, reader_id)
    except repo.NotFound:
        return page(request, "error.html", message="Читатель не найден")
    return page(request, "reader.html", reader=data)


@router.get("/summary", response_class=HTMLResponse)
def summary(request: Request, db=Depends(get_db)):
    if r := need_login(request):
        return r
    return page(request, "summary.html", s=repo.summary(db))
