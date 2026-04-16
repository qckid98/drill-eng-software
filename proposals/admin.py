from django.contrib import admin

from .models import (
    ApprovalLog,
    CasingSection,
    CompletionSpec,
    CoringInterval,
    FormationMarker,
    Proposal,
    ProposalActivity,
    TubeLengthRange,
    TubingItem,
)


class CasingSectionInline(admin.TabularInline):
    model = CasingSection
    extra = 0
    fields = (
        "order", "hole_section", "depth_m", "mud_type", "is_completion",
        "drilling_days", "non_drilling_days", "total_days",
    )
    readonly_fields = ("drilling_days", "non_drilling_days", "total_days")


class ProposalActivityInline(admin.TabularInline):
    model = ProposalActivity
    extra = 0
    autocomplete_fields = ("activity",)


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = (
        "doc_number", "well", "status", "total_dryhole_days",
        "total_completion_days", "total_rig_days", "created_by", "created_at",
    )
    list_filter = ("status", "well__field")
    search_fields = ("doc_number", "well__name", "well__location")
    readonly_fields = (
        "doc_number", "total_dryhole_days", "total_completion_days",
        "total_rig_days", "submitted_at", "reviewed_at", "approved_at",
    )
    inlines = [CasingSectionInline]


@admin.register(CasingSection)
class CasingSectionAdmin(admin.ModelAdmin):
    list_display = (
        "proposal", "order", "hole_section", "depth_m", "total_days",
        "drilling_rate_m_per_day",
    )
    list_filter = ("hole_section",)
    inlines = [ProposalActivityInline]


admin.site.register(TubingItem)
admin.site.register(FormationMarker)
admin.site.register(TubeLengthRange)
admin.site.register(CompletionSpec)
admin.site.register(CoringInterval)
admin.site.register(ApprovalLog)
