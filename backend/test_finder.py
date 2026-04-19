import sys
sys.path.insert(0, '.')
from app.collectors.careers_url_finder import careers_url_finder

test_domains = [
    ('agreserves.com', 'AgReserves'),
    ('blackriflecoffee.com', 'Black Rifle Coffee'),
    ('bluehost.com', 'Bluehost'),
    ('caferio.com', 'Cafe Rio'),
    ('digicert.com', 'DigiCert'),
    ('neighbor.com', 'Neighbor'),
    ('novell.com', 'Novell'),
    ('omniture.com', 'Omniture'),
    ('vidangel.com', 'VidAngel'),
    ('smule.com', 'Smule'),
    ('degreed.com', 'Degreed'),
    ('silencerco.com', 'SilencerCo'),
    ('powdr.com', 'Powdr'),
    ('zionsbancorporation.com', 'Zions Bancorporation'),
    ('sunrider.com', 'Sunrider'),
]

found = 0
total = len(test_domains)
for domain, name in test_domains:
    try:
        url, strategy, meta = careers_url_finder.find(domain, name)
        if url:
            found += 1
            print(f'[OK]   {domain:40s} -> {url[:70]}  ({strategy})')
        else:
            print(f'[NO]   {domain:40s} -> not found')
    except Exception as e:
        print(f'[ERR]  {domain:40s} -> {e}')

print(f'\nResult: {found}/{total} careers URLs found ({found*100//total}%)')
