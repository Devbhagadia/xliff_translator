from django.urls import path
from .views import index, upload_xliff, download_file, save_edits,download_translated_file,check_progress  # Import the view functions
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("", index, name="index"),  # Make sure you have a name for index
    path("upload/", upload_xliff, name="upload_xliff"),  # This should match the form action
    path("download/<str:file_name>/", download_file, name="download_file"),
    path("save-edits/", save_edits, name="save_edits"),
    path("download-translated/", download_translated_file, name="download_translated_file"),
    path("check-progress/", check_progress, name="check_progress"),
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)