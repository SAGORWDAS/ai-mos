CREATE TABLE validation_records (
 id varchar(36) PRIMARY KEY, created_at double precision NOT NULL,
 organization_id varchar(36) NOT NULL REFERENCES organizations(id),
 created_by varchar(36) NOT NULL REFERENCES users(id),
 kind varchar(40) NOT NULL, outcome varchar(16) NOT NULL,
 reference varchar(300) NOT NULL, note text NOT NULL, scope_hash varchar(64) NOT NULL
);
CREATE INDEX ix_validation_records_organization_id ON validation_records(organization_id);
ALTER TABLE validation_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_records FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON validation_records TO ai_mos_app
USING(organization_id=NULLIF(current_setting('app.current_org',true),''))
WITH CHECK(organization_id=NULLIF(current_setting('app.current_org',true),''));
GRANT SELECT,INSERT ON validation_records TO ai_mos_app;
