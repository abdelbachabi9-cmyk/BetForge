# APEX Bot — Prédictions sportives quotidiennes

Bot Telegram qui analyse les matchs du jour (football, basketball, tennis) avec des modèles statistiques et envoie un coupon de paris optimisé chaque matin.

---

## Fonctionnement

APEX récupère les données sportives et les cotes du marché via des APIs gratuites, applique des modèles de prédiction (Poisson pour le football, ELO pour le basketball, ELO-like + surface/forme/H2H pour le tennis), identifie les value bets avec un edge minimum de 5%, et assemble un coupon de 4 à 10 sélections ciblant une cote totale entre 3.0 et 8.0.

Le bot envoie automatiquement le coupon chaque jour à l'heure configurée, et répond aussi à la demande via des commandes Telegram.

### Commandes disponibles

| Commande | Description |
|----------|-------------|
| `/start` | Message de bienvenue |
| `/coupon` | Générer le coupon du jour |
| `/status` | Statut du bot et prochain envoi |
| `/aide` | Explication du fonctionnement |
| `/history` | Historique des 30 derniers jours |
| `/stats` | Statistiques de performance |
| `/result <id> <won\|lost\|void>` | Enregistrer le résultat d'un coupon |

---

## Prérequis

- Python 3.10+
- Un token de bot Telegram (via [@BotFather](https://t.me/BotFather))
- Au moins une clé API sportive (voir section Configuration)

---

## Installation

```bash
# Cloner le repo
git clone https://github.com/abdelbachabi9-cmyk/BetForge.git
cd BetForge

# Installer les dépendances
pip install -r requirements.txt

# Copier et configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos clés
```

---

## Configuration

### Variables d'environnement

Créez un fichier `.env` à la racine du projet (ou configurez-les dans Railway) :

```env
# --- OBLIGATOIRE ---
TELEGRAM_TOKEN=votre_token_botfather

# --- RECOMMANDÉ ---
TELEGRAM_CHAT_ID=id_du_canal_ou_chat
ALLOWED_USERS=123456789,987654321

# --- CLÉS API (au moins une pour le mode réel) ---
FOOTBALL_DATA_KEY=votre_cle_football_data
ODDS_API_KEY=votre_cle_odds_api
API_FOOTBALL_KEY=votre_cle_rapidapi

# --- OPTIONNEL ---
DEMO_MODE=false
BOT_SEND_HOUR=8
BOT_SEND_MINUTE=0
TIMEZONE=Europe/Paris
```

### Obtenir les clés API gratuites

| API | Inscription | Limites gratuites |
|-----|------------|-------------------|
| [football-data.org](https://www.football-data.org/client/register) | Email | 10 requêtes/min |
| [the-odds-api.com](https://the-odds-api.com/#get-access) | Email | 500 requêtes/mois |
| [api-football (RapidAPI)](https://rapidapi.com/api-sports/api/api-football) | Compte RapidAPI | 100 requêtes/jour |

Sans clé API, le bot fonctionne en mode démo avec des données simulées réalistes.

---

## Lancement

### En local

```bash
# Mode démo (pas d'appel API)
DEMO_MODE=true python bot.py

# Mode réel (nécessite les clés API)
python bot.py
```

### Sur Railway

1. Connectez votre repo GitHub à Railway
2. Configurez les variables d'environnement dans **Settings > Variables**
3. Railway détecte automatiquement Python et lance `bot.py`
4. Vérifiez le démarrage dans les logs Railway

Le guide détaillé de configuration Railway est disponible dans `guide_configuration_railway.md`.

---

## Architecture

```
BetForge/
├── bot.py                  # Point d'entrée — handlers Telegram, job planifié
├── coupon_generator.py     # Moteur de prédiction (8 classes, ~1400 lignes)
├── config.py               # Configuration centralisée
├── database.py             # Persistance SQLite (historique coupons)
├── backtester.py           # Suivi de performance
├── requirements.txt        # Dépendances épinglées
├── .env.example            # Template des variables d'environnement
├── CLAUDE.md               # Instructions pour l'assistant IA
├── SECURITY.md             # Règles de sécurité détaillées
└── railway.toml            # Configuration Railway (build/deploy uniquement)
```

### Pipeline de prédiction

```
DataFetcher (APIs / démo)
    → PoissonModel (football)
    → EloModel (basketball)
    → TennisModel (tennis)
    → StatsModel (marchés stats : corners, fautes, cartons, tirs)
        → ValueBetSelector (filtre edge ≥ 5%)
            → CouponBuilder (optimise 4-10 sélections, cote 3.0-8.0)
                → BacktestTracker (sauvegarde historique)
```

### Modèles statistiques

- **Football (Poisson)** — Distribution de Poisson indépendant avec correction de dépendance sur les scores faibles (inspiré Dixon-Coles, 1997). Calcule les probabilités 1X2, Over/Under, BTTS, et marchés stats.
- **Basketball (ELO)** — Système de rating ELO avec bonus domicile (+50 points) et pondération de la forme récente (5 derniers matchs).
- **Tennis (ELO-like)** — Rating combinant ranking ATP/WTA, performance sur surface (clay/hard/grass), forme récente, head-to-head historique, et facteur fatigue.

---

## Sécurité

Les règles de sécurité complètes sont documentées dans `SECURITY.md`. Points clés :

- Aucun secret en dur dans le code — tout passe par `os.getenv()`
- Contrôle d'accès par Telegram user ID (pas par username)
- Token Telegram masqué dans les logs par un filtre automatique
- Timeouts et circuit-breaker sur tous les appels API
- Pas de stack trace dans les messages Telegram

---

## Tests

```bash
# Lancer les tests
pytest -v

# Audit de sécurité des dépendances
pip install pip-audit
pip audit -r requirements.txt
```

---

## Licence

Projet privé. Tous droits réservés.
