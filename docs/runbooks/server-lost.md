# Сервер потерян

Регламент на случай, когда сам сервер пилотного контура недоступен
и вернуть его диск нельзя. Данные поднимают на новом сервере
в Казахстане из второй копии, которая тоже лежит в Казахстане.
Уровень и эскалация — в [`deploy/INCIDENT.md`](../../deploy/INCIDENT.md).

Алерты приходят в любое время. Шаги человека выполняют в рабочие часы
(Asia/Almaty, UTC+5). Срок уровня считают в рабочих часах.

К запуску pgBackRest не готов. На запуске базу читают из
зашифрованного дампа в Казахстане: `rclone`, затем `age -d`,
затем `pg_restore`. Раздел «Зашифрованный дамп» ниже.
Команды `pgbackrest` в этом файле — на потом, когда инструмент
уже стоит в контуре. До задачи DevOps по базе администратор
кластера — `anyq`.

Цель плана, не гарантия для клиента: RTO — ≤ 4 ч (пилот).
Цель RPO не больше 15 минут (`archive_timeout=60`) относится
к pgBackRest и на запуске не действует. Точка восстановления
на запуске — последний зашифрованный дамп. В письмо клиенту
эти цифры не ставят.

`deploy/restore.sh` — будет добавлено.
Существующий том всегда запускают тем образом, которым он создан.
Образ `postgis/postgis:16-3.4` — после миграции на этот образ
(задача DevOps). Перенос локального стенда с Alpine на PostGIS —
только дамп в новый пустой том.

## Признаки

- По SSH на прежний сервер зайти нельзя, и панель поставщика показывает, что машины или её диска больше нет.
- Хост не отвечает, а отдельно проверить «только контейнер» негде, потому что нет доступа к Docker.

Если SSH работает, это не этот регламент. Идите в
[`docs/runbooks/db-down.md`](db-down.md) или
[`docs/runbooks/bad-deploy.md`](bad-deploy.md).

Потеря сервера — SEV1.

## Первые 15 минут

Пятнадцать минут считают от момента старта срока в
[`deploy/INCIDENT.md`](../../deploy/INCIDENT.md), внутри рабочего окна.

1. Координатор (дежурный DLS) ставит SEV1 и открывает карточку.
2. Эскалация: IT/MLOps, собственник (решение взять новый сервер), SQL-разработчик, разработчик приложения. Юриста зовут, если на потерянном диске могли остаться персональные данные и собственнику нужно решить, считать ли это отдельным событием по [`docs/runbooks/data-leak.md`](data-leak.md).
3. Новый сервер заказывают только в Казахстане. Адрес записывают в закрытую карточку как `<ipv4-нового-сервера>`, не в git.
4. На запуске находят зашифрованный дамп `anyq-postgres-<штамп>.dump.age` в хранилище в Казахстане. Копию за пределами Казахстана не используют. Если файла в Казахстане нет, восстановление останавливают до решения собственника. Репозиторий pgBackRest `--repo=2` на запуске не ждут.
5. A-запись домена пока не меняют.

## Восстановление

На запуске источник базы — зашифрованный дамп в Казахстане.
Каталог на потерянном сервере недоступен, его не ждут.
Хранилище за пределами Казахстана не используют.
Ключ `age` берут только из офлайн-хранилища `<офлайн-хранилище>`.
В команду, карточку и git его не вставляют. pgBackRest к запуску
не готов: раздел «Репозиторий 2» на запуске не выполняют.

### Новый сервер

Берут VPS в Казахстане: Ubuntu 22.04 или 24.04, порты 22, 80 и 443.
Дальше шаги [`docs/DEPLOY.md`](../DEPLOY.md): подготовка, ключ SSH,
клон в `/opt/anyq`. Ключ SSH выпускают заново. Публичный ключ
с потерянного сервера в `authorized_keys` не переносят.

Подготовка, как в [`docs/DEPLOY.md`](../DEPLOY.md). Скрипт один раз
от root, ключ SSH — новый:

```bash
git clone <URL-репозитория> /tmp/anyq-src
sudo bash /tmp/anyq-src/deploy/bootstrap_server.sh
```

