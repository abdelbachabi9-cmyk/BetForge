#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║         GÉNÉRATEUR DE COUPON DE PARIS SPORTIFS QUOTIDIEN         ║
║         Modèle : Poisson + correction dépendance + ELO + Value   ║
║         Version : 2.0 | Python 3.10+                             ║
╚══════════════════════════════════════════════════════════════════╝

Changements v2.0 :
  - Value betting corrigé (plus de raisonnement circulaire)
  - Backtesting intégré avec historique JSON
  - Kelly Criterion pour le sizing des mises
  - Cache intégré pour réduire les appels API
  - Code dédupliqué (extract_bets générique)
  - np.random.Generator au lieu du seed global
  - Meilleur modèle Tennis (H2H, fatigue)
  - Exponential backoff sur les retries API
  - Aucun secret en dur

Utilisation :
    python coupon_generator.py

Prérequis :
    pip install requests numpy scipy pandas
"""

import json
import math
import os
import re
import random
import logging
import time as _time
from collections import Counter
from datetime import datetime, timedelta
from functools import reduce
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import poisson
import pandas as pd
import requests

# Import de la configuration locale
try:
    from config import (
        API_KEYS, ENDPOINTS, FOOTBALL_COMPETITIONS, ODDS_SPORTS,
        POISSON_PARAMS, ELO_PARAMS, TENNIS_PARAMS, VALUE_BETTING,
        KELLY, NETWORK, CACHE, DEMO_MODE, BACKTEST, TEAM_ALIASES,
    )
except ImportError:
    # Valeurs par défaut minimales si config.py est absent
    API_KEYS = {"football_data": "", "odds_api": "", "api_football": ""}
    ENDPOINTS = {
        "football_data_base": "https://api.football-data.org/v4",
        "odds_api_base":      "https://api.the-odds-api.com/v4",
        "thesportsdb_base":   "https://www.thesportsdb.com/api/v1/json/3",
    }
    FOOTBALL_COMPETITIONS = {
        "PL": "Premier League", "PD": "La Liga",
        "BL1": "Bundesliga", "SA": "Serie A", "FL1": "Ligue 1",
    }
    ODDS_SPORTS = [
        "soccer_france_ligue_one", "soccer_england_league1",
        "soccer_germany_bundesliga", "soccer_spain_la_liga",
        "soccer_italy_serie_a", "basketball_nba",
    ]
    POISSON_PARAMS = {
        "home_advantage": 1.1, "max_goals": 10,
        "goals_threshold": 2.5, "min_matches": 5,
        "low_score_rho": -0.13, "default_league_avg_goals": 2.65,
    }
    ELO_PARAMS = {"initial_rating": 1500, "k_factor": 20, "home_bonus": 50}
    TENNIS_PARAMS = {"surface_weight": 0.15, "form_weight": 0.08, "h2h_weight": 0.10}
    VALUE_BETTING = {
        "min_value": 0.05, "min_odd": 1.30, "max_odd": 4.00,
        "target_selections": 4, "target_total_odd": 5.0,
        "min_total_odd": 4.5, "max_total_odd": 6.0,
    }
    KELLY = {"fraction": 0.25, "min_stake_pct": 0.5, "max_stake_pct": 5.0}
    NETWORK = {"timeout": 10, "max_retries": 3, "retry_delay": 1.0}
    CACHE = {"api_data_ttl": 3600, "coupon_ttl": 900}
    DEMO_MODE = True
    BACKTEST = {"history_file": "coupon_history.json", "auto_track": True}
    TEAM_ALIASES: dict = {}

# ── Logger ────────────────────────────────────────────────────────
logger = logging.getLogger("APEX-Engine")


# ══════════════════════════════════════════════════════════════════
# UTILITAIRE : Normalisation des noms d'équipes (R1)
# ══════════════════════════════════════════════════════════════════

# Suffixes géographiques et de forme juridique à supprimer pour le matching
_TEAM_SUFFIXES = [
    " fc", " cf", " sc", " ac", " as", " ss", " afc", " bsc", " rsc",
    " london", " madrid", " munich", " münchen", " milano", " milan",
    " de marseille", " saint-germain",
    " united", " city", " town", " rovers",
    " wanderers", " athletic", " albion",
    " hotspur", " county", " palace",
]


def normalize_team_name(name: str) -> str:
    """
    Normalise le nom d'une équipe pour le matching cross-API.

    Applique dans l'ordre :
    1. Résolution des alias manuels (TEAM_ALIASES)
    2. Suppression des suffixes géographiques/juridiques courants
    3. Nettoyage des ponctuation et tirets

    Returns:
        Nom normalisé en minuscules, utilisable comme clé de lookup.
    """
    normalized = name.lower().strip()

    # 1. Alias manuels (résout PSG → paris saint-germain, etc.)
    if normalized in TEAM_ALIASES:
        normalized = TEAM_ALIASES[normalized]

    # 2. Supprimer les suffixes courants
    for suffix in _TEAM_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
            break  # un seul suffixe à la fois

    # 3. Normaliser la ponctuation
    normalized = normalized.replace(".", "").replace("-", " ")

    return normalized


# ══════════════════════════════════════════════════════════════════
# UTILITAIRE : Cache en mémoire avec TTL
# ══════════════════════════════════════════════════════════════════

class TTLCache:
    """Cache en mémoire simple avec TTL par clé."""

    def __init__(self):
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Retourne la valeur si elle existe et n'est pas expirée."""
        if key in self._store:
            expires_at, value = self._store[key]
            if _time.time() < expires_at:
                return value
            del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Stocke une valeur avec un TTL en secondes."""
        self._store[key] = (_time.time() + ttl, value)

    def clear(self) -> None:
        """Vide le cache."""
        self._store.clear()


# Cache global
_cache = TTLCache()


# ══════════════════════════════════════════════════════════════════
# CLASSE 1 : DataFetcher — Récupération des données (API + fallback)
# ══════════════════════════════════════════════════════════════════

class DataFetcher:
    """
    Récupère les données sportives depuis les APIs gratuites disponibles.
    En cas d'échec, bascule sur des données simulées réalistes.
    Intègre un cache TTL et un exponential backoff sur les retries.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BetForge/2.0"})
        self.tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.today = datetime.now().strftime("%Y-%m-%d")
        # Générateur aléatoire local (pas de state global)
        seed = int(datetime.now().strftime("%Y%m%d"))
        self._rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)
        # Circuit breaker : APIs en erreur
        self._broken_apis: Dict[str, float] = {}

    def _is_api_broken(self, api_name: str) -> bool:
        """Vérifie si une API est en circuit-break (down > 5 min)."""
        if api_name in self._broken_apis:
            if _time.time() - self._broken_apis[api_name] < 300:
                return True
            del self._broken_apis[api_name]
        return False

    def _mark_api_broken(self, api_name: str) -> None:
        """Marque une API comme en panne."""
        self._broken_apis[api_name] = _time.time()

    def _get(self, url: str, headers: dict = None,
             params: dict = None, api_name: str = "default") -> Optional[dict]:
        """
        Effectue un appel GET avec :
        - Cache TTL
        - Exponential backoff
        - Circuit breaker
        """
        # Circuit breaker
        if self._is_api_broken(api_name):
            logger.debug(f"API {api_name} en circuit-break — ignorée")
            return None

        # Cache
        cache_key = f"api:{url}:{json.dumps(params or {}, sort_keys=True)}"
        cached = _cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit pour {url}")
            return cached

        max_retries = NETWORK["max_retries"]
        base_delay = NETWORK.get("retry_delay", 1.0)

        for attempt in range(max_retries):
            try:
                resp = self.session.get(
                    url,
                    headers=headers or {},
                    params=params or {},
                    timeout=NETWORK["timeout"],
                )
                if resp.status_code == 200:
                    data = resp.json()
                    _cache.set(cache_key, data, CACHE["api_data_ttl"])
                    return data
                elif resp.status_code == 429:
                    logger.warning(f"Quota API dépassé ({api_name})")
                    self._mark_api_broken(api_name)
                    return None
                else:
                    logger.warning(
                        f"HTTP {resp.status_code} pour {api_name} "
                        f"(tentative {attempt + 1}/{max_retries})"
                    )
            except requests.Timeout:
                logger.warning(
                    f"Timeout {api_name} ({attempt + 1}/{max_retries})"
                )
            except requests.ConnectionError:
                logger.warning(f"Connexion impossible : {api_name}")
                self._mark_api_broken(api_name)
                return None
            except Exception as e:
                logger.warning(f"Erreur inattendue ({api_name}) : {e}")
                return None

            # Exponential backoff avant le prochain retry
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                _time.sleep(delay)

        self._mark_api_broken(api_name)
        return None

    # ── Football-data.org ──────────────────────────────────────────

    def fetch_football_fixtures(self, competition_code: str) -> List[dict]:
        """Récupère les matchs de demain depuis football-data.org."""
        if not API_KEYS.get("football_data"):
            return []

        url = f"{ENDPOINTS['football_data_base']}/competitions/{competition_code}/matches"
        headers = {"X-Auth-Token": API_KEYS["football_data"]}
        params = {"dateFrom": self.today, "dateTo": self.today}

        data = self._get(url, headers=headers, params=params, api_name="football_data")
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
        """Récupère le classement pour calculer les forces d'attaque/défense."""
        if not API_KEYS.get("football_data"):
            return []

        url = f"{ENDPOINTS['football_data_base']}/competitions/{competition_code}/standings"
        headers = {"X-Auth-Token": API_KEYS["football_data"]}

        data = self._get(url, headers=headers, api_name="football_data")
        if not data:
            return []

        standings = []
        for table in data.get("standings", []):
            if table.get("type") == "TOTAL":
                for entry in table.get("table", []):
                    standings.append({
                        "team":          entry["team"]["name"],
                        "played":        entry["playedGames"],
                        "goals_for":     entry["goalsFor"],
                        "goals_against": entry["goalsAgainst"],
                    })
        return standings

    # ── The-Odds-API ───────────────────────────────────────────────

    def fetch_odds(self, sport_key: str) -> List[dict]:
        """
        Récupère les VRAIES cotes bookmaker depuis the-odds-api.com.
        C'est la source de vérité pour le value betting.
        """
        if not API_KEYS.get("odds_api"):
            return []

        url = f"{ENDPOINTS['odds_api_base']}/sports/{sport_key}/odds"
        params = {
            "apiKey":     API_KEYS["odds_api"],
            "regions":    "eu",
            "markets":    "h2h,totals",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }

        data = self._get(url, params=params, api_name="odds_api")
        if not isinstance(data, list):
            return []

        odds_list = []
        for game in data:
            commence = game.get("commence_time", "")[:10]
            if commence != self.today:
                continue

            entry = {
                "id":    game.get("id"),
                "home":  game.get("home_team"),
                "away":  game.get("away_team"),
                "sport": sport_key,
                "markets": {},
            }

            # Moyenne des cotes de TOUS les bookmakers (pas juste le premier)
            market_odds: Dict[str, Dict[str, List[float]]] = {}
            for bookmaker in game.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    key = market.get("key")
                    if key not in market_odds:
                        market_odds[key] = {}
                    for outcome in market.get("outcomes", []):
                        name = outcome["name"]
                        if name not in market_odds[key]:
                            market_odds[key][name] = []
                        market_odds[key][name].append(outcome["price"])

            # Calculer les cotes moyennes
            for mkt_key, outcomes in market_odds.items():
                entry["markets"][mkt_key] = {
                    name: round(sum(prices) / len(prices), 2)
                    for name, prices in outcomes.items()
                }

            odds_list.append(entry)

        return odds_list

    def fetch_all_odds(self) -> Dict[str, List[dict]]:
        """Récupère les cotes pour tous les sports configurés."""
        all_odds = {}
        for sport_key in ODDS_SPORTS:
            odds = self.fetch_odds(sport_key)
            if odds:
                all_odds[sport_key] = odds
        return all_odds

    # ── TheSportsDB (multi-sports) ──────────────────────────────────

    def fetch_thesportsdb_events(self, league_id: str) -> List[dict]:
        """Récupère les événements à venir depuis TheSportsDB."""
        url = f"{ENDPOINTS['thesportsdb_base']}/eventsnextleague.php"
        params = {"id": league_id}

        data = self._get(url, params=params, api_name="thesportsdb")
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

    # ── Données simulées réalistes (mode démo / fallback) ────────────

    def get_demo_data(self) -> Dict:
        """
        Génère un jeu de données réalistes simulant des matchs de demain.
        ATTENTION : les cotes simulées sont marquées comme telles.
        """
        rng = self._rng
        np_rng = self._np_rng

        # ── Matchs de football simulés ──────────────────────────────
        football_fixtures = [
            {
                "id": 1001, "sport": "Football", "competition": "Premier League",
                "home": "Arsenal", "away": "Chelsea",
                "home_goals_avg": 2.1, "away_goals_avg": 1.6,
                "home_conceded_avg": 1.0, "away_conceded_avg": 1.3,
                "home_matches": 28, "away_matches": 28,
            },
            {
                "id": 1002, "sport": "Football", "competition": "La Liga",
                "home": "Real Madrid", "away": "Atletico Madrid",
                "home_goals_avg": 2.4, "away_goals_avg": 1.4,
                "home_conceded_avg": 0.8, "away_conceded_avg": 0.9,
                "home_matches": 29, "away_matches": 29,
            },
            {
                "id": 1003, "sport": "Football", "competition": "Bundesliga",
                "home": "Bayern Munich", "away": "Borussia Dortmund",
                "home_goals_avg": 2.7, "away_goals_avg": 2.0,
                "home_conceded_avg": 0.9, "away_conceded_avg": 1.5,
                "home_matches": 27, "away_matches": 27,
            },
            {
                "id": 1004, "sport": "Football", "competition": "Ligue 1",
                "home": "PSG", "away": "Olympique de Marseille",
                "home_goals_avg": 2.5, "away_goals_avg": 1.7,
                "home_conceded_avg": 0.7, "away_conceded_avg": 1.2,
                "home_matches": 26, "away_matches": 26,
            },
            {
                "id": 1005, "sport": "Football", "competition": "Serie A",
                "home": "Inter Milan", "away": "AC Milan",
                "home_goals_avg": 2.2, "away_goals_avg": 1.9,
                "home_conceded_avg": 0.8, "away_conceded_avg": 1.0,
                "home_matches": 27, "away_matches": 27,
            },
            {
                "id": 1006, "sport": "Football", "competition": "Ligue des Champions",
                "home": "Manchester City", "away": "Paris Saint-Germain",
                "home_goals_avg": 2.3, "away_goals_avg": 1.8,
                "home_conceded_avg": 0.9, "away_conceded_avg": 1.1,
                "home_matches": 8, "away_matches": 8,
            },
            {
                "id": 1007, "sport": "Football", "competition": "Premier League",
                "home": "Liverpool", "away": "Manchester United",
                "home_goals_avg": 2.3, "away_goals_avg": 1.5,
                "home_conceded_avg": 0.9, "away_conceded_avg": 1.4,
                "home_matches": 28, "away_matches": 28,
            },
        ]

        # ── Matchs de basketball simulés ────────────────────────────
        basketball_fixtures = [
            {
                "id": 2001, "sport": "Basketball", "competition": "NBA",
                "home": "Boston Celtics", "away": "Miami Heat",
                "home_elo": 1650, "away_elo": 1580,
                "home_form": [1, 1, 0, 1, 1],
                "away_form": [1, 0, 1, 0, 1],
                "home_ppg": 117.2, "away_ppg": 110.8,  # R8 : points par match
                "home_matches": 58, "away_matches": 58,
            },
            {
                "id": 2002, "sport": "Basketball", "competition": "NBA",
                "home": "Golden State Warriors", "away": "LA Lakers",
                "home_elo": 1610, "away_elo": 1595,
                "home_form": [1, 0, 1, 1, 0],
                "away_form": [0, 1, 1, 0, 1],
                "home_ppg": 112.5, "away_ppg": 113.1,  # R8 : points par match
                "home_matches": 57, "away_matches": 57,
            },
        ]

        # ── Matchs de tennis simulés ────────────────────────────────
        tennis_fixtures = [
            {
                "id": 3001, "sport": "Tennis", "competition": "ATP Masters",
                "home": "Carlos Alcaraz", "away": "Novak Djokovic",
                "surface": "clay",
                "home_ranking": 2, "away_ranking": 3,
                "home_surface_winrate": 0.78, "away_surface_winrate": 0.72,
                "home_form": [1, 1, 1, 0, 1], "away_form": [1, 0, 1, 1, 0],
                "h2h_home_wins": 3, "h2h_away_wins": 5,
                "home_matches_last_30d": 8, "away_matches_last_30d": 6,
            },
        ]

        # ── Cotes bookmaker INDÉPENDANTES ────────────────────────────
        # En mode démo, on simule des cotes qui ne dépendent PAS
        # des probabilités modèle, pour éviter le raisonnement circulaire.
        # On simule la perspective du bookmaker avec sa propre estimation.
        def independent_demo_odd(true_prob: float, bookmaker_error: float = 0.07,
                                  margin: float = 0.05) -> float:
            """
            Simule une cote bookmaker indépendante.
            Le bookmaker a sa propre estimation (avec erreur aléatoire)
            et applique sa marge.

            bookmaker_error=0.07 : erreur bookmaker ±7%, calibrée pour que des
            value bets (edge ≥ 5%) apparaissent en mode démo sur toute la plage
            de probabilités (0.13–0.56). Valeur de 0.025 était trop stricte —
            rendait mathématiquement impossible tout value bet pour p > 27%.
            """
            # Le bookmaker estime la proba avec une erreur aléatoire
            bookie_estimate = true_prob + rng.uniform(-bookmaker_error, bookmaker_error)
            bookie_estimate = max(0.03, min(0.97, bookie_estimate))
            # Il applique sa marge
            implied = bookie_estimate * (1 + margin)
            raw = 1 / implied if implied > 0 else 99.0
            return round(max(1.05, raw), 2)

        return {
            "football":   football_fixtures,
            "basketball": basketball_fixtures,
            "tennis":     tennis_fixtures,
            "date":       self.today,
            "demo_odd_fn": independent_demo_odd,
            "is_demo":    True,
        }

    def fetch_match_results(self, date: str) -> List[dict]:
        """
        Récupère les scores finaux des matchs de football d'une date donnée (R4).
        Source : football-data.org (seule API gratuite avec scores).

        Args:
            date: Date au format YYYY-MM-DD

        Returns:
            Liste de dicts {match_key, home, away, home_score, away_score,
            total_goals, home_won, is_draw}
        """
        if not API_KEYS.get("football_data"):
            logger.debug("fetch_match_results : FOOTBALL_DATA_KEY absent — impossible")
            return []

        results = []
        for code in FOOTBALL_COMPETITIONS:
            url = f"{ENDPOINTS['football_data_base']}/competitions/{code}/matches"
            headers = {"X-Auth-Token": API_KEYS["football_data"]}
            params = {"dateFrom": date, "dateTo": date, "status": "FINISHED"}

            data = self._get(url, headers=headers, params=params,
                             api_name="football_data")
            if not data:
                continue

            for match in data.get("matches", []):
                score = match.get("score", {})
                full_time = score.get("fullTime", {})
                home_score = full_time.get("home")
                away_score = full_time.get("away")

                if home_score is None or away_score is None:
                    continue

                home = match["homeTeam"]["name"]
                away = match["awayTeam"]["name"]
                results.append({
                    "match_key":   f"{home} vs {away}",
                    "home":        home,
                    "away":        away,
                    "home_score":  home_score,
                    "away_score":  away_score,
                    "total_goals": home_score + away_score,
                    "home_won":    home_score > away_score,
                    "is_draw":     home_score == away_score,
                    "date":        date,
                    "competition": FOOTBALL_COMPETITIONS.get(code, code),
                })

        logger.info(f"fetch_match_results : {len(results)} résultats récupérés pour {date}")
        return results


