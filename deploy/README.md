# Переменные сервера

Значения лежат в `deploy/.env` на сервере, права `600`. В репозитории их нет. Дату смены записывает оператор у себя, не в git.

| Имя | Где значение | Что это |
| --- | --- | --- |
| `JWT_SECRET` | `deploy/.env` | секрет сессий |
| `LOGIN_HASH_SECRET` | `deploy/.env` | секрет окна входа |
| `POSTGRES_PASSWORD` | `deploy/.env` | пароль базы |
| `AGE_RECIPIENT` | `deploy/.env` | публичный ключ age |
| `AGE_IDENTITY_FILE` | только машина, где запускают `deploy/restore.sh`, путь вне репозитория | приватный ключ age |
| `RCLONE_REMOTE_1` | `deploy/.env`, имя | первое хранилище в Казахстане |
| `RCLONE_REMOTE_2` | `deploy/.env`, имя | второе хранилище в Казахстане |

Остальные имена без значений перечислены в `deploy/.env.production.example`.