Затем под пользователем `deploy`:

```bash
git clone <URL-репозитория> /opt/anyq
cd /opt/anyq
git checkout <ветка>
```

Файл `deploy/.env` в git не хранится. Его приносят из закрытой копии
в Казахстане, ставят права `600` и проверяют:

```bash
./deploy/check_env.sh
```

Ожидаемая последняя строка: `Environment file is valid.`
Если закрытой копии файла нет, секреты создают заново на новом
сервере (`openssl rand -base64 48` для `JWT_SECRET`,
`openssl rand -base64 32` для `POSTGRES_PASSWORD`) и вписывают
их только в `deploy/.env`. В карточку значения не попадают.
Данные при этом всё равно берутся из второй копии базы, а не
из нового пустого тома.

Секрет `DEPLOY_HOST` в настройках репозитория меняют на адрес
нового сервера после проверки, не раньше. Значение в репозиторий
не коммитят.

До смены DNS не запускайте `deploy/deploy.sh`. Его публичная
проверка ждёт имя домена, а при неудаче скрипт пытается вернуть
прежние образы. На новой машине прежнего выпуска нет.

### Зашифрованный дамп

К запуску pgBackRest не готов. Этот раздел — восстановление базы
на запуске, после того как новый сервер и пустой PostgreSQL
описаны выше. Команды совпадают с разделом «Зашифрованный дамп»
в [`docs/runbooks/db-down.md`](db-down.md).

Файл — пользовательский формат `pg_dump -Fc`, затем зашифрован `age`.
Имя — `anyq-postgres-<штамп>.dump.age`. Ключ — файл `<ключ-age>`,
права `600`, только из `<офлайн-хранилище>`. Конфиг rclone
на сервере называется `<rclone-remote>` и указывает только
в хранилище в Казахстане. В git его нет.

`rclone` и `age` запускают на хосте, из `/opt/anyq`. Если команды
нет, IT/MLOps ставит её на этот сервер до загрузки. Дальше три шага
по порядку: получить файл, расшифровать, загрузить. Следующий шаг
начинают только если предыдущий закончился без ошибки.

Сначала поднимают пустой PostgreSQL и убеждаются, что он принимает
соединения. Живую или пустую базу `anyq` не перезаписывают.
Флаг `--clean` не ставят. Дамп грузят в новую пустую базу
`anyq_restore`. API не запускают до смены имён. На запуске дамп
грузит роль `anyq`. Координатор записывает, что после проверки
имена баз меняют. Пока `pg_restore --list` не прошёл, загрузку
не начинают. Если `alembic_version` или числа строк не сошлись,
имена не меняют.

Получить файл:

```bash
cd /opt/anyq
rclone copy \
  "<rclone-remote>:<префикс>/anyq-postgres-<штамп>.dump.age" \
  /var/backups/anyq/
test -s /var/backups/anyq/anyq-postgres-<штамп>.dump.age
```

Расшифровать:

```bash
umask 077
age -d -i "<ключ-age>" \
  -o /var/backups/anyq/anyq-postgres-<штамп>.dump \
  /var/backups/anyq/anyq-postgres-<штамп>.dump.age
test -s /var/backups/anyq/anyq-postgres-<штамп>.dump
```

Проверка архива до загрузки. Список объектов пишут в закрытый
каталог, не в канал. Ожидание: команда завершается с кодом 0,
файл списка непустой.

```bash
mkdir -p "<закрытый-каталог-инцидентов>/<номер>"
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  pg_isready -U anyq -d anyq
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml run --rm --no-deps -T \
  -v /var/backups/anyq:/backup:ro \
  --user root --entrypoint pg_restore \
  postgres \
  --list /backup/anyq-postgres-<штамп>.dump \
  > "<закрытый-каталог-инцидентов>/<номер>/dump-toc.txt"
test -s "<закрытый-каталог-инцидентов>/<номер>/dump-toc.txt"
```

