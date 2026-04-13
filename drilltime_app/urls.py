from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("proposals/", include("proposals.urls", namespace="proposals")),
    path("afe/", include("afe.urls", namespace="afe")),
    path("", RedirectView.as_view(pattern_name="proposals:dashboard", permanent=False)),
]
