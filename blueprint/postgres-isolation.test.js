const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {PGlite} = require('@electric-sql/pglite');
const {vector}=require('@electric-sql/pglite-pgvector');

test('AC01/AC02: PostgreSQL forced RLS covers every tenant table and rejects cross-tenant foreign keys', async () => {
  const root=path.join(__dirname,'..','backend','migrations');
  const db=new PGlite({extensions:{vector}});
  try {
    await db.exec('CREATE TABLE schema_migrations(version text PRIMARY KEY, checksum text NOT NULL)');
    await db.exec(fs.readFileSync(path.join(root,'0001_initial.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'0003_account_security.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'0004_provider_lifecycle.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'0005_cost_reconciliation.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'0006_inbox_schedule.sql'),'utf8'));
    for(const filename of ['0008_shared_throttle.sql','0009_multiple_subscriptions.sql','0010_embeddings.sql','0011_optional_pgvector.sql']) await db.exec(fs.readFileSync(path.join(root,filename),'utf8'));
    for(const filename of ['0012_validated_model_cache.sql','0013_content_job_identity.sql','0014_contact_personalisation.sql']) await db.exec(fs.readFileSync(path.join(root,filename),'utf8'));
    const fixtures=JSON.parse(fs.readFileSync(path.join(root,'isolation-fixtures.json'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'0016_campaign_attribution.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'0017_automatic_reply_drafts.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'0018_standing_reply_policy.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'0019_qualification_evidence.sql'),'utf8'));
    fixtures.tenants.forEach((tenant,index)=>fixtures.rows.push({table:'reply_policies',values:{id:'policy-'+index,created_at:1,organization_id:tenant.organization_id,brand_id:fixtures.rows.find(row=>row.table==='brands'&&row.values.organization_id===tenant.organization_id).values.id,owner_id:tenant.user_id,brand_hash:'a'.repeat(64),template_hash:'b'.repeat(64),expires_at:9999999999}}));
    fixtures.tenants.forEach((tenant,index)=>fixtures.rows.push({table:'attribution_touches',values:{id:'touch-'+index,created_at:1,organization_id:tenant.organization_id,lead_id:fixtures.rows.find(row=>row.table==='leads'&&row.values.organization_id===tenant.organization_id).values.id,campaign_id:fixtures.rows.find(row=>row.table==='campaigns'&&row.values.organization_id===tenant.organization_id).values.id,channel:'email',evidence:'synthetic fixture',occurred_at:1,simulated:true,idempotency_key:'touch-key-'+index}}));
    fixtures.tenants.forEach((tenant,index)=>fixtures.rows.push({table:'model_cache',values:{id:'cache-'+index,created_at:1,organization_id:tenant.organization_id,cache_key:'cache-key-'+index,model_id:'fixture',source_usage_id:fixtures.rows.find(row=>row.table==='model_usage'&&row.values.organization_id===tenant.organization_id).values.id,output:'{}',expires_at:9999999999}}));
    fixtures.tenants.forEach((tenant,index)=>fixtures.rows.push({table:'provider_events',values:{id:'provider-event-'+index,created_at:1,organization_id:tenant.organization_id,provider:'stripe',event_id:'event-'+index,kind:'test',object_ref:'object-'+index,occurred_at:1,amount_minor:0,currency:'USD',simulated:true,evidence:'{}'}}));
    for (const row of fixtures.rows) {
      const columns=Object.keys(row.values);
      await db.query(`INSERT INTO ${row.table} (${columns.join(',')}) VALUES (${columns.map((_,i)=>'$'+(i+1)).join(',')})`,Object.values(row.values));
    }
    const policies=(await db.query("SELECT tablename FROM pg_tables WHERE schemaname='public' AND rowsecurity ORDER BY tablename")).rows;
    assert.equal(policies.length,42);
    const flags=(await db.query("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname='ai_mos_app'")).rows[0];
    assert.equal(flags.rolsuper,false);assert.equal(flags.rolbypassrls,false);
    await db.exec('SET ROLE ai_mos_app');
    for (const table of policies) {
      assert.equal((await db.query(`SELECT count(*)::int AS count FROM ${table.tablename}`)).rows[0].count,0,`${table.tablename}: missing context exposes data`);
    }
    for (const tenant of fixtures.tenants) {
      await db.query("SELECT set_config('app.current_org',$1,false),set_config('app.current_user',$2,false)",[tenant.organization_id,tenant.user_id]);
      for (const table of policies) {
        const visible=(await db.query(`SELECT organization_id FROM ${table.tablename}`)).rows;
        assert.equal(visible.length,1,`${table.tablename}: expected one tenant row`);
        assert.equal(visible[0].organization_id,tenant.organization_id);
      }
    }
    const orgA=fixtures.organizations[0],orgB=fixtures.organizations[1];
    await db.query("SELECT set_config('app.current_org',$1,false),set_config('app.current_user',$2,false)",[orgA,fixtures.tenants[0].user_id]);
    await assert.rejects(db.query("INSERT INTO brands(id,name,website,positioning,icp,voice,pricing,approved_claims,prohibited_claims) VALUES('missing-tenant','Missing','','','{}','{}','{}','[]','[]')"));
    await assert.rejects(db.query("INSERT INTO brands(id,organization_id,name,website,positioning,icp,voice,pricing,approved_claims,prohibited_claims) VALUES('forged-tenant',$1,'Forged','','','{}','{}','{}','[]','[]')",[orgB]));
    const otherBrand=fixtures.rows.find(row=>row.table==='brands'&&row.values.organization_id===orgB).values.id;
    await assert.rejects(db.query("INSERT INTO brand_documents(id,organization_id,brand_id,title,source_uri,checksum,status) VALUES('bad-fk',$1,$2,'Bad','test','unique-checksum','indexed')",[orgA,otherBrand]));
    await assert.rejects(db.exec("UPDATE payments SET amount_minor=0"));
    await assert.rejects(db.exec("DELETE FROM audit_logs"));
    await assert.rejects(db.exec("UPDATE provider_events SET amount_minor=1"));
    await db.query("UPDATE brand_chunks SET embedding_model='fixture',embedding_vector='[1,0]'");
    const nearest=(await db.query("SELECT organization_id,1-(embedding_vector <=> '[1,0]') AS score FROM brand_chunks WHERE organization_id=$1 ORDER BY embedding_vector <=> '[1,0]'",[orgA])).rows;
    assert.equal(nearest.length,1);assert.equal(nearest[0].organization_id,orgA);assert.equal(nearest[0].score,1);
  } finally {await db.close();}
});

