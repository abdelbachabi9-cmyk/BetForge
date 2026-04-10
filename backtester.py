#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â         BACKTESTER â Module de backtesting pour APEX Bot        â
â         Analyse de performance historique et simulation        â
â         Version : 2.0 | Python 3.8+                          â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
"""

import logging
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from database import ApexDatabase
except ImportError:
    ApexDatabase = None


class ApexBacktester:
    """
    Module de backtesting pour Ã©valuer la performance historique
    du moteur APEX sur les coupons passÃ©s.

    FonctionnalitÃ©s :
    - Calcul du ROI, yield, taux de rÃ©ussite par sport/marchÃ©
    - Simulation Monte Carlo pour estimer la variance
    - Analyse de la calibration du modÃ¨le (prÃ©diction vs rÃ©alitÃ©)
    - Calcul de la sÃ©quence de drawdown maximale
    """

    def __init__(self, db: "ApexDatabase" = None):
        self.db = db or (ApexDatabase() if ApexDatabase else None)

    # ââ ANALYSE DE PERFORMANCE ââââââââââââââââââââââââââââââââââ

    def performance_report(self, days: int = 90) -> dict:
        """
        GÃ©nÃ¨re un rapport de performance complet.
        Retourne un dict avec toutes les mÃ©triques clÃ©s.
        """
        if not self.db:
            return {"error": "Base de donnÃ©es non disponible"}

        stats = self.db.get_performance_stats(days)
        history = self.db.get_history(days)
        streak = self.db.get_streak()

        # Calcul du drawdown max
        drawdown = self._calculate_max_drawdown(history)

        # Calcul de la variance et du Sharpe ratio
        returns = [c["profit"] for c in history if c["profit"] is not None]
        sharpe = self._calculate_sharpe(returns) if returns else 0.0

        report = {
            "period_days": days,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "overview": {
                "total_coupons": stats["total_coupons"],
                "won": stats["won"],
                "lost": stats["lost"],
                "pending": stats["pending"],
                "win_rate_pct": stats["win_rate_pct"],
                "roi_pct": stats["roi_pct"],
                "yield_pct": stats["yield_pct"],
                "total_staked": stats["total_staked"],
                "total_profit": round(stats["total_profit"], 2),
            },
            "averages": {
                "avg_total_odd": round(stats["avg_total_odd"], 2),
                "avg_edge": round(stats["avg_edge"], 2),
                "avg_confidence": round(stats["avg_confidence"], 1),
                "avg_selections": round(stats["avg_selections"], 1),
            },
            "risk": {
                "max_drawdown": drawdown,
                "sharpe_ratio": sharpe,
                "current_streak": streak,
            },
            "by_sport": stats.get("by_sport", []),
        }

        return report

    def _calculate_max_drawdown(self, history: List[dict]) -> dict:
        """
        Calcule le drawdown maximum (perte maximale depuis un pic).
        """
        if not history:
            return {"max_drawdown_pct": 0, "max_drawdown_abs": 0, "recovery_days": 0}

        # Reconstituer la courbe de bankroll
        bankroll = 100.0  # Base 100
        peak = bankroll
        max_dd_abs = 0
        max_dd_pct = 0
        dd_start = None
        max_recovery = 0

        for coupon in reversed(history):  # Du plus ancien au plus rÃ©cent
            profit = coupon.get("profit")
            if profit is not None:
                bankroll += profit
                if bankroll > peak:
                    if dd_start:
                        recovery_days = (
                            datetime.strptime(coupon["date"], "%Y-%m-%d") - dd_start
                        ).days
                        max_recovery = max(max_recovery, recovery_days)
                    peak = bankroll
                    dd_start = None
                else:
                    dd = peak - bankroll
                    if dd > max_dd_abs:
                        max_dd_abs = dd
                        max_dd_pct = (dd / peak) * 100
                        if not dd_start:
                            dd_start = datetime.strptime(coupon["date"], "%Y-%m-%d")

        return {
            "max_drawdown_pct": round(max_dd_pct, 2),
            "max_drawdown_abs": round(max_dd_abs, 2),
            "longest_recovery_days": max_recovery,
        }

    def _calculate_sharpe(self, returns: List[float],                   risk_free: float = 0.0) -> float:
        """
        Calcule le Sharpe Ratio (rendement ajustÃ© au risque).
        Sharpe > 1.0 = bon, > 2.0 = excellent.
        """
        if len(returns) < 2:
            return 0.0

        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0.001

        return round((avg_return - risk_free) / std_dev, 2)

    # ââ SIMULATION MONTE CARLO ââââââââââââââââââââââââââââââââââ

    def monte_carlo_simulation(self, win_rate: float, avg_odd: float,
                                stake: float = 2.0, num_coupons: int = 100,
                                simulations: int = 1000,
                                bankroll: float = 100.0) -> dict:
        """
        Simule N scÃ©narios Monte Carlo pour estimer la distribution
        des rendements possibles.

        ParamÃ¨tres :
            win_rate : taux de rÃ©ussite estimÃ© (0.0 Ã  1.0)
            avg_odd : cote moyenne des coupons
            stake : mise en % du bankroll
            num_coupons : nombre de coupons Ã  simuler
            simulations : nombre de simulations Monte Carlo
            bankroll : bankroll initiale
        """
        import random

        final_bankrolls = []
        busted = 0  # Nombre de ruines

        for _ in range(simulations):
            br = bankroll
            for _ in range(num_coupons):
                bet_size = br * (stake / 100)
                if random.random() < win_rate:
                    br += bet_size * (avg_odd - 1)
                else:
                    br -= bet_size
                if br <= 0:
                    busted += 1
                    break
            final_bankrolls.append(max(0, br))

        final_bankrolls.sort()
        n = len(final_bankrolls)

        return {
            "simulations": simulations,
            "num_coupons": num_coupons,
            "inputs": {
                "win_rate": win_rate,
                "avg_odd": avg_odd,
                "stake_pct": stake,
                "initial_bankroll": bankroll,
            },
            "results": {
                "median_bankroll": round(final_bankrolls[n // 2], 2),
                "p5_bankroll": round(final_bankrolls[int(n * 0.05)], 2),
                "p25_bankroll": round(final_bankrolls[int(n * 0.25)], 2),
                "p75_bankroll": round(final_bankrolls[int(n * 0.75)], 2),
                "p95_bankroll": round(final_bankrolls[int(n * 0.95)], 2),
                "avg_bankroll": round(sum(final_bankrolls) / n, 2),
                "ruin_probability_pct": round((busted / simulations) * 100, 2),
                "profit_probability_pct": round(
                    sum(1 for b in final_bankrolls if b > bankroll) / n * 100, 1
                ),
            },
        }

    # ââ ANALYSE DE CALIBRATION ââââââââââââââââââââââââââââââââââ

    def calibration_analysis(self, days: int = 90) -> dict:
        """
        Analyse la calibration du modÃ¨le : est-ce que les probabilitÃ©s
        prÃ©dites correspondent aux rÃ©sultats rÃ©els ?

        DÃ©coupe les prÃ©dictions en buckets (0-20%, 20-40%, etc.)
        et compare le taux de rÃ©ussite prÃ©dit vs rÃ©el.
        """
        if not self.db:
            return {"error": "Base de donnÃ©es non disponible"}

        conn = self.db._get_conn()
        try:
            rows = conn.execute("""
                SELECT s.p_model, s.odd, s.result, s.sport, s.market
                FROM selections s
                JOIN coupons c ON s.coupon_id = c.id
                WHERE c.date >= date('now', ?)
                  AND s.result IN ('won', 'lost')
            """, (f"-{days} days",)).fetchall()

            if not rows:
                return {"error": "Pas assez de donnÃ©es pour l'analyse"}

            # Buckets de probabilitÃ©
            buckets = {
                "0-20%": {"predicted": [], "actual": []},
                "20-40%": {"predicted": [], "actual": []},
                "40-60%": {"predicted": [], "actual": []},
                "60-80%": {"predicted": [], "actual": []},
                "80-100%": {"predicted": [], "actual": []},
            }

            for row in rows:
                p = row["p_model"]  # En pourcentage (ex: 65.3)
                won = 1 if row["result"] == "won" else 0

                if p < 20:
                    bucket = "0-20%"
                elif p < 40:
                    bucket = "20-40%"
                elif p < 60:
                    bucket = "40-60%"
                elif p < 80:
                    bucket = "60-80%"
                else:
                    bucket = "80-100%"

                buckets[bucket]["predicted"].append(p)
                buckets[bucket]["actual"].append(won)

            result = {}
            for bucket_name, data in buckets.items():
                n = len(data["actual"])
                if n > 0:
                    avg_predicted = round(sum(data["predicted"]) / n, 1)
                    actual_rate = round(sum(data["actual"]) / n * 100, 1)
                    result[bucket_name] = {
                        "count": n,
                        "avg_predicted_pct": avg_predicted,
                        "actual_win_rate_pct": actual_rate,
                        "calibration_error": round(abs(avg_predicted - actual_rate), 1),
                    }

            return {
                "period_days": days,
                "total_selections": len(rows),
                "buckets": result,
            }
        finally:
            conn.close()

    # ââ FORMATAGE TELEGRAM ââââââââââââââââââââââââââââââââââââââ

    def format_report_telegram(self, report: dict) -> str:
        """Formate le rapport de performance en MarkdownV2 Telegram."""

        def esc(text: str) -> str:
            special = r"\_*[]()~`>#+-=|{}.!"
            return "".join(f"\\{c}" if c in special else c for c in str(text))

        if "error" in report:
            return f"â ï¸ {esc(report['error'])}"

        ov = report["overview"]
        risk = report["risk"]
        avgs = report["averages"]

        lines = [
            "ð *RAPPORT DE PERFORMANCE APEX*",
            f"ð PÃ©riode : {esc(str(report['period_days']))} jours",
            "",
            "â" * 28,
            "",
            f"ð¯ *Coupons :  {ov['total_coupons']}",
            f"â GagnÃ©s : {ov['won']} \\| â Perdus : {ov['lost']} \\| â³ En attente : {ov['pending']}",
            f"ð *Taux de rÃ©ussite : {esc(str(ov['win_rate_pct']))}%*",
            "",
            f"ð° *ROI : {esc(str(ov['roi_pct']))}%*",
            f"ðµ MisÃ© total : {esc(str(ov['total_staked']))} unitÃ©s",
            f"ð Profit net : {esc(str(ov['total_profit']))} unitÃ©s",
            "",
            "â" * 28,
            "",
            f"ð Cote moyenne : {esc(str(avgs['avg_total_odd']))}",
            f"ð Edge moyen : \\+{esc(str(avgs['avg_edge']))}%",
            f"ð¯ Confiance moyenne : {esc(str(avgs['avg_confidence']))}/10",
            "",
            f"ð Drawdown max : {esc(str(risk['max_drawdown']['max_drawdown_pct']))}%",
            f"ð Sharpe ratio : {esc(str(risk['sharpe_ratio']))}",
        ]

        streak = risk["current_streak"]
        if streak["count"] > 0:
            emoji = "ð¥" if streak["type"] == "won" else "âï¸"
            lines.append(
                f"{emoji} SÃ©rie en cours : {streak['count']} "
                f"{'victoire' if streak['type'] == 'won' else 'dÃ©faite'}"
                f"{'s' if streak['count'] > 1 else ''}"
            )

        # Stats par sport
        if report.get("by_sport"):
            lines.extend(["", "â" * 28, "", "*Par sport :*"])
            sport_emoji = {"Football": "â½", "Basketball": "ð", "Tennis": "ð¾"}
            for sp in report["by_sport"]:
                emoji = sport_emoji.get(sp["sport"], "ð")
                win_str = f"{sp['won']}/{sp['total_bets']}"
                lines.append(
                    f"{emoji} {esc(sp['sport'])} : {esc(win_str)} "
                    f"\\(edge moy\\. \\+{esc(str(round(sp['avg_edge'], 1)))}%\\)"
                )

        lines.extend([
            "",
            "â" * 28,
            "ð _Minimum 50 coupons pour des statistiques fiables\\._",
        ])

        return "\n".join(lines)

    def format_history_telegram(self, history: List[dict], limit: int = 10) -> str:
        """Formate l'historique des derniers coupons pour Telegram."""

        def esc(text: str) -> str:
            special = r"\_*[]()~`>#+-=|{}.!"
            return "".join(f"\\{c}" if c in special else c for c in str(text))

        if not history:
            return "ð­ Aucun coupon dans l'historique\\."

        lines = [
            "ð *HISTORIQUE DES COUPONS*",
            "",
        ]

        status_emoji = {
            "won": "â", "lost": "â", "pending": "â³",
            "partial": "ð¶", "void": "âª",
        }

        for coupon in history[:limit]:
            emoji = status_emoji.get(coupon["status"], "â")
            profit_str = ""
            if coupon["profit"] is not None:
                sign = "\\+" if coupon["profit"] >= 0 else ""
                profit_str = f" â {sign}{esc(str(round(coupon['profit'], 2)))}u"

            lines.append(
                f"{emoji} `{esc(coupon['date'])}` \\| "
                f"Cote {esc(str(coupon['total_odd']))} "
                f"\\({coupon['num_selections']} sÃ©l\\.\\)"
                f"{profit_str}"
            )

        total_shown = min(limit, len(history))
        lines.extend([
            "",
            f"_Affichage : {total_shown}/{len(history)} coupons_",
        ])

        return "\n".join(lines)
