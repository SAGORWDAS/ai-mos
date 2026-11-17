ALTER TABLE users ADD COLUMN recovery_hash varchar(64) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN totp_secret varchar(2000) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN totp_pending varchar(2000) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN totp_last_counter double precision NOT NULL DEFAULT -1;
CREATE POLICY session_owner ON sessions TO ai_mos_app
USING (user_id = current_setting('app.current_user', true))
WITH CHECK (user_id = current_setting('app.current_user', true));
