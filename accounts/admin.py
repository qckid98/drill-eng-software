from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "full_name", "role", "position", "is_active")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "full_name", "email")
    fieldsets = UserAdmin.fieldsets + (
        ("Drilling Proposal", {"fields": ("full_name", "position", "role")}),
    )
