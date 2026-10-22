"""olimp-dbcheck: показывает, есть ли у приложения связь с MySQL.

Endpoints:
  /            HTML-страница со статусом (автообновление)
  /api/status  JSON, всегда 200
  /healthz     200 если БД доступна, иначе 503
  /metrics     Prometheus: app_db_up, app_db_check_duration_seconds, app_info
"""
import os
import socket
import time
from datetime import datetime, timezone

import pymysql
from flask import Flask, Response, jsonify, render_template_string

APP_VERSION = "1.0.0"

DB = {
    "host": os.getenv("DB_HOST", "db"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "app"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "app"),
}
TIMEOUT = float(os.getenv("DB_TIMEOUT", "3"))
STAND = os.getenv("STAND_NAME") or socket.gethostname()

app = Flask(__name__)


def check_db() -> dict:
    started = time.monotonic()
    result = {"up": False, "version": None, "error": None}
    try:
        conn = pymysql.connect(
            **DB,
            connect_timeout=TIMEOUT,
            read_timeout=TIMEOUT,
            write_timeout=TIMEOUT,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION()")
                result["version"] = cur.fetchone()[0]
            result["up"] = True
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — показываем любую причину
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["duration_s"] = round(time.monotonic() - started, 4)
    result["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


def public_target() -> dict:
    return {k: DB[k] for k in ("host", "port", "user", "database")}


PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>{{ stand }} — {{ 'DB OK' if s.up else 'DB DOWN' }}</title>
<style>
  :root { color-scheme: light dark; --ok:#1f9d55; --bad:#d64545; }
  body { font-family: system-ui, sans-serif; margin: 0; display: grid; place-items: center; min-height: 100vh; }
  .card { max-width: 560px; width: calc(100% - 32px); border-radius: 14px; padding: 28px;
          box-shadow: 0 4px 24px rgba(0,0,0,.12); }
  .badge { display: inline-block; padding: 8px 16px; border-radius: 999px; color: #fff;
           font-weight: 700; font-size: 1.2rem; background: {{ 'var(--ok)' if s.up else 'var(--bad)' }}; }
  h1 { margin: 0 0 16px; font-size: 1.4rem; }
  table { width: 100%; border-collapse: collapse; margin-top: 18px; }
  td { padding: 6px 0; vertical-align: top; }
  td:first-child { opacity: .65; width: 40%; }
  code { word-break: break-word; }
  .err { color: var(--bad); }
  footer { margin-top: 18px; font-size: .8rem; opacity: .6; }
</style>
</head>
<body>
<div class="card">
  <h1>{{ stand }}</h1>
  <span class="badge">{{ 'MySQL: соединение есть' if s.up else 'MySQL: нет соединения' }}</span>
  <table>
    <tr><td>Сервер БД</td><td><code>{{ t.host }}:{{ t.port }}</code></td></tr>
    <tr><td>База / пользователь</td><td><code>{{ t.database }}</code> / <code>{{ t.user }}</code></td></tr>
    {% if s.up %}<tr><td>Версия MySQL</td><td><code>{{ s.version }}</code></td></tr>{% endif %}
    {% if s.error %}<tr><td>Ошибка</td><td class="err"><code>{{ s.error }}</code></td></tr>{% endif %}
    <tr><td>Время проверки</td><td>{{ (s.duration_s * 1000) | round(1) }} мс</td></tr>
    <tr><td>Проверено</td><td>{{ s.checked_at }}</td></tr>
    <tr><td>Контейнер</td><td><code>{{ host }}</code></td></tr>
  </table>
  <footer>olimp-dbcheck {{ version }} · обновление каждые 10 с · <a href="/api/status">/api/status</a></footer>
</div>
</body>
</html>"""


@app.get("/")
def index():
    return render_template_string(
        PAGE, s=check_db(), t=public_target(), stand=STAND,
        host=socket.gethostname(), version=APP_VERSION,
    )


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
    body = (
        "# HELP app_db_up 1 if the app can connect to MySQL and run a query\n"
        "# TYPE app_db_up gauge\n"
        f"app_db_up{{{labels}}} {1 if s['up'] else 0}\n"
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
