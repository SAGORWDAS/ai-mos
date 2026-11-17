from sqlalchemy import select

from app.growth.models import Customer, Lead, Notification, Workflow, WorkflowRun
from app.growth.runtime_helpers import score


async def dispatch(session, org_id, trigger, subject, event_id):
    """Bounded internal event handlers. Actions cannot emit triggers or execute providers."""
    workflows = (
        await session.scalars(
            select(Workflow).where(
                Workflow.organization_id == org_id,
                Workflow.trigger == trigger,
                Workflow.enabled.is_(True),
            )
        )
    ).all()
    runs = []
    for workflow in workflows:
        prior = await session.scalar(
            select(WorkflowRun).where(
                WorkflowRun.organization_id == org_id,
                WorkflowRun.workflow_id == workflow.id,
                WorkflowRun.event_id == event_id,
            )
        )
        if prior:
            runs.append(prior)
            continue
        output = {"subject_id": subject.id, "action": workflow.action, "external_effects": 0}
        state = "succeeded"
        if workflow.action == "score_lead" and isinstance(subject, Lead):
            if subject.status == "suppressed":
                state = "blocked"
                output["reason"] = "suppressed_recipient"
            else:
                subject.score = score(subject)
                subject.status = "qualified" if subject.score >= 65 else "scored"
                output["score"] = subject.score
        elif workflow.action == "notify_owner":
            notification = Notification(
                organization_id=org_id, title=f"{workflow.name}: {trigger}", subject_id=subject.id
            )
            session.add(notification)
            await session.flush()
            output["notification_id"] = notification.id
        elif workflow.action == "onboarding_checklist":
            customer = await session.scalar(
                select(Customer).where(
                    Customer.organization_id == org_id, Customer.lead_id == subject.lead_id
                )
            )
            if customer:
                output["customer_id"] = customer.id
            else:
                state = "blocked"
                output["reason"] = "customer_not_ready"
        else:
            state = "blocked"
            output["reason"] = "incompatible_workflow_action"
        run = WorkflowRun(
            organization_id=org_id,
            workflow_id=workflow.id,
            event_id=event_id,
            status=state,
            output=output,
        )
        session.add(run)
        await session.flush()
        runs.append(run)
    return runs
