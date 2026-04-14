# APEX Bot — Instructions pour Claude

> **Dernière mise à jour :** 2026-04-14
> **Version :** 2.2 (audit v6 implémenté)

---

## 1. Vue d'ensemble du projet

**APEX** est un bot Telegram de prédiction sportive quotidien (football, basketball, tennis). Il analyse les matchs du jour avec des modèles statistiques, identifie les value bets par rapport aux cotes du marché, et envoie un coupon optimisé aux utilisateurs.

### Stack technique
- **Langage :** Python 3.9+ (3.12 recommandé — Railway déployé sur 3.12)
- **Bot framework :** python-telegram-bot v21+ (async, job-queue via APScheduler)
- **Calcul scientifique :** numpy, scipy (Poisson), pandas
- **HTTP :** requests (sync, exécuté dans `run_in_executor`)
- **Hébergement :** Railway (container Docker, variables d'environnement)
- **Base de données :** SQLite via `database.py` (persistance coupons et résultats)
- **Pas de frontend web** — backend-only Telegram

### Fichiers principaux

| Fichier | Rôle | Lignes |
|---------|------|--------|
| `bot.py` | Point d'entrée — handlers Telegram, 2 jobs planifiés, formatage MarkdownV2 | ~646 |
| `coupon_generator.py` | Moteur de prédiction — 8 classes, pipeline complet | ~1900 |
| `config.py` | Configuration centralisée — clés API, paramètres modèles, seuils | ~300 |
| `nba_elo_bootstrap.py` | Bootstrap ELO NBA — télécharge résultats BallDontLie, calcule ratings | ~220 |
| `database.py` | Persistance SQLite — historique coupons, résultats (sur GitHub) | — |
| `backtester.py` | Backtesting — suivi performance, rapports (sur GitHub) | — |

### Fichiers de documentation

| Fichier | Contenu |
|---------|---------|
| `SECURITY.md` | Règles de sécurité détaillées avec exemples de code |
| `PLAN_CORRECTION_V4.md` | Plan de correction issu de l'audit v4 global |
| `audit_betforge_v4_global.md` | Audit complet (code + GitHub + Railway) |
| `guide_configuration_railway.md` | Guide de configuration Railway |
| `GUIDE-CONFIGURATION-N8N.md` | Intégration n8n pour le pont Telegram → WhatsApp |

---

## 2. Architecture et flux de données

### Pipeline de génération du coupon (`run_pipeline`)

```
1. DataFetcher          → Récupère données (API réelles ou démo)
       ↓
2. PoissonModel         → Prédit football (lambda, matrice scores, 1X2, Over/Under)
   EloModel             → Prédit basketball (ratings ELO, forme récente)
   TennisModel          → Prédit tennis (ELO-like + surface + forme + H2H)
       ↓
3. StatsModel           → Marchés stats (corners, fautes, cartons, tirs, passes, touches)
       ↓
4. ValueBetSelector     → Filtre les value bets (edge ≥ 5% vs cotes bookmaker)
       ↓
5. CouponBuilder        → Assemble le coupon optimal (4-10 sélections, cote 3.0-8.0)
       ↓
6. BacktestTracker      → Sauvegarde dans l'historique
       ↓
7. format_coupon_telegram() → Formatage MarkdownV2 pour Telegram
```

### Classes du moteur (`coupon_generator.py`)

| Classe | Responsabilité |
|--------|---------------|
| `TTLCache` | Cache en mémoire avec TTL par clé (évite les appels API redondants) |
| `DataFetcher` | Récupération multi-sources avec cache, circuit-breaker, exponential backoff |
| `PoissonModel` | Modèle football : distribution de Poisson avec correction Dixon-Coles (rho) |
| `EloModel` | Modèle basketball : système ELO + bonus domicile + forme récente |
| `TennisModel` | Modèle tennis : ELO-like + pondération surface + forme + H2H + fatigue |
| `ValueBetSelector` | Sélection des value bets : compare P(modèle) vs P(implicite bookmaker) |
| `CouponBuilder` | Assemblage du coupon : optimise la cote totale, diversifie sports/types |
| `BacktestTracker` | Suivi historique et calcul de performance |

### APIs externes utilisées

| API | Sport | Données | Limites |
|-----|-------|---------|---------|
| football-data.org | Football | Fixtures, standings | 10 req/min (gratuit) |
| the-odds-api.com | Multi | Cotes bookmaker réelles | 500 req/mois (gratuit) |
| TheSportsDB | Multi | Événements, infos équipes | Illimité (tier 1 public) |
| api-football (RapidAPI) | Football | Stats avancées (corners, tirs) | 100 req/jour (gratuit) |
| BallDontLie | Basketball | Stats NBA | Limites variables |

### Mode démo vs mode réel

- **Mode démo** (`DEMO_MODE=true`) : Données simulées réalistes, pas d'appel API. Les cotes démo sont générées de manière **indépendante** du modèle (pas de raisonnement circulaire).
- **Mode réel** (`DEMO_MODE=false`) : Appels API en temps réel avec fallback démo si aucun match trouvé.
- Le mode est synchronisé entre `bot.py` et `coupon_generator.py` au démarrage.

---

## 3. Commandes Telegram

| Commande | Handler | Description |
|----------|---------|-------------|
| `/start` | `cmd_start` | Message de bienvenue + liste des commandes |
| `/coupon` | `cmd_coupon` | Génère et envoie le coupon du jour (message d'attente + thread séparé) |
| `/status` | `cmd_status` | Statut du bot, mode, heure du prochain envoi auto |
| `/aide` | `cmd_aide` | Explication du fonctionnement du modèle |
| `/history` | `cmd_history` | Historique des 30 derniers coupons (nécessite `database.py`) |
| `/stats` | `cmd_stats` | Rapport de performance backtesting (nécessite `backtester.py`) |
| `/result` | `cmd_result` | Enregistrer le résultat d'un coupon (`/result <id> <won\|lost\|void>`) |

Toutes les commandes sont protégées par le décorateur `@_check_access` (voir section sécurité).

### Envoi automatique quotidien

- Configuré via `BOT_SEND_HOUR` et `BOT_SEND_MINUTE` (défaut : 08h00)
- Timezone configurable via `TIMEZONE` (défaut : `Europe/Paris`)
- Envoie au `TELEGRAM_CHAT_ID` configuré
- Fallback texte brut si MarkdownV2 échoue

---

## 4. Règles de sécurité — OBLIGATOIRES

> Référence complète : `SECURITY.md`

### 4.1. Secrets & Clés API
- **JAMAIS** de clé API, token ou mot de passe en dur → toujours `os.getenv()`
- `TELEGRAM_TOKEN` sans valeur par défaut → crash explicite si absent
- Secrets Railway dans **Settings > Variables** uniquement, jamais dans `railway.toml`
- Vérifier qu'aucun secret n'apparaît dans les logs (le `_TokenMaskFilter` masque les tokens Telegram)

### 4.2. Inputs utilisateur Telegram
- Valider et typer chaque argument de commande Telegram
- Contrôle d'accès par `update.effective_user.id` (entier), **JAMAIS** par username
- Échapper le contenu utilisateur avec `html.escape()` avant `reply_text(parse_mode="HTML")`
- Pour MarkdownV2 : utiliser `_esc()` (défini dans `bot.py`) pour échapper les caractères spéciaux
- Si BDD future : parameterized queries obligatoires, jamais de concaténation

### 4.3. Appels API externes
- HTTPS uniquement
- Clés API dans les headers, pas dans les URLs (exception : `the-odds-api` qui exige `apiKey` en query param)
- `timeout=10` minimum sur chaque `requests.get/post` (configuré dans `NETWORK["timeout"]`)
- Toujours `try/except` avec logging serveur, message générique à l'utilisateur
- Exponential backoff sur les retries (configuré dans `NETWORK`)
- Circuit-breaker intégré dans `DataFetcher` (API en panne → ignorée 5 min)

### 4.4. Code interdit
```python
# JAMAIS dans ce projet :
eval()  exec()  __import__(user_input)  os.system(user_input)  subprocess.call(..., shell=True)
```

### 4.5. Protection des logs
- Le `_TokenMaskFilter` (dans `bot.py`) masque automatiquement tout pattern `\d{8,}:[A-Za-z0-9_-]{30,}` dans les logs
- Les loggers `httpx`, `httpcore`, `telegram.ext` sont réduits à `WARNING` pour éviter les fuites de token dans les URLs de polling
- Ne jamais logger de secrets, clés API, ou mots de passe
- Niveau de log : `DEBUG` en local, `INFO/WARNING` en production

### 4.6. Dépendances
- Vérifier chaque package ajouté à `requirements.txt`
- `pip audit -r requirements.txt` avant déploiement
- Versions épinglées dans `requirements.txt`

### 4.7. Checklist pré-commit
Avant chaque modification, vérifier :
1. Pas de secret en dur dans le code modifié
2. Tout nouveau secret est lu via `os.getenv()`
3. Les inputs utilisateur sont validés avant utilisation
4. Les appels API ont un `timeout` et une gestion d'erreur
5. Les messages d'erreur Telegram ne contiennent pas de stack trace
6. `.env` est bien dans `.gitignore`

---

## 5. Conventions de code

### 5.1. Style Python
- **PEP 8** strict (indentation 4 espaces, lignes ≤ 120 caractères)
- **Type hints** sur toutes les signatures de fonctions et méthodes
- **Docstrings** obligatoires sur chaque classe et fonction publique (format Google style)
- Commentaires en français pour les sections métier, en anglais acceptable pour le code technique générique
- Encoding : `# -*- coding: utf-8 -*-` en en-tête de chaque fichier

### 5.2. Nommage
- Classes : `PascalCase` (`PoissonModel`, `DataFetcher`, `TTLCache`)
- Fonctions/méthodes : `snake_case` (`calculate_lambdas`, `fetch_odds`)
- Constantes : `UPPER_SNAKE_CASE` (`DEMO_MODE`, `API_KEYS`, `POISSON_PARAMS`)
- Variables privées : préfixe `_` (`_cache`, `_rng`, `_broken_apis`)
- Handlers Telegram : préfixe `cmd_` (`cmd_start`, `cmd_coupon`)
- Fonctions utilitaires Telegram : préfixe `_` si internes (`_esc`, `_check_access`)

### 5.3. Patterns obligatoires

**Configuration centralisée :**
```python
# Toujours lire depuis config.py, jamais de valeur magique dans le code
from config import VALUE_BETTING
threshold = VALUE_BETTING["min_value"]  # ✅
threshold = 0.05                        # ❌ Valeur magique
```

**Gestion d'erreurs API :**
```python
try:
    resp = self.session.get(url, headers=headers, timeout=NETWORK["timeout"])
    resp.raise_for_status()
    data = resp.json()
except (requests.RequestException, ValueError) as e:
    logger.error(f"Erreur API {api_name}: {e}", exc_info=True)
    return None  # Fallback géré par l'appelant
```

**Messages Telegram avec fallback :**
```python
try:
    await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.MARKDOWN_V2)
except Exception:
    # Fallback texte brut si MarkdownV2 échoue
    plain = re.sub(r'\\([_*\\[\\]()~`>#+=|{}.!\\-])', r'\\1', chunk)
    await context.bot.send_message(chat_id=chat_id, text=plain)
```

**Exécution blocking dans async :**
```python
# Toujours run_in_executor pour les opérations blocking (API calls, calculs lourds)
loop = asyncio.get_running_loop()
result = await loop.run_in_executor(None, blocking_function)
```

### 5.4. Anti-patterns interdits
- ❌ `asyncio.get_event_loop()` → utiliser `asyncio.get_running_loop()`
- ❌ Valeurs magiques dans le code → utiliser `config.py`
- ❌ `print()` pour le debug → utiliser `logger.debug/info/warning/error`
- ❌ `except Exception: pass` → toujours logger l'erreur
- ❌ Duplication de fonctions utilitaires → factoriser dans un seul endroit
- ❌ Import circulaire entre modules → architecture en couches (config → engine → bot)

### 5.5. Structure des imports
```python
# 1. Bibliothèques standard
import os, sys, logging, asyncio, re, json, math, functools
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# 2. Bibliothèques tierces
import numpy as np
from scipy.stats import poisson
import pandas as pd
import requests

# 3. Modules locaux
from config import API_KEYS, ENDPOINTS, POISSON_PARAMS, ...
from coupon_generator import run_pipeline
```

---

## 6. Variables d'environnement

| Variable | Obligatoire | Défaut | Description |
|----------|:-----------:|--------|-------------|
| `TELEGRAM_TOKEN` | ✅ | — | Token du bot (via @BotFather). Crash si absent. |
| `TELEGRAM_CHAT_ID` | ⚠️ | `""` | ID du chat/canal pour l'envoi automatique. Sans lui, pas d'envoi auto. |
| `FOOTBALL_DATA_KEY` | Non | `""` | Clé API football-data.org |
| `ODDS_API_KEY` | Non | `""` | Clé API the-odds-api.com |
| `API_FOOTBALL_KEY` | Non | `""` | Clé API api-football (RapidAPI) |
| `DEMO_MODE` | Non | `false` | `true` pour données simulées, `false` pour API réelles |
| `BOT_SEND_HOUR` | Non | `8` | Heure d'envoi automatique (0-23) |
| `BOT_SEND_MINUTE` | Non | `0` | Minute d'envoi automatique (0-59) |
| `TIMEZONE` | Non | `Europe/Paris` | Timezone pour le job planifié |
| `ALLOWED_USERS` | Non | `""` | Liste d'IDs Telegram autorisés (séparés par `,`). Vide = ouvert à tous. |
| `BALLDONTLIE_API_KEY` | Non | `""` | Clé API BallDontLie (optionnel — tier public sans clé) |
| `ELO_RATINGS_FILE` | Non | `nba_elo_ratings.json` | Chemin du fichier de ratings ELO NBA pré-entraînés |

---

## 7. Workflow de développement

### 7.1. Process Git
1. Créer une branche feature depuis `main` : `git checkout -b feature/nom-feature`
2. Développer avec des commits atomiques et des messages descriptifs en français
3. Tester localement en mode démo (`DEMO_MODE=true`)
4. Vérifier la checklist pré-commit (section 4.7)
5. Push et créer une Pull Request
6. Merge dans `main` après review

### 7.2. Format des commits
```
<type>: <description courte en français>

Types : fix, feat, refactor, docs, security, test, config
Exemples :
  fix: corriger inversion p_home/p_away dans PoissonModel
  feat: ajouter marchés stats (corners, fautes, cartons)
  security: masquer token Telegram dans les logs
  refactor: supprimer duplication _esc/esc dans bot.py
```

### 7.3. Tests
```bash
# Lancer les tests
pytest -v

# Tests async (bot.py)
pytest -v --asyncio-mode=auto

# Audit de sécurité des dépendances
pip audit -r requirements.txt
```

### 7.4. Déploiement Railway
1. Push sur `main` → déploiement automatique via Railway
2. Vérifier les variables d'environnement dans **Settings > Variables**
3. Consulter les logs Railway pour confirmer le démarrage
4. Tester avec `/status` sur Telegram

### 7.5. Checklist avant déploiement production
- [ ] `pip audit -r requirements.txt` — pas de vulnérabilité critique
- [ ] `grep -rn "token\|key\|secret\|password" --include="*.py"` — vérifier qu'aucun secret n'est en dur
- [ ] `DEMO_MODE` configuré correctement (`false` en production)
- [ ] `ALLOWED_USERS` configuré (ne pas laisser le bot ouvert en production)
- [ ] Les logs ne contiennent pas de traces de secrets
- [ ] Le `TELEGRAM_CHAT_ID` pointe vers le bon canal

---

## 8. Paramètres des modèles (référence rapide)

### Poisson (Football)
| Paramètre | Valeur | Rôle |
|-----------|--------|------|
| `home_advantage` | 1.1 | Multiplicateur buts domicile |
| `max_goals` | 10 | Taille matrice de scores |
| `goals_threshold` | 2.5 | Seuil Over/Under |
| `min_matches` | 5 | Minimum matchs pour force d'équipe |
| `low_score_rho` | -0.13 | Correction dépendance scores faibles (Dixon-Coles simplifié) |
| `default_league_avg_goals` | 2.65 | Moyenne buts par défaut (calculée dynamiquement si standings dispo) |

### ELO (Basketball)
| Paramètre | Valeur | Rôle |
|-----------|--------|------|
| `initial_rating` | 1500 | ELO de départ |
| `k_factor` | 20 | Sensibilité aux mises à jour |
| `home_bonus` | 50 | Bonus domicile en points ELO |

### Tennis
| Paramètre | Valeur | Rôle |
|-----------|--------|------|
| `surface_weight` | 0.15 | Poids performance sur surface |
| `form_weight` | 0.08 | Poids forme récente |
| `h2h_weight` | 0.10 | Poids head-to-head historique |

### Value Betting
| Paramètre | Valeur | Rôle |
|-----------|--------|------|
| `min_value` | 0.05 | Edge minimum requis (5%) |
| `min_odd` / `max_odd` | 1.30 / 4.00 | Fourchette de cotes acceptées par sélection |
| `target_selections` | 6 | Nombre cible de sélections |
| `min_selections` / `max_selections` | 4 / 10 | Bornes du nombre de sélections |
| `target_total_odd` | 5.0 | Cote totale cible |
| `min_total_odd` / `max_total_odd` | 3.0 / 8.0 | Fourchette cote totale (max réduit de 15 à 8 après audit v4) |

### Kelly Criterion
| Paramètre | Valeur | Rôle |
|-----------|--------|------|
| `fraction` | 0.25 | Quart de Kelly (réduit la variance) |
| `max_stake_pct` | 5.0 | Cap de mise à 5% du bankroll |

---

## 9. Roadmap & dette technique

### Corrections implémentées (PLAN_CORRECTION_V4.md + audits v5 + v6)
- [x] T1 : Token masqué dans les logs (`_TokenMaskFilter`, exc_info couvert — SEC-1 v6)
- [x] T2 : Contrôle d'accès `ALLOWED_USERS` (warning démarrage — SEC-2/OBS-2 v6)
- [ ] T3 : Régénérer le token Telegram (l'ancien est compromis — **action manuelle requise**)
- [x] T4 : Correction inversion `p_home`/`p_away` dans `PoissonModel`
- [x] T5 : Enregistrement des 7 commandes dans `post_init`
- [x] T7 : Suppression duplication `_esc`/`esc`
- [x] T9 : Suppression `bot_patched.py` (fichier vide — audit v5)
- [x] R1 : Matching fuzzy noms d'équipes (`normalize_team_name`, `_lookup_odds`, `TEAM_ALIASES`)
- [x] R2 : Bootstrap ELO NBA (`nba_elo_bootstrap.py`, `EloModel._load_pretrained_ratings`)
- [x] R3 : Rho par ligue (`POISSON_PARAMS["league_rho"]`, `get_rho_for_league()`)
- [x] R4 : Backtesting résultats (`fetch_match_results`, `resolve_results`, job 01h00)
- [x] R5 : Facteur d'incertitude confiance (`sqrt(min(N,20)/20)`)
- [x] R6 : Diversification coupon (`_is_diversified`, `max_per_league=3`)
- [x] R7 : Thread-safety `PoissonModel` (paramètre `league_avg_goals` à `calculate_lambdas`)
- [x] R8 : Marché Over/Under basketball (`_estimate_total_points`)
- [x] R9 : Synchronisation config GitHub (`STATS_MARKETS`, `LEAGUE_HOME_ADVANTAGE`, etc.)
- [x] v6-SEC-3 : Username supprimé du log d'accès refusé
- [x] v6-ROB-1/MET-1 : `home_advantage` par ligue injecté dans les fixtures
- [x] v6-ROB-2 : Sauvegarde atomique `BacktestTracker` (write-tmp + replace)
- [x] v6-ROB-3 : `TTLCache` thread-safe via `threading.Lock`
- [x] v6-ROB-4 : Fuzzy matching étendu aux deux équipes dans `_evaluate_bet`
- [x] v6-ROB-6/PERF-3 : Fetch odds et fixtures parallélisés (ThreadPoolExecutor)
- [x] v6-MET-2 : Fallback `LEAGUE_AVG_GOALS` quand standings vides
- [x] v6-MET-4 : Seuil Over/Under NBA adaptatif (moyenne modèle + seuil naturel)
- [x] v6-MET-6 : `ranking_to_elo` continuation lisse au-delà du rang 500
- [x] v6-MET-7 : Limite 1 pari par match dans `select_best_bets`
- [x] v6-OBS-1 : Health check HTTP pour Railway (port `$PORT`)
- [x] v6-QUA-1..12 : Dead code, imports inutiles, docstrings, `_stars()` module-level

### Améliorations restantes
1. **Bootstrap NBA** : Lancer `python nba_elo_bootstrap.py` pour activer le basketball en mode réel
2. **Enrichissement données réelles tennis** : ajouter aces_avg, service_games, tiebreak_pct
3. **Backtesting marchés stats** : étendre le backtester pour suivre corners/fautes/etc.
4. **Marchés additionnels** : double chance football, score exact, mi-temps/fin
5. **Sync repo GitHub** : aligner `database.py`, `backtester.py`, `line_movement.py`
6. **Rho MLE** : estimer rho par MLE sur données historiques (actuellement valeurs empiriques)

### Dette technique résiduelle
- Le token Telegram compromis doit être régénéré via @BotFather (T3, action manuelle)
- Désynchronisation entre copie locale et repo GitHub (`database.py`, `backtester.py` manquants en local)
- Railway en trial limité — nécessite un upgrade pour la production
- Tests dev : `pip install -r requirements-dev.txt` (séparé de requirements.txt — v6 DEV-2)

---

## 10. Notes importantes pour Claude

### Quand tu modifies du code
1. **Toujours** lire le fichier concerné en entier avant de modifier
2. **Respecter** les conventions de nommage existantes (section 5.2)
3. **Ne jamais** introduire de secret en dur, même pour tester
4. **Tester** mentalement que le MarkdownV2 Telegram est correct (les caractères `_*[]()~>#+-=|{}.!` doivent être échappés avec `\`)
5. **Vérifier** que toute nouvelle variable d'environnement est documentée dans cette section et dans `.env.example`

### Quand tu ajoutes une fonctionnalité
1. Les paramètres configurables vont dans `config.py`, pas en dur dans le code
2. Les nouveaux handlers Telegram doivent avoir le décorateur `@_check_access`
3. Les nouvelles commandes doivent être ajoutées dans `post_init` (liste `BotCommand`)
4. Les appels API doivent passer par `DataFetcher._get()` (cache + retry + circuit-breaker)
5. Les messages longs doivent utiliser `send_long_message()` (découpage + fallback)

### Quand tu débugues
1. Vérifier d'abord si le mode démo est actif (`DEMO_MODE`)
2. Vérifier les logs pour les erreurs API (circuit-breaker, timeouts)
3. Vérifier que les clés API sont configurées et non vides
4. En cas de problème MarkdownV2 : le fallback texte brut doit toujours fonctionner
5. Les fichiers `audit_betforge_v*.md` contiennent l'historique complet des bugs trouvés et corrigés
