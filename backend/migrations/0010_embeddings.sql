ALTER TABLE brand_chunks ADD COLUMN embedding json NOT NULL DEFAULT '[]';
ALTER TABLE brand_chunks ADD COLUMN embedding_model varchar(200) NOT NULL DEFAULT '';
