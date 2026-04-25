"""
🎾 PADEL VALENCIENNES - Application Web Flask
Lance avec : python app.py
Accès local : http://localhost:5000
"""

from flask import Flask, request, render_template_string
import urllib.request
import json
import os
from datetime import datetime, date, timedelta

app = Flask(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

CLUBS_DOINSPORT = [
    {
        "nom": "TSBV Valenciennes", "emoji": "🏟️",
        "club_id": "3135a77b-6622-4f69-b844-d26d00f1e09c",
        "activites": [
            {"nom": "Padel Intérieur", "id": "73394a20-708e-4ffc-b555-977ed52b7327"},
            {"nom": "Padel Extérieur", "id": "8ee9b629-c5b1-4fd5-a680-51b1288e2527"},
        ],
        "adresse": "4 rue de l'Oiseau-Blanc, Valenciennes",
        "couleur": "#00b894",
        "lien": "https://tsb-valenciennes.doinsport.club",
    },
    {
        "nom": "Padel Football Club", "emoji": "⚽",
        "club_id": "063dbc89-6838-4f7b-a740-5b7d5d77dd68",
        "activites": [
            {"nom": "Padel", "id": "ce8c306e-224a-4f24-aa9d-6500580924dc"},
        ],
        "adresse": "130 rue du Marais, Noyelles-sur-Selle",
        "couleur": "#fdcb6e",
        "lien": "https://padelfootballclub.doinsport.club",
    },
]

PADEL4 = {
    "nom": "4PADEL Valenciennes", "emoji": "⚡",
    "adresse": "Zone de l'Aérodrome, Valenciennes",
    "couleur": "#e17055",
    "lien": "https://www.4padel.fr/reservations/slots",
    "center_id": 55, "sport_id": 3,
    "api_url": "https://api2-front.lefive.fr/bookingrules/allFields",
}

BASE = "https://api-v3.doinsport.club"
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token_4padel.txt")

# ─── Scrapers ─────────────────────────────────────────────────────────────────

def appel_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except:
        return None

def appel_post(url, payload, token=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "Origin": "https://www.4padel.fr", "User-Agent": "Mozilla/5.0"}
    if token:
        headers["Authorization"] = token
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except:
        return None

def to_utc(date_s, h_s):
    h = int(h_s.split(':')[0]) - 2
    m = h_s.split(':')[1]
    if h < 0:
        prev = (datetime.strptime(date_s, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        return f"{prev}T{str(24+h).zfill(2)}:{m}:00.000Z"
    if h >= 24:
        nxt = (datetime.strptime(date_s, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        return f"{nxt}T{str(h-24).zfill(2)}:{m}:00.000Z"
    return f"{date_s}T{str(h).zfill(2)}:{m}:00.000Z"

def scrape_doinsport(club_id, act_id, date_str, h1, h2):
    url = (f"{BASE}/clubs/playgrounds/plannings/{date_str}"
           f"?club.id={club_id}&activities.id={act_id}&from={h1}&to={h2}&bookingType=unique")
    data = appel_get(url)
    if not data:
        return []
    terrains = data if isinstance(data, list) else data.get("hydra:member", [])
    res = []
    for t in terrains:
        for a in t.get("activities", []):
            for s in a.get("slots", []):
                prices = s.get("prices", [])
                if not any(p.get("bookable") for p in prices):
                    continue
                p = prices[0]
                pp = p.get("pricePerParticipant", 0)
                nb = p.get("participantCount", 4)
                dur = p.get("duration", 5400) // 60
                res.append({"heure": s["startAt"], "terrain": t.get("name", "?"),
                             "duree": dur, "prix": int(pp * nb / 100), "prix_pp": int(pp / 100)})
    return sorted(res, key=lambda x: (x["terrain"], x["heure"]))

def scrape_4padel(date_str, h1, h2):
    try:
        token = open(TOKEN_FILE).read().strip()
    except:
        return []
    payload = {
        "startingDateZuluTime": to_utc(date_str, h1),
        "endingDateZuluTime": to_utc(date_str, h2),
        "durations": "90,120", "capacity": 4,
        "center_id": PADEL4["center_id"], "sportType_id": PADEL4["sport_id"],
        "bookingType_id": "1", "isChannelWeb": True,
        "computePriceWithDefaultCapaIfNoCapa": True,
    }
    data = appel_post(PADEL4["api_url"], payload, token)
    if not data:
        return []
    res, seen = [], set()
    for slot in data:
        start = slot.get("startingDate", "")
        if not start:
            continue
        try:
            heure = datetime.strptime(start[:19], "%Y-%m-%dT%H:%M:%S").strftime("%H:%M")
        except:
            continue
        for f in slot.get("fields", []):
            if not f.get("canBookOnline"):
                continue
            key = (heure, f.get("name"), f.get("duration"))
            if key in seen:
                continue
            seen.add(key)
            res.append({"heure": heure, "terrain": f.get("name", "Piste"),
                        "duree": f.get("duration", 90),
                        "prix": int(f.get("webPrice", 0)),
                        "prix_pp": int(f.get("participationWebPrice", 0))})
    return sorted(res, key=lambda x: (x["terrain"], x["heure"]))

def get_tous_creneaux(date_str, h1, h2):
    clubs_data = []
    for club in CLUBS_DOINSPORT:
        creneaux = []
        for act in club["activites"]:
            creneaux += scrape_doinsport(club["club_id"], act["id"], date_str, h1, h2)
        clubs_data.append({**club, "creneaux": creneaux})
    clubs_data.append({**PADEL4, "creneaux": scrape_4padel(date_str, h1, h2)})
    return clubs_data

# ─── Template HTML ────────────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🎾 Padel Valenciennes</title>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#e6edf3;font-family:"DM Sans",sans-serif;min-height:100vh}

header{padding:24px 28px;background:#161b22;border-bottom:1px solid #21262d}
header h1{font-family:"Bebas Neue",sans-serif;font-size:2.2rem;letter-spacing:3px;
  background:linear-gradient(90deg,#39d353,#58a6ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
header p{color:#8b949e;font-size:.85rem;margin-top:3px}

/* Formulaire */
.form-card{margin:24px 28px;background:#161b22;border:1px solid #21262d;
  border-radius:12px;padding:20px 24px}
.form-row{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end}
.form-group{display:flex;flex-direction:column;gap:6px}
label{color:#8b949e;font-size:.8rem;font-weight:600;letter-spacing:.5px;text-transform:uppercase}
input[type=date],select{
  background:#0d1117;border:1px solid #30363d;color:#e6edf3;
  padding:9px 14px;border-radius:8px;font-size:.9rem;font-family:"DM Sans",sans-serif;
  cursor:pointer;min-width:140px
}
input[type=date]:focus,select:focus{outline:none;border-color:#58a6ff}
.btn{
  background:#39d353;color:#000;border:none;padding:10px 24px;
  border-radius:8px;font-size:.95rem;font-weight:600;cursor:pointer;
  font-family:"DM Sans",sans-serif;white-space:nowrap
}
.btn:hover{background:#2ea043}

/* Résultats */
.results-header{
  margin:0 28px 16px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px
}
.total-badge{background:#39d353;color:#000;font-family:"Bebas Neue",sans-serif;
  font-size:1.2rem;letter-spacing:1px;padding:6px 18px;border-radius:100px}
.updated{color:#8b949e;font-size:.78rem}

/* Clubs */
.clubs{margin:0 28px 32px;display:flex;flex-direction:column;gap:20px}
.club{border:1px solid #21262d;border-radius:12px;overflow:hidden;border-top:3px solid var(--clr)}
.club-head{padding:16px 20px;background:#161b22;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.club-info{display:flex;align-items:center;gap:12px}
.club-emoji{font-size:1.6rem}
.club-name{font-size:1rem;font-weight:600}
.club-addr{color:#8b949e;font-size:.78rem;margin-top:1px}
.badge-ok{background:rgba(57,211,83,.15);color:#39d353;border:1px solid rgba(57,211,83,.3);
  padding:4px 12px;border-radius:100px;font-size:.82rem;font-weight:600}
.badge-empty{background:rgba(248,81,73,.1);color:#f85149;border:1px solid rgba(248,81,73,.2);
  padding:4px 12px;border-radius:100px;font-size:.82rem;font-weight:600}

.club-body{padding:16px 20px;background:#0d1117}
.empty{color:#8b949e;font-style:italic;font-size:.88rem}

.tgroup{margin-bottom:18px}
.tlabel{color:#8b949e;font-size:.72rem;font-weight:600;letter-spacing:.8px;text-transform:uppercase;margin-bottom:8px}
.tslots{display:flex;flex-wrap:wrap;gap:7px}

.slot{background:#161b22;border:1px solid #21262d;border-radius:9px;
  padding:9px 13px;display:flex;flex-direction:column;gap:2px;min-width:84px}
.slot b{font-family:"Bebas Neue",sans-serif;font-size:1.2rem;letter-spacing:1px}
.slot span{color:#8b949e;font-size:.72rem}
.slot small{color:#c9d1d9;font-size:.72rem;font-weight:600}
.slot-ok{border-left:3px solid #39d353}
.slot-peak{border-left:3px solid #e3b341}

.club-foot{padding:11px 20px;background:#161b22;border-top:1px solid #21262d}
.club-foot a{color:#58a6ff;text-decoration:none;font-size:.82rem}
.club-foot a:hover{text-decoration:underline}

.welcome{margin:40px 28px;text-align:center;color:#8b949e}
.welcome h2{font-family:"Bebas Neue",sans-serif;font-size:1.6rem;letter-spacing:2px;color:#e6edf3;margin-bottom:8px}

footer{text-align:center;padding:20px;color:#8b949e;font-size:.75rem;border-top:1px solid #21262d}
</style>
</head>
<body>

<header>
  <h1>🎾 Padel Valenciennes</h1>
  <p>Consultez les créneaux disponibles dans les 3 clubs du secteur</p>
</header>

<div class="form-card">
  <form method="GET" action="/recherche">
    <div class="form-row">
      <div class="form-group">
        <label>Date</label>
        <input type="date" name="date" value="{{ date_val }}" min="{{ today }}">
      </div>
      <div class="form-group">
        <label>À partir de</label>
        <select name="h1">
          {% for h in heures %}
          <option value="{{ h }}" {% if h == h1 %}selected{% endif %}>{{ h }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="form-group">
        <label>Jusqu'à</label>
        <select name="h2">
          {% for h in heures %}
          <option value="{{ h }}" {% if h == h2 %}selected{% endif %}>{{ h }}</option>
          {% endfor %}
        </select>
      </div>
      <button type="submit" class="btn">🔍 Rechercher</button>
    </div>
  </form>
</div>

{% if clubs_data %}
<div class="results-header">
  <div>
    <span style="color:#8b949e;font-size:.85rem">
      {{ date_fr }} · {{ h1 }} → {{ h2 }}
    </span>
  </div>
  <div style="display:flex;align-items:center;gap:12px">
    <span class="updated">Mis à jour à {{ now }}</span>
    <span class="total-badge">{{ total }} créneaux</span>
  </div>
</div>

<div class="clubs">
{% for club in clubs_data %}
<div class="club" style="--clr:{{ club.couleur }}">
  <div class="club-head">
    <div class="club-info">
      <span class="club-emoji">{{ club.emoji }}</span>
      <div>
        <div class="club-name">{{ club.nom }}</div>
        <div class="club-addr">📍 {{ club.adresse }}</div>
      </div>
    </div>
    {% if club.creneaux|length > 0 %}
    <span class="badge-ok">{{ club.creneaux|length }} créneau{{ 'x' if club.creneaux|length > 1 else '' }}</span>
    {% else %}
    <span class="badge-empty">Aucun créneau</span>
    {% endif %}
  </div>
  <div class="club-body">
    {% if not club.creneaux %}
    <p class="empty">Aucun créneau disponible sur cette plage horaire</p>
    {% else %}
    {% set ns = namespace(terrain='') %}
    {% for c in club.creneaux %}
      {% if c.terrain != ns.terrain %}
        {% if ns.terrain != '' %}</div></div>{% endif %}
        {% set ns.terrain = c.terrain %}
        <div class="tgroup">
        <div class="tlabel">📌 {{ c.terrain }}</div>
        <div class="tslots">
      {% endif %}
      <div class="slot {{ 'slot-peak' if c.prix > 54 else 'slot-ok' }}">
        <b>{{ c.heure }}</b>
        <span>{{ c.duree }} min</span>
        <small>{{ c.prix }}€</small>
        <span>{{ c.prix_pp }}€/pers</span>
      </div>
    {% endfor %}
    {% if ns.terrain != '' %}</div></div>{% endif %}
    {% endif %}
  </div>
  <div class="club-foot">
    <a href="{{ club.lien }}" target="_blank">🔗 Réserver sur le site →</a>
  </div>
</div>
{% endfor %}
</div>

{% else %}
<div class="welcome">
  <h2>Choisissez une date et une plage horaire</h2>
  <p>Les créneaux disponibles dans les 3 clubs s'afficheront ici</p>
</div>
{% endif %}

<footer>Données en temps réel · 3 clubs padel de Valenciennes</footer>
</body>
</html>"""

# ─── Routes ───────────────────────────────────────────────────────────────────

HEURES = [f"{h:02d}:00" for h in range(7, 24)] + ["23:30"]

@app.route("/")
def index():
    return render_template_string(
        TEMPLATE,
        clubs_data=None,
        date_val=date.today().strftime("%Y-%m-%d"),
        today=date.today().strftime("%Y-%m-%d"),
        heures=HEURES, h1="09:00", h2="23:00",
        date_fr="", total=0, now=""
    )

@app.route("/recherche")
def recherche():
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    h1 = request.args.get("h1", "09:00")
    h2 = request.args.get("h2", "23:00")

    clubs_data = get_tous_creneaux(date_str, h1, h2)
    total = sum(len(c["creneaux"]) for c in clubs_data)

    d = datetime.strptime(date_str, "%Y-%m-%d")
    jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    mois  = ["","Janvier","Février","Mars","Avril","Mai","Juin","Juillet",
             "Août","Septembre","Octobre","Novembre","Décembre"]
    date_fr = f"{jours[d.weekday()]} {d.day} {mois[d.month]} {d.year}"

    return render_template_string(
        TEMPLATE,
        clubs_data=clubs_data,
        date_val=date_str,
        today=date.today().strftime("%Y-%m-%d"),
        heures=HEURES, h1=h1, h2=h2,
        date_fr=date_fr, total=total,
        now=datetime.now().strftime("%H:%M")
    )

# ─── Lancement ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser, threading, time
    def open_browser():
        time.sleep(1)
        webbrowser.open("http://localhost:5000")
    threading.Thread(target=open_browser, daemon=True).start()
    print("\n🎾 Padel Valenciennes — Serveur lancé !")
    print("📡 Adresse locale : http://localhost:5000")
    print("⏹  Ctrl+C pour arrêter\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
