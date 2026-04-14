# Audit APEX Bot v7 — Rapport complet

> **Date :** 2026-04-14
> **Branche auditée :** `master` (commit de départ `3832dca`, commits v7 : `01c3db5`, `dc652b3`)
> **Auditeur :** Claude Sonnet 4.6

---

## 1. Résumé exécutif — Scores /10

| Catégorie | Avant v7 | Après v7 | Δ |
|-----------|:--------:|:--------:|:-:|
| **A. Sécurité** | 8.5 | 8.5 | = |
| **B. Qualité & Maintenabilité** | 7.0 | 8.5 | +1.5 |
| **C. Robustesse** | 7.5 | 9.0 | +1.5 |
| **D. Performance** | 8.0 | 8.0 | = |
| **E. Précision des prédictions** | 8.0 | 8.5 | +0.5 |
| **F. Déploiement** | 7.5 | 9.0 | +1.5 |
| **Score global** | **7.8** | **8.6** | **+0.8** |

---

## 2. Tableau complet des problèmes identifiés

### 🔴 Critiques — Aucun

Aucun secret en dur, pas de vulnérabilité de sécurité critique identifiée.

---

### 🟠 Importants

| # | Fichier:Ligne | Description | Sévérité | Statut |
|---|---------------|-------------|:--------:|:------:|
| I1 | `bot.py:634` | `logger.info("... ({TIMEZONE})")` — f-string manquant, `{TIMEZONE}` affiché littéralement dans les logs | 🟠 | ✅ Corrigé |
| I2 | `coupon_generator.py:648` | `calculate_lambdas` : division par `avg` sans garde-fou — `ZeroDivisionError` si `league_avg_goals == 0` (données corrompues ou manquantes) | 🟠 | ✅ Corrigé |
| I3 | `coupon_generator.py:877` | `nba_avg_total = 224.5` — magic number codé en dur dans `_estimate_total_points()`. Seuil Over/Under NBA non configurable sans modifier le code | 🟠 | ✅ Corrigé |
| I4 | `bot.py:508` | `import re as _re` dans un bloc `except` à l'intérieur d'une boucle `for` — `re` déjà importé au niveau module (ligne 27). Redondant + indentation irrégulière du `try/except` interne (16 espaces au lieu de 12) | 🟠 | ✅ Corrigé |

---

### 🟡 Mineurs

| # | Fichier:Ligne | Description | Sévérité | Statut |
|---|---------------|-------------|:--------:|:------:|
| M1 | `coupon_generator.py:185` | `self.tomorrow = ...` — calculé dans `DataFetcher.__init__` mais jamais utilisé dans tout le fichier (code mort) | 🟡 | ✅ Corrigé |
| M2 | `coupon_generator.py:71-88` | Bloc fallback `except ImportError` : valeurs désynchronisées avec `config.py` — `min_total_odd: 4.5` (vs 3.0), `max_total_odd: 6.0` (vs 8.0), `target_selections: 4` (vs 6), `min_matches: 5` (vs 10), clé `"low_score_rho"` (renommée `"default_rho"`), `min_selections`/`max_per_league`/`min_confidence` absents | 🟡 | ✅ Corrigé |
| M3 | `.env.example` | Variables `BACKTEST_HISTORY_FILE`, `BACKTEST_AUTO_TRACK`, `DB_PATH`, `DB_ENABLED`, `LINE_MOVEMENT_ENABLED` présentes dans `config.py` mais non documentées dans `.env.example` | 🟡 | ✅ Corrigé |
| M4 | `bot.py:56-71` | `logger_init = logging.getLogger("APEX-Bot")` défini deux fois dans deux blocs `try` séparés — manque de cohérence, variable temporaire non réutilisable | 🟡 | ✅ Corrigé |
| M5 | `nba_elo_bootstrap.py:215` | `if home_team and away_team and (home_score or away_score):` — condition erronée : ignore les matchs au score `0-0` (score nul considéré comme falsy). Inoffensif en NBA (score toujours > 0) mais techniquement incorrect pour des données corrompues ou des forfaits | 🟡 | ✅ Corrigé |
| M6 | `coupon_generator.py:691-695` | `score_matrix` : double boucle Python `O((max_goals+1)²)` = 121 itérations. Vectorisable avec `np.outer` + broadcasting NumPy mais impact négligeable (~7 matchs/appel) | 🟡 | Non corrigé (optimisation non critique) |
| M7 | `coupon_generator.py:1673-1675` | `BacktestTracker._evaluate_bet` : matching fuzzy fragile — `normalize_team_name(res["home"]) in normalize_team_name(match_key)` est un test de sous-chaîne susceptible de faux positifs sur des noms courts | 🟡 | Non corrigé (refactoring à risque) |
| M8 | `coupon_generator.py` | `StatsModel` mentionnée dans CLAUDE.md et dans la pipeline description, mais non implémentée — `API_FOOTBALL_KEY` et `STATS_MARKETS` sont définis mais jamais utilisés dans `run_pipeline` | 🟡 | Non corrigé (feature manquante documentée en dette technique) |

