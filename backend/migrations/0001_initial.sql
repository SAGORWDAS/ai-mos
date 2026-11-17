-- Initial application schema; apply through python -m app.migrate upgrade.

DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ai_mos_app') THEN CREATE ROLE ai_mos_app NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;


CREATE TABLE organizations (
	name VARCHAR(120) NOT NULL, 
	emergency_stop BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	PRIMARY KEY (id)
)

;


CREATE TABLE users (
	email VARCHAR(254) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(256) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
)

;


CREATE TABLE agents (
	role_id VARCHAR(16) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	config JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, role_id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_agents_organization_id ON agents (organization_id);


CREATE TABLE approvals (
	subject_type VARCHAR(32) NOT NULL, 
	subject_id VARCHAR(36) NOT NULL, 
	action_class VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	payload_hash VARCHAR(64) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	expires_at FLOAT NOT NULL, 
	decided_by VARCHAR(36), 
	decided_at FLOAT, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(decided_by) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_approvals_organization_id ON approvals (organization_id);


CREATE TABLE audit_logs (
	actor_id VARCHAR(36) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	subject_id VARCHAR(36) NOT NULL, 
	decision VARCHAR(24) NOT NULL, 
	trace_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_audit_logs_organization_id ON audit_logs (organization_id);


CREATE TABLE brands (
	name VARCHAR(120) NOT NULL, 
	website VARCHAR(500) NOT NULL, 
	positioning VARCHAR(5000) NOT NULL, 
	icp JSON NOT NULL, 
	voice JSON NOT NULL, 
	pricing JSON NOT NULL, 
	approved_claims JSON NOT NULL, 
	prohibited_claims JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, name), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_brands_organization_id ON brands (organization_id);


CREATE TABLE budgets (
	period VARCHAR(7) NOT NULL, 
	limit_micros INTEGER NOT NULL, 
	spent_micros INTEGER NOT NULL, 
	reserved_micros INTEGER NOT NULL, 
	daily_send_cap INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, period), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_budgets_organization_id ON budgets (organization_id);


CREATE TABLE daily_sends (
	organization_id VARCHAR(36) NOT NULL, 
	day VARCHAR(10) NOT NULL, 
	count INTEGER NOT NULL, 
	PRIMARY KEY (organization_id, day), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;


CREATE TABLE expenses (
	category VARCHAR(24) NOT NULL, 
	amount_micros INTEGER NOT NULL, 
	evidence VARCHAR(1000) NOT NULL, 
	simulated BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_expenses_organization_id ON expenses (organization_id);


CREATE TABLE integrations (
	provider VARCHAR(24) NOT NULL, 
	account_ref VARCHAR(254) NOT NULL, 
	token_ciphertext TEXT NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, provider), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_integrations_organization_id ON integrations (organization_id);


CREATE TABLE invitations (
	email VARCHAR(254) NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at FLOAT NOT NULL, 
	accepted BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (token_hash), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_invitations_organization_id ON invitations (organization_id);


CREATE TABLE learning_records (
	lesson TEXT NOT NULL, 
	evidence JSON NOT NULL, 
	effect_size INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_learning_records_organization_id ON learning_records (organization_id);


CREATE TABLE memberships (
	user_id VARCHAR(36) NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_memberships_organization_id ON memberships (organization_id);


CREATE TABLE notifications (
	title VARCHAR(200) NOT NULL, 
	subject_id VARCHAR(36) NOT NULL, 
	read BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_notifications_organization_id ON notifications (organization_id);


CREATE TABLE sessions (
	user_id VARCHAR(36) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at FLOAT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	UNIQUE (token_hash), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_sessions_organization_id ON sessions (organization_id);


CREATE TABLE suppressions (
	address VARCHAR(254) NOT NULL, 
	reason VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, address), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_suppressions_organization_id ON suppressions (organization_id);


CREATE TABLE workflows (
	name VARCHAR(160) NOT NULL, 
	trigger VARCHAR(80) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_workflows_organization_id ON workflows (organization_id);


CREATE TABLE brand_documents (
	brand_id VARCHAR(36) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	source_uri VARCHAR(500) NOT NULL, 
	checksum VARCHAR(64) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, brand_id, checksum), 
	FOREIGN KEY(brand_id) REFERENCES brands (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_brand_documents_organization_id ON brand_documents (organization_id);


CREATE TABLE campaigns (
	brand_id VARCHAR(36) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	lead_ids JSON NOT NULL, 
	budget_micros INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(brand_id) REFERENCES brands (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_campaigns_organization_id ON campaigns (organization_id);


CREATE TABLE commands (
	brand_id VARCHAR(36) NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	raw TEXT NOT NULL, 
	parsed JSON NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(brand_id) REFERENCES brands (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_commands_organization_id ON commands (organization_id);


CREATE TABLE content_items (
	brand_id VARCHAR(36) NOT NULL, 
	type VARCHAR(32) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	citations JSON NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(brand_id) REFERENCES brands (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_content_items_organization_id ON content_items (organization_id);


CREATE TABLE effects (
	action VARCHAR(40) NOT NULL, 
	idempotency_key VARCHAR(200) NOT NULL, 
	approval_id VARCHAR(36) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	payload JSON NOT NULL, 
	result JSON NOT NULL, 
	dispatch_started_at FLOAT, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, idempotency_key), 
	UNIQUE (approval_id), 
	FOREIGN KEY(approval_id) REFERENCES approvals (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_effects_organization_id ON effects (organization_id);


CREATE TABLE leads (
	brand_id VARCHAR(36) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	company VARCHAR(200) NOT NULL, 
	domain VARCHAR(250) NOT NULL, 
	source VARCHAR(500) NOT NULL, 
	source_confidence INTEGER NOT NULL, 
	lawful_basis VARCHAR(32) NOT NULL, 
	basis_evidence TEXT NOT NULL, 
	score INTEGER NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, email), 
	FOREIGN KEY(brand_id) REFERENCES brands (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_leads_organization_id ON leads (organization_id);


CREATE TABLE sequences (
	brand_id VARCHAR(36) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	delay_days INTEGER NOT NULL, 
	max_steps INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(brand_id) REFERENCES brands (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_sequences_organization_id ON sequences (organization_id);


CREATE TABLE workflow_runs (
	workflow_id VARCHAR(36) NOT NULL, 
	event_id VARCHAR(200) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	output JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, workflow_id, event_id), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_workflow_runs_organization_id ON workflow_runs (organization_id);


CREATE TABLE activities (
	lead_id VARCHAR(36) NOT NULL, 
	actor_id VARCHAR(36) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	detail TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_activities_organization_id ON activities (organization_id);


CREATE TABLE brand_chunks (
	document_id VARCHAR(36) NOT NULL, 
	brand_id VARCHAR(36) NOT NULL, 
	ordinal INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES brand_documents (id), 
	FOREIGN KEY(brand_id) REFERENCES brands (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_brand_chunks_organization_id ON brand_chunks (organization_id);


CREATE TABLE checkouts (
	lead_id VARCHAR(36) NOT NULL, 
	description VARCHAR(200) NOT NULL, 
	amount_minor INTEGER NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	provider_ref VARCHAR(200) NOT NULL, 
	recurring BOOLEAN NOT NULL, 
	url VARCHAR(2000) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	UNIQUE (provider_ref), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_checkouts_organization_id ON checkouts (organization_id);


CREATE TABLE customers (
	lead_id VARCHAR(36) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	onboarding JSON NOT NULL, 
	health_score INTEGER NOT NULL, 
	simulated BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, lead_id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_customers_organization_id ON customers (organization_id);


CREATE TABLE meetings (
	lead_id VARCHAR(36) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	starts_at FLOAT NOT NULL, 
	ends_at FLOAT NOT NULL, 
	timezone VARCHAR(80) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	provider_id VARCHAR(200) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_meetings_organization_id ON meetings (organization_id);


CREATE TABLE plans (
	command_id VARCHAR(36) NOT NULL, 
	brand_id VARCHAR(36) NOT NULL, 
	objective TEXT NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	payload JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(command_id) REFERENCES commands (id), 
	FOREIGN KEY(brand_id) REFERENCES brands (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_plans_organization_id ON plans (organization_id);


CREATE TABLE sequence_enrollments (
	sequence_id VARCHAR(36) NOT NULL, 
	lead_id VARCHAR(36) NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	step INTEGER NOT NULL, 
	next_at FLOAT NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, sequence_id, lead_id), 
	FOREIGN KEY(sequence_id) REFERENCES sequences (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_sequence_enrollments_organization_id ON sequence_enrollments (organization_id);


CREATE TABLE payments (
	provider_event_id VARCHAR(200) NOT NULL, 
	checkout_id VARCHAR(36) NOT NULL, 
	lead_id VARCHAR(36) NOT NULL, 
	amount_minor INTEGER NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	simulated BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (provider_event_id), 
	FOREIGN KEY(checkout_id) REFERENCES checkouts (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_payments_organization_id ON payments (organization_id);


CREATE TABLE subscriptions (
	customer_id VARCHAR(36) NOT NULL, 
	checkout_id VARCHAR(36) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	amount_minor INTEGER NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	current_period_end FLOAT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, customer_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(checkout_id) REFERENCES checkouts (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_subscriptions_organization_id ON subscriptions (organization_id);


CREATE TABLE support_threads (
	customer_id VARCHAR(36) NOT NULL, 
	subject VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	response TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_support_threads_organization_id ON support_threads (organization_id);


CREATE TABLE tasks (
	plan_id VARCHAR(36), 
	created_by VARCHAR(36) NOT NULL, 
	agent_id VARCHAR(16) NOT NULL, 
	type VARCHAR(40) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	idempotency_key VARCHAR(200) NOT NULL, 
	input JSON NOT NULL, 
	output JSON NOT NULL, 
	attempt INTEGER NOT NULL, 
	error_code VARCHAR(120) NOT NULL, 
	leased_until FLOAT, 
	finished_at FLOAT, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, idempotency_key), 
	FOREIGN KEY(plan_id) REFERENCES plans (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_tasks_organization_id ON tasks (organization_id);

CREATE INDEX ix_tasks_status ON tasks (status);


CREATE TABLE model_usage (
	request_id VARCHAR(36) NOT NULL, 
	task_id VARCHAR(36) NOT NULL, 
	agent_id VARCHAR(16) NOT NULL, 
	model_id VARCHAR(200) NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	input_tokens INTEGER NOT NULL, 
	output_tokens INTEGER NOT NULL, 
	cost_micros INTEGER NOT NULL, 
	simulated BOOLEAN NOT NULL, 
	latency_ms INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (request_id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_model_usage_organization_id ON model_usage (organization_id);


CREATE TABLE outreach_drafts (
	lead_id VARCHAR(36) NOT NULL, 
	task_id VARCHAR(36), 
	subject VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	claims JSON NOT NULL, 
	version INTEGER NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_outreach_drafts_organization_id ON outreach_drafts (organization_id);


CREATE TABLE task_dependencies (
	task_id VARCHAR(36) NOT NULL, 
	depends_on_id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (task_id, depends_on_id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id), 
	FOREIGN KEY(depends_on_id) REFERENCES tasks (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_task_dependencies_organization_id ON task_dependencies (organization_id);


CREATE TABLE messages (
	lead_id VARCHAR(36) NOT NULL, 
	draft_id VARCHAR(36), 
	approval_id VARCHAR(36), 
	direction VARCHAR(16) NOT NULL, 
	subject VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	provider_id VARCHAR(200) NOT NULL, 
	classification JSON NOT NULL, 
	idempotency_key VARCHAR(200) NOT NULL, 
	simulated BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, idempotency_key), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(draft_id) REFERENCES outreach_drafts (id), 
	FOREIGN KEY(approval_id) REFERENCES approvals (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE INDEX ix_messages_organization_id ON messages (organization_id);

ALTER TABLE agents ADD CONSTRAINT agents_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE approvals ADD CONSTRAINT approvals_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE brands ADD CONSTRAINT brands_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE budgets ADD CONSTRAINT budgets_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE expenses ADD CONSTRAINT expenses_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE integrations ADD CONSTRAINT integrations_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE invitations ADD CONSTRAINT invitations_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE learning_records ADD CONSTRAINT learning_records_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE memberships ADD CONSTRAINT memberships_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE notifications ADD CONSTRAINT notifications_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE sessions ADD CONSTRAINT sessions_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE suppressions ADD CONSTRAINT suppressions_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE workflows ADD CONSTRAINT workflows_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE brand_documents ADD CONSTRAINT brand_documents_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE campaigns ADD CONSTRAINT campaigns_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE commands ADD CONSTRAINT commands_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE content_items ADD CONSTRAINT content_items_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE effects ADD CONSTRAINT effects_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE leads ADD CONSTRAINT leads_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE sequences ADD CONSTRAINT sequences_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE workflow_runs ADD CONSTRAINT workflow_runs_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE activities ADD CONSTRAINT activities_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE brand_chunks ADD CONSTRAINT brand_chunks_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE checkouts ADD CONSTRAINT checkouts_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE customers ADD CONSTRAINT customers_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE meetings ADD CONSTRAINT meetings_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE plans ADD CONSTRAINT plans_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE sequence_enrollments ADD CONSTRAINT sequence_enrollments_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE payments ADD CONSTRAINT payments_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE support_threads ADD CONSTRAINT support_threads_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE tasks ADD CONSTRAINT tasks_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE model_usage ADD CONSTRAINT model_usage_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE outreach_drafts ADD CONSTRAINT outreach_drafts_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE messages ADD CONSTRAINT messages_tenant_identity UNIQUE (organization_id, id);

ALTER TABLE agents ENABLE ROW LEVEL SECURITY;

ALTER TABLE agents FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON agents TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;

ALTER TABLE approvals FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON approvals TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON audit_logs TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE brands ENABLE ROW LEVEL SECURITY;

ALTER TABLE brands FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON brands TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE budgets ENABLE ROW LEVEL SECURITY;

ALTER TABLE budgets FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON budgets TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE daily_sends ENABLE ROW LEVEL SECURITY;

ALTER TABLE daily_sends FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON daily_sends TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;

ALTER TABLE expenses FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON expenses TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE integrations ENABLE ROW LEVEL SECURITY;

ALTER TABLE integrations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON integrations TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;

ALTER TABLE invitations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON invitations TO ai_mos_app USING ((organization_id = NULLIF(current_setting('app.current_org', true), '') OR email = (SELECT email FROM users WHERE id = current_setting('app.current_user', true)))) WITH CHECK ((organization_id = NULLIF(current_setting('app.current_org', true), '') OR email = (SELECT email FROM users WHERE id = current_setting('app.current_user', true))));

ALTER TABLE learning_records ENABLE ROW LEVEL SECURITY;

ALTER TABLE learning_records FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON learning_records TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;

ALTER TABLE memberships FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON memberships TO ai_mos_app USING ((organization_id = NULLIF(current_setting('app.current_org', true), '') OR user_id = current_setting('app.current_user', true))) WITH CHECK ((organization_id = NULLIF(current_setting('app.current_org', true), '') OR user_id = current_setting('app.current_user', true)));

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

ALTER TABLE notifications FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON notifications TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

ALTER TABLE sessions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON sessions TO ai_mos_app USING ((organization_id = NULLIF(current_setting('app.current_org', true), '') OR token_hash = current_setting('app.session_hash', true))) WITH CHECK ((organization_id = NULLIF(current_setting('app.current_org', true), '') OR token_hash = current_setting('app.session_hash', true)));

ALTER TABLE suppressions ENABLE ROW LEVEL SECURITY;

ALTER TABLE suppressions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON suppressions TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;

ALTER TABLE workflows FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON workflows TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE brand_documents ADD CONSTRAINT fk_brand_documents_brand_id_tenant FOREIGN KEY (organization_id, brand_id) REFERENCES brands(organization_id, id);

ALTER TABLE brand_documents ENABLE ROW LEVEL SECURITY;

ALTER TABLE brand_documents FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON brand_documents TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE campaigns ADD CONSTRAINT fk_campaigns_brand_id_tenant FOREIGN KEY (organization_id, brand_id) REFERENCES brands(organization_id, id);

ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;

ALTER TABLE campaigns FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON campaigns TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE commands ADD CONSTRAINT fk_commands_brand_id_tenant FOREIGN KEY (organization_id, brand_id) REFERENCES brands(organization_id, id);

ALTER TABLE commands ENABLE ROW LEVEL SECURITY;

ALTER TABLE commands FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON commands TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE content_items ADD CONSTRAINT fk_content_items_brand_id_tenant FOREIGN KEY (organization_id, brand_id) REFERENCES brands(organization_id, id);

ALTER TABLE content_items ENABLE ROW LEVEL SECURITY;

ALTER TABLE content_items FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON content_items TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE effects ADD CONSTRAINT fk_effects_approval_id_tenant FOREIGN KEY (organization_id, approval_id) REFERENCES approvals(organization_id, id);

ALTER TABLE effects ENABLE ROW LEVEL SECURITY;

ALTER TABLE effects FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON effects TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE leads ADD CONSTRAINT fk_leads_brand_id_tenant FOREIGN KEY (organization_id, brand_id) REFERENCES brands(organization_id, id);

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

ALTER TABLE leads FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON leads TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE sequences ADD CONSTRAINT fk_sequences_brand_id_tenant FOREIGN KEY (organization_id, brand_id) REFERENCES brands(organization_id, id);

ALTER TABLE sequences ENABLE ROW LEVEL SECURITY;

ALTER TABLE sequences FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON sequences TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE workflow_runs ADD CONSTRAINT fk_workflow_runs_workflow_id_tenant FOREIGN KEY (organization_id, workflow_id) REFERENCES workflows(organization_id, id);

ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE workflow_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON workflow_runs TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE activities ADD CONSTRAINT fk_activities_lead_id_tenant FOREIGN KEY (organization_id, lead_id) REFERENCES leads(organization_id, id);

ALTER TABLE activities ENABLE ROW LEVEL SECURITY;

ALTER TABLE activities FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON activities TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE brand_chunks ADD CONSTRAINT fk_brand_chunks_document_id_tenant FOREIGN KEY (organization_id, document_id) REFERENCES brand_documents(organization_id, id);

ALTER TABLE brand_chunks ADD CONSTRAINT fk_brand_chunks_brand_id_tenant FOREIGN KEY (organization_id, brand_id) REFERENCES brands(organization_id, id);

ALTER TABLE brand_chunks ENABLE ROW LEVEL SECURITY;

ALTER TABLE brand_chunks FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON brand_chunks TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE checkouts ADD CONSTRAINT fk_checkouts_lead_id_tenant FOREIGN KEY (organization_id, lead_id) REFERENCES leads(organization_id, id);

ALTER TABLE checkouts ENABLE ROW LEVEL SECURITY;

ALTER TABLE checkouts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON checkouts TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE customers ADD CONSTRAINT fk_customers_lead_id_tenant FOREIGN KEY (organization_id, lead_id) REFERENCES leads(organization_id, id);

ALTER TABLE customers ENABLE ROW LEVEL SECURITY;

ALTER TABLE customers FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON customers TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE meetings ADD CONSTRAINT fk_meetings_lead_id_tenant FOREIGN KEY (organization_id, lead_id) REFERENCES leads(organization_id, id);

ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;

ALTER TABLE meetings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON meetings TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE plans ADD CONSTRAINT fk_plans_command_id_tenant FOREIGN KEY (organization_id, command_id) REFERENCES commands(organization_id, id);

ALTER TABLE plans ADD CONSTRAINT fk_plans_brand_id_tenant FOREIGN KEY (organization_id, brand_id) REFERENCES brands(organization_id, id);

ALTER TABLE plans ENABLE ROW LEVEL SECURITY;

ALTER TABLE plans FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON plans TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE sequence_enrollments ADD CONSTRAINT fk_sequence_enrollments_sequence_id_tenant FOREIGN KEY (organization_id, sequence_id) REFERENCES sequences(organization_id, id);

ALTER TABLE sequence_enrollments ADD CONSTRAINT fk_sequence_enrollments_lead_id_tenant FOREIGN KEY (organization_id, lead_id) REFERENCES leads(organization_id, id);

ALTER TABLE sequence_enrollments ENABLE ROW LEVEL SECURITY;

ALTER TABLE sequence_enrollments FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON sequence_enrollments TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE payments ADD CONSTRAINT fk_payments_checkout_id_tenant FOREIGN KEY (organization_id, checkout_id) REFERENCES checkouts(organization_id, id);

ALTER TABLE payments ADD CONSTRAINT fk_payments_lead_id_tenant FOREIGN KEY (organization_id, lead_id) REFERENCES leads(organization_id, id);

ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

ALTER TABLE payments FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON payments TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE subscriptions ADD CONSTRAINT fk_subscriptions_customer_id_tenant FOREIGN KEY (organization_id, customer_id) REFERENCES customers(organization_id, id);

ALTER TABLE subscriptions ADD CONSTRAINT fk_subscriptions_checkout_id_tenant FOREIGN KEY (organization_id, checkout_id) REFERENCES checkouts(organization_id, id);

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON subscriptions TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE support_threads ADD CONSTRAINT fk_support_threads_customer_id_tenant FOREIGN KEY (organization_id, customer_id) REFERENCES customers(organization_id, id);

ALTER TABLE support_threads ENABLE ROW LEVEL SECURITY;

ALTER TABLE support_threads FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON support_threads TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE tasks ADD CONSTRAINT fk_tasks_plan_id_tenant FOREIGN KEY (organization_id, plan_id) REFERENCES plans(organization_id, id);

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

ALTER TABLE tasks FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tasks TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE model_usage ADD CONSTRAINT fk_model_usage_task_id_tenant FOREIGN KEY (organization_id, task_id) REFERENCES tasks(organization_id, id);

ALTER TABLE model_usage ENABLE ROW LEVEL SECURITY;

ALTER TABLE model_usage FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON model_usage TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE outreach_drafts ADD CONSTRAINT fk_outreach_drafts_lead_id_tenant FOREIGN KEY (organization_id, lead_id) REFERENCES leads(organization_id, id);

ALTER TABLE outreach_drafts ADD CONSTRAINT fk_outreach_drafts_task_id_tenant FOREIGN KEY (organization_id, task_id) REFERENCES tasks(organization_id, id);

ALTER TABLE outreach_drafts ENABLE ROW LEVEL SECURITY;

ALTER TABLE outreach_drafts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON outreach_drafts TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE task_dependencies ADD CONSTRAINT fk_task_dependencies_task_id_tenant FOREIGN KEY (organization_id, task_id) REFERENCES tasks(organization_id, id);

ALTER TABLE task_dependencies ADD CONSTRAINT fk_task_dependencies_depends_on_id_tenant FOREIGN KEY (organization_id, depends_on_id) REFERENCES tasks(organization_id, id);

ALTER TABLE task_dependencies ENABLE ROW LEVEL SECURITY;

ALTER TABLE task_dependencies FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON task_dependencies TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

ALTER TABLE messages ADD CONSTRAINT fk_messages_lead_id_tenant FOREIGN KEY (organization_id, lead_id) REFERENCES leads(organization_id, id);

ALTER TABLE messages ADD CONSTRAINT fk_messages_draft_id_tenant FOREIGN KEY (organization_id, draft_id) REFERENCES outreach_drafts(organization_id, id);

ALTER TABLE messages ADD CONSTRAINT fk_messages_approval_id_tenant FOREIGN KEY (organization_id, approval_id) REFERENCES approvals(organization_id, id);

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

ALTER TABLE messages FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON messages TO ai_mos_app USING (organization_id = NULLIF(current_setting('app.current_org', true), '')) WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), ''));

GRANT USAGE ON SCHEMA public TO ai_mos_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_mos_app;

REVOKE ALL ON schema_migrations FROM ai_mos_app;

REVOKE UPDATE, DELETE ON audit_logs, payments, model_usage FROM ai_mos_app;

GRANT UPDATE ON model_usage TO ai_mos_app;
