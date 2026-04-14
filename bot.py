#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â              APEX â Bot Telegram Coupon Sportif                  â
â   Commandes manuelles + envoi automatique quotidien              â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

Commandes disponibles :
    /start        â Message de bienvenue
    /coupon       â GÃ©nÃ¨re et envoie le coupon du jour
    /status       â Statut du bot et prochaine gÃ©nÃ©ration
    /aide         â Liste des commandes

Envoi automatique : chaque jour Ã  l'heure configurÃ©e (BOT_SEND_HOUR)

Variables d'environnement requises (Railway) :
    TELEGRAM_TOKEN   â Token du bot (obtenu via @BotFather)
    TELEGRAM_CHAT_ID â ID du chat/canal oÃ¹ envoyer le coupon automatique
    BOT_SEND_HOUR    â Heure d'envoi automatique (dÃ©faut : 8)
    BOT_SEND_MINUTE  â Minute d'envoi (dÃ©faut : 0)
    DEMO_MODE        â true/false (dÃ©faut : false)
"""

import os
import re
import sys
import logging
import asyncio
import functools
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo

# ââ BibliothÃ¨ques Telegram ââââââââââââââââââââââââââââââââââââââââââââ
try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application, CommandHandler, ContextTypes, JobQueue,
        ApplicationBuilder
    )
    from telegram.constants import ParseMode
except ImportError:
    print("â python-telegram-bot manquant. Lancez :")
    print("   pip install python-telegram-bot>=20.0 apscheduler")
    sys.exit(1)

# ââ Import du moteur APEX âââââââââââââââââââââââââââââââââââââââââââââ
try:
    from coupon_generator import run_pipeline
    from config import DEMO_MODE as CONFIG_DEMO_MODE
except ImportError as e:
    print(f"â Impossible d'importer coupon_generator.py : {e}")
    sys.exit(1)

# ── [v2.0] Import des modules de persistance et backtesting ──────────
_startup_logger = logging.getLogger("APEX-Bot")

try:
    from database import ApexDatabase
    _db = ApexDatabase()
    _startup_logger.info("✅ Module de persistance (SQLite) chargé")
except ImportError:
    _db = None

try:
    from backtester import ApexBacktester
    _backtester = ApexBacktester(_db) if _db else None
    if _backtester:
        _startup_logger.info("✅ Module de backtesting chargé")
except ImportError:
    _backtester = None


# ââ Configuration du logger âââââââââââââââââââââââââââââââââââââââââââ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s â %(levelname)s â %(name)s â %(message)s",
    datefmt="%H:%M:%S"
)
# FIX T1 : Empêcher httpx/httpcore de logger les URLs contenant le token
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
logging.getLogger("telegram.ext._updater").setLevel(logging.WARNING)

# FIX C1 : Filtre de sécurité — masquer les tokens Telegram dans les logs
# La librairie python-telegram-bot logue le token en clair dans les exceptions
# InvalidToken. Ce filtre le remplace par "***MASKED***" dans tous les messages.
_TOKEN_PATTERN = re.compile(r"\d{8,}:[A-Za-z0-9_-]{30,}")

class _TokenMaskFilter(logging.Filter):
    """Masque tout token Telegram (format 123456:ABC...) dans les messages de log."""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = _TOKEN_PATTERN.sub("***MASKED***", record.msg)
        if record.args:
            # Masquer aussi dans les arguments formatés
            if isinstance(record.args, dict):
                record.args = {
                    k: _TOKEN_PATTERN.sub("***MASKED***", str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _TOKEN_PATTERN.sub("***MASKED***", str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return True

# Appliquer le filtre à TOUS les loggers (root logger)
logging.getLogger().addFilter(_TokenMaskFilter())

logger = logging.getLogger("APEX-Bot")

# ââ Variables d'environnement âââââââââââââââââââââââââââââââââââââââââ
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TIMEZONE         = os.getenv("TIMEZONE", "Europe/Paris")
DEMO_MODE        = os.getenv("DEMO_MODE", "false").lower() == "true"

# Validation des variables d'environnement numÃ©riques
try:
    BOT_SEND_HOUR = int(os.getenv("BOT_SEND_HOUR", "8"))
    if not (0 <= BOT_SEND_HOUR <= 23):
        raise ValueError
except ValueError:
    logger.warning("BOT_SEND_HOUR invalide, utilisation de la valeur par dÃ©faut (8)")
    BOT_SEND_HOUR = 8

try:
    BOT_SEND_MINUTE = int(os.getenv("BOT_SEND_MINUTE", "0"))
    if not (0 <= BOT_SEND_MINUTE <= 59):
        raise ValueError
except ValueError:
    logger.warning("BOT_SEND_MINUTE invalide, utilisation de la valeur par dÃ©faut (0)")
    BOT_SEND_MINUTE = 0

# Synchronisation du mode dÃ©mo avec config.py
import config
config.DEMO_MODE = DEMO_MODE

# FIX T2 : Contrôle d'accès par Telegram user ID
from config import ALLOWED_USERS

def _check_access(func):
    """Décorateur : rejette les utilisateurs non autorisés si ALLOWED_USERS est défini."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
            logger.warning(
                f"Accès refusé pour user_id={update.effective_user.id} "
                f"(@{update.effective_user.username})"
            )
            await update.message.reply_text("⛔ Accès non autorisé.")
            return
        return await func(update, context)
    return wrapper
