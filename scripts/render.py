"""Render the animated profile panels.

Writes contributions-{light,dark}.svg and dev-news-{light,dark}.svg into --out.
GitHub draws README SVGs as <img>, so everything here is CSS @keyframes only:
no script, no external fonts (glyph subsets are embedded as base64 woff2).

Exits non-zero if any source fails, so the workflow keeps the previous render.
"""
import argparse, base64, datetime, html, io, json, os, re, sys, urllib.error, urllib.request

LOGIN = 'dakcoe'
DEV_NEWS_INDEX = 'https://dev-news.net/data/search-index-{month}.json'
W = 840

THEMES = {
    'light': dict(bg='#ffffff', panel='#f6f6f9', line='#e4e4ec', tx='#1c1c22', tx2='#54545f', tx3='#8b8b98',
                  pri='#7c6ee6', lv=['#ececf3', '#d4cff8', '#ab9ff0', '#7c6ee6', '#4b3fc0'], gh='#1f2328', gh_fg='#ffffff'),
    'dark': dict(bg='#0d1117', panel='#161b22', line='#2a313c', tx='#e6edf3', tx2='#a4adb8', tx3='#6e7681',
                 pri='#9d92f0', lv=['#1b2029', '#3d3680', '#5a4fc0', '#8a7df0', '#c4bcff'], gh='#e6edf3', gh_fg='#0d1117'),
}
# dev-news.net 사이트의 출처 색
SOURCES = {'hackernews': ('HN', '#ff6600'), 'geeknews': ('GeekNews', '#2f7de0'), 'github': ('GitHub', None),
           'rss': ('RSS', '#d9902b'), 'devto': ('DEV', '#3b49df'), 'anthropic': ('Anthropic', '#d97757'),
           'lobsters': ('Lobsters', '#ac130d')}

FONTS = [  # (css family, weight, file)
    ('dk-mono', 400, 'IBMPlexMono-Regular.ttf'),
    ('dk-mono', 600, 'IBMPlexMono-SemiBold.ttf'),
    ('dk-kr', 400, 'IBMPlexSansKR-Regular.ttf'),
]
MONO = "dk-mono,dk-kr,ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
KR = "dk-kr,'Apple SD Gothic Neo','Malgun Gothic',sans-serif"


def get_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'dakcoe-profile-render', **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ── data ──────────────────────────────────────────────────────────────────
def fetch_calendar(token):
    q = '''query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{
      totalContributions weeks{contributionDays{date weekday contributionCount}}}}}}'''
    body = json.dumps({'query': q, 'variables': {'login': LOGIN}}).encode()
    res = get_json('https://api.github.com/graphql', body, {'Authorization': f'bearer {token}', 'Content-Type': 'application/json'})
    if 'errors' in res:
        raise RuntimeError(res['errors'])
    cal = res['data']['user']['contributionsCollection']['contributionCalendar']
    weeks = []
    for w in cal['weeks']:
        row = [None] * 7  # 첫 주와 마지막 주는 비어 있는 요일이 있다
        for d in w['contributionDays']:
            row[d['weekday']] = d['contributionCount']
        weeks.append(row)
    days = [d for w in cal['weeks'] for d in w['contributionDays']]
    return {'total': cal['totalContributions'], 'weeks': weeks,
            'from': days[0]['date'], 'to': days[-1]['date'],
            'active': sum(1 for d in days if d['contributionCount'])}


def fetch_dev_news(today):
    rows = []
    first = today.replace(day=1)
    for month in (first - datetime.timedelta(days=1), today):
        try:
            rows += get_json(DEV_NEWS_INDEX.format(month=month.strftime('%Y-%m')))
        except urllib.error.HTTPError as e:
            if e.code != 404:  # 새 달의 첫 수집 전에는 파일이 없다
                raise
    by_day = {}
    for r in rows:
        by_day.setdefault(r['d'], []).append(r)
    # 안내판은 12칸(6줄 × 2면)이 필요하다. 그만큼 모이지 않은 날은 건너뛴다
    for day in sorted(by_day, reverse=True):
        if len(by_day[day]) >= 12:
            return {'day': day, 'items': [{'t': r['t'], 's': r['s'], 'g': (r.get('g') or [''])[0]} for r in by_day[day]]}
    raise RuntimeError('dev-news index has no day with 12+ articles')


