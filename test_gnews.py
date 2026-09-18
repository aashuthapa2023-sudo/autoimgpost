import requests, re, html

gnews_url = 'https://news.google.com/rss/articles/CBMi5AFBVV95cUxPdlRGQXBCeU81VmZNV290cHVQWTZsSUZvYXRsN2NEMnNtS0J6ZUFBT1M1RlFLdlJVYTFMeXNyTHBkZVpsX0FGUkEyRThjb2I0UXk2b2ZyU0paSnRyeUZoUTRSakRfeE9WTWxPRXYyV3FTUThIMjdvUWtjd0hMMXI2LUVHNERiczRRc2F1YlVJMU9wNVRrX0NRbTNLQWN2ekhhdGNQbjJaODgybXNJb3BfaC1jRVdnNVBBQmhTclNRQ25xM0k3eGZXUmJsU1dtYkRqdUFVekhsRkhVLVpSbmtHWmNxQ0g?oc=5'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}

r = requests.get(gnews_url, headers=headers, timeout=15, allow_redirects=True)
print('Final URL:', r.url)
print('Status:', r.status_code)

# Try og:image
patterns = [
    r'property="og:image"\s+content="([^"]+)"',
    r'content="([^"]+)"\s+property="og:image"',
    r'name="twitter:image"\s+content="([^"]+)"',
]
for pat in patterns:
    m = re.search(pat, r.text)
    if m:
        img = html.unescape(m.group(1))
        print('Found image:', img[:120])
        break
else:
    print('No og:image — checking content-type:', r.headers.get('Content-Type','?'))
    print('Page title:', re.search(r'<title>(.*?)</title>', r.text, re.I) and re.search(r'<title>(.*?)</title>', r.text, re.I).group(1))
