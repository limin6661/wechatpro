import re,html as h
from pathlib import Path
from bs4 import BeautifulSoup

data=Path("debug.html").read_text(encoding="utf-8")
m=re.search(r"var\s+content\s*=\s*\'(.+?)\';", data, re.S)
print('var content found', bool(m))
if m:
    raw=m.group(1).encode('utf-8').decode('unicode_escape')
    raw=h.unescape(raw)
    soup=BeautifulSoup(raw, 'lxml')
    text=soup.get_text("\n", strip=True)
    print('len', len(text))
    print(text[:500])
