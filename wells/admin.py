from django.contrib import admin

from .models import Well


@admin.register(Well)
class WellAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "field", "well_type", "well_category", "created_at")
    list_filter = ("well_type", "well_category", "field")
    search_fields = ("name", "location", "field", "target_formation")
