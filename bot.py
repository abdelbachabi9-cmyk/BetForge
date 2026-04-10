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

# ââ Configuration du logger âââââââââââââââââââââââââââââââââââââââââââ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s â %(levelname)s â %(name)s â %(message)s",
    datefmt="%H:%M:%S"
)
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
    Telegram supporte le gras, l'italique et les blocs de code.
    """
    if not coupon:
        return "ð *Pas de matchs disponibles aujourd'hui* â aucun coupon gÃ©nÃ©rÃ©\\."

    # Calculs globaux
    total_odd  = round(
        functools.reduce(lambda x, y: x * y, [b["odd"] for b in coupon]), 2
    )
    avg_edge   = round(sum(b["value"]      for b in coupon) / len(coupon), 2)
    avg_conf   = round(sum(b["confidence"] for b in coupon) / len(coupon), 1)

    def esc(text: str) -> str:
        """Ãchappe les caractÃ¨res spÃ©ciaux MarkdownV2."""
        special = r"\_*[]()~`>#+-=|{}.!"
        return "".join(f"\\{c}" if c in special else c for c in str(text))

    lines = []

    # ââ En-tÃªte âââââââââââââââââââââââââââââââââââââââââââââââââââ
    lines.append(f"ð¯ *APEX â COUPON DU JOUR*")
    lines.append(f"ð {esc(date)}")
    lines.append(f"ð _ModÃ¨le Poisson \\(correction scores faibles\\) \\+ ELO_")
    lines.append("")
    lines.append("â" * 30)

    # ââ SÃ©lections ââââââââââââââââââââââââââââââââââââââââââââââââ
    sport_emoji = {
        "Football":   "â½",
        "Basketball": "ð",
        "Tennis":     "ð¾",
    }

    for i, bet in enumerate(coupon, start=1):
        emoji = sport_emoji.get(bet["sport"], "ð")
        lines.append(f"")
        lines.append(f"*SÃLECTION {i}* {emoji} {esc(bet['competition'])}")
        lines.append(f"ð {esc(bet['match'])}")
        lines.append(f"ð *{esc(bet['bet_type'])}*")
        odd_str = f"{bet['odd']:.2f}"
        lines.append(f"ð¶ Cote : *{esc(odd_str)}*")
        lines.append(
            f"ð Proba modÃ¨le : {esc(str(bet['p_model']))}% "
            f"\\| Edge : \\+{esc(str(bet['value']))}%"
        )
        conf_stars = "â­" * int(round(bet["confidence"] / 2))
        lines.append(f"ð Confiance : {conf_stars} {esc(str(bet['confidence']))}/10")
        lines.append("â" * 30)

    # ââ RÃ©sumÃ© ââââââââââââââââââââââââââââââââââââââââââââââââââââ
    target_ok = 4.5 <= total_odd <= 6.0
    status_icon = "â" if target_ok else "â ï¸"

    lines.append("")
    lines.append(f"ð° *COTE TOTALE : {esc(str(total_odd))}* {status_icon}")
    lines.append(f"ð° Mise recommandÃ©e : 2% du bankroll")
    lines.append(f"ð Edge moyen : \\+{esc(str(avg_edge))}%")
    lines.append(f"ð Confiance moyenne : {esc(str(avg_conf))}/10")
    lines.append(f"ð SÃ©lections : {len(coupon)}")
    lines.append("")
    lines.append("â" * 30)
    lines.append(
        "ð _Variance : ~20% de chances de gain par coupon\\. "
        "L'edge se manifeste sur 50\\-100 coupons\\._"
    )
    lines.append("")
    lines.append(
        "â ï¸ _Coupon gÃ©nÃ©rÃ© par algorithme statistique\\. "
        "Les paris comportent un risque de perte\\. "
        "Jouez de faÃ§on responsable\\._"
    )

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

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /start â Message de bienvenue."""
    user = update.effective_user
    prenom = user.first_name if user else "lÃ "

    msg = (
        f"ð¯ *Bienvenue sur APEX, {_esc(prenom)}\\!*\n\n"
        "Je suis un bot de prÃ©diction sportive basÃ© sur des modÃ¨les "
        "statistiques avancÃ©s \\(Poisson \\+ correction scores faibles \\+ ELO\\)\\.\n\n"
        "*Commandes disponibles :*\n"
        "ð /coupon â GÃ©nÃ©rer le coupon du jour\n"
        "ð /status â Statut et prochaine gÃ©nÃ©ration\n"
        "â /aide   â Aide complÃ¨te\n\n"
        f"â° *Envoi automatique :* chaque jour Ã  {BOT_SEND_HOUR:02d}:{BOT_SEND_MINUTE:02d} "
        f"\\({_esc(TIMEZONE)}\\)\n\n"
        "â ï¸ _Les paris comportent un risque de perte\\. Jouez responsablement\\._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /coupon â GÃ©nÃ¨re et envoie le coupon Ã  la demande."""
    # Message d'attente
    wait_msg = await update.message.reply_text(
        "â³ _GÃ©nÃ©ration du coupon en cours\\.\\.\\._",
        parse_mode=ParseMode.MARKDOWN_V2
    )

    # GÃ©nÃ©ration dans un thread sÃ©parÃ© pour ne pas bloquer le bot
    loop = asyncio.get_event_loop()
    message = await loop.run_in_executor(None, generate_coupon_message)

    if "Pas de matchs" in message:
        logger.info("ð Aucun match aujourd'hui â notification envoyÃ©e")

    # Suppression du message d'attente
    await wait_msg.delete()

    # Envoi du coupon (dÃ©couper si > 4096 caractÃ¨res)
    await send_long_message(update.effective_chat.id, message, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /status â Affiche le statut du bot."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    next_send = now.replace(
        hour=BOT_SEND_HOUR, minute=BOT_SEND_MINUTE, second=0, microsecond=0
    )
    if next_send <= now:
        next_send = next_send + timedelta(days=1)

    diff       = next_send - now
    heures     = diff.seconds // 3600
    minutes    = (diff.seconds % 3600) // 60
    mode_label = "ð¡ DÃ©mo \\(donnÃ©es simulÃ©es\\)" if DEMO_MODE else "ð¢ Temps rÃ©el \\(APIs actives\\)"

    msg = (
        "ð *STATUT APEX BOT*\n\n"
        f"ð Heure actuelle : `{now.strftime('%d/%m/%Y %H:%M')}`\n"
        f"â° Prochain coupon : `{next_send.strftime('%d/%m/%Y %H:%M')}`\n"
        f"â Dans : {heures}h {minutes}min\n"
        f"ð Fuseau : `{TIMEZONE}`\n"
        f"âï¸ Mode : {mode_label}\n"
        f"â Bot : *OpÃ©rationnel*"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_aide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /aide â Aide complÃ¨te."""
    msg = (
        "â *AIDE APEX BOT*\n\n"
        "*Commandes :*\n"
        "â«ï¸ /start  â Message de bienvenue\n"
        "â«ï¸ /coupon â GÃ©nÃ©rer le coupon du jour maintenant\n"
        "â«ï¸ /status â Voir le statut et la prochaine gÃ©nÃ©ration\n"
        "â«ï¸ /aide   â Cette aide\n\n"
        "*Comment Ã§a marche ?*\n"
        "APEX analyse les matchs du lendemain avec un modÃ¨le "
        "Poisson \\(correction scores faibles\\) pour le football, ELO pour le basket, "
        "et un modÃ¨le surface\\+forme pour le tennis\\.\n\n"
        "Seuls les paris avec un _edge \\> 5%_ \\(avantage statistique\\) "
        "sont sÃ©lectionnÃ©s\\. Le coupon cible une cote totale de ~5\\.\n\n"
        "*LÃ©gende :*\n"
        "ð¶ Cote : cote bookmaker simulÃ©e\n"
        "ð Edge : avantage statistique vs bookmaker\n"
        "ð Confiance : score /10 basÃ© sur le critÃ¨re de Kelly\n\n"
        "*Comprendre la variance :*\n"
        "Un coupon combinÃ© Ã  cote ~5\\.0 a ~20% de chances de "
        "passer\\. MÃªme avec un edge positif, il faut *50 Ã  100 "
        "coupons* \\(2\\-3 mois\\) pour que l'avantage statistique "
        "se manifeste\\.\n\n"
        "â ï¸ _Jouez de faÃ§on responsable\\. Interdit aux mineurs\\._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# JOB PLANIFIÃ â ENVOI AUTOMATIQUE QUOTIDIEN
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def scheduled_coupon(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job exÃ©cutÃ© chaque jour Ã  l'heure configurÃ©e.
    GÃ©nÃ¨re le coupon et l'envoie dans le chat/canal configurÃ©.
    """
    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID non dÃ©fini â envoi automatique ignorÃ©")
        return

    logger.info(f"â° Envoi automatique du coupon vers {TELEGRAM_CHAT_ID}")

    loop = asyncio.get_event_loop()
    message = await loop.run_in_executor(None, generate_coupon_message)

    try:
        # DÃ©coupage si message trop long
        chunks = split_message(message)
        for chunk in chunks:
            await context.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=chunk,
                parse_mode=ParseMode.MARKDOWN_V2
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
    """Envoie un message potentiellement long en le dÃ©coupant."""
    chunks = split_message(text)
    for chunk in chunks:
        await context.bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode=ParseMode.MARKDOWN_V2
        )


async def post_init(application: Application) -> None:
    """Configure les commandes affichÃ©es dans le menu Telegram."""
    commands = [
        BotCommand("start",  "DÃ©marrer le bot"),
        BotCommand("coupon", "GÃ©nÃ©rer le coupon du jour"),
        BotCommand("status", "Statut et prochaine gÃ©nÃ©ration"),
        BotCommand("aide",   "Aide et documentation"),
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
    logger.info(f"â° Job quotidien planifiÃ© Ã  {send_time.strftime('%H:%M')} ({TIMEZONE})")

    # ââ Lancement du bot ââââââââââââââââââââââââââââââââââââââââââ
    logger.info("ð Bot dÃ©marrÃ© â en attente des messagesâ¦")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
