# База недоступна

Регламент на случай, когда PostgreSQL пилотного контура не принимает
соединения или контейнер базы не становится здоровым. Уровень, роли
и эскалация — в [`deploy/INCIDENT.md`](../../deploy/INCIDENT.md).

Алерты приходят в любое время. Шаги человека выполняют в рабочие часы
(Asia/Almaty, UTC+5). Срок уровня считают в рабочих часах.

Команды ниже запускает IT/MLOps или SQL-разработчик из `/opt/anyq`
под пользователем `deploy`. Координатор до этого записывает уровень
и метку времени восстановления, если дошли до pgBackRest.

Цель плана, не гарантия для клиента: RPO не больше 15 минут,
RTO — `<цель-RTO>`. В письмо клиенту эти цифры не ставят.

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

Базу поднимают только в образе `postgis/postgis:16-3.4`.
Образ Alpine для базы не используют. `deploy/restore.sh` —
будет добавлено. Пока команды выполняют напрямую.

Остановка API, чтобы он не писал в базу:

```bash
cd /opt/anyq
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop api
```

Образ базы для этого запуска:

```bash
cat > /tmp/anyq-postgres-image.yml <<'EOF'
services:
  postgres:
    image: postgis/postgis:16-3.4
EOF
```

Файл `/tmp/anyq-postgres-image.yml` в git не кладут.

Если контейнер просто остановлен и том трогать не нужно:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml \
  -f /tmp/anyq-postgres-image.yml up -d postgres
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

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop postgres
docker run --rm --entrypoint tar \
  -v anyq-postgres:/from:ro \
  -v /var/backups/anyq:/backup \
  postgis/postgis:16-3.4 \
  -C /from -czf /backup/anyq-pgvolume-<штамп>.tar.gz .
```

Эта копия — слепок тома в Казахстане, не замена pgBackRest.
Пока архив не проверен `tar -tzf`, том не удаляют.

### pgBackRest

Пароль шифрования репозитория берут только из офлайн-хранилища
`<офлайн-хранилище>`. В команду, карточку, чат и git его не вставляют.
Метку `<timestamp>` выбирает SQL-разработчик и пишет в карточку.
Для повреждённого шага migrate это момент непосредственно до шага.

PostgreSQL на время restore остановлен. Репозиторий за пределами
Казахстана не используют.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop postgres
pgbackrest info
pgbackrest restore --delta --type=time \
  --target='<timestamp>' --target-action=promote
```

Затем снова контейнер `postgis/postgis:16-3.4` и проверка копии:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml \
  -f /tmp/anyq-postgres-image.yml up -d postgres
pgbackrest check
pgbackrest backup --type=full
```

### Логический дамп

Логический дамп (`pg_dump --no-owner --no-privileges`) не подменяет
pgBackRest. Его грузят только если координатор записал, что
репозиторий pgBackRest для этой метки недоступен, а дамп проверен
`gzip -t`. Дамп не восстанавливает владельцев и права.

Роль приложения — `anyq`. Она не суперпользователь. Роль
администрирования кластера отдельная, приложению её не выдают.
Пароль роли берут из офлайн-хранилища, в SQL его не пишут
(`\password anyq` в сессии `psql`). Сначала роль, затем база:

```sql
CREATE ROLE anyq WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
```

Если роль уже есть, вместо `CREATE ROLE`:

```sql
ALTER ROLE anyq WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
```

Базу создают так и только так:

```sql
CREATE DATABASE anyq OWNER anyq
  TEMPLATE template0
  ENCODING 'UTF8'
  LOCALE_PROVIDER icu
  ICU_LOCALE 'ru-KZ';
```

Дамп загружают в эту пустую базу:

```bash
gunzip -c /var/backups/anyq/anyq-postgres-<штамп>.sql.gz \
  | docker compose --env-file deploy/.env \
    -f deploy/docker-compose.prod.yml exec -T postgres \
    psql --username anyq --dbname anyq -v ON_ERROR_STOP=1
```

После загрузки заново применяют права. Список GRANT/REVOKE
берут из файла рядом с дампом, `<скрипт-прав>`, а не составляют
по памяти. Если этого файла нет, минимум такой:

```sql
GRANT CONNECT ON DATABASE anyq TO anyq;
GRANT USAGE ON SCHEMA public TO anyq;
GRANT SELECT, INSERT, UPDATE, DELETE
  ON ALL TABLES IN SCHEMA public TO anyq;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anyq;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Том загрузок `anyq-data` этими командами не трогают.

## Проверка

Сверяют ревизию с ожидаемой `<ревизия>` из карточки выпуска.
Числа строк — с прошлыми известными счётчиками `<счётчики>`,
не с выгрузкой людей. `max(created_at)` не позже метки `<timestamp>`.
Сами строки, почту и `payload` не выводят.

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
pgbackrest verify
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  pg_amcheck --username anyq --dbname anyq --all
```

После этого поднимают API и смотрят готовность внутри контейнера,
на `127.0.0.1`, порт процесса API:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml \
  -f /tmp/anyq-postgres-image.yml up -d
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T api \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/v1/health/ready', timeout=3).read()"
```

Ожидание: `pg_amcheck` без ошибок, `pgbackrest verify` без ошибок,
ревизия совпала, числа строк сходятся со `<счётчики>`,
`newest` не позже `<timestamp>`, ответ ready без ошибки.
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
2. Если было восстановление, полная копия уже снята командой `pgbackrest backup --type=full`. Её вторая точка — в Казахстане. Логический дамп `deploy/backup.sh` эту копию не заменяет.
3. Для SEV1 и SEV2 назначьте разбор по [`docs/incidents/POSTMORTEM.md`](../incidents/POSTMORTEM.md) в рабочие часы.
4. Образы и тома, которые не стирали, не удаляйте до конца разбора.
