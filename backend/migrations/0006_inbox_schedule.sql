ALTER TABLE integrations ADD COLUMN sync_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE integrations ADD COLUMN sync_interval_minutes integer NOT NULL DEFAULT 10;
ALTER TABLE integrations ADD COLUMN sync_next_at double precision NOT NULL DEFAULT 0;
ALTER TABLE integrations ADD COLUMN sync_cursor varchar(2000) NOT NULL DEFAULT '';
ALTER TABLE integrations ADD COLUMN sync_last_at double precision NOT NULL DEFAULT 0;
ALTER TABLE integrations ADD COLUMN sync_error varchar(120) NOT NULL DEFAULT '';