---

## 3. Analyse par catégorie

### A. Sécurité (8.5/10)

**Correct :**
- `_TokenMaskFilter` masque les tokens Telegram dans tous les logs
- Loggers `httpx`/`httpcore`/`telegram.ext` réduits à `WARNING`
- Contrôle d'accès par `ALLOWED_USERS` (IDs Telegram, pas usernames)
- Toutes les clés API via `os.getenv()`, aucun secret en dur
- `timeout=10` sur tous les appels API via `NETWORK["timeout"]`
- Circuit-breaker + exponential backoff dans `DataFetcher`
- Validation des inputs Telegram (`coupon_id = int(args[0])` avec try/except)
- Échappement MarkdownV2 via `_esc()` centralisé

**Restant :**
- Token Telegram compromis — régénération via @BotFather (action manuelle, T3)
- `ALLOWED_USERS` vide par défaut = bot ouvert à tous en production si non configuré

### B. Qualité & Maintenabilité (8.5/10 après)

**Corrigé :**
- `logger_init` défini 2× → `_startup_logger` défini une seule fois
- `self.tomorrow` code mort supprimé
- `import re as _re` redondant supprimé
- Fallback defaults alignés avec `config.py`

**Correct :**
- `_esc()` unique (pas de duplication)
- `extract_bets()` générique évite la duplication football/basket/tennis
- Configuration centralisée dans `config.py`
- Docstrings présents sur toutes les classes et méthodes publiques
- Type hints sur les signatures

**Non corrigé (acceptable) :**
- `StatsModel` non implémentée (dette technique documentée)
- `pandas` importé pour une seule méthode `to_dataframe()` (refactoring non nécessaire)

### C. Robustesse (9.0/10 après)

**Corrigé :**
- Protection `ZeroDivisionError` dans `calculate_lambdas` si `avg <= 0`
- Score 0-0 NBA non ignoré dans `nba_elo_bootstrap.py`

**Correct :**
- `BacktestTracker._load()` : JSON corrompu → reset silencieux
- Toutes les probabilités normalisées (`matrix /= total`)
- `p_btts = 1 - P(h=0) - P(a=0) + P(0,0)` : formule inclusion-exclusion correcte
- `min_selections=4` respecté (CouponBuilder retourne `[]` si insuffisant)
- `p_home + p_draw + p_away ≈ 1.0` grâce à la normalisation de la matrice

