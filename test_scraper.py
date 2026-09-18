import sys
sys.path.insert(0, 'd:/Img post pipeline')
from modules.web_scraper import fetch_web_news

print('--- Testing NETFLIX category ---')
posts = fetch_web_news(category='netflix', limit=3, max_hours_old=72)
for p in posts:
    cap = p['caption'][:70]
    img = p['image_url'][:80]
    ts  = p['created_time']
    print(f'  Title : {cap}')
    print(f'  Image : {img}')
    print(f'  Time  : {ts}')
    print()

print('--- Testing HOLLYWOOD category ---')
posts2 = fetch_web_news(category='hollywood', limit=3, max_hours_old=72)
for p in posts2:
    cap = p['caption'][:70]
    img = p['image_url'][:80]
    print(f'  Title : {cap}')
    print(f'  Image : {img}')
    print()
