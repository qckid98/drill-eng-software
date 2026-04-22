"""
Tests for afe.services.calc — AFE calculation engine.

Covers:
- recalculate_afe() tangible/intangible roll-up
- Contingency calculation
- Cost per meter / cost per day KPIs
- Signal disconnect during generate (no 58x recalculate)
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounts.models import Role, User
from afe.models import (
    AFE,
    AFECategory,
    AFELine,
    AFETemplate,
    CalcMethod,
    RateCardItem,
)
from afe.services.calc import recalculate_afe
from proposals.models import CasingSection, Proposal, ProposalStatus
from masterdata.models import HoleSection
from wells.models import Well


class AFECalcTestMixin:
    """Shared fixtures for AFE calc tests."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="afe_calc_eng", password="pass", role=Role.ENGINEER,
        )
        cls.well = Well.objects.create(name="CALC-WELL", location="LOC")
        cls.hole = HoleSection.objects.create(
            size_inch=Decimal("12.250"), label='12.25"',
        )
        cls.proposal = Proposal.objects.create(
            well=cls.well, created_by=cls.user,
            status=ProposalStatus.APPROVED,
            total_rig_days=Decimal("30"),
            total_dryhole_days=Decimal("20"),
            total_completion_days=Decimal("10"),
            mob_days=Decimal("3"), demob_days=Decimal("2"),
        )
        CasingSection.objects.create(
            proposal=cls.proposal, hole_section=cls.hole,
            depth_m=Decimal("2000"), order=1,
        )

        # Create templates
        cls.tpl_tangible = AFETemplate.objects.create(
            line_code="C01", name="Tangible Item",
            category=AFECategory.TANGIBLE, section="TANGIBLE",
            calc_method=CalcMethod.LUMP_SUM, order=1,
        )
        cls.tpl_intangible = AFETemplate.objects.create(
            line_code="C02", name="Intangible Item",
            category=AFECategory.INTANGIBLE, section="DRILLING",
            calc_method=CalcMethod.LUMP_SUM, order=2,
        )
        cls.tpl_subtotal = AFETemplate.objects.create(
            line_code="C03", name="Subtotal Row",
            category=AFECategory.TANGIBLE, section="TANGIBLE",
            calc_method=CalcMethod.MANUAL, is_subtotal_row=True, order=3,
        )


class TestRecalculateAFE(AFECalcTestMixin, TestCase):

    def _make_afe_with_lines(self, contingency=Decimal("0")):
        afe = AFE.objects.create(
            proposal=self.proposal, created_by=self.user,
            contingency_percent=contingency,
        )
        # Tangible line: $50,000
        AFELine.objects.create(
            afe=afe, template=self.tpl_tangible,
            calculated_usd=Decimal("50000"),
        )
        # Intangible line: $30,000
        AFELine.objects.create(
            afe=afe, template=self.tpl_intangible,
            calculated_usd=Decimal("30000"),
        )
        # Subtotal row: should be ignored
        AFELine.objects.create(
            afe=afe, template=self.tpl_subtotal,
            calculated_usd=Decimal("0"),
        )
        return afe

    def test_tangible_intangible_split(self):
        """Tangible and intangible totals are summed separately."""
        afe = self._make_afe_with_lines()
        recalculate_afe(afe)
        afe.refresh_from_db()
        self.assertEqual(afe.total_tangible_usd, Decimal("50000.00"))
        self.assertEqual(afe.total_intangible_usd, Decimal("30000.00"))

    def test_grand_total_without_contingency(self):
        """Grand total = tangible + intangible when contingency is 0%."""
        afe = self._make_afe_with_lines(contingency=Decimal("0"))
        recalculate_afe(afe)
        afe.refresh_from_db()
        self.assertEqual(afe.grand_total_usd, Decimal("80000.00"))
        self.assertEqual(afe.contingency_amount_usd, Decimal("0.00"))

    def test_grand_total_with_contingency(self):
        """Grand total = base + (base × contingency%)."""
        afe = self._make_afe_with_lines(contingency=Decimal("10"))
        recalculate_afe(afe)
        afe.refresh_from_db()
        # base = 80000, contingency = 80000 * 10% = 8000
        self.assertEqual(afe.contingency_amount_usd, Decimal("8000.00"))
        self.assertEqual(afe.grand_total_usd, Decimal("88000.00"))

    def test_cost_per_meter(self):
        """cost_per_meter = grand_total / max_depth."""
        afe = self._make_afe_with_lines(contingency=Decimal("0"))
        recalculate_afe(afe)
        afe.refresh_from_db()
        # 80000 / 2000m = 40.00
        self.assertEqual(afe.cost_per_meter_usd, Decimal("40.00"))

    def test_cost_per_day(self):
        """cost_per_day = grand_total / rig_days."""
        afe = self._make_afe_with_lines(contingency=Decimal("0"))
        recalculate_afe(afe)
        afe.refresh_from_db()
        # rig_days from ProposalDrivers = proposal.total_rig_days
        # After signal recalc: 0 section days + 3 mob + 2 demob = 5
        # 80000 / 5 = 16000.00
        self.assertEqual(afe.cost_per_day_usd, Decimal("16000.00"))

    def test_subtotal_rows_excluded(self):
        """Subtotal rows should not contribute to tangible/intangible sums."""
        afe = self._make_afe_with_lines()
        # Manually set subtotal row to a non-zero value
        subtotal_line = AFELine.objects.get(afe=afe, template=self.tpl_subtotal)
        subtotal_line.calculated_usd = Decimal("99999")
        subtotal_line.save()

        recalculate_afe(afe)
        afe.refresh_from_db()
        # Should still be 50000 + 30000, not including 99999
        self.assertEqual(afe.grand_total_usd, Decimal("80000.00"))

    def test_override_usd_takes_precedence(self):
        """When override_usd is set, it should be used instead of calculated_usd."""
        afe = self._make_afe_with_lines()
        tangible_line = AFELine.objects.get(afe=afe, template=self.tpl_tangible)
        tangible_line.override_usd = Decimal("75000")
        tangible_line.save()

        recalculate_afe(afe)
        afe.refresh_from_db()
        # 75000 (override) + 30000 = 105000
        self.assertEqual(afe.total_tangible_usd, Decimal("75000.00"))
        self.assertEqual(afe.grand_total_usd, Decimal("105000.00"))


class TestGenerateSignalDisconnect(AFECalcTestMixin, TestCase):
    """Verify that generate_afe_from_proposal disconnects signals."""

    def test_recalculate_not_called_per_line(self):
        """During generation, recalculate_afe should be called once, not 58 times."""
        afe = AFE.objects.create(
            proposal=self.proposal, created_by=self.user,
        )
        with patch("afe.services.calc.recalculate_afe") as mock_recalc:
            from afe.services.calc import generate_afe_from_proposal
            # Unpatch for the final call inside generate
            mock_recalc.side_effect = lambda a: None
            generate_afe_from_proposal(afe)
            # Should be called exactly once (at the end of generate)
            self.assertEqual(mock_recalc.call_count, 1)
