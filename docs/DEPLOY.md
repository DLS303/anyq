# Развёртывание Anyq на одном сервере

Инструкция для запуска в Казахстане на одном виртуальном сервере с Ubuntu 22.04 или 24.04. Внешние платные сервисы не нужны. Файл `render.yaml` в корне репозитория к этому контуру не относится и не меняется.

Данные приложения (файл `db.json`, загрузки, медиафайлы), резервные копии и сертификаты HTTPS лежат на диске этого сервера. Не копируйте их в хранилище за пределами Казахстана.

После того как сервер принимает SSH, а DNS-запись домена указывает на него, шаги ниже занимают около часа. Распространение DNS может занять больше времени и от этой инструкции не зависит.

## Что нужно купить

| Статья | Оценка |
| --- | --- |
| VPS: 2 vCPU, 4 ГБ RAM, диск 40–80 ГБ, Ubuntu 22.04 или 24.04, дата-центр в Казахстане | ____ ₸ / месяц |
| Домен (например `.kz`) | ____ ₸ / год |
| Резервные копии на том же диске | входят в диск VPS |
| Итого в месяц, без домена | ____ ₸ |
| Итого в месяц с доменом (домен / 12) | ____ ₸ |

Подойдёт любой такой VPS у казахстанского оператора (в том числе Hoster.kz). В панели провайдера откройте входящие порты 22, 80 и 443. Порт 5432 наружу не открывается.

## Что уже лежит в репозитории

- `apps/api/Dockerfile` — образ API: Python 3.11, gunicorn и несколько worker Uvicorn, пользователь `anyq` (uid 10001).
- `apps/web/Dockerfile` — образ сайта: Next.js standalone, пользователь `nextjs` (uid 1001). `NEXT_PUBLIC_PILOT_MODE` задаётся аргументом сборки.
- `deploy/docker-compose.prod.yml` — API, PostgreSQL, сайт и Caddy. Порты 80 и 443 публикует только Caddy. Порт 5432 наружу не публикуется.
- `deploy/Caddyfile` — HTTPS для имени из переменной `DOMAIN`.
- `deploy/.env.production.example` — перечень переменных без секретов.
- `deploy/bootstrap_server.sh`, `deploy/deploy.sh`, `deploy/backup.sh`, `deploy/anyq-backup.cron`.
- `.github/workflows/deploy.yml` — ручной деплой по SSH. Пока секреты не созданы, workflow ничего не делает.

Данные приложения лежат в PostgreSQL. `WEB_CONCURRENCY` может быть от 1 до 8, по умолчанию 2: записи и ключи идемпотентности хранятся в базе с ограничением уникальности, а не в одном JSON-файле. Том `anyq-data` остаётся для загрузок и медиа. Файл `db.json` нужен только для одноразового импорта, описанного ниже.

## Чеклист

- [ ] Арендован VPS в Казахстане, известен его IPv4.
- [ ] В панели провайдера открыты порты 22, 80 и 443.
- [ ] Куплен домен, создана A-запись на IPv4 сервера.
- [ ] С локальной машины проходит `ssh` под пользователем, которого создаст bootstrap (после шага 2 — `deploy`).
- [ ] Репозиторий склонирован в `/opt/anyq`.
- [ ] Заполнен `deploy/.env`, права `600`, `JWT_SECRET` сгенерирован на сервере.
- [ ] `deploy/check_env.sh` заканчивается фразой `Environment file is valid.`
- [ ] `deploy/deploy.sh` завершился без ошибки.
- [ ] `https://<домен>/healthz`, `https://<домен>/health` и `https://<домен>/ru` открываются.
- [ ] В браузере сертификат выдан для этого домена, без предупреждения.
- [ ] Установлен cron из `deploy/anyq-backup.cron`, пробный `deploy/backup.sh` создал архив.
- [ ] Если нужен деплой кнопкой из GitHub: записаны секреты `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`.

## 1. DNS

В панели регистратора домена создайте A-запись:

```text
<домен>    A    <IPv4 сервера>
```

