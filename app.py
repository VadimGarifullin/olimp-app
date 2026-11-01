"""TechStart — приложение компании для олимпиады olimp.almetpt.tech.

Показывает, есть ли связь с MySQL, сколько сотрудников в базе, и отдаёт
внутренний справочник сотрудников.

Endpoints:
  /            главная страница: статус БД и число сотрудников
  /health      JSON: {"stand", "db": "ok"|"error", "employees", "error"}; 200 / 503
  /internal    справочник сотрудников (публиковать только во внутренний портал)
  /api/status  JSON со всеми деталями, всегда 200
  /healthz     200 / 503 (для docker healthcheck и балансировщиков)
  /metrics     Prometheus: app_db_up, app_employees, app_db_check_duration_seconds, app_info

Переменные окружения:
  STAND                         имя стенда, например stand03
  DB_HOST, DB_PORT              адрес и порт MySQL
  DB_NAME, DB_USER, DB_PASSWORD параметры подключения
  DB_TIMEOUT                    таймаут подключения, сек (по умолчанию 3)
"""
import os
import socket
import time
from datetime import datetime, timezone

import pymysql
from flask import Flask, Response, jsonify, render_template_string

APP_VERSION = "2.0.0"

DB = {
    "host": os.getenv("DB_HOST", "mysql"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "techstart"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "techstart"),
}
TIMEOUT = float(os.getenv("DB_TIMEOUT", "3"))
# STAND — по заданию; STAND_NAME — совместимость с первой версией
STAND = os.getenv("STAND") or os.getenv("STAND_NAME") or socket.gethostname()

EMPLOYEES_SQL = """
    SELECT e.full_name, e.position, d.name, e.phone_ext, e.email
    FROM employees e JOIN departments d ON d.id = e.department_id
    ORDER BY d.id, e.id
"""

app = Flask(__name__)


def connect():
    return pymysql.connect(
        **DB,
        connect_timeout=TIMEOUT,
        read_timeout=TIMEOUT,
        write_timeout=TIMEOUT,
        charset="utf8mb4",
    )


