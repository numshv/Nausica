import asyncio
from playwright.async_api import async_playwright
from database import supabase

START_PAGE = 201
END_PAGE = 229

async def scrape_cosmos_certified():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            data =[]
            for page_num in range (START_PAGE, END_PAGE+1):
                await page.goto(f"https://www.cosmos-standard.org/en/databases/approved-raw-materials/?page={page_num}")
                print("PAGE: ", page_num)
            
                # adjustable
                await page.wait_for_selector("table", timeout=15000)
                
                rows = await page.query_selector_all("table tbody tr")
                
                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) < 2:
                        continue
                    
                    inci_name = (await cols[1].inner_text()).strip()
                    pemo_pct_raw = (await cols[4].inner_text()).strip()
                    restriction = (await cols[9].inner_text()).strip()
                    
                    try:
                        bio_pct = 100 - float(pemo_pct_raw.replace("%", "").replace(",", "."))
                    except ValueError:
                        print("ValueError")
                        return ValueError #ini gue bedain
                    
                    if inci_name:
                        data.append({
                            "inci_name": inci_name,
                            "natural_origin_pct": bio_pct,
                            "data_source": "COSMOS Certified Raw Materials without Organic Content",
                            "restriction": restriction if restriction else None
                        })
                
            
            await browser.close()
            return data

async def main():
    print("starts scraping:")
    print("==================================\n")
    
    data = await scrape_cosmos_certified()
    print(f"found {len(data)} data rows")
    
    if data:
        print("Sample:", data[:3])
        
        proceed = input("Proceed to upload to supabase? (y/n): ")
        
        if(proceed == "y"):
            # sebelum upsert
            seen = set()
            unique_data = []
            for item in data:
                if item["inci_name"] not in seen:
                    seen.add(item["inci_name"])
                    unique_data.append(item)

            res = supabase.table("ingredient_master").upsert(
                unique_data, on_conflict="inci_name"
            ).execute()
                        
            print("Done: ", len(res.data), "rows inserted")

if __name__ == "__main__":
    asyncio.run(main())