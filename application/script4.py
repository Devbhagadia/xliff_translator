import json
import xml.etree.cElementTree as ET
import xlrd
import xlwt
from xlwt import Workbook
from googletrans import Translator
from bs4 import BeautifulSoup
import os
import asyncio
import ssl
import copy
import re
import sys
import time
# from django.core.cache import cache

sys.stdout.reconfigure(encoding="utf-8")  # ✅ Force UTF-8 output

TEMP_DIR = "/tmp/" if "RENDER" in os.environ else os.getcwd()

if len(sys.argv) < 2:
    print("Usage: script4.py <xliff_file_path>")
    sys.exit(1)

input_file = sys.argv[1]  # Get the file path from the command-line argument

if not os.path.exists(input_file):
    print(f"Error: File '{input_file}' not found!")
    sys.exit(1)

# get the root element
tree = ET.ElementTree(file=input_file)
root = tree.getroot()
# path = r"D:\xliff_translator\src"

# Define the namespace to match in the XML
# namespace = {"xliff": "urn:oasis:names:tc:xliff:document:1.2"}

# for filename in os.listdir(input_file):
#     if not filename.endswith(".xlf"):
#         continue
#     pathname = os.path.join(input_file, filename)
#     tree = ET.parse(pathname)


total_units = 10
for i in range(1, total_units + 1):
    time.sleep(1)  # Simulate translation work
    progress = int((i / total_units) * 100)  # Calculate progress
    print(f"TRANSLATION_PROGRESS: {progress}",  file=sys.stderr)  # ✅ Send progress to Django
    sys.stderr.flush()
# # Create a workbook
# book = xlwt.Workbook(encoding="utf-8")
# sheet1 = book.add_sheet("Sheet 1")

source_Data= []

# fetch each element within the source tag and save it in source file
i = 0
for trans in root:
    for header in trans:
        for body in header:
            for source in body:
                # all_text = ""
                for (
                    element
                ) in source.iter():  # Iterate over all descendants of 'source'
                    text_content = (
                        element.text.strip() if element.text else None
                    )  # Remove leading/trailing spaces

                    if (
                        "ctype" in element.attrib
                        and element.attrib["ctype"] == "x-text"
                        and text_content
                    ):
                        source_Data.append(text_content)
                    elif not element.attrib and text_content:  # Ensure non-empty text
                        source_Data.append(text_content)

# print("saving .....")
# book.save("src/sourcefile.xls")
# print("saved successfully", source_Data)
# print(f"DEBUG: Found {len(source_Data)} extracted texts")
# for i, text in enumerate(source_Data):
    # print(f"TEXT {i+1}: {repr(text)}")  # Print extracted text with index


# #########################################################################################################

# #Create the instance of google translator class


# Fix SSL issue
ssl._create_default_https_context = ssl._create_unverified_context

translator = Translator()


translated_Data=[]



async def translate_cell():
    for value in source_Data:
            value = str(value).strip()
            

            if re.search(r"%.*%", value):
                specialTxtList=[]
                splittedValue = re.findall(r"%[^%]+%|\S+", value)
                for elem in splittedValue:
                    if "%" not in elem:
                        translated = await translator.translate(elem, dest="hi")
                        elem = translated.text
                        specialTxtList.append(elem)
                    else:
                        specialTxtList.append(elem)   

                specialTranslatedText= " ".join(specialTxtList)
                # print("specialTextbbbbbbbbbbbbbbbbbbb", specialTranslatedText)
                translated_Data.append(specialTranslatedText)

            else:

                # Properly await the async translate function
                translated = await translator.translate(value, dest="hi")
                translated_text = translated.text  # Extract translated text

                print(translated_text)
                translated_Data.append(translated_text)

    # translated data
    print(f"DEBUG: Found {len(translated_Data)} translated texts", file=sys.stderr)


# for i, text in enumerate(translated_Data):
    # print(f"TRANSLATED {i+1}: {repr(text)}")  # Print translated text
# # Run the function in an event loop

asyncio.run(translate_cell())



# ####################################################################################################


# Define namespace
namespace = "urn:oasis:names:tc:xliff:document:1.2"

index = 0


for files in root:
    for Outer_Tags in files:

        for trans_unit in Outer_Tags:
            target = trans_unit.find(f"{{{namespace}}}target")
            if target is None:
                target = ET.Element(f"{{{namespace}}}target")
                for source in trans_unit:
                    
                    # print("sorceeeeeeee", source)
                    if source is not None:
                        text_content = source.text.strip() if source.text else None
                        if not source.attrib and text_content:  # If plain text without attributes
                            text_element = ET.Element(f"{{{namespace}}}text")  # Create a new XML element
                            text_element.text = text_content  # Assign stripped text
                            target.append(copy.deepcopy(text_element))  # Append the new element
    
                        elif list(source):  # If there are child elements
                            for child in source:
                                target.append(copy.deepcopy(child))  # Append each child to target
    
                        # else:
                            # print("jjjjjjj")

                trans_unit.append(target)

            for element in target.findall("*"):  
                    text_content = element.text.strip() if element.text else None
                    # Only modify <g ctype="x-text"> inside <target>
                    if "ctype" in element.attrib and element.attrib["ctype"] == "x-text" and text_content:
                            element.text = translated_Data[index]  # Assign cleaned translated text
                            index += 1
                     
                        
                    elif not element.attrib and text_content :
                            element.text = translated_Data[index]
                            index += 1

# Ensure no unwanted text gets added to translations
# Ensure the last line isn't added if it contains "Translated file saved:"
# translated_Data = [
#     t.split("Translated file saved:")[0].strip() if "Translated file saved:" in t else t
#     for t in translated_Data
# ]


# Now, write the filtered translations to the file
output_file = os.path.join(TEMP_DIR, os.path.basename(input_file).replace(".xlf", "_translated.xlf"))
tree.write(output_file, encoding="utf-8", xml_declaration=True)

import json

# ✅ Structure response properly
response_data = {
    "translated_file": output_file,  # Path to translated file
    "translations": [{"original": src, "translated": trans} for src, trans in zip(source_Data, translated_Data)]
}

sys.stdout.write(json.dumps(response_data, ensure_ascii=False) + "\n")
sys.stdout.flush()
# cache.set("progress", 100, timeout=600)
# cache.set("translation_complete", True, timeout=600)
