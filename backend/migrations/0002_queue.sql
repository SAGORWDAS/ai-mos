-- Queue selection is a narrow security-definer boundary. Web connections cannot invoke it.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ai_mos_queue') THEN
    CREATE ROLE ai_mos_queue NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ai_mos_worker') THEN
    CREATE ROLE ai_mos_worker NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;
GRANT ai_mos_app TO ai_mos_worker;
GRANT USAGE ON SCHEMA public TO ai_mos_queue;
GRANT SELECT, UPDATE ON tasks, sequence_enrollments TO ai_mos_queue;
GRANT SELECT ON organizations TO ai_mos_queue;
GRANT SELECT ON checkouts TO ai_mos_queue;
GRANT SELECT, UPDATE ON effects TO ai_mos_queue;
GRANT SELECT ON approvals TO ai_mos_queue;
CREATE POLICY queue_selection ON tasks TO ai_mos_queue USING (true) WITH CHECK (true);
CREATE POLICY queue_selection ON sequence_enrollments TO ai_mos_queue USING (true) WITH CHECK (true);
CREATE POLICY provider_reference_lookup ON checkouts FOR SELECT TO ai_mos_queue USING (true);
CREATE POLICY effect_queue_selection ON effects TO ai_mos_queue USING (true) WITH CHECK (true);
CREATE POLICY effect_approval_lookup ON approvals FOR SELECT TO ai_mos_queue USING (true);

CREATE FUNCTION claim_next_task()
RETURNS TABLE(job_id varchar, org_id varchar, actor_id varchar)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
  RETURN QUERY
    WITH candidate AS (
      SELECT t.id FROM public.tasks t
      WHERE t.status='running' AND t.leased_until < extract(epoch from now()) AND t.attempt>=3
      ORDER BY t.leased_until FOR UPDATE SKIP LOCKED LIMIT 1
    ) UPDATE public.tasks t SET status='failed', error_code='attempt_limit', leased_until=NULL
      FROM candidate c WHERE t.id=c.id RETURNING t.id,t.organization_id,t.created_by;
  IF FOUND THEN RETURN; END IF;
  UPDATE public.tasks SET status='ready'
    WHERE status='running' AND leased_until < extract(epoch from now()) AND attempt<3;
  RETURN QUERY
    WITH candidate AS (
      SELECT t.id FROM public.tasks t JOIN public.organizations o ON o.id=t.organization_id
      WHERE t.status='ready' AND NOT o.emergency_stop
      ORDER BY t.created_at,t.id FOR UPDATE OF t SKIP LOCKED LIMIT 1
    ) UPDATE public.tasks t SET status='running',attempt=t.attempt+1,
      leased_until=extract(epoch from now())+90
      FROM candidate c WHERE t.id=c.id RETURNING t.id,t.organization_id,t.created_by;
END $$;

CREATE FUNCTION claim_next_enrollment()
RETURNS TABLE(enrollment_id varchar, org_id varchar, actor_id varchar)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
  UPDATE public.sequence_enrollments SET status='active'
    WHERE status='processing' AND next_at < extract(epoch from now())-120;
  RETURN QUERY
    WITH candidate AS (
      SELECT e.id FROM public.sequence_enrollments e
      JOIN public.organizations o ON o.id=e.organization_id
      WHERE e.status='active' AND e.next_at<=extract(epoch from now()) AND NOT o.emergency_stop
      ORDER BY e.next_at FOR UPDATE OF e SKIP LOCKED LIMIT 1
    ) UPDATE public.sequence_enrollments e SET status='processing' FROM candidate c
      WHERE e.id=c.id RETURNING e.id,e.organization_id,e.created_by;
END $$;

CREATE FUNCTION claim_next_effect()
RETURNS TABLE(effect_id varchar, org_id varchar, actor_id varchar)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
  RETURN QUERY WITH candidate AS (
    SELECT e.id,a.decided_by FROM public.effects e JOIN public.approvals a ON a.id=e.approval_id
    WHERE e.status='dispatching' AND e.dispatch_started_at < extract(epoch from now())-90
    ORDER BY e.dispatch_started_at FOR UPDATE OF e SKIP LOCKED LIMIT 1
  ) UPDATE public.effects e SET status='uncertain' FROM candidate c WHERE e.id=c.id
    RETURNING e.id,e.organization_id,c.decided_by;
  IF FOUND THEN RETURN; END IF;
  RETURN QUERY WITH candidate AS (
    SELECT e.id,a.decided_by FROM public.effects e
    JOIN public.approvals a ON a.id=e.approval_id
    JOIN public.organizations o ON o.id=e.organization_id
    WHERE e.status='queued' AND NOT o.emergency_stop
    ORDER BY e.created_at FOR UPDATE OF e SKIP LOCKED LIMIT 1
  ) UPDATE public.effects e SET status='dispatching',dispatch_started_at=extract(epoch from now())
    FROM candidate c WHERE e.id=c.id RETURNING e.id,e.organization_id,c.decided_by;
END $$;

GRANT CREATE ON SCHEMA public TO ai_mos_queue;
CREATE FUNCTION resolve_checkout_org(provider_reference text) RETURNS varchar
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
  SELECT organization_id FROM public.checkouts WHERE provider_ref=provider_reference
$$;
ALTER FUNCTION resolve_checkout_org(text) OWNER TO ai_mos_queue;
ALTER FUNCTION claim_next_task() OWNER TO ai_mos_queue;
ALTER FUNCTION claim_next_enrollment() OWNER TO ai_mos_queue;
ALTER FUNCTION claim_next_effect() OWNER TO ai_mos_queue;
REVOKE CREATE ON SCHEMA public FROM ai_mos_queue;
REVOKE ALL ON FUNCTION claim_next_task() FROM PUBLIC;
REVOKE ALL ON FUNCTION claim_next_enrollment() FROM PUBLIC;
REVOKE ALL ON FUNCTION claim_next_effect() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_next_task(),claim_next_enrollment(),claim_next_effect() TO ai_mos_worker;
REVOKE ALL ON FUNCTION resolve_checkout_org(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resolve_checkout_org(text) TO ai_mos_app;
