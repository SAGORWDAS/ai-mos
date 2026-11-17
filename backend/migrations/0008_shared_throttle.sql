CREATE TABLE auth_rate_limits (
  key_hash varchar(64) PRIMARY KEY,
  counter integer NOT NULL,
  expires_at double precision NOT NULL
);
CREATE INDEX ix_auth_rate_limits_expires_at ON auth_rate_limits(expires_at);
GRANT SELECT,INSERT,UPDATE,DELETE ON auth_rate_limits TO ai_mos_app;
