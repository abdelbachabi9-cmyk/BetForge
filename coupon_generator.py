#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â         GÃNÃRATEUR DE COUPON DE PARIS SPORTIFS QUOTIDIEN         â
â         ModÃ¨le : Poisson + correction scores faibles + ELO       â
â         Version : 2.0 | Python 3.8+                              â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

Ce script gÃ©nÃ¨re automatiquement un coupon de paris sportifs avec
une cote globale cible de ~5, en utilisant des modÃ¨les statistiques
sophistiquÃ©s et du value betting.

Utilisation :
    python coupon_generator.py

PrÃ©requis :
    pip install requests numpy scipy pandas
"""

import sys
import math
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

# Imports avec gestion d'erreur si bibliothÃ¨ques manquantes
try:
    import numpy as np
except ImportError:
    print("â numpy manquant. Lancez : pip install numpy")
    sys.exit(1)

try:
    from scipy.stats import poisson
except ImportError:
    print("â scipy manquant. Lancez : pip install scipy")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("â pandas manquant. Lancez : pip install pandas")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("â requests manquant. Lancez : pip install requests")
    sys.exit(1)

# Import de la configuration locale
try:
    from config import (
        API_KEYS, ENDPOINTS, FOOTBALL_COMPETITIONS, ODDS_SPORTS, API_FOOTBALL_LEAGUES,
        POISSON_PARAMS, ELO_PARAMS, VALUE_BETTING, KELLY, NETWORK, DEMO_MODE,
        LEAGUE_HOME_ADVANTAGE, LEAGUE_AVG_GOALS, DATABASE, LINE_MOVEMENT
    )
except ImportError:
    # Valeurs par dÃ©faut si config.py est absent
    API_KEYS = {"football_data": "", "odds_api": ""}
    ENDPOINTS = {
        "football_data_base":   "https://api.football-data.org/v4",
        "odds_api_base":        "https://api.the-odds-api.com/v4",
        "thesportsdb_base":     "https://www.thesportsdb.com/api/v1/json/3",
    }
    FOOTBALL_COMPETITIONS = {
        "PL": "Premier League", "PD": "La Liga",
        "BL1": "Bundesliga", "SA": "Serie A", "FL1": "Ligue 1",
    }
    POISSON_PARAMS  = {"home_advantage": 1.1, "max_goals": 10,
                       "goals_threshold": 2.5, "min_matches": 5}
    ELO_PARAMS      = {"initial_rating": 1500, "k_factor": 20, "home_bonus": 50}
    VALUE_BETTING   = {"min_value": 0.05, "min_odd": 1.30, "max_odd": 4.00,
                       "target_selections": 6, "min_selections": 4, "max_selections": 10,
                       "target_total_odd": 5.0, "min_total_odd": 3.0, "max_total_odd": 15.0}
    KELLY           = {"fraction": 0.25, "max_stake_pct": 5.0}
    NETWORK         = {"timeout": 10, "max_retries": 2}
    ODDS_SPORTS = ["soccer_france_ligue_one", "soccer_england_league1",
                   "soccer_germany_bundesliga", "soccer_spain_la_liga",
                   "soccer_italy_serie_a", "soccer_uefa_champs_league",
                   "basketball_nba", "basketball_euroleague",
                   "tennis_atp_french_open"]
    API_FOOTBALL_LEAGUES = {61: "Ligue 1", 39: "Premier League", 78: "Bundesliga",
                            140: "La Liga", 135: "Serie A", 2: "Ligue des Champions"}
    DEMO_MODE       = True
    LEAGUE_HOME_ADVANTAGE = {
        "Premier League": 1.08, "La Liga": 1.12, "Bundesliga": 1.10,
        "Serie A": 1.09, "Ligue 1": 1.11, "Ligue des Champions": 1.05,
    }
    LEAGUE_AVG_GOALS = {
        "Premier League": 2.69, "La Liga": 2.51, "Bundesliga": 3.17,
        "Serie A": 2.65, "Ligue 1": 2.64, "Ligue des Champions": 2.73,
    }
    DATABASE = {"auto_save": False, "path": "apex_history.db"}
    LINE_MOVEMENT = {"enabled": False}

# Configuration du logger
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s â %(message)s"
)
logger = logging.getLogger(__name__)

# Import des modules v2.0 (persistance, line movement)
try:
    from database import ApexDatabase
    _db = ApexDatabase(DATABASE.get("path", "apex_history.db")) if DATABASE.get("auto_save", True) else None
except Exception:
    _db = None
    logger.info("Module database non disponible — persistance désactivée")

try:
    from line_movement import LineMovementTracker
    _line_tracker = LineMovementTracker(db=_db) if LINE_MOVEMENT.get("enabled", False) else None
except Exception:
    _line_tracker = None
    logger.info("Module line_movement non disponible")


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CLASSE 1 : DataFetcher â RÃ©cupÃ©ration des donnÃ©es (API + fallback)
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class DataFetcher:
    """
    RÃ©cupÃ¨re les donnÃ©es sportives depuis les APIs gratuites disponibles.
    En cas d'Ã©chec (clÃ© invalide, timeout, erreur rÃ©seau), bascule
    automatiquement sur des donnÃ©es simulÃ©es rÃ©alistes.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "CouponGenerator/1.0"})
        self.today    = datetime.now().strftime("%Y-%m-%d")  # Matchs DU JOUR

    def _get(self, url: str, headers: dict = None, params: dict = None) -> Optional[dict]:
        """Effectue un appel GET avec gestion d'erreurs et timeout."""
        for attempt in range(NETWORK["max_retries"]):
            try:
                resp = self.session.get(
                    url,
                    headers=headers or {},
                    params=params or {},
                    timeout=NETWORK["timeout"]
                )
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    logger.warning(f"Quota API dÃ©passÃ© ({url})")
                    return None
                else:
                    logger.warning(f"Erreur HTTP {resp.status_code} pour {url}")
                    return None
            except requests.Timeout:
                logger.warning(f"Timeout ({attempt+1}/{NETWORK['max_retries']}) : {url}")
            except requests.ConnectionError:
                logger.warning(f"Pas de connexion : {url}")
                return None
            except Exception as e:
                logger.warning(f"Erreur inattendue : {e}")
                return None
        return None

    # ââ Football-data.org âââââââââââââââââââââââââââââââââââââââââââ

    def fetch_football_fixtures(self, competition_code: str) -> List[dict]:
        """
        RÃ©cupÃ¨re les matchs de demain depuis football-data.org.
        Retourne une liste de dicts normalisÃ©s.
        """
        if DEMO_MODE or not API_KEYS["football_data"]:
            logger.info(f"Mode dÃ©mo actif â donnÃ©es simulÃ©es pour {competition_code}")
            return []

        url = f"{ENDPOINTS['football_data_base']}/competitions/{competition_code}/matches"
        headers = {"X-Auth-Token": API_KEYS["football_data"]}
        params  = {"dateFrom": self.today, "dateTo": self.today}

        data = self._get(url, headers=headers, params=params)
        if not data:
            return []

        fixtures = []
        for match in data.get("matches", []):
            fixtures.append({
                "id":          match["id"],
                "competition": FOOTBALL_COMPETITIONS.get(competition_code, competition_code),
                "sport":       "Football",
                "home":        match["homeTeam"]["name"],
                "away":        match["awayTeam"]["name"],
                "date":        match["utcDate"][:10],
            })
        return fixtures

    def fetch_football_standings(self, competition_code: str) -> List[dict]:
        """
        RÃ©cupÃ¨re le classement d'une compÃ©tition pour calculer
        les forces d'attaque/dÃ©fense.
        """
        if DEMO_MODE or not API_KEYS["football_data"]:
            return []

        url = f"{ENDPOINTS['football_data_base']}/competitions/{competition_code}/standings"
        headers = {"X-Auth-Token": API_KEYS["football_data"]}

        data = self._get(url, headers=headers)
        if not data:
            return []

        standings = []
        for table in data.get("standings", []):
            if table.get("type") == "TOTAL":
                for entry in table.get("table", []):
                    standings.append({
                        "team":           entry["team"]["name"],
                        "played":         entry["playedGames"],
                        "goals_for":      entry["goalsFor"],
                        "goals_against":  entry["goalsAgainst"],
                    })
        return standings

    # ââ The-Odds-API ââââââââââââââââââââââââââââââââââââââââââââââââ

    def fetch_odds(self, sport_key: str) -> List[dict]:
        """
        RÃ©cupÃ¨re les cotes en temps rÃ©el depuis the-odds-api.com.
        Retourne les marchÃ©s 1X2 et Over/Under.
        """
        if DEMO_MODE or not API_KEYS["odds_api"]:
            return []

        url = f"{ENDPOINTS['odds_api_base']}/sports/{sport_key}/odds"
        params = {
            "apiKey":   API_KEYS["odds_api"],
            "regions":  "eu",
            "markets":  "h2h,totals",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }

        data = self._get(url, params=params)
        if not isinstance(data, list):
            return []

        odds_list = []
        for game in data:
            if game.get("commence_time", "")[:10] != self.today:
                continue
            entry = {
                "id":    game.get("id"),
                "home":  game.get("home_team"),
                "away":  game.get("away_team"),
                "sport": sport_key,
                "markets": {}
            }
            for bookmaker in game.get("bookmakers", [])[:1]:  # Premier bookmaker
                for market in bookmaker.get("markets", []):
                    key = market.get("key")
                    outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                    entry["markets"][key] = outcomes
            odds_list.append(entry)

        return odds_list

    # ââ TheSportsDB (multi-sports) âââââââââââââââââââââââââââââââââââ

    def fetch_thesportsdb_events(self, league_id: str) -> List[dict]:
        """
        RÃ©cupÃ¨re les Ã©vÃ©nements Ã  venir depuis TheSportsDB (API publique).
        """
        if DEMO_MODE:
            return []

        url = f"{ENDPOINTS['thesportsdb_base']}/eventsnextleague.php"
        params = {"id": league_id}

        data = self._get(url, params=params)
        if not data:
            return []

        events = []
        for event in (data.get("events") or []):
            if event.get("dateEvent") == self.today:
                events.append({
                    "sport":       event.get("strSport"),
                    "competition": event.get("strLeague"),
                    "home":        event.get("strHomeTeam"),
                    "away":        event.get("strAwayTeam"),
                    "date":        event.get("dateEvent"),
                })
        return events

    # ââ DonnÃ©es simulÃ©es rÃ©alistes (mode dÃ©mo / fallback) âââââââââââââ

    def get_demo_data(self) -> Dict:
        """
        GÃ©nÃ¨re un jeu de donnÃ©es rÃ©alistes simulant des matchs de demain,
        avec statistiques d'Ã©quipes et cotes bookmaker plausibles.
        UtilisÃ© quand les APIs ne rÃ©pondent pas ou en mode dÃ©mo.
        """
        # Seed alÃ©atoire basÃ©e sur la date pour des rÃ©sultats reproductibles
        seed = int(datetime.now().strftime("%Y%m%d"))
        rng  = random.Random(seed)
        np.random.seed(seed % (2**31))

        # ââ Matchs de football simulÃ©s âââââââââââââââââââââââââââââââ
        football_fixtures = [
            {
                "id": 1001, "sport": "Football", "competition": "Premier League",
                "home": "Arsenal",        "away": "Chelsea",
                "home_goals_avg": 2.1, "away_goals_avg": 1.6,
                "home_conceded_avg": 1.0, "away_conceded_avg": 1.3,
                "home_matches": 28, "away_matches": 28,
            },
            {
                "id": 1002, "sport": "Football", "competition": "La Liga",
                "home": "Real Madrid",    "away": "Atletico Madrid",
                "home_goals_avg": 2.4, "away_goals_avg": 1.4,
                "home_conceded_avg": 0.8, "away_conceded_avg": 0.9,
                "home_matches": 29, "away_matches": 29,
            },
            {
                "id": 1003, "sport": "Football", "competition": "Bundesliga",
                "home": "Bayern Munich",  "away": "Borussia Dortmund",
                "home_goals_avg": 2.7, "away_goals_avg": 2.0,
                "home_conceded_avg": 0.9, "away_conceded_avg": 1.5,
                "home_matches": 27, "away_matches": 27,
            },
            {
                "id": 1004, "sport": "Football", "competition": "Ligue 1",
                "home": "PSG",            "away": "Olympique de Marseille",
                "home_goals_avg": 2.5, "away_goals_avg": 1.7,
                "home_conceded_avg": 0.7, "away_conceded_avg": 1.2,
                "home_matches": 26, "away_matches": 26,
            },
            {
                "id": 1005, "sport": "Football", "competition": "Serie A",
                "home": "Inter Milan",    "away": "AC Milan",
                "home_goals_avg": 2.2, "away_goals_avg": 1.9,
                "home_conceded_avg": 0.8, "away_conceded_avg": 1.0,
                "home_matches": 27, "away_matches": 27,
            },
            {
                "id": 1006, "sport": "Football", "competition": "Ligue des Champions",
                "home": "Manchester City", "away": "Paris Saint-Germain",
                "home_goals_avg": 2.3, "away_goals_avg": 1.8,
                "home_conceded_avg": 0.9, "away_conceded_avg": 1.1,
                "home_matches": 8,  "away_matches": 8,
            },
            {
                "id": 1007, "sport": "Football", "competition": "Premier League",
                "home": "Liverpool",      "away": "Manchester United",
                "home_goals_avg": 2.3, "away_goals_avg": 1.5,
                "home_conceded_avg": 0.9, "away_conceded_avg": 1.4,
                "home_matches": 28, "away_matches": 28,
            },
        ]

        # ââ Matchs de basketball simulÃ©s ââââââââââââââââââââââââââââ
        basketball_fixtures = [
            {
                "id": 2001, "sport": "Basketball", "competition": "NBA",
                "home": "Boston Celtics",  "away": "Miami Heat",
                "home_elo": 1650, "away_elo": 1580,
                "home_form": [1, 1, 0, 1, 1],
                "away_form": [1, 0, 1, 0, 1],
            },
            {
                "id": 2002, "sport": "Basketball", "competition": "NBA",
                "home": "Golden State Warriors", "away": "LA Lakers",
                "home_elo": 1610, "away_elo": 1595,
                "home_form": [1, 0, 1, 1, 0],
                "away_form": [0, 1, 1, 0, 1],
            },
        ]

        # ââ Matchs de tennis simulÃ©s âââââââââââââââââââââââââââââââââ
        tennis_fixtures = [
            {
                "id": 3001, "sport": "Tennis", "competition": "ATP Masters",
                "home": "Carlos Alcaraz",  "away": "Novak Djokovic",
                "surface": "clay",
                "home_ranking": 2,  "away_ranking": 3,
                "home_surface_winrate": 0.78, "away_surface_winrate": 0.72,
                "home_form": [1, 1, 1, 0, 1], "away_form": [1, 0, 1, 1, 0],
            },
        ]

        # ââ Cotes bookmaker simulÃ©es rÃ©alistes âââââââââââââââââââââââ
        # LÃ©gÃ¨rement dÃ©favorables (marge bookmaker ~5%)
        def noisy_odd(p: float, margin: float = 0.05) -> float:
            """Simule la cote bookmaker Ã  partir d'une proba rÃ©elle."""
            implied = p * (1 - margin)
            raw = 1 / implied if implied > 0 else 99.0
            noise = rng.uniform(0.98, 1.02)
            return round(max(1.10, raw * noise), 2)

        return {
            "football":   football_fixtures,
            "basketball": basketball_fixtures,
            "tennis":     tennis_fixtures,
            "date":       self.today,
            "noisy_odd":  noisy_odd,  # Fonction utilitaire
        }


    # ââ API-Football (RapidAPI) â enrichissement football prioritaire ââ

    def fetch_api_football_fixtures(self, league_id: int) -> List[dict]:
        """
        R\u00e9cup\u00e8re les matchs du jour via API-Football (RapidAPI).
        Retourne la liste des fixtures au format standard.
        """
        key = API_KEYS.get("api_football", "")
        if not key or key == "demo":
            return []

        url = f"{ENDPOINTS['api_football_base']}/fixtures"
        headers = {
            "X-RapidAPI-Key": key,
            "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
        }
        params = {"league": league_id, "season": datetime.now().year, "date": self.today}

        data = self._get(url, headers=headers, params=params)
        if not data or "response" not in data:
            return []

        fixtures = []
        for match in data["response"]:
            home_team = match.get("teams", {}).get("home", {}).get("name", "?")
            away_team = match.get("teams", {}).get("away", {}).get("name", "?")
            fixture_id = match.get("fixture", {}).get("id", f"{home_team}_{away_team}")

            fixtures.append({
                "id": fixture_id,
                "home": home_team,
                "away": away_team,
                "competition": API_FOOTBALL_LEAGUES.get(league_id, str(league_id)),
                "date": self.today,
            })

        return fixtures

    def fetch_api_football_team_stats(self, league_id: int) -> Dict[str, dict]:
        """
        R\u00e9cup\u00e8re les classements via API-Football pour enrichir le mod\u00e8le Poisson.
        Retourne un dict {team_name: {goals_avg, conceded_avg, matches}}.
        """
        key = API_KEYS.get("api_football", "")
        if not key or key == "demo":
            return {}

        url = f"{ENDPOINTS['api_football_base']}/standings"
        headers = {
            "X-RapidAPI-Key": key,
            "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
        }
        params = {"league": league_id, "season": datetime.now().year}

        data = self._get(url, headers=headers, params=params)
        if not data or "response" not in data:
            return {}

        stats = {}
        try:
            standings = data["response"][0]["league"]["standings"][0]
            for team_entry in standings:
                team_name = team_entry["team"]["name"]
                played = team_entry["all"]["played"]
                if played >= POISSON_PARAMS["min_matches"]:
                    stats[team_name] = {
                        "goals_avg": team_entry["all"]["goals"]["for"] / played,
                        "conceded_avg": team_entry["all"]["goals"]["against"] / played,
                        "matches": played,
                    }
        except (KeyError, IndexError, ZeroDivisionError) as e:
            logger.warning(f"Erreur parsing standings API-Football league {league_id}: {e}")

        return stats

    # ââ BallDontLie API â enrichissement basketball NBA ââââââââââââ

    def fetch_balldontlie_team_stats(self) -> Dict[str, dict]:
        """
        R\u00e9cup\u00e8re les stats d'\u00e9quipes NBA via BallDontLie (gratuit, sans cl\u00e9).
        Retourne un dict {team_full_name: {wins, losses, win_pct, elo_approx}}.
        """
        url = f"{ENDPOINTS.get('balldontlie_base', 'https://api.balldontlie.io/v1')}/teams"
        data = self._get(url)
        if not data or "data" not in data:
            return {}

        # R\u00e9cup\u00e9rer les standings NBA courants
        standings_url = f"{ENDPOINTS.get('balldontlie_base', 'https://api.balldontlie.io/v1')}/standings"
        params = {"season": datetime.now().year if datetime.now().month >= 10 else datetime.now().year - 1}
        standings_data = self._get(standings_url, params=params)

        if not standings_data or "data" not in standings_data:
            # Fallback: utiliser uniquement les noms d'\u00e9quipe sans stats
            return {}

        stats = {}
        for team in standings_data["data"]:
            try:
                name = team.get("team", {}).get("full_name", "")
                wins = team.get("wins", 0)
                losses = team.get("losses", 0)
                total = wins + losses
                if total > 0:
                    win_pct = wins / total
                    # Approximation ELO bas\u00e9e sur le win%
                    # 50% win = 1500, chaque 10% = +/- 150 ELO
                    elo_approx = round(1500 + (win_pct - 0.5) * 1500, 0)
                    stats[name] = {
                        "wins": wins,
                        "losses": losses,
                        "win_pct": round(win_pct, 3),
                        "elo_approx": elo_approx,
                    }
            except (KeyError, ZeroDivisionError):
                continue

        return stats

    def fetch_football_stats(self, fixtures: list) -> dict:
        """
        Récupère les statistiques historiques (corners, fautes, cartons, tirs)
        pour chaque fixture via api-football.
        
        Returns:
            dict: {fixture_id: {"home": {stats...}, "away": {stats...}}}
        """
        stats_data = {}
        
        if DEMO_MODE:
            # Mode démo : générer des stats réalistes
            import random
            seed_base = int(datetime.now().strftime("%Y%m%d"))
            for fix in fixtures:
                fix_id = fix.get("id", 0)
                rng = random.Random(seed_base + fix_id)
                stats_data[fix_id] = {
                    "home": {
                        "corners_avg": round(rng.uniform(4.0, 7.0), 1),
                        "corners_conceded_avg": round(rng.uniform(3.5, 6.5), 1),
                        "fouls_avg": round(rng.uniform(9.0, 15.0), 1),
                        "fouls_conceded_avg": round(rng.uniform(9.0, 14.0), 1),
                        "cards_avg": round(rng.uniform(1.2, 3.0), 1),
                        "cards_conceded_avg": round(rng.uniform(1.0, 2.8), 1),
                        "shots_on_target_avg": round(rng.uniform(3.5, 6.5), 1),
                        "shots_on_target_conceded_avg": round(rng.uniform(3.0, 6.0), 1),
                    },
                    "away": {
                        "corners_avg": round(rng.uniform(3.5, 6.5), 1),
                        "corners_conceded_avg": round(rng.uniform(4.0, 7.0), 1),
                        "fouls_avg": round(rng.uniform(9.5, 15.5), 1),
                        "fouls_conceded_avg": round(rng.uniform(9.0, 14.5), 1),
                        "cards_avg": round(rng.uniform(1.3, 3.2), 1),
                        "cards_conceded_avg": round(rng.uniform(1.1, 3.0), 1),
                        "shots_on_target_avg": round(rng.uniform(3.0, 6.0), 1),
                        "shots_on_target_conceded_avg": round(rng.uniform(3.5, 6.5), 1),
                    },
                }
            return stats_data
        
        # Mode réel : appel api-football /fixtures/statistics
        try:
            api_key = os.environ.get("API_FOOTBALL_KEY", "")
            if not api_key:
                logger.warning("API_FOOTBALL_KEY non définie, skip stats")
                return stats_data
            
            headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": "api-football-v1.p.rapidapi.com"}
            
            for fix in fixtures:
                fix_id = fix.get("id", 0)
                home_id = fix.get("home_id")
                away_id = fix.get("away_id")
                if not home_id or not away_id:
                    continue
                
                home_stats = self._fetch_team_stats_avg(home_id, headers)
                away_stats = self._fetch_team_stats_avg(away_id, headers)
                
                if home_stats and away_stats:
                    stats_data[fix_id] = {"home": home_stats, "away": away_stats}
        except Exception as e:
            logger.error(f"Erreur fetch_football_stats: {e}")
        
        return stats_data
    
    def _fetch_team_stats_avg(self, team_id: int, headers: dict) -> Optional[dict]:
        """Récupère les moyennes stats des 5 derniers matchs d'une équipe."""
        try:
            url = f"https://api-football-v1.p.rapidapi.com/v3/fixtures?team={team_id}&last=5"
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code != 200:
                return None
            
            matches = resp.json().get("response", [])
            if len(matches) < 3:
                return None
            
            totals = {"corners": [], "fouls": [], "cards": [], "shots_on_target": []}
            conceded = {"corners": [], "fouls": [], "cards": [], "shots_on_target": []}
            
            for match in matches:
                stats_list = match.get("statistics", [])
                for team_stats in stats_list:
                    tid = team_stats.get("team", {}).get("id")
                    s = {item["type"].lower(): item["value"] for item in team_stats.get("statistics", [])}
                    
                    if tid == team_id:
                        totals["corners"].append(s.get("corner kicks", 0) or 0)
                        totals["fouls"].append(s.get("fouls", 0) or 0)
                        totals["cards"].append((s.get("yellow cards", 0) or 0) + (s.get("red cards", 0) or 0))
                        totals["shots_on_target"].append(s.get("shots on goal", 0) or 0)
                    else:
                        conceded["corners"].append(s.get("corner kicks", 0) or 0)
                        conceded["fouls"].append(s.get("fouls", 0) or 0)
                        conceded["cards"].append((s.get("yellow cards", 0) or 0) + (s.get("red cards", 0) or 0))
                        conceded["shots_on_target"].append(s.get("shots on goal", 0) or 0)
            
            def avg(lst):
                return round(sum(lst) / len(lst), 1) if lst else 0.0
            
            return {
                "corners_avg": avg(totals["corners"]),
                "corners_conceded_avg": avg(conceded["corners"]),
                "fouls_avg": avg(totals["fouls"]),
                "fouls_conceded_avg": avg(conceded["fouls"]),
                "cards_avg": avg(totals["cards"]),
                "cards_conceded_avg": avg(conceded["cards"]),
                "shots_on_target_avg": avg(totals["shots_on_target"]),
                "shots_on_target_conceded_avg": avg(conceded["shots_on_target"]),
            }
        except Exception as e:
            logger.error(f"Erreur _fetch_team_stats_avg: {e}")
            return None


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CLASSE 2 : PoissonModel â ModÃ¨le football (Poisson + correction scores faibles)
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class PoissonModel:
    """
    ModÃ¨le statistique de prÃ©diction football basÃ© sur la distribution
    de Poisson (correction scores faibles).

    Calcule :
    - P(victoire domicile) | P(nul) | P(victoire extÃ©rieur)
    - P(Over 2.5 buts)
    - P(BTTS â les deux Ã©quipes marquent)
    - P(1 ou 0 but dans le match)
    """

    def __init__(self, league_avg_goals: float = None, league_name: str = None):
        self.league_avg_goals = league_avg_goals or POISSON_PARAMS.get("default_league_avg_goals", 2.65)
        # [v2.0] Calibrage home_advantage par ligue
        if league_name and league_name in LEAGUE_HOME_ADVANTAGE:
            self.home_adv = LEAGUE_HOME_ADVANTAGE[league_name]
        else:
            self.home_adv = POISSON_PARAMS["home_advantage"]
        self._league_name = league_name
        self.max_goals         = POISSON_PARAMS["max_goals"]
        self.goals_thresh      = POISSON_PARAMS["goals_threshold"]
        self.rho               = POISSON_PARAMS.get("low_score_rho", -0.13)

        # Matrice de correction rho (scores faibles)
        # (rÃ©duit la sous-estimation de ces scores par Poisson classique)
        self.tau_correction = {
            (0, 0): 0.05,
            (0, 1): -0.05,
            (1, 0): -0.05,
            (1, 1): 0.05,
        }

    def calculate_lambdas(self, fixture: dict) -> Tuple[float, float]:
        """
        Calcule les paramÃ¨tres lambda (buts attendus) pour chaque Ã©quipe.

        Formule :
            lambda_home = att_home Ã def_away Ã avg_goals Ã home_adv
            lambda_away = att_away Ã def_home Ã avg_goals
        """
        # Force d'attaque = moyenne de buts marquÃ©s / moyenne de la ligue
        att_home = fixture["home_goals_avg"] / self.league_avg_goals
        att_away = fixture["away_goals_avg"] / self.league_avg_goals

        # Force de dÃ©fense = moyenne de buts encaissÃ©s / moyenne de la ligue
        # Plus c'est faible, mieux c'est en dÃ©fense
        def_home = fixture["home_conceded_avg"] / self.league_avg_goals
        def_away = fixture["away_conceded_avg"] / self.league_avg_goals

        # Buts attendus (xG)
        lambda_home = att_home * def_away * self.league_avg_goals * self.home_adv
        lambda_away = att_away * def_home * self.league_avg_goals

        return round(lambda_home, 4), round(lambda_away, 4)

    def _low_score_tau(self, goals_h: int, goals_a: int,
                       lambda_h: float, lambda_a: float) -> float:
        """
        Correction rho pour les scores faibles.
        Utilise self.rho configurÃ© Ã  partir de POISSON_PARAMS.
        """
        rho = self.rho
        if goals_h == 0 and goals_a == 0:
            return 1 - lambda_h * lambda_a * rho
        elif goals_h == 0 and goals_a == 1:
            return 1 + lambda_h * rho
        elif goals_h == 1 and goals_a == 0:
            return 1 + lambda_a * rho
        elif goals_h == 1 and goals_a == 1:
            return 1 - rho
        else:
            return 1.0

    def score_matrix(self, lambda_home: float, lambda_away: float) -> np.ndarray:
        """
        Construit la matrice de probabilitÃ©s de scores.
        score_matrix[i][j] = P(domicile marque i buts, extÃ©rieur marque j buts)
        """
        max_g = self.max_goals
        matrix = np.zeros((max_g + 1, max_g + 1))

        for i in range(max_g + 1):
            for j in range(max_g + 1):
                p = (poisson.pmf(i, lambda_home) *
                     poisson.pmf(j, lambda_away))
                # Correction rho pour les petits scores
                tau = self._low_score_tau(i, j, lambda_home, lambda_away)
                matrix[i][j] = p * tau

        # Normalisation pour que la somme = 1
        total = matrix.sum()
        if total > 0:
            matrix /= total

        return matrix

    def predict(self, fixture: dict) -> Dict[str, Any]:
        """
        PrÃ©dit toutes les probabilitÃ©s pour un match de football.
        Retourne un dict avec les probabilitÃ©s et les lambdas.
        """
        lambda_h, lambda_a = self.calculate_lambdas(fixture)
        matrix = self.score_matrix(lambda_h, lambda_a)

        # ââ ProbabilitÃ©s 1X2 ââââââââââââââââââââââââââââââââââââââ
        # FIX T4 : INVERSION CORRIGÉE — matrice[home][away]
        #   triu(k=1) = home_goals > away_goals → victoire domicile
        #   tril(k=-1) = away_goals > home_goals → victoire extérieur
        p_home = float(np.sum(np.triu(matrix, 1)))    # domicile gagne
        p_draw = float(np.sum(np.diag(matrix)))       # égalité
        p_away = float(np.sum(np.tril(matrix, -1)))   # extérieur gagne

        # ââ Over/Under 2.5 buts âââââââââââââââââââââââââââââââââââ
        threshold = int(self.goals_thresh)  # 2
        p_over = 0.0
        p_under = 0.0
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                total_goals = i + j
                if total_goals > self.goals_thresh:
                    p_over += matrix[i][j]
                else:
                    p_under += matrix[i][j]

        # ââ BTTS (Both Teams To Score) ââââââââââââââââââââââââââââ
        # P(home > 0 ET away > 0) = 1 - P(home=0) - P(away=0) + P(home=0 ET away=0)
        p_btts = float(1
                       - np.sum(matrix[0, :])     # P(home ne marque pas)
                       - np.sum(matrix[:, 0])     # P(away ne marque pas)
                       + matrix[0, 0])            # P(aucun but, ajoutÃ© car soustrait 2x)

        # ââ Score le plus probable ââââââââââââââââââââââââââââââââ
        max_idx = np.unravel_index(np.argmax(matrix), matrix.shape)
        most_likely_score = f"{max_idx[0]}-{max_idx[1]}"

        return {
            "sport":       "Football",
            "fixture":     fixture,
            "lambda_home": lambda_h,
            "lambda_away": lambda_a,
            "p_home_win":  round(p_home, 4),
            "p_draw":      round(p_draw, 4),
            "p_away_win":  round(p_away, 4),
            "p_over_2_5":  round(p_over, 4),
            "p_under_2_5": round(p_under, 4),
            "p_btts":      round(p_btts, 4),
            "p_btts_no":   round(1 - p_btts, 4),
            "most_likely_score": most_likely_score,
            "matrix":      matrix,
        }


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CLASSE 3 : EloModel â ModÃ¨le basketball (ELO adaptÃ©)
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class EloModel:
    """
    ModÃ¨le ELO adaptÃ© pour la prÃ©diction basketball.

    Le rating ELO mesure la force relative de chaque Ã©quipe.
    AprÃ¨s chaque match, les ratings sont mis Ã  jour selon le rÃ©sultat.
    Un bonus domicile est appliquÃ© Ã  l'Ã©quipe qui reÃ§oit.
    """

    def __init__(self):
        self.ratings: Dict[str, float] = {}
        self.k       = ELO_PARAMS["k_factor"]
        self.initial = ELO_PARAMS["initial_rating"]
        self.home_bonus = ELO_PARAMS["home_bonus"]

    def get_rating(self, team: str) -> float:
        """Retourne le rating ELO d'une Ã©quipe (initial si inconnue)."""
        return self.ratings.get(team, self.initial)

    def update(self, home: str, away: str, home_won: bool) -> None:
        """
        Met Ã  jour les ratings ELO aprÃ¨s un match.
        S : 1 si victoire, 0 si dÃ©faite.
        """
        r_home = self.get_rating(home) + self.home_bonus
        r_away = self.get_rating(away)

        # ProbabilitÃ© attendue de victoire domicile
        e_home = 1 / (1 + 10 ** ((r_away - r_home) / 400))
        e_away = 1 - e_home

        # RÃ©sultat rÃ©el
        s_home = 1.0 if home_won else 0.0
        s_away = 1.0 - s_home

        # Mise Ã  jour
        self.ratings[home] = self.get_rating(home) + self.k * (s_home - e_home)
        self.ratings[away] = self.get_rating(away) + self.k * (s_away - e_away)

    def expected_win_prob(self, home: str, away: str) -> Tuple[float, float]:
        """
        Calcule les probabilitÃ©s de victoire selon les ratings ELO.
        Retourne (p_home, p_away).
        """
        r_home = self.get_rating(home) + self.home_bonus
        r_away = self.get_rating(away)

        p_home = 1 / (1 + 10 ** ((r_away - r_home) / 400))
        p_away = 1 - p_home

        return round(p_home, 4), round(p_away, 4)

    def form_adjustment(self, form_list: List[int]) -> float:
        """
        Calcule un score de forme rÃ©cente pondÃ©rÃ©.
        form_list = liste de rÃ©sultats [1/0] du plus rÃ©cent au plus ancien.
        Poids dÃ©croissants : match le plus rÃ©cent pÃ¨se le plus lourd.
        """
        weights = [0.35, 0.25, 0.20, 0.12, 0.08]
        score = 0.0
        for i, result in enumerate(form_list[:5]):
            score += result * weights[i]
        return round(score, 4)

    def predict(self, fixture: dict) -> Dict[str, Any]:
        """
        PrÃ©dit le rÃ©sultat d'un match de basketball avec ELO + forme.
        """
        home, away = fixture["home"], fixture["away"]

        # Initialisation des ratings Ã  partir des donnÃ©es disponibles
        if "home_elo" in fixture:
            self.ratings[home] = fixture["home_elo"]
        if "away_elo" in fixture:
            self.ratings[away] = fixture["away_elo"]

        # ProbabilitÃ©s ELO de base
        p_home, p_away = self.expected_win_prob(home, away)

        # Ajustement forme rÃ©cente
        form_home = self.form_adjustment(fixture.get("home_form", []))
        form_away = self.form_adjustment(fixture.get("away_form", []))

        # Ajustement: si forme nettement supÃ©rieure, lÃ©gÃ¨re correction
        form_diff = (form_home - form_away) * 0.10
        p_home_adj = min(0.95, max(0.05, p_home + form_diff))
        p_away_adj = 1 - p_home_adj

        return {
            "sport":         "Basketball",
            "fixture":       fixture,
            "elo_home":      self.get_rating(home) + self.home_bonus,
            "elo_away":      self.get_rating(away),
            "form_home":     form_home,
            "form_away":     form_away,
            "p_home_win":    round(p_home_adj, 4),
            "p_away_win":    round(p_away_adj, 4),
        }


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CLASSE 4 : TennisModel â ModÃ¨le tennis (ELO-like + surface + forme)
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class TennisModel:
    """
    ModÃ¨le de prÃ©diction tennis combinant :
    - Classement ATP/WTA (approximation ELO via ranking)
    - Performance sur la surface spÃ©cifique
    - Forme rÃ©cente (derniers 10 matchs)
    """

    # Conversion ranking â rating ELO approximatif
    # (basÃ© sur la distribution empirique des rankings ATP)
    RANKING_TO_ELO = {
        1: 2200, 2: 2150, 3: 2100, 5: 2050, 10: 2000,
        20: 1950, 30: 1900, 50: 1850, 75: 1800, 100: 1750,
        150: 1700, 200: 1650, 300: 1600, 500: 1550
    }

    def ranking_to_elo(self, ranking: int) -> float:
        """Convertit un classement ATP/WTA en rating ELO approximatif."""
        if ranking <= 0:
            return 1500
        # Interpolation linÃ©aire entre les points de rÃ©fÃ©rence
        keys = sorted(self.RANKING_TO_ELO.keys())
        for i in range(len(keys) - 1):
            if keys[i] <= ranking <= keys[i + 1]:
                r1, r2 = keys[i], keys[i + 1]
                e1, e2 = self.RANKING_TO_ELO[r1], self.RANKING_TO_ELO[r2]
                fraction = (ranking - r1) / (r2 - r1)
                return e1 + fraction * (e2 - e1)
        return max(1400, 2200 - ranking * 1.5)

    def surface_adjustment(self, win_rate: float, surface: str) -> float:
        """
        Ajuste la probabilitÃ© selon le taux de victoire sur la surface.
        win_rate : taux historique de victoire sur cette surface [0,1]
        """
        # Score normalisÃ© : 0.5 = neutre, >0.5 = fort sur la surface
        return round((win_rate - 0.5) * 0.15, 4)

    def form_score(self, form_list: List[int]) -> float:
        """
        Calcule le score de forme sur les 10 derniers matchs.
        Les matchs rÃ©cents ont plus de poids.
        """
        weights = [0.20, 0.18, 0.15, 0.12, 0.10, 0.09, 0.07, 0.05, 0.03, 0.01]
        score = 0.0
        for i, result in enumerate(form_list[:10]):
            score += result * weights[i]
        return round(score, 4)

    def predict(self, fixture: dict) -> Dict[str, Any]:
        """
        PrÃ©dit le rÃ©sultat d'un match de tennis.
        """
        home, away = fixture["home"], fixture["away"]
        surface    = fixture.get("surface", "clay")

        # Rating ELO approximatif basÃ© sur le classement
        elo_home = self.ranking_to_elo(fixture.get("home_ranking", 100))
        elo_away = self.ranking_to_elo(fixture.get("away_ranking", 100))

        # ProbabilitÃ© ELO de base
        p_home_base = 1 / (1 + 10 ** ((elo_away - elo_home) / 400))

        # Ajustement surface
        adj_home = self.surface_adjustment(
            fixture.get("home_surface_winrate", 0.5), surface)
        adj_away = self.surface_adjustment(
            fixture.get("away_surface_winrate", 0.5), surface)

        # Score de forme
        form_home = self.form_score(fixture.get("home_form", []))
        form_away = self.form_score(fixture.get("away_form", []))

        # Combinaison : ELO + surface + forme
        p_home_adj = p_home_base + (adj_home - adj_away) + (form_home - form_away) * 0.08
        p_home_adj = min(0.95, max(0.05, p_home_adj))
        p_away_adj = 1 - p_home_adj

        return {
            "sport":       "Tennis",
            "fixture":     fixture,
            "surface":     surface,
            "elo_home":    round(elo_home, 1),
            "elo_away":    round(elo_away, 1),
            "form_home":   form_home,
            "form_away":   form_away,
            "p_home_win":  round(p_home_adj, 4),
            "p_away_win":  round(p_away_adj, 4),
        }


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CLASSE 5 : ValueBetSelector â Calcul de valeur et sÃ©lection des paris
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class StatsModel:
    """Modèle Poisson pour les statistiques de match (corners, fautes, cartons, tirs)."""
    
    def __init__(self):
        try:
            from config import (STATS_MARKETS, LEAGUE_AVG_CORNERS, LEAGUE_AVG_FOULS,
                                LEAGUE_AVG_CARDS, LEAGUE_AVG_SHOTS_ON_TARGET)
            self.config = STATS_MARKETS
            self.league_avgs = {
                "corners": LEAGUE_AVG_CORNERS,
                "fouls": LEAGUE_AVG_FOULS,
                "cards": LEAGUE_AVG_CARDS,
                "shots_on_target": LEAGUE_AVG_SHOTS_ON_TARGET,
            }
        except ImportError:
            self.config = {"enabled": False, "markets": {}}
            self.league_avgs = {
                "corners": {"default": 10.2},
                "fouls": {"default": 23.0},
                "cards": {"default": 4.2},
                "shots_on_target": {"default": 9.5},
            }
    
    def _get_league_avg(self, stat_type: str, league: str) -> float:
        avgs = self.league_avgs.get(stat_type, {})
        return avgs.get(league, avgs.get("default", 10.0))
    
    def _poisson_over(self, lam: float, line: float) -> float:
        """P(X > line) où X ~ Poisson(lambda)."""
        from scipy.stats import poisson
        k = int(line)
        return 1.0 - poisson.cdf(k, lam)
    
    def predict(self, fixture: dict, stats_history: dict) -> dict:
        """
        Calcule les probabilités pour les marchés stats d'un match.
        
        Args:
            fixture: dict avec home, away, competition
            stats_history: dict avec clés 'home' et 'away', chacun contenant
                          corners_avg, fouls_avg, cards_avg, shots_on_target_avg,
                          corners_conceded_avg, fouls_conceded_avg, etc.
        
        Returns:
            dict avec probabilités pour chaque marché stats
        """
        if not self.config.get("enabled", False):
            return {}
        
        league = fixture.get("competition", "default")
        home_stats = stats_history.get("home", {})
        away_stats = stats_history.get("away", {})
        
        result = {
            "sport": "Football",
            "fixture": fixture,
            "stats_markets": {}
        }
        
        stat_types = {
            "corners": ("corners_avg", "corners_conceded_avg"),
            "fouls": ("fouls_avg", "fouls_conceded_avg"),
            "cards": ("cards_avg", "cards_conceded_avg"),
            "shots_on_target": ("shots_on_target_avg", "shots_on_target_conceded_avg"),
        }
        
        for stat_type, (avg_key, conceded_key) in stat_types.items():
            market_cfg = self.config.get("markets", {}).get(stat_type, {})
            if not market_cfg.get("enabled", False):
                continue
            
            league_avg = self._get_league_avg(stat_type, league)
            
            # Lambda domicile
            h_avg = home_stats.get(avg_key, league_avg / 2)
            h_conc = away_stats.get(conceded_key, league_avg / 2)
            lam_home = (h_avg / (league_avg / 2)) * (h_conc / (league_avg / 2)) * (league_avg / 2)
            
            # Lambda extérieur
            a_avg = away_stats.get(avg_key, league_avg / 2)
            a_conc = home_stats.get(conceded_key, league_avg / 2)
            lam_away = (a_avg / (league_avg / 2)) * (a_conc / (league_avg / 2)) * (league_avg / 2)
            
            lam_total = lam_home + lam_away
            
            markets = {}
            # Marchés total match
            for line in market_cfg.get("lines", []):
                p_over = self._poisson_over(lam_total, line)
                markets[f"over_{line}_{stat_type}"] = {
                    "prob": p_over,
                    "label": f"Over {line} {stat_type}",
                    "lambda": lam_total,
                }
                markets[f"under_{line}_{stat_type}"] = {
                    "prob": 1.0 - p_over,
                    "label": f"Under {line} {stat_type}",
                    "lambda": lam_total,
                }
            
            # Marchés par équipe
            for line in market_cfg.get("team_lines", []):
                home_name = fixture.get("home", "Home")
                away_name = fixture.get("away", "Away")
                
                p_home_over = self._poisson_over(lam_home, line)
                markets[f"home_over_{line}_{stat_type}"] = {
                    "prob": p_home_over,
                    "label": f"{home_name} +{line} {stat_type}",
                    "lambda": lam_home,
                }
                
                p_away_over = self._poisson_over(lam_away, line)
                markets[f"away_over_{line}_{stat_type}"] = {
                    "prob": p_away_over,
                    "label": f"{away_name} +{line} {stat_type}",
                    "lambda": lam_away,
                }
            
            result["stats_markets"][stat_type] = markets
        
        return result


