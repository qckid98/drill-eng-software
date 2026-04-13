from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ENGINEER = "ENGINEER", "Drilling Engineer"
    SUPERVISOR = "SUPERVISOR", "Drilling Supervisor"
    MANAGEMENT = "MANAGEMENT", "Management"
    ADMIN = "ADMIN", "Administrator"


class User(AbstractUser):
    """Custom user with a single role field driving the approval workflow."""

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.ENGINEER,
    )
    full_name = models.CharField(max_length=150, blank=True)
    position = models.CharField(max_length=150, blank=True, help_text="Job title, e.g. Drilling Engineer III")

    def __str__(self):
        return self.full_name or self.username

    # ---- convenience role predicates (used in templates & views) ----
    @property
    def is_engineer(self) -> bool:
        return self.role == Role.ENGINEER

    @property
    def is_supervisor(self) -> bool:
        return self.role == Role.SUPERVISOR

    @property
    def is_management(self) -> bool:
        return self.role == Role.MANAGEMENT

    @property
    def is_admin_role(self) -> bool:
        return self.role == Role.ADMIN or self.is_superuser
