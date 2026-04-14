# Guide de Configuration — Workflow N8N : Telegram → WhatsApp

## Architecture du Workflow

```
Telegram Trigger → Détection du type de message → Téléchargement média (si nécessaire) → Envoi vers WhatsApp
```

Le workflow gère 5 types de contenus : texte, images/photos, documents, audio/voix et vidéos. Chaque message relayé inclut le nom de l'expéditeur Telegram.

---

## Prérequis

Avant d'importer le workflow, tu as besoin de :

1. **Un Bot Telegram** — créé via @BotFather sur Telegram. Note le **Bot Token**.
2. **Un compte WhatsApp Business API (Meta)** — configuré sur [developers.facebook.com](https://developers.facebook.com). Tu auras besoin de :
   - Le **Phone Number ID** (identifiant du numéro WhatsApp)
   - Un **Access Token** permanent (Bearer token)
3. **Ton instance N8N self-hosted** accessible et fonctionnelle.

---

## Étape 1 : Configurer le Bot Telegram

1. Ouvre Telegram et cherche **@BotFather**.
2. Envoie `/newbot` et suis les instructions pour créer ton bot.
3. Copie le **Bot Token** (format : `123456789:ABCdefGhIJklMNOPqrsTUVwxyz`).
4. **Ajoute le bot dans ton groupe Telegram** en tant que membre (ou admin pour lire tous les messages).
5. **Désactive le mode Privacy** : envoie `/setprivacy` à @BotFather → choisis ton bot → `Disable`. Cela permet au bot de lire tous les messages du groupe, pas seulement les commandes.

---

## Étape 2 : Configurer WhatsApp Business API

1. Va sur [developers.facebook.com](https://developers.facebook.com) et crée une app de type **Business**.
2. Ajoute le produit **WhatsApp** à ton app.
3. Dans la section **WhatsApp > API Setup** :
   - Note ton **Phone Number ID** (ex: `1234567890123456`)
   - Génère un **Permanent Access Token** (le token temporaire expire après 24h)
4. Pour envoyer à un groupe WhatsApp, tu devras utiliser le **numéro de téléphone du destinataire** ou l'**ID du groupe** (les groupes via l'API Cloud nécessitent WhatsApp Business API On-Premises pour un envoi direct aux groupes ; via Cloud API, tu envoies à des numéros individuels).

**Note importante** : L'API WhatsApp Cloud de Meta ne supporte pas nativement l'envoi vers des groupes WhatsApp. Les alternatives sont :
- Utiliser **WhatsApp Business API On-Premises** (solution hébergée)
- Utiliser **Evolution API** (open-source, supporte les groupes)
- Envoyer aux **membres individuels** du groupe via Cloud API

---

## Étape 3 : Configurer les Variables d'Environnement N8N

Dans les paramètres de ton instance N8N, ajoute ces variables d'environnement :

```bash
# Dans ton fichier .env ou docker-compose.yml
N8N_CUSTOM_EXTENSIONS=""

# Variables personnalisées (accessible via $env dans les workflows)
TELEGRAM_BOT_TOKEN=ton_bot_token_ici
WHATSAPP_PHONE_NUMBER_ID=ton_phone_number_id
WHATSAPP_RECIPIENT_NUMBER=numero_destinataire_avec_indicatif
```

Le numéro destinataire doit être au format international sans le `+` (ex: `22901234567` pour le Bénin).

---

## Étape 4 : Importer le Workflow

1. Ouvre ton instance N8N dans le navigateur.
2. Va dans **Workflows** → **Import from File**.
3. Sélectionne le fichier `telegram-to-whatsapp-n8n-workflow.json`.
4. Le workflow apparaît avec tous les nœuds pré-configurés.

---

## Étape 5 : Configurer les Credentials dans N8N

### Credential Telegram
1. Dans N8N, va dans **Settings > Credentials > Add Credential**.
2. Choisis **Telegram API**.
3. Colle ton **Bot Token**.
4. Assigne ce credential au nœud **Telegram Trigger**.

### Credential WhatsApp (HTTP Header Auth)
1. Ajoute un nouveau credential de type **Header Auth**.
2. Configure :
   - **Name** : `Authorization`
   - **Value** : `Bearer TON_ACCESS_TOKEN_WHATSAPP`
3. Assigne ce credential à tous les nœuds **Send * to WhatsApp**.

---

## Étape 6 : Adapter les Nœuds

Après import, certains nœuds nécessitent des ajustements :

1. **Telegram Trigger** : Associe le credential Telegram créé à l'étape 5.
2. **Tous les nœuds HTTP "Send to WhatsApp"** : Associe le credential WhatsApp Header Auth.
3. **Si tu n'utilises pas les variables d'environnement** : Remplace `$env.WHATSAPP_PHONE_NUMBER_ID` et `$env.WHATSAPP_RECIPIENT_NUMBER` par tes valeurs en dur dans chaque nœud HTTP.

---

## Étape 7 : Activer et Tester

1. Clique sur **Activate** (toggle en haut à droite) pour démarrer le workflow.
2. Envoie un message test dans ton groupe Telegram.
3. Vérifie que le message arrive sur WhatsApp.
4. Teste chaque type de média : envoie une photo, un document, un audio et une vidéo.

---

## Dépannage

**Le Telegram Trigger ne se déclenche pas :**
- Vérifie que le bot est bien dans le groupe Telegram.
- Vérifie que le mode Privacy est désactivé.
- Vérifie que ton instance N8N est accessible depuis Internet (Telegram doit pouvoir envoyer des webhooks).

**Erreur 401 sur WhatsApp :**
- Ton Access Token a peut-être expiré. Génère un token permanent.

**Erreur 400 sur WhatsApp :**
- Vérifie le format du numéro destinataire (sans `+`, sans espaces).
- Vérifie que le numéro a accepté de recevoir des messages (template message requis pour le premier contact).

**Les médias ne s'envoient pas :**
- Les fichiers Telegram > 20 Mo ne sont pas téléchargeables via l'API Bot.
- Vérifie que ton serveur N8N a accès à `api.telegram.org` et `graph.facebook.com`.

---

## Structure du Workflow

| Nœud | Rôle |
|------|------|
| **Telegram Trigger** | Écoute tous les messages entrants |
| **Has Photo?** | Détecte si le message contient une photo |
| **Has Document?** | Détecte si le message contient un document |
| **Has Audio?** | Détecte si le message contient un audio/voix |
| **Has Video?** | Détecte si le message contient une vidéo |
| **Is Text Only?** | Détecte si c'est un message texte simple |
| **Get * File Path** | Récupère le chemin du fichier via l'API Telegram |
| **Send * to WhatsApp** | Envoie le contenu via WhatsApp Cloud API |

Chaque message relayé est préfixé par le nom de l'expéditeur Telegram pour identifier la source.