# ══════════════════════════════════════════════════════════════════
# CLASSE 2 : PoissonModel — Modèle football (Poisson + correction dépendance)
# ══════════════════════════════════════════════════════════════════

class PoissonModel:
    """
    Modèle statistique de prédiction football basé sur la distribution
    de Poisson indépendant avec correction de dépendance sur les faibles
    scores (paramètre rho inspiré de Dixon-Coles, 1997).

    ⚠️  Ce n'est PAS un vrai Dixon-Coles (pas de MLE). Le paramètre rho
    est une valeur empirique fixe, non estimée sur données historiques.
    """

    def __init__(self, league_avg_goals: float = None, rho: Optional[float] = None):
        self.league_avg_goals = league_avg_goals or POISSON_PARAMS.get(
            "default_league_avg_goals", 2.65
        )
        self.home_adv = POISSON_PARAMS["home_advantage"]
        self.max_goals = POISSON_PARAMS["max_goals"]
        self.goals_thresh = POISSON_PARAMS["goals_threshold"]
        # R3 : rho peut être passé explicitement (par ligue) ou via config
        self.rho = rho if rho is not None else POISSON_PARAMS.get(
            "default_rho",
            POISSON_PARAMS.get("low_score_rho", -0.13),
        )

    @staticmethod
    def get_rho_for_league(league_code: str) -> float:
        """Retourne le rho Dixon-Coles pour une ligue donnée (R3)."""
        league_rho_table = POISSON_PARAMS.get("league_rho", {})
        default = POISSON_PARAMS.get("default_rho", -0.13)
        return league_rho_table.get(league_code, default)

    def calculate_lambdas(self, fixture: dict,
                          league_avg_goals: Optional[float] = None) -> Tuple[float, float]:
        """
        Calcule les paramètres lambda (buts attendus) pour chaque équipe.
        lambda_home = att_home × def_away × avg_goals × home_adv
        lambda_away = att_away × def_home × avg_goals

        Args:
            fixture: Données du match (home_goals_avg, away_goals_avg, etc.)
            league_avg_goals: Moyenne de buts de la ligue (prioritaire sur self.league_avg_goals).
                              Accepter ce paramètre évite la mutation de self et garantit
                              la thread-safety.
        """
        avg = league_avg_goals if league_avg_goals is not None else self.league_avg_goals

        att_home = fixture["home_goals_avg"] / avg
        att_away = fixture["away_goals_avg"] / avg
        def_home = fixture["home_conceded_avg"] / avg
        def_away = fixture["away_conceded_avg"] / avg

        lambda_home = att_home * def_away * avg * self.home_adv
        lambda_away = att_away * def_home * avg

        return round(lambda_home, 4), round(lambda_away, 4)

    def _low_score_tau(self, goals_h: int, goals_a: int,
                       lambda_h: float, lambda_a: float,
                       rho: Optional[float] = None) -> float:
        """Correction de dépendance pour les scores faibles (inspiré Dixon-Coles).

        Args:
            rho: Paramètre de correction. Si None, utilise self.rho.
        """
        r = rho if rho is not None else self.rho
        if goals_h == 0 and goals_a == 0:
            return 1 - lambda_h * lambda_a * r
        elif goals_h == 0 and goals_a == 1:
            return 1 + lambda_h * r
        elif goals_h == 1 and goals_a == 0:
            return 1 + lambda_a * r
        elif goals_h == 1 and goals_a == 1:
            return 1 - r
        return 1.0

    def score_matrix(self, lambda_home: float, lambda_away: float,
                     rho: Optional[float] = None) -> np.ndarray:
        """
        Matrice de probabilités de scores.
        score_matrix[i][j] = P(domicile marque i, extérieur marque j)

        Args:
            rho: Paramètre de correction par ligue (R3). Si None, utilise self.rho.
        """
        max_g = self.max_goals
        matrix = np.zeros((max_g + 1, max_g + 1))

        for i in range(max_g + 1):
            for j in range(max_g + 1):
                p = poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
                tau = self._low_score_tau(i, j, lambda_home, lambda_away, rho=rho)
                matrix[i][j] = p * tau

        total = matrix.sum()
        if total > 0:
            matrix /= total

        return matrix

    def predict(self, fixture: dict) -> Dict[str, Any]:
        """Prédit toutes les probabilités pour un match de football."""
        # R7 FIX : passer league_avg_goals en paramètre au lieu de muter self
        # → thread-safe même si plusieurs matchs sont traités en parallèle
        league_avg = fixture.get("league_avg_goals") or self.league_avg_goals
        lambda_h, lambda_a = self.calculate_lambdas(fixture, league_avg_goals=league_avg)

        # R3 FIX : résoudre rho selon la ligue du fixture
        league_code = fixture.get("league_code", "")
        rho = self.get_rho_for_league(league_code)

        matrix = self.score_matrix(lambda_h, lambda_a, rho=rho)

        # Probabilités 1X2
        # matrix[i][j] = P(home=i buts, away=j buts)
        # tril(k=-1) : entrées où i > j → home_goals > away_goals → victoire domicile
        # triu(k=+1) : entrées où j > i → away_goals > home_goals → victoire extérieur
        p_home = float(np.sum(np.tril(matrix, -1)))
        p_draw = float(np.sum(np.diag(matrix)))
        p_away = float(np.sum(np.triu(matrix, 1)))

        # Over/Under 2.5 buts
        p_over = 0.0
        p_under = 0.0
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                if i + j > self.goals_thresh:
                    p_over += matrix[i][j]
                else:
                    p_under += matrix[i][j]

        # BTTS (Both Teams To Score)
        p_btts = float(
            1
            - np.sum(matrix[0, :])
            - np.sum(matrix[:, 0])
            + matrix[0, 0]
        )

        # Score le plus probable
        max_idx = np.unravel_index(np.argmax(matrix), matrix.shape)

        return {
            "sport":             "Football",
            "fixture":           fixture,
            "lambda_home":       lambda_h,
            "lambda_away":       lambda_a,
            "p_home_win":        round(p_home, 4),
            "p_draw":            round(p_draw, 4),
            "p_away_win":        round(p_away, 4),
            "p_over_2_5":        round(p_over, 4),
            "p_under_2_5":       round(p_under, 4),
            "p_btts":            round(p_btts, 4),
            "p_btts_no":         round(1 - p_btts, 4),
            "most_likely_score": f"{max_idx[0]}-{max_idx[1]}",
        }


