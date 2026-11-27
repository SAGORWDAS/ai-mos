# Setup — T-1.1

The stack is scaffolded. Two prerequisites are missing on this machine, and neither can be installed for you.

## 1. Install Docker Desktop

```powershell
winget install --id Docker.DockerDesktop -e
```

Then start Docker Desktop once and leave it running. It must be running before `make up`; the engine is a background service, not a CLI convenience.

## 2. Python (optional, host-side only)

Everything runs in containers, so Python is not required to run the stack. Install it only if you want to run `pytest` or `ruff` outside Docker:

```powershell
winget install --id Python.Python.3.12 -e
```

Node 22+ is already present and is enough for host-side frontend work.

## 3. First run

```powershell
make doctor     # checks docker, engine, ports, .env
make env        # creates .env from .env.example
make up         # builds and starts db, redis, api, worker, web
```

Expected: `web` at http://localhost:3000 shows **Stack status** with `database: reachable` and `redis: reachable`, and http://localhost:8000/healthz returns `{"status":"ok"}`.

`make down` stops everything. `make logs` follows all containers.

## 4. Definition of done for T-1.1

- [ ] `make up` brings up five containers, all healthy
- [ ] `/healthz` returns 200 with both checks true
- [ ] the web page renders the two checks as reachable
- [ ] `make test` runs the two backend tests green
- [ ] CI passes on the first push

Until Docker is installed, the first two boxes cannot be ticked — the scaffold is written but **unproven**. That is the honest state, and it is the reason T-1.1 is not marked done.

## What is deliberately not here yet

- No database tables — migrations are `T-1.3`.
- No auth — `T-1.2`.
- No job handlers — `T-1.5` registers them; the worker currently heartbeats only.
- No CI lockfile — `package-lock.json` is generated on the first `npm install` and then committed.
