GRANT SELECT(id,organization_id,provider,status,enabled,sync_enabled,sync_next_at,sync_interval_minutes)
ON integrations TO ai_mos_queue;
GRANT UPDATE(sync_next_at) ON integrations TO ai_mos_queue;
CREATE POLICY inbox_queue ON integrations TO ai_mos_queue
USING (provider='gmail' AND status='verified' AND enabled AND sync_enabled)
WITH CHECK (provider='gmail' AND status='verified' AND enabled AND sync_enabled);
CREATE FUNCTION claim_next_inbox()
RETURNS TABLE(integration_id varchar,org_id varchar)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
  RETURN QUERY WITH candidate AS (
    SELECT i.id FROM public.integrations i
    JOIN public.organizations o ON o.id=i.organization_id
    WHERE i.provider='gmail' AND i.status='verified' AND i.enabled AND i.sync_enabled
      AND i.sync_next_at<=extract(epoch from now()) AND NOT o.emergency_stop
    ORDER BY i.sync_next_at FOR UPDATE OF i SKIP LOCKED LIMIT 1
  ) UPDATE public.integrations i SET sync_next_at=extract(epoch from now())+i.sync_interval_minutes*60
    FROM candidate c WHERE i.id=c.id RETURNING i.id,i.organization_id;
END $$;
GRANT CREATE ON SCHEMA public TO ai_mos_queue;
ALTER FUNCTION claim_next_inbox() OWNER TO ai_mos_queue;
REVOKE CREATE ON SCHEMA public FROM ai_mos_queue;
REVOKE ALL ON FUNCTION claim_next_inbox() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_next_inbox() TO ai_mos_worker;
