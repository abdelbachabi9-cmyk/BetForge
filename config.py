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

# Identifiants the-odds-api.com
ODDS_SPORTS = [
    "soccer_france_ligue_one",
    "soccer_england_league1",
    "soccer_germany_bundesliga",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_uefa_champs_league",
    "basketball_nba",
    "basketball_euroleague",
    "tennis_atp_french_open",
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
    # Edge minimum requis pour s\u00e9lectionner un pari (5%)
    "min_value":            0.05,
    # Cote minimale accept\u00e9e par s\u00e9lection
    "min_odd":              1.30,
    # Cote maximale accept\u00e9e par s\u00e9lection
    "max_odd":              4.00,
    # Nombre cible de s\u00e9lections dans le coupon
    "target_selections":    6,
    # Nombre minimum de s\u00e9lections
    "min_selections":       4,
    # Nombre maximum de s\u00e9lections
    "max_selections":       10,
    # Cote totale cible du coupon
    "target_total_odd":     5.0,
    # Fourchette acceptable de cote totale (\u00e9largie pour multi-sport)
    "min_total_odd":        3.0,
    "max_total_odd":        15.0,
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
