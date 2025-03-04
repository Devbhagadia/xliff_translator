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

if len(sys.argv) < 2:
    print("Usage: script4.py <xliff_file_path>")
    sys.exit(1)

input_file = sys.argv[1]  # Get the file path from the command-line argument

if not os.path.exists(input_file):
    print(f"Error: File '{input_file}' not found!")
    sys.exit(1)

if not input_file.endswith(".xlf"):
    print("Error: The provided file is not an XLIFF (.xlf) file!")
    sys.exit(1)

# ✅ Correctly parse the single file
tree = ET.parse(input_file)  
root = tree.getroot()

print("File parsed successfully!")



# Create a workbook
book = xlwt.Workbook(encoding="utf-8")
sheet1 = book.add_sheet("Sheet 1")

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

print("saving .....")
# book.save("src/sourcefile.xls")
print("saved successfully", source_Data)


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
                print("specialTextbbbbbbbbbbbbbbbbbbb", specialTranslatedText)
                translated_Data.append(specialTranslatedText)

            else:

                # Properly await the async translate function
                translated = await translator.translate(value, dest="hi")
                translated_text = translated.text  # Extract translated text

                print(translated_text)
                translated_Data.append(translated_text)

    # translated data
    print("translated data", translated_Data)


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
    
                        else:
                            print("jjjjjjj")

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
                       
output_file = input_file.replace(".xlf", "_translated.xlf")
tree.write(output_file, encoding="utf-8", xml_declaration=True)
print(output_file)  # ✅ Make sure views.py can read the path

# tree.write(r"src/translated.xlf", encoding="utf-8", xml_declaration=True)