# Règles de sécurité — BetForge / APEX Bot

> **Stack :** Python 3.10+ · python-telegram-bot · Railway
> **Architecture :** Bot Telegram backend-only, pas de BDD, pas de frontend web
> **Dernière mise à jour :** 2026-04-12

---

## 1. Secrets & Clés API

### Règles absolues
- **JAMAIS** de clé API, token Telegram, ou mot de passe en dur dans le code source
- **TOUS** les secrets sont lus via `os.getenv()` (comme déjà fait dans `config.py`)
- Le fichier `.env` est dans `.gitignore` **AVANT** le premier commit (✅ déjà en place)
- Un fichier `.env.example` avec des valeurs vides documente les variables requises (✅ déjà en place)

### Application au projet
```python
# ✅ CORRECT — ce que fait déjà config.py
API_KEYS = {
    "football_data": os.getenv("FOOTBALL_DATA_KEY", ""),
    "odds_api":      os.getenv("ODDS_API_KEY", ""),
}
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# ❌ INTERDIT — ne jamais faire ça
TELEGRAM_TOKEN = "123456:ABC-DEF..."
API_KEYS = {"football_data": "ma_vraie_cle_ici"}
```

### Valeurs par défaut
- Les clés API optionnelles peuvent avoir `""` comme fallback (mode démo)
- Le `TELEGRAM_TOKEN` ne doit **JAMAIS** avoir de valeur par défaut → crash explicite si absent
- Valider au démarrage que les secrets critiques sont présents :
```python
if not os.getenv("TELEGRAM_TOKEN"):
    raise RuntimeError("TELEGRAM_TOKEN manquant — configurez-le dans .env ou Railway")
```

### Railway
- Tous les secrets sont configurés dans **Settings > Variables** du service Railway
- Ne jamais stocker de secrets dans `railway.toml`
- Utiliser les **Shared Variables** si plusieurs services partagent des clés

---

## 2. Validation des inputs utilisateur (Telegram)

### Commandes et messages
- **Valider et typer** chaque argument reçu via les commandes Telegram
- Ne jamais utiliser directement `update.message.text` dans une opération sensible sans validation
- Utiliser des listes blanches (allowlists) pour les valeurs attendues

```python
# ✅ CORRECT — validation stricte
SPORTS_VALIDES = {"football", "basketball", "tennis"}
sport = user_input.lower().strip()
if sport not in SPORTS_VALIDES:
    await update.message.reply_text("Sport non supporté.")
    return

# ❌ INTERDIT — input brut dans une logique métier
sport = update.message.text.split()[1]  # pas de validation
```

