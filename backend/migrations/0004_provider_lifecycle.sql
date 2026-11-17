ALTER TABLE checkouts ADD COLUMN payment_ref varchar(200) NOT NULL DEFAULT '';
ALTER TABLE checkouts ADD COLUMN subscription_ref varchar(200) NOT NULL DEFAULT '';
ALTER TABLE subscriptions ADD COLUMN provider_ref varchar(200) NOT NULL DEFAULT '';
ALTER TABLE subscriptions ADD COLUMN last_event_at double precision NOT NULL DEFAULT 0;
CREATE TABLE provider_events (
  id varchar(36) PRIMARY KEY,
  created_at double precision NOT NULL,
  organization_id varchar(36) NOT NULL REFERENCES organizations(id),
  provider varchar(24) NOT NULL,
  event_id varchar(200) NOT NULL,
  kind varchar(80) NOT NULL,
  object_ref varchar(200) NOT NULL,
  occurred_at double precision NOT NULL,
  amount_minor integer NOT NULL,
  currency varchar(3) NOT NULL,
  simulated boolean NOT NULL,
  evidence json NOT NULL,
  UNIQUE(organization_id,provider,event_id)
);
CREATE INDEX ix_provider_events_organization_id ON provider_events(organization_id);
ALTER TABLE provider_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON provider_events TO ai_mos_app
USING (organization_id = NULLIF(current_setting('app.current_org',true),''))
WITH CHECK (organization_id = NULLIF(current_setting('app.current_org',true),''));
GRANT SELECT,INSERT ON provider_events TO ai_mos_app;