Имя в записи — то же, что позже будет в `DOMAIN`, без `https://` и без пути. Отдельное имя `www` само не заработает: его нужно добавить и в DNS, и в `CORS_ORIGINS`, и в адрес сайта в `deploy/Caddyfile`. Для первого запуска достаточно одного имени.

Проверка с машины, где уже виден DNS:

```bash
dig +short <домен> A
```

Ответ должен быть IPv4 сервера. Пока запись не видна, Caddy не получит публичный сертификат.

## 2. Подготовка сервера

Войдите на сервер по SSH под пользователем, которого выдал провайдер. Склонируйте репозиторий во временный каталог и выполните подготовку от root:

```bash
git clone <URL репозитория> /tmp/anyq-src
sudo bash /tmp/anyq-src/deploy/bootstrap_server.sh
```

Скрипт обновляет пакеты, ставит Docker Engine и плагин Compose, включает firewall `ufw` (22, 80, 443), fail2ban для SSH и ежедневные security-обновления. Создаётся пользователь `deploy` в группе `docker` и каталоги `/opt/anyq` и `/var/backups/anyq`.

Добавьте свой публичный ключ:

```bash
sudo install -m 600 -o deploy -g deploy /dev/null /home/deploy/.ssh/authorized_keys
echo 'ssh-ed25519 AAAA... ваш ключ' | sudo tee -a /home/deploy/.ssh/authorized_keys
```

Проверьте вход с локальной машины: `ssh deploy@<IPv4> true`. Только после этого имеет смысл отключать вход по паролю в `sshd`. Скрипт сам парольный вход не выключает.

## 3. Код и переменные

На сервере, уже под пользователем `deploy`:

```bash
git clone <URL репозитория> /opt/anyq
cd /opt/anyq
git checkout <ветка, которую нужно запустить>
cp deploy/.env.production.example deploy/.env
chmod 600 deploy/.env
openssl rand -base64 48
```

Вставьте вывод `openssl` в `JWT_SECRET`. Дальше в том же файле:

- `DOMAIN` — голое имя, например `app.example.kz`.
- `ACME_EMAIL` — почта для уведомлений выпуска сертификата.
- `CORS_ORIGINS` — `https://` и то же имя, без пробелов. Если имён несколько, перечислите через запятую, и `https://<DOMAIN>` обязан быть в списке.
- `ANYQ_DEMO_PASSWORD` оставьте пустым.
- `POSTGRES_PASSWORD` — длинный пароль с сервера (`openssl rand -base64 32`). Не используйте `anyq`, `postgres`, `superapp`, `changeme`.
- `DATABASE_URL` — `postgresql+psycopg://anyq:<тот же пароль>@postgres:5432/anyq`. Compose подставляет пароль из `POSTGRES_PASSWORD` сам, но в файле адрес тоже должен быть адресом PostgreSQL.
- `WEB_CONCURRENCY` оставьте `2` или поставьте число от 1 до 8.
- `NEXT_PUBLIC_PILOT_MODE=1` включает пилотный интерфейс. Значение попадает в образ сайта на сборке. Смена потребует нового `deploy.sh`.
- `INTERNAL_API_URL` оставьте `http://api:8010`.

Контейнер API не стартует, если секрет пустой, короче 32 символов или похож на заготовку (`changeme`, `replace-me`, `test-only`, `superapp`, `your-secret` и те же слова в другом регистре). Пустой `CORS_ORIGINS`, символ `*` в нём, непустой демо-пароль и пароль базы по умолчанию тоже останавливают запуск. Тот же набор проверяет `deploy/check_env.sh` до сборки. Процесс Python дополнительно отказывается стартовать без `JWT_SECRET` достаточной длины и без `CORS_ORIGINS`.

```bash
./deploy/check_env.sh
```

Ожидаемая последняя строка: `Environment file is valid.`

## 4. Первый запуск

Из `/opt/anyq` под пользователем `deploy`:

```bash
./deploy/deploy.sh
```

