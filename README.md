# 🎯 APEX — Bot Telegram de Prédiction Sportive

Algorithme statistique complet qui génère un coupon de paris sportifs quotidien (cote cible ~5) et le diffuse via un **bot Telegram**, avec envoi automatique quotidien et commandes à la demande.

---

## 📋 Fichiers du projet

```
├── bot.py                ← Bot Telegram (commandes + planificateur)
├── coupon_generator.py   ← Moteur APEX (Poisson + ELO + Value Betting)
├── config.py             ← Paramètres des modèles et clés API
├── requirements.txt      ← Dépendances Python
├── Procfile              ← Configuration Railway (démarrage)
├── railway.toml          ← Configuration Railway (build)
├── .env.example          ← Modèle de variables d'environnement
└── README.md             ← Ce fichier
```

---

## 🤖 Étape 1 — Créer le bot Telegram

1. Ouvrez Telegram et cherchez **@BotFather**
2. Envoyez `/newbot`
3. Choisissez un nom, ex : `APEX Sports`
4. Choisissez un username, ex : `apex_sports_bot`
5. BotFather vous donne un **token** du type :
   ```
   123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```
   → Notez-le, c'est votre `TELEGRAM_TOKEN`

### Obtenir votre Chat ID

1. Envoyez n'importe quel message à votre bot
2. Visitez dans votre navigateur :
   ```
   https://api.telegram.org/bot<VOTRE_TOKEN>/getUpdates
   ```
3. Trouvez `"chat":{"id": 123456789}` → c'est votre `TELEGRAM_CHAT_ID`

---

## 🚀 Étape 2 — Déployer sur Railway (gratuit)

### Prérequis
- Compte GitHub : [github.com](https://github.com)
- Compte Railway : [railway.app](https://railway.app) *(connexion avec GitHub)*

### Procédure

**1. Pousser le code sur GitHub**
```bash
git init
git add .
git commit -m "APEX Bot - initial commit"
git branch -M main
git remote add origin https://github.com/VOTRE_USERNAME/apex-bot.git
git push -u origin main
```

**2. Créer un nouveau projet Railway**
- Allez sur [railway.app/new](https://railway.app/new)
- Cliquez **"Deploy from GitHub repo"**
- Sélectionnez votre repo `apex-bot`
- Railway détecte automatiquement `Procfile` et `requirements.txt`

**3. Configurer les variables d'environnement**

Dans Railway → votre projet → onglet **Variables**, ajoutez :

| Variable | Valeur | Obligatoire |
|----------|--------|-------------|
| `TELEGRAM_TOKEN` | `123456789:ABCdef...` | ✅ |
| `TELEGRAM_CHAT_ID` | `123456789` | ✅ |
| `BOT_SEND_HOUR` | `8` | (défaut : 8) |
| `BOT_SEND_MINUTE` | `0` | (défaut : 0) |
| `TIMEZONE` | `Europe/Paris` | (défaut) |
| `DEMO_MODE` | `true` | (défaut) |

**4. Déployer**
- Railway démarre automatiquement le bot après chaque push
- Vérifiez les logs dans l'onglet **Deployments**

---

## 💻 Étape 3 — Test local (optionnel)

```bash
# Installer les dépendances
pip install -r requirements.txt

# Créer votre fichier .env
cp .env.example .env
# Éditez .env avec votre token et chat ID

# Lancer le bot
python bot.py
```

---

## 📱 Commandes du bot

| Commande | Description |
|----------|-------------|
| `/start` | Message de bienvenue |
| `/coupon` | Générer le coupon maintenant |
| `/status` | Statut et prochaine génération |
| `/aide` | Aide complète |

---

## 🔑 Activer les données en temps réel

Par défaut le bot tourne en mode démo (données simulées). Pour des données réelles :

1. Obtenez vos clés gratuites :
   - **football-data.org** → [football-data.org/client/register](https://www.football-data.org/client/register)
   - **the-odds-api.com** → [the-odds-api.com/#get-access](https://the-odds-api.com/#get-access)

2. Dans Railway Variables, ajoutez :
   ```
   DEMO_MODE=false
   ```
   Et mettez à jour `config.py` avec vos clés.

---

## 📊 Modèles statistiques

- **Football** : Poisson/Dixon-Coles — calcule les buts attendus (xG) et les probabilités 1X2/Over/BTTS
- **Basketball** : ELO adapté avec bonus domicile et score de forme récente
- **Tennis** : ELO-like basé sur le classement ATP/WTA + performance sur surface + forme

Seuls les paris avec un **edge ≥ 5%** (avantage vs bookmaker) sont retenus.

---

## ⚠️ Avertissement

> Ce programme est fourni à titre éducatif et de recherche statistique.
> Les paris sportifs comportent un risque de perte financière.
> Jouez de façon responsable. Interdit aux mineurs.
