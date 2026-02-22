import pdfplumber
import csv
import re

def extract_cas_numbers(pdf_path: str) -> list[str]:
    cas_numbers = []
    # CAS number pattern: digits-digits-digits
    cas_pattern = re.compile(r'\b\d{1,7}-\d{2}-\d\b')

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row:
                        continue
                    # CAS Number is the 3rd column (index 2)
                    for cell in row:
                        if cell and cas_pattern.match(str(cell).strip()):
                            # Handle multiple CAS numbers in one cell (e.g. "132-60-5 / 5949-18-8")
                            found = cas_pattern.findall(str(cell))
                            cas_numbers.extend(found)

    return cas_numbers


def save_to_csv(cas_numbers: list[str], output_path: str = "cosing_prohibited_output.csv"):
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "inci_name",
            "natural_origin_pct",
            "is_eu_banned",
            "is_eu_restricted",
            "is_sin_list",
            "sin_list_flags",
            "is_nanomaterial",
            "is_nanomaterial_whitelisted",
            "restriction",
            "data_source"
        ])
        writer.writeheader()
        for cas in cas_numbers:
            writer.writerow({
                "inci_name": cas,
                "natural_origin_pct": 10,
                "is_eu_banned": True,
                "is_eu_restricted": False,
                "is_sin_list": False,
                "sin_list_flags": None,
                "is_nanomaterial": False,
                "is_nanomaterial_whitelisted": False,
                "restriction": None,
                "data_source": "COSING Prohibited List"
            })
    print(f"Saved {len(cas_numbers)} entries to {output_path}")


def main():
    pdf_path = "COSING_PROHIBITED_ANNEX_2.pdf"
    print(f"Extracting CAS numbers from {pdf_path}...")
    cas_numbers = extract_cas_numbers(pdf_path)
    print(f"Found {len(cas_numbers)} CAS numbers")

    if cas_numbers:
        print("Sample:", cas_numbers[:5])
        save_to_csv(cas_numbers)


if __name__ == "__main__":
    main()