from django.contrib import admin

from .models import (
    ActivityCategoryL1,
    ActivityCategoryL2,
    DrillingActivity,
    HoleSection,
    MudType,
    RigSpec,
    RopRate,
)


@admin.register(HoleSection)
class HoleSectionAdmin(admin.ModelAdmin):
    list_display = ("label", "size_inch", "default_od", "default_id", "order")
    ordering = ("-size_inch",)


@admin.register(MudType)
class MudTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


@admin.register(RopRate)
class RopRateAdmin(admin.ModelAdmin):
    list_display = ("hole_section", "start_depth_m", "end_depth_m", "days", "rop_m_per_day")
    list_filter = ("hole_section",)


class ActivityCategoryL2Inline(admin.TabularInline):
    model = ActivityCategoryL2
    extra = 0


@admin.register(ActivityCategoryL1)
class ActivityCategoryL1Admin(admin.ModelAdmin):
    list_display = ("name", "order")
    inlines = [ActivityCategoryL2Inline]


@admin.register(ActivityCategoryL2)
class ActivityCategoryL2Admin(admin.ModelAdmin):
    list_display = ("name", "parent", "order")
    list_filter = ("parent",)
    search_fields = ("name",)


@admin.register(DrillingActivity)
class DrillingActivityAdmin(admin.ModelAdmin):
    list_display = ("code", "description", "category_l2", "default_hours", "phase_type")
    list_filter = ("phase_type", "category_l2__parent")
    search_fields = ("code", "description")
    filter_horizontal = ("applies_to_hole_sections",)


@admin.register(RigSpec)
class RigSpecAdmin(admin.ModelAdmin):
    list_display = ("platform_name", "horsepower", "floor_height_m", "capacity", "status")
    search_fields = ("platform_name",)
