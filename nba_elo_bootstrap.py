#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nba_elo_bootstrap.py — Bootstrapping des ratings ELO NBA

Ce script :
  1. Télécharge les résultats NBA de la/des saison(s) configurée(s) via BallDontLie API
  2. Itère chronologiquement sur les matchs et met à jour les ratings ELO
  3. Sauvegarde les ratings finaux dans nba_elo_ratings.json

Usage :
    python nba_elo_bootstrap.py

Prérequis :
    pip install requests
    Variables d'environnement : BALLDONTLIE_API_KEY (optionnel si tier public)

Le fichier généré (nba_elo_ratings.json) est lu automatiquement par
EloModel au démarrage du pipeline (si ELO_RATINGS_FILE est défini).
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ── Configuration ──────────────────────────────────────────────────
try:
    from config import ENDPOINTS, ELO_PARAMS, NETWORK
except ImportError:
    ENDPOINTS = {"balldontlie_base": "https://api.balldontlie.io/v1"}
    ELO_PARAMS = {
        "initial_rating": 1500,
        "k_factor": 20,
        "home_bonus": 50,
        "ratings_file": "nba_elo_ratings.json",
        "bootstrap_seasons": [2025, 2026],
    }
    NETWORK = {"timeout": 10, "max_retries": 3, "retry_delay": 1.0}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("NBA-ELO-Bootstrap")

# ── Constantes ─────────────────────────────────────────────────────
BALLDONTLIE_BASE = ENDPOINTS.get("balldontlie_base", "https://api.balldontlie.io/v1")
OUTPUT_FILE = Path(ELO_PARAMS.get("ratings_file", "nba_elo_ratings.json"))
SEASONS = ELO_PARAMS.get("bootstrap_seasons", [2025])
K_FACTOR = ELO_PARAMS.get("k_factor", 20)
INITIAL_RATING = ELO_PARAMS.get("initial_rating", 1500)
HOME_BONUS = ELO_PARAMS.get("home_bonus", 50)

# Clé API BallDontLie (optionnelle — tier public disponible sans clé)
_BDONTLIE_KEY = os.getenv("BALLDONTLIE_API_KEY", "")


def _get_headers() -> dict:
    """Headers pour BallDontLie (clé optionnelle en tier public)."""
    if _BDONTLIE_KEY:
        return {"Authorization": _BDONTLIE_KEY}
    return {}


