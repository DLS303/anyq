# SuperAPP — скелет фазы 1

Комплексная экосистема земли, стройки и архитектуры РК по ТЗ от 15.09.2026.

Это **первый каркас**, не прототип DLS/Kumbez. Вертикальный срез фазы 1:

- публичный портал Next.js (RU / KK)
- каталог участков + карта OSM
- цифровой паспорт v1
- кабинет продавца и очередь модератора
- API-шлюз FastAPI с живыми модулями marketplace/gis и заглушками CRM, эскроу, гос-API, чата
- локальные данные в `data/db.json` (файл не коммитится; образец — `data/db.example.json`)

## Запуск

Нужны Node 20+ и Python 3.12+. Docker на этой машине пока нет — данные в памяти.

```bash
cd superapp
python -m venv apps/api/.venv
apps/api/.venv/Scripts/python -m pip install -r apps/api/requirements.txt
npm install
npm run dev
```

- Web: http://localhost:3000 → редирект на `/ru`
- API: http://127.0.0.1:8010/docs

### Демо-роли

| Email | Роль |
|-------|------|
| `buyer@demo.superapp` | покупатель |
| `owner@demo.superapp` | продавец |
| `moderator@demo.superapp` | модератор |
| `admin@demo.superapp` | админ |

Вымышленные записи создаются только при `ANYQ_DEMO_MODE=1` (и `NEXT_PUBLIC_ANYQ_DEMO_MODE=1` для экранов). Без флага база пустая. Публичная регистрация закрыта, пока `REGISTRATION_ENABLED` и `NEXT_PUBLIC_REGISTRATION_ENABLED` не равны `1`; вход существующих аккаунтов при этом работает. Пароль демо-аккаунтов задаётся через `ANYQ_DEMO_PASSWORD` и не применяется при `ANYQ_ENV=production`. В production интерфейс OpenAPI (`/docs`) отвечает 404. Бейдж проверки появляется только после записи модератора или администратора.

## Когда появится Docker

```bash
docker compose up -d
```

Поднимутся PostgreSQL + PostGIS и Redis для GIS-контура. Схема: `infra/postgres/init.sql`. Приложение хранит свои данные в SQLite, если `DATABASE_URL` пустой, и в PostgreSQL, если он задан. Рабочий запуск описан в `docs/DEPLOY.md`.

## Что сознательно не сделано

Эскроу, Kaspi Pay, eGov QR, Flutter, KENML, Pin-on-Plan, e-Qurylys, Elasticsearch, Kafka, S3.
