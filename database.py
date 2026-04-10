# test#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â         DATABASE â Persistance SQLite pour APEX Bot          â
â         Historique coupons, rÃ©sultats, ROI tracking           â
â         Version : 2.0 | Python 3.8+                          â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
"""

import sqlite3
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Chemin de la base de donnÃ©es (configurable via variable d'environnement)
DB_PATH = os.getenv("APEX_DB_PATH", "apex_history.db")


class ApexDatabase:
    """
    Gestionnaire de persistance SQLite pour APEX Bot.
    Stocke l'historique des coupons, les rÃ©sultats et les mÃ©triques de performance.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """CrÃ©e une connexion SQLite avec row_factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        """Initialise le schÃ©ma de la base de donnÃ©es."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS coupons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    total_odd REAL NOT NULL,
                    num_selections INTEGER NOT NULL,
                    avg_edge REAL NOT NULL,
                    avg_confidence REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    result TEXT DEFAULT NULL,
                    profit REAL DEFAULT NULL,
                    stake REAL DEFAULT 2.0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT NULL
                );

                CREATE TABLE IF NOT EXISTS selections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coupon_id INTEGER NOT NULL,
                    sport TEXT NOT NULL,
                    competition TEXT NOT NULL,
                    match_name TEXT NOT NULL,
                    bet_type TEXT NOT NULL,
                    market TEXT NOT NULL,
                    odd REAL NOT NULL,
                    p_model REAL NOT NULL,
                    p_implied REAL NOT NULL,
                    edge REAL NOT NULL,
                    confidence REAL NOT NULL,
                    result TEXT DEFAULT 'pending',
                    FOREIGN KEY (coupon_id) REFERENCES coupons(id)
                );

                CREATE TABLE IF NOT EXISTS line_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    selection_id INTEGER,
                    match_name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    odd_initial REAL NOT NULL,
                    odd_current REAL NOT NULL,
                    movement_pct REAL NOT NULL,
                    alert_level TEXT DEFAULT 'normal',
                    recorded_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (selection_id) REFERENCES selections(id)
                );

                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE NOT NULL,
                    coupons_generated INTEGER DEFAULT 0,
                    coupons_won INTEGER DEFAULT 0,
                    coupons_lost INTEGER DEFAULT 0,
                    total_stake REAL DEFAULT 0,
                    total_profit REAL DEFAULT 0,
                    roi_pct REAL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_coupons_date ON coupons(date);
                CREATE INDEX IF NOT EXISTS idx_coupons_status ON coupons(status);
                CREATE INDEX IF NOT EXISTS idx_selections_coupon ON selections(coupon_id);
                CREATE INDEX IF NOT EXISTS idx_line_movements_selection ON line_movements(selection_id);
            """)
            conn.commit()
            logger.info(f"â Base de donnÃ©es initialisÃ©e : {self.db_path}")
        except Exception as e:
            logger.error(f"â Erreur initialisation DB : {e}")
        finally:
            conn.close()

    # ââ COUPONS âââââââââââââââââââââââââââââââââââââââââââââââââ

    def save_coupon(self, coupon: List[dict], total_odd: float,
                    avg_edge: float, avg_confidence: float,
                    stake: float = 2.0) -> int:
        """
        Sauvegarde un coupon et ses sÃ©lections dans la DB.
        Retourne l'ID du coupon crÃ©Ã©.
        """
        conn = self._get_conn()
        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            cursor = conn.execute("""
                INSERT INTO coupons (date, total_odd, num_selections, avg_edge,
                                     avg_confidence, stake)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (date_str, total_odd, len(coupon), avg_edge, avg_confidence, stake))

            coupon_id = cursor.lastrowid

            for sel in coupon:
                conn.execute("""
                    INSERT INTO selections (coupon_id, sport, competition, match_name,
                                            bet_type, market, odd, p_model, p_implied,
                                            edge, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    coupon_id,
                    sel.get("sport", ""),
                    sel.get("competition", ""),
                    sel.get("match", ""),
                    sel.get("bet_type", ""),
                    sel.get("market", ""),
                    sel.get("odd", 0),
                    sel.get("p_model", 0),
                    sel.get("p_implied", 0),
                    sel.get("value", 0),
                    sel.get("confidence", 0),
                ))

            conn.commit()
            logger.info(f"ð¾ Coupon #{coupon_id} sauvegardÃ© ({len(coupon)} sÃ©lections)")
            return coupon_id

        except Exception as e:
            logger.error(f"â Erreur sauvegarde coupon : {e}")
            conn.rollback()
            return -1
        finally:
            conn.close()

    def update_coupon_result(self, coupon_id: int, status: str,
                              profit: float = None) -> bool:
        """
        Met Ã  jour le rÃ©sultat d'un coupon.
        status : 'won', 'lost', 'partial', 'void'
        """
        conn = self._get_conn()
        try:
            conn.execute("""
                UPDATE coupons SET status = ?, profit = ?,
                       updated_at = datetime('now')
                WHERE id = ?
            """, (status, profit, coupon_id))
            conn.commit()
            logger.info(f"ð Coupon #{coupon_id} â {status} (profit: {profit})")
            return True
        except Exception as e:
            logger.error(f"â Erreur mise Ã  jour coupon : {e}")
            return False
        finally:
            conn.close()

    def update_selection_result(self, selection_id: int, result: str) -> bool:
        """Met Ã  jour le rÃ©sultat d'une sÃ©lection individuelle."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE selections SET result = ? WHERE id = ?",
                (result, selection_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"â Erreur mise Ã  jour sÃ©lection : {e}")
            return False
        finally:
            conn.close()

    # ââ LINE MOVEMENTS ââââââââââââââââââââââââââââââââââââââââââ

    def save_line_movement(self, selection_id: Optional[int], match_name: str,
                           market: str, odd_initial: float, odd_current: float) -> int:
        """Enregistre un mouvement de cote."""
        movement_pct = round(((odd_current - odd_initial) / odd_initial) * 100, 2)

        # DÃ©terminer le niveau d'alerte
        abs_mvt = abs(movement_pct)
        if abs_mvt >= 10:
            alert_level = "critical"
        elif abs_mvt >= 5:
            alert_level = "warning"
        else:
            alert_level = "normal"

        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                INSERT INTO line_movements (selection_id, match_name, market,
                                            odd_initial, odd_current, movement_pct,
                                            alert_level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (selection_id, match_name, market, odd_initial, odd_current,
                  movement_pct, alert_level))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"â Erreur sauvegarde line movement : {e}")
            return -1
        finally:
            conn.close()

    # ââ STATISTIQUES & REPORTING ââââââââââââââââââââââââââââââââ

    def get_history(self, days: int = 30) -> List[dict]:
        """RÃ©cupÃ¨re l'historique des coupons sur N jours."""
        conn = self._get_conn()
        try:
            since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute("""
                SELECT id, date, total_odd, num_selections, avg_edge,
                       avg_confidence, status, profit, stake
                FROM coupons
                WHERE date >= ?
                ORDER BY date DESC
            """, (since,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_coupon_detail(self, coupon_id: int) -> Optional[dict]:
        """RÃ©cupÃ¨re le dÃ©tail complet d'un coupon."""
        conn = self._get_conn()
        try:
            coupon = conn.execute(
                "SELECT * FROM coupons WHERE id = ?", (coupon_id,)
            ).fetchone()
            if not coupon:
                return None

            selections = conn.execute(
                "SELECT * FROM selections WHERE coupon_id = ?", (coupon_id,)
            ).fetchall()

            result = dict(coupon)
            result["selections"] = [dict(s) for s in selections]
            return result
        finally:
            conn.close()

    def get_performance_stats(self, days: int = 90) -> dict:
        """
        Calcule les statistiques de performance globales.
        Retourne ROI, yield, taux de rÃ©ussite, etc.
        """
        conn = self._get_conn()
        try:
            since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

            stats = conn.execute("""
                SELECT
                    COUNT(*) as total_coupons,
                    SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as won,
                    SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) as lost,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    COALESCE(SUM(stake), 0) as total_staked,
                    COALESCE(SUM(profit), 0) as total_profit,
                    COALESCE(AVG(total_odd), 0) as avg_total_odd,
                    COALESCE(AVG(avg_edge), 0) as avg_edge,
                    COALESCE(AVG(avg_confidence), 0) as avg_confidence,
                    COALESCE(AVG(num_selections), 0) as avg_selections
                FROM coupons
                WHERE date >= ?
            """, (since,)).fetchone()

            result = dict(stats)

            # Calcul du ROI
            total_staked = result["total_staked"]
            if total_staked > 0:
                result["roi_pct"] = round(
                    (result["total_profit"] / total_staked) * 100, 2
                )
            else:
                result["roi_pct"] = 0.0

            # Taux de rÃ©ussite
            decided = result["won"] + result["lost"]
            if decided > 0:
                result["win_rate_pct"] = round(
                    (result["won"] / decided) * 100, 1
                )
            else:
                result["win_rate_pct"] = 0.0

            # Yield (profit par unitÃ© misÃ©e)
            result["yield_pct"] = result["roi_pct"]

            # Stats par sport
            sport_stats = conn.execute("""
                SELECT
                    s.sport,
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN s.result = 'won' THEN 1 ELSE 0 END) as won,
                    AVG(s.edge) as avg_edge,
                    AVG(s.odd) as avg_odd
                FROM selections s
                JOIN coupons c ON s.coupon_id = c.id
                WHERE c.date >= ?
                GROUP BY s.sport
            """, (since,)).fetchall()

            result["by_sport"] = [dict(row) for row in sport_stats]

            return result
        finally:
            conn.close()

    def get_streak(self) -> dict:
        """Calcule la sÃ©rie en cours (wins/losses consÃ©cutifs)."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT status FROM coupons
                WHERE status IN ('won', 'lost')
                ORDER BY date DESC, id DESC
                LIMIT 20
            """).fetchall()

            if not rows:
                return {"type": "none", "count": 0}

            streak_type = rows[0]["status"]
            count = 0
            for row in rows:
                if row["status"] == streak_type:
                    count += 1
                else:
                    break

            return {"type": streak_type, "count": count}
        finally:
            conn.close()

    def get_pending_coupons(self) -> List[dict]:
        """RÃ©cupÃ¨re les coupons en attente de rÃ©sultat."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT id, date, total_odd, num_selections, avg_edge
                FROM coupons
                WHERE status = 'pending'
                ORDER BY date DESC
            """).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_line_movements_for_coupon(self, coupon_id: int) -> List[dict]:
        """RÃ©cupÃ¨re les mouvements de cotes pour un coupon donnÃ©."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT lm.*
                FROM line_movements lm
                JOIN selections s ON lm.selection_id = s.id
                WHERE s.coupon_id = ?
                ORDER BY lm.recorded_at DESC
            """, (coupon_id,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
