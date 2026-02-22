import csv

def load_csv(path: str) -> dict[str, dict]:
    result = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            inci = row["inci_name"].strip()
            if inci and inci not in result:
                result[inci] = row
    return result

def merge():
    banned = load_csv("files/cosing_prohibited_output.csv")
    sin = load_csv("files/sin_list_output.csv")

    merged = {}

    # Add all banned entries
    for inci, row in banned.items():
        merged[inci] = row.copy()

    # Merge sin list entries
    for inci, row in sin.items():
        if inci in merged:
            # Conflict: exists in both → is_eu_banned = True, is_sin_list = True
            merged[inci]["is_eu_banned"] = True
            merged[inci]["is_sin_list"] = True
            merged[inci]["sin_list_flags"] = row["sin_list_flags"]
        else:
            merged[inci] = row.copy()

    # Write output
    fieldnames = [
        "inci_name", "natural_origin_pct", "is_eu_banned", "is_eu_restricted",
        "is_sin_list", "sin_list_flags", "is_nanomaterial", "is_nanomaterial_whitelisted",
        "restriction", "data_source"
    ]

    with open("files/merged_cosing_sin_output.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in merged.values():
            writer.writerow({k: row.get(k, None) for k in fieldnames})

    print(f"Done. Total unique entries: {len(merged)}")
    print(f"  From cosing_prohibited: {len(banned)}")
    print(f"  From sin_list: {len(sin)}")
    print(f"  Overlap (both): {len(set(banned) & set(sin))}")

if __name__ == "__main__":
    merge()