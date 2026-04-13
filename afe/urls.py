from django.urls import path

from . import views

app_name = "afe"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inbox/", views.inbox, name="inbox"),
    path("create/<int:proposal_pk>/", views.afe_create, name="create"),
    path("<int:pk>/", views.afe_detail, name="detail"),
    path("<int:pk>/edit/", views.afe_edit, name="edit"),
    path("<int:pk>/regenerate/", views.afe_regenerate, name="regenerate"),
    path("<int:pk>/action/", views.afe_action, name="action"),
]
