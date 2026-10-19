# Сервер потерян

Регламент на случай, когда сам сервер пилотного контура недоступен
и вернуть его диск нельзя. Данные поднимают на новом сервере
в Казахстане из второй копии, которая тоже лежит в Казахстане.
Уровень и эскалация — в [`deploy/INCIDENT.md`](../../deploy/INCIDENT.md).

Алерты приходят в любое время. Шаги человека выполняют в рабочие часы
(Asia/Almaty, UTC+5). Срок уровня считают в рабочих часах.

`deploy/restore.sh` — будет добавлено. `pgbackrest` — будет добавлено.
Пока вторая копия — это архивы `deploy/backup.sh`:
`anyq-postgres-<штамп>.sql.gz` и `anyq-data-<штамп>.tar.gz`.

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

Источник — вторая копия в Казахстане. Каталог `/var/backups/anyq`
на потерянном сервере недоступен, его не ждут.

Плановая выгрузка архива во вторую точку скриптом — будет добавлено.
Пока IT/MLOps в рабочие часы копирует архивы `deploy/backup.sh`
на диск или сервер в Казахстане. На новом сервере берут уже
лежащую там копию.

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

### Вторая копия

На новом сервере:

```bash
mkdir -p /var/backups/anyq
rsync -a \
  "<вторая-копия-в-казахстане>/" \
  /var/backups/anyq/
ls -lh /var/backups/anyq
gzip -t /var/backups/anyq/anyq-postgres-<штамп>.sql.gz
tar -tzf /var/backups/anyq/anyq-data-<штамп>.tar.gz >/dev/null
```

Штамп выбирает координатор вместе с SQL-разработчиком и пишет его
в карточку. Если `rsync` идёт с другой машины в Казахстане, в источнике
стоит метка `<пользователь>@<вторая-копия-в-казахстане>:` и каталог
архивов. Имя узла в репозиторий не подставляют.

Когда появится `pgbackrest`, вместо архива `pg_dump` смотрят
репозиторий второй точки (команды сейчас не запускают):

```bash
# будет добавлено
# pgbackrest --stanza=anyq info
# pgbackrest --stanza=anyq restore
```

Когда появится скрипт, ручную загрузку заменит:

```bash
# будет добавлено
./deploy/restore.sh
```

### Загрузка на пустой контур

Сначала поднимают только PostgreSQL, без API. Образ создаёт пустую
базу `anyq`. Пока API не стартовал, миграции пустую базу не заполняют,
и дамп `pg_dump` ложится в неё без `DROP DATABASE`.

```bash
cd /opt/anyq
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d postgres
docker inspect -f '{{.State.Health.Status}}' anyq-postgres
gunzip -c /var/backups/anyq/anyq-postgres-<штамп>.sql.gz \
  | docker compose --env-file deploy/.env \
    -f deploy/docker-compose.prod.yml exec -T postgres \
    psql --username anyq --dbname anyq -v ON_ERROR_STOP=1
```

Если API уже успели запустить и в пустой базе появились объекты
приложения, остановите API и загружайте дамп только в заново
созданную пустую базу. Это стирает то, что успели записать уже
на новом сервере, не архив:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop api
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname postgres -v ON_ERROR_STOP=1 \
  -c 'DROP DATABASE IF EXISTS anyq WITH (FORCE);'
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname postgres -v ON_ERROR_STOP=1 \
  -c 'CREATE DATABASE anyq OWNER anyq;'
```

После `CREATE DATABASE` повторите `gunzip` и `psql` из блока выше.

Файлы тома `anyq-data` (команда очищает каталог внутри тома
перед распаковкой):

```bash
docker run --rm \
  -v anyq-data:/data \
  -v /var/backups/anyq:/backup:ro \
  alpine:3.20 \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +
tar -C /data -xzf /backup/anyq-data-<штамп>.tar.gz'
```

Затем весь стек, всё ещё без публичного смоука `deploy.sh`:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d
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
Трафик на неё не переключают.

## Проверка

На новом сервере, до смены DNS:

```bash
docker inspect -f '{{.State.Health.Status}}' anyq-postgres
docker inspect -f '{{.State.Health.Status}}' anyq-api
docker inspect -f '{{.State.Health.Status}}' anyq-web
docker inspect -f '{{.State.Health.Status}}' anyq-caddy
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname anyq -c 'SELECT count(*) FROM records;'
```

Ожидание: контейнеры `healthy` (Caddy до выпуска сертификата может
ещё подниматься — тогда повторите осмотр после смены DNS), запрос
возвращает одно число. Строки таблиц не печатают.

После смены A-записи, с любой машины, где уже виден новый адрес:

```bash
dig +short <домен> A
curl -fsS "https://<домен>/healthz"
curl -fsS "https://<домен>/health"
curl -fsS -o /dev/null -w '%{http_code}\n' "https://<домен>/ru"
```

Ожидание: в ответе DNS адрес нового сервера, в двух первых ответах
есть `"ok":true`, у страницы код `200`, сертификат выдан на это имя.
Флаг `-k` для боевого домена не используют.

Поставьте расписание копий, как в [`docs/DEPLOY.md`](../DEPLOY.md),
и снимите первую копию уже на новом сервере:

```bash
./deploy/backup.sh
```

Эту копию также уносят на вторую точку в Казахстане.

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