def check_db() -> dict:
    """up — подключение и запрос к серверу работают.
    employees — COUNT(*) из таблицы employees или None, если данных нет."""
    started = time.monotonic()
    res = {"up": False, "version": None, "employees": None, "error": None}
    try:
        conn = connect()
    except Exception as exc:  # noqa: BLE001 — показываем любую причину
        res["error"] = f"{type(exc).__name__}: {exc}"
    else:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION()")
                res["version"] = cur.fetchone()[0]
                res["up"] = True
                try:
                    cur.execute("SELECT COUNT(*) FROM employees")
                    res["employees"] = int(cur.fetchone()[0])
                except pymysql.MySQLError as exc:
                    res["error"] = f"data not loaded: {exc.args[-1] if exc.args else exc}"
        except Exception as exc:  # noqa: BLE001
            res["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            conn.close()
    res["duration_s"] = round(time.monotonic() - started, 4)
    res["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return res


def public_target() -> dict:
    return {k: DB[k] for k in ("host", "port", "user", "database")}


BASE_CSS = """
  :root { color-scheme: light dark; --ok:#1f9d55; --bad:#d64545; --warn:#c77d00; }
  body { font-family: system-ui, sans-serif; margin: 0; }
  code { word-break: break-word; }
  .badge { display:inline-block; padding:8px 16px; border-radius:999px; color:#fff; font-weight:700; }
  .ok { background: var(--ok); } .bad { background: var(--bad); } .warn { background: var(--warn); }
  .err { color: var(--bad); }
  footer { margin-top: 18px; font-size: .8rem; opacity: .6; }
"""

PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="olimp-dbcheck">
<meta http-equiv="refresh" content="10">
<title>TechStart · {{ stand }}</title>
<style>{{ css }}
  body { display:grid; place-items:center; min-height:100vh; }
  .card { max-width:560px; width:calc(100% - 32px); border-radius:14px; padding:28px;
          box-shadow:0 4px 24px rgba(0,0,0,.12); }
  h1 { margin:0 0 16px; font-size:1.4rem; }
  table { width:100%; border-collapse:collapse; margin-top:18px; }
  td { padding:6px 0; vertical-align:top; }
  td:first-child { opacity:.65; width:40%; }
</style>
</head>
<body>
<div class="card">
  <h1>TechStart · {{ stand }}</h1>
  {% if s.up and s.employees is not none %}
    <span class="badge ok">MySQL: соединение есть</span>
  {% elif s.up %}
    <span class="badge warn">MySQL: соединение есть, данных нет</span>
  {% else %}
    <span class="badge bad">MySQL: нет соединения</span>
  {% endif %}
  <table>
    <tr><td>Сервер БД</td><td><code>{{ t.host }}:{{ t.port }}</code></td></tr>
    <tr><td>База / пользователь</td><td><code>{{ t.database }}</code> / <code>{{ t.user }}</code></td></tr>
    {% if s.up %}<tr><td>Версия MySQL</td><td><code>{{ s.version }}</code></td></tr>{% endif %}
    {% if s.employees is not none %}<tr><td>Сотрудников в базе</td><td><b>{{ s.employees }}</b></td></tr>{% endif %}
    {% if s.error %}<tr><td>Ошибка</td><td class="err"><code>{{ s.error }}</code></td></tr>{% endif %}
    <tr><td>Время проверки</td><td>{{ (s.duration_s * 1000) | round(1) }} мс</td></tr>
    <tr><td>Проверено</td><td>{{ s.checked_at }}</td></tr>
    <tr><td>Контейнер</td><td><code>{{ host }}</code></td></tr>
  </table>
  <footer>TechStart {{ version }} · olimp-dbcheck · <a href="/health">/health</a></footer>
</div>
</body>
</html>"""

INTERNAL_PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="olimp-internal-directory">
<title>Справочник сотрудников · {{ stand }}</title>
<style>{{ css }}
  main { max-width:960px; margin:32px auto; padding:0 16px; }
  table { width:100%; border-collapse:collapse; margin-top:16px; }
  th, td { text-align:left; padding:8px; border-bottom:1px solid rgba(127,127,127,.3); }
  th { opacity:.7; font-weight:600; }
</style>
</head>
<body>
<main>
  <span class="badge warn">INTERNAL</span>
  <h1>Справочник сотрудников TechStart · {{ stand }}</h1>
  {% if error %}
    <p class="err"><code>{{ error }}</code></p>
  {% else %}
    <p>Сотрудников: {{ rows | length }}</p>
    <table>
      <tr><th>ФИО</th><th>Должность</th><th>Отдел</th><th>Вн. тел.</th><th>Email</th></tr>
      {% for name, pos, dep, ext, email in rows %}
      <tr><td>{{ name }}</td><td>{{ pos }}</td><td>{{ dep }}</td><td>{{ ext }}</td><td>{{ email }}</td></tr>
      {% endfor %}
    </table>
  {% endif %}
  <footer>olimp-internal-directory · TechStart {{ version }}</footer>
</main>
</body>
</html>"""


@app.get("/")
def index():
    return render_template_string(
        PAGE, s=check_db(), t=public_target(), stand=STAND, css=BASE_CSS,
        host=socket.gethostname(), version=APP_VERSION,
    )


@app.get("/health")
def health():
    s = check_db()
    body = {
        "stand": STAND,
        "db": "ok" if s["up"] else "error",
        "employees": s["employees"],
        "error": s["error"],
    }
    return jsonify(body), (200 if s["up"] else 503)


@app.get("/internal")
def internal():
    rows, error = [], None
    try:
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute(EMPLOYEES_SQL)
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    html = render_template_string(
        INTERNAL_PAGE, rows=rows, error=error, stand=STAND, css=BASE_CSS, version=APP_VERSION,
    )
    # 200 и при ошибке БД: маркер страницы нужен проверкам маршрутизации (4.4) и утечек (4.5)
    return html


@app.get("/api/status")
def api_status():
    return jsonify(stand=STAND, app_version=APP_VERSION, db=public_target(), **check_db())


@app.get("/healthz")
def healthz():
    s = check_db()
    return jsonify(up=s["up"], error=s["error"]), (200 if s["up"] else 503)


@app.get("/metrics")
def metrics():
    s = check_db()
    labels = f'stand="{STAND}",db_host="{DB["host"]}"'
    emp = s["employees"] if s["employees"] is not None else "NaN"
    body = (
        "# HELP app_db_up 1 if the app can connect to MySQL and run a query\n"
        "# TYPE app_db_up gauge\n"
        f"app_db_up{{{labels}}} {1 if s['up'] else 0}\n"
        "# HELP app_employees Rows in techstart.employees (NaN if not loaded)\n"
        "# TYPE app_employees gauge\n"
        f"app_employees{{{labels}}} {emp}\n"
        "# HELP app_db_check_duration_seconds Duration of the DB check\n"
        "# TYPE app_db_check_duration_seconds gauge\n"
        f"app_db_check_duration_seconds{{{labels}}} {s['duration_s']}\n"
        "# HELP app_info Static app info\n"
        "# TYPE app_info gauge\n"
        f'app_info{{stand="{STAND}",version="{APP_VERSION}"}} 1\n'
    )
    return Response(body, mimetype="text/plain; version=0.0.4")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
