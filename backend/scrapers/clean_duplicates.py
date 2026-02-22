import asyncio
from database import supabase
import re

def fetch_all(table):
    all_rows = []
    limit = 1000
    offset = 0
    while True:
        res = supabase.table(table).select("*").range(offset, offset + limit - 1).execute()
        all_rows.extend(res.data)
        if len(res.data) < limit:
            break
        offset += limit
    return all_rows

def chunked(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

def get_separators(inci_name):
    base = r'\s*\(and\)\s*|\s*\(And\)\s*|\s*,\s*|\s*\+\s*|\s*&\s*'
    if inci_name.count('/') > 1:
        base += r'|\s*/\s*'
    return base

def clean_duplicates():
    # Ambil semua data
    res = supabase.table("ingredient_master").select("id, inci_name, natural_origin_pct, restriction, data_source").execute()
    rows = fetch_all("ingredient_master")

    # Group by inci_name
    groups = {}
    for row in rows:
        name = row["inci_name"]
        if name not in groups:
            groups[name] = []
        groups[name].append(row)

    to_delete = []
    to_update = []

    for inci_name, entries in groups.items():
        if len(entries) == 1:
            continue

        # Hitung mean natural_origin_pct
        pcts = [e["natural_origin_pct"] for e in entries if e["natural_origin_pct"] is not None]
        mean_pct = sum(pcts) / len(pcts) if pcts else None

        # Union restriction
        all_restrictions = set()
        for e in entries:
            if e["restriction"]:
                all_restrictions.update(e["restriction"])

        # Keep id pertama, delete sisanya
        keep = entries[0]
        to_delete.extend([e["id"] for e in entries[1:]])
        to_update.append({
            "id": keep["id"],
            "natural_origin_pct": mean_pct,
            "restriction": list(all_restrictions) if all_restrictions else None
        })

    print(f"Duplicates found: {len(to_update)} groups, {len(to_delete)} rows to delete")

    # Update rows yang di-keep
    for item in to_update:
        supabase.table("ingredient_master").update({
            "natural_origin_pct": item["natural_origin_pct"],
            "restriction": item["restriction"]
        }).eq("id", item["id"]).execute()

    # Delete duplicates
    if to_delete:
        for chunk in chunked(to_delete, 100):
            supabase.table("ingredient_master").delete().in_("id", chunk).execute()

    print("Done!")
    
def split_inci_in_db():
    res = supabase.table("ingredient_master").select("*").execute()
    rows = fetch_all("ingredient_master")

    to_delete = []
    to_insert = []

    for row in rows:
        parts = re.split(get_separators(row["inci_name"]), row["inci_name"])
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) <= 1:
            continue  # skip kalau gak ada split

        to_delete.append(row["id"])
        for part in parts:
            to_insert.append({
                "inci_name": part,
                "natural_origin_pct": row["natural_origin_pct"],
                "restriction": row["restriction"],
                "data_source": row["data_source"]
            })

    print(f"Rows to split: {len(to_delete)}, new rows to insert: {len(to_insert)}")

    if to_delete:
        for chunk in chunked(to_delete, 100):
            supabase.table("ingredient_master").delete().in_("id", chunk).execute()

    seen = set()
    unique_insert = []
    for item in to_insert:
        if item["inci_name"] not in seen:
            seen.add(item["inci_name"])
            unique_insert.append(item)

    for chunk in chunked(unique_insert, 100):
        supabase.table("ingredient_master").upsert(chunk, on_conflict="inci_name").execute()

    print("Done!")

if __name__ == "__main__":
    split_inci_in_db()
    clean_duplicates()