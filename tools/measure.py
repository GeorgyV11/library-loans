"""Замер времени ответа операций контракта.

    python tools/measure.py --label small [--base http://localhost:8000] [--repeat 20]

Для каждой операции: один прогревочный запрос (в расчёт не входит), затем серия
повторов под учётной записью librarian. Время ответа снимается на клиенте;
время в базе и число запросов - из заголовков X-DB-Time-ms и X-DB-Queries,
которые выставляет сервис. Результат - таблица в консоли и results/<label>.json.
"""
import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import httpx

LOGIN = {"login": "librarian", "password": "library"}


def pct(values, p):
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def timed(client, method, url, **kw):
    started = time.perf_counter()
    r = client.request(method, url, **kw)
    ms = (time.perf_counter() - started) * 1000
    return r, ms


def series(name, call, repeat):
    call()                                   # прогрев
    rows = []
    for _ in range(repeat):
        r, ms = call()
        rows.append((ms, float(r.headers["X-DB-Time-ms"]), int(r.headers["X-DB-Queries"]), r.status_code))
    times = [x[0] for x in rows]
    return {
        "operation": name,
        "status": sorted({x[3] for x in rows}),
        "p50": statistics.median(times), "p95": pct(times, 95), "max": max(times),
        "db_ms": statistics.median(x[1] for x in rows),
        "queries": statistics.median(x[2] for x in rows),
        "raw": times,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--repeat", type=int, default=20)
    a = ap.parse_args()

    c = httpx.Client(base_url=a.base, timeout=120)
    results = []
    anon = httpx.Client(base_url=a.base, timeout=120)
    results.append(series("POST /api/login", lambda: timed(anon, "POST", "/api/login", json=LOGIN), a.repeat))
    results.append(series("POST /api/logout", lambda: timed(anon, "POST", "/api/logout"), a.repeat))

    assert c.post("/api/login", json=LOGIN).status_code == 200
    ops = [
        ("GET /api/loans (стр. 1)", "/api/loans?page=1&size=20"),
        ("GET /api/loans (фильтр)", "/api/loans?status=overdue&reader=Иванов&page=1&size=20"),
        ("GET /api/loans/{id}", "/api/loans/150"),
        ("GET /api/readers/{id}", "/api/readers/25"),
        ("GET /api/summary", "/api/summary"),
    ]
    for name, url in ops:
        results.append(series(name, lambda url=url: timed(c, "GET", url), a.repeat))

    # выдача и возврат: свободный экземпляр и читатель без просрочки, цикл «выдать - вернуть»
    reader_id = next(i for i in range(1, 51) if not c.get(f"/api/readers/{i}").json()["has_overdue"])
    copy_id = None
    for i in range(1, 201):                 # первый свободный экземпляр; пробная выдача сразу закрывается
        r = c.post("/api/loans", json={"reader_id": reader_id, "copy_id": i})
        if r.status_code == 201:
            copy_id = i
            c.post(f"/api/loans/{r.json()['id']}/return", json={})
            break
    last = {"loan": None}

    def issue():
        r, ms = timed(c, "POST", "/api/loans", json={"reader_id": reader_id, "copy_id": copy_id})
        last["loan"] = r.json()["id"]
        c.post(f"/api/loans/{last['loan']}/return", json={})   # освободить экземпляр, вне замера
        return r, ms

    def give_back():
        loan = c.post("/api/loans", json={"reader_id": reader_id, "copy_id": copy_id}).json()["id"]  # вне замера
        return timed(c, "POST", f"/api/loans/{loan}/return", json={})

    results.append(series("POST /api/loans", issue, a.repeat))
    results.append(series("POST /api/loans/{id}/return", give_back, a.repeat))
    added = 1 + 2 * (a.repeat + 1)

    out = Path(__file__).resolve().parent.parent / "results"
    out.mkdir(exist_ok=True)
    meta = {"label": a.label, "repeat": a.repeat, "warmup": 1, "account": "librarian",
            "python": platform.python_version(), "loans_added_by_measure": added}
    (out / f"{a.label}.json").write_text(json.dumps({"meta": meta, "results": results}, ensure_ascii=False, indent=1))

    print(f"замер {a.label}: {a.repeat} повторов после прогрева, учётная запись librarian")
    print(f"{'операция':<30}{'p50, мс':>10}{'p95, мс':>10}{'макс, мс':>10}{'база, мс':>10}{'запросов':>10}  коды")
    for r in results:
        print(f"{r['operation']:<30}{r['p50']:>10.1f}{r['p95']:>10.1f}{r['max']:>10.1f}"
              f"{r['db_ms']:>10.1f}{r['queries']:>10.0f}  {','.join(map(str, r['status']))}")
    print(f"замер добавил выдач: {added}")


if __name__ == "__main__":
    main()