# ── svg ───────────────────────────────────────────────────────────────────
def svg(h, body, css, t, title):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" role="img" aria-label="{html.escape(title)}">
<title>{html.escape(title)}</title>
<style>
/*FONTS*/
text{{font-family:{MONO};fill:{t['tx']}}}
.kr{{font-family:{KR}}}
{css}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<rect x=".5" y=".5" width="{W-1}" height="{h-1}" rx="10" fill="{t['bg']}" stroke="{t['line']}"/>
{body}
</svg>'''


def cut(s, n):
    return s if len(s) <= n else s[:n - 1] + '…'


def contributions(t, cal):
    weeks = cal['weeks']
    vals = sorted(v for w in weeks for v in w if v)

    def level(v):  # 값 순위로 4단계. 하루 몰아서 한 날 때문에 나머지가 다 흐려지지 않게
        return 1 + min(3, int(vals.index(v) / max(1, len(vals) - 1) * 4))

    cs, gap, x0, y0, T = 11, 3, 70, 74, 9.0
    css = f'''.c{{transform-box:fill-box;animation:drop {T}s cubic-bezier(.5,0,.75,0) infinite both}}
@keyframes drop{{0%{{transform:translateY(-140px);opacity:1}}9%{{transform:translateY(0)}}11%{{transform:translateY(-7px)}}13%{{transform:translateY(0)}}86%{{opacity:1;transform:translateY(0)}}94%{{opacity:0;transform:translateY(0)}}100%{{opacity:0;transform:translateY(-140px)}}}}'''
    body = [f'<defs><clipPath id="clip"><rect x="0" y="50" width="{W}" height="140"/></clipPath></defs>',
            f'<text x="28" y="36" font-size="15" font-weight="600">{LOGIN} <tspan fill="{t["tx3"]}" font-weight="400">/ contributions</tspan></text>',
            f'<text x="{W-28}" y="36" font-size="13" text-anchor="end" fill="{t["tx2"]}">{cal["total"]} in the last year</text>']
    for i, n in ((1, 'Mon'), (3, 'Wed'), (5, 'Fri')):
        body.append(f'<text x="{x0-10}" y="{y0+i*(cs+gap)+9}" font-size="9" text-anchor="end" fill="{t["tx3"]}">{n}</text>')
    start = datetime.date.fromisoformat(cal['from'])
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)  # 그 주 일요일
    last = None
    for wi in range(len(weeks) - 2):
        m = (start + datetime.timedelta(days=7 * wi)).strftime('%b')
        if m != last:
            body.append(f'<text x="{x0+wi*(cs+gap)}" y="{y0-10}" font-size="9" fill="{t["tx3"]}">{m}</text>')
            last = m
    order = 0
    body.append('<g clip-path="url(#clip)">')
    for wi, w in enumerate(weeks):
        for di, v in enumerate(w):
            if v is None:
                continue
            x, y = x0 + wi * (cs + gap), y0 + di * (cs + gap)
            body.append(f'<rect x="{x}" y="{y}" width="{cs}" height="{cs}" rx="2" fill="{t["lv"][0]}"/>')
            if v:
                body.append(f'<rect class="c" x="{x}" y="{y}" width="{cs}" height="{cs}" rx="2" fill="{t["lv"][level(v)]}" style="animation-delay:{order*0.11:.2f}s"/>')
                order += 1
    body.append('</g>')
    body.append(f'<text x="28" y="{y0+7*(cs+gap)+30}" font-size="11" fill="{t["tx3"]}">한 칸 = 하루. 커밋한 날만 위에서 떨어져 쌓입니다 · {cal["active"]} active days · {cal["from"][:7]} → {cal["to"][:7]}</text>')
    return svg(y0 + 7 * (cs + gap) + 50, '\n'.join(body), css, t, f'{LOGIN} contributions')


def dev_news(t, news):
    items = news['items']
    rows, rh, y0, T = 6, 36, 78, 12.0
    css = f'''.row{{transform-box:fill-box;transform-origin:center;animation:flip {T}s infinite}}