Пустую базу создают из сессии в базе `postgres`, не из `anyq`.
На запуске сессию открывает роль `anyq`. После задачи DevOps
та же команда с `--username postgres`. Если имя `anyq_restore`
осталось от незавершённой попытки, перед созданием удаляют только
его. Базу `anyq` этой командой не удаляют.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname postgres -v ON_ERROR_STOP=1 <<'SQL'
DROP DATABASE IF EXISTS anyq_restore;
CREATE DATABASE anyq_restore OWNER anyq
  TEMPLATE template0
  ENCODING 'UTF8'
  LOCALE_PROVIDER icu
  ICU_LOCALE 'ru-KZ';
SQL
```

Загрузить в `anyq_restore`. Флагов `--clean` и `--if-exists` нет.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml cp \
  /var/backups/anyq/anyq-postgres-<штамп>.dump \
  postgres:/tmp/anyq-restore.dump
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user root postgres \
  sh -c 'chown postgres:postgres /tmp/anyq-restore.dump && chmod 600 /tmp/anyq-restore.dump'
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user postgres postgres \
  pg_restore --username anyq --dbname anyq_restore \
  --no-owner --no-privileges --exit-on-error --single-transaction \
  /tmp/anyq-restore.dump
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user root postgres \
  rm -f /tmp/anyq-restore.dump
```

Дамп не восстанавливает владельцев и права. После загрузки права
выдают в базе `anyq_restore` тем же блоком, что в
[`docs/runbooks/db-down.md`](db-down.md), раздел «Логический дамп»,
с `\connect anyq_restore` вместо `\connect anyq`. GRANT,
ALTER DEFAULT PRIVILEGES и отдельный REVOKE для `consent_events`.
REVOKE для `audit_log` — отдельная команда и только после миграции
журнала аудита.

Проверка загрузки идёт в `anyq_restore`, до смены имён.
Строки людей не печатают. Ожидание: `version_num` равен `<ревизия>`
из карточки, числа строк сходятся со `<счётчики>`.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname anyq_restore -c \
  'SELECT version_num FROM alembic_version;'
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname anyq_restore -c \
  "SELECT collection, count(*) AS rows
   FROM records GROUP BY collection ORDER BY collection;"
```

После этих двух результатов расшифрованный файл на хосте удаляют.
Файл `.dump.age` и копию в хранилище не трогают.

```bash
rm -f /var/backups/anyq/anyq-postgres-<штамп>.dump
```

Смена имён — только если оба запроса сошлись. Сессия открыта
в базе `postgres`: базу, к которой подключены, переименовать нельзя.
Сначала останавливают API, чтобы он не держал соединение с `anyq`.
Имени `anyq_old` ещё не должно быть. Этот запуск API не вызывает
сервис `migrate`.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop api
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname postgres -v ON_ERROR_STOP=1 \
  -c 'ALTER DATABASE anyq RENAME TO anyq_old;'
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname postgres -v ON_ERROR_STOP=1 \
  -c 'ALTER DATABASE anyq_restore RENAME TO anyq;'
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d --no-deps api
```

После задачи DevOps те же команды `psql` запускают с
`--username postgres`.

`anyq_old` удаляют отдельной командой и только после проверок
из раздела «Проверка». До них эту базу не удаляют.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname postgres -v ON_ERROR_STOP=1 \
  -c 'DROP DATABASE anyq_old;'
