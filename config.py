# ============================================================
# config.py — Configuration du générateur de coupon sportif
# ============================================================
# Obtenez vos clés API gratuites :
#   football-data.org : https://www.football-data.org/client/register
#   the-odds-api.com  : https://the-odds-api.com/#get-access
#   thesportsdb.com   : API publique, pas de clé requise (tier 1)
#
# IMPORTANT : Ne mettez JAMAIS vos clés API en dur dans ce fichier.
# Utilisez les variables d'environnement (Railway ou fichier .env local).
# ============================================================

import os

# ─── CLÉS API (lues depuis les variables d'environnement) ───
API_KEYS = {
    # football-data.org — clé gratuite (10 req/min)
    "football_data": os.getenv("FOOTBALL_DATA_KEY", ""),
    # the-odds-api.com — tier gratuit (500 req/mois)
    "odds_api":      os.getenv("ODDS_API_KEY", ""),
    # api-football via RapidAPI — tier gratuit (100 req/jour)
    "api_football":  os.getenv("API_FOOTBALL_KEY", ""),
}

# ─── ENDPOINTS API ────────────────────────────────────────────
ENDPOINTS = {
    "football_data_base": "https://api.football-data.org/v4",
    "odds_api_base":      "https://api.the-odds-api.com/v4",
    "thesportsdb_base":   "https://www.thesportsdb.com/api/v1/json/3",
    "api_football_base":  "https://api-football-v1.p.rapidapi.com/v3",
    "balldontlie_base":   "https://api.balldontlie.io/v1",
}

# ─── COMPÉTITIONS FOOTBALL À SURVEILLER ──────────────────────
# Codes football-data.org
FOOTBALL_COMPETITIONS = {
    "PL":  "Premier League",
    "PD":  "La Liga",
    "BL1": "Bundesliga",
    "SA":  "Serie A",
    "FL1": "Ligue 1",
    "CL":  "Ligue des Champions",
}

# Mapping API-Football league IDs (api-football-v1.p.rapidapi.com)
API_FOOTBALL_LEAGUES = {
    61:  "Ligue 1",           # France
    39:  "Premier League",    # Angleterre
    78:  "Bundesliga",        # Allemagne
    140: "La Liga",           # Espagne
    135: "Serie A",           # Italie
    2:   "Ligue des Champions",  # UEFA
}

# Identifiants the-odds-api.com
# NOTE SAISONNALITÉ : Ne listez que les compétitions actives sur la période.
#   - Saison football : août → mai
#   - NBA : octobre → juin
#   - Roland-Garros : fin mai → début juin (actif uniquement cette période)
#   - US Open tennis : fin août → début septembre
#   - Wimbledon / Open d'Australie : désactivés (hors saison en avril-mai)
ODDS_SPORTS = [
    # Football (les 5 grands championnats + UCL) — actifs août–mai
    "soccer_france_ligue_one",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_uefa_champs_league",
    # Basketball — NBA actif octobre–juin, EuroLeague octobre–mai
    "basketball_nba",
    "basketball_euroleague",
    # Tennis — NE DÉCOMMENTEZ que pendant la période du tournoi :
    # "tennis_atp_french_open",    # Roland-Garros : fin mai – début juin
    # "tennis_atp_us_open",        # US Open : fin août – début sept.
    # "tennis_atp_wimbledon",      # Wimbledon : fin juin – début juillet
    # "tennis_atp_australian_open",# Open d'Australie : mi-janvier
]

# ─── PARAMÈTRES DU MODÈLE DE POISSON ─────────────────────────
POISSON_PARAMS = {
    # Avantage à domicile (facteur multiplicatif sur les buts)
    "home_advantage": 1.1,
    # Nombre de buts maximum à considérer dans la distribution
    "max_goals": 10,
    # Seuil Over/Under buts
    "goals_threshold": 2.5,
    # Nombre minimum de matchs pour calculer la force d'une équipe
    "min_matches": 5,
    # Paramètre rho de correction des scores faibles (Poisson corrigé)
    # Valeur empirique fixe — idéalement à estimer par MLE sur données historiques
    # Plage réaliste : -0.05 à -0.20 selon ligue et saison
    "low_score_rho": -0.13,
    # Moyenne de buts par défaut (utilisée si pas de données dynamiques)
    # ATTENTION : varie par ligue (Bundesliga ~3.1, Serie A ~2.6, L1 ~2.5)
    # → Calculée dynamiquement dans DataFetcher si standings disponibles
    "default_league_avg_goals": 2.65,
}

