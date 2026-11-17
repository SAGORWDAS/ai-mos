ALTER TABLE leads ADD COLUMN version integer NOT NULL DEFAULT 1;
ALTER TABLE leads ADD COLUMN personalisation varchar(400) NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN personalisation_evidence varchar(2000) NOT NULL DEFAULT '';
