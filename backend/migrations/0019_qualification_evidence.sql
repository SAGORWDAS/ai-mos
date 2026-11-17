ALTER TABLE leads ADD COLUMN source_ref varchar(2000) NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN source_observed_at double precision NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN score_model varchar(64) NOT NULL DEFAULT 'unscored';
ALTER TABLE leads ADD COLUMN score_features json NOT NULL DEFAULT '{}';
ALTER TABLE leads ADD COLUMN qualification_threshold integer NOT NULL DEFAULT 65;