# ─── PARAMÈTRES ELO (BASKETBALL) ──────────────────────────────
ELO_PARAMS = {
    # ELO de départ pour toutes les équipes
    "initial_rating": 1500,
    # Facteur K (sensibilité aux mises à jour)
    "k_factor": 20,
    # Bonus domicile en ELO
    "home_bonus": 50,
}

# ─── PARAMÈTRES VALUE BETTING ─────────────────────────────────
VALUE_BETTING = {
    # Edge minimum requis pour sélectionner un pari (5%)
    "min_value": 0.05,
    # Cote minimale acceptée par sélection
    "min_odd": 1.30,
    # Cote maximale acceptée par sélection
    "max_odd": 4.00,
    # Nombre cible de sélections dans le coupon
    "target_selections": 6,
    # Nombre minimum de sélections
    "min_selections": 4,
    # Nombre maximum de sélections
    "max_selections": 10,
    # Cote totale cible du coupon
    "target_total_odd": 5.0,
    # Fourchette acceptable de cote totale.
    # FIX v4 : max_total_odd réduit de 15.0 à 8.0 — une cote de 15 n'a
    # que ~6-7% de chance de passer, rendant la variance inacceptable.
    "min_total_odd": 3.0,
    "max_total_odd": 8.0,
}

# ─── KELLY CRITERION ────────────────────────────────────────────
KELLY = {
    # Fraction du Kelly (0.25 = quart de Kelly, recommandé pour réduire la variance)
    "fraction":      0.25,
    # Mise maximale (% du bankroll) — cap de sécurité
    "max_stake_pct": 5.0,
    # Pas de minimum forcé : si Kelly < seuil, c'est un signal de ne pas parier
}

# ─── PARAMÈTRES RÉSEAU ─────────────────────────────────────────
NETWORK = {
    # Timeout en secondes pour chaque appel API
    "timeout": 8,
    # FIX v4 : max_retries remonté de 1 à 3 — les APIs gratuites ont des
    # latences variables, 1 seule tentative génère trop de coupons vides.
    "max_retries": 3,
    # Délai initial entre les retries (secondes) — exponential backoff
    "retry_delay": 1.0,
}

# ─── CACHE ─────────────────────────────────────────────────────
CACHE = {
    # TTL du cache des données API (en secondes)
    "api_data_ttl": 3600,   # 1 heure
    # TTL du cache du coupon généré (en secondes)
    "coupon_ttl":   900,    # 15 minutes
}

# ─── MODE DÉMO ──────────────────────────────────────────────────
# Si True, utilise des données simulées réalistes (pas d'appels API)
# Contrôlé par la variable d'environnement DEMO_MODE (défaut : false)
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

# ─── UTILISATEURS AUTORISÉS ─────────────────────────────────────
# Liste de Telegram user IDs autorisés à utiliser le bot.
# Si vide, le bot est ouvert à tous (déconseillé en production).
# Exemple : ALLOWED_USERS=123456789,987654321
ALLOWED_USERS_RAW = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS = (
    [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip()]
    if ALLOWED_USERS_RAW else []
)

# ─── BACKTESTING ────────────────────────────────────────────────
BACKTEST = {
    # Fichier JSON pour stocker l'historique des coupons et résultats
    "history_file": os.getenv("BACKTEST_HISTORY_FILE", "coupon_history.json"),
    # Activer le tracking automatique des résultats
    "auto_track":   os.getenv("BACKTEST_AUTO_TRACK", "true").lower() == "true",
}
# ============================================================
# config.py — Configuration du générateur de coupon sportif
# ============================================================
# Obtenez vos clés API gratuites :
#   football-data.org : https://www.football-data.org/client/register
#   the-odds-api.com  : https://the-odds-api.com/#get-access
#   thesportsdb.com   : API publique, pas de clé requise (tier 1)
#
# IMPORTANT : Ne mettez JAMAIS vos clés API en dur dans ce fichier.
# Utilisez les variables d'environnement (Railway ou fichier .env local).
# ============================================================

import os

# ─── CLÉS API (lues depuis les variables d'environnement) ───
API_KEYS = {
    # football-data.org — clé gratuite (10 req/min)
    "football_data": os.getenv("FOOTBALL_DATA_KEY", ""),

    # the-odds-api.com — tier gratuit (500 req/mois)
    "odds_api": os.getenv("ODDS_API_KEY", ""),

    # api-football via RapidAPI — tier gratuit (100 req/jour)
    "api_football": os.getenv("API_FOOTBALL_KEY", "demo"),
}

