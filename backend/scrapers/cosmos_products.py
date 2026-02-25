import asyncio
import re
from playwright.async_api import async_playwright
from database import supabase

START_PAGE = 201
END_PAGE = 400  # adjust manually

def clean_commercial_name(name: str) -> str:
    return re.sub(r"^[\d\s\-]+", "", name).strip()

async def get_or_create_corporation(corp_name: str) -> str:
    existing = supabase.table("corporations").select("id").eq("name", corp_name).execute()
    if existing.data:
        return existing.data[0]["id"]
    res = supabase.table("corporations").insert({
        "name": corp_name,
        "free_animal_testing": True
    }).execute()
    return res.data[0]["id"]

async def get_or_create_brand(brand_name: str, corp_id: str) -> str:
    existing = supabase.table("brands").select("id").eq("name", brand_name).execute()
    if existing.data:
        return existing.data[0]["id"]
    res = supabase.table("brands").insert({
        "name": brand_name,
        "corp_id": corp_id
    }).execute()
    return res.data[0]["id"]

async def scrape_cosmos_products():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        data = []
        for page_num in range(START_PAGE, END_PAGE + 1):
            await page.goto(f"https://www.cosmos-standard.org/en/databases/products-directory/?page={page_num}")
            print(f"PAGE: {page_num}")

            await page.wait_for_selector("table", timeout=15000)
            rows = await page.query_selector_all("table#product-table tbody tr")
                        
            for row in rows:
                cells = await row.evaluate("""row => {
                    const th = row.querySelector('th') ? row.querySelector('th').innerText.trim() : ''
                    const tds = Array.from(row.querySelectorAll('td')).map(td => td.innerText.trim())
                    return [th, ...tds]
                }""")
                
                if len(cells) < 4:
                    continue
                
                commercial_name_raw = cells[0]  # th
                cosmos_signature    = cells[1]  # td[0]
                brand_name          = cells[2]  # td[1]
                company_name        = cells[3]  # td[2]

                commercial_name = clean_commercial_name(commercial_name_raw)

                if not commercial_name:
                    continue

                data.append({
                    "commercial_name": commercial_name,
                    "cosmos_signature": cosmos_signature,
                    "brand_name": brand_name,
                    "company_name": company_name
                })

        await browser.close()
        return data

async def main():
    print("Starts scraping:")
    print("==================================\n")

    data = await scrape_cosmos_products()
    print(f"Found {len(data)} rows")

    if not data:
        return

    print("Sample:", data[:3])
    # proceed = input("Proceed to upload to Supabase? (y/n): ")
    # if proceed != "y":
    #     print("Aborted.")
    #     return

    for entry in data:
        try:
            corp_id = await get_or_create_corporation(entry["company_name"])
            brand_id = await get_or_create_brand(entry["brand_name"], corp_id)

            # Check if product already exists
            existing = supabase.table("products").select("id").eq("name", entry["commercial_name"]).execute()
            if existing.data:
                print(f"  Skipped (exists): {entry['commercial_name']}")
                continue

            supabase.table("products").insert({
                "name": entry["commercial_name"],
                "brand_id": brand_id,
                "cosmos_cert_level": entry["cosmos_signature"]
            }).execute()

            print(f"  Inserted: {entry['commercial_name']}")
        except Exception as e:
            print(f"  Error on {entry['commercial_name']}: {e}")

    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())