class ValueBetSelector:
    """
    Identifie les paris Ã  valeur positive (value bets).

    Principe du value betting :
        Si la probabilitÃ© modÃ©lisÃ©e > probabilitÃ© implicite du bookmaker,
        alors le pari est mathÃ©matiquement favorable Ã  long terme.

    Formule value : value = (p_model Ã cote_book) - 1
    """

    def __init__(self):
        self.min_value    = VALUE_BETTING["min_value"]
        self.min_odd      = VALUE_BETTING["min_odd"]
        self.max_odd      = VALUE_BETTING["max_odd"]
        self.noisy_odd_fn = None  # Sera assignÃ© par DataFetcher en mode dÃ©mo

    def calculate_value(self, p_model: float, odd_book: float) -> float:
        """
        Calcule la valeur espÃ©rÃ©e d'un pari.
        value > 0 : pari mathÃ©matiquement favorable.
        value > 0.05 : edge significatif (critÃ¨re de sÃ©lection).
        """
        return round((p_model * odd_book) - 1, 4)

    def simulate_bookmaker_odd(self, p_model: float,
                                market_margin: float = 0.06) -> float:
        """
        Simule une cote bookmaker rÃ©aliste avec marge intÃ©grÃ©e.
        UtilisÃ© en mode dÃ©mo ou si l'API des cotes est indisponible.
        """
        if self.noisy_odd_fn:
            return self.noisy_odd_fn(p_model)

        # Marge bookmaker typique : 5-7% sur les marchÃ©s populaires
        p_implied = p_model * (1 - market_margin)
        if p_implied <= 0:
            return 99.0
        base_odd = 1 / p_implied
        # Bruit alÃ©atoire Â±5% pour simuler la variation entre bookmakers
        noise = random.uniform(0.98, 1.02)
        return round(max(1.10, base_odd * noise), 2)

    def extract_football_bets(self, prediction: dict,
                               odds_data: Optional[dict] = None) -> List[dict]:
        """
        Extrait tous les paris possibles d'une prÃ©diction football.
        Compare les probabilitÃ©s modÃ¨les aux cotes disponibles.
        """
        bets   = []
        fix    = prediction["fixture"]
        home   = fix["home"]
        away   = fix["away"]
        comp   = fix["competition"]
        sport  = "Football"

        # MarchÃ©s disponibles et leurs probabilitÃ©s modÃ¨les
        markets = [
            ("Victoire " + home,          prediction["p_home_win"],  "1X2"),
            ("Match nul",                  prediction["p_draw"],      "1X2"),
            ("Victoire " + away,           prediction["p_away_win"],  "1X2"),
            ("Over 2.5 buts",              prediction["p_over_2_5"],  "totals"),
            ("Under 2.5 buts",             prediction["p_under_2_5"], "totals"),
            ("BTTS â Les deux marquent",   prediction["p_btts"],      "btts"),
            ("BTTS Non",                   prediction["p_btts_no"],   "btts"),
        ]

        for bet_name, p_model, market_type in markets:
            # RÃ©cupÃ©rer la cote bookmaker (API ou simulation)
            odd_book = None

            if odds_data and "markets" in odds_data:
                # Tentative de rÃ©cupÃ©ration depuis l'API des cotes
                mkt = odds_data["markets"].get("h2h") if "1X2" in market_type else \
                      odds_data["markets"].get("totals")
                if mkt:
                    if "Victoire " + home in bet_name:
                        odd_book = mkt.get(home)
                    elif "Victoire " + away in bet_name:
                        odd_book = mkt.get(away)
                    elif "nul" in bet_name:
                        odd_book = mkt.get("Draw")

            # Fallback simulation si cote non disponible
            if not odd_book or not (self.min_odd <= odd_book <= self.max_odd):
                odd_book = self.simulate_bookmaker_odd(p_model)

            # Filtre sur la fourchette de cotes
            if not (self.min_odd <= odd_book <= self.max_odd):
                continue

            # Calcul de la valeur
            value = self.calculate_value(p_model, odd_book)

            if value >= self.min_value:
                bets.append({
                    "id":          fix.get("id", f"{fix.get('home', '?')}_{fix.get('away', '?')}") ,
                    "sport":       sport,
                    "competition": comp,
                    "match":       f"{home} vs {away}",
                    "bet_type":    bet_name,
                    "market":      market_type,
                    "odd":         odd_book,
                    "p_model":     round(p_model * 100, 1),
                    "p_implied":   round((1 / odd_book) * 100, 1),
                    "value":       round(value * 100, 2),
                    "confidence":  self._confidence_score(p_model, value, odd_book),
                })

        return bets

    def extract_basketball_bets(self, prediction: dict) -> List[dict]:
        """Extrait les paris d'une prÃ©diction basketball."""
        bets  = []
        fix   = prediction["fixture"]
        home  = fix["home"]
        away  = fix["away"]
        comp  = fix["competition"]

        markets = [
            ("Victoire " + home, prediction["p_home_win"]),
            ("Victoire " + away, prediction["p_away_win"]),
        ]

        for bet_name, p_model in markets:
            odd_book = self.simulate_bookmaker_odd(p_model)
            if not (self.min_odd <= odd_book <= self.max_odd):
                      continue
            value = self.calculate_value(p_model, odd_book)
            if value >= self.min_value:
                bets.append({
                    "id":          fix["id"],
                    "sport":       "Basketball",
                    "competition": comp,
                    "match":       f"{home} vs {away}",
                    "bet_type":    bet_name,
                    "market":      "winner",
                    "odd":         odd_book,
                    "p_model":     round(p_model * 100, 1),
                    "p_implied":   round((1 / odd_book) * 100, 1),
                    "value":       round(value * 100, 2),
                    "confidence":  self._confidence_score(p_model, value, odd_book),
                })

        return bets

    def extract_tennis_bets(self, prediction: dict) -> List[dict]:
        """Extrait les paris d'une prÃ©diction tennis."""
        bets  = []
        fix   = prediction["fixture"]
        home  = fix["home"]
        away  = fix["away"]
        comp  = fix["competition"]

        markets = [
            ("Victoire " + home, prediction["p_home_win"]),
            ("Victoire " + away, prediction["p_away_win"]),
        ]

        for bet_name, p_model in markets:
            odd_book = self.simulate_bookmaker_odd(p_model)
            if not (self.min_odd <= odd_book <= self.max_odd):
                continue
            value = self.calculate_value(p_model, odd_book)
            if value >= self.min_value:
                bets.append({
                    "id":          fix["id"],
                    "sport":       "Tennis",
                    "competition": comp,
                    "match":       f"{home} vs {away}",
                    "bet_type":    bet_name,
                    "market":      "match_winner",
                    "odd":         odd_book,
                    "p_model":     round(p_model * 100, 1),
                    "p_implied":   round((1 / odd_book) * 100, 1),
                    "value":       round(value * 100, 2),
                    "confidence":  self._confidence_score(p_model, value, odd_book),
                })

        return bets

    def _confidence_score(self, p_model: float, value: float, odd: float = 2.0) -> float:
        """Score de confiance basÃ© sur le critÃ¨re de Kelly fractionnel."""
        b = odd - 1
        if b <= 0:
            return 0.0
        q = 1 - p_model
        kelly_full = (b * p_model - q) / b
        if kelly_full <= 0:
            return 0.0
        kelly_frac = kelly_full * KELLY["fraction"]
        score = min(10.0, (kelly_frac * 100) / KELLY["max_stake_pct"] * 10)
        return round(score, 1)

    def extract_stats_bets(self, stats_prediction: dict, odds_data: dict = None) -> list:
        """
        Extrait les paris statistiques avec valeur (edge >= 5%).
        
        Args:
            stats_prediction: résultat de StatsModel.predict()
            odds_data: cotes bookmaker (optionnel, simulées si absent)
        
        Returns:
            list de dicts paris au format unifié
        """
        bets = []
        fixture = stats_prediction.get("fixture", {})
        stats_markets = stats_prediction.get("stats_markets", {})
        
        if not stats_markets:
            return bets
        
        match_name = f"{fixture.get('home', '?')} vs {fixture.get('away', '?')}"
        competition = fixture.get("competition", "Unknown")
        fix_id = fixture.get("id", 0)
        
        stat_labels_fr = {
            "corners": "corners",
            "fouls": "fautes",
            "cards": "cartons",
            "shots_on_target": "tirs cadrés",
        }
        
        for stat_type, markets in stats_markets.items():
            label_fr = stat_labels_fr.get(stat_type, stat_type)
            
            for market_key, market_data in markets.items():
                p_model = market_data["prob"]
                
                # Skip probabilités trop extrêmes
                if p_model < 0.25 or p_model > 0.85:
                    continue
                
                # Cote bookmaker (simulée si pas de données réelles)
                if odds_data and market_key in odds_data:
                    odd = odds_data[market_key]
                else:
                    # Simulation réaliste : marge bookmaker ~5-8%
                    margin = random.uniform(0.05, 0.08)
                    odd = round(1.0 / (p_model + margin * (1 - p_model)), 2)
                    odd = max(1.30, min(4.00, odd))
                
                # Calcul edge
                p_implied = 1.0 / odd
                value = (p_model * odd) - 1.0
                
                if value < 0.05:  # Minimum 5% edge
                    continue
                
                # Confiance (Kelly)
                b = odd - 1
                kelly_full = (b * p_model - (1 - p_model)) / b if b > 0 else 0
                kelly_frac = kelly_full * 0.25
                confidence = min(10.0, (kelly_frac * 100) / 5.0 * 10)
                confidence = round(max(1.0, confidence), 1)
                
                # Formater le label
                bet_label = market_data["label"]
                # Traduire en français
                bet_label = bet_label.replace("Over", "+").replace("Under", "-")
                bet_label = bet_label.replace("corners", "corners").replace("fouls", "fautes")
                bet_label = bet_label.replace("cards", "cartons").replace("shots_on_target", "tirs cadrés")
                
                bets.append({
                    "id": f"{fix_id}_stats_{market_key}",
                    "sport": "Football",
                    "competition": competition,
                    "match": match_name,
                    "bet_type": bet_label,
                    "market": f"stats_{stat_type}",
                    "odd": odd,
                    "p_model": round(p_model * 100, 1),
                    "p_implied": round(p_implied * 100, 1),
                    "value": round(value * 100, 1),
                    "confidence": confidence,
                })
        
        return bets

    def select_best_bets(self, all_bets: List[dict]) -> List[dict]:
        """
        Trie tous les paris par valeur dÃ©croissante.
        Ãlimine les doublons (mÃªme match, marchÃ©s incompatibles).
        """
        # Trier par valeur dÃ©croissante
        sorted_bets = sorted(all_bets, key=lambda x: x["value"], reverse=True)

        selected   = []
        used_ids   = {}   # id_match â liste des marchÃ©s dÃ©jÃ  sÃ©lectionnÃ©s
        stats_per_match = {}  # limite 1 pari stats par match

        for bet in sorted_bets:
            match_id = bet["id"]
            market   = bet["market"]

            if match_id not in used_ids:
                used_ids[match_id] = []

            current_markets = used_ids[match_id]

            # RÃ¨gles d'incompatibilitÃ© pour Ã©viter les paris redondants :
            # â Ne pas combiner Over ET Under du mÃªme match
            # â Ne pas combiner BTTS Oui ET Non du mÃªme match
            # â Ne pas mettre 2 paris de type 1X2 du mÃªme match
            incompatible = False

            if market == "totals" and "totals" in current_markets:
                incompatible = True
            elif market == "btts" and "btts" in current_markets:
                incompatible = True
            elif market == "1X2" and "1X2" in current_markets:
                incompatible = True
            elif market == "winner" and "winner" in current_markets:
                incompatible = True
            elif market == "match_winner" and "match_winner" in current_markets:
                incompatible = True

            if not incompatible:
                if bet.get("market", "").startswith("stats_"):
                    match_key = bet["match"]
                    if stats_per_match.get(match_key, 0) >= 1:
                        continue
                    stats_per_match[match_key] = stats_per_match.get(match_key, 0) + 1
                selected.append(bet)
                used_ids[match_id].append(market)

        return selected


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CLASSE 6 : CouponBuilder â Construction et formatage du coupon final
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class CouponBuilder:
    """
    Assemble les paris sÃ©lectionnÃ©s en un coupon cohÃ©rent.
    Ajuste la composition pour atteindre la cote cible (~5.0).
    Formate le coupon pour l'affichage console.
    """

    def __init__(self):
        self.min_sel    = VALUE_BETTING.get("min_selections", 4)
        self.max_sel    = VALUE_BETTING.get("max_selections", 10)
        self.target     = VALUE_BETTING["target_selections"]
        self.min_total  = VALUE_BETTING["min_total_odd"]
        self.max_total  = VALUE_BETTING["max_total_odd"]
        self.target_odd = VALUE_BETTING["target_total_odd"]

    def total_odd(self, bets: List[dict]) -> float:
        """Calcule la cote totale d'un coupon combinÃ©."""
        result = 1.0
        for bet in bets:
            result *= bet["odd"]
        return round(result, 2)

    def build(self, candidates: List[dict]) -> List[dict]:
        """
        Construit le coupon optimal depuis la liste de candidats.

        Algorithme amÃ©liorÃ© :
        1. Trie les candidats par valeur dÃ©croissante
        2. Cherche par recherche gloutonne la combinaison de N paris
           dont la cote totale est la plus proche de la cible (5.0)
        3. Ajuste si hors fourchette en ajoutant/remplaÃ§ant
        """
        if not candidates:
            logger.warning("Aucun pari valide trouvÃ© â coupon vide")
            return []

        n = len(candidates)

        # \u2500\u2500 Strat\u00e9gie 1 : recherche multi-taille (4 \u00e0 10 s\u00e9lections) \u2500\u2500
        # Teste toutes les tailles entre min_sel et max_sel pour trouver
        # la combinaison dont la cote totale est la plus proche de la cible
        best_coupon = []
        best_distance = float("inf")

        # Limiter la recherche exhaustive \u00e0 un pool raisonnable
        pool = candidates[:min(n, 12)]

        from itertools import combinations
        for size in range(self.min_sel, min(self.max_sel + 1, len(pool) + 1)):
            for combo in combinations(pool, size):
                combo = list(combo)
                total = self.total_odd(combo)
                dist = abs(total - self.target_odd)
                # Bonus si dans la fourchette acceptable
                if self.min_total <= total <= self.max_total:
                    dist -= 1.0
                # L\u00e9ger bonus pour plus de s\u00e9lections (coupon plus riche)
                dist -= len(combo) * 0.05
                if dist < best_distance:
                    best_distance = dist
                    best_coupon = combo

        if not best_coupon:
            best_coupon = candidates[:min(self.target, len(candidates))]

        # ââ StratÃ©gie 2 : ajustement fin si hors fourchette ââââââ
        coupon = list(best_coupon)
        total  = self.total_odd(coupon)

        if total < self.min_total:
            # Ajouter la sÃ©lection restante qui rapproche le plus de la cible
            remaining = [b for b in candidates if b not in coupon]
            if remaining:
                best_add = min(
                    remaining,
                    key=lambda b: abs(self.total_odd(coupon + [b]) - self.target_odd)
                )
                coupon.append(best_add)
                logger.info(f"Cote {total:.2f} â ajout d'une sÃ©lection (cible {self.target_odd})")

        elif total > self.max_total:
            # Remplacer la sÃ©lection la moins probable par une Ã  cote plus basse
            if len(coupon) > 2:
                riskiest = min(coupon, key=lambda x: x["p_model"])
                alternatives = [b for b in candidates
                                if b not in coupon and b["odd"] < riskiest["odd"]]
                if alternatives:
                    best_swap = min(
                        alternatives,
                        key=lambda b: abs(
                            self.total_odd(
                                [x for x in coupon if x is not riskiest] + [b]
                            ) - self.target_odd
                        )
                    )
                    coupon.remove(riskiest)
                    coupon.append(best_swap)
                    logger.info(f"Cote {total:.2f} â remplacement pour rester dans la cible")

        return coupon

    def format_coupon(self, coupon: List[dict], date: str) -> str:
        """
        Formate le coupon final pour affichage console.
        Retourne une chaÃ®ne de caractÃ¨res prÃªte Ã  l'emploi.
        """
        if not coupon:
            return "â ï¸  Aucune sÃ©lection valide pour aujourd'hui."

        total    = self.total_odd(coupon)
        avg_edge = round(sum(b["value"] for b in coupon) / len(coupon), 2)
        avg_conf = round(sum(b["confidence"] for b in coupon) / len(coupon), 1)

        lines = []

        # ââ En-tÃªte âââââââââââââââââââââââââââââââââââââââââââââââ
        lines.append("ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ")
        lines.append(f"â          ð¯  COUPON DU JOUR  â  {date}                 â")
        lines.append("ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ")
        lines.append("")
        lines.append("ð ANALYSE : ModÃ¨le Poisson (correction scores faibles) + ELO + Value Betting")
        lines.append("")

        # ââ SÃ©lections ââââââââââââââââââââââââââââââââââââââââââââ
        for i, bet in enumerate(coupon, start=1):
            sport_emoji = {
                "Football":   "â½",
                "Basketball": "ð",
                "Tennis":     "ð¾",
            }.get(bet["sport"], "ð")

            lines.append("â" * 64)
            lines.append(f"SÃLECTION {i} â {sport_emoji} {bet['sport']} â {bet['competition']}")
            lines.append(f"Match     : {bet['match']}")
            lines.append(f"Pari      : {bet['bet_type']}")
            lines.append(f"Cote      : {bet['odd']:.2f}")
            lines.append(
                f"Prob. modÃ¨le : {bet['p_model']}%  â  "
                f"Prob. implicite : {bet['p_implied']}%  â  "
                f"Edge : +{bet['value']}%"
            )
            lines.append(f"Confiance : {'â' * int(bet['confidence'] // 2)}"
                         f"{'â' * (5 - int(bet['confidence'] // 2))}  ({bet['confidence']}/10)")

        # ââ RÃ©sumÃ© ââââââââââââââââââââââââââââââââââââââââââââââââ
        lines.append("â" * 64)
        lines.append("")
        lines.append(f"ð°  COTE TOTALE          : {total:.2f}  "
                     f"({'â Dans la cible' if self.min_total <= total <= self.max_total else 'â ï¸ Hors cible'})")
        lines.append(f"ð°  MISE RECOMMANDÃE     : 2% du bankroll")
        lines.append(f"ð  EDGE MOYEN            : +{avg_edge}%")
        lines.append(f"ð  CONFIANCE MOYENNE    : {avg_conf}/10")
        lines.append(f"ð  NOMBRE DE SÃLECTIONS : {len(coupon)}")
        lines.append("")
        lines.append("â" * 64)
        lines.append("â ï¸   Ce coupon est gÃ©nÃ©rÃ© par algorithme statistique.")
        lines.append("    Les paris comportent un risque de perte en capital.")
        lines.append("    Jouez de faÃ§on responsable. Interdit aux mineurs.")
        lines.append("â" * 64)

        return "\n".join(lines)

    def to_dataframe(self, coupon: List[dict]) -> "pd.DataFrame":
        """Exporte le coupon au format DataFrame pandas."""
        if not coupon:
            return pd.DataFrame()
        return pd.DataFrame(coupon)[
            ["sport", "competition", "match", "bet_type", "odd",
             "p_model", "p_implied", "value", "confidence"]
        ]


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# POINT D'ENTRÃE PRINCIPAL
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def run_pipeline() -> Tuple[List[dict], str]:
    """
    Pipeline complet de gÃ©nÃ©ration du coupon.
    Retourne (coupon, texte_formate).
    """
    logger.info("â" * 60)
    logger.info("  DÃMARRAGE DU GÃNÃRATEUR DE COUPON SPORTIF")
    logger.info("â" * 60)

    # ââ 1. RÃ©cupÃ©ration des donnÃ©es âââââââââââââââââââââââââââââââ
    logger.info("ð¡ Ãtape 1/5 : RÃ©cupÃ©ration des donnÃ©esâ¦")
    fetcher = DataFetcher()

    if DEMO_MODE:
        logger.info("  â³ Mode dÃ©mo actif â utilisation de donnÃ©es simulÃ©es rÃ©alistes")
        data = fetcher.get_demo_data()
    else:
        logger.info("  \u21b3 Appel aux APIs en temps r\u00e9el\u2026")
        data = {"football": [], "basketball": [], "tennis": [], "date": fetcher.today}

        # \u2500\u2500 SOURCE PRIMAIRE : The Odds API pour TOUS les sports \u2500\u2500
        COMPETITION_NAMES = {
            "soccer_france_ligue_one": "Ligue 1",
            "soccer_epl": "Premier League",
            "soccer_england_league1": "Premier League",
            "soccer_germany_bundesliga": "Bundesliga",
            "soccer_spain_la_liga": "La Liga",
            "soccer_italy_serie_a": "Serie A",
            "soccer_uefa_champs_league": "Ligue des Champions",
            "basketball_nba": "NBA",
            "basketball_euroleague": "EuroLeague",
            "tennis_atp_french_open": "Roland-Garros ATP",
            "tennis_atp_us_open": "US Open ATP",
            "tennis_atp_wimbledon": "Wimbledon ATP",
            "tennis_atp_australian_open": "Open d'Australie ATP",
        }

        logger.info("  \u21b3 R\u00e9cup\u00e9ration via The Odds API pour tous les sports\u2026")
        for sport_key in ODDS_SPORTS:
            odds_events = fetcher.fetch_odds(sport_key)
            comp_name = COMPETITION_NAMES.get(sport_key, sport_key)

            for ev in odds_events:
                event = {
                    "id": ev.get("id", f"{ev['home']}_{ev['away']}"),
                    "sport": sport_key,
                    "competition": comp_name,
                    "home": ev["home"],
                    "away": ev["away"],
                    "date": fetcher.today,
                    "odds_h2h": ev["markets"].get("h2h", {}),
                }

                if sport_key.startswith("soccer_"):
                    # Stats Poisson par d\u00e9faut (moyennes de ligue europ\u00e9enne)
                    event["home_goals_avg"] = 1.35
                    event["away_goals_avg"] = 1.25
                    event["home_conceded_avg"] = 1.10
                    event["away_conceded_avg"] = 1.30
                    event["home_matches"] = 10
                    event["away_matches"] = 10
                    data["football"].append(event)
                elif sport_key.startswith("basketball_"):
                    data["basketball"].append(event)
                elif sport_key.startswith("tennis_"):
                    data["tennis"].append(event)

            if odds_events:
                logger.info(f"  \u21b3 {len(odds_events)} \u00e9v\u00e9nements {comp_name} via Odds API")

        # \u2500\u2500 ENRICHISSEMENT PRIORITAIRE : API-Football (RapidAPI) \u2500\u2500
        if data["football"]:
            logger.info("  \u21b3 Enrichissement football via API-Football (RapidAPI)\u2026")
            try:
                team_stats: Dict[str, dict] = {}
                for league_id in API_FOOTBALL_LEAGUES:
                    league_stats = fetcher.fetch_api_football_team_stats(league_id)
                    team_stats.update(league_stats)

                enriched_count = 0
                for fix in data["football"]:
                    home_s = team_stats.get(fix["home"])
                    away_s = team_stats.get(fix["away"])
                    if home_s and away_s:
                        fix["home_goals_avg"] = home_s["goals_avg"]
                        fix["away_goals_avg"] = away_s["goals_avg"]
                        fix["home_conceded_avg"] = home_s["conceded_avg"]
                        fix["away_conceded_avg"] = away_s["conceded_avg"]
                        fix["home_matches"] = home_s["matches"]
                        fix["away_matches"] = away_s["matches"]
                        enriched_count += 1

                if enriched_count:
                    logger.info(f"  \u21b3 {enriched_count}/{len(data['football'])} matchs enrichis via API-Football")
                else:
                    # Fallback : football-data.org
                    logger.info("  \u21b3 API-Football sans r\u00e9sultat, tentative football-data.org\u2026")
                    for code in FOOTBALL_COMPETITIONS:
                        standings = fetcher.fetch_football_standings(code)
                        for entry in standings:
                            if entry["played"] >= POISSON_PARAMS["min_matches"]:
                                team_stats[entry["team"]] = {
                                    "goals_avg": entry["goals_for"] / entry["played"],
                                    "conceded_avg": entry["goals_against"] / entry["played"],
                                    "matches": entry["played"],
                                }
                    for fix in data["football"]:
                        home_s = team_stats.get(fix["home"])
                        away_s = team_stats.get(fix["away"])
                        if home_s and away_s:
                            fix["home_goals_avg"] = home_s["goals_avg"]
                            fix["away_goals_avg"] = away_s["goals_avg"]
                            fix["home_conceded_avg"] = home_s["conceded_avg"]
                            fix["away_conceded_avg"] = away_s["conceded_avg"]
                            fix["home_matches"] = home_s["matches"]
                            fix["away_matches"] = away_s["matches"]
                            enriched_count += 1
                    if enriched_count:
                        logger.info(f"  \u21b3 {enriched_count}/{len(data['football'])} matchs enrichis via football-data.org")
            except Exception as e:
                logger.warning(f"  \u21b3 Enrichissement football \u00e9chou\u00e9 : {e} \u2014 stats par d\u00e9faut utilis\u00e9es")

        # \u2500\u2500 ENRICHISSEMENT BASKETBALL : BallDontLie (NBA) \u2500\u2500
        if data["basketball"]:
            logger.info("  \u21b3 Enrichissement basketball via BallDontLie\u2026")
            try:
                nba_stats = fetcher.fetch_balldontlie_team_stats()
                enriched_bball = 0
                for fix in data["basketball"]:
                    home_s = nba_stats.get(fix["home"])
                    away_s = nba_stats.get(fix["away"])
                    if home_s:
                        fix["home_elo"] = home_s["elo_approx"]
                        enriched_bball += 1
                    if away_s:
                        fix["away_elo"] = away_s["elo_approx"]
                if enriched_bball:
                    logger.info(f"  \u21b3 {enriched_bball} \u00e9quipes NBA enrichies avec ELO r\u00e9el via BallDontLie")
            except Exception as e:
                logger.warning(f"  \u21b3 Enrichissement BallDontLie \u00e9chou\u00e9 : {e} \u2014 ELO par d\u00e9faut utilis\u00e9")

        total_events = len(data["football"]) + len(data["basketball"]) + len(data["tennis"])
        logger.info(f"  \u21b3 Total : {total_events} \u00e9v\u00e9nements ({len(data['football'])} football, {len(data['basketball'])} basketball, {len(data['tennis'])} tennis)")

        if total_events == 0:
            logger.warning("  \u21b3 Aucun \u00e9v\u00e9nement trouv\u00e9 via Odds API \u2014 fallback d\u00e9mo")
            data = fetcher.get_demo_data()

    # ââ Calcul dynamique de la moyenne de buts par ligue ââ
    league_avg_goals_map = {}
    if not DEMO_MODE:
        for code in FOOTBALL_COMPETITIONS:
            standings = fetcher.fetch_football_standings(code)
            if standings:
                total_goals = sum(e["goals_for"] for e in standings if e["played"] > 0)
                total_matches = sum(e["played"] for e in standings if e["played"] > 0) / 2
                if total_matches > 0:
                    league_avg = total_goals / total_matches
                    league_avg_goals_map[FOOTBALL_COMPETITIONS[code]] = round(league_avg, 2)
                    logger.info(f"ð {FOOTBALL_COMPETITIONS[code]} : {league_avg:.2f} buts/match")

    # ââ 2. ModÃ©lisation football ââââââââââââââââââââââââââââââââââ
    logger.info("ð Ãtape 2/5 : ModÃ©lisation Poisson (correction scores faibles) (football)â¦")
    football_predictions = []

    for fixture in data["football"]:
        try:
            comp = fixture.get("competition", "")
            # [v2.0] Instanciation par ligue pour calibrer home_advantage
            league_avg = league_avg_goals_map.get(comp,
                         LEAGUE_AVG_GOALS.get(comp,
                         POISSON_PARAMS.get("default_league_avg_goals", 2.65)))
            poisson_model = PoissonModel(league_avg_goals=league_avg, league_name=comp)
            pred = poisson_model.predict(fixture)
            football_predictions.append(pred)
            logger.info(
                f"  â³ {fixture['home']} vs {fixture['away']} | "
                f"xG : {pred['lambda_home']:.2f}-{pred['lambda_away']:.2f} | "
                f"1X2 : {pred['p_home_win']*100:.0f}%/"
                f"{pred['p_draw']*100:.0f}%/"
                f"{pred['p_away_win']*100:.0f}%"
            )
        except Exception as e:
            logger.warning(f"  â³ Erreur prÃ©diction {fixture.get('home','?')} : {e}")

    # ââ 3. ModÃ©lisation basketball + tennis âââââââââââââââââââââââ
    logger.info("ð Ãtape 3/5 : ModÃ©lisation ELO (basketball) + Tennisâ¦")
    elo_model    = EloModel()
    tennis_model = TennisModel()

    bball_predictions  = []
    tennis_predictions = []

    for fixture in data.get("basketball", []):
        try:
            pred = elo_model.predict(fixture)
            bball_predictions.append(pred)
            logger.info(
                f"  â³ [NBA] {fixture['home']} vs {fixture['away']} | "
                f"P(home) : {pred['p_home_win']*100:.0f}%"
            )
        except Exception as e:
            logger.warning(f"  â³ Erreur prÃ©diction basket : {e}")

    for fixture in data.get("tennis", []):
        try:
            pred = tennis_model.predict(fixture)
            tennis_predictions.append(pred)
            logger.info(
                f"  \u21b3 [Tennis] {fixture['home']} vs {fixture['away']} | "
                f"P(home) : {pred['p_home_win']*100:.0f}%"
            )
        except Exception as e:
            logger.warning(f"  \u21b3 Erreur prÃ©diction tennis : {e}")

    # ââ 4. Extraction des paris Ã  valeur positive âââââââââââââââââ
    logger.info("ð Ãtape 4/5 : Identification des value betsâ¦")
    selector = ValueBetSelector()
    selector.noisy_odd_fn = data.get("noisy_odd")

    all_bets = []

    for pred in football_predictions:
        fixture = pred.get("fixture", {})
        odds_data = None
        if "odds_h2h" in fixture:
            odds_data = {"markets": {"h2h": fixture["odds_h2h"]}}
        bets = selector.extract_football_bets(pred, odds_data=odds_data)
        all_bets.extend(bets)

    # --- Marchés statistiques football ---
    try:
        stats_model = StatsModel()
        if stats_model.config.get("enabled", False):
            football_fixtures = [pred.get("fixture", {}) for pred in football_predictions]
            stats_data = fetcher.fetch_football_stats(football_fixtures)
            
            for pred in football_predictions:
                fixture = pred.get("fixture", {})
                fix_id = fixture.get("id", 0)
                fix_stats = stats_data.get(fix_id)
                
                if fix_stats:
                    stats_pred = stats_model.predict(fixture, fix_stats)
                    stats_bets = selector.extract_stats_bets(stats_pred)
                    all_bets.extend(stats_bets)
            
            logger.info(f"Paris stats ajoutés: {len([b for b in all_bets if b.get('market', '').startswith('stats_')])}")
    except Exception as e:
        logger.error(f"Erreur marchés statistiques: {e}")

    for pred in bball_predictions:
        bets = selector.extract_basketball_bets(pred)
        all_bets.extend(bets)

    for pred in tennis_predictions:
        bets = selector.extract_tennis_bets(pred)
        all_bets.extend(bets)

    # SÃ©lection des meilleurs paris sans doublons
    best_bets = selector.select_best_bets(all_bets)
    logger.info(f"  â³ {len(all_bets)} paris candidats â {len(best_bets)} retenus aprÃ¨s filtrage")

    # ââ 5. Construction et affichage du coupon ââââââââââââââââââââ
    logger.info("ðï¸  Ãtape 5/5 : Construction du coupon optimalâ¦")
    builder = CouponBuilder()
    coupon  = builder.build(best_bets)

    logger.info(
        f"  â³ Coupon final : {len(coupon)} sÃ©lections â "
        f"Cote totale : {builder.total_odd(coupon):.2f}"
    )

    # Affichage du coupon formatÃ©
    coupon_text = builder.format_coupon(coupon, data["date"])

    # Export DataFrame (optionnel)
    df = builder.to_dataframe(coupon)
    if not df.empty:
        logger.info("\nð RÃ©capitulatif tabulaire :")
        logger.info("\n" + df.to_string(index=False))

    logger.info("â" * 60)
    logger.info("  GÃNÃRATION TERMINÃE")
    logger.info("â" * 60)

    return coupon, coupon_text


if __name__ == "__main__":
    # ExÃ©cution principale
    try:
        coupon, coupon_text = run_pipeline()
        print("\n")
        print(coupon_text)
    except KeyboardInterrupt:
        print("\nâ ï¸  Interruption par l'utilisateur.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Erreur critique : {e}", exc_info=True)
        sys.exit(1)
