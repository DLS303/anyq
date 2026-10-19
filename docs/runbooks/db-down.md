# База недоступна

Регламент на случай, когда PostgreSQL пилотного контура не принимает
соединения или контейнер базы не становится здоровым. Уровень, роли
и эскалация — в [`deploy/INCIDENT.md`](../../deploy/INCIDENT.md).

Алерты приходят в любое время. Шаги человека выполняют в рабочие часы
(Asia/Almaty, UTC+5). Срок уровня считают в рабочих часах.

Команды ниже запускает IT/MLOps или SQL-разработчик из `/opt/anyq`
под пользователем `deploy`. Координатор до этого записывает уровень
и штамп копии, если дошли до загрузки архива.

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

5. Если диск заполнен, освобождают место, которое не является томом базы и не является `/var/backups/anyq`. Каталог копий не чистят.

## Восстановление

Сначала возвращают уже существующий том. Загрузка архива — только
если контейнер с этим томом не становится здоровым или SQL-разработчик
записал в карточку, что кластер не читается.

`deploy/restore.sh` — будет добавлено. `pgbackrest` — будет добавлено.
Пока действует путь ниже, из шапки `deploy/backup.sh`.

Поднять контейнер, если он остановлен, но том на месте:

```bash
cd /opt/anyq
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d postgres
docker inspect -f '{{.State.Health.Status}}' anyq-postgres
```

Проверка готовности:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  pg_isready -U anyq -d anyq
```

Если база здорова, запустите остальные сервисы и перейдите к разделу
«Проверка»:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d
```

Если кластер не отвечает на `pg_isready`, сохраните журнал в закрытый
каталог в Казахстане и не вставляйте его в канал:

```bash
docker logs anyq-postgres --tail 200 \
  > "<закрытый-каталог-инцидентов>/<номер>/postgres.log"
```

Дальше только с записью координатора в карточке. Выберите штамп
глазами, не самым новым файлом автоматически:

```bash
ls -lh /var/backups/anyq
gzip -t /var/backups/anyq/anyq-postgres-<штамп>.sql.gz
```

Если локальный архив не проходит `gzip -t`, берут тот же штамп
из `<вторая-копия-в-казахстане>`. Копию за пределами Казахстана
не используют. Вторую точку копируют на этот сервер в `/var/backups/anyq`
и снова выполняют `gzip -t`.

Остановите API, чтобы он не писал в базу во время загрузки:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop api
```

Архив `pg_dump` не содержит `DROP`. Его загружают в пустую базу `anyq`.
Это уничтожает текущее содержимое базы. Делайте это только после
`gzip -t` и записи штампа в карточку.

Если `pg_isready` проходит, а данные всё равно нужно заменить,
очистите базу и загрузите архив:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname postgres -v ON_ERROR_STOP=1 \
  -c 'DROP DATABASE IF EXISTS anyq WITH (FORCE);'
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname postgres -v ON_ERROR_STOP=1 \
  -c 'CREATE DATABASE anyq OWNER anyq;'
gunzip -c /var/backups/anyq/anyq-postgres-<штамп>.sql.gz \
  | docker compose --env-file deploy/.env \
    -f deploy/docker-compose.prod.yml exec -T postgres \
    psql --username anyq --dbname anyq -v ON_ERROR_STOP=1
```

Если контейнер так и не становится здоровым, `psql` недоступен
и команды выше не выполняют. Сначала, если на диске есть место,
снимите том в каталог копий в Казахстане. Пока такого файла нет,
том не удаляют:

```bash
docker run --rm \
  -v anyq-postgres:/from:ro \
  -v /var/backups/anyq:/backup \
  alpine:3.20 \
  tar -C /from -czf /backup/anyq-pgvolume-<штамп>.tar.gz .
tar -tzf /var/backups/anyq/anyq-pgvolume-<штамп>.tar.gz >/dev/null
```

После успешной проверки и этого архива, и `gzip -t` дампа
координатор разрешает заменить том пустым. Удаляют только том
базы, не `anyq-data`:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml stop postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml rm -f postgres
docker volume rm anyq-postgres
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d postgres
```

Дождитесь `healthy`, затем загрузите дамп в пустую базу
без `DROP DATABASE`:

```bash
gunzip -c /var/backups/anyq/anyq-postgres-<штамп>.sql.gz \
  | docker compose --env-file deploy/.env \
    -f deploy/docker-compose.prod.yml exec -T postgres \
    psql --username anyq --dbname anyq -v ON_ERROR_STOP=1
```

Том загрузок `anyq-data` этой командой не трогают. Его распаковывают
только если пропали и файлы, отдельной командой из
[`docs/runbooks/server-lost.md`](server-lost.md), и только тем же штампом.

Когда появится `pgbackrest`, справка и восстановление будут такими
(сейчас эти команды не запускают):

```bash
# будет добавлено
# pgbackrest --stanza=anyq info
# pgbackrest --stanza=anyq restore
```

Когда появится скрипт, вместо ручной загрузки SQL:

```bash
# будет добавлено
./deploy/restore.sh
```

Затем снова поднимите стек:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d
```

## Проверка

```bash
docker inspect -f '{{.State.Health.Status}}' anyq-postgres
docker inspect -f '{{.State.Health.Status}}' anyq-api
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml exec -T postgres \
  psql --username anyq --dbname anyq -c 'SELECT count(*) FROM records;'
curl -fsS "https://<домен>/health"
curl -fsS "https://<домен>/healthz"
curl -fsS -o /dev/null -w '%{http_code}\n' "https://<домен>/ru"
```

Ожидание: оба контейнера `healthy`, запрос возвращает одно число,
в `/health` и `/healthz` есть `"ok":true`, у страницы код `200`.
Число строк сравните с ожиданием SQL-разработчика. Сами строки,
почту и содержимое `payload` не выводите.

Для боевого домена флаг `-k` не используют.

## Коммуникации

Если пилотный клиент уже видит простой, координатор готовит письмо
по [`docs/runbooks/comms.md`](comms.md). Текст одобряет собственник.
В письмо не ставят штамп архива, имя узла и причину на уровне команд.

Пока клиент работу не терял, внешнее письмо не отправляют.
В канале достаточно номера карточки и уровня.

## После инцидента

1. Допишите хронологию в закрытой карточке.
2. Если загружали архив, снимите новую копию и оставьте её в Казахстане:

   ```bash
   ./deploy/backup.sh
   ```

3. Для SEV1 и SEV2 назначьте разбор по [`docs/incidents/POSTMORTEM.md`](../incidents/POSTMORTEM.md) в рабочие часы.
4. Образы и тома, которые не стирали, не удаляйте до конца разбора.
