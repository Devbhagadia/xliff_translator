import os
import re
import xml.etree.ElementTree as ET
import subprocess
from django.conf import settings
from django.shortcuts import render
from django.http import FileResponse, HttpResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import uuid
from xml.dom import minidom
from django.shortcuts import render
from django.http import JsonResponse
import time
from django.core.cache import cache
import threading
import queue
import uuid
import logging
from urllib.parse import quote


logger = logging.getLogger(__name__)


def index(request):
    return render(request, "index.html")

def check_progress(request): 
    """ Returns the current translation progress as JSON """
    progress = cache.get("progress", 0)
    translation_complete = cache.get("translation_complete", False)

    #  Prevent starting at 100% when a new translation starts
    if progress is None or (progress == 100 and translation_complete):  
        cache.set("progress", 0, timeout=600)
        progress = 0
        print("DEBUG: Progress was None or a completed translation (100%), resetting to 0%")

    elif progress == 100 and not translation_complete:
        print("DEBUG: Translation at 100% but not yet complete. Keeping progress at 99%.")
        return JsonResponse({"progress": 95})

    print(f"DEBUG: Returning progress: {progress}")  
    return JsonResponse({"progress": progress})




def enqueue_output(out, queue):
    for line in iter(out.readline, ""):
        queue.put(line)
    out.close()

def download_file(request, file_name):
    file_path = os.path.join(default_storage.location, "xliff_files", file_name)

    print(f"DEBUG: Download requested for {file_path}")

    if os.path.exists(file_path):
        print("DEBUG: File exists, sending response")
        return FileResponse(open(file_path, "rb"), as_attachment=True)

    print("DEBUG: File not found")
    return HttpResponse("File not found.", status=404)

def download_translated_file(request):
    new_file_path = request.session.get("new_file_path")
    
    if not new_file_path or not os.path.exists(new_file_path):
        return HttpResponse("Error: Translated file not found.", status=404)

    file_name = os.path.basename(new_file_path)
    response = FileResponse(open(new_file_path, "rb"), as_attachment=True, filename=file_name)
    
    return response

def upload_xliff(request):
    if request.method == "POST" and request.FILES.get("xliff_file"):
        cache.set("progress", 0, timeout=600)
        cache.set("translation_complete", False, timeout=600)
        print("DEBUG: Progress reset to 0% before upload")

        xliff_file = request.FILES["xliff_file"]
        if not xliff_file.name.endswith((".xlf", ".xliff")):
            return HttpResponse("Invalid file format. Please upload an XLIFF file.", status=400)

        # ✅ Save uploaded file
        file_path = default_storage.save("xliff_files/" + xliff_file.name, ContentFile(xliff_file.read()))
        full_path = os.path.join(default_storage.location, file_path)
        print(f"DEBUG: File saved at {full_path}")

        cache.set("progress", 10, timeout=600)
        print("DEBUG: Progress set to 10%")

        try:
            # ✅ Run script and capture output
            process = subprocess.Popen(
                ["python3", "-u", "script4.py", full_path],  
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )

            q = queue.Queue()
            t = threading.Thread(target=enqueue_output, args=(process.stdout, q))
            t.daemon = True
            t.start()

            translated_content = []  # ✅ Instead of file path, store translated text
            translation_started = False

            while process.poll() is None:
                while not q.empty():
                    line = q.get()
                    print(f"DEBUG: Script Output: {line}")

                    if "TEXT" in line:
                        translation_started = True

                    if "TRANSLATION_PROGRESS:" in line:
                        try:
                            _, progress_value = line.split("TRANSLATION_PROGRESS: ")
                            progress_value = int(progress_value.strip())
                            cache.set("progress", progress_value, timeout=600)
                            print(f"DEBUG: Progress updated to {progress_value}")
                        except ValueError:
                            print(f"WARNING: Invalid progress format: {line}")

                    # ✅ Store translation directly from script output
                    if "TRANSLATION_OUTPUT:" in line:
                        _, content = line.split("TRANSLATION_OUTPUT: ", 1)
                        translated_content.append(content.strip())

            process.wait()

            if translation_started:
                cache.set("progress", 100, timeout=600)
                print("DEBUG: Progress set to 100% after translation")

            cache.set("progress", 100, timeout=600)

            if not translated_content:
                print(f"ERROR: No translation content received!")
                return JsonResponse({"error": "Translation failed, no output received."}, status=500)

            return JsonResponse({"translated_text": translated_content})

        except Exception as e:
            return HttpResponse(f"Error processing XLIFF file: {e}")
        
        
def save_edits(request):
    if request.method == "POST":
        translated_texts = request.POST.getlist("translated_text[]")
        print(f"DEBUG: Received {len(translated_texts)} translations")

        original_file_path = request.session.get("translated_file_path")
        if not original_file_path or not os.path.exists(original_file_path):
            return HttpResponse("Error: Translated file not found.")

        new_file_name = f"translated_{uuid.uuid4().hex}.xlf"
        new_file_path = os.path.join(os.path.dirname(original_file_path), new_file_name)

        try:
            #  Load XLIFF File
            tree = ET.parse(original_file_path)
            root = tree.getroot()
            ns = {'ns0': 'urn:oasis:names:tc:xliff:document:1.2'}

            #  Find all <target> elements
            target_elements = root.findall(".//ns0:target", ns)
            print(f"DEBUG: Found {len(target_elements)} <target> elements")

            #  Extract elements that need translation
            target_mapping = []  # Stores tuples (target, child elements, type)
            total_translation_units = 0  

            for target in target_elements:
                g_elements = target.findall(".//ns0:g", ns)
                text_elements = target.findall(".//ns0:text", ns)

                elements = []
                elem_type = None
                
                if g_elements:
                    elements = [g for g in g_elements if g.text and g.text.strip()]
                    elem_type = "g"
                elif text_elements:
                    elements = [t for t in text_elements if t.text and t.text.strip()]
                    elem_type = "text"
                elif target.text and target.text.strip():
                    elements = [target]  # Treat as list for consistency
                    elem_type = "direct"

                #  Only add if there's valid text to translate
                if elements:
                    total_translation_units += len(elements)  
                    target_mapping.append((target, elements, elem_type))
                else:
                    print(f" Skipping empty <target>: {ET.tostring(target, encoding='unicode')}")

            print(f" Expected {total_translation_units} translations (should match received count of)")

            #  Strictly Check Count
            if total_translation_units != len(translated_texts):
                print(" ERROR: Mismatch in translation count!")
                return HttpResponse(f"Error: Expected {total_translation_units} translations, but got {len(translated_texts)}.")

            #  Apply Translations
            text_index = 0
            for target, elements, elem_type in target_mapping:
                for elem in elements:
                    if text_index < len(translated_texts):
                        translation = translated_texts[text_index].strip()
                        elem.text = translation
                        text_index += 1
                    else:
                        print(f" WARNING: No translation available for {elem_type} - id={elem.get('id', 'N/A')}")

            #  Final Check Before Saving
            if text_index != len(translated_texts):
                print(f" ERROR: Expected to apply {len(translated_texts)} translations, but only applied {text_index}")

            #  Save Updated File
            tree.write(new_file_path, encoding="utf-8", xml_declaration=True)

            print(f" SUCCESS! File saved at: {new_file_path}")
            request.session["new_file_path"] = new_file_path  
            return render(request, "save_edits.html", {"new_file_name": new_file_name})

        except Exception as e:
            return HttpResponse(f"Error saving edits: {e}")

    return HttpResponse("Invalid request.")