```

Сжатый SQL `anyq-postgres-<штамп>.sql.gz` — другой файл. Его грузят
через `psql`, как логический дамп в [`docs/runbooks/db-down.md`](db-down.md),
а не через `pg_restore`. Локальный снимок `pre-migrate-*.dump`
тоже не зашифрован `age`.

### Репозиторий 2

Эти команды не выполняют на запуске: pgBackRest к запуску не готов.
Их оставляют на контур, где инструмент уже установлен.

На новом сервере тома ещё нет. Его создаёт образ из
`deploy/docker-compose.prod.yml`. Дальше этот том запускают только
тем же образом. API не запускают, пока restore не закончен.
Шаг migrate — отдельно и только если ревизия в `alembic_version`
старше ожидаемой. `alembic downgrade` в бою запрещён.

`pgbackrest` на хосте нет. `info` и `restore` запускают через
`run --rm`, пока `postgres` остановлен. `verify` тоже запускают
через `run --rm`: команда читает только репозиторий и подходит
и при работающей базе. `check`, `backup` и `stanza-create`
выполняют через `exec` в уже запущенном контейнере: одноразовый
контейнер сокет базы не видит. У `check` и у `stanza-create` нет
опции `--repo`. Пароль шифрования в команду не подставляют. Файл
`deploy/.env.pgbackrest` (права `600`, в git его нет) содержит
`PGBACKREST_REPO2_CIPHER_PASS` из `<офлайн-хранилище>`. Задача
DevOps по базе прописывает сервису `postgres` в compose
`env_file: .env.pgbackrest`. Тогда пароль репозитория 2 видят
`run`, `exec` и архиватор. У `docker compose run` флага `--env-file`
нет. Метку пишут в карточку как `<YYYY-MM-DD HH:MM:SS+05>`
(пример `2026-10-24 10:15:00+05`). Кластер в UTC, смещение в
`--target` обязательно. Читают репозиторий `--repo=2`.

Сначала тот же образ один раз создаёт каталог данных, затем его
останавливают и восстанавливают поверх. В журнале до restore
возможны ошибки archive-push: первый репозиторий ещё пуст. Эти
строки ожидаемы.

```bash
cd /opt/anyq
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml run --rm --no-deps -T \
  --user postgres postgres \
  pgbackrest --stanza=anyq --repo=2 info
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml run --rm --no-deps -T \
  --user postgres postgres \
  pgbackrest --stanza=anyq restore --delta --type=time \
  --target='<YYYY-MM-DD HH:MM:SS+05>' --target-action=promote \
  --repo=2
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user postgres postgres \
  pgbackrest --stanza=anyq stanza-create
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user postgres postgres \
  pgbackrest --stanza=anyq check
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user postgres postgres \
  pgbackrest --stanza=anyq backup --type=full
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T --user postgres postgres \
  pgbackrest --stanza=anyq --repo=2 backup --type=full
```

`stanza-create` создаёт stanza в каждом настроенном репозитории и
пропускает ту, что уже есть. После restore вторая stanza уже
существует, первая ещё пустая: команда заполняет её. Без stanza
в первом репозитории `archive-push` не пишет WAL, и каталог
`pg_wal` растёт. `check` идёт без `--repo`: такой опции у команды
нет. `backup` без `--repo` пишет только в первый репозиторий.
Копия во второй репозиторий в Казахстане — отдельная команда
с `--repo=2`.

`deploy/restore.sh` — будет добавлено.

Если вместо зашифрованного дампа и репозитория 2 остался только логический дамп
(`pg_dump --no-owner --no-privileges`), его грузят в пустую базу
тем же образом, как в [`docs/runbooks/db-down.md`](db-down.md).
Роль `postgres` (`POSTGRES_USER`) создаёт роли и базу. Роль `anyq`
грузит дамп. Права заново выдают в базе `anyq`: в сессии `psql`
под ролью `postgres` перед GRANT, ALTER DEFAULT PRIVILEGES и REVOKE
выполняют `\connect anyq`. Дальше отдельные команды
`REVOKE UPDATE, DELETE, TRUNCATE ON consent_events FROM anyq_app`
и, после миграции журнала аудита,
`REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM anyq_app`.
`ALTER ROLE anyq ... NOSUPERUSER` не выполняют. Базу, если её ещё нет,
создают так:

```sql
-- выполняет роль postgres
CREATE DATABASE anyq OWNER anyq
  TEMPLATE template0
  ENCODING 'UTF8'
  LOCALE_PROVIDER icu
  ICU_LOCALE 'ru-KZ';
