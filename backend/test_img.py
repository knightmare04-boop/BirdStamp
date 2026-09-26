import urllib.request
import urllib.error

urls = [
    'https://www.birdtheme.org/showimages/abu/i/abu196501s.jpg',
    'https://www.birdtheme.org/showimages/abu/i/abu196501.jpg',
    'https://www.birdtheme.org/showimages/abu/i/abu196501b.jpg',
    'https://www.birdtheme.org/showimages/abu/i/abu196501l.jpg',
    'https://www.birdtheme.org/showimages/abu/i/abu196501m.jpg'
]

for u in urls:
    try:
        r = urllib.request.urlopen(u)
        print(u, '=>', r.getcode())
    except urllib.error.URLError as e:
        print(u, '=>', getattr(e, 'code', str(e)))
