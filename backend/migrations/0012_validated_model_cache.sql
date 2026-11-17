ALTER TABLE model_usage ADD COLUMN cache_source_id varchar(36) REFERENCES model_usage(id);
ALTER TABLE model_usage ADD CONSTRAINT cache_source_tenant
FOREIGN KEY(organization_id,cache_source_id) REFERENCES model_usage(organization_id,id);
CREATE TABLE model_cache (
 id varchar(36) PRIMARY KEY,
 created_at double precision NOT NULL,
 organization_id varchar(36) NOT NULL REFERENCES organizations(id),
 cache_key varchar(64) NOT NULL,
 model_id varchar(200) NOT NULL,
 source_usage_id varchar(36) NOT NULL REFERENCES model_usage(id),
 output json NOT NULL,
 expires_at double precision NOT NULL,
 UNIQUE(organization_id,cache_key),
 FOREIGN KEY(organization_id,source_usage_id) REFERENCES model_usage(organization_id,id)
);
CREATE INDEX ix_model_cache_organization_id ON model_cache(organization_id);
ALTER TABLE model_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_cache FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON model_cache TO ai_mos_app
USING(organization_id=NULLIF(current_setting('app.current_org',true),''))
WITH CHECK(organization_id=NULLIF(current_setting('app.current_org',true),''));
GRANT SELECT,INSERT,UPDATE,DELETE ON model_cache TO ai_mos_app;
