from django.urls import path

from . import views

app_name = "afe"

urlpatterns = [
    # AFE document CRUD
    path("", views.dashboard, name="dashboard"),
    path("inbox/", views.inbox, name="inbox"),
    path("create/<int:proposal_pk>/", views.afe_create, name="create"),
    path("<int:pk>/", views.afe_detail, name="detail"),
    path("<int:pk>/edit/", views.afe_edit, name="edit"),
    path("<int:pk>/line/<int:line_pk>/components/", views.afe_line_components, name="line_components"),
    path("<int:pk>/regenerate/", views.afe_regenerate, name="regenerate"),
    path("<int:pk>/action/", views.afe_action, name="action"),

    # Rate Card management (Admin + Management only)
    path("rates/", views.rate_card_list, name="rate_card_list"),
    path("rates/create/", views.rate_card_create, name="rate_card_create"),
    path("rates/<int:pk>/edit/", views.rate_card_edit, name="rate_card_edit"),
    path("rates/<int:pk>/delete/", views.rate_card_delete, name="rate_card_delete"),
    path("rates/upload/", views.rate_card_upload, name="rate_card_upload"),
]
