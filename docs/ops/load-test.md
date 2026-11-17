# Controlled queue burst

Run `pytest -q tests/test_burst_acceptance.py` from backend for SQLite, or the `test_native_tenfold_worker_burst` test with `AI_MOS_TEST_ADMIN_URL` for disposable PostgreSQL databases. See tests/test_postgres.py for restricted API/worker identities and cleanup.

The nominal fixture batch is two tasks; a tenfold batch queues twenty distinct outreach drafts and replays every enqueue request. Four workers drain the queue. Each resulting exact-copy approval is then executed through the live-dispatch code with an HTTP-mocked Gmail transport, and every execution request is replayed. Four workers drain the effect queue. Assertions require twenty complete jobs, twenty drafts, twenty successful effects, twenty unique provider IDs and exactly twenty unique provider calls. A further drain performs no new calls. No network messages are sent.

This demonstrates a bounded concurrency/idempotency regression on both databases. It does not measure production p95 latency, a multi-host outage, actual Gmail quotas or the provider's retry semantics. Configure a staging SLO and independent operational drill before promising a production capacity.
