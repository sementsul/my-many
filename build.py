#!/usr/bin/env python3
"""MyMany — генератор статического «Монитора крипторынка» (my-many.ru).

Отдельный от ratescout сайт с ДРУГИМ интентом: ratescout = «где выгодно обменять» (обменники BestChange),
MyMany = «что происходит на рынке» (обзор цен/капитализации/настроений). Ведёт на ratescout как на сервис обмена.

Данные: CoinGecko (global + markets) + alternative.me (индекс страха и жадности). SSR — данные вшиты в HTML
для индексации. Крон обновляет ежечасно. Без сети — берёт последний data/*.json (фолбэк).
"""
import html
import json
import os
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
DATA = os.path.join(ROOT, "data")
DOMAIN = "my-many.ru"
BASE = f"https://{DOMAIN}"
RATESCOUT = "https://ratescout.ru/?utm_source=mymany&utm_medium=cta"
CG = "https://api.coingecko.com/api/v3"

# Подтверждение прав в поисковых панелях (мета-теги). Google добавим, когда пришлёт свой код.
VERIFY = '<meta name="yandex-verification" content="d5dd2e5c5d4ee324" />'

# Аналитика — те же счётчики, что на ratescout (Яндекс.Метрика + Google Analytics).
# 🔴 my-many.ru нужно добавить в список доменов счётчика Метрики 111586112, иначе визиты не зачтутся.
ANALYTICS = """<!-- Yandex.Metrika -->
<script>(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
m[i].l=1*new Date();for(var j=0;j<document.scripts.length;j++){if(document.scripts[j].src===r){return;}}
k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
(window,document,'script','https://mc.yandex.ru/metrika/tag.js?id=111586112','ym');
ym(111586112,'init',{ssr:true,webvisor:true,clickmap:true,accurateTrackBounce:true,trackLinks:true});</script>
<noscript><div><img src="https://mc.yandex.ru/watch/111586112" style="position:absolute;left:-9999px;" alt=""/></div></noscript>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-PPN27D6JXS"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}
gtag('js',new Date());gtag('config','G-PPN27D6JXS');</script>"""