### Contrôle d'accès
- Utiliser `ALLOWED_USERS` (variable d'environnement) pour restreindre l'accès au bot
- Vérifier `update.effective_user.id` (entier, non falsifiable) et **JAMAIS** le username
```python
# ✅ CORRECT
allowed = os.getenv("ALLOWED_USERS", "").split(",")
allowed_ids = [int(uid.strip()) for uid in allowed if uid.strip()]
if allowed_ids and update.effective_user.id not in allowed_ids:
    return  # silencieux ou message d'erreur

# ❌ INTERDIT — username falsifiable
if update.effective_user.username != "admin":
```

### Protection contre l'injection
- Si un jour une BDD est ajoutée : **parameterized queries obligatoires**
- Ne jamais construire de chaînes dynamiques avec du contenu utilisateur pour des appels API
- Échapper le contenu utilisateur avant de l'inclure dans des messages Telegram (HTML/Markdown)
```python
# ✅ CORRECT — échapper le HTML dans les réponses Telegram
from html import escape
await update.message.reply_text(
    f"Résultat pour : {escape(user_input)}",
    parse_mode="HTML"
)
```

---

## 3. Sécurité des appels API externes

### Requêtes HTTP
- **HTTPS obligatoire** pour tous les appels API (✅ déjà le cas dans `config.py`)
- Ne jamais mettre de clé API dans l'URL en paramètre GET si l'API supporte les headers
```python
# ✅ CORRECT — clé dans le header
headers = {"X-Auth-Token": API_KEYS["football_data"]}
response = requests.get(url, headers=headers, timeout=10)

# ❌ INTERDIT — clé dans l'URL (visible dans les logs)
response = requests.get(f"{url}?apiKey={API_KEYS['football_data']}")
```

### Timeouts et résilience
- **Toujours** spécifier un `timeout` sur les requêtes HTTP (10-30 secondes)
- Gérer les exceptions réseau (`requests.exceptions.RequestException`)
- Ne jamais faire confiance aux données retournées par une API externe : valider la structure
```python
# ✅ CORRECT
try:
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "matches" not in data:
        raise ValueError("Réponse API inattendue")
except (requests.RequestException, ValueError) as e:
    logger.error(f"Erreur API: {e}")
    return None
```

### Rate limiting
- Respecter les limites des APIs gratuites (10 req/min football-data, 500 req/mois odds-api)
- Implémenter un mécanisme de cache ou de throttling pour éviter les bans
- Logger les appels API pour monitorer la consommation

---

## 4. Gestion des erreurs et logs

### Erreurs
- Ne **jamais** exposer de stack trace ou de détails techniques aux utilisateurs Telegram
- Logger les erreurs complètes côté serveur, renvoyer un message générique à l'utilisateur
```python
# ✅ CORRECT
except Exception as e:
    logger.error(f"Erreur dans /coupon: {e}", exc_info=True)
    await update.message.reply_text("Une erreur est survenue. Réessayez plus tard.")

# ❌ INTERDIT
except Exception as e:
    await update.message.reply_text(f"ERREUR: {e}\n{traceback.format_exc()}")
```

### Logs
- Ne **jamais** logger de secrets (tokens, clés API, mots de passe)
- Configurer le niveau de log approprié : `DEBUG` en local, `INFO` ou `WARNING` en production
- Les logs Railway sont éphémères — envisager un service externe si l'historique est important

---

## 5. Dépendances & Packages

### Règles
- Vérifier chaque package dans `requirements.txt` avant de commit
- Lancer `pip audit` régulièrement pour détecter les vulnérabilités connues
- Se méfier des packages peu connus ou très récents suggérés par l'IA
- Épingler les versions dans `requirements.txt` (✅ déjà fait)

### Interdictions absolues
```python
# ❌ JAMAIS dans le code de production
eval(user_input)
exec(user_input)
__import__(user_input)
os.system(user_input)
subprocess.call(user_input, shell=True)
```

### Audit
```bash
# Installer pip-audit
pip install pip-audit

# Scanner les dépendances
pip-audit -r requirements.txt
```

---

## 6. Déploiement Railway

### Variables d'environnement
- Configurées **uniquement** dans le dashboard Railway (Settings > Variables)
- Le fichier `.env` n'est **PAS** dans le repo Git (✅ déjà dans `.gitignore`)
- Utiliser des noms clairs et cohérents (`TELEGRAM_TOKEN`, pas `TK` ou `TOKEN`)

### Configuration Railway
- Ne pas stocker de secrets dans `railway.toml` — uniquement la config de build/deploy
- Activer les **deploy previews** pour tester avant la production si disponible
- Vérifier que le healthcheck ne retourne pas d'informations sensibles

### Vérifications avant chaque déploiement
1. `pip audit -r requirements.txt` — pas de vulnérabilité critique
2. Aucun secret en dur dans le code (`grep -rn "token\|key\|secret\|password" --include="*.py"` et vérifier)
3. Le mode `DEMO_MODE` est bien configuré selon l'intention (true/false)
4. Les logs ne contiennent pas de traces de secrets

---

## 7. Fichiers sensibles à protéger

### Déjà dans .gitignore (vérifier) :
```
.env
.env.*
coupon_history.json
*.log
```

### À ne jamais committer :
- Fichiers `.env` (même renommés)
- Fichiers de données utilisateur (`coupon_history.json`)
- Exports de base de données ou dumps
- Clés SSH ou certificats

---

## 8. Checklist pré-commit

Avant chaque commit, vérifier :

- [ ] Aucune clé API ou token en dur dans le code modifié
- [ ] Tout nouveau secret est lu via `os.getenv()`
- [ ] Les inputs utilisateur sont validés avant utilisation
- [ ] Les appels API ont un `timeout` et une gestion d'erreur
- [ ] Les messages d'erreur Telegram ne contiennent pas de stack trace
- [ ] `pip audit` ne remonte pas de vulnérabilité critique
- [ ] `.env` est bien dans `.gitignore`

---

## Sections non applicables (pour référence future)

Les règles suivantes ne sont **pas encore pertinentes** mais devront être activées si le projet évolue :

| Évolution prévue | Règles à activer |
|---|---|
| **Ajout d'une BDD** (Supabase, SQLite, etc.) | RLS, parameterized queries, policies restrictives, service key backend-only |
| **Ajout d'un frontend web** (React, Next.js, etc.) | CORS restreint, CSP headers, préfixes variables (`NEXT_PUBLIC_`), pas de `dangerouslySetInnerHTML`, cookies Secure/HttpOnly/SameSite |
| **Authentification avancée** | JWT côté serveur, refresh tokens (15min/7j), invalidation session au logout |
| **Mise en place d'un domaine** | HTTPS obligatoire, headers de sécurité (CSP, X-Frame-Options, HSTS) |
