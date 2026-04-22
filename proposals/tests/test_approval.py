"""
Tests for proposals.services.approval — proposal approval state machine.

Covers:
- Happy path: DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED
- Error cases: wrong role, wrong status
- Revision and rejection flows
- Audit trail (ApprovalLog) creation
"""
from django.test import TestCase

from accounts.models import Role, User
from masterdata.models import (
    ActivityCategoryL1,
    ActivityCategoryL2,
    DrillingActivity,
    HoleSection,
    PhaseType,
)
from proposals.models import (
    ApprovalLog,
    CasingSection,
    Proposal,
    ProposalActivity,
    ProposalStatus,
)
from proposals.services.approval import (
    ApprovalError,
    approve,
    forward,
    reject,
    request_revision,
    submit,
)
from wells.models import Well


class ApprovalTestMixin:
    """Shared fixtures for approval tests."""

    @classmethod
    def setUpTestData(cls):
        cls.engineer = User.objects.create_user(
            username="eng", password="pass", role=Role.ENGINEER,
        )
        cls.supervisor = User.objects.create_user(
            username="sup", password="pass", role=Role.SUPERVISOR,
        )
        cls.manager = User.objects.create_user(
            username="mgr", password="pass", role=Role.MANAGEMENT,
        )
        cls.well = Well.objects.create(name="APPROVAL-WELL", location="LOC")
        cls.hole = HoleSection.objects.create(
            size_inch="12.250", label='12.25"',
        )
        l1 = ActivityCategoryL1.objects.create(name="L1-Test")
        l2 = ActivityCategoryL2.objects.create(parent=l1, name="L2-Test")
        cls.activity = DrillingActivity.objects.create(
            category_l2=l2, description="Test drill",
            default_hours=24, phase_type=PhaseType.DRILLING,
        )

    def _make_proposal(self, status=ProposalStatus.DRAFT):
        p = Proposal.objects.create(
            well=self.well, created_by=self.engineer, status=status,
        )
        section = CasingSection.objects.create(
            proposal=p, hole_section=self.hole,
            depth_m=500, order=1,
        )
        ProposalActivity.objects.create(
            casing_section=section, activity=self.activity, order=1,
        )
        return p


class TestSubmit(ApprovalTestMixin, TestCase):

    def test_engineer_can_submit_draft(self):
        p = self._make_proposal(ProposalStatus.DRAFT)
        submit(p, self.engineer)
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.SUBMITTED)
        self.assertIsNotNone(p.submitted_at)

    def test_submit_creates_audit_log(self):
        p = self._make_proposal(ProposalStatus.DRAFT)
        submit(p, self.engineer)
        log = ApprovalLog.objects.filter(proposal=p).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, ProposalStatus.DRAFT)
        self.assertEqual(log.to_status, ProposalStatus.SUBMITTED)

    def test_supervisor_cannot_submit(self):
        p = self._make_proposal(ProposalStatus.DRAFT)
        with self.assertRaises(ApprovalError):
            submit(p, self.supervisor)

    def test_cannot_submit_without_sections(self):
        p = Proposal.objects.create(
            well=self.well, created_by=self.engineer,
            status=ProposalStatus.DRAFT,
        )
        with self.assertRaises(ApprovalError):
            submit(p, self.engineer)

    def test_cannot_submit_already_submitted(self):
        p = self._make_proposal(ProposalStatus.SUBMITTED)
        with self.assertRaises(ApprovalError):
            submit(p, self.engineer)


class TestForward(ApprovalTestMixin, TestCase):

    def test_supervisor_can_forward(self):
        p = self._make_proposal(ProposalStatus.SUBMITTED)
        forward(p, self.supervisor)
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.UNDER_REVIEW)

    def test_engineer_cannot_forward(self):
        p = self._make_proposal(ProposalStatus.SUBMITTED)
        with self.assertRaises(ApprovalError):
            forward(p, self.engineer)

    def test_cannot_forward_draft(self):
        p = self._make_proposal(ProposalStatus.DRAFT)
        with self.assertRaises(ApprovalError):
            forward(p, self.supervisor)


class TestApproveReject(ApprovalTestMixin, TestCase):

    def test_manager_can_approve(self):
        p = self._make_proposal(ProposalStatus.UNDER_REVIEW)
        approve(p, self.manager)
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.APPROVED)
        self.assertIsNotNone(p.approved_at)

    def test_manager_can_reject(self):
        p = self._make_proposal(ProposalStatus.UNDER_REVIEW)
        reject(p, self.manager)
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.REJECTED)

    def test_engineer_cannot_approve(self):
        p = self._make_proposal(ProposalStatus.UNDER_REVIEW)
        with self.assertRaises(ApprovalError):
            approve(p, self.engineer)

    def test_cannot_approve_draft(self):
        p = self._make_proposal(ProposalStatus.DRAFT)
        with self.assertRaises(ApprovalError):
            approve(p, self.manager)


class TestRevision(ApprovalTestMixin, TestCase):

    def test_supervisor_can_request_revision_on_submitted(self):
        p = self._make_proposal(ProposalStatus.SUBMITTED)
        request_revision(p, self.supervisor, comment="Perlu perbaikan")
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.REVISION)

    def test_manager_can_request_revision_on_under_review(self):
        p = self._make_proposal(ProposalStatus.UNDER_REVIEW)
        request_revision(p, self.manager)
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.REVISION)

    def test_engineer_cannot_request_revision(self):
        p = self._make_proposal(ProposalStatus.SUBMITTED)
        with self.assertRaises(ApprovalError):
            request_revision(p, self.engineer)

    def test_can_resubmit_after_revision(self):
        p = self._make_proposal(ProposalStatus.REVISION)
        submit(p, self.engineer)
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.SUBMITTED)


class TestFullWorkflow(ApprovalTestMixin, TestCase):
    """End-to-end: DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED."""

    def test_happy_path(self):
        p = self._make_proposal(ProposalStatus.DRAFT)

        submit(p, self.engineer)
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.SUBMITTED)

        forward(p, self.supervisor)
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.UNDER_REVIEW)

        approve(p, self.manager)
        p.refresh_from_db()
        self.assertEqual(p.status, ProposalStatus.APPROVED)

        # Should have 3 audit log entries
        self.assertEqual(ApprovalLog.objects.filter(proposal=p).count(), 3)
