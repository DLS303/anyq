# База недоступна

Регламент на случай, когда PostgreSQL пилотного контура не принимает
соединения или контейнер базы не становится здоровым. Уровень, роли
и эскалация — в [`deploy/INCIDENT.md`](../../deploy/INCIDENT.md).

Алерты приходят в любое время. Шаги человека выполняют в рабочие часы
(Asia/Almaty, UTC+5). Срок уровня считают в рабочих часах.

Команды рассчитаны на образ и роли после задачи DevOps по базе.
До неё администратор кластера — `anyq`, `pgbackrest` не установлен,
восстановление — только из логического дампа.

Команды ниже запускает IT/MLOps или SQL-разработчик из `/opt/anyq`
под пользователем `deploy`. Координатор до этого записывает уровень
и метку времени восстановления, если дошли до pgBackRest.

Цель плана, не гарантия для клиента: RPO не больше 15 минут
(`archive_timeout=60` в конфигурации DevOps), RTO — ≤ 4 ч (пилот).
В письмо клиенту эти цифры не ставят.

## Признаки

- `https://<домен>/health` не отвечает или не содержит `"ok":true`, при этом страница сайта может ещё открываться.
- Контейнер `anyq-postgres` в состоянии `exited`, `restarting` или `unhealthy`.
- `pg_isready` для базы `anyq` завершается с ошибкой.
- В журнале API повторяются ошибки соединения с базой. Текст ошибок в канал не копируют.

Один неуспешный запрос при живой базе — это не SEV1. Координатор
ставит SEV1, если пилотный клиент не может работать или база не
поднимается. Иначе начинают с SEV2.

## Первые 15 минут

Пятнадцать минут считают от момента старта срока в
[`deploy/INCIDENT.md`](../../deploy/INCIDENT.md), внутри рабочего окна.

1. Координатор (дежурный DLS) ставит уровень и открывает карточку по [`docs/incidents/TEMPLATE.md`](../incidents/TEMPLATE.md).
2. Эскалация: IT/MLOps, затем SQL-разработчик. Разработчика приложения зовут, если после подъёма базы API всё ещё нездоров. Собственника зовут при SEV1.
3. Не удаляйте тома `anyq-postgres` и `anyq-data`. Не запускайте `docker compose down -v`.
4. Снимите состояние, не выводя строки таблиц:

   ```bash
   cd /opt/anyq
   docker compose --env-file deploy/.env \
     -f deploy/docker-compose.prod.yml ps
   docker inspect -f '{{.State.Health.Status}}' anyq-postgres
   df -h
   ```

5. Если диск заполнен и база ещё принимает сессию, смотрят архиватор. Файлы в `pg_wal` вручную не удаляют. Место освобождают вне каталога WAL и вне репозитория копий.

   ```sql
   SELECT archived_count, failed_count, last_archived_time, last_failed_time
   FROM pg_stat_archiver;
   ```

## Восстановление

Сначала возвращают уже остановленный кластер, если том на месте
и читается. Восстановление из копии — если SQL-разработчик записал,
что кластер не читается, или если нужен момент времени до повреждения.

Существующий том всегда запускают тем образом, которым он создан.
Образ `postgis/postgis:16-3.4` — после миграции на этот образ
(задача DevOps). Перенос локального стенда с Alpine на PostGIS —
только дамп в новый пустой том. Боевой том другим образом не
запускают.

`deploy/restore.sh` — будет добавлено: он восстанавливает в отдельный
том. Пока его нет, pgBackRest на месте выполняют только при SEV1
и только если координатор записал это решение. В остальных случаях
ждут скрипт.

Остановка API и базы, чтобы API не писал в кластер:

```bash
cd /opt/anyq
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop api postgres
```

Если контейнер просто остановлен и том трогать не нужно, его
запускают файлом compose, без второго образа:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d postgres
docker inspect -f '{{.State.Health.Status}}' anyq-postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  pg_isready -U anyq -d anyq
```

Если база здорова, переходят к разделу «Проверка» и затем
поднимают остальные сервисы. Шаг migrate отдельно и только если
ревизия в `alembic_version` старше ожидаемой. `alembic downgrade`
в бою запрещён.

### Копия тома

Любое копирование тома или каталога данных через tar делают только
после остановки PostgreSQL. Файлы в `pg_wal` вручную не удаляют.
Архив снимает тот же сервис `postgres`, тем же образом, которым
создан том.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml run --rm --no-deps -T \
  --user root --entrypoint tar \
  -v /var/backups/anyq:/backup \
  postgres \
  -C /var/lib/postgresql/data \
  -czf /backup/anyq-pgvolume-<штамп>.tar.gz .
tar -tzf /var/backups/anyq/anyq-pgvolume-<штамп>.tar.gz >/dev/null
```

