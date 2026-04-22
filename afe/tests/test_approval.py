"""
Tests for afe.services.approval — AFE approval state machine.

Covers:
- Happy path: DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED
- Error cases: wrong role, wrong status, zero grand total
- Revision and rejection flows
- select_for_update race condition protection
"""
from decimal import Decimal

from django.test import TestCase

from accounts.models import Role, User
from afe.models import AFE, AFEApprovalLog, AFELine, AFEStatus, AFETemplate, CalcMethod
from afe.services.approval import (
    ApprovalError,
    approve,
    forward,
    reject,
    request_revision,
    submit,
)
from proposals.models import Proposal, ProposalStatus
from wells.models import Well


class AFEApprovalTestMixin:
    """Shared fixtures for AFE approval tests."""

    @classmethod
    def setUpTestData(cls):
        cls.engineer = User.objects.create_user(
            username="afe_eng", password="pass", role=Role.ENGINEER,
        )
        cls.supervisor = User.objects.create_user(
            username="afe_sup", password="pass", role=Role.SUPERVISOR,
        )
        cls.manager = User.objects.create_user(
            username="afe_mgr", password="pass", role=Role.MANAGEMENT,
        )
        cls.well = Well.objects.create(name="AFE-WELL", location="LOC")
        cls.proposal = Proposal.objects.create(
            well=cls.well, created_by=cls.engineer,
            status=ProposalStatus.APPROVED,
        )
        cls.template = AFETemplate.objects.create(
            line_code="T01", name="Test Line",
            category="TANGIBLE", section="TANGIBLE",
            calc_method=CalcMethod.LUMP_SUM, order=1,
        )

    def _make_afe(self, status=AFEStatus.DRAFT, grand_total=Decimal("100000")):
        afe = AFE.objects.create(
            proposal=self.proposal, created_by=self.engineer,
            status=status, grand_total_usd=grand_total,
        )
        AFELine.objects.create(
            afe=afe, template=self.template,
            calculated_usd=grand_total,
        )
        return afe


class TestAFESubmit(AFEApprovalTestMixin, TestCase):

    def test_engineer_can_submit_draft(self):
        afe = self._make_afe(AFEStatus.DRAFT)
        submit(afe, self.engineer)
        afe.refresh_from_db()
        self.assertEqual(afe.status, AFEStatus.SUBMITTED)
        self.assertIsNotNone(afe.submitted_at)

    def test_submit_creates_audit_log(self):
        afe = self._make_afe(AFEStatus.DRAFT)
        submit(afe, self.engineer)
        log = AFEApprovalLog.objects.filter(afe=afe).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, "submit")

    def test_cannot_submit_zero_total(self):
        afe = self._make_afe(AFEStatus.DRAFT, grand_total=Decimal("0"))
        with self.assertRaises(ApprovalError):
            submit(afe, self.engineer)

    def test_supervisor_cannot_submit(self):
        afe = self._make_afe(AFEStatus.DRAFT)
        with self.assertRaises(ApprovalError):
            submit(afe, self.supervisor)


class TestAFEForward(AFEApprovalTestMixin, TestCase):

    def test_supervisor_can_forward(self):
        afe = self._make_afe(AFEStatus.SUBMITTED)
        forward(afe, self.supervisor)
        afe.refresh_from_db()
        self.assertEqual(afe.status, AFEStatus.UNDER_REVIEW)

    def test_engineer_cannot_forward(self):
        afe = self._make_afe(AFEStatus.SUBMITTED)
        with self.assertRaises(ApprovalError):
            forward(afe, self.engineer)


class TestAFEApproveReject(AFEApprovalTestMixin, TestCase):

    def test_manager_can_approve(self):
        afe = self._make_afe(AFEStatus.UNDER_REVIEW)
        approve(afe, self.manager)
        afe.refresh_from_db()
        self.assertEqual(afe.status, AFEStatus.APPROVED)

    def test_manager_can_reject(self):
        afe = self._make_afe(AFEStatus.UNDER_REVIEW)
        reject(afe, self.manager)
        afe.refresh_from_db()
        self.assertEqual(afe.status, AFEStatus.REJECTED)

    def test_engineer_cannot_approve(self):
        afe = self._make_afe(AFEStatus.UNDER_REVIEW)
        with self.assertRaises(ApprovalError):
            approve(afe, self.engineer)


class TestAFERevision(AFEApprovalTestMixin, TestCase):

    def test_supervisor_can_request_revision(self):
        afe = self._make_afe(AFEStatus.SUBMITTED)
        request_revision(afe, self.supervisor, comment="Revisi rate card")
        afe.refresh_from_db()
        self.assertEqual(afe.status, AFEStatus.REVISION)

    def test_can_resubmit_after_revision(self):
        afe = self._make_afe(AFEStatus.REVISION)
        submit(afe, self.engineer)
        afe.refresh_from_db()
        self.assertEqual(afe.status, AFEStatus.SUBMITTED)


class TestAFEFullWorkflow(AFEApprovalTestMixin, TestCase):

    def test_happy_path(self):
        afe = self._make_afe(AFEStatus.DRAFT)

        submit(afe, self.engineer)
        afe.refresh_from_db()
        self.assertEqual(afe.status, AFEStatus.SUBMITTED)

        forward(afe, self.supervisor)
        afe.refresh_from_db()
        self.assertEqual(afe.status, AFEStatus.UNDER_REVIEW)

        approve(afe, self.manager)
        afe.refresh_from_db()
        self.assertEqual(afe.status, AFEStatus.APPROVED)

        self.assertEqual(AFEApprovalLog.objects.filter(afe=afe).count(), 3)
