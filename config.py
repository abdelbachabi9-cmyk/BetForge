# ============================================================
# config.py â Configuration du gÃ©nÃ©rateur de coupon sportif
# ============================================================
# Version : 2.0 â Avec calibrage par ligue, persistance SQLite,
#                  line movement, backtesting
#
# Obtenez vos clÃ©s API gratuites :
#   football-data.org : https://www.football-data.org/client/register
#   the-odds-api.com  : https://the-odds-api.com/#get-access
#   thesportsdb.com   : API publique, pas de clÃ© requise (tier 1)
#
# IMPORTANT : Ne mettez JAMAIS vos clÃ©s API en dur dans ce fichier.
# Utilisez les variables d'environnement (Railway ou fichier .env local).
# ============================================================

import os

# âââ CLÃS API (lues depuis les variables d'environnement) âââ
API_KEYS = {
    # football-data.org â clÃ© gratuite (10 req/min)
    "football_data": os.getenv("FOOTBALL_DATA_KEY", ""),
    # the-odds-api.com â tier gratuit (500 req/mois)
    "odds_api":      os.getenv("ODDS_API_KEY", ""),
    # api-football via RapidAPI â tier gratuit (100 req/jour)
    "api_football":  os.getenv("API_FOOTBALL_KEY", ""),
}

# âââ ENDPOINTS API ââââââââââââââââââââââââââââââââââââââââââââ
ENDPOINTS = {
    "football_data_base": "https://api.football-data.org/v4",
    "odds_api_base":      "https://api.the-odds-api.com/v4",
    "thesportsdb_base":   "https://www.thesportsdb.com/api/v1/json/3",
    "api_football_base":  "https://api-football-v1.p.rapidapi.com/v3",
    "balldontlie_base":   "https://api.balldontlie.io/v1",
}

# âââ COMPÃTITIONS FOOTBALL Ã SURVEILLER ââââââââââââââââââââââ
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
# NOTE SAISONNALISÃ : Ne listez que les compÃ©titions actives sur la pÃ©riode.
ODDS_SPORTS = [
    # Football (les 5 grands championnats + UCL) â actifs aoÃ»tâmai
    "soccer_france_ligue_one",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_uefa_champs_league",
    # Basketball â NBA actif octobreâjuin, EuroLeague octobreâmai
    "basketball_nba",
    "basketball_euroleague",
    # Tennis â NE DÃCOMMENTEZ que pendant la pÃ©riode du tournoi :
    # "tennis_atp_french_open",    # Roland-Garros : fin mai â dÃ©but juin
    # "tennis_atp_us_open",        # US Open : fin aoÃ»t â dÃ©but sept.
    # "tennis_atp_wimbledon",      # Wimbledon : fin juin â dÃ©but juillet
    # "tennis_atp_australian_open",# Open d'Australie : mi-janvier
]

# âââ PARAMÃTRES DU MODÃLE DE POISSON âââââââââââââââââââââââââ
POISSON_PARAMS = {
    # Avantage Ã  domicile PAR DÃFAUT (facteur multiplicatif sur les buts)
    # UtilisÃ© si la ligue n'est pas dans LEAGUE_HOME_ADVANTAGE
    "home_advantage": 1.1,
    # Nombre de buts maximum Ã  considÃ©rer dans la distribution
    "max_goals": 10,
    # Seuil Over/Under buts
    "goals_threshold": 2.5,
    # Nombre minimum de matchs pour calculer la force d'une Ã©quipe
    "min_matches": 5,
    # ParamÃ¨tre rho de correction des scores faibles (Poisson corrigÃ©)
    # Valeur empirique fixe â idÃ©alement Ã  estimer par MLE sur donnÃ©es historiques
    # Plage rÃ©aliste : -0.05 Ã  -0.20 selon ligue et saison
    "low_score_rho": -0.13,
    # Moyenne de buts par dÃ©faut (utilisÃ©e si pas de donnÃ©es dynamiques)
    # â CalculÃ©e dynamiquement dans DataFetcher si standings disponibles
    "default_league_avg_goals": 2.65,
}

# âââ CALIBRAGE HOME ADVANTAGE PAR LIGUE âââââââââââââââââââââââââ
# [NOUVEAU v2.0] Avantage domicile calibrÃ© par ligue.
# BasÃ© sur les donnÃ©es historiques 2018-2025 (source : football-data.co.uk).
# L'avantage domicile varie significativement entre les ligues :
#   - Bundesliga : stades bruyants, forte culture supporters
#   - Serie A : historiquement fort avantage domicile
#   - Premier League : plus Ã©quilibrÃ©
#   - Ligue 1 : avantage domicile modÃ©rÃ©
#   - La Liga : avantage marquÃ© (grandes enceintes)
#   - Ligue des Champions : avantage rÃ©duit (compÃ©tition europÃ©enne)
LEAGUE_HOME_ADVANTAGE = {
    "Premier League":       1.08,   # ~47% wins domicile, 28% nuls, 25% ext.
    "La Liga":              1.12,   # ~48% wins domicile, 26% nuls, 26% ext.
    "Bundesliga":           1.14,   # ~49% wins domicile, 25% nuls, 26% ext.
    "Serie A":              1.13,   # ~48% wins domicile, 27% nuls, 25% ext.
    "Ligue 1":              1.09,   # ~46% wins domicile, 28% nuls, 26% ext.
    "Ligue des Champions":  1.06,   # ~44% wins domicile, 24% nuls, 32% ext.
}

