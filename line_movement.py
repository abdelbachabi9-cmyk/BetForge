#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â    LINE MOVEMENT â DÃ©tection des mouvements de cotes          â
â    Alerte quand une cote bouge significativement               â
â    Version : 2.0 | Python 3.8+                                â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from database import ApexDatabase
except ImportError:
    ApexDatabase = None


# ââ CONFIGURATION ââââââââââââââââââââââââââââââââââââââââââââââ
LINE_MOVEMENT_CONFIG = {
    # Seuil de mouvement pour dÃ©clencher une alerte (en %)
    "warning_threshold_pct": 5.0,
    # Seuil critique (mouvement majeur)
    "critical_threshold_pct": 10.0,
    # Intervalle minimum entre deux vÃ©rifications (secondes)
    "check_interval": 300,
    # Nombre maximum de snapshots conservÃ©s par match
    "max_snapshots": 20,
}


class OddsSnapshot:
    """ReprÃ©sente un instantanÃ© de cotes pour un match."""

    def __init__(self, match_name: str, market: str, odd: float,
                 timestamp: float = None):
        self.match_name = match_name
        self.market = market
        self.odd = odd
        self.timestamp = timestamp or time.time()

    def __repr__(self):
        return f"OddsSnapshot({self.match_name}, {self.market}, {self.odd})"