Эта копия — слепок тома в Казахстане, не замена pgBackRest.
Пока `tar -tzf` не прошёл, том не удаляют.

### pgBackRest

На месте — только SEV1 и запись решения координатора, как сказано
выше. Пароль шифрования репозитория берут только из офлайн-хранилища
`<офлайн-хранилище>`. В команду, карточку, чат и git его не вставляют.
Метку выбирает SQL-разработчик и пишет в карточку как
`<YYYY-MM-DD HH:MM:SS+05>` (пример `2026-10-24 10:15:00+05`).
Кластер в UTC, смещение в `--target` обязательно. Для повреждённого
шага migrate это момент непосредственно до шага.

`pgbackrest` на хосте нет. `run --rm` — только пока `postgres`
остановлен: так запускают `info`, `restore` и `verify`, они читают
репозиторий. `check` и `backup` выполняют через `exec`, когда
`postgres` уже работает. Одноразовый контейнер сокет этой базы
не видит. Том при этом не меняет образ. Репозиторий за пределами
Казахстана не используют.

Пароль шифрования в команду, карточку, чат и git не пишут.
Файл `deploy/.env.pgbackrest` лежит только на сервере, права `600`,
в репозиторий его не добавляют. Внутри одна переменная
`PGBACKREST_REPO2_CIPHER_PASS`, значение из `<офлайн-хранилище>`.
Одноразовый контейнер получает файл через `--env-file`. Рабочий
контейнер должен видеть ту же переменную с момента запуска
(задача DevOps): иначе архивация в зашифрованный репозиторий не идёт.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop api postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml run --rm --no-deps -T \
  --user postgres \
  --env-file deploy/.env.pgbackrest \
  postgres \
  pgbackrest --stanza=anyq info
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml run --rm --no-deps -T \
  --user postgres \
  --env-file deploy/.env.pgbackrest \
  postgres \
  pgbackrest --stanza=anyq restore --delta --type=time \
  --target='<YYYY-MM-DD HH:MM:SS+05>' --target-action=promote
```

Затем тот же образ из файла compose. `check` и полную копию
выполняют в уже запущенном контейнере:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user postgres postgres \
  pgbackrest --stanza=anyq check
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user postgres postgres \
  pgbackrest --stanza=anyq backup --type=full
```

### Логический дамп

Логический дамп (`pg_dump --no-owner --no-privileges`) не подменяет
pgBackRest. Его грузят только если координатор записал, что
репозиторий pgBackRest для этой метки недоступен, а дамп проверен
`gzip -t`. Дамп не восстанавливает владельцев и права.

Три роли. Роль `postgres` (`POSTGRES_USER`) создаёт роли и базу,
выдаёт и снимает права, запускает `pg_amcheck`. Роль `anyq` —
владелец таблиц: она грузит дамп и выполняет шаг migrate. Роль
приложения — `anyq_app`. Приложению роль `postgres` не выдают.

Пароли берут из офлайн-хранилища. В SQL, карточку и git их не пишут.
В интерактивной сессии `psql` под ролью `postgres`: `\password anyq`
и `\password anyq_app`.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -it postgres \
  psql --username postgres --dbname postgres
```

Дальше в этой сессии, роль `postgres`. Если роль `anyq` уже есть,
строку `CREATE ROLE anyq` пропускают. `ALTER ROLE anyq ... NOSUPERUSER`
не выполняют.

```sql
-- выполняет роль postgres
CREATE ROLE anyq WITH LOGIN;
CREATE ROLE anyq_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
```

Базу создают так и только так, если её ещё нет. Если образ уже
создал пустую базу `anyq`, эту команду пропускают. Владелец —
роль `anyq`. Базу, в которой уже есть данные, этим путём не стирают.

```sql
-- выполняет роль postgres
CREATE DATABASE anyq OWNER anyq
  TEMPLATE template0
  ENCODING 'UTF8'
  LOCALE_PROVIDER icu
  ICU_LOCALE 'ru-KZ';