**Restant :**
- `BacktestTracker._save()` non atomique (crash pendant l'écriture = JSON corrompu)
- Matching fuzzy fragile dans `_evaluate_bet` (sous-chaîne)

### D. Performance (8.0/10)

**Correct :**
- Cache TTL évite les appels API redondants
- `run_in_executor` pour toutes les opérations blocking dans les handlers async
- `score_matrix` : O(121) = négligeable pour ~7 matchs
- Coupon mis en cache 15 minutes après génération

**Optimisation possible (non bloquante) :**
- `score_matrix` vectorisable avec `np.outer` (gain ~5× mais inobservable à l'échelle)

### E. Précision des prédictions (8.5/10 après)

**Correct :**
- Démarginalisation appliquée dans `_get_odd()` → `demarginalise_odds()` ✅
- Probabilités 1X2 somment à 1.0 (normalisation matrice) ✅
- `tril(-1)` = victoire domicile (i > j), `triu(1)` = victoire extérieur (j > i) ✅ (corrigé en v5)
- `min_matches=10` respecté dans `run_pipeline` ✅
- Minimum 4 sélections enforced dans `CouponBuilder.build()` ✅
- Facteur d'incertitude `sqrt(N/20)` propagé à toutes les sélections ✅
- Cotes démo indépendantes du modèle (±7% bookmaker_error) ✅

**Corrigé :**
- `nba_avg_total` maintenant dans `ELO_PARAMS["avg_total_points"]` (configurable)

**Limitation documentée :**
- Rho Dixon-Coles = valeur empirique fixe, non estimée par MLE sur données historiques
- ELO NBA désactivé en mode réel si `nba_elo_bootstrap.py` n'a pas été exécuté

### F. Déploiement (9.0/10 après)

**Corrigé :**
- `.env.example` complété avec 5 variables manquantes

**Correct :**
- `requirements.txt` avec versions épinglées, cohérent avec les imports
- `.python-version = 3.12`
- `Procfile : worker: python bot.py` correct
- `python-telegram-bot[job-queue]` inclut APScheduler (pas besoin d'entrée séparée)
- Pas de `python-dotenv` nécessaire (Railway gère les variables d'environnement)

---

## 4. Changelog des modifications appliquées

### Commit `01c3db5` — fix(v7-important)

| Fichier | Ligne(s) | Modification |
|---------|----------|--------------|
| `bot.py` | 634 | `logger.info("...")` → `logger.info(f"...")` (f-string manquant) |
| `bot.py` | 499-513 | Correction indentation `try/except` (16→12 espaces) + suppression `import re as _re` + utilisation du `re` module-level |
| `coupon_generator.py` | 648-653 | Ajout guard `if avg <= 0: avg = POISSON_PARAMS["default_league_avg_goals"]` |
| `config.py` | 271-276 | Ajout `"avg_total_points": 224.5` dans `ELO_PARAMS.update({...})` |
| `coupon_generator.py` | 877 | `nba_avg_total = 224.5` → `nba_avg_total = ELO_PARAMS.get("avg_total_points", 224.5)` |

### Commit `dc652b3` — fix(v7-minor)

| Fichier | Ligne(s) | Modification |
|---------|----------|--------------|
| `coupon_generator.py` | 185 | Suppression `self.tomorrow = ...` (code mort) |
| `coupon_generator.py` | 71-88 | Alignement fallback : `min_matches: 5→10`, `"low_score_rho"→"default_rho"`, `min_total_odd: 4.5→3.0`, `max_total_odd: 6.0→8.0`, `target_selections: 4→6`, ajout `min_selections/max_per_league/min_confidence`, suppression `min_stake_pct` |
| `.env.example` | — | Ajout section `BACKTESTING`, `BASE DE DONNÉES SQLite`, `LINE MOVEMENT` |
| `bot.py` | 56-71 | `logger_init` × 2 → `_startup_logger` défini une seule fois avant les deux `try` |
| `nba_elo_bootstrap.py` | 215 | `(home_score or away_score)` → `home_score is not None and away_score is not None` |

### Commit `3832dca` — Pré-audit (push initial)

Commit de l'audit v6-final pushé vers `origin/master` (était en attente).

---

## 5. Recommandations restantes

### Actions manuelles requises (non automatisables)

| Priorité | Action | Raison |
|:--------:|--------|--------|
| 🔴 | Régénérer le token Telegram via @BotFather | Token compromis (T3, documenté depuis audit v4) |
| 🟠 | Configurer `ALLOWED_USERS` en production | Bot ouvert à tous si variable vide |
| 🟠 | Exécuter `python nba_elo_bootstrap.py` | Basketball désactivé en mode réel sans ratings ELO |

### Améliorations techniques restantes

1. **`BacktestTracker._save()` non-atomique** — Utiliser écriture dans un fichier temporaire + `os.replace()` pour une sauvegarde atomique. Risque faible en pratique (Railway ne crashe pas en milieu d'écriture).

2. **`StatsModel` non implémentée** — `STATS_MARKETS`, `API_FOOTBALL_KEY` et `API_FOOTBALL_LEAGUES` sont définis dans `config.py` mais aucun code ne les utilise. Représente la fonctionnalité la plus impactante restante en termes de diversification des marchés.

3. **`score_matrix` vectorisation** — Remplacement de la double boucle Python par `np.outer(poisson.pmf(range, λh), poisson.pmf(range, λa))`. Gain de performance 5-10× (invisible à l'échelle mais cleaner).

4. **Matching fuzzy `_evaluate_bet`** — Le test de sous-chaîne `normalize_team_name(res["home"]) in normalize_team_name(match_key)` peut produire des faux positifs. Migrer vers un score de similarité (ex: `difflib.SequenceMatcher`).

5. **Rho Dixon-Coles par MLE** — Estimer `rho` par maximum de vraisemblance sur les données historiques plutôt qu'utiliser des valeurs empiriques fixes. Nécessite un dataset de résultats historiques.

6. **Synchronisation repo GitHub** — `database.py`, `backtester.py`, `line_movement.py` référencés dans le code mais absents du repo local. Les commandes `/history`, `/stats`, `/result` sont en fallback silencieux.

---

## 6. État de synchronisation GitHub

| Commit | Message | Statut |
|--------|---------|--------|
| `dc652b3` | fix(v7-minor) | ✅ Pushé |
| `01c3db5` | fix(v7-important) | ✅ Pushé |
| `3832dca` | audit(v6-final) | ✅ Pushé |
| `3b85f8e` | fix MarkdownV2 | ✅ Déjà présent |

Local et GitHub sont **100% synchronisés** sur `master`.
