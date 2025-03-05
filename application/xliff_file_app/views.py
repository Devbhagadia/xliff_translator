import json
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
import sys



logger = logging.getLogger(__name__)
sys.stdout.reconfigure(encoding="utf-8")
def log_debug(message):
    """ Redirect debug logs to stderr """
    sys.stderr.write(f"DEBUG: {message}\n")
    sys.stderr.flush()

def index(request):
    return render(request, "index.html")

def check_progress(request):
    progress = cache.get("progress", 0)
    translation_complete = cache.get("translation_complete", False)

    if progress is None or (progress == 100 and translation_complete):  
        cache.set("progress", 0, timeout=600)
        progress = 0
        log_debug("Progress was None or completed (100%), resetting to 0%")

    elif progress == 95 and not translation_complete:  # 🚨 ISSUE: Prevents going to 100%
        log_debug("Translation at 95% but not marked complete. Checking...")
        if cache.get("translation_complete"):  # ✅ Fix: Double-check status
            log_debug("Translation is actually done. Setting progress to 100%.")
            cache.set("progress", 100, timeout=600)
            return JsonResponse({"progress": 100})
        return JsonResponse({"progress": 95})  # 🔄 Keeps polling

    log_debug(f"Returning progress: {progress}")  
    return JsonResponse({"progress": progress})



def enqueue_output(pipe, q):
    """ Helper function to read process output asynchronously. """
    try:
        for line in iter(pipe.readline, ''):
            q.put(line)
    finally:
        pipe.close()

def download_file(request, file_name):
    file_path = os.path.join(default_storage.location, "xliff_files", file_name)

    log_debug(f"Download requested for {file_path}")

    if os.path.exists(file_path):
        log_debug("File exists, sending response")
        return FileResponse(open(file_path, "rb"), as_attachment=True)

    log_debug("File not found")
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

        xliff_file = request.FILES["xliff_file"]
        if not xliff_file.name.endswith((".xlf", ".xliff")):
            return JsonResponse({"error": "Invalid file format. Please upload an XLIFF file."}, status=400)

        # ✅ Save uploaded file properly
        try:
            file_path = default_storage.save("xliff_files/" + xliff_file.name, ContentFile(xliff_file.read()))
            full_path = default_storage.path(file_path)
        except Exception as e:
            return JsonResponse({"error": f"File saving failed: {str(e)}"}, status=500)

        cache.set("progress", 10, timeout=600)  # ✅ Initial progress update

        try:
            # ✅ Run the script and capture output/errors
            process = subprocess.Popen(
                ["python3", "-u", os.path.join(os.path.dirname(__file__), "../script4.py"), full_path],  
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            script_output, script_error = process.communicate()

            # ✅ Log stderr for debugging
            if script_error:
                logger.debug(f"Script error: {script_error.strip()}")

            if process.returncode != 0:
                return JsonResponse({
                    "error": "Script execution failed",
                    "details": script_error.strip() or "Unknown error occurred"
                }, status=500)

            # ✅ Extract only valid JSON part (Fixing extra printed text issue)
            script_output = script_output.strip()
            match = re.search(r'(\{.*\})', script_output, re.DOTALL)
            if match:
                script_output = match.group(1)  # Get only the JSON part
            else:
                return JsonResponse({
                    "error": "Invalid JSON response from script",
                    "raw_output": script_output.strip()
                }, status=500)

            # ✅ Parse JSON safely
            script_data = json.loads(script_output)
            request.session["translated_data"] = script_data

            cache.set("progress", 100, timeout=600)  # ✅ Translation completed

            return JsonResponse({
                "translated_file": script_data.get("translated_file", ""),
                "translations": script_data.get("translations", []),
                "translation_complete": True
            })

        except Exception as e:
            return JsonResponse({"error": f"Error processing XLIFF file: {str(e)}"}, status=500)
        
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

