ALTER TABLE model_usage ADD COLUMN reserved_micros integer NOT NULL DEFAULT 0;
ALTER TABLE model_usage ADD COLUMN reservation_period varchar(10) NOT NULL DEFAULT '';
ALTER TABLE model_usage ADD COLUMN provider_ref varchar(200) NOT NULL DEFAULT '';
ALTER TABLE model_usage ADD COLUMN settled boolean NOT NULL DEFAULT true;
ALTER TABLE model_usage ADD COLUMN reconciliation_evidence varchar(1000) NOT NULL DEFAULT '';
