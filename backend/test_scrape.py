import requests
from bs4 import BeautifulSoup
import re

r = requests.get('https://www.birdtheme.org/country/abu.html')
soup = BeautifulSoup(r.text, 'html.parser')

images = soup.find_all('img')
for img in images[:5]:
    parent = img.parent
    if parent.name == 'a':
        print(f"IMG SRC: {img.get('src')}")
        print(f"PARENT A HREF: {parent.get('href')}")
    else:
        print(f"IMG SRC: {img.get('src')} (No parent A tag)")