class LineMovementTracker:
    """
    Suit les mouvements de cotes entre la capture initiale
    et les mises Ã  jour ultÃ©rieures.

    Cas d'usage :
    - DÃ©tecter les steam moves (mouvements brusques = info sharp)
    - Alerter si une cote se dÃ©grade fortement avant le kick-off
    - Identifier les reverse line movements (cote qui monte malgrÃ©
      un volume de paris cÃ´tÃ© adverse = signal sharp)
    """

    def __init__(self, db: "ApexDatabase" = None):
        self.db = db
        self.config = LINE_MOVEMENT_CONFIG
        # Cache en mÃ©moire : {match_key: [OddsSnapshot, ...]}
        self._snapshots: Dict[str, List[OddsSnapshot]] = {}
        # Cotes initiales capturÃ©es lors de la gÃ©nÃ©ration du coupon
        self._initial_odds: Dict[str, float] = {}

    def _make_key(self, match_name: str, market: str) -> str:
        """ClÃ© unique pour un match + marchÃ©."""
        return f"{match_name}|{market}"

    # ââ CAPTURE DES COTES ââââââââââââââââââââââââââââââââââââââ

    def record_initial_odds(self, coupon: List[dict]) -> None:
        """
        Enregistre les cotes initiales du coupon gÃ©nÃ©rÃ©.
        AppelÃ© juste aprÃ¨s la gÃ©nÃ©ration du coupon.
        """
        for bet in coupon:
            key = self._make_key(bet["match"], bet["market"])
            self._initial_odds[key] = bet["odd"]
            self._snapshots[key] = [
                OddsSnapshot(bet["match"], bet["market"], bet["odd"])
            ]
        logger.info(f"ð¸ Cotes initiales capturÃ©es pour {len(coupon)} sÃ©lections")

    def record_current_odds(self, match_name: str, market: str,
                            current_odd: float) -> Optional[dict]:
        """
        Enregistre une nouvelle cote et calcule le mouvement.
        Retourne un dict avec les infos de mouvement si significatif.
        """
        key = self._make_key(match_name, market)
        initial = self._initial_odds.get(key)

        if initial is None:
            return None

        # Ajouter le snapshot
        snapshot = OddsSnapshot(match_name, market, current_odd)
        if key not in self._snapshots:
            self._snapshots[key] = []
        self._snapshots[key].append(snapshot)

        # Limiter les snapshots
        max_snap = self.config["max_snapshots"]
        if len(self._snapshots[key]) > max_snap:
            self._snapshots[key] = self._snapshots[key][-max_snap:]

        # Calcul du mouvement
        movement_pct = ((current_odd - initial) / initial) * 100

        # DÃ©terminer le niveau d'alerte
        abs_mvt = abs(movement_pct)
        if abs_mvt >= self.config["critical_threshold_pct"]:
            alert_level = "critical"
        elif abs_mvt >= self.config["warning_threshold_pct"]:
            alert_level = "warning"
        else:
            alert_level = "normal"

        # Sauvegarder en DB si significatif
        if alert_level != "normal" and self.db:
            self.db.save_line_movement(
                selection_id=None,
                match_name=match_name,
                market=market,
                odd_initial=initial,
                odd_current=current_odd,
            )

        movement = {
            "match": match_name,
            "market": market,
            "initial_odd": initial,
            "current_odd": current_odd,
            "movement_pct": round(movement_pct, 2),
            "alert_level": alert_level,
            "direction": "up" if movement_pct > 0 else "down",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }

        if alert_level != "normal":
            logger.warning(
                f"â¡ Line movement {alert_level.upper()} : {match_name} "
                f"({market}) : {initial:.2f} â {current_odd:.2f} "
                f"({movement_pct:+.1f}%)"
            )

        return movement

    # ââ VÃRIFICATION BATCH âââââââââââââââââââââââââââââââââââââ

    def check_all_movements(self, current_odds: Dict[str, Dict[str, float]]
                            ) -> List[dict]:
        """
        VÃ©rifie les mouvements pour tous les paris du coupon.

        current_odds : {match_name: {market: current_odd}}
        Retourne la liste des mouvements significatifs.
        """
        alerts = []

        for match_name, markets in current_odds.items():
            for market, current_odd in markets.items():
                movement = self.record_current_odds(
                    match_name, market, current_odd
                )
                if movement and movement["alert_level"] != "normal":
                    alerts.append(movement)

        return alerts

    # ââ ANALYSE ââââââââââââââââââââââââââââââââââââââââââââââââ

    def get_movement_summary(self) -> List[dict]:
        """
        RÃ©sumÃ© de tous les mouvements en cours.
        Retourne une liste triÃ©e par amplitude de mouvement.
        """
        summary = []

        for key, snapshots in self._snapshots.items():
            if len(snapshots) < 2:
                continue

            initial = snapshots[0]
            latest = snapshots[-1]
            movement_pct = ((latest.odd - initial.odd) / initial.odd) * 100

            abs_mvt = abs(movement_pct)
            if abs_mvt >= self.config["critical_threshold_pct"]:
                alert = "critical"
            elif abs_mvt >= self.config["warning_threshold_pct"]:
                alert = "warning"
            else:
                alert = "normal"

            summary.append({
                "match": initial.match_name,
                "market": initial.market,
                "initial_odd": initial.odd,
                "latest_odd": latest.odd,
                "movement_pct": round(movement_pct, 2),
                "num_snapshots": len(snapshots),
                "alert_level": alert,
                "time_span_min": round(
                    (latest.timestamp - initial.timestamp) / 60, 1
                ),
            })

        # Trier par amplitude dÃ©croissante
        summary.sort(key=lambda x: abs(x["movement_pct"]), reverse=True)
        return summary

    def detect_steam_move(self, match_name: str, market: str,
                          threshold_pct: float = 8.0,
                          window_min: float = 15.0) -> bool:
        """
        DÃ©tecte un steam move : mouvement rapide et significatif
        dans un court laps de temps.
        Signe typique d'une info sharp (ex : blessure, composition).
        """
        key = self._make_key(match_name, market)
        snapshots = self._snapshots.get(key, [])

        if len(snapshots) < 2:
            return False

        latest = snapshots[-1]
        window_start = latest.timestamp - (window_min * 60)

        # Trouver le snapshot le plus ancien dans la fenÃªtre
        in_window = [s for s in snapshots if s.timestamp >= window_start]
        if len(in_window) < 2:
            return False

        earliest_in_window = in_window[0]
        movement_pct = abs(
            ((latest.odd - earliest_in_window.odd) / earliest_in_window.odd) * 100
        )

        return movement_pct >= threshold_pct

    # ââ FORMATAGE TELEGRAM âââââââââââââââââââââââââââââââââââââ

    def format_alerts_telegram(self, alerts: List[dict]) -> str:
        """Formate les alertes de mouvement de cotes pour Telegram."""

        def esc(text: str) -> str:
            special = r"\_*[]()~`>#+-=|{}.!"
            return "".join(f"\\{c}" if c in special else c for c in str(text))

        if not alerts:
            return "â Aucun mouvement de cote significatif dÃ©tectÃ©\\."

        lines = [
            "â¡ *ALERTES MOUVEMENT DE COTES*",
            "",
        ]

        level_emoji = {
            "critical": "ð´",
            "warning": "ð¡",
            "normal": "ð¢",
        }

        for alert in alerts:
            emoji = level_emoji.get(alert["alert_level"], "âª")
            direction = "ð" if alert["direction"] == "up" else "ð"

            lines.append(
                f"{emoji} {direction} *{esc(alert['match'])}*"
            )
            lines.append(
                f"   {esc(alert['market'])} : "
                f"{esc(str(alert['initial_odd']))} â "
                f"*{esc(str(alert['current_odd']))}* "
                f"\\({esc(str(alert['movement_pct']))}%\\)"
            )
            lines.append("")

        lines.extend([
            "â" * 28,
            "ð _Cote en baisse \\= argent sharp cÃ´tÃ© opposÃ©_",
            "ð _Cote en hausse \\= opportunitÃ© potentielle_",
        ])

        return "\n".join(lines)