Скрипт подтягивает ту же ветку с `origin` (fast-forward), собирает образы `anyq-api:current` и `anyq-web:current`, поднимает контейнеры и ждёт состояния healthy. Затем проверяет:

- `https://<DOMAIN>/healthz` — сайт;
- `https://<DOMAIN>/health` — API;
- `https://<DOMAIN>/v1/modules` — ответ API;
- `https://<DOMAIN>/ru` — страница.

Если проверка не проходит, скрипт возвращает предыдущие образы (`anyq-api:rollback` и `anyq-web:rollback`) и снова их запускает. На самом первом запуске предыдущих образов ещё нет: при ошибке в логе будет `no rollback image is available`.

Полезные команды:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml ps
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml logs --tail 100
```

Тома:

- `anyq-data` — `/data` в API: `uploads`, `private`, `public`. Старый `db.json` можно положить сюда для импорта.
- `anyq-postgres` — данные PostgreSQL. Удаление тома стирает базу.
- `anyq-caddy-data` и `anyq-caddy-config` — сертификаты. Удаление этих томов заставит Caddy запросить сертификат заново.

Логи контейнеров пишутся драйвером `json-file`: не больше 10 МБ на файл и 5 файлов на сервис. Лимиты ресурсов в compose-файле рассчитаны на 2 vCPU и 4 ГБ: API до 1 CPU и 1536 МБ, PostgreSQL до 0.5 CPU и 512 МБ, сайт до 0.75 CPU и 768 МБ, Caddy до 0.25 CPU и 128 МБ. Политика перезапуска — `unless-stopped`. Сервис `db-backup` снимает `pg_dump` в том `anyq-backups` (`/backups/pre-migrate.sql`) до старта `migrate`. Если дамп не создался, `migrate` не запускается. Сервис `migrate` один раз выполняет `alembic upgrade head` до старта API. API при старте таблицы не создаёт и отвечает 503 на `/ready`, пока версия схемы не совпадает с ожидаемой.

## 5. Проверка HTTPS

С любой машины, где открыт 443:

```bash
curl -fsS "https://<домен>/healthz"
curl -fsS "https://<домен>/health"
curl -fsS -o /dev/null -w '%{http_code}\n' "https://<домен>/ru"
```

Ожидание: в двух первых ответах есть `"ok":true`, у страницы код `200`. В браузере откройте `https://<домен>/ru` и убедитесь, что сертификат выдан на это имя и срок действия не истёк.

`/healthz` у сайта не ходит в API. `/health` и `/healthz` у API — отдельные адреса; снаружи через Caddy открыт `/health`. Адрес `/v1/...` Caddy отдаёт API, остальное — сайту.

Локальная проверка без домена использует `DOMAIN=localhost`. Caddy тогда выпускает локальный сертификат, и `curl` нужен флаг `-k`. Для боевого домена флаг `-k` не используйте.

## 6. Резервные копии

После первого успешного запуска:

```bash
./deploy/backup.sh
ls -lh /var/backups/anyq
```

Появляются два файла: `anyq-data-<дата>.tar.gz` (каталог `/data`: загрузки и медиа) и `anyq-postgres-<дата>.sql.gz` (`pg_dump` базы `anyq`). Срок хранения задаёт `BACKUP_RETENTION_DAYS` (по умолчанию 14).

Перед каждой миграцией compose дополнительно пишет `/backups/pre-migrate.sql` в томе `anyq-backups`. Это снимок, который делает `pg_dump` из `postgres:16-alpine` с паролем `POSTGRES_PASSWORD`. Файл непустой, иначе сервис `db-backup` завершается с ошибкой и `migrate` не стартует. Восстановление этого снимка: `psql` в уже запущенный PostgreSQL.

Ежедневный запуск в 03:15 UTC от пользователя `deploy`:

```bash
sudo cp /opt/anyq/deploy/anyq-backup.cron /etc/cron.d/anyq-backup
sudo chmod 644 /etc/cron.d/anyq-backup
```

Если репозиторий лежит не в `/opt/anyq`, поправьте путь в cron-файле до копирования.

