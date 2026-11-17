-- The portable PostgreSQL test path uses exact cosine over JSON vectors.
-- pgvector deployments also receive a native vector column; tenant RLS still applies.
DO $$ BEGIN
  IF EXISTS(SELECT 1 FROM pg_available_extensions WHERE name='vector') THEN
    CREATE EXTENSION IF NOT EXISTS vector;
    ALTER TABLE brand_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector;
  END IF;
END $$;