# ─── ENDPOINTS API ──────────────────────────────────────────
ENDPOINTS = {
    "football_data_base":   "https://api.football-data.org/v4",
    "odds_api_base":        "https://api.the-odds-api.com/v4",
    "thesportsdb_base":     "https://www.thesportsdb.com/api/v1/json/3",
    "api_football_base":    "https://api-football-v1.p.rapidapi.com/v3",
    "balldontlie_base":     "https://api.balldontlie.io/v1",
}

# ─── COMPÉTITIONS FOOTBALL À SURVEILLER ──────────────────────
# Codes football-data.org
FOOTBALL_COMPETITIONS = {
    "PL":   "Premier League",
    "PD":   "La Liga",
    "BL1":  "Bundesliga",
    "SA":   "Serie A",
    "FL1":  "Ligue 1",
    "CL":   "Ligue des Champions",
}

# Mapping API-Football league IDs (api-football-v1.p.rapidapi.com)
API_FOOTBALL_LEAGUES = {
    61:  "Ligue 1",          # France
    39:  "Premier League",   # Angleterre
    78:  "Bundesliga",       # Allemagne
    140: "La Liga",          # Espagne
    135: "Serie A",          # Italie
    2:   "Ligue des Champions",  # UEFA
}

# Identifiants the-odds-api.com
ODDS_SPORTS = [
    # Football (les 5 grands championnats + UCL)
    "soccer_france_ligue_one",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_uefa_champs_league",
    # Basketball
    "basketball_nba",
    "basketball_euroleague",
    # Tennis (tournois ATP/WTA actifs selon la saison)
    "tennis_atp_french_open",
    "tennis_atp_us_open",
    "tennis_atp_wimbledon",
    "tennis_atp_australian_open",
]

# ─── PARAMÈTRES DU MODÈLE DE POISSON ────────────────────────
POISSON_PARAMS = {
    # Avantage à domicile (facteur multiplicatif sur les buts)
    "home_advantage":       1.1,
    # Nombre de buts maximum à considérer dans la distribution
    "max_goals":            10,
    # Seuil Over/Under buts
    "goals_threshold":      2.5,
    # Nombre minimum de matchs pour calculer la force d'une équipe
    "min_matches":          5,
    # Paramètre rho de correction des scores faibles (Poisson corrigé)
    # Valeur empirique fixe — idéalement à estimer par MLE sur données historiques
    "low_score_rho":        -0.13,
    # Moyenne de buts par défaut (utilisée si pas de données dynamiques)
    "default_league_avg_goals": 2.65,
}

# ─── PARAMÈTRES ELO (BASKETBALL) ────────────────────────────
ELO_PARAMS = {
    # ELO de départ pour toutes les équipes
    "initial_rating":       1500,
    # Facteur K (sensibilité aux mises à jour)
    "k_factor":             20,
    # Bonus domicile en ELO
    "home_bonus":           50,
}

# ─── PARAMÈTRES VALUE BETTING ────────────────────────────────
VALUE_BETTING = {
    # Edge minimum requis pour sélectionner un pari (5%)
    "min_value":            0.05,
    # Cote minimale acceptée par sélection
    "min_odd":              1.30,
    # Cote maximale acceptée par sélection
    "max_odd":              4.00,
    # Nombre cible de sélections dans le coupon
    "target_selections":    6,
    # Nombre minimum de sélections
    "min_selections":       4,
    # Nombre maximum de sélections
    "max_selections":       10,
    # Cote totale cible du coupon
    "target_total_odd":     5.0,
    # Fourchette acceptable de cote totale (élargie pour multi-sport)
    "min_total_odd":        3.0,
    "max_total_odd":        15.0,
}

# ─── KELLY CRITERION ──────────────────────────────────────
KELLY = {
    # Fraction du Kelly (1.0 = Kelly complet, 0.25 = quart de Kelly)
    # Le quart de Kelly est recommandé pour réduire la variance
    "fraction":             0.25,
    # Mise maximale (% du bankroll)
    "max_stake_pct":        5.0,
}

# ─── PARAMÈTRES RÉSEAU ──────────────────────────────────────
NETWORK = {
    # Timeout en secondes pour chaque appel API
    "timeout":              5,
    # Nombre de tentatives avant fallback (1 = pas de retry, échec rapide)
    "max_retries":          1,
}

# ─── MODE DÉMO ──────────────────────────────────────────────
# Si True, utilise des données simulées réalistes (pas d'appels API)
# Contrôlé par la variable d'environnement DEMO_MODE (défaut : false)
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