Восстановление описано в шапке `deploy/backup.sh`. Кратко: остановить API, распаковать архив в том `anyq-data`, загрузить SQL в уже запущенный PostgreSQL командой `psql`, снова выполнить `docker compose ... up -d`. Расписание и архивы держите на этом сервере или на другом диске в Казахстане.

## Перенос db.json

Один раз, после того как сервис `migrate` завершился успешно. Скрипт идемпотентный: повторный запуск обновляет изменившиеся строки и оставляет совпавшие. В отчёте для каждой коллекции три числа: `insert`, `update`, `same`. Флаг `--dry-run` печатает те же числа и ничего не записывает.

Положите прежний файл в том данных, например `/data/db.json` внутри контейнера API, и выполните из `/opt/anyq`:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml exec -T api \
  python scripts/import_json.py /data/db.json --dry-run
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml exec -T api \
  python scripts/import_json.py /data/db.json
```

Локально, из каталога `apps/api`, тот же скрипт читает `DATABASE_URL`. Пустой `DATABASE_URL` пишет в SQLite рядом с путём `ANYQ_DB_PATH`.

```bash
cd apps/api
python scripts/import_json.py ../../data/db.json --dry-run
python scripts/import_json.py ../../data/db.json
```

## 7. Обновление

На сервере, в `/opt/anyq`, под пользователем `deploy`:

```bash
./deploy/deploy.sh
```

По умолчанию скрипт обновляет текущую ветку fast-forward с `origin`. Другая ветка:

```bash
DEPLOY_REF=<ветка> ./deploy/deploy.sh
```

Перед сборкой скрипт запоминает образы, которые в этот момент healthy, как `anyq-api:rollback` и `anyq-web:rollback`. Смена `NEXT_PUBLIC_PILOT_MODE` применяется только вместе с пересборкой образа сайта.

## 8. Откат

Если новый выпуск прошёл проверки, но его нужно убрать вручную и предыдущие образы ещё есть:

```bash
cd /opt/anyq
docker tag anyq-api:rollback anyq-api:current
docker tag anyq-web:rollback anyq-web:current
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml up -d --no-build
```

Автоматический откат при неудачном `deploy.sh` делает то же самое. Если контейнер API перезапускается по кругу из-за `deploy/.env`, смотрите причину так:

```bash
docker logs anyq-api --tail 50
```

Исправьте файл и снова запустите `./deploy/deploy.sh`. Секрет в репозиторий не кладите.

## 9. GitHub Actions

Файл `.github/workflows/deploy.yml` запускается только вручную (`workflow_dispatch`). Пока в секретах репозитория нет всех трёх значений, job деплоя пропускается:

- `DEPLOY_HOST` — IPv4 или имя сервера;
- `DEPLOY_USER` — `deploy`;
- `DEPLOY_SSH_KEY` — приватный ключ, пара к ключу в `/home/deploy/.ssh/authorized_keys`.

Необязательный секрет `DEPLOY_KNOWN_HOSTS` — строка из `ssh-keygen -f ~/.ssh/known_hosts -F <хост>`. Если его нет, первый запуск примет ключ сервера (`accept-new`).

В поле `ref` укажите ветку, которая уже запушена и которую сервер может получить из `origin`. На сервере репозиторий должен быть в `/opt/anyq`. Workflow выполняет там `deploy/deploy.sh`.

Существующий `.github/workflows/ci.yml` этот файл не заменяет. Проверки pull request идут через него.

## 10. Что скрипты не делают

- Не покупают сервер и домен и не создают DNS-запись.
- Не генерируют боевой `JWT_SECRET` за вас: его нужно создать на сервере и оставить только в `deploy/.env`.
- Не выключают парольный SSH. Это отдельное решение после проверки входа по ключу.
- Не копируют старый `db.json` сами. Импорт описан в разделе «Перенос db.json» и запускается отдельно.
- Не публикуют порт API и порт сайта на хосте.
- Не отправляют копии за пределы машины.
