from django.urls import path

from . import views

app_name = "proposals"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inbox/", views.inbox, name="inbox"),
    path("new/", views.proposal_create, name="create"),
    path("<int:pk>/", views.proposal_detail, name="detail"),
    path("<int:pk>/edit/general/", views.proposal_edit_general, name="edit_general"),
    path("<int:pk>/edit/casing/", views.proposal_edit_casing, name="edit_casing"),
    path("<int:pk>/edit/tubing/", views.proposal_edit_tubing, name="edit_tubing"),
    path("<int:pk>/edit/completion/", views.proposal_edit_completion, name="edit_completion"),
    path(
        "<int:pk>/casing/<int:section_id>/activities/",
        views.casing_activities,
        name="casing_activities",
    ),
    path("<int:pk>/action/", views.proposal_action, name="action"),
    # HTMX endpoints for cascading dropdowns
    path("api/l2/", views.api_l2_options, name="api_l2"),
    path("api/activities/", views.api_activity_options, name="api_activities"),
]
