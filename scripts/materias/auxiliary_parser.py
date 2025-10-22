import os
import argparse
import requests
import xml.etree.ElementTree as ET
import json
import re
import sys

def to_pascal_case(text: str) -> str:
    """Converts snake_case or kebab-case text to PascalCase for class names."""
    return "".join(word.capitalize() for word in re.split(r'[-_]', text))

def to_constant_name(text: str) -> str:
    """Converts a description string into a valid Python constant name."""
    # Handle specific cases or common patterns first
    text = text.replace('%', 'PORCENTAJE')

    text = text.upper()
    # Normalize accented characters
    text = re.sub(r'[ÁÀÂÄ]', 'A', text)
    text = re.sub(r'[ÉÈÊË]', 'E', text)
    text = re.sub(r'[ÍÌÎÏ]', 'I', text)
    text = re.sub(r'[ÓÒÔÖ]', 'O', text)
    text = re.sub(r'[ÚÙÛÜ]', 'U', text)
    text = re.sub(r'Ñ', 'N', text)

    # Replace all non-alphanumeric characters with underscores
    text = re.sub(r'[^A-Z0-9_]', '_', text)

    # Consolidate multiple underscores
    text = re.sub(r'_+', '_', text)

    # Ensure it doesn't start with a number
    if text and text[0].isdigit():
        text = '_' + text

    return text.strip('_')

def fetch_xml_data(api_type: str) -> str:
    """Fetches XML data from the BOE API for a given type."""
    url = f"https://www.boe.es/datosabiertos/api/datos-auxiliares/{api_type}"
    headers = {"Accept": "application/xml"}
    try:
        print(f"Fetching data from {url} ...")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for '{api_type}': {e}", file=sys.stderr)
        return None

def parse_xml_to_dict(xml_content: str) -> dict:
    """Parses the XML content and extracts a description-to-code mapping."""
    try:
        root = ET.fromstring(xml_content)

        data_container = None
        # Case 1: The structure is nested, e.g., <response><data><item>...
        if root.tag == 'response':
            data_container = root.find('data')

        # Case 2: Items are top-level, e.g., <materias><item>...
        # This also acts as a fallback if the first case fails.
        if data_container is None:
            data_container = root
        
        if data_container is None:
            print("Error: Could not find the element containing data items in the XML.", file=sys.stderr)
            return {}

        desc_to_code = {}
        for item in data_container.findall("item"):
            desc_element = item.find("descripcion")
            code_element = item.find("codigo")
            if desc_element is not None and code_element is not None and desc_element.text is not None and code_element.text is not None:
                desc = desc_element.text.strip()
                code = code_element.text.strip()
                # Use a numeric value for the code if possible
                desc_to_code[desc] = int(code) if code.isdigit() else f'"{code}"'
        
        if not desc_to_code:
            print("Warning: XML parsed successfully, but no items were found.", file=sys.stderr)

        return desc_to_code
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}", file=sys.stderr)
        return {}

def generate_python_class(class_name: str, api_type: str, data_dict: dict) -> str:
    """Generates the Python class source code as a string."""
    lines = [f"class {class_name}:\n"]
    lines.append("    \"\"\"Data model for BOE auxiliary data.\n\n")
    lines.append(f"    Generated from: https://www.boe.es/datosabiertos/api/datos-auxiliares/{api_type}\n")
    lines.append("    \"\"\"\n")

    if not data_dict:
        lines.append("    # No data found to generate constants.\n    pass\n")
        return "".join(lines)

    for desc, code in sorted(data_dict.items()):
        const_name = to_constant_name(desc)
        if not const_name:
            continue
        lines.append(f"    {const_name} = {code}\n")

    lines.append("\n    _code_to_name = None\n")
    lines.append("\n    @classmethod\n")
    lines.append("    def name_from_code(cls, code):\n")
    lines.append("        \"\"\"Reverse lookup to get the constant name from a code.\"\"\"\n")
    lines.append("        if cls._code_to_name is None:\n")
    lines.append("            cls._code_to_name = {\n")
    lines.append("                v: k for k, v in cls.__dict__.items() \n")
    lines.append("                if not k.startswith('_') and not callable(v)\n")
    lines.append("            }\n")
    lines.append("        return cls._code_to_name.get(code)\n")

    return "".join(lines)

def process_api_type(api_type: str, output_file: str = None, preview: bool = False):
    """Fetches, parses, and generates the model for a single API type."""
    # Determine class name and output path
    class_name = to_pascal_case(api_type)
    if output_file == None:
        output_file = f"{api_type.replace('-', '_')}_model.py"

    project_root_directory = os.getcwd()
    relative_path = os.path.join('src/models/auxiliary', output_file)
    output_path = os.path.join(project_root_directory, relative_path)
    # Core logic
    xml_data = fetch_xml_data(api_type)
    if xml_data is None:
        return # Skip if fetching failed

    data_dict = parse_xml_to_dict(xml_data)

    if preview:
        print("\n--- JSON Preview ---")
        print(json.dumps(data_dict, indent=2, ensure_ascii=False))
        print("--------------------\n")

    class_code = generate_python_class(class_name, api_type, data_dict)

    # Write to file
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(class_code)
        print(f"✅ Data model saved as: {os.path.abspath(output_path)}")
    except IOError as e:
        print(f"Error writing to file {output_path}: {e}", file=sys.stderr)

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(
        description="Generate a Python data model class from the BOE Datos Abiertos API."
    )
    parser.add_argument(
        "api_type",
        nargs='?',
        default=None,
        help="The type of data to fetch (e.g., 'materias', 'departamentos'). Required if --all is not used."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate models for all known API types."
    )
    parser.add_argument(
        "-o", "--output",
        help="Optional: The path to the output .py file. Defaults to '{api_type}_model.py'. Ignored with --all."
    )
    parser.add_argument(
        "-p", "--preview",
        action="store_true",
        help="Print a JSON preview of the data to the console. Ignored with --all."
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.api_type:
        parser.error("Either an api_type must be specified, or the --all flag must be used.")
    if args.all and args.api_type:
        parser.error("Cannot specify both an api_type and the --all flag.")

    ALL_API_TYPES = [
        'materias',
        'ambitos',
        'estados-consolidacion',
        'departamentos',
        'rangos',
        'relaciones-anteriores',
        'relaciones-posteriores',
    ]

    if args.all:
        print("Generating models for all API types...")
        for api_type in ALL_API_TYPES:
            print(f"\n--- Processing: {api_type} ---")
            # Use default output path and no preview for batch mode
            process_api_type(api_type)
        print("\n✅ All models generated successfully.")
    else:
        # Process a single type with specified options
        process_api_type(args.api_type, args.output, args.preview)


if __name__ == "__main__":
    main()

