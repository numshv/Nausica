import asyncio
import httpx
from playwright.async_api import async_playwright
from database import supabase
import os
import csv

def chunked(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

# async def cas_to_inci(cas: str) -> str | None:
#     """Convert CAS number to INCI name via PubChem API."""
#     url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}/property/IUPACName/JSON"
#     async with httpx.AsyncClient(timeout=10) as client:
#         try:
#             res = await client.get(url)
#             data = res.json()
#             return data["PropertyTable"]["Properties"][0]["IUPACName"]
#         except Exception:
#             return None

async def cas_to_inci(cas: str) -> str | None:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}/synonyms/JSON"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            res = await client.get(url)
            data = res.json()
            synonyms = data["InformationList"]["Information"][0]["Synonym"]
            
            # INCI names biasanya all-caps dan tidak mengandung karakter aneh
            for syn in synonyms:
                if syn.isupper() and len(syn) > 2 and not syn.startswith("DTXSID") and not syn.startswith("CHEBI"):
                    return syn
            
            # Fallback: return synonym pertama
            return synonyms[0]
        except Exception:
            return None
        

async def save_to_csv(results: list[dict], filename: str = "sin_list_output.csv"):
    with open(filename, "w", newline="", encoding="utf-8") as f:
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
        for entry in results:
            writer.writerow({
                "inci_name": entry["cas"],
                "natural_origin_pct": 15,
                "is_eu_banned": False,
                "is_eu_restricted": False,
                "is_sin_list": True,
                "sin_list_flags": "{" + ",".join(entry["sin_list_flags"]) + "}",
                "is_nanomaterial": False,
                "is_nanomaterial_whitelisted": False,
                "restriction": None,
                "data_source": "ChemSec SIN List"
            })
    print(f"Saved to {filename}")

async def scrape_sin_list():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=False biar bisa liat prosesnya
        page = await browser.new_page()

        await page.goto("https://sinsearch.chemsec.org/")
        # Klik tombol Sign in di navbar
        await page.click("text=Sign in")
        await page.wait_for_selector("input[type='email']")

        # Isi form
        await page.fill("input[type='email']", os.getenv("SIN_EMAIL"))
        await page.fill("input[type='password']", os.getenv("SIN_PASSWORD"))
        await page.locator("button.popup__button.account").click()
        print("here")
        await page.wait_for_load_state("networkidle")
        print("here2")

        # Dismiss cookie banner kalau ada 
        try:
            await page.click("text=Only necessary", timeout=5000)
        except Exception:
            pass
        
        print("here3")
        await page.screenshot(path="debug_after_login.png")
        
        # Nyalakan filter Health and environmental concerns
        health_filter_alts = ["PBT/vPvB", "PMT/vPvM", "Extremely persistent"]
        for alt in health_filter_alts:
            try:
                await page.locator(f"button.filter-button[alt='{alt}']").click(timeout=5000)
                print(f"Clicked filter: {alt}")
            except Exception:
                print(f"Filter not found: {alt}")

        # Klik "Show more" di section Uses dulu biar Personal Care muncul
        try:
            await page.locator("#show-more-link_Uses button").click(timeout=5000)
            await page.wait_for_timeout(1000)
            print("Clicked show more for Uses")
        except Exception:
            print("Show more Uses not found")

        # Nyalakan filter Uses: Personal Care
        try:
            await page.locator("button.filter-button[alt='Personal care']").click(timeout=5000)
            print("Clicked filter: Personal Care")
        except Exception:
            print("Filter 'Personal Care' not found")

        all_results = []

        # Loop through all pages
        while True:
            await page.wait_for_selector("table tbody tr", timeout=20000)
            rows = await page.query_selector_all("table tbody tr")
            print(f"Found {len(rows)} rows on current page")

            for row in rows:
                cols = await row.query_selector_all("td")
                if len(cols) < 2:
                    continue

                cas_number = (await cols[1].inner_text()).strip()
                health_concerns_raw = (await cols[3].inner_text()).strip()
                health_concerns = [h.strip() for h in health_concerns_raw.split(",") if h.strip()]

                if not cas_number:
                    continue

                all_results.append({
                    "cas": cas_number,
                    "sin_list_flags": health_concerns
                })

            # Cek apakah ada next page
            next_btn = await page.query_selector("li.paginationjs-next:not(.disabled)")
            if not next_btn:
                print("No more pages")
                break

            await next_btn.click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)

        await browser.close()
        return all_results

async def update_ingredient_master(results: list[dict]):
    print(f"Processing {len(results)} entries...")

    for entry in results:
        cas = entry["cas"]
        flags = entry["sin_list_flags"]

        # Convert CAS ke INCI
        inci_name = await cas_to_inci(cas)
        if not inci_name:
            print(f"Could not convert CAS {cas} to INCI, skipping")
            continue

        print(f"CAS {cas} → {inci_name}")

        # Cek apakah sudah ada di DB
        existing = supabase.table("ingredient_master").select("id").eq("inci_name", inci_name).execute()

        if existing.data:
            # Update existing
            supabase.table("ingredient_master").update({
                "is_sin_list": True,
                "sin_list_flags": flags
            }).eq("inci_name", inci_name).execute()
            print(f"  Updated: {inci_name}")
        else:
            # Insert baru
            supabase.table("ingredient_master").insert({
                "inci_name": inci_name,
                "natural_origin_pct": 15,
                "is_sin_list": True,
                "sin_list_flags": flags,
                "data_source": "ChemSec SIN List"
            }).execute()
            print(f"  Inserted: {inci_name}")

async def main():
    print("Scraping SIN List...")
    results = await scrape_sin_list()
    print(f"Scraped {len(results)} entries")

    if results:
        await save_to_csv(results)  # ← tambah ini
        print("Sample:", results[:3])
        # proceed = input("Proceed to update ingredient_master? (y/n): ")
        # if proceed == "y":
        #     await update_ingredient_master(results)
        #     print("Done!")

if __name__ == "__main__":
    asyncio.run(main())