# Неудачный выпуск

Регламент на случай, когда новый выпуск не проходит проверку или уже
отвечает пользователям, но его нужно убрать. Уровень и эскалация —
в [`deploy/INCIDENT.md`](../../deploy/INCIDENT.md).

Алерты приходят в любое время. Шаги человека выполняют в рабочие часы
(Asia/Almaty, UTC+5). Срок уровня считают в рабочих часах.

Пока скрипта отката нет: `deploy/rollback.sh` — будет добавлено.
Ниже — то, что уже делает `deploy/deploy.sh`, и ручной откат образов
из [`docs/DEPLOY.md`](../DEPLOY.md).

## Признаки

- `deploy/deploy.sh` закончился с текстом `deploy failed, rolling back`.
- В журнале есть `no rollback image is available`.
- Скрипт написал `rollback finished. The previous images are running.` и завершился с ненулевым кодом.
- Выпуск прошёл публичную проверку, но пилотный сценарий ведёт себя неправильно. Какую именно ошибку увидели, пишут в карточку общими словами, без трассировки запросов в канал.

Неудачный выпуск, который скрипт уже сам вернул на прежние образы
и который клиент не заметил, начинают как SEV2. Простой для клиента
или подозрение на порчу данных — SEV1, и дальше подключают регламент
базы или утечки, если признаки туда ведут.

## Первые 15 минут

Пятнадцать минут считают от момента старта срока в
[`deploy/INCIDENT.md`](../../deploy/INCIDENT.md), внутри рабочего окна.

1. Координатор (дежурный DLS) ставит уровень и открывает карточку.
2. Эскалация: IT/MLOps и разработчик приложения. SQL-разработчика зовут, если выпуск уже запускал миграции. Собственника зовут, если клиент видит простой.
3. Не запускайте второй `deploy/deploy.sh`, пока карточка не зафиксирует, какой образ сейчас обслуживает трафик.
4. Посмотрите состояние:

```bash
cd /opt/anyq
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml ps
docker image inspect anyq-api:rollback >/dev/null && echo api-rollback-present
docker image inspect anyq-web:rollback >/dev/null && echo web-rollback-present
git rev-parse --short HEAD
```

Хеш коммита в карточку записать можно. Секреты и `deploy/.env` — нет.

## Восстановление

### Скрипт уже вернул прежние образы

Если в выводе есть `rollback finished. The previous images are running.`,
повторно теги `rollback` не перевешивают: они уже стоят как `current`.
Переходите к разделу «Проверка». Следующий выпуск в этот день не
запускают, пока разработчик приложения не запишет причину общими словами.

Если в выводе есть `no rollback image is available`, откатывать нечего.
Не повторяйте `deploy/deploy.sh` в цикле. Оставьте контейнеры как есть,
снимите журналы в закрытый каталог и зовите разработчика приложения:

```bash
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml logs --tail 80 \
  > "<закрытый-каталог-инцидентов>/<номер>/deploy.log"
```

### Выпуск отвечает, но его нужно убрать

Когда появится скрипт:

```bash
# будет добавлено
./deploy/rollback.sh
```

Пока его нет, и образы `anyq-api:rollback` и `anyq-web:rollback` есть:

```bash
cd /opt/anyq
docker tag anyq-api:rollback anyq-api:current
docker tag anyq-web:rollback anyq-web:current
docker compose --env-file deploy/.env \
  -f deploy/docker-compose.prod.yml up -d --no-build
```

Так же поступает сам `deploy/deploy.sh`, если не проходит проверка
здоровья или смоук. Смоук ждёт `"ok":true` на `/healthz`, `/health`
и `/v1/modules`, а также успешный ответ `/ru`.

Откат — это повторный запуск предыдущего образа. Схему этим шагом
не возвращают. `alembic downgrade` в бою запрещён.

Миграции выполняют отдельным шагом migrate. Если этот шаг повредил
данные, базу восстанавливают на момент непосредственно до него.
Метку времени `<timestamp>` пишут в карточку. Дальше команды из
[`docs/runbooks/db-down.md`](db-down.md):

```bash
pgbackrest info
pgbackrest restore --delta --type=time \
  --target='<timestamp>' --target-action=promote
```

Пароль шифрования репозитория берут только из офлайн-хранилища
`<офлайн-хранилище>`. В команду, карточку и git его не вставляют.
Контейнер базы при этом восстановлении — только `postgis/postgis:16-3.4`.
Образ Alpine для базы не используют. После восстановления —
`pgbackrest check` и новая полная копия, как в регламенте базы.
`deploy/restore.sh` — будет добавлено.

Контейнер, который перезапускается из-за `deploy/.env`, смотрят так:

```bash
docker logs anyq-api --tail 50
```

Файл правят на сервере. В репозиторий его не кладут. После правки:

```bash
./deploy/check_env.sh
```

Последняя строка: `Environment file is valid.` Затем снова
`./deploy/deploy.sh` только по решению координатора.

## Проверка

```bash
docker inspect -f '{{.State.Health.Status}}' anyq-api
docker inspect -f '{{.State.Health.Status}}' anyq-web
docker inspect -f '{{.State.Health.Status}}' anyq-caddy
curl -fsS "https://<домен>/healthz"
curl -fsS "https://<домен>/health"
curl -fsS "https://<домен>/v1/modules"
curl -fsS -o /dev/null -w '%{http_code}\n' "https://<домен>/ru"
```

Ожидание: три контейнера `healthy`, в первых трёх ответах есть
`"ok":true`, у страницы код `200`. Для боевого домена флаг `-k`
не используют.

Разработчик приложения проходит один короткий пилотный сценарий
и записывает в карточку «сценарий проходит» или «не проходит»,
без дампа ответа.

## Коммуникации

Если клиент видел простой или ошибку, письмо — по
[`docs/runbooks/comms.md`](comms.md). Хеш коммита и имя образа
в письмо не ставят. Пока клиент ничего не заметил, внешнее письмо
не отправляют.

## После инцидента

1. В карточке зафиксируйте хеш неудачного выпуска и хеш того, что осталось в работе.
2. Образы `:rollback` не удаляйте до следующего успешного `deploy/deploy.sh`: скрипт перезапишет их сам в начале следующего выпуска.
3. Для SEV1 и для клиентского SEV2 откройте разбор по [`docs/incidents/POSTMORTEM.md`](../incidents/POSTMORTEM.md).
4. Повторять тот же `DEPLOY_REF` в этот рабочий день нельзя, пока причина не записана в карточке.
