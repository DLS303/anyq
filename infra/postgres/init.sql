-- Схема фазы 1. Целевой движок — PostGIS (ТЗ §6.2 FR-MKT-02).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE plot_status AS ENUM (
  'draft',
  'pending',
  'needs_revision',
  'published',
  'rejected',
  'reserved',
  'sold',
  'archived'
);

CREATE TYPE land_purpose AS ENUM (
  'izhs',
  'lph',
  'dacha',
  'commercial',
  'industrial',
  'recreation',
  'investment'
);

CREATE TYPE utility_status AS ENUM (
  'connected',
  'nearby',
  'tu_received',
  'absent'
);

CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text UNIQUE NOT NULL,
  full_name     text NOT NULL,
  role          text NOT NULL CHECK (role IN (
                  'guest','buyer','owner','moderator','admin',
                  'specialist','contractor','supplier','supervisor'
                )),
  iin           text,
  bin           text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE plots (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            text UNIQUE NOT NULL,
  owner_id        uuid REFERENCES users(id),
  cadastral_no    text NOT NULL,
  title_ru        text NOT NULL,
  title_kk        text NOT NULL,
  district        text NOT NULL,
  purpose         land_purpose NOT NULL,
  area_sotka      numeric(10,2) NOT NULL,
  price_kzt       bigint NOT NULL,
  divisible       boolean NOT NULL DEFAULT false,
  land_category   text,
  status          plot_status NOT NULL DEFAULT 'draft',
  verified        boolean NOT NULL DEFAULT false,
  trust_score     integer NOT NULL DEFAULT 0 CHECK (trust_score BETWEEN 0 AND 100),
  electricity     utility_status NOT NULL DEFAULT 'absent',
  gas             utility_status NOT NULL DEFAULT 'absent',
  water           utility_status NOT NULL DEFAULT 'absent',
  sewage          utility_status NOT NULL DEFAULT 'absent',
  access_road     utility_status NOT NULL DEFAULT 'absent',
  description_ru  text,
  description_kk  text,
  geom            geometry(Polygon, 4326),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX plots_geom_gix ON plots USING gist (geom);
CREATE INDEX plots_status_idx ON plots (status);
CREATE INDEX plots_cadastral_idx ON plots (cadastral_no);

CREATE TABLE moderation_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plot_id     uuid NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  actor_id    uuid REFERENCES users(id),
  action      text NOT NULL,
  comment     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
