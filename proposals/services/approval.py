"""State machine for the Drilling Proposal approval workflow."""

from django.utils import timezone

from ..models import ApprovalAction, ApprovalLog, Proposal, ProposalStatus


class ApprovalError(Exception):
    """Raised when a user tries to perform an action that is not allowed."""


def _log(proposal, actor, action, from_status, to_status, comment=""):
    ApprovalLog.objects.create(
        proposal=proposal,
        actor=actor,
        action=action,
        from_status=from_status,
        to_status=to_status,
        comment=comment,
    )


def submit(proposal: Proposal, actor, comment: str = "") -> None:
    if not proposal.can_submit(actor):
        raise ApprovalError("Anda tidak dapat submit proposal ini saat status/role saat ini.")
    if not proposal.casing_sections.exists():
        raise ApprovalError("Proposal harus memiliki minimal 1 casing section sebelum submit.")

    from_status = proposal.status
    proposal.status = ProposalStatus.SUBMITTED
    proposal.submitted_at = timezone.now()
    proposal.save(update_fields=["status", "submitted_at"])
    _log(proposal, actor, ApprovalAction.SUBMIT, from_status, proposal.status, comment)


def forward(proposal: Proposal, actor, comment: str = "") -> None:
    if not proposal.can_review(actor):
        raise ApprovalError("Hanya Supervisor yang dapat meneruskan proposal ke management.")
    from_status = proposal.status
    proposal.status = ProposalStatus.UNDER_REVIEW
    proposal.reviewed_at = timezone.now()
    proposal.save(update_fields=["status", "reviewed_at"])
    _log(proposal, actor, ApprovalAction.FORWARD, from_status, proposal.status, comment)


def request_revision(proposal: Proposal, actor, comment: str = "") -> None:
    if proposal.status not in (ProposalStatus.SUBMITTED, ProposalStatus.UNDER_REVIEW):
        raise ApprovalError("Revisi hanya bisa diminta untuk proposal yang sudah disubmit.")
    if not (actor.is_supervisor or actor.is_management):
        raise ApprovalError("Anda tidak berwenang meminta revisi.")
    from_status = proposal.status
    proposal.status = ProposalStatus.REVISION
    proposal.save(update_fields=["status"])
    _log(proposal, actor, ApprovalAction.REQUEST_REVISION, from_status, proposal.status, comment)


def approve(proposal: Proposal, actor, comment: str = "") -> None:
    if not proposal.can_approve(actor):
        raise ApprovalError("Hanya Management yang dapat menyetujui proposal yang sedang di-review.")
    from_status = proposal.status
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = timezone.now()
    proposal.save(update_fields=["status", "approved_at"])
    _log(proposal, actor, ApprovalAction.APPROVE, from_status, proposal.status, comment)


def reject(proposal: Proposal, actor, comment: str = "") -> None:
    if not proposal.can_approve(actor):
        raise ApprovalError("Hanya Management yang dapat menolak proposal yang sedang di-review.")
    from_status = proposal.status
    proposal.status = ProposalStatus.REJECTED
    proposal.save(update_fields=["status"])
    _log(proposal, actor, ApprovalAction.REJECT, from_status, proposal.status, comment)
