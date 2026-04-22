"""
Tests for proposals.services.calc — drilling time calculation engine.

Covers:
- Section-level totals (drilling/non-drilling/completion days, rate)
- Proposal-level totals (dryhole, completion, rig days)
- Edge cases: zero hours, missing activities, safe division
"""
from decimal import Decimal

from django.test import TestCase

from accounts.models import Role, User
from masterdata.models import (
    ActivityCategoryL1,
    ActivityCategoryL2,
    DrillingActivity,
    HoleSection,
    PhaseType,
)
from proposals.models import CasingSection, Proposal, ProposalActivity
from proposals.services.calc import (
    calculate_proposal_totals,
    calculate_section_totals,
    recalculate_proposal,
    recalculate_section,
)
from wells.models import Well


class CalcTestMixin:
    """Shared helpers for creating test fixtures."""

    @classmethod
    def _create_user(cls):
        return User.objects.create_user(
            username="eng_test", password="pass", role=Role.ENGINEER,
        )

    @classmethod
    def _create_well(cls):
        return Well.objects.create(name="TEST-WELL-1", location="LOC-1")

    @classmethod
    def _create_hole_section(cls, size=Decimal("12.250"), label='12.25"'):
        return HoleSection.objects.create(size_inch=size, label=label)

    @classmethod
    def _create_activity(cls, phase_type=PhaseType.DRILLING, hours=Decimal("24")):
        l1 = ActivityCategoryL1.objects.create(name=f"L1-{phase_type}")
        l2 = ActivityCategoryL2.objects.create(parent=l1, name=f"L2-{phase_type}")
        return DrillingActivity.objects.create(
            category_l2=l2,
            description=f"Test activity ({phase_type})",
            default_hours=hours,
            phase_type=phase_type,
        )


class TestCalculateSectionTotals(CalcTestMixin, TestCase):
    """Test calculate_section_totals()."""

    def setUp(self):
        self.user = self._create_user()
        self.well = self._create_well()
        self.hole = self._create_hole_section()
        self.proposal = Proposal.objects.create(
            well=self.well, created_by=self.user,
        )
        self.section = CasingSection.objects.create(
            proposal=self.proposal, hole_section=self.hole,
            depth_m=Decimal("500"), order=1,
        )

    def test_empty_section_returns_zeros(self):
        """Section with no activities should have all-zero totals."""
        totals = calculate_section_totals(self.section)
        self.assertEqual(totals.drilling_days, Decimal("0"))
        self.assertEqual(totals.non_drilling_days, Decimal("0"))
        self.assertEqual(totals.completion_days, Decimal("0"))
        self.assertEqual(totals.total_days, Decimal("0"))
        self.assertEqual(totals.drilling_rate_m_per_day, Decimal("0"))

    def test_drilling_hours_converted_to_days(self):
        """24 drilling hours = 1 drilling day."""
        act = self._create_activity(PhaseType.DRILLING, hours=Decimal("24"))
        ProposalActivity.objects.create(
            casing_section=self.section, activity=act, order=1,
        )
        totals = calculate_section_totals(self.section)
        self.assertEqual(totals.drilling_days, Decimal("1.000"))
        self.assertEqual(totals.non_drilling_days, Decimal("0.000"))
        self.assertEqual(totals.total_days, Decimal("1.000"))

    def test_mixed_phase_types(self):
        """Activities of different phase types are summed separately."""
        drill_act = self._create_activity(PhaseType.DRILLING, hours=Decimal("48"))
        non_drill_act = self._create_activity(PhaseType.NON_DRILLING, hours=Decimal("12"))
        comp_act = self._create_activity(PhaseType.COMPLETION, hours=Decimal("6"))

        ProposalActivity.objects.create(
            casing_section=self.section, activity=drill_act, order=1,
        )
        ProposalActivity.objects.create(
            casing_section=self.section, activity=non_drill_act, order=2,
        )
        ProposalActivity.objects.create(
            casing_section=self.section, activity=comp_act, order=3,
        )

        totals = calculate_section_totals(self.section)
        self.assertEqual(totals.drilling_days, Decimal("2.000"))
        self.assertEqual(totals.non_drilling_days, Decimal("0.500"))
        self.assertEqual(totals.completion_days, Decimal("0.250"))
        self.assertEqual(totals.total_days, Decimal("2.750"))

    def test_hours_override_used_when_set(self):
        """ProposalActivity.hours_override takes precedence over default_hours."""
        act = self._create_activity(PhaseType.DRILLING, hours=Decimal("24"))
        ProposalActivity.objects.create(
            casing_section=self.section, activity=act, order=1,
            hours_override=Decimal("48"),
        )
        totals = calculate_section_totals(self.section)
        self.assertEqual(totals.drilling_days, Decimal("2.000"))

    def test_drilling_rate_calculation(self):
        """drilling_rate_m_per_day = interval_length / drilling_days."""
        # Section at 500m, no previous section → interval = 500m
        act = self._create_activity(PhaseType.DRILLING, hours=Decimal("48"))
        ProposalActivity.objects.create(
            casing_section=self.section, activity=act, order=1,
        )
        totals = calculate_section_totals(self.section)
        # 500m / 2 days = 250 m/day
        self.assertEqual(totals.drilling_rate_m_per_day, Decimal("250.00"))

    def test_drilling_rate_zero_when_no_drilling(self):
        """Rate should be 0 when there are no drilling activities."""
        act = self._create_activity(PhaseType.NON_DRILLING, hours=Decimal("24"))
        ProposalActivity.objects.create(
            casing_section=self.section, activity=act, order=1,
        )
        totals = calculate_section_totals(self.section)
        self.assertEqual(totals.drilling_rate_m_per_day, Decimal("0"))