@keyframes flip{{0%{{transform:scaleY(1)}}46%{{transform:scaleY(1)}}48%{{transform:scaleY(.05)}}50%{{transform:scaleY(1)}}96%{{transform:scaleY(1)}}98%{{transform:scaleY(.05)}}100%{{transform:scaleY(1)}}}}
.a{{animation:a {T}s steps(1) infinite both}} .b{{animation:b {T}s steps(1) infinite both}}
@keyframes a{{0%{{opacity:1}}48%{{opacity:0}}98%{{opacity:1}}}}
@keyframes b{{0%{{opacity:0}}48%{{opacity:1}}98%{{opacity:0}}}}
.dot{{animation:blink 1.2s steps(1) infinite}} @keyframes blink{{50%{{opacity:.2}}}}'''
    body = [f'<rect x="16" y="16" width="{W-32}" height="{y0+rows*rh-6}" rx="6" fill="{t["panel"]}"/>',
            '<circle class="dot" cx="38" cy="40" r="5" fill="#2ecc71"/>',
            '<text x="52" y="45" font-size="15" font-weight="600">DEV-NEWS ARRIVALS</text>',
            f'<text x="{W-34}" y="45" font-size="12" text-anchor="end" fill="{t["tx2"]}">{news["day"]} · {len(items)}건 수집</text>']
    for x, h, a in ((38, 'SOURCE', 'start'), (150, 'HEADLINE', 'start'), (W - 40, 'TOPIC', 'end')):
        body.append(f'<text x="{x}" y="68" font-size="10" letter-spacing="1.5" fill="{t["tx3"]}" text-anchor="{a}">{h}</text>')
    for r in range(rows):
        y, dl = y0 + r * rh, r * 0.18
        body.append(f'<g class="row" style="animation-delay:{dl:.2f}s">')
        body.append(f'<rect x="28" y="{y}" width="{W-56}" height="{rh-6}" rx="3" fill="{t["bg"]}" stroke="{t["line"]}"/>')
        body.append(f'<line x1="28" x2="{W-28}" y1="{y+(rh-6)/2}" y2="{y+(rh-6)/2}" stroke="{t["line"]}"/>')
        for cls, it in (('a', items[r]), ('b', items[r + rows])):
            name, col = SOURCES.get(it['s'], (it['s'], t['tx3']))
            fg = t['gh_fg'] if col is None else '#ffffff'
            col = col or t['gh']
            body.append(f'<g class="{cls}" style="animation-delay:{dl:.2f}s">'
                        f'<rect x="36" y="{y+7}" width="100" height="16" rx="3" fill="{col}"/>'
                        f'<text x="86" y="{y+19}" font-size="10.5" text-anchor="middle" font-weight="600" style="fill:{fg}">{html.escape(name)}</text>'
                        f'<text class="kr" x="150" y="{y+20}" font-size="13.5">{html.escape(cut(it["t"], 38))}</text>'
                        f'<text x="{W-40}" y="{y+20}" font-size="11" text-anchor="end" fill="{t["pri"]}">{html.escape(it["g"] or "-")}</text></g>')
        body.append('</g>')
    body.append(f'<text x="28" y="{y0+rows*rh+30}" font-size="11" fill="{t["tx3"]}">dev-news.net이 그날 모은 기사 제목이 6초마다 넘어갑니다</text>')
    return svg(y0 + rows * rh + 46, '\n'.join(body), css, t, 'dev-news arrivals')


# ── fonts ─────────────────────────────────────────────────────────────────
def embed_fonts(doc, font_dir):
    from fontTools import subset
    from fontTools.ttLib import TTFont
    chars = set(html.unescape(''.join(re.findall(r'>([^<]+)<', doc))))
    chars.discard('\n')
    faces = []
    for family, weight, file in FONTS:
        font = TTFont(os.path.join(font_dir, file))
        opts = subset.Options()
        opts.flavor = 'woff2'
        opts.drop_tables += ['meta']
        opts.layout_features = ['kern', 'liga', 'calt', 'ccmp', 'locl']
        sub = subset.Subsetter(opts)
        cmap = font.getBestCmap()
        keep = [c for c in chars if ord(c) in cmap]
        if not keep:
            continue
        sub.populate(text=''.join(keep))
        sub.subset(font)
        buf = io.BytesIO()
        font.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        faces.append(f"@font-face{{font-family:{family};font-weight:{weight};src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return doc.replace('/*FONTS*/', '\n'.join(faces))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='dist')
    ap.add_argument('--fonts', default=os.environ.get('FONT_DIR', 'fonts'))
    a = ap.parse_args()
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        sys.exit('GITHUB_TOKEN is not set')
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()
    cal = fetch_calendar(token)
    news = fetch_dev_news(today)
    os.makedirs(a.out, exist_ok=True)
    for name, fn, data in (('contributions', contributions, cal), ('dev-news', dev_news, news)):
        for theme, t in THEMES.items():
            doc = embed_fonts(fn(t, data), a.fonts)
            path = os.path.join(a.out, f'{name}-{theme}.svg')
            with open(path, 'w') as f:
                f.write(doc)
            print(f'{path}  {len(doc)//1024} KB')
    print(f'contributions {cal["total"]} ({cal["active"]} days) · dev-news {news["day"]} {len(news["items"])}건')


if __name__ == '__main__':
    main()
