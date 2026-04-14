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
    # BallDontLie — optionnel (tier public sans clé, tier payant avec clé)
    "balldontlie":   os.getenv("BALLDONTLIE_API_KEY", ""),
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

# ─── ALIAS D'ÉQUIPES (normalisation cross-API) ────────────────
# Utilisé par normalize_team_name() dans coupon_generator.py pour
# résoudre les divergences de nommage entre football-data.org, the-odds-api
# et TheSportsDB. Clés en minuscules normalisées.
TEAM_ALIASES: dict = {
    # Football — abréviations courantes
    "psg":                "paris saint-germain",
    "man utd":            "manchester united",
    "man united":         "manchester united",
    "man city":           "manchester city",
    "inter":              "inter milan",
    "internazionale":     "inter milan",
    "atletico":           "atletico madrid",
    "atm":                "atletico madrid",
    "spurs":              "tottenham hotspur",
    "tottenham":          "tottenham hotspur",
    "wolves":             "wolverhampton",
    "wolverhampton wanderers": "wolverhampton",
    "bvb":                "borussia dortmund",
    "dortmund":           "borussia dortmund",
    "bayer":              "bayer leverkusen",
    "leverkusen":         "bayer leverkusen",
    "rb leipzig":         "leipzig",
    "rasenballsport":     "leipzig",
    "newcastle":          "newcastle united",
    "west ham":           "west ham united",
    "brighton":           "brighton & hove albion",
    "sheffield":          "sheffield united",
    "nottm forest":       "nottingham forest",
    "nott'm forest":      "nottingham forest",
    "ac milan":           "milan",
    "as roma":            "roma",
    "ss lazio":           "lazio",
    "ssc napoli":         "napoli",
    "juventus fc":        "juventus",
    "real sociedad":      "sociedad",
    "athletic bilbao":    "athletic club",
    "betis":              "real betis",
    "villarreal cf":      "villarreal",
    "sevilla fc":         "sevilla",
    "om":                 "olympique de marseille",
    "marseille":          "olympique de marseille",
    "ol":                 "olympique lyonnais",
    "lyon":               "olympique lyonnais",
    "asm":                "as monaco",
    "monaco":             "as monaco",
    "ogc nice":           "nice",
    "stade rennais":      "rennes",
    "rc lens":            "lens",
    "losc":               "lille",
    "losc lille":         "lille",
    "girondins":          "bordeaux",
}

