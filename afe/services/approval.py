"""State machine for AFE approval workflow.

Mirrors `proposals.services.approval` but operates on the AFE model.
"""
from django.utils import timezone

from ..models import AFE, AFEApprovalLog, AFEStatus


class ApprovalError(Exception):
    """Raised when a user action is not permitted by the state machine."""


def _log(afe: AFE, actor, action: str, from_status: str, to_status: str, comment: str = "") -> None:
    AFEApprovalLog.objects.create(
        afe=afe,
        actor=actor,
        action=action,
        from_status=from_status,
        to_status=to_status,
        comment=comment,
    )


def submit(afe: AFE, actor, comment: str = "") -> None:
    if not afe.can_submit(actor):
        raise ApprovalError("Anda tidak dapat submit AFE ini pada status/role saat ini.")
    if not afe.lines.exists():
        raise ApprovalError("AFE harus memiliki baris cost sebelum disubmit.")
    if (afe.grand_total_usd or 0) <= 0:
        raise ApprovalError("Grand total AFE masih 0. Isi / generate ulang dari rate card dahulu.")

    from_status = afe.status
    afe.status = AFEStatus.SUBMITTED
    afe.submitted_at = timezone.now()
    afe.save(update_fields=["status", "submitted_at"])
    _log(afe, actor, "submit", from_status, afe.status, comment)


def forward(afe: AFE, actor, comment: str = "") -> None:
    if not afe.can_review(actor):
        raise ApprovalError("Hanya Supervisor yang dapat meneruskan AFE ke management.")
    from_status = afe.status
    afe.status = AFEStatus.UNDER_REVIEW
    afe.reviewed_at = timezone.now()
    afe.save(update_fields=["status", "reviewed_at"])
    _log(afe, actor, "forward", from_status, afe.status, comment)


def request_revision(afe: AFE, actor, comment: str = "") -> None:
    if afe.status not in (AFEStatus.SUBMITTED, AFEStatus.UNDER_REVIEW):
        raise ApprovalError("Revisi hanya bisa diminta untuk AFE yang sudah disubmit.")
    if not (getattr(actor, "is_supervisor", False) or getattr(actor, "is_management", False)):
        raise ApprovalError("Anda tidak berwenang meminta revisi AFE.")
    from_status = afe.status
    afe.status = AFEStatus.REVISION
    afe.save(update_fields=["status"])
    _log(afe, actor, "request_revision", from_status, afe.status, comment)


def approve(afe: AFE, actor, comment: str = "") -> None:
    if not afe.can_approve(actor):
        raise ApprovalError("Hanya Management yang dapat menyetujui AFE yang sedang di-review.")
    from_status = afe.status
    afe.status = AFEStatus.APPROVED
    afe.approved_at = timezone.now()
    afe.save(update_fields=["status", "approved_at"])
    _log(afe, actor, "approve", from_status, afe.status, comment)


def reject(afe: AFE, actor, comment: str = "") -> None:
    if not afe.can_approve(actor):
        raise ApprovalError("Hanya Management yang dapat menolak AFE yang sedang di-review.")
    from_status = afe.status
    afe.status = AFEStatus.REJECTED
    afe.save(update_fields=["status"])
    _log(afe, actor, "reject", from_status, afe.status, comment)
