#!/usr/bin/env python3
"""MyMany — арбитражная база цепочек обмена валют (my-many.ru). Проект RateScout по арбитражу.

Что делает: берёт направленные курсы обменников BestChange (rates.json из репозитория ratescout, raw GitHub) +
цены в USDT (history.json) + справочник валют (currencies.json), считает ВЫГОДНЫЕ цепочки обмена A→…→A
(2/3/4 звена) и рендерит статический сайт в стиле ratescout:
  • главная `/`            — монитор цепочек (топ + фильтр по стартовой валюте, режимы, сортировка, мини-бары);
  • `/c/`                  — страница цепочки: пошаговая конверсия + итог + КАЛЬКУЛЯТОР (клиентский, по ?s=&i=);
  • `/valuta/<slug>/`      — цепочки с конкретной валюты (SSR, SEO «арбитраж с BTC»), перелинковка на ratescout;
  • `data/chains/<slug>.json` — шарды базы по стартовой валюте (масштаб + быстрые страницы).

Данные ratescout обновляются ~ежечасно; крон MyMany можно гонять чаще (15 мин) — свежее станет, когда обновится
исходный rates.json. Без сети — фолбэк на кэш data/*.json. Интерфейс/футер — как у ratescout (его styles.css).
"""
import html
import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
DATA = os.path.join(ROOT, "data")
DOMAIN = "my-many.ru"
BASE = f"https://{DOMAIN}"
RS = "https://ratescout.ru"                         # для перелинковки
RS_UTM = f"{RS}/?utm_source=mymany&utm_medium=cta"
REF = "1116359"                                     # партнёрская метка BestChange (как у ratescout)
RAW = "https://raw.githubusercontent.com/sementsul/ratescout/main"
CSS = f"{RS}/assets/styles.css"                     # тот же интерфейс, что у ratescout
OG_IMAGE = f"{RS}/apple-touch-icon.png"             # карточка для соцсетей/поиска (бренд-иконка)

MODE_NAME = {2: "туда-обратно", 3: "треугольник", 4: "4 звена"}
SHARD_CAP = 200                                     # цепочек на стартовую валюту (масштаб базы)
TOP_CAP = 800                                       # цепочек в монитор на главной
HIST_TRACK = 800                                    # для скольких топ-цепочек пишем историю доходности
HIST_PTS = 720                                      # точек истории на цепочку (~30 дней при часовых данных)

VERIFY = '<meta name="yandex-verification" content="d5dd2e5c5d4ee324" />'

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

SUPP_CSS = """<style>
.mm-updnote{color:#a8a8a8;font-size:13px;margin:2px 0 10px}
.mm-stats{display:flex;gap:18px;flex-wrap:wrap;margin:12px 0}
.mm-stat{border:1px solid #245;border-radius:6px;padding:8px 14px;background:#0a0f14}
.mm-stat b{color:#55ffff;font-size:1.15rem}
.mm-stat span{display:block;color:#a8a8a8;font-size:12px}
.ch-ctl{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin:12px 0}
.ch-ctl .seg button{background:#0a0f14;border:1px solid #245;color:#7cf;padding:4px 10px;cursor:pointer;margin-right:4px;border-radius:3px}
.ch-ctl .on{background:#00aaaa;color:#111;font-weight:bold}
.ch-ctl select,.ch-ctl input{background:#0a0f14;border:1px solid #245;color:#e6edf3;padding:4px 8px;border-radius:3px}
#chTbl{width:100%;border-collapse:collapse;font-size:14px}
#chTbl th,#chTbl td{padding:6px 8px;border-bottom:1px solid #245;text-align:left;vertical-align:middle}
#chTbl td.num,#chTbl th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.ch-path a{white-space:nowrap}
.arr{color:#00aaaa;padding:0 1px}
.prof{color:#7CFC7C;font-weight:bold}
.mval{display:inline-block;min-width:56px}
.badge{display:inline-block;padding:1px 7px;border-radius:3px;font-weight:bold;font-size:12px}
.r-low{background:#0a3d0a;color:#8CFC8C}.r-mid{background:#3d3300;color:#ffd24a}.r-high{background:#4d0a0a;color:#ff8a8a}
.mbar-wrap{display:inline-block;width:54px;height:7px;background:#0a0f14;border:1px solid #245;border-radius:2px;vertical-align:middle;margin-left:7px;overflow:hidden}
.mbar-fill{display:block;height:100%}
#chWrap{overflow-x:auto}
.ch-more{margin:12px 0;text-align:center}
.ch-more button{background:#00aaaa;color:#111;border:0;padding:8px 18px;cursor:pointer;font-weight:bold;border-radius:3px}
.ch-disc{padding:12px;margin-top:16px;color:#a8a8a8;font-size:13px;border:1px solid #245;border-radius:6px}
.ch-disc b{color:#ffd24a}
.entry-links{line-height:2.1}
.e404{text-align:center;padding:30px 10px}
.e404 .big{font-size:3rem;color:#55ffff;font-weight:bold;margin:0}
/* страница цепочки */
.step-tbl{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}
.step-tbl th,.step-tbl td{padding:7px 9px;border-bottom:1px solid #245;text-align:right}
.step-tbl th:first-child,.step-tbl td:first-child{text-align:left}
.calc{border:1px solid #245;border-radius:6px;padding:14px;background:#0a0f14;margin:14px 0}
.calc input{background:#0d1117;border:1px solid #245;color:#e6edf3;padding:6px 10px;border-radius:3px;width:160px;font-size:15px}
.calc .res{font-size:1.1rem;margin-top:10px}
.calc .res b{color:#7CFC7C}
.cc-title{color:#55ffff;font-weight:bold;margin:2px 0 8px}
#chChart svg{width:100%;height:auto;display:block}
.cc-tip{position:absolute;pointer-events:none;display:none;background:#0a0f14;border:1px solid #55ffff;border-radius:4px;padding:6px 9px;font:12px/1.35 system-ui;color:#e6edf3;white-space:nowrap;transform:translate(-50%,-115%);z-index:6}
.cc-tip b{color:#7CFC7C}.cc-tip .tt-p{color:#9fb3c8}.cc-tip .tt-d{color:#ffd24a}
.ch-ranges{margin:0 0 8px;display:flex;gap:6px;flex-wrap:wrap}
.ch-ranges button{background:#0a0f14;border:1px solid #245;color:#7cf;padding:3px 12px;cursor:pointer;border-radius:3px;font-size:13px}
.ch-ranges button.on{background:#00aaaa;color:#111;font-weight:bold}
.ch-ranges button:disabled{opacity:.4;cursor:not-allowed}
/* ── мобильная адаптация ── */
@media (max-width:760px){
  /* ratescout прячет #topnav на мобиле (там бургер+app.js, которых у нас нет) — возвращаем меню */
  #topnav{display:block !important}
  #menu-top{gap:6px 14px;font-size:14px}
  #logotop{font-size:1.3rem}
  .mm-stats{gap:8px}
  .mm-stat{flex:1 1 44%;padding:8px 10px}
  .mm-stat b{font-size:1.05rem}
  .ch-ctl{gap:10px}
  .ch-ctl label,.ch-ctl select{width:100%}
  .ch-ctl .seg{display:flex;flex-wrap:wrap}
  #chTbl{font-size:13px}
  #chTbl th,#chTbl td{padding:5px 6px}
  .ch-path a{white-space:normal}
  .cc-tip{max-width:80vw;white-space:normal}
  .calc input{width:100%;max-width:240px}
  .step-tbl{font-size:13px}
  .step-tbl th,.step-tbl td{padding:6px 5px}
  #footer .links{line-height:2}
}
@media (max-width:460px){
  .mbar-wrap{display:none}          /* мини-бары прячем на узких — цифры остаются */
  .mm-stat{flex:1 1 100%}
}
</style>"""


