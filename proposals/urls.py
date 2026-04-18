from django.urls import path

from . import views

app_name = "proposals"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inbox/", views.inbox, name="inbox"),
    path("new/", views.proposal_create, name="create"),
    path("new/from-template/<int:template_pk>/", views.proposal_create_from_template, name="create_from_template"),
    path("<int:pk>/", views.proposal_detail, name="detail"),
    path("<int:pk>/edit/general/", views.proposal_edit_general, name="edit_general"),
    path("<int:pk>/edit/casing/", views.proposal_edit_casing, name="edit_casing"),
    path("<int:pk>/edit/tubing/", views.proposal_edit_tubing, name="edit_tubing"),
    path("<int:pk>/edit/completion/", views.proposal_edit_completion, name="edit_completion"),
    path("<int:pk>/edit/rates/", views.proposal_edit_rates, name="edit_rates"),
    path("<int:pk>/edit/markers/", views.proposal_edit_markers, name="edit_markers"),
    path(
        "<int:pk>/casing/<int:section_id>/activities/",
        views.casing_activities,
        name="casing_activities",
    ),
    path(
        "<int:pk>/casing/<int:section_id>/apply-template/",
        views.apply_section_template,
        name="apply_section_template",
    ),
    path(
        "<int:pk>/phase/<str:phase>/",
        views.phase_activities,
        name="phase_activities",
    ),
    path(
        "<int:pk>/phase/<str:phase>/apply-template/",
        views.apply_phase_template,
        name="apply_phase_template",
    ),
    path("<int:pk>/action/", views.proposal_action, name="action"),
    # HTMX endpoints for cascading dropdowns
    path("api/l2/", views.api_l2_options, name="api_l2"),
    path("api/activities/", views.api_activity_options, name="api_activities"),
]
