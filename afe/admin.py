from django.contrib import admin

from .models import AFE, AFEApprovalLog, AFELine, AFELineComponent, AFETemplate, RateCardItem, RateCardImportLog


@admin.register(AFETemplate)
class AFETemplateAdmin(admin.ModelAdmin):
    list_display = ("line_code", "name", "category", "section", "calc_method", "is_subtotal_row", "order")
    list_filter = ("category", "section", "calc_method", "is_subtotal_row")
    search_fields = ("line_code", "name")
    ordering = ("order",)


@admin.register(RateCardItem)
class RateCardItemAdmin(admin.ModelAdmin):
    list_display = ("code", "description", "unit_price_usd", "unit_of_measure", "afe_line", "phase_flag", "source_sheet", "effective_from")
    list_filter = ("phase_flag", "source_sheet", "afe_line", "material_type")
    search_fields = ("code", "description")
    autocomplete_fields = ("afe_line",)


class AFELineComponentInline(admin.TabularInline):
    model = AFELineComponent
    extra = 0
    fields = ("description", "quantity", "unit_of_measure", "unit_price_usd", "total_usd",
              "material_type", "material_category", "phase_flag")
    readonly_fields = ("total_usd",)


class AFELineInline(admin.TabularInline):
    model = AFELine
    extra = 0
    readonly_fields = ("template", "calculated_usd", "unit_price_usd", "quantity")
    fields = ("template", "quantity", "unit_price_usd", "calculated_usd", "override_usd", "notes")
    show_change_link = True


@admin.register(AFE)
class AFEAdmin(admin.ModelAdmin):
    list_display = ("doc_number", "proposal", "version", "status",
                    "grand_total_usd", "contingency_percent", "created_at")
    list_filter = ("status",)
    search_fields = ("doc_number", "proposal__doc_number", "title")
    inlines = [AFELineInline]
    readonly_fields = ("doc_number", "total_tangible_usd", "total_intangible_usd",
                       "contingency_amount_usd", "grand_total_usd",
                       "cost_per_meter_usd", "cost_per_day_usd")


@admin.register(AFELine)
class AFELineAdmin(admin.ModelAdmin):
    list_display = ("afe", "template", "quantity", "unit_price_usd", "calculated_usd", "override_usd")
    list_filter = ("template__section", "template__category")
    inlines = [AFELineComponentInline]


@admin.register(AFEApprovalLog)
class AFEApprovalLogAdmin(admin.ModelAdmin):
    list_display = ("afe", "action", "actor", "from_status", "to_status", "timestamp")
    list_filter = ("action",)
    readonly_fields = ("afe", "actor", "action", "from_status", "to_status", "comment", "timestamp")


@admin.register(RateCardImportLog)
class RateCardImportLogAdmin(admin.ModelAdmin):
    list_display = ("uploaded_at", "uploaded_by", "file_name", "items_created", "items_updated")
    readonly_fields = ("uploaded_at", "uploaded_by", "file_name", "items_created", "items_updated", "notes")
