# Setup and operation

## Windows local app

Install Node.js 22+ and Python 3.12+. Double-click `Start-AI-MOS.cmd`; open http://localhost:3000. If Python is not on PATH:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1 -PythonPath "C:\path\to\python.exe"
```

The API is at http://127.0.0.1:8000, with interactive documentation at `/docs`. The frontend uses a same-origin `/api/` proxy. Both processes bind to loopback. `Stop-AI-MOS.cmd` stops only launcher-managed processes whose command lines belong to this project.

Create your own account; synthetic QA accounts are absent from source releases. Save an offline recovery code privately under Team & settings, and optionally configure an authenticator. Recovery consumes the code once, resets MFA and revokes all sessions. Invitations are shared manually; automated verification/password-reset email is not provided.

Private files live in `.run/`. Keep `encryption.key` with private database backups: losing it prevents decrypting saved provider credentials. Never publish that directory. The launcher makes a new backup before applying a changed local schema. Backups are not automatically deleted or uploaded.

## SQLite backup and restore

Run from `backend/` using the project's Python environment:

```powershell
python -m app.backup backup ..\.run\local.db ..\.run\backups\new-backup.db
python -m app.backup restore ..\.run\backups\new-backup.db ..\.run\restored-check.db
```

Destinations must be new. Restore checks the manifest, checksum, integrity and counts. It creates a separate database and never replaces the active one. Stop the app before deliberately switching database files, and retain the original.

## Docker and PostgreSQL development

Copy `.env.example` to `.env`. Choose separate database role passwords. Generate a persistent Fernet key and store it privately as `TOKEN_ENCRYPTION_KEY`:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose -f infra/docker-compose.yml up -d --build
```

The migrator applies checksum-tracked migrations and provisions restricted API/worker roles. The app's durable queue and shared throttles use the database; Redis is included in the reference development stack but is not required by the current runtime. `docker compose ... down` keeps the named data volume. Adding `-v` deletes it; use that only for disposable test stacks.

Never edit an applied migration. Run `python -m app.migrate upgrade` with private `MIGRATION_DATABASE_URL` for a controlled migration. Runtime credentials must not be superusers or bypass RLS.

## PostgreSQL backup and restore

Install matching PostgreSQL client tools. From `backend/`, set a private `BACKUP_DATABASE_URL` for a dedicated backup administrator, then:

```powershell
python -m app.pgbackup backup ..\.run\backups\new.dump --bin-dir "C:\PostgreSQL\16\bin"
```

Create a different, empty database and set private `RESTORE_DATABASE_URL` for it. Run:

```powershell
python -m app.pgbackup restore ..\.run\backups\new.dump --bin-dir "C:\PostgreSQL\16\bin"
```

Backup uses an exported consistent snapshot and writes a checksum/count/audit manifest. Restore is transactional, preserves role grants, resets narrow queue function ownership to the restricted queue role, and verifies table counts and audit content. It refuses a nonempty destination or the same database name. Cluster login credentials are managed separately. Store the encryption key separately with the backup. Periodically practice recovery into an isolated database.

## Before public hosting

This release defaults to local development. Configure an HTTPS reverse proxy, trusted forwarded client addresses, `ALLOWED_ORIGINS`, `PUBLIC_API_URL`, `SECURE_COOKIES=true`, persistent secrets, backups, monitoring and provider callbacks. Review tenancy, abuse handling and recovery. `APP_ENV=production` deliberately refuses startup pending that deployment review; changing the flag is not a production readiness certificate. See the build status and integration checklist.
