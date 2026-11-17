ALTER TABLE approvals ADD COLUMN decision_basis varchar(200) NOT NULL DEFAULT 'human';
CREATE TABLE reply_policies (
 id varchar(36) PRIMARY KEY, created_at double precision NOT NULL,
 organization_id varchar(36) NOT NULL REFERENCES organizations(id),
 brand_id varchar(36) NOT NULL REFERENCES brands(id),
 owner_id varchar(36) NOT NULL REFERENCES users(id),
 enabled boolean NOT NULL DEFAULT false,
 execution_mode varchar(16) NOT NULL DEFAULT 'sandbox',
 connection_id varchar(36) REFERENCES integrations(id),
 connection_version integer NOT NULL DEFAULT 0,
 brand_hash varchar(64) NOT NULL, template_hash varchar(64) NOT NULL,
 expires_at double precision NOT NULL, daily_cap integer NOT NULL DEFAULT 5,
 counter_day varchar(10) NOT NULL DEFAULT '', counter_used integer NOT NULL DEFAULT 0,
 UNIQUE(organization_id,brand_id),
 FOREIGN KEY(organization_id,brand_id) REFERENCES brands(organization_id,id),
 FOREIGN KEY(organization_id,owner_id) REFERENCES memberships(organization_id,user_id),
 FOREIGN KEY(organization_id,connection_id) REFERENCES integrations(organization_id,id)
);
CREATE INDEX ix_reply_policies_organization_id ON reply_policies(organization_id);
ALTER TABLE reply_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE reply_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON reply_policies TO ai_mos_app
USING(organization_id=NULLIF(current_setting('app.current_org',true),''))
WITH CHECK(organization_id=NULLIF(current_setting('app.current_org',true),''));
GRANT SELECT,INSERT,UPDATE,DELETE ON reply_policies TO ai_mos_app;
