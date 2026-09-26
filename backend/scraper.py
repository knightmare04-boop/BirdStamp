import logging
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
import models
import re
import urllib.parse

logger = logging.getLogger(__name__)

BASE_URL = "https://www.birdtheme.org"
REQUEST_TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BirdStamp/1.0"}

scrape_state = {"is_running": False, "progress": 0, "total": 0, "message": ""}

def run_scrape(db: Session):
    logger.info("Starting scrape...")
    scrape_state["is_running"] = True
    scrape_state["progress"] = 0
    scrape_state["total"] = 0
    scrape_state["message"] = "Fetching country list..."

    try:
        list_url = f"{BASE_URL}/country/listc.html"
        r = requests.get(list_url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        country_links = []
        for a in soup.find_all('a'):
            href = a.get('href')
            if href and '.html' in href and '/' not in href:
                country_links.append(href)

        # Optional limit for testing/development. For production, we do all.
        # country_links = country_links[:5]

        scrape_state["total"] = len(country_links)

        for idx, link in enumerate(country_links):
            country_url = f"{BASE_URL}/country/{link}"
            logger.info("Scraping %s", country_url)
            scrape_state["message"] = f"Scraping {link}..."
            scrape_country_page(country_url, db)
            scrape_state["progress"] = idx + 1

        scrape_state["message"] = "Completed"
        logger.info("Scraping completed.")
    except Exception:
        logger.exception("Scrape failed")
        scrape_state["message"] = "Scrape failed: could not reach birdtheme.org"
    finally:
        scrape_state["is_running"] = False

def scrape_country_page(url, db: Session):
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        r.raise_for_status()
    except Exception:
        logger.exception("Failed to fetch %s", url)
        return

    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Get country name from top table
    country_name = "Unknown"
    td_country = soup.find('td', class_='country')
    if td_country:
        country_name = td_country.text.split('\n')[0].strip()

    # The structure: <a name="1"></a> -> <table> (issue) -> <span><img></span> -> <table> (data)
    anchors = soup.find_all('a', attrs={'name': re.compile(r'^\d+$')})
    
    for anchor in anchors:
        try:
            current = anchor.find_next_sibling()
            
            issue_year = ""
            release_date = ""
            stamp_type = ""
            
            # Find the issue table
            if current and current.name == 'table':
                issue_tds = current.find_all('td', class_='issue')
                if len(issue_tds) >= 3:
                    issue_year = issue_tds[0].text.strip()
                    release_date = issue_tds[1].text.strip()
                    stamp_type = issue_tds[2].text.strip()
                current = current.find_next_sibling()
            
            # Find images
            images = []
            while current and current.name in ['span', 'br']:
                if current.name == 'span':
                    img_tag = current.find('img')
                    if img_tag and img_tag.get('src'):
                        img_url = urllib.parse.urljoin(url, img_tag.get('src'))
                        images.append(img_url)
                current = current.find_next_sibling()
                
            # Find data table
            if current and current.name == 'table':
                rows = current.find_all('tr')
                img_idx = 0
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        face_value = cols[0].text.strip()
                        # handle 'and' or '=' logic simply by skipping if not a real stamp row
                        if face_value.lower() == 'and':
                            continue
                            
                        name_cell = cols[2]
                        em_tag = name_cell.find('em')
                        scientific_name = em_tag.text.strip() if em_tag else ""
                        english_name = name_cell.text.replace(scientific_name, '').strip() if em_tag else name_cell.text.strip()
                        
                        image_url = images[img_idx] if img_idx < len(images) else (images[-1] if images else "")
                        
                        # Save to db
                        existing = db.query(models.Stamp).filter_by(
                            country=country_name, 
                            year=issue_year, 
                            face_value=face_value,
                            scientific_name=scientific_name
                        ).first()
                        
                        if not existing:
                            stamp = models.Stamp(
                                country=country_name,
                                year=issue_year,
                                face_value=face_value,
                                english_name=english_name,
                                scientific_name=scientific_name,
                                category="Bird",
                                stamp_type=stamp_type,
                                release_date=release_date,
                                image_url=image_url
                            )
                            db.add(stamp)
                        
                        img_idx += 1
                db.commit()
        except Exception:
            logger.exception("Error parsing issue in %s", url)
            db.rollback()
