import json
import os
import requests
from bs4 import BeautifulSoup
import urllib.parse

# ================= CONFIGURACIÓ =================
# Pots posar directament les claus aquí o via variables d'entorn
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DB_FILE = "vist_opos.json"

# Llista exhaustiva de cerca (Bombers, suport, escales tècniques i afins)
TERMES_CERCA = [
    # Bombers i escales directives
    "bomber",
    "bombers",
    "subinspector bombers",
    "oficial bombers",
    
    # Campanya forestal i suport operatiu DGPEIS
    "teoc",
    "aof",
    "ajudant ofici forestal",
    "operador control bombers",
    "campanya forestal",
    "epaf",
    "conductor carrecop",
    "guaita forestal",
    "taller-radio",
    
    # Cossos afins, medi natural i gestió d'emergències
    "agent rural",
    "agents rurals",
    "forestal catalana",
    "proteccio civil",
    "cecat"
]

# Paraules clau per validar la rellevància i evitar falsos positius
KEYWORDS_FILTRE = [
    "bomber", "teoc", "aof", "forestal", "epaf", "operador",
    "control", "dgpeis", "spcpeis", "incendi", "incendis",
    "rural", "protecció civil", "proteccio civil", "carrecop",
    "guaita", "cecat", "emergència", "emergencies"
]
# ===============================================

def carregar_vists():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def desar_vists(vistos):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(vistos), f, ensure_ascii=False, indent=2)

def enviar_telegram(missatge):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Avis Telegram omès - manca token o chat_id]")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": missatge,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"Error enviant Telegram: {e}")

def es_contingut_rellevant(text):
    text_lower = text.lower()
    return any(k in text_lower for k in KEYWORDS_FILTRE)

def cercar_cido():
    trobats = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    base_url = "https://cido.diba.cat/oposicions"

    for terme in TERMES_CERCA:
        params = {"paraula_clau": terme, "estat": "oberta"}
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                items = soup.select(".llista-items li, article.item-llista, .card-cerca, .result-item")
                for item in items:
                    titol_elem = item.select_one("h2, h3, a.link-detall, .titol a")
                    if titol_elem:
                        titol = titol_elem.get_text(strip=True)
                        link = titol_elem.get("href", "")
                        if link and not link.startswith("http"):
                            link = f"https://cido.diba.cat{link}"

                        if es_contingut_rellevant(titol):
                            uid = f"cido_{hash(link or titol)}"
                            trobats.append({
                                "id": uid,
                                "origen": "CIDO (Diputacions / Ajuntaments / Generalitat)",
                                "titol": titol,
                                "enllac": link
                            })
        except Exception as e:
            print(f"Error consultant CIDO amb terme '{terme}': {e}")
    return trobats

def cercar_dogc():
    trobats = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    base_url = "https://dogc.gencat.cat/ca/documentacio-per-temes/cercador-general/"
    
    queries_dogc = [
        "bomber convocatòria",
        "ajudant ofici forestal",
        "teoc bombers",
        "campanya forestal",
        "agents rurals convocatòria",
        "protecció civil convocatòria"
    ]
    
    for q in queries_dogc:
        params = {"q": q, "field": "tots"}
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                elements = soup.select(".cerca-resultat, .item-cerca, article")
                for el in elements:
                    titol_elem = el.select_one("a")
                    if titol_elem:
                        titol = titol_elem.get_text(strip=True)
                        link = titol_elem.get("href", "")
                        if link and not link.startswith("http"):
                            link = f"https://dogc.gencat.cat{link}"

                        if es_contingut_rellevant(titol):
                            uid = f"dogc_{hash(link or titol)}"
                            trobats.append({
                                "id": uid,
                                "origen": "DOGC (Generalitat de Catalunya)",
                                "titol": titol,
                                "enllac": link
                            })
        except Exception as e:
            print(f"Error consultant DOGC query '{q}': {e}")
    return trobats

def main():
    vistos = carregar_vists()
    tots = cercar_cido() + cercar_dogc()

    # Desduplicar per ID únic
    unics = {item["id"]: item for item in tots}.values()

    nous = []
    for item in unics:
        if item["id"] not in vistos:
            nous.append(item)
            vistos.add(item["id"])

    if nous:
        print(f"S'han detectat {len(nous)} novetats!")
        for n in nous:
            msg = (
                f"🚨 <b>OPOSICIÓ / BORSA DETECTADA</b> 🚨\n\n"
                f"🏛 <b>Font:</b> {n['origen']}\n"
                f"📋 <b>Convocatòria:</b> {n['titol']}\n"
                f"🔗 <b>Enllaç:</b> {n['enllac']}"
            )
            print(msg)
            enviar_telegram(msg)
        desar_vists(vistos)
    else:
        print("Cap novetat avui. Tot el registre està al dia.")

if __name__ == "__main__":
    main()