class TestRecalculateSection(CalcTestMixin, TestCase):
    """Test recalculate_section() persists cached fields."""

    def setUp(self):
        self.user = self._create_user()
        self.well = self._create_well()
        self.hole = self._create_hole_section()
        self.proposal = Proposal.objects.create(
            well=self.well, created_by=self.user,
        )
        self.section = CasingSection.objects.create(
            proposal=self.proposal, hole_section=self.hole,
            depth_m=Decimal("1000"), order=1,
        )

    def test_saves_cached_fields(self):
        """recalculate_section should persist totals to the database."""
        act = self._create_activity(PhaseType.DRILLING, hours=Decimal("72"))
        ProposalActivity.objects.create(
            casing_section=self.section, activity=act, order=1,
        )
        recalculate_section(self.section)

        self.section.refresh_from_db()
        self.assertEqual(self.section.drilling_days, Decimal("3.000"))
        self.assertEqual(self.section.total_days, Decimal("3.000"))


class TestCalculateProposalTotals(CalcTestMixin, TestCase):
    """Test calculate_proposal_totals() and recalculate_proposal()."""

    def setUp(self):
        self.user = self._create_user()
        self.well = self._create_well()
        self.hole1 = self._create_hole_section(Decimal("17.500"), '17.5"')
        self.hole2 = self._create_hole_section(Decimal("12.250"), '12.25"')
        self.proposal = Proposal.objects.create(
            well=self.well, created_by=self.user,
            mob_days=Decimal("3"), demob_days=Decimal("2"),
        )

    def test_sum_based_rig_days(self):
        """total_rig_days = SUM(all section total_days) + mob + demob."""
        drill_act = self._create_activity(PhaseType.DRILLING, hours=Decimal("48"))
        comp_act = self._create_activity(PhaseType.COMPLETION, hours=Decimal("72"))

        # Section 1: dryhole, 48h drilling = 2 days
        s1 = CasingSection.objects.create(
            proposal=self.proposal, hole_section=self.hole1,
            depth_m=Decimal("500"), order=1, is_completion=False,
        )
        ProposalActivity.objects.create(
            casing_section=s1, activity=drill_act, order=1,
        )

        # Section 2: completion, 72h completion = 3 days
        s2 = CasingSection.objects.create(
            proposal=self.proposal, hole_section=self.hole2,
            depth_m=Decimal("1000"), order=2, is_completion=True,
        )
        ProposalActivity.objects.create(
            casing_section=s2, activity=comp_act, order=1,
        )

        # Recalculate to refresh cached fields
        recalculate_proposal(self.proposal)
        totals = calculate_proposal_totals(self.proposal)
        self.assertEqual(totals.total_dryhole_days, Decimal("2.00"))
        self.assertEqual(totals.total_completion_days, Decimal("3.00"))
        # SUM(2 + 3) + 3 mob + 2 demob = 10
        self.assertEqual(totals.total_rig_days, Decimal("10.00"))

    def test_empty_proposal(self):
        """Proposal with no sections should have mob+demob as rig days."""
        totals = calculate_proposal_totals(self.proposal)
        self.assertEqual(totals.total_dryhole_days, Decimal("0.00"))
        self.assertEqual(totals.total_completion_days, Decimal("0.00"))
        # 0 + 3 + 2 = 5
        self.assertEqual(totals.total_rig_days, Decimal("5.00"))

    def test_recalculate_proposal_persists(self):
        """recalculate_proposal should save cached totals to DB."""
        s1 = CasingSection.objects.create(
            proposal=self.proposal, hole_section=self.hole1,
            depth_m=Decimal("500"), order=1, is_completion=False,
        )
        act = self._create_activity(PhaseType.DRILLING, hours=Decimal("48"))
        ProposalActivity.objects.create(
            casing_section=s1, activity=act, order=1,
        )

        recalculate_proposal(self.proposal)
        self.proposal.refresh_from_db()

        # 48h / 24 = 2 days drilling + 3 mob + 2 demob = 7
        self.assertEqual(self.proposal.total_dryhole_days, Decimal("2.00"))
        self.assertEqual(self.proposal.total_rig_days, Decimal("7.00"))
