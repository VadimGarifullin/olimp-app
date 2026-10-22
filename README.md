# olimp-dbcheck

Мини-приложение: показывает, есть ли у него соединение с MySQL.

    cp .env.example .env    # поправить пароли и STAND_NAME
    docker compose up -d --build     # или docker-compose up -d --build
    curl -s http://127.0.0.1:8000/api/status

| Путь          | Что отдаёт                                  |
|---------------|---------------------------------------------|
| `/`           | страница: зелёная — БД доступна, красная — нет |
| `/api/status` | JSON, всегда 200                            |
| `/healthz`    | 200 / 503 в зависимости от БД               |
| `/metrics`    | `app_db_up`, `app_db_check_duration_seconds`, `app_info` |

Переменные: `DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD DB_TIMEOUT STAND_NAME`.