try:
    import coupon_generator
    coupon_generator.DEMO_MODE = DEMO_MODE
except ImportError:
    pass


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# FORMATAGE DU COUPON EN MARKDOWN TELEGRAM
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _esc(text: str) -> str:
    """Ãchappe les caractÃ¨res spÃ©ciaux MarkdownV2 Telegram."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))

def format_coupon_telegram(coupon: list, date: str) -> str:
    """
    Formate le coupon en MarkdownV2 pour Telegram.
    Format minimaliste : 2 lignes par sélection.
    """
    if not coupon:
        return "⚽ *Pas de matchs disponibles aujourd'hui* \\."

    # Calculs globaux
    total_odd = round(
        functools.reduce(lambda x, y: x * y, [b["odd"] for b in coupon]), 2
    )

    # FIX T7 : Suppression de esc() local — utilise _esc() global

    def stars(confidence: float) -> str:
        """Génère les étoiles de confiance (max 4 étoiles)."""
        count = min(4, max(1, int(round(confidence / 10 * 3))))
        return "★" * count

    sport_emoji = {
        "Football":   "⚽",
        "Basketball": "🏀",
        "Tennis":     "🎾",
    }

    lines = []

    # ── En-tête ───────────────────────────────────────────
    lines.append(f"🎯 *APEX — Coupon du {_esc(date)}*")
    lines.append("")

    # ── Sélections ────────────────────────────────────
    for bet in coupon:
        emoji = sport_emoji.get(bet["sport"], "🏆")

        match_str = bet["match"]
        if " - " in match_str:
            home, _, away = match_str.partition(" - ")
        elif " vs " in match_str:
            home, _, away = match_str.partition(" vs ")
        else:
            home, away = match_str, ""

        if away:
            match_line = f"{emoji} {_esc(home)} — {_esc(away)}"
        else:
            match_line = f"{emoji} {_esc(home)}"

        odd_str = f"{bet['odd']:.2f}"
        bet_line = f"   {_esc(bet['bet_type'])} · {_esc(odd_str)} · {stars(bet['confidence'])}"

        lines.append(match_line)
        lines.append(bet_line)
        lines.append("")

    # ── Résumé ───────────────────────────────────────────────
    total_str = _esc(f"{total_odd:.2f}")
    lines.append("─" * 25)
    lines.append(f"Cote totale : *{total_str}* \\| {len(coupon)} sélections")
    lines.append("Mise : 2% du bankroll")
    lines.append("")
    lines.append("⚠️ Paris à titre indicatif uniquement")

    return "\n".join(lines)


def generate_coupon_message() -> str:
    """GÃ©nÃ¨re le coupon et retourne le message formatÃ© Telegram."""
    try:
        logger.info("ð GÃ©nÃ©ration du coupon APEX en coursâ¦")
        coupon, _ = run_pipeline()
        date = datetime.now().strftime("%d/%m/%Y")
        return format_coupon_telegram(coupon, date)
    except Exception as e:
        logger.error(f"Erreur lors de la gÃ©nÃ©ration : {e}", exc_info=True)
        return "â Une erreur est survenue lors de la gÃ©nÃ©ration du coupon\\.\nVeuillez rÃ©essayer dans quelques instants\\."


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# HANDLERS DES COMMANDES TELEGRAM
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@_check_access
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /start — Message de bienvenue."""
    msg = (
        "*APEX Bot* — Prédictions sportives quotidiennes\n\n"
        "Commandes :\n"
        "/coupon — Coupon du jour\n"
        "/history — Historique 30j\n"
        "/stats — Performance\n"
        "/aide — Comment ça marche\n"
        "/status — État du bot\n\n"
        f"Envoi auto : {BOT_SEND_HOUR:02d}h{BOT_SEND_MINUTE:02d} \\({_esc(TIMEZONE)}\\)"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


@_check_access
async def cmd_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /coupon â GÃ©nÃ¨re et envoie le coupon Ã  la demande."""
    # Message d'attente
    wait_msg = await update.message.reply_text(
        "â³ _GÃ©nÃ©ration du coupon en cours\\.\\.\\._",
        parse_mode=ParseMode.MARKDOWN_V2
    )

    # GÃ©nÃ©ration dans un thread sÃ©parÃ© pour ne pas bloquer le bot
    loop = asyncio.get_running_loop()
    message = await loop.run_in_executor(None, generate_coupon_message)

    if "Pas de matchs" in message:
        logger.info("ð Aucun match aujourd'hui â notification envoyÃ©e")

    # Suppression du message d'attente
    await wait_msg.delete()

    # Envoi du coupon (dÃ©couper si > 4096 caractÃ¨res)
    await send_long_message(update.effective_chat.id, message, context)


@_check_access
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /status — Affiche le statut du bot."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    next_send = now.replace(
        hour=BOT_SEND_HOUR, minute=BOT_SEND_MINUTE, second=0, microsecond=0
    )
    if next_send <= now:
        next_send = next_send + timedelta(days=1)

    mode_label = "Démo" if DEMO_MODE else "Temps réel"

    msg = (
        "*Statut APEX*\n\n"
        f"Heure : `{now.strftime('%d/%m/%Y %H:%M')}`\n"
        f"Prochain coupon : `{next_send.strftime('%d/%m/%Y %H:%M')}`\n"
        f"Mode : {_esc(mode_label)}\n"
        "Statut : ✅ Opérationnel"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


@_check_access
async def cmd_aide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /aide — Comment ça marche."""
    msg = (
        "*Comment fonctionne APEX ?*\n\n"
        "Le bot analyse les matchs du jour avec un modèle statistique "
        "\\(Poisson pour le football, ELO pour basket/tennis\\)\\. "
        "Il sélectionne les paris avec un avantage ≥5% par rapport aux cotes du marché\\.\n\n"
        "Le coupon cible une cote totale d'environ 5\\.0 avec 4 à 8 sélections\\. "
        "Mise recommandée : 2% du bankroll \\(quart de Kelly\\)\\.\n\n"
        "Les étoiles \\(★\\) indiquent le niveau de confiance du modèle\\."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

# ════════════════════════════════════════════════════════════════════
# [v2.0] NOUVELLES COMMANDES — HISTORIQUE ET STATISTIQUES
# ════════════════════════════════════════════════════════════════════

@_check_access
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /history — Affiche l'historique des derniers coupons."""
    if not _db or not _backtester:
        await update.message.reply_text(
            "⚠️ Module de persistance non disponible\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    history = _db.get_history(days=30)
    if not history:
        await update.message.reply_text(
            "📭 Aucun coupon dans l'historique\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    msg = _backtester.format_history_telegram(history, limit=10)
    await send_long_message(update.effective_chat.id, msg, context)


@_check_access
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /stats — Affiche les statistiques de performance."""
    if not _backtester:
        await update.message.reply_text(
            "⚠️ Module de backtesting non disponible\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    wait_msg = await update.message.reply_text(
        "📊 _Calcul des statistiques en cours\\.\\.\\._",
        parse_mode=ParseMode.MARKDOWN_V2
    )

    loop = asyncio.get_running_loop()
    report = await loop.run_in_executor(None, lambda: _backtester.performance_report(90))
    msg = _backtester.format_report_telegram(report)

    await wait_msg.delete()
    await send_long_message(update.effective_chat.id, msg, context)


@_check_access
async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Commande /result <id> <won|lost> — Enregistre le résultat d'un coupon.
    Exemple : /result 42 won
    """
    if not _db:
        await update.message.reply_text(
            "⚠️ Module de persistance non disponible\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "ℹ️ Usage : `/result <id> <won|lost|void>`\n"
            "Exemple : `/result 42 won`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    try:
        coupon_id = int(args[0])
        result = args[1].lower()
        if result not in ('won', 'lost', 'void', 'partial'):
            raise ValueError

        coupon_detail = _db.get_coupon_detail(coupon_id)
        if not coupon_detail:
            await update.message.reply_text(
                f"❌ Coupon \\#{_esc(str(coupon_id))} non trouvé\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # Calcul du profit
        stake = coupon_detail.get('stake', 2.0)
        if result == 'won':
            profit = round(stake * (coupon_detail['total_odd'] - 1), 2)
        elif result == 'lost':
            profit = -stake
        else:
            profit = 0.0

        _db.update_coupon_result(coupon_id, result, profit)

        emoji = '✅' if result == 'won' else '❌' if result == 'lost' else '⚪'
        sign = '\\+' if profit >= 0 else ''
        await update.message.reply_text(
            f"{emoji} Coupon \\#{_esc(str(coupon_id))} → *{_esc(result)}*\n"
            f"💰 Profit : {sign}{_esc(str(profit))} unités",
            parse_mode=ParseMode.MARKDOWN_V2
        )

    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Format invalide\\. Usage : `/result <id> <won|lost|void>`",
            parse_mode=ParseMode.MARKDOWN_V2
        )


# JOB PLANIFIÃ â ENVOI AUTOMATIQUE QUOTIDIEN
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def scheduled_resolve_results(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job exécuté chaque nuit à 01h00 (R4).
    Récupère les scores réels des matchs d'hier et met à jour le BacktestTracker.
    Nécessite FOOTBALL_DATA_KEY pour la résolution football.
    """
    from datetime import date as _date
    yesterday = (_date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    logger.info(f'Resolution des resultats du {yesterday}...')

    try:
        from coupon_generator import DataFetcher, BacktestTracker
        loop = asyncio.get_running_loop()

        def _resolve():
            fetcher = DataFetcher()
            match_results = fetcher.fetch_match_results(yesterday)
            if not match_results:
                logger.info(f'  Aucun resultat recupere pour {yesterday}')
                return 0
            tracker = BacktestTracker()
            return tracker.resolve_results(yesterday, match_results)

        updated = await loop.run_in_executor(None, _resolve)
        if updated:
            logger.info(f'{updated} selections resolues pour {yesterday}')
        else:
            logger.info(f'  Aucune selection a resoudre pour {yesterday}')
    except Exception as e:
        logger.error(f'Erreur lors de la resolution des resultats : {e}', exc_info=True)


async def scheduled_coupon(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job exÃ©cutÃ© chaque jour Ã  l'heure configurÃ©e.
    GÃ©nÃ¨re le coupon et l'envoie dans le chat/canal configurÃ©.
    """
    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID non dÃ©fini â envoi automatique ignorÃ©")
        return

    logger.info(f"â° Envoi automatique du coupon vers {TELEGRAM_CHAT_ID}")

    loop = asyncio.get_running_loop()
    message = await loop.run_in_executor(None, generate_coupon_message)

    try:
        # DÃ©coupage si message trop long
        chunks = split_message(message)
        for chunk in chunks:
            try:
                await context.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=chunk,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as md_err:
                logger.warning(f"MarkdownV2 fallback : {md_err}")
                plain = re.sub(r'\\([_*\[\]()~`>#+=|{}.!\-])', r'\1', chunk)
                plain = plain.replace("*", "").replace("_", "")
                await context.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID, text=plain
                )
        logger.info("â Coupon automatique envoyÃ© avec succÃ¨s")
    except Exception as e:
        logger.error(f"â Erreur envoi automatique : {e}", exc_info=True)


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# UTILITAIRES
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def split_message(text: str, max_len: int = 4000) -> list:
    """DÃ©coupe un message Telegram en morceaux si > max_len caractÃ¨res."""
    if len(text) <= max_len:
        return [text]
    parts = []
    while len(text) > max_len:
        # DÃ©couper Ã  la derniÃ¨re ligne avant la limite
        cut = text[:max_len].rfind("\n")
        if cut == -1:
            cut = max_len
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


async def send_long_message(chat_id, text: str,
                             context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message potentiellement long en le découpant.
    Fallback en texte brut si MarkdownV2 échoue."""
    chunks = split_message(text)
    for chunk in chunks:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as md_err:
            logger.warning(f"MarkdownV2 échoué, fallback texte brut : {md_err}")
            plain = re.sub(r'\\([_*\\[\\]()~`>#+=|{}.!\\-])', r'\\1', chunk)
            plain = plain.replace('*', '').replace('_', '')
            await context.bot.send_message(chat_id=chat_id, text=plain)


async def post_init(application: Application) -> None:
    """Configure les commandes affichÃ©es dans le menu Telegram."""
    # FIX T5 : Enregistrement des 7 commandes (pas seulement 4)
    commands = [
        BotCommand("start",   "DÃ©marrer le bot"),
        BotCommand("coupon",  "GÃ©nÃ©rer le coupon du jour"),
        BotCommand("status",  "Statut et prochaine gÃ©nÃ©ration"),
        BotCommand("aide",    "Aide et documentation"),
        BotCommand("history", "Historique des 30 derniers jours"),
        BotCommand("stats",   "Statistiques de performance"),
        BotCommand("result",  "RÃ©sultat d'un coupon"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("â Commandes Telegram enregistrÃ©es")


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# POINT D'ENTRÃE PRINCIPAL
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def main() -> None:
    """Lance le bot Telegram APEX."""

    # ââ VÃ©rification du token âââââââââââââââââââââââââââââââââââââ
    if not TELEGRAM_TOKEN:
        logger.error(
            "â TELEGRAM_TOKEN non dÃ©fini !\n"
            "   Ajoutez la variable d'environnement TELEGRAM_TOKEN\n"
            "   (obtenu via @BotFather sur Telegram)"
        )
        sys.exit(1)

    logger.info("â" * 55)
    logger.info("  ð¯ APEX BOT â DÃ©marrage")
    logger.info(f"  â° Envoi auto : {BOT_SEND_HOUR:02d}:{BOT_SEND_MINUTE:02d} ({TIMEZONE})")
    logger.info(f"  âï¸  Mode : {'DÃ©mo' if DEMO_MODE else 'Temps rÃ©el'}")
    logger.info("â" * 55)

    # ââ Construction de l'application ââââââââââââââââââââââââââââ
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ââ Enregistrement des handlers âââââââââââââââââââââââââââââââ
    application.add_handler(CommandHandler("start",  cmd_start))
    application.add_handler(CommandHandler("coupon", cmd_coupon))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("aide",   cmd_aide))
    # [v2.0] Nouvelles commandes
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("stats",   cmd_stats))
    application.add_handler(CommandHandler("result",  cmd_result))

    # ââ Job planifiÃ© (envoi automatique quotidien) ââââââââââââââââ
    tz = ZoneInfo(TIMEZONE)
    send_time = dt_time(
        hour=BOT_SEND_HOUR,
        minute=BOT_SEND_MINUTE,
        second=0,
        tzinfo=tz
    )
    application.job_queue.run_daily(
        callback=scheduled_coupon,
        time=send_time,
        name="daily_coupon"
    )
    # R4 : Job de resolution automatique des resultats (chaque nuit a 01h00)
    resolve_time = dt_time(hour=1, minute=0, second=0, tzinfo=tz)
    application.job_queue.run_daily(
        callback=scheduled_resolve_results,
        time=resolve_time,
        name="daily_resolve_results"
    )
    logger.info(f"Job resolution resultats planifie a 01:00 ({TIMEZONE})")
    logger.info(f"â° Job quotidien planifiÃ© Ã  {send_time.strftime('%H:%M')} ({TIMEZONE})")

    # ââ Lancement du bot ââââââââââââââââââââââââââââââââââââââââââ
    logger.info("ð Bot dÃ©marrÃ© â en attente des messagesâ¦")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