def fetch_games_page(season: int, cursor: Optional[str] = None) -> Optional[dict]:
    """
    Récupère une page de résultats NBA pour une saison donnée.

    Args:
        season: Année de début de saison (ex: 2025 pour 2025-26)
        cursor: Curseur de pagination BallDontLie v2

    Returns:
        Réponse JSON de l'API ou None en cas d'erreur.
    """
    url = f"{BALLDONTLIE_BASE}/games"
    params: Dict[str, Any] = {
        "seasons[]": season,
        "per_page": 100,
        "postseason": "false",  # saison régulière uniquement
    }
    if cursor:
        params["cursor"] = cursor

    for attempt in range(NETWORK.get("max_retries", 3)):
        try:
            resp = requests.get(
                url,
                headers=_get_headers(),
                params=params,
                timeout=NETWORK.get("timeout", 10),
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                logger.warning("Quota API BallDontLie dépassé — pause 60s")
                time.sleep(60)
            elif resp.status_code == 401:
                logger.error(
                    "Clé BallDontLie invalide ou requise. "
                    "Définissez BALLDONTLIE_API_KEY dans les variables d'environnement."
                )
                return None
            else:
                logger.warning(
                    f"HTTP {resp.status_code} BallDontLie "
                    f"(tentative {attempt + 1})"
                )
        except requests.Timeout:
            logger.warning(f"Timeout BallDontLie (tentative {attempt + 1})")
        except requests.ConnectionError:
            logger.error("Connexion impossible à BallDontLie")
            return None
        except Exception as e:
            logger.error(f"Erreur inattendue BallDontLie : {e}")
            return None

        delay = NETWORK.get("retry_delay", 1.0) * (2 ** attempt)
        time.sleep(delay)

    return None


def fetch_all_games(season: int) -> List[dict]:
    """
    Récupère TOUS les matchs terminés d'une saison NBA via pagination.

    Args:
        season: Année de début de saison (ex: 2025)

    Returns:
        Liste de matchs triés chronologiquement.
    """
    games = []
    cursor = None
    page = 1

    logger.info(f"  Téléchargement saison {season}…")

    while True:
        data = fetch_games_page(season, cursor)
        if not data:
            logger.warning(f"  Impossible de récupérer la page {page} — arrêt")
            break

        page_games = data.get("data", [])
        # Filtrer uniquement les matchs terminés
        finished = [
            g for g in page_games
            if g.get("status") == "Final"
            and g.get("home_team_score") is not None
            and g.get("visitor_team_score") is not None
        ]
        games.extend(finished)

        # Pagination via cursor BallDontLie v2
        meta = data.get("meta", {})
        next_cursor = meta.get("next_cursor")

        logger.debug(f"  Page {page} : {len(finished)}/{len(page_games)} matchs terminés")

        if not next_cursor:
            break

        cursor = next_cursor
        page += 1
        # Respecter la rate limit
        time.sleep(0.5)

    logger.info(f"  ↳ {len(games)} matchs terminés récupérés pour saison {season}")
    return games


def compute_elo_ratings(all_games: List[dict]) -> Dict[str, float]:
    """
    Calcule les ratings ELO à partir de l'historique chronologique des matchs.

    Args:
        all_games: Liste de matchs (dict BallDontLie) triés chronologiquement.

    Returns:
        Dict {nom_équipe → rating_elo_final}
    """
    ratings: Dict[str, float] = {}

    def get_rating(team: str) -> float:
        return ratings.get(team, INITIAL_RATING)

    def update(home: str, away: str, home_score: int, away_score: int) -> None:
        """Met à jour les ratings ELO après un match."""
        r_home = get_rating(home) + HOME_BONUS
        r_away = get_rating(away)
        e_home = 1 / (1 + 10 ** ((r_away - r_home) / 400))
        home_won = home_score > away_score
        s_home = 1.0 if home_won else 0.0
        ratings[home] = get_rating(home) + K_FACTOR * (s_home - e_home)
        ratings[away] = get_rating(away) + K_FACTOR * ((1 - s_home) - (1 - e_home))

    # Trier chronologiquement
    sorted_games = sorted(all_games, key=lambda g: g.get("date", ""))

    for game in sorted_games:
        home_team = game.get("home_team", {}).get("full_name", "")
        away_team = game.get("visitor_team", {}).get("full_name", "")
        home_score = game.get("home_team_score", 0)
        away_score = game.get("visitor_team_score", 0)

        # Vérifier la présence des noms d'équipes et que les scores ne sont pas None
        if home_team and away_team and home_score is not None and away_score is not None:
            update(home_team, away_team, home_score, away_score)

    return ratings


def save_ratings(ratings: Dict[str, float], output_file: Path) -> None:
    """
    Sauvegarde les ratings ELO dans un fichier JSON.

    Args:
        ratings: Dict {nom_équipe → rating}
        output_file: Chemin du fichier de sortie
    """
    output = {
        "generated_at":  datetime.now().isoformat(),
        "seasons":       SEASONS,
        "total_teams":   len(ratings),
        "ratings":       {k: round(v, 2) for k, v in sorted(ratings.items())},
    }
    output_file.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"✅ Ratings ELO sauvegardés dans {output_file} ({len(ratings)} équipes)")


def main() -> None:
    """Point d'entrée principal du bootstrap ELO NBA."""
    logger.info("═" * 60)
    logger.info("  NBA ELO BOOTSTRAP — Génération des ratings ELO")
    logger.info("═" * 60)
    logger.info(f"Saisons : {SEASONS}")
    logger.info(f"Fichier de sortie : {OUTPUT_FILE}")

    all_games: List[dict] = []
    for season in SEASONS:
        games = fetch_all_games(season)
        all_games.extend(games)

    if not all_games:
        logger.error(
            "Aucun match récupéré. Vérifiez votre connexion et "
            "la clé BALLDONTLIE_API_KEY si requise."
        )
        return

    logger.info(f"Total matchs : {len(all_games)} — Calcul des ratings ELO…")
    ratings = compute_elo_ratings(all_games)

    # Afficher le top 10
    top10 = sorted(ratings.items(), key=lambda x: x[1], reverse=True)[:10]
    logger.info("Top 10 équipes :")
    for rank, (team, elo) in enumerate(top10, 1):
        logger.info(f"  {rank:2}. {team:<35} ELO : {elo:.0f}")

    save_ratings(ratings, OUTPUT_FILE)

    logger.info("═" * 60)
    logger.info("  BOOTSTRAP TERMINÉ")
    logger.info("═" * 60)


if __name__ == "__main__":
    main()
