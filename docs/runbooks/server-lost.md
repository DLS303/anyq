# Сервер потерян

Регламент на случай, когда сам сервер пилотного контура недоступен
и вернуть его диск нельзя. Данные поднимают на новом сервере
в Казахстане из второй копии, которая тоже лежит в Казахстане.
Уровень и эскалация — в [`deploy/INCIDENT.md`](../../deploy/INCIDENT.md).

Алерты приходят в любое время. Шаги человека выполняют в рабочие часы
(Asia/Almaty, UTC+5). Срок уровня считают в рабочих часах.

Цель плана, не гарантия для клиента: RPO не больше 15 минут,
RTO — `<цель-RTO>`. В письмо клиенту эти цифры не ставят.

Базу поднимают только в образе `postgis/postgis:16-3.4`, из
репозитория pgBackRest `--repo=2` (вторая точка в Казахстане).
`deploy/restore.sh` — будет добавлено. Образ Alpine для базы
не используют.

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
4. Находят вторую копию `<вторая-копия-в-казахстане>`. Копию за пределами Казахстана не используют. Если второй точки в Казахстане нет, восстановление останавливают до решения собственника.
5. A-запись домена пока не меняют.

## Восстановление

Источник базы — репозиторий pgBackRest `--repo=2` в Казахстане.
Каталог на потерянном сервере недоступен, его не ждут.
Репозиторий за пределами Казахстана не используют.
Пароль шифрования берут только из офлайн-хранилища
`<офлайн-хранилище>`. В команду, карточку и git его не вставляют.

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

### Репозиторий 2

На новом сервере PostgreSQL ещё не запущен. API не запускают,
пока restore не закончен. Шаг migrate — отдельно и только если
ревизия в `alembic_version` старше ожидаемой. `alembic downgrade`
в бою запрещён.

Образ базы:

```bash
cd /opt/anyq
cat > /tmp/anyq-postgres-image.yml <<'EOF'
services:
  postgres:
    image: postgis/postgis:16-3.4
EOF
```

Файл в git не кладут. Метку `<timestamp>` пишут в карточку.
Пароль шифрования в команду не подставляют: pgBackRest читает его
из офлайн-хранилища.

```bash
pgbackrest info
pgbackrest restore --delta --type=time \
  --target='<timestamp>' --target-action=promote --repo=2
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml \
  -f /tmp/anyq-postgres-image.yml up -d postgres
pgbackrest check
pgbackrest backup --type=full
```

`deploy/restore.sh` — будет добавлено.

Если вместо репозитория 2 остался только логический дамп
(`pg_dump --no-owner --no-privileges`), его грузят в пустую базу
на этом же образе, как в [`docs/runbooks/db-down.md`](db-down.md):
роль `anyq` без прав суперпользователя, затем

```sql
CREATE DATABASE anyq OWNER anyq
  TEMPLATE template0
  ENCODING 'UTF8'
  LOCALE_PROVIDER icu
  ICU_LOCALE 'ru-KZ';
```

и заново GRANT/REVOKE из `<скрипт-прав>`. Дамп владельцев и прав
не содержит.

Файлы тома `anyq-data` — не база. Перед любым tar PostgreSQL
останавливают. Каталог внутри тома очищают по записи координатора.
Образ Alpine не используют.

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop postgres api
docker run --rm --entrypoint sh \
  -v anyq-data:/data \
  -v /var/backups/anyq:/backup:ro \
  postgis/postgis:16-3.4 \
  -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +
tar -C /data -xzf /backup/anyq-data-<штамп>.tar.gz'
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
`<timestamp>`. Строки людей не печатают.

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

Готовность API — внутри контейнера, на `127.0.0.1`:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml \
  -f /tmp/anyq-postgres-image.yml up -d
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T api \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/v1/health/ready', timeout=3).read()"
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
Полная копия `pgbackrest backup --type=full` уже снята выше
и остаётся в Казахстане, включая репозиторий 2.

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