def fetch(url, cache_name):
    """GET JSON с фолбэком на кэш data/<cache_name>.json (если сеть недоступна)."""
    path = os.path.join(DATA, cache_name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MyMany/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        return d, True
    except Exception as e:                        # noqa: BLE001
        print(f"  сеть недоступна для {cache_name} ({e}); беру кэш")
        if os.path.exists(path):
            return json.load(open(path, encoding="utf-8")), False
        return None, False


def esc(s):
    return html.escape(str(s))


def fmt_usd(n):
    n = float(n or 0)
    if n >= 1e12:
        return f"${n / 1e12:.2f} трлн"
    if n >= 1e9:
        return f"${n / 1e9:.2f} млрд"
    if n >= 1e6:
        return f"${n / 1e6:.2f} млн"
    if n >= 1:
        return f"${n:,.2f}".replace(",", " ")
    return f"${n:.6f}".rstrip("0").rstrip(".")


def pct(n):
    n = float(n or 0)
    cls = "up" if n >= 0 else "down"
    return f'<span class="{cls}">{n:+.2f}%</span>'


def fng_label(v):
    v = int(v)
    if v <= 24:
        return "Крайний страх"
    if v <= 44:
        return "Страх"
    if v <= 55:
        return "Нейтрально"
    if v <= 74:
        return "Жадность"
    return "Крайняя жадность"


def main():
    os.makedirs(DIST, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")

    glob, _ = fetch(f"{CG}/global", "global.json")
    markets, _ = fetch(f"{CG}/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1"
                       "&price_change_percentage=24h", "markets.json")
    fng, _ = fetch("https://api.alternative.me/fng/?limit=1", "fng.json")

    if not markets:
        print("❌ нет данных markets (и кэша нет) — прерываю")
        return 1
    gd = (glob or {}).get("data", {})
    total_mc = gd.get("total_market_cap", {}).get("usd", 0)
    total_vol = gd.get("total_volume", {}).get("usd", 0)
    mc_chg = gd.get("market_cap_change_percentage_24h_usd", 0)
    btc_dom = gd.get("market_cap_percentage", {}).get("btc", 0)
    eth_dom = gd.get("market_cap_percentage", {}).get("eth", 0)

    fng_val = fng_txt = ""
    if fng and fng.get("data"):
        fng_val = fng["data"][0]["value"]
        fng_txt = fng_label(fng_val)

    # топ роста/падения из полученного набора
    valid = [c for c in markets if c.get("price_change_percentage_24h") is not None]
    gainers = sorted(valid, key=lambda c: c["price_change_percentage_24h"], reverse=True)[:5]
    losers = sorted(valid, key=lambda c: c["price_change_percentage_24h"])[:5]

    def coin_rows(coins):
        out = ""
        for c in coins:
            out += (f'<tr><td class="c-name"><b>{esc(c["symbol"].upper())}</b> '
                    f'<span class="c-full">{esc(c["name"])}</span></td>'
                    f'<td class="num">{fmt_usd(c["current_price"])}</td>'
                    f'<td class="num">{pct(c.get("price_change_percentage_24h"))}</td>'
                    f'<td class="num c-mc">{fmt_usd(c["market_cap"])}</td></tr>')
        return out

    def mover_rows(coins):
        return "".join(f'<li><b>{esc(c["symbol"].upper())}</b> {pct(c.get("price_change_percentage_24h"))}</li>'
                       for c in coins)

    top20 = coin_rows(markets[:20])

    fng_block = (f'<div class="stat"><div class="stat-v">{esc(fng_val)} · {esc(fng_txt)}</div>'
                 f'<div class="stat-l">Индекс страха и жадности</div></div>') if fng_val else ""

    # Уникальный FAQ (не дубль ratescout): объясняет метрики монитора + связывает с обменом.
    faq = [
        ("Что показывает капитализация крипторынка?",
         "Это суммарная стоимость всех криптовалют. Рост капитализации обычно означает приток денег в рынок, "
         "падение — отток. Резкие изменения за 24 часа — сигнал повышенной волатильности, когда курсы обмена «гуляют» сильнее."),
        ("Что такое доминация BTC и зачем за ней следить?",
         "Доминация биткоина — его доля в общей капитализации рынка. Когда она растёт, деньги перетекают из альткоинов "
         "в BTC (рынок осторожничает); когда падает — растёт интерес к альткоинам. Это помогает понять настроение рынка перед обменом."),
        ("Как читать индекс страха и жадности?",
         "Индекс от 0 до 100 отражает эмоции рынка: низкие значения (страх) часто совпадают с локальными «дном», высокие "
         "(жадность) — с перегревом. Это не сигнал к сделке, а фон: в «жадности» спреды и курсы бывают менее выгодными."),
        ("Чем этот монитор отличается от RateScout?",
         "MyMany показывает, ЧТО происходит на рынке (цены, капитализация, настроения). RateScout показывает, ГДЕ выгоднее "
         "обменять — это мониторинг обменных пунктов BestChange по сотням направлений с реальными курсами и резервами."),
        ("Как найти выгодный курс обмена криптовалюты?",
         "Сравнивать курсы нескольких обменников одновременно, а не идти в первый попавшийся. Именно это делает RateScout: "
         "собирает курсы, резервы и рейтинги обменных пунктов в одном месте, чтобы выбрать лучшее направление."),
        ("Что важно проверить перед обменом?",
         "Актуальный курс и резерв обменника, его рейтинг и отзывы, а для криптоадреса — базовую AML-проверку (нет ли адреса "
         "в санкционных списках). Инструменты для этого есть на RateScout."),
    ]
    faq_html = "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
    faq_schema = json.dumps({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq],
    }, ensure_ascii=False)

    schema = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Монитор крипторынка MyMany",
        "description": "Живые метрики крипторынка: цены, капитализация, доминация BTC, лидеры роста и падения, "
                       "индекс страха и жадности. Обновляется автоматически.",
        "url": BASE + "/", "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "MyMany", "url": BASE + "/"},
        "license": BASE + "/",
    }, ensure_ascii=False)
    website = json.dumps({"@context": "https://schema.org", "@type": "WebSite",
                          "name": "MyMany — монитор крипторынка", "url": BASE + "/"}, ensure_ascii=False)

    title = "Монитор крипторынка — цены, капитализация, лидеры и настроения | MyMany"
    desc = ("Живой обзор крипторынка: капитализация, доминация BTC, топ роста и падения за 24 часа, индекс страха "
            "и жадности, цены топ-50 монет. Обновляется автоматически.")

    page = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{VERIFY}
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{BASE}/">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{BASE}/">
<meta property="og:site_name" content="MyMany">
<script type="application/ld+json">{website}</script>
<script type="application/ld+json">{schema}</script>
<script type="application/ld+json">{faq_schema}</script>
{ANALYTICS}
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:#0d1117;color:#e6edf3;font:16px/1.5 system-ui,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:960px;margin:0 auto;padding:20px 16px 60px}}
header h1{{font-size:1.5rem;margin:.2em 0}}
.sub{{color:#9aa7b4;margin:0 0 4px}}
.upd{{color:#6b7785;font-size:.8rem}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:22px 0}}
.stat{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px}}
.stat-v{{font-size:1.25rem;font-weight:700}}
.stat-l{{color:#9aa7b4;font-size:.82rem;margin-top:4px}}
h2{{font-size:1.15rem;margin:28px 0 10px;border-bottom:1px solid #21262d;padding-bottom:6px}}
.movers{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.movers ul{{list-style:none;margin:0;padding:0}}
.movers li{{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #1b2129}}
.movers h3{{font-size:.95rem;margin:0 0 6px;color:#9aa7b4}}
table{{width:100%;border-collapse:collapse;font-size:.92rem}}
th,td{{padding:8px 10px;text-align:right;border-bottom:1px solid #1b2129;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
thead th{{color:#9aa7b4;font-weight:600}}
.c-full{{color:#6b7785;font-weight:400;font-size:.85em}}
.c-mc{{color:#9aa7b4}}
.up{{color:#2ea043}}.down{{color:#f85149}}
.tablewrap{{overflow-x:auto}}
.cta{{display:block;margin:34px 0 10px;padding:18px;background:#161b22;border:1px solid #2ea043;
border-radius:12px;text-align:center}}
.cta a{{display:inline-block;margin-top:10px;background:#2ea043;color:#fff;padding:12px 26px;border-radius:8px;
text-decoration:none;font-weight:600}}
.why{{background:#161b22;border:1px solid #21262d;border-radius:12px;padding:18px 20px;margin:28px 0}}
.why h2{{margin-top:0;border:0}}
.why p{{color:#c3ccd6;margin:.5em 0}}
.why a.more{{color:#2ea043;font-weight:600;text-decoration:none}}
details{{background:#12171e;border:1px solid #21262d;border-radius:8px;padding:0 14px;margin:8px 0}}
details summary{{cursor:pointer;padding:12px 0;font-weight:600;list-style:none}}
details summary::-webkit-details-marker{{display:none}}
details summary::before{{content:"+ ";color:#2ea043}}
details[open] summary::before{{content:"– "}}
details p{{color:#9aa7b4;margin:0 0 14px}}
footer{{margin-top:40px;color:#6b7785;font-size:.82rem;border-top:1px solid #21262d;padding-top:16px}}
footer a{{color:#9aa7b4}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <p class="sub">MyMany</p>
  <h1>Монитор крипторынка</h1>
  <p class="upd">Обновлено: {esc(stamp)} · данные CoinGecko</p>
</header>

<section class="stats">
  <div class="stat"><div class="stat-v">{fmt_usd(total_mc)}</div><div class="stat-l">Капитализация рынка</div></div>
  <div class="stat"><div class="stat-v">{pct(mc_chg)}</div><div class="stat-l">Изменение за 24ч</div></div>
  <div class="stat"><div class="stat-v">{btc_dom:.1f}%</div><div class="stat-l">Доминация BTC</div></div>
  <div class="stat"><div class="stat-v">{eth_dom:.1f}%</div><div class="stat-l">Доминация ETH</div></div>
  <div class="stat"><div class="stat-v">{fmt_usd(total_vol)}</div><div class="stat-l">Объём торгов 24ч</div></div>
  {fng_block}
</section>

<h2>Лидеры за 24 часа</h2>
<div class="movers">
  <div><h3>📈 Рост</h3><ul>{mover_rows(gainers)}</ul></div>
  <div><h3>📉 Падение</h3><ul>{mover_rows(losers)}</ul></div>
</div>

<h2>Топ-20 монет по капитализации</h2>
<div class="tablewrap">
<table>
<thead><tr><th>Монета</th><th>Цена</th><th>24ч</th><th>Капитализация</th></tr></thead>
<tbody>{top20}</tbody>
</table>
</div>

<div class="cta">
  <div>Нашли момент для обмена? Сравните курсы обменников и обменяйте по лучшему.</div>
  <a href="{RATESCOUT}" rel="noopener">Перейти на RateScout →</a>
</div>

<h2>Что показывает монитор</h2>
<p style="color:#9aa7b4">MyMany — независимый обзор крипторынка: суммарная капитализация, доминация ключевых
монет, лидеры роста и падения и индекс настроений. Данные обновляются автоматически из CoinGecko.
Хотите не просто следить, а обменять валюту по выгодному курсу — воспользуйтесь мониторингом обменников
<a href="{RATESCOUT}" style="color:#2ea043">RateScout</a>.</p>

<section class="why">
  <h2>Почему обменивать через RateScout</h2>
  <p>Монитор выше показывает <b>настроение рынка</b>, но для самой сделки важен другой вопрос — <b>где курс выгоднее</b>.
     Идти в первый попавшийся обменник — почти всегда терять на спреде.</p>
  <p><b>RateScout</b> решает это: сравнивает курсы, резервы и рейтинги десятков обменных пунктов по сотням направлений
     сразу, плюс даёт базовую AML-проверку криптоадреса. Вы видите лучший вариант, а не первый.</p>
  <p><a class="more" href="{RATESCOUT}" rel="noopener">Сравнить курсы обмена на RateScout →</a></p>
</section>

<h2>Частые вопросы</h2>
<div class="faq">{faq_html}</div>

<footer>
  © MyMany · {DOMAIN} · данные CoinGecko / alternative.me · не финансовая рекомендация, 18+.<br>
  Обмен валют и криптовалют — на <a href="{RATESCOUT}" rel="noopener">RateScout</a>.
</footer>
</div>
</body>
</html>"""

    open(os.path.join(DIST, "index.html"), "w", encoding="utf-8").write(page)
    open(os.path.join(DIST, "CNAME"), "w", encoding="utf-8").write(DOMAIN + "\n")
    open(os.path.join(DIST, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    open(os.path.join(DIST, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>{BASE}/</loc><lastmod>{now.strftime("%Y-%m-%d")}</lastmod>'
        '<changefreq>hourly</changefreq><priority>1.0</priority></url>\n</urlset>')
    print(f"✅ dist/: index.html ({len(page)//1024}KB) + sitemap + robots + CNAME · капитализация {fmt_usd(total_mc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