# ─── PARAMÈTRES DU MODÈLE DE POISSON ─────────────────────────
POISSON_PARAMS = {
    # Avantage à domicile (facteur multiplicatif sur les buts)
    "home_advantage": 1.1,
    # Nombre de buts maximum à considérer dans la distribution
    "max_goals": 10,
    # Seuil Over/Under buts
    "goals_threshold": 2.5,
    # Nombre minimum de matchs pour calculer la force d'une équipe
    # FIX v8 : redescendu à 5 — 10 était trop strict en début de saison
    # (août–oct) et causait un pipeline vide. 5 est un compromis acceptable :
    # légère variance mais assez de données pour la distribution de Poisson.
    "min_matches": 5,
    # R3 — Rho de correction des scores faibles (Dixon-Coles simplifié) PAR LIGUE
    # Valeurs empiriques issues de la littérature et ajustées par ligue :
    #   Ligues très défensives (SA, L1) : rho plus négatif
    #   Ligues à buts (BL1) : rho plus faible en valeur absolue
    # → Idéalement à estimer par MLE sur données historiques de la saison
    "league_rho": {
        "PL":  -0.11,   # Premier League (Angleterre)
        "PD":  -0.12,   # La Liga (Espagne)
        "BL1": -0.09,   # Bundesliga (Allemagne) — ligue la plus offensive
        "SA":  -0.15,   # Serie A (Italie) — ligue la plus défensive
        "FL1": -0.14,   # Ligue 1 (France)
        "CL":  -0.10,   # Ligue des Champions — matchs ouverts
    },
    # Rho par défaut utilisé si la ligue n'est pas dans league_rho
    "default_rho": -0.13,
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

# ─── PARAMÈTRES TENNIS (ELO-like + surface + forme + H2H) ────
TENNIS_PARAMS = {
    # Poids de la performance sur surface dans le calcul du rating
    "surface_weight": 0.15,
    # Poids de la forme récente (derniers matchs)
    "form_weight": 0.08,
    # Poids du head-to-head historique entre les deux joueurs
    "h2h_weight": 0.10,
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
    # Nombre minimum de sélections (mode dégradé : 3 si le pool est réduit)
    # FIX v8 : réduit de 4 à 3 — évite de rejeter un coupon avec 3 bons paris
    "min_selections": 3,
    # Nombre maximum de sélections
    "max_selections": 10,
    # Cote totale cible du coupon
    "target_total_odd": 5.0,
    # Fourchette acceptable de cote totale.
    # FIX v8 : max_total_odd relevé de 8.0 à 15.0 — avec min_selections=3 et
    # des cotes individuelles typiques (1.5–3.5), le produit dépasse facilement 8.0.
    # 8.0 provoquait un coupon systématiquement hors fourchette → inacceptable.
    # Compromis : 15.0 (~6-7% de taux de réussite) reste raisonnable pour un
    # coupon value-betting multi-sélections.
    "min_total_odd": 3.0,
    "max_total_odd": 15.0,
    # R6 : Limite de sélections par ligue/compétition dans le coupon
    # Évite qu'un coupon contienne 6 matchs de Premier League par exemple.
    "max_per_league": 3,
    # FIX v8 : score de confiance minimum abaissé de 3.0 à 2.0
    # 3.0 était trop strict : avec incertitude sqrt(N/20), un match à 10 matchs
    # et Kelly frac ~1.5% donnait confiance 2.1 → rejet injustifié.
    "min_confidence": 2.0,
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
    "timeout": 10,
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

# ─── ELO NBA (R2) ───────────────────────────────────────────────
ELO_PARAMS.update({
    # Fichier JSON des ratings ELO pré-entraînés (généré par nba_elo_bootstrap.py)
    "ratings_file":      os.getenv("ELO_RATINGS_FILE", "nba_elo_ratings.json"),
    # Saisons à bootstrapper (liste d'entiers)
    "bootstrap_seasons": [2025, 2026],
})

# ─── MARCHÉS STATS (R9 — synchronisé depuis GitHub) ─────────────
# Marchés statistiques football : corners, fautes, cartons, tirs, passes
STATS_MARKETS = {
    "corners": {
        "threshold":     9.5,       # Seuil Over/Under corners
        "market_key":    "corners",
        "min_data_pts":  10,        # Minimum de matchs pour activer ce marché
    },
    "cards": {
        "threshold":     3.5,       # Seuil Over/Under cartons
        "market_key":    "cards",
        "min_data_pts":  10,
    },
    "fouls": {
        "threshold":     20.5,      # Seuil Over/Under fautes totales
        "market_key":    "fouls",
        "min_data_pts":  10,
    },
}

# ─── AVANTAGE DOMICILE PAR LIGUE (R9) ────────────────────────────
# Facteur multiplicatif d'avantage domicile spécifique à chaque ligue.
# Utilisé pour affiner le home_advantage de POISSON_PARAMS par ligue.
# Source : analyse statistique des 5 dernières saisons.
LEAGUE_HOME_ADVANTAGE = {
    "PL":  1.10,   # Premier League — avantage modéré
    "PD":  1.12,   # La Liga — avantage légèrement supérieur
    "BL1": 1.08,   # Bundesliga — avantage faible (matchs ouverts)
    "SA":  1.15,   # Serie A — avantage domicile plus marqué
    "FL1": 1.11,   # Ligue 1
    "CL":  1.07,   # Ligue des Champions — avantage réduit (matchs neutres rares)
}

# ─── MOYENNE DE BUTS PAR LIGUE (R9) ──────────────────────────────
# Valeurs de référence par ligue — remplacées dynamiquement si standings dispo.
LEAGUE_AVG_GOALS = {
    "PL":  2.85,   # Premier League
    "PD":  2.70,   # La Liga
    "BL1": 3.10,   # Bundesliga — la plus offensive
    "SA":  2.60,   # Serie A — la plus défensive
    "FL1": 2.55,   # Ligue 1
    "CL":  2.75,   # Ligue des Champions
}

# ─── BASE DE DONNÉES SQLite (R9) ─────────────────────────────────
DATABASE = {
    # Chemin du fichier SQLite
    "path":       os.getenv("DB_PATH", "apex.db"),
    # Activer la persistance SQLite (nécessite database.py)
    "enabled":    os.getenv("DB_ENABLED", "true").lower() == "true",
}

# ─── LINE MOVEMENT (R9) ──────────────────────────────────────────
# Suivi des mouvements de cotes pour détecter les sharp money
LINE_MOVEMENT = {
    # Variation minimale de cote pour déclencher une alerte (%)
    "alert_threshold_pct": 5.0,
    # Fenêtre de temps pour calculer le mouvement (secondes)
    "window_seconds":       3600,
    # Activer le suivi des mouvements de cotes
    "enabled":              os.getenv("LINE_MOVEMENT_ENABLED", "false").lower() == "true",
}

# ─── AFFICHAGE (R9) ──────────────────────────────────────────────
DISPLAY = {
    # Nombre maximum de sélections à afficher dans le message Telegram
    "max_selections_display": 10,
    # Afficher les probabilités modèle dans le message Telegram
    "show_probabilities":     True,
    # Afficher le critère de Kelly dans le message Telegram
    "show_kelly":             True,
    # Format de date pour l'affichage
    "date_format":            "%d/%m/%Y",
}
