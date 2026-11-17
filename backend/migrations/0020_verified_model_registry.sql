CREATE TABLE model_registry (
 id varchar(36) PRIMARY KEY, created_at double precision NOT NULL,
 organization_id varchar(36) NOT NULL REFERENCES organizations(id),
 operation varchar(16) NOT NULL, model_id varchar(200) NOT NULL,
 status varchar(24) NOT NULL DEFAULT 'unverified',
 price_snapshot json NOT NULL DEFAULT '{}', verified_at double precision,
 source_connection_id varchar(36) REFERENCES integrations(id),
 source_connection_version integer NOT NULL DEFAULT 0,
 source_fingerprint varchar(64) NOT NULL,
 verification_error varchar(80) NOT NULL DEFAULT '',
 last_checked_at double precision NOT NULL DEFAULT 0,
 UNIQUE(organization_id,id), UNIQUE(organization_id,operation,model_id),
 FOREIGN KEY(organization_id,source_connection_id) REFERENCES integrations(organization_id,id)
);
CREATE INDEX ix_model_registry_organization_id ON model_registry(organization_id);
ALTER TABLE model_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_registry FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON model_registry TO ai_mos_app
USING(organization_id=NULLIF(current_setting('app.current_org',true),''))
WITH CHECK(organization_id=NULLIF(current_setting('app.current_org',true),''));
GRANT SELECT,INSERT,UPDATE,DELETE ON model_registry TO ai_mos_app;
ALTER TABLE model_usage ADD COLUMN model_registry_id varchar(36) REFERENCES model_registry(id);
ALTER TABLE model_usage ADD COLUMN model_price_snapshot json NOT NULL DEFAULT '{}';
ALTER TABLE model_usage ADD CONSTRAINT model_usage_registry_tenant_fk
FOREIGN KEY(organization_id,model_registry_id) REFERENCES model_registry(organization_id,id);
