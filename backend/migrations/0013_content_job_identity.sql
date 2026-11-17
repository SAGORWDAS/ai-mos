ALTER TABLE content_items ADD COLUMN task_id varchar(36) REFERENCES tasks(id);
ALTER TABLE content_items ADD CONSTRAINT content_task_tenant
FOREIGN KEY(organization_id,task_id) REFERENCES tasks(organization_id,id);
CREATE UNIQUE INDEX content_items_task_unique ON content_items(organization_id,task_id);