# âââ MOYENNE DE BUTS PAR LIGUE (VALEURS PAR DÃFAUT) âââââââââââ
# [NOUVEAU v2.0] CalculÃ©es dynamiquement si standings disponibles,
# sinon ces valeurs de fallback sont utilisÃ©es.
# Source : donnÃ©es moyennes saisons 2020-2025.
LEAGUE_AVG_GOALS = {
    "Premier League":       2.69,
    "La Liga":              2.55,
    "Bundesliga":           3.12,   # Ligue la plus offensive d'Europe
    "Serie A":              2.63,
    "Ligue 1":              2.49,
    "Ligue des Champions":  2.82,
}

# âââ PARAMÃTRES ELO (BASKETBALL) ââââââââââââââââââââââââââââââ
ELO_PARAMS = {
    # ELO de dÃ©part pour toutes les Ã©quipes
    "initial_rating": 1500,
    # Facteur K (sensibilitÃ© aux mises Ã  jour)
    "k_factor": 20,
    # Bonus domicile en ELO
    "home_bonus": 50,
}

# âââ PARAMÃTRES VALUE BETTING âââââââââââââââââââââââââââââââââ
VALUE_BETTING = {
    # Edge minimum requis pour sÃ©lectionner un pari (5%)
    "min_value": 0.05,
    # Cote minimale acceptÃ©e par sÃ©lection
    "min_odd": 1.30,
    # Cote maximale acceptÃ©e par sÃ©lection
    "max_odd": 4.00,
    # Nombre cible de sÃ©lections dans le coupon
    "target_selections": 6,
    # Nombre minimum de sÃ©lections
    "min_selections": 4,
    # Nombre maximum de sÃ©lections
    "max_selections": 10,
    # Cote totale cible du coupon
    "target_total_odd": 5.0,
    # FIX v4 : max_total_odd rÃ©duit de 15.0 Ã  8.0
    "min_total_odd": 3.0,
    "max_total_odd": 8.0,
}

# âââ KELLY CRITERION ââââââââââââââââââââââââââââââââââââââââââââ
KELLY = {
    # Fraction du Kelly (0.25 = quart de Kelly, recommandÃ© pour rÃ©duire la variance)
    "fraction":      0.25,
    # Mise maximale (% du bankroll) â cap de sÃ©curitÃ©
    "max_stake_pct": 5.0,
}

# âââ PARAMÃTRES RÃSEAU âââââââââââââââââââââââââââââââââââââââââ
NETWORK = {
    # Timeout en secondes pour chaque appel API
    "timeout": 8,
    # FIX v4 : max_retries remontÃ© de 1 Ã  3
    "max_retries": 3,
    # DÃ©lai initial entre les retries (secondes) â exponential backoff
    "retry_delay": 1.0,
}

# âââ CACHE âââââââââââââââââââââââââââââââââââââââââââââââââââââ
CACHE = {
    # TTL du cache des donnÃ©es API (en secondes)
    "api_data_ttl": 3600,   # 1 heure
    # TTL du cache du coupon gÃ©nÃ©rÃ© (en secondes)
    "coupon_ttl":   900,    # 15 minutes
}

# âââ MODE DÃMO ââââââââââââââââââââââââââââââââââââââââââââââââââ
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

# âââ UTILISATEURS AUTORISÃS âââââââââââââââââââââââââââââââââââââ
ALLOWED_USERS_RAW = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS = (
    [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip()]
    if ALLOWED_USERS_RAW else []
)

# âââ BASE DE DONNÃES (PERSISTANCE) âââââââââââââââââââââââââââââ
# [NOUVEAU v2.0] Stockage SQLite pour l'historique des coupons
DATABASE = {
    # Chemin de la base SQLite
    "path": os.getenv("APEX_DB_PATH", "apex_history.db"),
    # Activer la persistance automatique des coupons
    "auto_save": os.getenv("APEX_AUTO_SAVE", "true").lower() == "true",
}

# âââ LINE MOVEMENT (DÃTECTION MOUVEMENTS DE COTES) âââââââââââââ
# [NOUVEAU v2.0] ParamÃ¨tres de suivi des mouvements de cotes
LINE_MOVEMENT = {
    # Activer le suivi des mouvements de cotes
    "enabled": os.getenv("LINE_MOVEMENT_ENABLED", "true").lower() == "true",
    # Seuil de mouvement pour alerte warning (en %)
    "warning_threshold_pct": 5.0,
    # Seuil de mouvement pour alerte critique (en %)
    "critical_threshold_pct": 10.0,
    # Intervalle de vÃ©rification (secondes)
    "check_interval": 300,
}

# âââ BACKTESTING ââââââââââââââââââââââââââââââââââââââââââââââââ
# [NOUVEAU v2.0] Configuration du module de backtesting
BACKTEST = {
    # Activer le tracking automatique des rÃ©sultats
    "auto_track": os.getenv("BACKTEST_AUTO_TRACK", "true").lower() == "true",
    # Nombre de jours par dÃ©faut pour les rapports
    "default_report_days": 90,
    # Nombre de simulations Monte Carlo
    "monte_carlo_sims": 1000,
}
# ============================================================
