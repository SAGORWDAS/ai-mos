ALTER TABLE expenses ADD COLUMN campaign_id varchar(36) REFERENCES campaigns(id);
ALTER TABLE expenses ADD CONSTRAINT expense_campaign_tenant FOREIGN KEY(organization_id,campaign_id) REFERENCES campaigns(organization_id,id);
CREATE TABLE attribution_touches (
 id varchar(36) PRIMARY KEY,
 created_at double precision NOT NULL,
 organization_id varchar(36) NOT NULL REFERENCES organizations(id),
 lead_id varchar(36) NOT NULL REFERENCES leads(id),
 campaign_id varchar(36) NOT NULL REFERENCES campaigns(id),
 channel varchar(40) NOT NULL,
 evidence varchar(1000) NOT NULL,
 occurred_at double precision NOT NULL,
 simulated boolean NOT NULL DEFAULT true,
 idempotency_key varchar(200) NOT NULL,
 UNIQUE(organization_id,idempotency_key),
 FOREIGN KEY(organization_id,lead_id) REFERENCES leads(organization_id,id),
 FOREIGN KEY(organization_id,campaign_id) REFERENCES campaigns(organization_id,id)
);
CREATE INDEX ix_attribution_touches_organization_id ON attribution_touches(organization_id);
CREATE INDEX ix_attribution_lead_time ON attribution_touches(organization_id,lead_id,occurred_at);
ALTER TABLE attribution_touches ENABLE ROW LEVEL SECURITY;
ALTER TABLE attribution_touches FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON attribution_touches TO ai_mos_app
USING(organization_id=NULLIF(current_setting('app.current_org',true),''))
WITH CHECK(organization_id=NULLIF(current_setting('app.current_org',true),''));
GRANT SELECT,INSERT ON attribution_touches TO ai_mos_app;
