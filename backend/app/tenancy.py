from sqlalchemy import event, text
from sqlalchemy.orm import Session


@event.listens_for(Session, "after_begin")
def apply_transaction_scope(session, transaction, connection):
    if connection.dialect.name != "postgresql":
        return
    for setting, key in [
        ("app.current_org", "organization_id"),
        ("app.current_user", "user_id"),
        ("app.session_hash", "session_hash"),
    ]:
        connection.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": setting, "value": session.info.get(key, "")},
        )


async def tenant_scope(session, organization_id=None, user_id=None, session_hash=None):
    updates = {
        key: value
        for key, value in {
            "organization_id": organization_id,
            "user_id": user_id,
            "session_hash": session_hash,
        }.items()
        if value is not None
    }
    session.info.update(updates)
    if session.bind.dialect.name == "postgresql":
        for setting, key in [
            ("app.current_org", "organization_id"),
            ("app.current_user", "user_id"),
            ("app.session_hash", "session_hash"),
        ]:
            if key in updates:
                await session.execute(
                    text("SELECT set_config(:setting, :value, true)"),
                    {"setting": setting, "value": updates[key]},
                )
