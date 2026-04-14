# Guide pas-à-pas : Configurer BetForge sur Railway

Ce guide est conçu pour quelqu'un qui n'a aucune notion de GitHub ou de programmation. Suivez chaque étape dans l'ordre.

---

## Étape 1 — Obtenir vos clés API

Avant de configurer Railway, vous avez besoin de 3 éléments :

### 1.1 Token Telegram (votre bot)
Vous l'avez déjà via @BotFather. C'est la longue chaîne de caractères qui ressemble à `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`.

### 1.2 Clé Football-Data.org
1. Allez sur [football-data.org](https://www.football-data.org/)
2. Cliquez **"Register"** (en haut à droite)
3. Créez un compte avec votre email
4. Après confirmation, allez dans **"My Account"**
5. Votre clé API s'affiche — copiez-la

### 1.3 Clé The Odds API
1. Allez sur [the-odds-api.com](https://the-odds-api.com/)
2. Cliquez **"Get API Key"**
3. Entrez votre email
4. Vous recevez votre clé par email — copiez-la

---

## Étape 2 — Configurer Railway

### 2.1 Se connecter à Railway
1. Allez sur [railway.app](https://railway.app/)
2. Connectez-vous avec votre compte GitHub

### 2.2 Ouvrir votre projet BetForge
1. Sur le tableau de bord Railway, cliquez sur votre projet **BetForge**
2. Cliquez sur le **service** (le rectangle qui représente votre bot)

### 2.3 Ajouter les variables d'environnement
1. Cliquez sur l'onglet **"Variables"** (en haut)
2. Pour chaque variable ci-dessous, cliquez **"+ New Variable"**, entrez le nom à gauche et la valeur à droite :

| Nom de la variable | Valeur à entrer |
|---|---|
| `TELEGRAM_TOKEN` | Votre token Telegram (de l'étape 1.1) |
| `TELEGRAM_CHAT_ID` | L'ID de votre chat/canal Telegram |
| `BOT_SEND_HOUR` | `8` (heure d'envoi automatique, format 24h) |
| `BOT_SEND_MINUTE` | `0` (minute d'envoi) |
| `TIMEZONE` | `Africa/Porto-Novo` |
| `DEMO_MODE` | `false` |
| `FOOTBALL_DATA_KEY` | Votre clé football-data.org (étape 1.2) |
| `ODDS_API_KEY` | Votre clé the-odds-api.com (étape 1.3) |

3. Après avoir ajouté toutes les variables, Railway redéploie automatiquement votre bot

---

## Étape 3 — Trouver votre TELEGRAM_CHAT_ID

Si vous ne connaissez pas votre Chat ID :

1. Ouvrez Telegram
2. Cherchez le bot **@userinfobot** ou **@getidsbot**
3. Envoyez-lui `/start`
4. Il vous répondra avec votre **ID** — c'est votre `TELEGRAM_CHAT_ID`

Pour un **canal** ou **groupe** : ajoutez le bot au canal, envoyez un message, puis allez sur `https://api.telegram.org/botVOTRE_TOKEN/getUpdates` dans votre navigateur. Cherchez le champ `"chat":{"id": -100xxxxx}` — ce nombre négatif est votre Chat ID.

---

## Étape 4 — Vérifier que tout fonctionne

1. Dans Railway, allez dans l'onglet **"Deployments"**
2. Vérifiez que le dernier déploiement est **vert** (succès)
3. Ouvrez Telegram et envoyez `/status` à votre bot
4. Le bot doit répondre avec son statut et l'heure du prochain envoi
5. Envoyez `/coupon` pour tester la génération d'un coupon en mode réel

---

## Étape 5 — Révoquer les anciens secrets (IMPORTANT)

Vos anciens tokens Telegram étaient visibles publiquement dans le code sur GitHub. Par sécurité :

### 5.1 Révoquer le token Telegram
1. Ouvrez Telegram
2. Allez voir **@BotFather**
3. Envoyez `/revoke`
4. Sélectionnez votre bot
5. BotFather vous donne un **nouveau token**
6. Retournez dans Railway > Variables et mettez à jour `TELEGRAM_TOKEN` avec le nouveau token

### 5.2 Régénérer les clés API (recommandé)
- Sur football-data.org : allez dans My Account et régénérez votre clé
- Sur the-odds-api.com : demandez une nouvelle clé via leur site
- Mettez à jour les variables correspondantes dans Railway

---

## Résumé des changements effectués sur votre dépôt

| Fichier | Action | Raison |
|---|---|---|
| `config.py` | Modifié | Les clés API sont maintenant lues depuis les variables d'environnement (plus aucun secret dans le code) |
| `bot.py` | Modifié | Correction de bugs, passage en mode réel, validation des paramètres |
| `coupon_generator.py` | Modifié | Suppression des vérifications "demo", utilisation des vraies API |
| `.env.example` | Créé | Modèle listant toutes les variables nécessaires |
| `.env` | Supprimé | Contenait vos vrais tokens exposés publiquement |
| `__pycache__/` | Supprimé | Fichiers compilés qui n'ont pas leur place sur GitHub |
| `.gitignore` | Modifié | Empêche la publication future de secrets et fichiers compilés |

---

## En cas de problème

- **Le bot ne répond pas** : vérifiez dans Railway > Deployments que le service est actif (vert)
- **Erreur "Token invalid"** : votre token a probablement été révoqué, régénérez-le via @BotFather
- **Coupon vide ou erreur API** : vérifiez que vos clés `FOOTBALL_DATA_KEY` et `ODDS_API_KEY` sont correctes dans Railway > Variables
- **Mauvaise heure d'envoi** : ajustez `BOT_SEND_HOUR` et `TIMEZONE` dans Railway > Variables
