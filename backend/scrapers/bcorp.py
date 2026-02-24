import asyncio
import csv
from playwright.async_api import async_playwright
from database import supabase

BASE_URL = (
    "https://www.bcorporation.net/en-us/find-a-b-corp/"
    "?refinement%5Bindustry%5D%5B0%5D=Hairdressing%20%26%20other%20beauty%20services"
    "&refinement%5Bindustry%5D%5B1%5D=Pharmaceutical%20products"
    "&page={page}"
)

async def scrape():
    links = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for page_num in range(1, 4):
            url = BASE_URL.format(page=page_num)
            print(f"Scraping page {page_num}...")
            await page.goto(url)
            await page.wait_for_selector("li.ais-Hits-item", timeout=15000)

            cards = await page.query_selector_all("li.ais-Hits-item a[data-testid='profile-link']")
            for card in cards:
                href = await card.get_attribute("href")
                if href:
                    full_url = "https://www.bcorporation.net" + href
                    links.append(full_url)

            print(f"  Found {len(cards)} cards")

        await browser.close()

    with open("files/bcorp_links.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["link"])
        for link in links:
            writer.writerow([link])

    print(f"Done. Total {len(links)} links saved to bcorp_links.csv")

async def scrape_brand_profile(page, url: str) -> dict | None:
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_selector("main h1", timeout=15000)

        # Name
        name = await page.locator("main h1").first.inner_text()
        name = name.strip()

        # Country
        country = None
        try:
            p_text = await page.locator("div:has(> span:text('Headquarters')) .opacity-60 p").first.inner_text()
            # inner_text() akan return sesuatu seperti "Uusimaa ,  Finland"
            # ambil bagian setelah koma terakhir
            parts = p_text.split(",")
            if len(parts) >= 2:
                country = parts[-1].strip()
        except Exception:
            pass

        # B Corp Score
        b_corp_score_raw = None
        try:
            spans = await page.locator("span:has-text('Overall B Impact Score')").all()
            for span in spans:
                text = await span.inner_text()
                match = re.search(r"[\d.]+", text)
                if match:
                    b_corp_score_raw = float(match.group())
                    break
        except Exception:
            pass

        # Calculate eco_score
        b_corp_score = None
        if b_corp_score_raw is not None:
            eco_score = 75 + ((b_corp_score_raw - 80) / (150 - 80)) * 40
            b_corp_score = min(round(eco_score, 2), 100)

        return {
            "name": name,
            "country": country,
            "has_takeback_program": False,
            "has_carbon_commitment": False,
            "has_csr_program": False,
            "b_corp_score": b_corp_score,
            "free_animal_testing": True,
            "bad_news_score": 0,
            "bad_news_last_checked": None,
        }
    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return None


async def scrape_all_brands():
    import re

    # Load links from CSV
    links = []
    with open("files/bcorp_links.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            links.append(row["link"])

    print(f"Loaded {len(links)} links")

    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, url in enumerate(links):
            print(f"[{i+1}/{len(links)}] Scraping {url}...")
            brand = await scrape_brand_profile(page, url)
            if brand:
                results.append(brand)

        await browser.close()

    print(f"\nScraped {len(results)} brands")
    print("\nSample (3):")
    for b in results[:3]:
        print(b)

    proceed = input("\nProceed to insert to DB? (y/n): ")
    if proceed.lower() != "y":
        print("Aborted.")
        return

    print("Inserting to DB...")
    for brand in results:
        try:
            existing = supabase.table("brands").select("id").eq("name", brand["name"]).execute()
            if existing.data:
                supabase.table("brands").update(brand).eq("name", brand["name"]).execute()
                print(f"  Updated: {brand['name']}")
            else:
                supabase.table("brands").insert(brand).execute()
                print(f"  Inserted: {brand['name']}")
        except Exception as e:
            print(f"  Error inserting {brand['name']}: {e}")

    print("Done!")


if __name__ == "__main__":
    import re
    asyncio.run(scrape_all_brands())

# if __name__ == "__main__":
#     import re
#     async def test():
#         async with async_playwright() as p:
#             browser = await p.chromium.launch(headless=False)
#             page = await browser.new_page()
#             result = await scrape_brand_profile(page, "https://www.bcorporation.net/en-us/find-a-b-corp/company/nrtex-laboratorios-homeopticos/")
#             print(result)
#             await browser.close()
#     asyncio.run(test())