```

Дамп владельцев и прав не содержит. Перед блоком прав в той же
сессии:

```sql
-- выполняет роль postgres, дальше команды в базе anyq
\connect anyq
```

Файлы тома `anyq-data` — не база. Перед любым tar останавливают
PostgreSQL и API. Каталог внутри тома очищают по записи координатора.
Считают архив образом сервиса `api`, у которого этот том уже смонтирован.
Образ базы для этого не подменяют.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop postgres api
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml run --rm --no-deps -T \
  --entrypoint sh \
  -v /var/backups/anyq:/backup:ro \
  api \
  -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -C /data -xzf /backup/anyq-data-<штамп>.tar.gz'
```

Сайт пользователям не объявляют, пока не пройдена проверка
и собственник не согласился сменить A-запись на
`<ipv4-нового-сервера>`.

```text
<домен>    A    <ipv4-нового-сервера>
```

Сертификат Caddy выпускает после того, как имя указывает на новый
сервер. Старый адрес в работе не оставляют.

Если прежняя машина позже снова появится в панели, в строй её
не возвращают, пока собственник не запишет отдельное решение.
Трафик на неё не переключают. До любого запуска на ней меняют
stanza или отключают `archive_command`, чтобы она не складывала
WAL в тот же репозиторий. Имя новой stanza — `<stanza-карантин>`,
в git его не пишут.

## Проверка

Те же сверки, что в [`docs/runbooks/db-down.md`](db-down.md).
Ревизия `alembic_version` равна `<ревизия>`. Числа строк по
коллекциям сходятся со `<счётчики>`. `max(created_at)` не позже
`<YYYY-MM-DD HH:MM:SS+05>`. Строки людей не печатают.
Запросы счёта выполняет роль `anyq`. `pg_amcheck` выполняет роль
`postgres`, без флага `--all`.

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
  -f deploy/docker-compose.prod.yml exec -T --user postgres postgres \
  pg_amcheck --username postgres -d anyq \
  --install-missing --heapallindexed
```

На запуске `pgbackrest verify` не выполняют: инструмента ещё нет.
Проверка запуска — `version_num` и числа строк из раздела
«Зашифрованный дамп». Когда pgBackRest уже стоит в контуре:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml run --rm --no-deps -T \
  --user postgres postgres \
  pgbackrest --stanza=anyq verify
```

Готовность API — внутри контейнера, на `127.0.0.1`:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T api \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/ready', timeout=3).read()"
```

Caddy до выпуска сертификата может ещё подниматься. Повторите
осмотр после смены DNS. Снаружи:

```bash
dig +short <домен> A
curl -fsS "https://<домен>/healthz"
curl -fsS "https://<домен>/health"
curl -fsS -o /dev/null -w '%{http_code}\n' "https://<домен>/ru"
```

Ожидание: в ответе DNS адрес нового сервера, в `/health` и
`/healthz` есть `"ok":true`, у страницы код `200`, сертификат
выдан на это имя. Флаг `-k` для боевого домена не используют.
Если грузили зашифрованный дамп, базу `anyq_old` удаляют только
после этих проверок, командой из раздела «Зашифрованный дамп».
На запуске `pgbackrest backup` не запускают. Когда инструмент
уже стоит в контуре, выше снимают две полные копии:
`pgbackrest --stanza=anyq backup --type=full` в первый репозиторий
и `pgbackrest --stanza=anyq --repo=2 backup --type=full`
во второй репозиторий в Казахстане.

## Коммуникации

Пилотному клиенту пишут по [`docs/runbooks/comms.md`](comms.md):
сначала подтверждение, после проверки — что доступ восстановлен.
Новый адрес сервера, штамп и название площадки в письмо не ставят.
Время в письме — Asia/Almaty (UTC+5). Текст одобряет собственник.

## После инцидента

1. В закрытой карточке остаётся штамп, из которого восстановили контур, и факт, что новый сервер находится в Казахстане. Адрес хранят там же, не в git.
2. Секрет `DEPLOY_HOST` указывает на новый сервер. Старый ключ SSH нигде не оставлен в `authorized_keys`.
3. Разбор — по [`docs/incidents/POSTMORTEM.md`](../incidents/POSTMORTEM.md).
4. Если вместе с диском под вопрос попали персональные данные, решение собственника об уведомлении ведут по [`docs/runbooks/data-leak.md`](data-leak.md), а не только этим файлом.
