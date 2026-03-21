#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║              APEX — Bot Telegram Coupon Sportif                  ║
║   Commandes manuelles + envoi automatique quotidien              ║
╚══════════════════════════════════════════════════════════════════╝

Commandes disponibles :
    /start        — Message de bienvenue
    /coupon       — Génère et envoie le coupon du jour
    /status       — Statut du bot et prochaine génération
    /aide         — Liste des commandes

Envoi automatique : chaque jour à l'heure configurée (BOT_SEND_HOUR)

Variables d'environnement requises (Railway) :
    TELEGRAM_TOKEN   — Token du bot (obtenu via @BotFather)
    TELEGRAM_CHAT_ID — ID du chat/canal où envoyer le coupon automatique
    BOT_SEND_HOUR    — Heure d'envoi automatique (défaut : 8)
    BOT_SEND_MINUTE  — Minute d'envoi (défaut : 0)
    DEMO_MODE        — true/false (défaut : true)
"""

import os
import sys
import logging
import asyncio
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

# ── Bibliothèques Telegram ────────────────────────────────────────────
try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application, CommandHandler, ContextTypes, JobQueue,
        ApplicationBuilder
    )
    from telegram.constants import ParseMode
except ImportError:
    print("❌ python-telegram-bot manquant. Lancez :")
    print("   pip install python-telegram-bot>=20.0 apscheduler")
    sys.exit(1)

# ── Import du moteur APEX ─────────────────────────────────────────────
try:
    from coupon_generator import run_pipeline
    from config import DEMO_MODE as CONFIG_DEMO_MODE
except ImportError as e:
    print(f"❌ Impossible d'importer coupon_generator.py : {e}")
    sys.exit(1)

# ── Configuration du logger ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("APEX-Bot")

# ── Variables d'environnement ─────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BOT_SEND_HOUR    = int(os.getenv("BOT_SEND_HOUR",   "8"))
BOT_SEND_MINUTE  = int(os.getenv("BOT_SEND_MINUTE", "0"))
TIMEZONE         = os.getenv("TIMEZONE", "Europe/Paris")
DEMO_MODE        = os.getenv("DEMO_MODE", "true").lower() == "true"

# Surcharge du mode démo depuis l'env (priorité sur config.py)
if DEMO_MODE != CONFIG_DEMO_MODE:
    import config
    config.DEMO_MODE = DEMO_MODE


# ══════════════════════════════════════════════════════════════════════
# FORMATAGE DU COUPON EN MARKDOWN TELEGRAM
# ══════════════════════════════════════════════════════════════════════

def format_coupon_telegram(coupon: list, date: str) -> str:
    """
    Formate le coupon en MarkdownV2 pour Telegram.
    Telegram supporte le gras, l'italique et les blocs de code.
    """
    if not coupon:
        return "⚠️ Aucune sélection valide générée aujourd'hui\\."

    # Calculs globaux
    total_odd  = round(
        __import__("functools").reduce(lambda x, y: x * y, [b["odd"] for b in coupon]), 2
    )
    avg_edge   = round(sum(b["value"]      for b in coupon) / len(coupon), 2)
    avg_conf   = round(sum(b["confidence"] for b in coupon) / len(coupon), 1)

    def esc(text: str) -> str:
        """Échappe les caractères spéciaux MarkdownV2."""
        special = r"\_*[]()~`>#+-=|{}.!"
        return "".join(f"\\{c}" if c in special else c for c in str(text))

    lines = []

    # ── En-tête ───────────────────────────────────────────────────
    lines.append(f"🎯 *APEX — COUPON DU JOUR*")
    lines.append(f"📅 {esc(date)}")
    lines.append(f"📊 _Modèle Poisson\\-Dixon\\-Coles \\+ ELO \\+ Value Betting_")
    lines.append("")
    lines.append("━" * 30)

    # ── Sélections ────────────────────────────────────────────────
    sport_emoji = {
        "Football":   "⚽",
        "Basketball": "🏀",
        "Tennis":     "🎾",
    }

    for i, bet in enumerate(coupon, start=1):
        emoji = sport_emoji.get(bet["sport"], "🏅")
        lines.append(f"")
        lines.append(f"*SÉLECTION {i}* {emoji} {esc(bet['competition'])}")
        lines.append(f"🆚 {esc(bet['match'])}")
        lines.append(f"📌 *{esc(bet['bet_type'])}*")
        odd_str = f"{bet['odd']:.2f}"
        lines.append(f"💶 Cote : *{esc(odd_str)}*")
        lines.append(
            f"📈 Proba modèle : {esc(str(bet['p_model']))}% "
            f"\\| Edge : \\+{esc(str(bet['value']))}%"
        )
        conf_stars = "⭐" * int(round(bet["confidence"] / 2))
        lines.append(f"🔒 Confiance : {conf_stars} {esc(str(bet['confidence']))}/10")
        lines.append("━" * 30)

    # ── Résumé ────────────────────────────────────────────────────
    target_ok = 4.5 <= total_odd <= 6.0
    status_icon = "✅" if target_ok else "⚠️"

    lines.append("")
    lines.append(f"🎰 *COTE TOTALE : {esc(str(total_odd))}* {status_icon}")
    lines.append(f"💰 Mise recommandée : 2% du bankroll")
    lines.append(f"📈 Edge moyen : \\+{esc(str(avg_edge))}%")
    lines.append(f"🔒 Confiance moyenne : {esc(str(avg_conf))}/10")
    lines.append(f"📋 Sélections : {len(coupon)}")
    lines.append("")
    lines.append("━" * 30)
    lines.append(
        "⚠️ _Coupon généré par algorithme statistique\\. "
        "Les paris comportent un risque de perte\\. "
        "Jouez de façon responsable\\._"
    )

    return "\n".join(lines)


def generate_coupon_message() -> str:
    """Génère le coupon et retourne le message formaté Telegram."""
    try:
        logger.info("🔄 Génération du coupon APEX en cours…")
        coupon, _ = run_pipeline()
        date = (datetime.now() + __import__("datetime").timedelta(days=1)).strftime("%d/%m/%Y")
        return format_coupon_telegram(coupon, date)
    except Exception as e:
        logger.error(f"Erreur lors de la génération : {e}", exc_info=True)
        return f"❌ Erreur lors de la génération du coupon : {e}"


# ══════════════════════════════════════════════════════════════════════
# HANDLERS DES COMMANDES TELEGRAM
# ══════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /start — Message de bienvenue."""
    user = update.effective_user
    prenom = user.first_name if user else "là"

    msg = (
        f"🎯 *Bienvenue sur APEX, {prenom}\\!*\n\n"
        "Je suis un bot de prédiction sportive basé sur des modèles "
        "statistiques avancés \\(Poisson\\-Dixon\\-Coles \\+ ELO\\)\\.\n\n"
        "*Commandes disponibles :*\n"
        "📌 /coupon — Générer le coupon du jour\n"
        "📊 /status — Statut et prochaine génération\n"
        "❓ /aide   — Aide complète\n\n"
        f"⏰ *Envoi automatique :* chaque jour à {BOT_SEND_HOUR:02d}:{BOT_SEND_MINUTE:02d} "
        f"\\({TIMEZONE}\\)\n\n"
        "⚠️ _Les paris comportent un risque de perte\\. Jouez responsablement\\._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /coupon — Génère et envoie le coupon à la demande."""
    # Message d'attente
    wait_msg = await update.message.reply_text(
        "⏳ _Génération du coupon en cours\\.\\.\\._",
        parse_mode=ParseMode.MARKDOWN_V2
    )

    # Génération dans un thread séparé pour ne pas bloquer le bot
    loop = asyncio.get_event_loop()
    message = await loop.run_in_executor(None, generate_coupon_message)

    # Suppression du message d'attente
    await wait_msg.delete()

    # Envoi du coupon (découper si > 4096 caractères)
    await send_long_message(update.effective_chat.id, message, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /status — Affiche le statut du bot."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    next_send = now.replace(
        hour=BOT_SEND_HOUR, minute=BOT_SEND_MINUTE, second=0, microsecond=0
    )
    if next_send <= now:
        next_send = next_send.replace(day=next_send.day + 1)

    diff       = next_send - now
    heures     = diff.seconds // 3600
    minutes    = (diff.seconds % 3600) // 60
    mode_label = "🟡 Démo \\(données simulées\\)" if DEMO_MODE else "🟢 Temps réel \\(APIs actives\\)"

    msg = (
        "📊 *STATUT APEX BOT*\n\n"
        f"🕐 Heure actuelle : `{now.strftime('%d/%m/%Y %H:%M')}`\n"
        f"⏰ Prochain coupon : `{next_send.strftime('%d/%m/%Y %H:%M')}`\n"
        f"⌛ Dans : {heures}h {minutes}min\n"
        f"🌍 Fuseau : `{TIMEZONE}`\n"
        f"⚙️ Mode : {mode_label}\n"
        f"✅ Bot : *Opérationnel*"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_aide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /aide — Aide complète."""
    msg = (
        "❓ *AIDE APEX BOT*\n\n"
        "*Commandes :*\n"
        "▫️ /start  — Message de bienvenue\n"
        "▫️ /coupon — Générer le coupon du jour maintenant\n"
        "▫️ /status — Voir le statut et la prochaine génération\n"
        "▫️ /aide   — Cette aide\n\n"
        "*Comment ça marche ?*\n"
        "APEX analyse les matchs du lendemain avec un modèle "
        "Poisson\\-Dixon\\-Coles pour le football, ELO pour le basket, "
        "et un modèle surface\\+forme pour le tennis\\.\n\n"
        "Seuls les paris avec un _edge \\> 5%_ \\(avantage statistique\\) "
        "sont sélectionnés\\. Le coupon cible une cote totale de ~5\\.\n\n"
        "*Légende :*\n"
        "💶 Cote : cote bookmaker simulée\n"
        "📈 Edge : avantage statistique vs bookmaker\n"
        "🔒 Confiance : score /10 basé sur proba \\+ edge\n\n"
        "⚠️ _Jouez de façon responsable\\. Interdit aux mineurs\\._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


# ══════════════════════════════════════════════════════════════════════
# JOB PLANIFIÉ — ENVOI AUTOMATIQUE QUOTIDIEN
# ══════════════════════════════════════════════════════════════════════

async def scheduled_coupon(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job exécuté chaque jour à l'heure configurée.
    Génère le coupon et l'envoie dans le chat/canal configuré.
    """
    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID non défini — envoi automatique ignoré")
        return

    logger.info(f"⏰ Envoi automatique du coupon vers {TELEGRAM_CHAT_ID}")

    loop = asyncio.get_event_loop()
    message = await loop.run_in_executor(None, generate_coupon_message)

    try:
        # Découpage si message trop long
        chunks = split_message(message)
        for chunk in chunks:
            await context.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=chunk,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        logger.info("✅ Coupon automatique envoyé avec succès")
    except Exception as e:
        logger.error(f"❌ Erreur envoi automatique : {e}", exc_info=True)


# ══════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════

def split_message(text: str, max_len: int = 4000) -> list:
    """Découpe un message Telegram en morceaux si > max_len caractères."""
    if len(text) <= max_len:
        return [text]
    parts = []
    while len(text) > max_len:
        # Découper à la dernière ligne avant la limite
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
    """Envoie un message potentiellement long en le découpant."""
    chunks = split_message(text)
    for chunk in chunks:
        await context.bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode=ParseMode.MARKDOWN_V2
        )


async def post_init(application: Application) -> None:
    """Configure les commandes affichées dans le menu Telegram."""
    commands = [
        BotCommand("start",  "Démarrer le bot"),
        BotCommand("coupon", "Générer le coupon du jour"),
        BotCommand("status", "Statut et prochaine génération"),
        BotCommand("aide",   "Aide et documentation"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Commandes Telegram enregistrées")


# ══════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    """Lance le bot Telegram APEX."""

    # ── Vérification du token ─────────────────────────────────────
    if not TELEGRAM_TOKEN:
        logger.error(
            "❌ TELEGRAM_TOKEN non défini !\n"
            "   Ajoutez la variable d'environnement TELEGRAM_TOKEN\n"
            "   (obtenu via @BotFather sur Telegram)"
        )
        sys.exit(1)

    logger.info("═" * 55)
    logger.info("  🎯 APEX BOT — Démarrage")
    logger.info(f"  ⏰ Envoi auto : {BOT_SEND_HOUR:02d}:{BOT_SEND_MINUTE:02d} ({TIMEZONE})")
    logger.info(f"  ⚙️  Mode : {'Démo' if DEMO_MODE else 'Temps réel'}")
    logger.info("═" * 55)

    # ── Construction de l'application ────────────────────────────
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── Enregistrement des handlers ───────────────────────────────
    application.add_handler(CommandHandler("start",  cmd_start))
    application.add_handler(CommandHandler("coupon", cmd_coupon))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("aide",   cmd_aide))

    # ── Job planifié (envoi automatique quotidien) ────────────────
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
    logger.info(f"⏰ Job quotidien planifié à {send_time.strftime('%H:%M')} ({TIMEZONE})")

    # ── Lancement du bot ──────────────────────────────────────────
    logger.info("🚀 Bot démarré — en attente des messages…")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