# ══════════════════════════════════════════════════════════════════
# CLASSE 3 : EloModel — Modèle basketball (ELO adapté)
# ══════════════════════════════════════════════════════════════════

class EloModel:
    """
    Modèle ELO adapté pour la prédiction basketball.
    Rating ELO + bonus domicile + ajustement forme récente.
    Charge les ratings pré-entraînés depuis nba_elo_ratings.json si disponible (R2).
    """

    def __init__(self, ratings_file: Optional[str] = None):
        self.ratings: Dict[str, float] = {}
        self.k = ELO_PARAMS["k_factor"]
        self.initial = ELO_PARAMS["initial_rating"]
        self.home_bonus = ELO_PARAMS["home_bonus"]
        # R2 : charger les ratings pré-entraînés si disponibles
        self._ratings_loaded = False
        file_path = ratings_file or ELO_PARAMS.get("ratings_file", "nba_elo_ratings.json")
        self._load_pretrained_ratings(file_path)

    def _load_pretrained_ratings(self, ratings_file: str) -> None:
        """
        Charge les ratings ELO pré-entraînés depuis un fichier JSON (R2).
        Les ratings sont générés par nba_elo_bootstrap.py.

        Args:
            ratings_file: Chemin du fichier JSON de ratings.
        """
        path = Path(ratings_file)
        if not path.exists():
            logger.debug(
                f"Fichier ELO non trouvé : {ratings_file} "
                "(exécutez nba_elo_bootstrap.py pour générer les ratings)"
            )
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            loaded = data.get("ratings", {})
            self.ratings.update(loaded)
            self._ratings_loaded = True
            logger.info(
                f"✅ ELO NBA chargés : {len(loaded)} équipes "
                f"(généré le {data.get('generated_at', 'N/A')[:10]})"
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Impossible de charger les ratings ELO : {e}")

    def save_ratings(self, output_file: Optional[str] = None) -> None:
        """
        Sauvegarde les ratings ELO courants dans un fichier JSON.

        Args:
            output_file: Chemin de sortie. Si None, utilise ELO_PARAMS['ratings_file'].
        """
        path = Path(output_file or ELO_PARAMS.get("ratings_file", "nba_elo_ratings.json"))
        data = {
            "generated_at": datetime.now().isoformat(),
            "total_teams": len(self.ratings),
            "ratings": {k: round(v, 2) for k, v in sorted(self.ratings.items())},
        }
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info(f"Ratings ELO sauvegardés dans {path}")
        except OSError as e:
            logger.warning(f"Impossible de sauvegarder les ratings ELO : {e}")

    def get_rating(self, team: str) -> float:
        return self.ratings.get(team, self.initial)

    def update(self, home: str, away: str, home_won: bool) -> None:
        """Met à jour les ratings ELO après un match."""
        r_home = self.get_rating(home) + self.home_bonus
        r_away = self.get_rating(away)
        e_home = 1 / (1 + 10 ** ((r_away - r_home) / 400))
        s_home = 1.0 if home_won else 0.0
        self.ratings[home] = self.get_rating(home) + self.k * (s_home - e_home)
        self.ratings[away] = self.get_rating(away) + self.k * ((1 - s_home) - (1 - e_home))

    def expected_win_prob(self, home: str, away: str) -> Tuple[float, float]:
        """Probabilités de victoire selon les ratings ELO."""
        r_home = self.get_rating(home) + self.home_bonus
        r_away = self.get_rating(away)
        p_home = 1 / (1 + 10 ** ((r_away - r_home) / 400))
        return round(p_home, 4), round(1 - p_home, 4)

    @staticmethod
    def form_adjustment(form_list: List[int]) -> float:
        """Score de forme pondéré (récent = plus lourd)."""
        weights = [0.35, 0.25, 0.20, 0.12, 0.08]
        score = sum(r * w for r, w in zip(form_list[:5], weights))
        return round(score, 4)

    @staticmethod
    def _estimate_total_points(elo_home: float, elo_away: float,
                               home_ppg: float = 112.0,
                               away_ppg: float = 110.0) -> Tuple[float, float]:
        """
        Estime le total de points attendu pour un match NBA (R8).
        Utilise une approche sigmoïde sur la différence de ratings ELO.

        Points par équipe estimés à partir de :
        - Points par match de la saison (ppg) si disponibles dans le fixture
        - Sinon, la moyenne NBA (~110-115 pts par équipe)

        Returns:
            (total_expected, p_over_threshold)
            total_expected : somme des points attendus
            p_over_threshold : probabilité que le total dépasse le seuil
        """
        # Moyenne NBA saison 2024-25 ≈ 113 pts par équipe par match
        nba_avg_total = 224.5

        # Différence de rating ajustée (impact sur le tempo)
        elo_diff = abs(elo_home - elo_away)
        # Plus les équipes sont déséquilibrées, moins le match est disputé
        # → légèrement moins de points en moyenne
        tempo_factor = 1.0 - min(0.05, elo_diff / 4000)

        home_exp = home_ppg * tempo_factor
        away_exp = away_ppg * tempo_factor
        total_expected = home_exp + away_exp

        # Seuil Over/Under NBA typique (lignes bookmaker) ≈ moyenne ± 5
        threshold = nba_avg_total
        # P(Over) via sigmoïde sur l'écart attendu/seuil
        # diff > 0 → total attendu > seuil → over probable
        diff_normalized = (total_expected - threshold) / 10.0  # normalisation
        p_over = 1 / (1 + math.exp(-diff_normalized))

        return round(total_expected, 1), round(p_over, 4)

    def predict(self, fixture: dict) -> Dict[str, Any]:
        """Prédit le résultat d'un match de basketball, incluant Over/Under (R8)."""
        home, away = fixture["home"], fixture["away"]

        if "home_elo" in fixture:
            self.ratings[home] = fixture["home_elo"]
        if "away_elo" in fixture:
            self.ratings[away] = fixture["away_elo"]

        p_home, p_away = self.expected_win_prob(home, away)

        form_home = self.form_adjustment(fixture.get("home_form", []))
        form_away = self.form_adjustment(fixture.get("away_form", []))

        form_diff = (form_home - form_away) * 0.10
        p_home_adj = min(0.95, max(0.05, p_home + form_diff))

        # R8 : estimation Over/Under points
        elo_h = self.get_rating(home) + self.home_bonus
        elo_a = self.get_rating(away)
        home_ppg = fixture.get("home_ppg", 112.0)
        away_ppg = fixture.get("away_ppg", 110.0)
        total_exp, p_over = self._estimate_total_points(
            elo_h, elo_a, home_ppg, away_ppg
        )

        return {
            "sport":           "Basketball",
            "fixture":         fixture,
            "elo_home":        elo_h,
            "elo_away":        elo_a,
            "form_home":       form_home,
            "form_away":       form_away,
            "p_home_win":      round(p_home_adj, 4),
            "p_away_win":      round(1 - p_home_adj, 4),
            "total_expected":  total_exp,
            "p_over_total":    p_over,
            "p_under_total":   round(1 - p_over, 4),
        }


# ══════════════════════════════════════════════════════════════════
# CLASSE 4 : TennisModel — Modèle tennis amélioré
# ══════════════════════════════════════════════════════════════════

class TennisModel:
    """
    Modèle de prédiction tennis combinant :
    - Classement ATP/WTA → rating ELO approximatif
    - Performance sur la surface spécifique
    - Forme récente (derniers 5-10 matchs)
    - Head-to-head (confrontations directes)
    - Fatigue (nombre de matchs récents)
    """

    RANKING_TO_ELO = {
        1: 2200, 2: 2150, 3: 2100, 5: 2050, 10: 2000,
        20: 1950, 30: 1900, 50: 1850, 75: 1800, 100: 1750,
        150: 1700, 200: 1650, 300: 1600, 500: 1550,
    }

    def ranking_to_elo(self, ranking: int) -> float:
        if ranking <= 0:
            return 1500
        keys = sorted(self.RANKING_TO_ELO.keys())
        for i in range(len(keys) - 1):
            if keys[i] <= ranking <= keys[i + 1]:
                r1, r2 = keys[i], keys[i + 1]
                e1, e2 = self.RANKING_TO_ELO[r1], self.RANKING_TO_ELO[r2]
                fraction = (ranking - r1) / (r2 - r1)
                return e1 + fraction * (e2 - e1)
        return max(1400, 2200 - ranking * 1.5)

    @staticmethod
    def surface_adjustment(win_rate: float) -> float:
        """Ajustement basé sur le taux de victoire sur la surface."""
        return round((win_rate - 0.5) * TENNIS_PARAMS["surface_weight"], 4)

    @staticmethod
    def form_score(form_list: List[int]) -> float:
        """Score de forme pondéré (10 derniers matchs)."""
        weights = [0.20, 0.18, 0.15, 0.12, 0.10, 0.09, 0.07, 0.05, 0.03, 0.01]
        return round(sum(r * w for r, w in zip(form_list[:10], weights)), 4)

    @staticmethod
    def h2h_adjustment(home_wins: int, away_wins: int) -> float:
        """
        Ajustement basé sur le head-to-head.
        Retourne un bonus/malus pour le joueur 'home'.
        """
        total = home_wins + away_wins
        if total < 2:
            return 0.0  # Pas assez de données H2H
        h2h_rate = home_wins / total
        return round((h2h_rate - 0.5) * TENNIS_PARAMS["h2h_weight"], 4)

    @staticmethod
    def fatigue_factor(matches_last_30d: int) -> float:
        """
        Pénalité de fatigue si trop de matchs récents.
        > 10 matchs en 30 jours = fatigue significative.
        """
        if matches_last_30d <= 6:
            return 0.0
        elif matches_last_30d <= 10:
            return -0.01 * (matches_last_30d - 6)
        else:
            return -0.02 * (matches_last_30d - 6)

    def predict(self, fixture: dict) -> Dict[str, Any]:
        """Prédit le résultat d'un match de tennis."""
        home, away = fixture["home"], fixture["away"]
        surface = fixture.get("surface", "hard")

        elo_home = self.ranking_to_elo(fixture.get("home_ranking", 100))
        elo_away = self.ranking_to_elo(fixture.get("away_ranking", 100))

        # Probabilité ELO de base
        p_home_base = 1 / (1 + 10 ** ((elo_away - elo_home) / 400))

        # Ajustements
        adj_surface_h = self.surface_adjustment(fixture.get("home_surface_winrate", 0.5))
        adj_surface_a = self.surface_adjustment(fixture.get("away_surface_winrate", 0.5))
        form_home = self.form_score(fixture.get("home_form", []))
        form_away = self.form_score(fixture.get("away_form", []))

        # H2H
        h2h_adj = self.h2h_adjustment(
            fixture.get("h2h_home_wins", 0),
            fixture.get("h2h_away_wins", 0),
        )

        # Fatigue
        fatigue_h = self.fatigue_factor(fixture.get("home_matches_last_30d", 5))
        fatigue_a = self.fatigue_factor(fixture.get("away_matches_last_30d", 5))

        # Combinaison
        p_home_adj = (
            p_home_base
            + (adj_surface_h - adj_surface_a)
            + (form_home - form_away) * TENNIS_PARAMS["form_weight"]
            + h2h_adj
            + (fatigue_h - fatigue_a)
        )
        p_home_adj = min(0.95, max(0.05, p_home_adj))

        return {
            "sport":      "Tennis",
            "fixture":    fixture,
            "surface":    surface,
            "elo_home":   round(elo_home, 1),
            "elo_away":   round(elo_away, 1),
            "form_home":  form_home,
            "form_away":  form_away,
            "h2h_adj":    h2h_adj,
            "p_home_win": round(p_home_adj, 4),
            "p_away_win": round(1 - p_home_adj, 4),
        }


# ══════════════════════════════════════════════════════════════════
# CLASSE 5 : ValueBetSelector — Value betting corrigé
# ══════════════════════════════════════════════════════════════════

class ValueBetSelector:
    """
    Identifie les paris à valeur positive (value bets).
    v2.0 : utilise les VRAIES cotes bookmaker quand disponibles.
    En mode démo, les cotes sont simulées de façon INDÉPENDANTE
    (perspective bookmaker différente du modèle).
    """

    def __init__(self):
        self.min_value = VALUE_BETTING["min_value"]
        self.min_odd = VALUE_BETTING["min_odd"]
        self.max_odd = VALUE_BETTING["max_odd"]
        self._demo_odd_fn: Optional[Callable] = None

    @staticmethod
    def calculate_value(p_model: float, odd_book: float) -> float:
        """value = (p_model × cote) - 1. > 0 = favorable."""
        return round((p_model * odd_book) - 1, 4)

    @staticmethod
    def kelly_stake(p_model: float, odd_book: float) -> float:
        """
        Critère de Kelly : f* = (bp - q) / b
        b = odd - 1 (gain net), p = proba modèle, q = 1 - p
        Retourne le % du bankroll à miser (fractionné).

        Note : pas de minimum forcé — si Kelly recommande < 0.5%,
        le pari est marginal et la mise reflète ce faible avantage.
        """
        b = odd_book - 1
        q = 1 - p_model
        if b <= 0:
            return 0.0
        kelly_full = (b * p_model - q) / b
        if kelly_full <= 0:
            return 0.0
        kelly_frac = kelly_full * KELLY["fraction"]
        # Clamp uniquement le maximum (pas de minimum artificiel)
        stake = min(KELLY["max_stake_pct"], kelly_frac * 100)
        return round(stake, 2)

    def _confidence_score(self, p_model: float, value: float,
                          odd: float = 2.0,
                          matches_played: int = 20) -> float:
        """
        Score de confiance /10 basé sur le critère de Kelly fractionné,
        pondéré par le facteur d'incertitude lié au volume de données (R5).

        Justification Kelly : intègre naturellement la probabilité ET l'edge.
        Justification incertitude : moins de matchs = moins de données = moins
        de confiance dans les moyennes. Formule : sqrt(min(N,20)/20).
            5 matchs → ×0.50 | 10 matchs → ×0.71 | 20+ matchs → ×1.00

        Échelle finale : Kelly frac 0% → 0/10, Kelly frac ≥ 5% → 10/10
        """
        b = odd - 1
        if b <= 0:
            return 0.0
        q = 1 - p_model
        kelly_full = (b * p_model - q) / b
        if kelly_full <= 0:
            return 0.0
        kelly_frac = kelly_full * KELLY["fraction"]
        # Normaliser sur 0-10 : Kelly frac de 5% du bankroll = confiance max
        score = min(10.0, (kelly_frac * 100) / KELLY["max_stake_pct"] * 10)
        # R5 : facteur d'incertitude basé sur le nombre de matchs disputés
        uncertainty_factor = min(1.0, (min(matches_played, 20) / 20) ** 0.5)
        return round(score * uncertainty_factor, 1)

    def _get_odd(self, p_model: float, odds_data: Optional[dict],
                 market_key: str, outcome_name: str) -> Optional[float]:
        """
        Récupère la cote bookmaker réelle ou simule une cote indépendante.
        Retourne None si la cote est hors fourchette.
        """
        odd = None

        # 1. Essayer les vraies cotes API
        if odds_data and "markets" in odds_data:
            mkt = odds_data["markets"].get(market_key, {})
            odd = mkt.get(outcome_name)

        # 2. Fallback : simulation indépendante (pas circulaire)
        if odd is None and self._demo_odd_fn:
            odd = self._demo_odd_fn(p_model)

        # 3. Vérifier la fourchette
        if odd is not None and self.min_odd <= odd <= self.max_odd:
            return odd
        return None

    def extract_bets(self, prediction: dict, markets: List[Tuple[str, float, str, str]],
                     odds_data: Optional[dict] = None) -> List[dict]:
        """
        Méthode GÉNÉRIQUE d'extraction de paris.
        Évite la duplication entre football/basketball/tennis.

        markets : liste de (bet_name, p_model, market_key, outcome_name)
        """
        bets = []
        fix = prediction["fixture"]
        sport = prediction["sport"]

        # R5 : nombre de matchs minimum entre équipes domicile/extérieur
        # pour le facteur d'incertitude (utilise home_matches si disponible)
        matches_played = min(
            fix.get("home_matches", 20),
            fix.get("away_matches", 20),
        )

        for bet_name, p_model, market_key, outcome_name in markets:
            odd = self._get_odd(p_model, odds_data, market_key, outcome_name)
            if odd is None:
                continue

            value = self.calculate_value(p_model, odd)
            if value < self.min_value:
                continue

            stake = self.kelly_stake(p_model, odd)

            bets.append({
                "id":          fix["id"],
                "sport":       sport,
                "competition": fix["competition"],
                "match":       f"{fix['home']} vs {fix['away']}",
                "bet_type":    bet_name,
                "market":      market_key,
                "odd":         odd,
                "p_model":     round(p_model * 100, 1),
                "p_implied":   round((1 / odd) * 100, 1),
                "value":       round(value * 100, 2),
                "confidence":  self._confidence_score(p_model, value, odd,
                                                       matches_played=matches_played),
                "kelly_stake": stake,
            })

        return bets

    def extract_football_bets(self, prediction: dict,
                              odds_data: Optional[dict] = None) -> List[dict]:
        """Extrait les paris football."""
        fix = prediction["fixture"]
        home, away = fix["home"], fix["away"]

        markets = [
            (f"Victoire {home}",         prediction["p_home_win"],  "h2h",    home),
            ("Match nul",                 prediction["p_draw"],      "h2h",    "Draw"),
            (f"Victoire {away}",          prediction["p_away_win"],  "h2h",    away),
            ("Over 2.5 buts",             prediction["p_over_2_5"],  "totals", "Over"),
            ("Under 2.5 buts",            prediction["p_under_2_5"], "totals", "Under"),
            ("BTTS — Les deux marquent",  prediction["p_btts"],      "btts",   "Yes"),
            ("BTTS Non",                  prediction["p_btts_no"],   "btts",   "No"),
        ]
        return self.extract_bets(prediction, markets, odds_data)

    def extract_basketball_bets(self, prediction: dict,
                                odds_data: Optional[dict] = None) -> List[dict]:
        """Extrait les paris basketball, incluant le marché Over/Under (R8)."""
        fix = prediction["fixture"]
        markets = [
            (f"Victoire {fix['home']}", prediction["p_home_win"], "h2h", fix["home"]),
            (f"Victoire {fix['away']}", prediction["p_away_win"], "h2h", fix["away"]),
        ]
        # R8 : marchés Over/Under si disponibles dans la prédiction
        if "p_over_total" in prediction:
            markets += [
                ("Over (total points)", prediction["p_over_total"], "totals", "Over"),
                ("Under (total points)", prediction["p_under_total"], "totals", "Under"),
            ]
        return self.extract_bets(prediction, markets, odds_data)

    def extract_tennis_bets(self, prediction: dict,
                            odds_data: Optional[dict] = None) -> List[dict]:
        """Extrait les paris tennis."""
        fix = prediction["fixture"]
        markets = [
            (f"Victoire {fix['home']}", prediction["p_home_win"], "h2h", fix["home"]),
            (f"Victoire {fix['away']}", prediction["p_away_win"], "h2h", fix["away"]),
        ]
        return self.extract_bets(prediction, markets, odds_data)

    def select_best_bets(self, all_bets: List[dict]) -> List[dict]:
        """
        Trie par valeur décroissante et élimine les doublons
        (même match, marchés incompatibles).
        """
        sorted_bets = sorted(all_bets, key=lambda x: x["value"], reverse=True)
        selected = []
        used_ids: Dict[int, List[str]] = {}

        incompatible_groups = {"h2h", "totals", "btts", "winner", "match_winner"}

        for bet in sorted_bets:
            match_id = bet["id"]
            market = bet["market"]

            if match_id not in used_ids:
                used_ids[match_id] = []

            if market in used_ids[match_id]:
                continue  # Même marché du même match déjà pris

            selected.append(bet)
            used_ids[match_id].append(market)

        return selected


# ══════════════════════════════════════════════════════════════════
# CLASSE 6 : CouponBuilder — Construction du coupon final
# ══════════════════════════════════════════════════════════════════

class CouponBuilder:
    """
    Assemble les paris sélectionnés en un coupon cohérent.
    Ajuste la composition pour atteindre la cote cible (~5.0).
    """

    SPORT_EMOJI = {
        "Football":   "⚽",
        "Basketball": "🏀",
        "Tennis":     "🎾",
    }

    def __init__(self):
        self.target = VALUE_BETTING["target_selections"]
        self.min_total = VALUE_BETTING["min_total_odd"]
        self.max_total = VALUE_BETTING["max_total_odd"]
        self.target_odd = VALUE_BETTING["target_total_odd"]
        self.max_per_league = VALUE_BETTING.get("max_per_league", 3)

    @staticmethod
    def total_odd(bets: List[dict]) -> float:
        """Cote totale d'un coupon combiné."""
        return round(reduce(lambda a, b: a * b["odd"], bets, 1.0), 2)

    @staticmethod
    def _is_diversified(combo: List[dict], max_per_league: int) -> bool:
        """
        Vérifie qu'une combinaison respecte la limite de sélections par ligue (R6).
        Évite qu'un coupon soit surconcentré sur une seule compétition.

        Args:
            combo: Liste de paris candidats.
            max_per_league: Nombre maximum de sélections par compétition.

        Returns:
            True si la diversification est respectée.
        """
        if not combo:
            return True
        league_counts = Counter(bet.get("competition", "Unknown") for bet in combo)
        return max(league_counts.values()) <= max_per_league

    def build(self, candidates: List[dict]) -> List[dict]:
        """
        Construit le coupon optimal via recherche combinatoire bornée.
        Limite à C(15, target) pour éviter l'explosion.
        """
        if not candidates:
            logger.warning("Aucun pari valide trouvé — coupon vide")
            return []

        pool = candidates[:min(len(candidates), 15)]
        target_size = min(self.target, len(pool))

        best_coupon = []
        best_distance = float("inf")

        for combo in combinations(pool, target_size):
            combo_list = list(combo)
            # R6 : ignorer les combinaisons qui violent la diversification
            if not self._is_diversified(combo_list, self.max_per_league):
                continue
            total = self.total_odd(combo_list)
            dist = abs(total - self.target_odd)
            if self.min_total <= total <= self.max_total:
                dist -= 0.5  # Bonus si dans la fourchette
            if dist < best_distance:
                best_distance = dist
                best_coupon = combo_list

        if not best_coupon:
            best_coupon = candidates[:target_size]

        # Ajustement fin
        coupon = list(best_coupon)
        total = self.total_odd(coupon)

        if total < self.min_total:
            remaining = [b for b in candidates if b not in coupon]
            if remaining:
                best_add = min(
                    remaining,
                    key=lambda b: abs(self.total_odd(coupon + [b]) - self.target_odd),
                )
                coupon.append(best_add)

        elif total > self.max_total and len(coupon) > 2:
            riskiest = min(coupon, key=lambda x: x["p_model"])
            alternatives = [
                b for b in candidates
                if b not in coupon and b["odd"] < riskiest["odd"]
            ]
            if alternatives:
                best_swap = min(
                    alternatives,
                    key=lambda b: abs(
                        self.total_odd([x for x in coupon if x is not riskiest] + [b])
                        - self.target_odd
                    ),
                )
                coupon.remove(riskiest)
                coupon.append(best_swap)

        return coupon

    def format_coupon(self, coupon: List[dict], date: str,
                      is_demo: bool = False) -> str:
        """Formate le coupon pour affichage console."""
        if not coupon:
            return "⚠️  Aucune sélection valide pour aujourd'hui."

        total = self.total_odd(coupon)
        avg_edge = round(sum(b["value"] for b in coupon) / len(coupon), 2)
        avg_conf = round(sum(b["confidence"] for b in coupon) / len(coupon), 1)

        lines = []
        lines.append("╔══════════════════════════════════════════════════════════════╗")
        lines.append(f"║          🎯  COUPON DU JOUR  —  {date}                 ║")
        lines.append("╚══════════════════════════════════════════════════════════════╝")
        lines.append("")

        if is_demo:
            lines.append("⚠️  MODE DÉMO — Cotes simulées (non réelles)")
            lines.append("")

        lines.append("📊 ANALYSE : Modèle Poisson + ELO + Value Betting")
        lines.append("")

        for i, bet in enumerate(coupon, start=1):
            emoji = self.SPORT_EMOJI.get(bet["sport"], "🏅")
            lines.append("─" * 64)
            lines.append(f"SÉLECTION {i} │ {emoji} {bet['sport']} │ {bet['competition']}")
            lines.append(f"Match     : {bet['match']}")
            lines.append(f"Pari      : {bet['bet_type']}")
            lines.append(f"Cote      : {bet['odd']:.2f}")
            lines.append(
                f"Prob. modèle : {bet['p_model']}%  │  "
                f"Prob. implicite : {bet['p_implied']}%  │  "
                f"Edge : +{bet['value']}%"
            )
            lines.append(
                f"Confiance : {'★' * int(bet['confidence'] // 2)}"
                f"{'☆' * (5 - int(bet['confidence'] // 2))}  "
                f"({bet['confidence']}/10)"
            )
            lines.append(
                f"💰 Mise Kelly ({KELLY['fraction']*100:.0f}%) : "
                f"{bet['kelly_stake']}% du bankroll"
            )

        lines.append("─" * 64)
        lines.append("")

        target_ok = self.min_total <= total <= self.max_total
        lines.append(
            f"🎰  COTE TOTALE          : {total:.2f}  "
            f"({'✅ Dans la cible' if target_ok else '⚠️ Hors cible'})"
        )
        lines.append(f"📈  EDGE MOYEN            : +{avg_edge}%")
        lines.append(f"🔒  CONFIANCE MOYENNE    : {avg_conf}/10")
        lines.append(f"📋  NOMBRE DE SÉLECTIONS : {len(coupon)}")
        lines.append("")
        lines.append("─" * 64)
        lines.append("⚠️   Ce coupon est généré par algorithme statistique.")
        lines.append("    Un combiné à cote ~5 passe environ 1 fois sur 5.")
        lines.append("    Comptez 50-100 coupons pour évaluer la performance réelle.")
        lines.append("    Les séries perdantes sont normales. Jouez responsablement.")
        lines.append("─" * 64)

        return "\n".join(lines)

    def to_dataframe(self, coupon: List[dict]) -> pd.DataFrame:
        """Exporte le coupon au format DataFrame pandas."""
        if not coupon:
            return pd.DataFrame()
        cols = [
            "sport", "competition", "match", "bet_type", "odd",
            "p_model", "p_implied", "value", "confidence", "kelly_stake",
        ]
        return pd.DataFrame(coupon)[[c for c in cols if c in coupon[0]]]


# ══════════════════════════════════════════════════════════════════
# CLASSE 7 : BacktestTracker — Historique et suivi des résultats
# ══════════════════════════════════════════════════════════════════

class BacktestTracker:
    """
    Enregistre chaque coupon généré dans un fichier JSON
    et permet de tracker les résultats pour mesurer la performance.
    """

    def __init__(self, history_file: str = None):
        self.history_file = Path(history_file or BACKTEST["history_file"])
        self._history: Optional[List[dict]] = None

    def _load(self) -> List[dict]:
        """Charge l'historique depuis le fichier JSON."""
        if self._history is not None:
            return self._history
        if self.history_file.exists():
            try:
                self._history = json.loads(self.history_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Historique corrompu — réinitialisé")
                self._history = []
        else:
            self._history = []
        return self._history

    def _save(self) -> None:
        """Sauvegarde l'historique dans le fichier JSON."""
        if self._history is not None:
            self.history_file.write_text(
                json.dumps(self._history, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def record_coupon(self, coupon: List[dict], date: str,
                      is_demo: bool = False) -> None:
        """Enregistre un coupon généré."""
        history = self._load()
        entry = {
            "date":       date,
            "generated":  datetime.now().isoformat(),
            "is_demo":    is_demo,
            "total_odd":  CouponBuilder.total_odd(coupon),
            "selections": [
                {
                    "match":       b["match"],
                    "bet_type":    b["bet_type"],
                    "odd":         b["odd"],
                    "p_model":     b["p_model"],
                    "value":       b["value"],
                    "kelly_stake": b.get("kelly_stake", 2.0),
                    "result":      None,  # À remplir manuellement ou via API
                }
                for b in coupon
            ],
            "result":     None,
        }
        history.append(entry)
        self._save()
        logger.info(f"📝 Coupon enregistré dans {self.history_file}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Calcule les statistiques de performance.
        Deux modes de calcul du ROI :
        - ROI combiné : 1 mise plate par coupon, gain = mise × cote_totale si win
        - ROI sélections : mises Kelly individuelles par sélection (plus précis)
        """
        history = self._load()
        resolved = [e for e in history if e.get("result") is not None]

        if not resolved:
            return {
                "total_coupons":   len(history),
                "resolved":        0,
                "message":         "Aucun résultat enregistré pour le moment.",
            }

        wins = sum(1 for e in resolved if e["result"] == "win")
        losses = len(resolved) - wins

        # ── ROI combiné (mise plate par coupon) ────────────────────
        flat_stake = 2.0  # % bankroll par coupon
        total_staked_flat = 0.0
        total_returned_flat = 0.0
        for entry in resolved:
            total_staked_flat += flat_stake
            if entry["result"] == "win":
                total_returned_flat += flat_stake * entry["total_odd"]

        roi_flat = (
            ((total_returned_flat - total_staked_flat) / total_staked_flat * 100)
            if total_staked_flat else 0
        )

        # ── ROI sélections individuelles (mises Kelly) ─────────────
        total_staked_kelly = 0.0
        total_returned_kelly = 0.0
        total_selections = 0
        selections_won = 0
        for entry in resolved:
            for sel in entry.get("selections", []):
                kelly = sel.get("kelly_stake", flat_stake)
                total_staked_kelly += kelly
                total_selections += 1
                if sel.get("result") == "win":
                    total_returned_kelly += kelly * sel["odd"]
                    selections_won += 1

        roi_kelly = (
            ((total_returned_kelly - total_staked_kelly) / total_staked_kelly * 100)
            if total_staked_kelly else 0
        )

        return {
            "total_coupons":       len(history),
            "resolved":            len(resolved),
            "wins":                wins,
            "losses":              losses,
            "win_rate":            round(wins / len(resolved) * 100, 1),
            "roi_flat":            round(roi_flat, 2),
            "roi_kelly":           round(roi_kelly, 2),
            # Legacy : garder "roi" comme alias de roi_flat pour compatibilité
            "roi":                 round(roi_flat, 2),
            "total_staked_pct":    round(total_staked_flat, 2),
            "total_returned_pct":  round(total_returned_flat, 2),
            "total_selections":    total_selections,
            "selections_won":      selections_won,
        }

    @staticmethod
    def _evaluate_bet(bet: dict, results_map: Dict[str, dict]) -> Optional[str]:
        """
        Détermine le résultat d'un pari individuel à partir des scores réels (R4).

        Args:
            bet: Sélection du coupon (match, bet_type, market, etc.)
            results_map: Dict {match_key_normalisé → résultat_match}

        Returns:
            "win", "loss", "void" ou None si résultat inconnu.
        """
        match_key = bet.get("match", "")
        market = bet.get("market", "")
        bet_type = bet.get("bet_type", "")

        # Chercher le résultat avec matching fuzzy
        result = None
        for key, res in results_map.items():
            if match_key == key or (
                normalize_team_name(res["home"]) in normalize_team_name(match_key)
            ):
                result = res
                break

        if not result:
            return None

        home_score = result.get("home_score", 0)
        away_score = result.get("away_score", 0)
        total_goals = result.get("total_goals", 0)

        if market == "h2h":
            # Identifier si c'est la victoire domicile, nul ou extérieur
            home_name = normalize_team_name(result["home"])
            away_name = normalize_team_name(result["away"])
            bet_lower = bet_type.lower()

            if "nul" in bet_lower or "draw" in bet_lower:
                return "win" if result.get("is_draw") else "loss"
            elif home_name in normalize_team_name(bet_lower):
                return "win" if result.get("home_won") else "loss"
            elif away_name in normalize_team_name(bet_lower):
                return "win" if (not result.get("home_won") and not result.get("is_draw")) else "loss"

        elif market == "totals":
            # Extraire le seuil du bet_type (ex: "Over 2.5 buts")
            thresh_match = re.search(r"(\d+\.?\d*)", bet_type)
            threshold = float(thresh_match.group(1)) if thresh_match else 2.5

            if "over" in bet_type.lower():
                return "win" if total_goals > threshold else "loss"
            elif "under" in bet_type.lower():
                return "win" if total_goals < threshold else "loss"

        elif market == "btts":
            btts = home_score > 0 and away_score > 0
            if "non" in bet_type.lower() or "no" in bet_type.lower():
                return "win" if not btts else "loss"
            return "win" if btts else "loss"

        return None

    def resolve_results(self, date: str, match_results: List[dict]) -> int:
        """
        Alimente le BacktestTracker avec les résultats réels des matchs (R4).
        Mis à jour automatiquement par le job quotidien à 01h00.

        Args:
            date: Date des matchs (YYYY-MM-DD)
            match_results: Liste de résultats retournée par DataFetcher.fetch_match_results()

        Returns:
            Nombre de sélections mises à jour.
        """
        history = self._load()
        # Index des résultats par clé normalisée
        results_map: Dict[str, dict] = {}
        for res in match_results:
            results_map[res["match_key"]] = res
            # Ajouter aussi la clé normalisée
            norm_key = (
                f"{normalize_team_name(res['home'])} vs "
                f"{normalize_team_name(res['away'])}"
            )
            results_map[norm_key] = res

        updated_count = 0
        for entry in history:
            if entry.get("date") != date:
                continue
            if entry.get("result") is not None:
                continue  # Déjà résolu

            selections = entry.get("selections", [])
            all_resolved = True
            coupon_won = True

            for sel in selections:
                if sel.get("result") is not None:
                    if sel["result"] != "win":
                        coupon_won = False
                    continue

                result = self._evaluate_bet(sel, results_map)
                if result is not None:
                    sel["result"] = result
                    updated_count += 1
                    if result != "win":
                        coupon_won = False
                else:
                    all_resolved = False
                    coupon_won = False

            if all_resolved:
                entry["result"] = "win" if coupon_won else "loss"
                logger.info(
                    f"✅ Coupon {date} résolu : "
                    f"{'WIN' if coupon_won else 'LOSS'}"
                )

        if updated_count:
            self._save()
            logger.info(
                f"BacktestTracker : {updated_count} sélections mises à jour pour {date}"
            )
        else:
            logger.debug(f"BacktestTracker : aucune mise à jour pour {date}")

        return updated_count


# ══════════════════════════════════════════════════════════════════
# UTILITAIRE : Fixtures NBA du jour via BallDontLie (R2)
# ══════════════════════════════════════════════════════════════════

def _fetch_nba_fixtures_today(fetcher: DataFetcher) -> List[dict]:
    """
    Récupère les matchs NBA du jour via BallDontLie (R2).
    Utilisé uniquement en mode réel quand les ratings ELO sont disponibles.

    Args:
        fetcher: Instance DataFetcher avec session et cache.

    Returns:
        Liste de fixtures NBA enrichis pour EloModel.predict().
    """
    today = fetcher.today
    url = f"{ENDPOINTS.get('balldontlie_base', 'https://api.balldontlie.io/v1')}/games"
    params = {
        "dates[]": today,
        "per_page": 30,
    }
    headers: dict = {}
    bdl_key = API_KEYS.get("balldontlie", "")
    if bdl_key:
        headers["Authorization"] = bdl_key

    data = fetcher._get(url, headers=headers, params=params, api_name="balldontlie")
    if not data:
        logger.debug("BallDontLie : aucune donnée récupérée pour aujourd'hui")
        return []

    fixtures = []
    for game in data.get("data", []):
        # Filtrer les matchs non encore joués (status != "Final")
        if game.get("status") == "Final":
            continue
        home = game.get("home_team", {}).get("full_name", "")
        away = game.get("visitor_team", {}).get("full_name", "")
        if not home or not away:
            continue
        fixtures.append({
            "id":          game.get("id", 0),
            "sport":       "Basketball",
            "competition": "NBA",
            "home":        home,
            "away":        away,
            "date":        today,
            # ppg non disponible via BallDontLie basic — utiliser moyennes NBA
            "home_ppg":    112.0,
            "away_ppg":    110.0,
            "home_matches": 50,  # approximation milieu de saison
            "away_matches": 50,
        })

    logger.info(f"  ↳ BallDontLie : {len(fixtures)} matchs NBA trouvés pour {today}")
    return fixtures


# ══════════════════════════════════════════════════════════════════
# UTILITAIRE : Lookup cotes avec matching fuzzy (R1)
# ══════════════════════════════════════════════════════════════════

def _lookup_odds(home: str, away: str,
                 odds_index: Dict[str, dict]) -> Optional[dict]:
    """
    Recherche les cotes d'un match dans l'index avec matching progressif.

    Stratégies dans l'ordre :
    1. Clé exacte brute (rétrocompatibilité)
    2. Clé normalisée (normalize_team_name)
    3. Fallback substring : home normalisé contenu dans une clé de l'index

    Args:
        home: Nom de l'équipe domicile (tel que reçu du fixture)
        away: Nom de l'équipe extérieure
        odds_index: Dict {clé_match → données_cotes}

    Returns:
        Données cotes si trouvées, None sinon.
    """
    # 1. Clé brute exacte
    raw_key = f"{home} vs {away}"
    if raw_key in odds_index:
        return odds_index[raw_key]

    # 2. Clé normalisée
    h_norm = normalize_team_name(home)
    a_norm = normalize_team_name(away)
    norm_key = f"{h_norm} vs {a_norm}"
    if norm_key in odds_index:
        return odds_index[norm_key]

    # 3. Fallback substring : chercher une clé dont les deux parties contiennent
    #    le nom normalisé (ex: "arsenal fc" contenu dans "arsenal london")
    for key, entry in odds_index.items():
        if " vs " not in key:
            continue
        parts = key.split(" vs ", 1)
        if h_norm in parts[0] and a_norm in parts[1]:
            logger.debug(f"R1 fallback substring : {raw_key!r} → {key!r}")
            return entry

    logger.debug(f"R1 aucune cote trouvée pour : {raw_key!r}")
    return None


# ══════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def run_pipeline() -> Tuple[List[dict], str]:
    """
    Pipeline complet de génération du coupon.
    Retourne (coupon, texte_formaté).
    """
    logger.info("═" * 60)
    logger.info("  DÉMARRAGE DU GÉNÉRATEUR DE COUPON SPORTIF v2.0")
    logger.info("═" * 60)

    # Vérifier le cache du coupon
    cached_result = _cache.get("coupon_result")
    if cached_result is not None:
        logger.info("📦 Coupon en cache — utilisation du résultat précédent")
        return cached_result

    # ── 1. Récupération des données ──────────────────────────────
    logger.info("📡 Étape 1/5 : Récupération des données…")
    fetcher = DataFetcher()
    is_demo = DEMO_MODE
    odds_index: Dict[str, dict] = {}  # Index cotes par "home vs away"

    if DEMO_MODE:
        logger.info("  ↳ Mode démo actif — données simulées")
        data = fetcher.get_demo_data()
    else:
        logger.info("  ↳ Appel aux APIs en temps réel…")
        data = {"football": [], "basketball": [], "tennis": [], "date": fetcher.today}

        # Récupérer les cotes RÉELLES d'abord
        # R1 : indexer les cotes avec clés normalisées pour le matching fuzzy
        all_odds = fetcher.fetch_all_odds()
        for sport_key, odds_list in all_odds.items():
            for odds_entry in odds_list:
                h_norm = normalize_team_name(odds_entry["home"])
                a_norm = normalize_team_name(odds_entry["away"])
                # Clé normalisée (matching principal)
                norm_key = f"{h_norm} vs {a_norm}"
                odds_index[norm_key] = odds_entry
                # Clé brute (fallback exacte legacy)
                raw_key = f"{odds_entry['home']} vs {odds_entry['away']}"
                if raw_key not in odds_index:
                    odds_index[raw_key] = odds_entry

        logger.info(f"  ↳ {len(odds_index)} entrées de cotes indexées")

        # Récupérer les fixtures et classements football
        team_stats: Dict[str, dict] = {}
        league_avg_goals_map: Dict[str, float] = {}  # Moyenne buts par ligue
        real_fixtures = []

        for code in FOOTBALL_COMPETITIONS:
            fixtures = fetcher.fetch_football_fixtures(code)
            standings = fetcher.fetch_football_standings(code)

            # Calculer la moyenne de buts dynamique pour cette ligue
            total_goals = sum(e["goals_for"] for e in standings if e["played"] > 0)
            total_matches = sum(e["played"] for e in standings if e["played"] > 0) / 2
            if total_matches > 0:
                league_avg = total_goals / total_matches
                league_avg_goals_map[code] = round(league_avg, 2)
                logger.info(f"  ↳ {FOOTBALL_COMPETITIONS.get(code, code)} : {league_avg:.2f} buts/match")

            for entry in standings:
                if entry["played"] >= POISSON_PARAMS["min_matches"]:
                    team_stats[entry["team"]] = {
                        "goals_avg":    entry["goals_for"] / entry["played"],
                        "conceded_avg": entry["goals_against"] / entry["played"],
                        "matches":      entry["played"],
                        "league_code":  code,
                    }
            real_fixtures.extend(fixtures)

        # Enrichir les fixtures avec la moyenne de buts de leur ligue
        for fix in real_fixtures:
            home_s = team_stats.get(fix["home"])
            away_s = team_stats.get(fix["away"])
            if home_s and away_s:
                fix["home_goals_avg"] = home_s["goals_avg"]
                fix["away_goals_avg"] = away_s["goals_avg"]
                fix["home_conceded_avg"] = home_s["conceded_avg"]
                fix["away_conceded_avg"] = away_s["conceded_avg"]
                fix["home_matches"] = home_s["matches"]
                fix["away_matches"] = away_s["matches"]
                # Ajouter la moyenne de buts et le code ligue pour le modèle Poisson
                league_code = home_s.get("league_code", "")
                fix["league_avg_goals"] = league_avg_goals_map.get(league_code)
                fix["league_code"] = league_code  # R3 : nécessaire pour le rho par ligue
                data["football"].append(fix)

        if not data["football"]:
            logger.warning("  ↳ Aucun match réel enrichi — fallback démo")
            data = fetcher.get_demo_data()
            is_demo = True

    # ── 2. Modélisation football ─────────────────────────────────
    logger.info("📐 Étape 2/5 : Modélisation Poisson + correction dépendance…")
    poisson_model = PoissonModel()
    football_predictions = []

    for fixture in data.get("football", []):
        try:
            pred = poisson_model.predict(fixture)
            football_predictions.append(pred)
            logger.info(
                f"  ↳ {fixture['home']} vs {fixture['away']} | "
                f"xG : {pred['lambda_home']:.2f}-{pred['lambda_away']:.2f} | "
                f"1X2 : {pred['p_home_win']*100:.0f}%/"
                f"{pred['p_draw']*100:.0f}%/"
                f"{pred['p_away_win']*100:.0f}%"
            )
        except Exception as e:
            logger.warning(f"  ↳ Erreur prédiction {fixture.get('home', '?')} : {e}")

    # ── 3. Modélisation basketball + tennis ──────────────────────
    logger.info("📐 Étape 3/5 : Modélisation ELO + Tennis…")
    # R2 : EloModel charge automatiquement nba_elo_ratings.json si disponible
    elo_model = EloModel()
    tennis_model = TennisModel()

    bball_predictions = []
    tennis_predictions = []

    # Basketball : activé en mode démo OU en mode réel si ratings pré-entraînés disponibles
    # R2 : elo_model._ratings_loaded indique si les ratings ont été chargés depuis le fichier
    basketball_enabled = is_demo or elo_model._ratings_loaded

    if basketball_enabled:
        basketball_source = "démo" if is_demo else "ratings pré-entraînés (R2)"
        logger.info(f"  ↳ Basketball activé ({basketball_source})")
        bball_fixtures = data.get("basketball", [])

        # En mode réel avec ratings chargés, récupérer les fixtures NBA du jour
        if not is_demo and elo_model._ratings_loaded and not bball_fixtures:
            bball_fixtures = _fetch_nba_fixtures_today(fetcher)

        for fixture in bball_fixtures:
            try:
                pred = elo_model.predict(fixture)
                bball_predictions.append(pred)
                logger.info(
                    f"  ↳ [NBA] {fixture['home']} vs {fixture['away']} | "
                    f"P(home) : {pred['p_home_win']*100:.0f}% | "
                    f"Total exp : {pred.get('total_expected', '?')} pts"
                )
            except Exception as e:
                logger.warning(f"  ↳ Erreur basket : {e}")
    else:
        logger.info(
            "  ↳ Basketball désactivé en mode réel "
            "(exécutez nba_elo_bootstrap.py pour activer)"
        )

    # Tennis : uniquement en mode démo (pas de flux temps réel disponible)
    if is_demo:
        for fixture in data.get("tennis", []):
            try:
                pred = tennis_model.predict(fixture)
                tennis_predictions.append(pred)
                logger.info(
                    f"  ↳ [Tennis] {fixture['home']} vs {fixture['away']} | "
                    f"P(home) : {pred['p_home_win']*100:.0f}%"
                )
            except Exception as e:
                logger.warning(f"  ↳ Erreur tennis : {e}")
    else:
        logger.info("  ↳ Tennis désactivé en mode réel (pas de données temps réel)")

    # ── 4. Extraction des value bets ─────────────────────────────
    logger.info("💎 Étape 4/5 : Identification des value bets…")
    selector = ValueBetSelector()

    if is_demo:
        selector._demo_odd_fn = data.get("demo_odd_fn")

    all_bets = []
    matched_count = 0

    for pred in football_predictions:
        fix = pred["fixture"]
        odds_data = _lookup_odds(fix["home"], fix["away"], odds_index)
        if odds_data:
            matched_count += 1
        bets = selector.extract_football_bets(pred, odds_data)
        all_bets.extend(bets)

    for pred in bball_predictions:
        fix = pred["fixture"]
        odds_data = _lookup_odds(fix["home"], fix["away"], odds_index)
        if odds_data:
            matched_count += 1
        bets = selector.extract_basketball_bets(pred, odds_data)
        all_bets.extend(bets)

    for pred in tennis_predictions:
        fix = pred["fixture"]
        odds_data = _lookup_odds(fix["home"], fix["away"], odds_index)
        if odds_data:
            matched_count += 1
        bets = selector.extract_tennis_bets(pred, odds_data)
        all_bets.extend(bets)

    total_preds = len(football_predictions) + len(bball_predictions) + len(tennis_predictions)
    logger.info(f"  ↳ Cotes matchées : {matched_count}/{total_preds} matchs")

    best_bets = selector.select_best_bets(all_bets)
    logger.info(
        f"  ↳ {len(all_bets)} paris candidats → {len(best_bets)} retenus"
    )

    # ── 5. Construction du coupon ────────────────────────────────
    logger.info("🏗️  Étape 5/5 : Construction du coupon optimal…")
    builder = CouponBuilder()
    coupon = builder.build(best_bets)

    logger.info(
        f"  ↳ Coupon final : {len(coupon)} sélections │ "
        f"Cote totale : {builder.total_odd(coupon):.2f}"
    )

    coupon_text = builder.format_coupon(coupon, data.get("date", ""), is_demo=is_demo)

    # Export DataFrame
    df = builder.to_dataframe(coupon)
    if not df.empty:
        logger.info("\n📊 Récapitulatif tabulaire :")
        logger.info("\n" + df.to_string(index=False))

    # Backtesting : enregistrer le coupon
    if BACKTEST.get("auto_track") and coupon:
        try:
            tracker = BacktestTracker()
            tracker.record_coupon(coupon, data.get("date", ""), is_demo=is_demo)
        except Exception as e:
            logger.warning(f"Erreur enregistrement backtest : {e}")

    # Mettre en cache
    result = (coupon, coupon_text)
    _cache.set("coupon_result", result, CACHE["coupon_ttl"])

    logger.info("═" * 60)
    logger.info("  GÉNÉRATION TERMINÉE")
    logger.info("═" * 60)

    return result


if __name__ == "__main__":
    # Configuration du logging pour l'exécution standalone
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s │ %(message)s",
    )
    try:
        coupon, coupon_text = run_pipeline()
        print("\n")
        print(coupon_text)
    except KeyboardInterrupt:
        print("\n⚠️  Interruption par l'utilisateur.")
    except Exception as e:
        logger.error(f"Erreur critique : {e}", exc_info=True)