def fetch_json(url, cache_name):
    """GET JSON с фолбэком на кэш data/<cache_name> (если raw-GitHub недоступен на сборке)."""
    path = os.path.join(DATA, cache_name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MyMany/2.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.load(r)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        return d, True
    except Exception as e:                          # noqa: BLE001
        print(f"  raw-GitHub недоступен для {cache_name} ({e}); беру кэш")
        if os.path.exists(path):
            return json.load(open(path, encoding="utf-8")), False
        return None, False


def esc(s):
    return html.escape(str(s))


def bc_link(CUR, frm, to):
    """Реф-ссылка на обмен frm→to в BestChange (как у ratescout)."""
    f, t = CUR.get(frm, {}), CUR.get(to, {})
    if f.get("num") or t.get("num"):
        return f"https://www.bestchange.ru/index.php?mt=rates&from={f.get('id')}&to={t.get('id')}&p={REF}"
    return f"https://www.bestchange.ru/{frm}-to-{to}.html?p={REF}"


def compute_shards(RATES, HIST, CUR):
    """Считает выгодные цепочки и раскладывает по стартовой валюте. Возврат: (shards, stats)."""
    MINC = 2                                          # ≥2 обменников на леге (максимум цепочек, но без «одиночек»)
    usd = {s: (h[-1][1] if h else None) for s, h in HIST.items()}
    R = {}
    for k, v in RATES.items():
        if ">" not in k:
            continue
        a, b = k.split(">", 1)
        try:
            rate = float(v["rate"])
        except (ValueError, KeyError, TypeError):
            continue
        if rate <= 0:
            continue
        cnt = int(v.get("count", 0) or 0)
        if cnt < MINC or float(v.get("reserve", 0) or 0) <= 0:
            continue
        pa, pb = usd.get(a), usd.get(b)
        if pa and pb and pb > 0:                      # отсев битых курсов по USDT-справедливому
            f = pa / pb
            if rate > f * 1.5 or rate < f * 0.66:
                continue
        R.setdefault(a, {})[b] = (rate, cnt)
    tkf = lambda s: (CUR.get(s, {}).get("ticker") or s)
    deg = sorted(R, key=lambda n: -len(R[n]))

    def risk(legs, minc, prof):
        base = {2: 8, 3: 20, 4: 35}[legs]
        liq = 30 if minc < 5 else 18 if minc < 10 else 10 if minc < 20 else 4 if minc < 40 else 0
        hot = 30 if prof > 15 else 18 if prof > 8 else 9 if prof > 4 else 3 if prof > 2 else 0
        return max(5, min(95, base + liq + hot))

    raw = defaultdict(list)                           # start slug -> [(profit, cyc, minCount)]
    # 2 звена — туда-обратно
    for a in R:
        for b, (r1, c1) in R[a].items():
            e = R.get(b, {}).get(a)
            if e and (r1 * e[0] - 1) > 0:
                raw[a].append(((r1 * e[0] - 1) * 100, [a, b], min(c1, e[1])))
    # 3 звена — треугольник (стартовые из ядра 250; леги — любые ликвидные)
    for a in deg[:250]:
        for b, (r1, c1) in R[a].items():
            Rb = R.get(b)
            if not Rb:
                continue
            for c, (r2, c2) in Rb.items():
                if c == a:
                    continue
                e = R.get(c, {}).get(a)
                if e and (r1 * r2 * e[0] - 1) > 0:
                    raw[a].append(((r1 * r2 * e[0] - 1) * 100, [a, b, c], min(c1, c2, e[1])))
    # 4 звена — ядро 45 (иначе O(n⁴))
    core4 = deg[:45]
    cs = set(core4)
    for a in core4:
        for b, (r1, c1) in R[a].items():
            if b not in cs:
                continue
            for c, (r2, c2) in R.get(b, {}).items():
                if c not in cs or c == a:
                    continue
                for d, (r3, c3) in R.get(c, {}).items():
                    if d not in cs or d == a or d == b:
                        continue
                    e = R.get(d, {}).get(a)
                    if e and (r1 * r2 * r3 * e[0] - 1) > 0:
                        raw[a].append(((r1 * r2 * r3 * e[0] - 1) * 100, [a, b, c, d], min(c1, c2, c3, e[1])))

    shards, total = {}, 0
    for a, rows in raw.items():
        rows.sort(key=lambda x: x[0], reverse=True)
        seen, out = set(), []
        for prof, cyc, mc in rows:
            key = tuple(tkf(s) for s in cyc)
            if len(set(key)) < len(cyc) or key in seen:   # повтор тикера / дубль набора
                continue
            seen.add(key)
            nodes = [[s, tkf(s), CUR.get(s, {}).get("name", s)] for s in cyc + [cyc[0]]]
            legs = []
            for i in range(len(cyc)):
                x, y = cyc[i], cyc[(i + 1) % len(cyc)]
                r, c = R[x][y]
                legs.append([r, c, bc_link(CUR, x, y)])   # полная точность — иначе калькулятор врёт на крипта→фиат
            out.append({"m": len(cyc), "n": nodes, "l": legs,
                        "p": round(prof, 2), "r": risk(len(cyc), mc, prof), "c": mc})
            if len(out) >= SHARD_CAP:
                break
        if out:
            shards[a] = out
            total += len(out)
    return shards, {"currencies": len(shards), "chains": total, "nodes": len(R)}


# ─────────────────────────── шаблоны (интерфейс ratescout) ───────────────────────────
def head(title, desc, canonical, extra_ld="", robots=""):
    robots_tag = f'<meta name="robots" content="{robots}">\n' if robots else ""
    canon_tag = f'<link rel="canonical" href="{canonical}">\n' if canonical else ""
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{VERIFY}
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{robots_tag}{canon_tag}<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="MyMany · арбитраж RateScout">
<meta property="og:image" content="{OG_IMAGE}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{OG_IMAGE}">
<link rel="stylesheet" href="{CSS}">
<link rel="icon" href="{RS}/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="{OG_IMAGE}">
{extra_ld}
{ANALYTICS}
{SUPP_CSS}
</head>
<body>
<div id="wrapper">
<div id="header">
  <h1 id="logotop"><a href="/"><span class="logo">[⇄]</span> MyMany<span class="tld">.ru</span></a>
    <small style="color:#a8a8a8"> · арбитраж</small></h1>
</div>
<div id="topnav" class="doscyan dosborder">
  <ul id="menu-top">
    <li><a href="/">Монитор цепочек</a></li>
    <li><a href="/valuta/bitcoin/">С биткоина</a></li>
    <li><a href="/valuta/tether-trc20/">С USDT</a></li>
    <li><a href="{RS}/monitor/">RateScout&nbsp;монитор</a></li>
    <li><a href="{RS}/tsepochki/">RateScout&nbsp;цепочки</a></li>
  </ul>
</div>
<div id="main"><div id="content" style="float:none;width:100%">"""


def foot():
    year = datetime.now(timezone.utc).year
    return f"""
  </div></div>
<div id="footer">
  <div class="disc"><b>MyMany</b> — проект <a href="{RS}/" rel="noopener">RateScout</a> по арбитражу. База выгодных
    цепочек обмена валют по данным мониторинга обменников
    <a href="https://www.bestchange.ru/?p={REF}" rel="nofollow sponsored">BestChange</a>, обновление автоматическое.
    Доходность цепочек <b>теоретическая</b> (лучшие курсы на момент обновления): резервы, лимиты, верификация,
    комиссии сети и время исполнения снижают результат — это не оферта и не финансовая рекомендация.</div>
  <div class="links">
    <a href="{RS_UTM}" rel="noopener">Обменять на RateScout</a> · <a href="{RS}/napravleniya/">Направления</a> ·
    <a href="{RS}/kursy/">Курсы</a> · <a href="{RS}/heatmap/">Тепловая карта</a> · <a href="{RS}/tsepochki/">Цепочки</a> ·
    <a href="{RS}/o-servise/">О сервисе</a> · <a href="{RS}/aml/">AML-проверка</a> · <a href="{RS}/vidzhet/">Виджет</a> ·
    <a href="{RS}/redakciya/">О редакции</a> ·
    <a href="https://blogger.ratescout.ru/" target="_blank" rel="noopener me">Блог</a> ·
    <a href="https://t.me/ratescout_kurs" target="_blank" rel="noopener me">Telegram</a> ·
    <a href="https://mastodon.social/@ratescout_ru" target="_blank" rel="noopener me">Mastodon</a> ·
    <a href="https://www.yell.ru/moscow/com/ratescout-ru_14524615/" target="_blank" rel="noopener me">Yell.ru</a> ·
    <a href="{RS}/raskrytie/">Раскрытие</a> · <a href="{RS}/politika/">Политика конфиденциальности</a></div>
  <div class="fine">18+. Информация носит справочный характер, не является рекламой, офертой или финансовой
    рекомендацией. Курсы меняются. © {year} MyMany · {DOMAIN} — проект RateScout.<br>
    <span class="erid">Владелец сайта: самозанятый (НПД) Семенцул Максим Геннадиевич, ИНН 381616884622.</span></div>
</div>
</div>
</body>
</html>"""


def render_home(shards, stats, stamp, top):
    updnote = f'<p class="mm-updnote">Обновлено: {esc(stamp)} · данные BestChange (через RateScout) · обновляется автоматически</p>'
    ld = ('<script type="application/ld+json">'
          + json.dumps({"@context": "https://schema.org", "@type": "WebSite",
                        "name": "MyMany — арбитраж цепочек обмена", "url": BASE + "/"}, ensure_ascii=False)
          + "</script>")
    stats_html = (
        f'<div class="mm-stats">'
        f'<div class="mm-stat"><b>{stats["chains"]:,}</b><span>цепочек в базе</span></div>'.replace(",", " ")
        + f'<div class="mm-stat"><b>{stats["currencies"]}</b><span>стартовых валют</span></div>'
        + f'<div class="mm-stat"><b>{stats["nodes"]}</b><span>валют в графе</span></div>'
        + (f'<div class="mm-stat"><b>+{top[0]["p"]:.1f}%</b><span>лучшая цепочка</span></div>' if top else "")
        + "</div>")
    data = json.dumps(top, ensure_ascii=False)
    # список стартовых валют для фильтра (по тикеру, отсорт. по числу цепочек)
    opts = sorted(shards.items(), key=lambda kv: -len(kv[1]))
    opts_html = '<option value="">все валюты</option>' + "".join(
        f'<option value="{esc(s)}">{esc((v[0]["n"][0][1]))} — {len(v)}</option>' for s, v in opts[:120])
    js = HOME_JS.replace("__DATA__", data)
    # SEO-перелинковка: популярные точки входа по стартовой валюте (внутренние ссылки на /valuta/)
    entry_links = " · ".join(
        f'<a href="/valuta/{esc(s)}/">{esc(v[0]["n"][0][1])}</a>' for s, v in opts[:40])
    entry_html = (f'<h2>Популярные точки входа</h2><p class="mon-note">Выберите валюту, которая у вас есть, — '
                  f'увидите цепочки, начинающиеся с неё:</p><p class="entry-links">{entry_links}</p>')
    about_html = ("<h2>Что такое арбитраж обмена валют</h2><p>Арбитраж — это последовательность обменов по кругу "
                  "(например, USDT → TON → карта → USDT), где из-за разницы курсов у разных обменников вы возвращаетесь "
                  "в исходную валюту с прибылью. MyMany считает такие цепочки по данным мониторинга обменников "
                  f'<a href="{RS}/" rel="noopener">BestChange/RateScout</a> и показывает доходность, риск и калькулятор. '
                  "Доходность теоретическая: перед сделкой проверяйте резерв, лимиты и комиссии у самого обменника.</p>")
    body = f"""
  <h1>Монитор арбитражных цепочек обмена</h1>
  <p class="lead">Огромная база выгодных цепочек обмена валют: обмениваешь по кругу (A→B→C→A) и возвращаешься с
    бо́льшим. Данные — лучшие курсы обменников BestChange (через RateScout), обновление автоматическое. Каждая
    цепочка открывается отдельно — с пошаговой конверсией и калькулятором.</p>
  {updnote}
  {stats_html}
  <div class="ch-ctl">
    <span class="seg" id="chModes"></span>
    <label>Старт: <select id="chCur">{opts_html}</select></label>
    <span class="seg" id="chSort">
      <button data-s="profit" class="on">доходность</button>
      <button data-s="risk">риск</button></span>
  </div>
  <div id="chWrap" class="dosborder"><table id="chTbl"><thead></thead><tbody></tbody></table></div>
  <div class="ch-more"><button id="chMore">показать ещё</button></div>
  <p class="mon-note">Мини-бар у доходности — относительно лучшей в выборке; у риска — по шкале 0–100.
    Клик по цепочке — пошаговый разбор и калькулятор.</p>
  {entry_html}
  {about_html}
  <div class="ch-disc">{DISC_HTML}</div>
""" + "<script>" + js + "</script>"
    return head("Монитор арбитражных цепочек обмена валют — доходность и калькулятор | MyMany",
                "Огромная база выгодных цепочек обмена валют (арбитраж): доходность, риск, калькулятор и пошаговая "
                "конверсия. Данные BestChange, автообновление. Проект RateScout.",
                BASE + "/", ld) + body + foot()


def render_currency(slug, chains, stamp, CUR):
    info = CUR.get(slug, {})
    nm = info.get("name", slug)
    tkr = info.get("ticker") or slug
    rows = ""
    for i, c in enumerate(chains):
        path = ' <span class="arr">→</span> '.join(esc(n[1]) for n in c["n"])
        rk = "r-low" if c["r"] < 30 else "r-mid" if c["r"] < 60 else "r-high"
        rl = "низкий" if c["r"] < 30 else "средний" if c["r"] < 60 else "высокий"
        rows += (f'<tr><td class="ch-path"><a href="/c/?s={esc(slug)}&i={i}">{path}</a></td>'
                 f'<td class="num prof">+{c["p"]:.2f}%</td>'
                 f'<td class="num"><span class="badge {rk}">{c["r"]} {rl}</span></td>'
                 f'<td class="num">≥{c["c"]}</td>'
                 f'<td class="num">{MODE_NAME[c["m"]]}</td></tr>')
    ld = ('<script type="application/ld+json">'
          + json.dumps({"@context": "https://schema.org", "@type": "CollectionPage",
                        "name": f"Арбитражные цепочки с {nm}", "url": f"{BASE}/valuta/{slug}/",
                        "isPartOf": {"@type": "WebSite", "name": "MyMany", "url": BASE + "/"},
                        "about": f"Арбитраж и выгодный обмен {nm} ({tkr})"}, ensure_ascii=False)
          + '</script><script type="application/ld+json">'
          + json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Монитор цепочек", "item": BASE + "/"},
              {"@type": "ListItem", "position": 2, "name": f"Арбитраж с {nm}", "item": f"{BASE}/valuta/{slug}/"}]},
              ensure_ascii=False)
          + "</script>")
    body = f"""
  <nav class="crumbs"><a href="/">Монитор</a> / {esc(nm)}</nav>
  <h1>Арбитражные цепочки обмена с {esc(nm)} ({esc(tkr)})</h1>
  <p class="lead">У вас есть <b>{esc(nm)}</b>? Ниже — выгодные цепочки обмена, которые начинаются с этой валюты:
    обмениваете по кругу и возвращаетесь в {esc(tkr)} с прибылью. {len(chains)} цепочек, отсортированы по доходности.
    Клик — пошаговый разбор и калькулятор.</p>
  <p class="mm-updnote">Обновлено: {esc(stamp)} · данные BestChange</p>
  <div id="chWrap" class="dosborder"><table id="chTbl"><thead>
    <tr><th>Цепочка</th><th class="num">Доходность</th><th class="num">Риск</th><th class="num">Обменников</th><th class="num">Тип</th></tr>
  </thead><tbody>{rows}</tbody></table></div>
  <p class="mon-note">Курс и обменники {esc(tkr)} — на
    <a href="{RS}/valuta/{esc(slug)}/" rel="noopener">RateScout: {esc(nm)}</a>.
    Обменять — на <a href="{RS_UTM}" rel="noopener">RateScout</a>.</p>
  <div class="ch-disc">{DISC_HTML}</div>
"""
    return head(f"Арбитраж с {nm} ({tkr}) — выгодные цепочки обмена | MyMany",
                f"Выгодные цепочки обмена, начинающиеся с {nm} ({tkr}): доходность, риск, калькулятор. "
                f"Данные BestChange. Проект RateScout.",
                f"{BASE}/valuta/{slug}/", ld) + body + foot()


def render_detail_page():
    """Единый шаблон страницы цепочки — рендерит клиентски по ?s=<slug>&i=<index> из шарда."""
    ld = ('<script type="application/ld+json">'
          + json.dumps({"@context": "https://schema.org", "@type": "WebApplication",
                        "name": "Калькулятор арбитражной цепочки", "url": BASE + "/c/",
                        "applicationCategory": "FinanceApplication", "offers": {"@type": "Offer", "price": "0"}},
                       ensure_ascii=False)
          + "</script>")
    body = """
  <nav class="crumbs"><a href="/">Монитор</a> / <span id="crumb">цепочка</span></nav>
  <h1 id="chTitle">Цепочка обмена</h1>
  <p class="lead" id="chLead">Загружаю цепочку…</p>
  <div id="chChartWrap" class="dosborder" style="position:relative" hidden>
    <div class="cc-title">📈 Как менялась доходность цепочки</div>
    <div id="ccRanges" class="ch-ranges"></div>
    <div id="chChart"></div>
    <p class="mon-note" id="ccNote"></p>
    <div id="ccTip" class="cc-tip"></div>
  </div>
  <div class="calc">
    <label>Сколько пропустить через цепочку (в стартовой валюте):
      <input id="calcIn" type="number" min="0" step="any" value="1000"></label>
    <span id="calcCur"></span>
    <div class="res" id="calcRes"></div>
  </div>
  <div id="chWrap" class="dosborder"><table class="step-tbl" id="stepTbl"><thead></thead><tbody></tbody></table></div>
  <p class="mon-note" id="chMeta"></p>
  <p class="mon-note" id="chLinks"></p>
  <div class="ch-disc">""" + DISC_HTML + """</div>
""" + "<script>" + DETAIL_JS + "</script>"
    return head("Арбитражная цепочка обмена — калькулятор и пошаговая конверсия | MyMany",
                "Пошаговый разбор арбитражной цепочки обмена валют: курс на каждом шаге, итоговый процент и "
                "калькулятор суммы. Данные BestChange. Проект RateScout.",
                BASE + "/c/", ld, robots="noindex, follow") + body + foot()


DISC_HTML = (
    "<b>Важно.</b> Доходность здесь <b>теоретическая</b> — по лучшим рекламируемым курсам обменников BestChange на "
    "момент обновления. Реальный результат почти всегда ниже: у обменников ограничены <b>резерв и лимиты</b>, часто "
    "нужна <b>верификация (KYC)</b>, перевод занимает время, есть <b>комиссии сети</b>, а курс за это время меняется — "
    "окно закрывается быстро. Региональные направления (карты AMD/KZT и т.п.) бывают с ограничениями. Это <b>не "
    "инвестиционная рекомендация и не оферта</b>. Проверяйте условия у самого обменника. 18+. "
    f'Обмен и AML-проверка — на <a href="{RS_UTM}" rel="noopener">RateScout</a>.')

HOME_JS = r"""(function(){
 var ALL=__DATA__, mode="3", sort="profit", cur="", shown=0, STEP=60;
 var mc=document.getElementById("chModes");
 [["2","2 звена"],["3","3 звена"],["4","4 звена"]].forEach(function(m){
   var b=document.createElement("button");b.textContent=m[1];b.dataset.m=m[0];
   if(m[0]===mode)b.className="on";
   b.onclick=function(){mode=m[0];[].forEach.call(mc.children,function(x){x.className=x.dataset.m===mode?"on":"";});reset();};
   mc.appendChild(b);
 });
 document.querySelectorAll("#chSort button").forEach(function(b){
   b.onclick=function(){sort=b.dataset.s;document.querySelectorAll("#chSort button").forEach(function(x){x.className=x.dataset.s===sort?"on":"";});reset();};
 });
 document.getElementById("chCur").onchange=function(){cur=this.value;reset();};
 document.getElementById("chMore").onclick=function(){shown+=STEP;paint();};
 function rc(r){return r<30?"r-low":r<60?"r-mid":"r-high";}
 function rl(r){return r<30?"низкий":r<60?"средний":"высокий";}
 function riskColor(r){return r<30?"#8CFC8C":r<60?"#ffd24a":"#ff8a8a";}
 function bar(w,c){w=Math.max(2,Math.min(100,w));return "<span class='mbar-wrap'><i class='mbar-fill' style='width:"+w.toFixed(0)+"%;background:"+c+"'></i></span>";}
 function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");}
 function cursel(){
   return ALL.filter(function(x){return x.m==mode&&(!cur||x.s===cur);})
             .sort(function(a,b){return sort==="risk"?a.r-b.r:b.p-a.p;});
 }
 function reset(){shown=STEP;paint();}
 function paint(){
   var rows=cursel(), mp=rows.reduce(function(m,r){return r.p>m?r.p:m;},0)||1;
   document.querySelector("#chTbl thead").innerHTML=
     "<tr><th>Цепочка</th><th class='num'>Доходность</th><th class='num'>Риск</th><th class='num'>Обменников</th></tr>";
   var vis=rows.slice(0,shown);
   document.querySelector("#chTbl tbody").innerHTML = vis.length? vis.map(function(c){
     return "<tr><td class='ch-path'><a href='/c/?s="+encodeURIComponent(c.s)+"&i="+c.i+"'>"+esc(c.path)+"</a></td>"+
       "<td class='num prof'><span class='mval'>+"+c.p.toFixed(2)+"%</span>"+bar(c.p/mp*100,"#7CFC7C")+"</td>"+
       "<td class='num'><span class='badge "+rc(c.r)+"'>"+c.r+" "+rl(c.r)+"</span>"+bar(c.r,riskColor(c.r))+"</td>"+
       "<td class='num'>≥"+c.c+"</td></tr>";
   }).join("") : "<tr><td colspan='4' class='mon-empty'>В этом режиме/по этой валюте выгодных цепочек нет.</td></tr>";
   document.getElementById("chMore").style.display = rows.length>shown ? "" : "none";
 }
 reset();
})();"""

DETAIL_JS = r"""(function(){
 var q=new URLSearchParams(location.search), s=q.get("s"), i=parseInt(q.get("i"),10);
 function esc(t){return String(t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");}
 function fnum(x){return x>=1000?x.toLocaleString("ru-RU",{maximumFractionDigits:2}):x>=1?x.toFixed(4):x.toPrecision(4);}
 if(!s||isNaN(i)){document.getElementById("chLead").textContent="Цепочка не указана.";return;}
 fetch("/data/chains/"+encodeURIComponent(s)+".json").then(function(r){return r.json();}).then(function(list){
   var c=list[i];
   if(!c){document.getElementById("chLead").textContent="Цепочка не найдена (данные обновились).";return;}
   var tks=c.n.map(function(n){return n[1];});
   var title=tks.join(" → ");
   document.getElementById("crumb").textContent=title;
   document.getElementById("chTitle").textContent="Цепочка: "+title;
   var rk=c.r<30?"низкий":c.r<60?"средний":"высокий";
   document.getElementById("chLead").innerHTML="Тип: <b>"+({2:"туда-обратно",3:"треугольник",4:"4 звена"}[c.m])+
     "</b>. Теоретическая доходность за круг: <b class='prof'>+"+c.p.toFixed(2)+"%</b>. Риск: "+c.r+" ("+rk+
     "). Минимум обменников на шаге: ≥"+c.c+".";
   var startTk=c.n[0][1], startNm=c.n[0][2], startSlug=c.n[0][0];
   document.getElementById("calcCur").innerHTML=" <b>"+esc(startTk)+"</b>";
   document.getElementById("chMeta").innerHTML="Курсы — лучшие среди обменников BestChange на момент обновления. "+
     "Каждый шаг открывается в BestChange для реального обмена.";
   document.getElementById("chLinks").innerHTML="Курс и обменники "+esc(startTk)+" — <a href='https://ratescout.ru/valuta/"+
     encodeURIComponent(startSlug)+"/' rel='noopener'>на RateScout: "+esc(startNm)+"</a>. Обменять — "+
     "<a href='https://ratescout.ru/?utm_source=mymany&utm_medium=chain' rel='noopener'>RateScout</a>.";
   var thead=document.querySelector("#stepTbl thead"), tbody=document.querySelector("#stepTbl tbody");
   thead.innerHTML="<tr><th>Шаг</th><th>Отдаёте</th><th>Курс</th><th>Получаете</th></tr>";
   function render(){
     var amt=parseFloat(document.getElementById("calcIn").value)||0, a0=amt, html="";
     for(var k=0;k<c.l.length;k++){
       var rate=c.l[k][0], from=c.n[k], to=c.n[k+1], got=amt*rate;
       html+="<tr><td>"+(k+1)+". <a href='"+c.l[k][2]+"' target='_blank' rel='nofollow sponsored'>"+
         esc(from[1])+" → "+esc(to[1])+"</a></td>"+
         "<td>"+fnum(amt)+" "+esc(from[1])+"</td>"+
         "<td>"+rate.toPrecision(6)+"</td>"+
         "<td>"+fnum(got)+" "+esc(to[1])+"</td></tr>";
       amt=got;
     }
     tbody.innerHTML=html;
     var prof=a0>0?(amt/a0-1)*100:0, delta=amt-a0;
     document.getElementById("calcRes").innerHTML="Вложено: <b>"+fnum(a0)+" "+esc(startTk)+
       "</b> → получено: <b>"+fnum(amt)+" "+esc(startTk)+"</b> · прибыль: <b>"+(delta>=0?"+":"")+fnum(delta)+" "+
       esc(startTk)+" ("+(prof>=0?"+":"")+prof.toFixed(2)+"%)</b>";
   }
   document.getElementById("calcIn").addEventListener("input",render);
   render();
   loadChart(c, s);
 }).catch(function(){document.getElementById("chLead").textContent="Не удалось загрузить цепочку.";});

 function loadChart(c, s){
   var box=document.getElementById("chChartWrap");
   fetch("/data/chist/"+encodeURIComponent(s)+".json").then(function(r){return r.json();}).then(function(hist){
     var key=c.n.slice(0,-1).map(function(n){return n[1];}).join("-"), ser=hist[key];
     if(!ser||ser.length<2){
       box.hidden=false;
       document.getElementById("ccNote").textContent=
         "История доходности только начала накапливаться — точки пишутся при каждом обновлении данных (≈раз в час). Загляните позже.";
       return;
     }
     setupChart(ser, c, box);
   }).catch(function(){});
 }
 function setupChart(ser, c, box){
   box.hidden=false;
   var RANGES=[["24ч",86400],["3д",259200],["7д",604800],["14д",1209600],["30д",2592000]], cur=2592000;
   var last=ser[ser.length-1][0], rb=document.getElementById("ccRanges");
   function paint(){
     var sub=ser.filter(function(p){return p[0]>=last-cur;});
     if(sub.length<2){document.getElementById("chChart").innerHTML="";
       document.getElementById("ccNote").textContent="За выбранный период точек мало — истории пока накоплено меньше.";return;}
     drawChart(sub, c, box);
   }
   rb.innerHTML="";
   RANGES.forEach(function(r){
     var n=ser.filter(function(p){return p[0]>=last-r[1];}).length;
     var b=document.createElement("button");b.textContent=r[0];b.dataset.w=r[1];
     if(n<2)b.disabled=true;
     b.onclick=function(){cur=r[1];[].forEach.call(rb.children,function(x){x.className=(+x.dataset.w===cur)?"on":"";});paint();};
     rb.appendChild(b);
   });
   [].forEach.call(rb.children,function(x){x.className=(+x.dataset.w===cur)?"on":"";});
   paint();
 }
 function drawChart(ser, c, box){
   box.hidden=false;
   var W=820,H=230,PL=52,PR=14,PT=14,PB=28;
   var x0=ser[0][0], x1=ser[ser.length-1][0]; if(x1===x0)x1=x0+1;
   var ys=ser.map(function(p){return p[1];});
   var ymin=Math.min.apply(null,ys), ymax=Math.max.apply(null,ys);
   if(ymin===ymax){ymin-=1;ymax+=1;} var pd=(ymax-ymin)*0.12; ymin-=pd; ymax+=pd;
   function X(t){return PL+(t-x0)/(x1-x0)*(W-PL-PR);}
   function Y(v){return PT+(1-(v-ymin)/(ymax-ymin))*(H-PT-PB);}
   var poly=ser.map(function(p){return X(p[0]).toFixed(1)+","+Y(p[1]).toFixed(1);}).join(" ");
   var grid="";
   for(var g=0;g<=3;g++){var v=ymin+(ymax-ymin)*g/3, yy=Y(v);
     grid+="<line x1='"+PL+"' y1='"+yy.toFixed(1)+"' x2='"+(W-PR)+"' y2='"+yy.toFixed(1)+"' stroke='#22303c'/>"+
       "<text x='6' y='"+(yy+4).toFixed(1)+"' fill='#7a8797' font-size='11'>"+v.toFixed(1)+"%</text>";}
   function dstr(t){var d=new Date(t*1000);return ("0"+d.getUTCDate()).slice(-2)+"."+("0"+(d.getUTCMonth()+1)).slice(-2);}
   var svg="<svg viewBox='0 0 "+W+" "+H+"' xmlns='http://www.w3.org/2000/svg'>"+grid+
     "<polyline points='"+poly+"' fill='none' stroke='#55ffff' stroke-width='2'/>"+
     "<text x='"+PL+"' y='"+(H-8)+"' fill='#7a8797' font-size='11'>"+dstr(x0)+"</text>"+
     "<text x='"+(W-PR)+"' y='"+(H-8)+"' fill='#7a8797' font-size='11' text-anchor='end'>"+dstr(x1)+"</text>"+
     "<circle id='ccDot' r='4' fill='#55ffff' style='display:none'/>"+
     "<rect id='ccOv' x='"+PL+"' y='"+PT+"' width='"+(W-PL-PR)+"' height='"+(H-PT-PB)+"' fill='transparent'/></svg>";
   document.getElementById("chChart").innerHTML=svg;
   document.getElementById("ccNote").textContent=ser.length+" точек · доходность за круг (%). Наведите курсор.";
   var path=c.n.map(function(n){return n[1];}).join(" → "), startTk=c.n[0][1];
   var svgEl=document.querySelector("#chChart svg"), dot=document.getElementById("ccDot"),
       tip=document.getElementById("ccTip"), ov=document.getElementById("ccOv");
   ov.addEventListener("mousemove",function(ev){
     var r=svgEl.getBoundingClientRect(), sx=(ev.clientX-r.left)/r.width*W, best=0,bd=1e9;
     for(var k=0;k<ser.length;k++){var dd=Math.abs(X(ser[k][0])-sx);if(dd<bd){bd=dd;best=k;}}
     var p=ser[best], px=X(p[0]), py=Y(p[1]), br=box.getBoundingClientRect();
     dot.setAttribute("cx",px);dot.setAttribute("cy",py);dot.style.display="";
     tip.style.display="block";tip.style.left=(ev.clientX-br.left)+"px";tip.style.top=(ev.clientY-br.top)+"px";
     var ds=new Date(p[0]*1000).toISOString().slice(0,16).replace("T"," ");
     tip.innerHTML="<div class='tt-d'>"+ds+" UTC</div><div class='tt-p'>"+path+"</div>"+
       "<div>Доходность: <b>+"+p[1].toFixed(2)+"%</b></div>"+
       (p[2]!=null?"<div>Цена "+startTk+": "+p[2]+" USDT</div>":"");
   });
   ov.addEventListener("mouseleave",function(){dot.style.display="none";tip.style.display="none";});
 }
})();"""


def render_404(popular):
    """Страница 404 (GitHub Pages отдаёт /404.html). Не индексируется, ведёт назад в базу."""
    links = " · ".join(f'<a href="/valuta/{esc(s)}/">{esc(tk)}</a>' for s, tk in popular)
    body = f"""
  <div class="e404">
    <p class="big">404</p>
    <h1>Страница не найдена</h1>
    <p class="lead">Такой страницы нет или она устарела (база цепочек обновляется автоматически, и ссылки на
      отдельные цепочки со временем меняются).</p>
    <p><a class="dosbtn" href="/">← В монитор арбитражных цепочек</a></p>
    <p class="mon-note">Популярные точки входа: {links}</p>
    <p class="mon-note">Обменять валюту по лучшему курсу — на <a href="{RS_UTM}" rel="noopener">RateScout</a>.</p>
  </div>
"""
    return head("404 — страница не найдена | MyMany", "Страница не найдена. Вернитесь в монитор арбитражных "
                "цепочек обмена MyMany.", "", robots="noindex, follow") + body + foot()


def main():
    if os.path.isdir(DIST):
        import shutil
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    os.makedirs(os.path.join(DIST, "data", "chains"), exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")

    # rates.json в ratescout не коммитится (CI) → берём его ПУБЛИЧНЫЙ экспорт с боевого сайта; остальное — из raw-GitHub
    rates, _ = fetch_json(f"{RS}/rates.json", "rates.json")
    hist, _ = fetch_json(f"{RAW}/history.json", "history.json")
    cur, _ = fetch_json(f"{RAW}/currencies.json", "currencies.json")
    if not rates or "pairs" not in rates:
        print("❌ нет rates.json (и кэша) — прерываю")
        return 1
    RATES = rates["pairs"]
    HIST = (hist or {}).get("series", {})
    CUR = (cur or {}).get("currencies", {})

    shards, stats = compute_shards(RATES, HIST, CUR)
    print(f"   цепочек: {stats['chains']} по {stats['currencies']} валютам (граф {stats['nodes']} узлов)")

    # шарды базы + топ для главной
    top = []
    for slug, chains in shards.items():
        with open(os.path.join(DIST, "data", "chains", f"{slug}.json"), "w", encoding="utf-8") as f:
            json.dump(chains, f, ensure_ascii=False, separators=(",", ":"))
        for i, c in enumerate(chains):
            path = " → ".join(n[1] for n in c["n"])
            top.append({"p": c["p"], "r": c["r"], "c": c["c"], "m": c["m"], "path": path, "s": slug, "i": i})
    top.sort(key=lambda x: x["p"], reverse=True)
    top = top[:TOP_CAP]

    # ── история доходности цепочек: пишется ВПЕРЁД, точка на каждое обновление данных (rates.generated_at) ──
    # (исторических курсов обменников нет — восстановить прошлое нельзя; копим с этого момента)
    gen_ts = int(rates.get("generated_at", 0) or int(now.timestamp()))
    ckey = lambda ch: "-".join(n[1] for n in ch["n"][:-1])
    tracked = []
    for slug, chains in shards.items():
        h = HIST.get(slug) or []
        price = h[-1][1] if h else None
        for ch in chains:
            tracked.append((ch["p"], ckey(ch), slug, price))
    tracked.sort(key=lambda x: -x[0])
    tracked = tracked[:HIST_TRACK]
    prev, _ = fetch_json(f"{BASE}/data/chain-history.json", "chain-history.json")  # прошлая история с живого сайта
    pts = (prev.get("points") if isinstance(prev, dict) else {}) or {}
    keep, by_slug_hist = {}, defaultdict(dict)
    for profit, key, slug, price in tracked:
        ser = pts.get(key, [])
        if not ser or ser[-1][0] != gen_ts:                 # не дублируем один и тот же момент данных
            ser = ser + [[gen_ts, profit, round(price, 6) if price else None]]
            ser = ser[-HIST_PTS:]
        keep[key] = ser
        by_slug_hist[slug][key] = ser
    with open(os.path.join(DIST, "data", "chain-history.json"), "w", encoding="utf-8") as f:
        json.dump({"ts": gen_ts, "points": keep}, f, ensure_ascii=False, separators=(",", ":"))
    hd = os.path.join(DIST, "data", "chist")
    os.makedirs(hd, exist_ok=True)
    for slug, d in by_slug_hist.items():
        with open(os.path.join(hd, f"{slug}.json"), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    pmax = max((len(v) for v in keep.values()), default=0)
    print(f"   история: {len(keep)} цепочек, ts={gen_ts}, макс.точек={pmax}")

    # страницы
    open(os.path.join(DIST, "index.html"), "w", encoding="utf-8").write(render_home(shards, stats, stamp, top))
    os.makedirs(os.path.join(DIST, "c"), exist_ok=True)
    open(os.path.join(DIST, "c", "index.html"), "w", encoding="utf-8").write(render_detail_page())
    for slug, chains in shards.items():
        d = os.path.join(DIST, "valuta", slug)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(render_currency(slug, chains, stamp, CUR))

    # 404 (GitHub Pages отдаёт /404.html) — популярные точки входа для навигации назад
    popular = [(s, shards[s][0]["n"][0][1]) for s in sorted(shards, key=lambda s: -len(shards[s]))[:20]]
    open(os.path.join(DIST, "404.html"), "w", encoding="utf-8").write(render_404(popular))

    # служебное
    open(os.path.join(DIST, "CNAME"), "w", encoding="utf-8").write(DOMAIN + "\n")
    open(os.path.join(DIST, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    day = now.strftime("%Y-%m-%d")
    urls = [f'  <url><loc>{BASE}/</loc><lastmod>{day}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>']
    for slug in sorted(shards, key=lambda s: -len(shards[s])):
        urls.append(f'  <url><loc>{BASE}/valuta/{slug}/</loc><lastmod>{day}</lastmod>'
                    f'<changefreq>hourly</changefreq><priority>0.7</priority></url>')
    open(os.path.join(DIST, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>")
    print(f"✅ dist/: главная + /c/ + {len(shards)} стр. валют + {len(shards)} шардов + sitemap/robots/CNAME")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