```

Дамп загружает роль `anyq`:

```bash
gunzip -c /var/backups/anyq/anyq-postgres-<штамп>.sql.gz \
  | docker compose --env-file deploy/.env \
    -f deploy/docker-compose.prod.yml exec -T postgres \
    psql --username anyq --dbname anyq -v ON_ERROR_STOP=1
```

После загрузки права заново применяет роль `postgres`. Если рядом
с дампом лежит `<скрипт-прав>`, берут его. `REVOKE` в нём — отдельные
команды, по одной таблице. Иначе минимум такой:

```sql
-- выполняет роль postgres
GRANT CONNECT ON DATABASE anyq TO anyq_app;
GRANT USAGE ON SCHEMA public TO anyq_app;
GRANT SELECT, INSERT, UPDATE, DELETE
  ON ALL TABLES IN SCHEMA public TO anyq_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anyq_app;
ALTER DEFAULT PRIVILEGES FOR ROLE anyq IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anyq_app;
ALTER DEFAULT PRIVILEGES FOR ROLE anyq IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO anyq_app;
REVOKE UPDATE, DELETE, TRUNCATE ON consent_events FROM anyq_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Строку журнала аудита выполняют отдельной командой и только после
миграции журнала аудита. Пока таблицы `audit_log` нет, эту команду
пропускают. Так `REVOKE` для `consent_events` применяется сам по себе.

```sql
-- выполняет роль postgres, после миграции журнала аудита
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM anyq_app;
```

Том загрузок `anyq-data` этими командами не трогают.

## Проверка

Сверяют ревизию с ожидаемой `<ревизия>` из карточки выпуска.
Числа строк — с прошлыми известными счётчиками `<счётчики>`,
не с выгрузкой людей. `max(created_at)` не позже метки
`<YYYY-MM-DD HH:MM:SS+05>`. Сами строки, почту и `payload` не выводят.
Запросы счёта выполняет роль `anyq`.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname anyq -c \
  'SELECT version_num FROM alembic_version;'
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname anyq -c \
  "SELECT collection, count(*) AS rows
   FROM records GROUP BY collection ORDER BY collection;"
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname anyq -c \
  'SELECT max(created_at) AS newest FROM records;'
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml run --rm --no-deps -T \
  --user postgres \
  --env-file deploy/.env.pgbackrest \
  postgres \
  pgbackrest --stanza=anyq verify
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user postgres postgres \
  pg_amcheck --username postgres -d anyq \
  --install-missing --heapallindexed
```

`pg_amcheck` выполняет роль `postgres`. Флаг `--all` не ставят.

Если точка восстановления — момент до migrate, к запуску API теги
`anyq-api:current` и `anyq-web:current` уже стоят с образов отката.
Как их вернуть — в [`docs/runbooks/bad-deploy.md`](bad-deploy.md).
Иначе старт API снова выполнит этот migrate.

После этого поднимают API и смотрят готовность внутри контейнера,
на `127.0.0.1`, порт процесса API:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T api \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/v1/health/ready', timeout=3).read()"
```

Ожидание: `pg_amcheck` без ошибок, `pgbackrest --stanza=anyq verify`
без ошибок, ревизия совпала, числа строк сходятся со `<счётчики>`,
`newest` не позже `<YYYY-MM-DD HH:MM:SS+05>`, ответ ready без ошибки.
Снаружи, когда вход уже открыт: `/health` и `/healthz` содержат
`"ok":true`. Для боевого домена флаг `-k` не используют.

## Коммуникации

Если пилотный клиент уже видит простой, координатор готовит письмо
по [`docs/runbooks/comms.md`](comms.md). Текст одобряет собственник.
В письмо не ставят штамп архива, имя узла и причину на уровне команд.

Пока клиент работу не терял, внешнее письмо не отправляют.
В канале достаточно номера карточки и уровня.

## После инцидента

1. Допишите хронологию в закрытой карточке.
2. Если было восстановление, полная копия уже снята командой `pgbackrest --stanza=anyq backup --type=full`. Её вторая точка — в Казахстане. Логический дамп `deploy/backup.sh` эту копию не заменяет.
3. Для SEV1 и SEV2 назначьте разбор по [`docs/incidents/POSTMORTEM.md`](../incidents/POSTMORTEM.md) в рабочие часы.
4. Образы и тома, которые не стирали, не удаляйте до конца разбора.
