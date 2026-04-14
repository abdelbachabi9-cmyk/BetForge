# Audit APEX Bot — v6
> **Date** : 2026-04-14  
> **Auditeur** : Claude Sonnet 4.6  
> **Périmètre** : `bot.py`, `coupon_generator.py`, `config.py`, `nba_elo_bootstrap.py`, `requirements.txt`, `Procfile`, `.python-version`  
> **Base** : Post audit v5 + corrections Python 3.12

---

## 1. Résumé exécutif

| Catégorie | Score /10 | Tendance vs v5 |
|-----------|:---------:|---------------|
| **SEC** — Sécurité | 7/10 | ↑ (masquage token, contrôle accès) |
| **QUA** — Qualité code | 5/10 | → (dead code, imports inutiles) |
| **ROB** — Robustesse | 6/10 | ↑ (circuit-breaker, backoff) |
| **PERF** — Performance | 6/10 | → (API séquentielles) |
| **MET** — Modèles/Métier | 5/10 | → (config non utilisée, StatsModel absent) |
| **ARC** — Architecture | 6/10 | ↑ (factorisation, thread-safety) |
| **OBS** — Observabilité | 4/10 | → (pas de health check, log cassé) |
| **DEV** — Déploiement | 6/10 | → (deps prod/test mélangées) |

**Score global estimé : 5,6/10**

Les audits précédents ont bien corrigé les bugs fonctionnels critiques (inversion triu/tril, raisonnement circulaire, thread-safety PoissonModel). L'audit v6 révèle principalement : du **dead code accumulé**, une **configuration incomplètement câblée** (plusieurs paramètres config.py non consommés), et un **bug de log silencieux** (f-string manquant).

---

## 2. Top 5 des corrections prioritaires

| Priorité | Code | Titre | Fichier | Effort |
|----------|------|-------|---------|--------|
| 🔴 1 | QUA-9 | f-string manquant → TIMEZONE non interpolé dans le log | `bot.py:634` | 1 min |
| 🔴 2 | MET-8 | `LEAGUE_HOME_ADVANTAGE` défini mais jamais câblé dans `PoissonModel` | `config.py`, `coupon_generator.py` | 30 min |
| 🟠 3 | SEC-4 | `_TokenMaskFilter` ne masque pas `exc_info` (tracebacks) | `bot.py:91-108` | 15 min |
| 🟠 4 | QUA-12 | `normalize_team_name(" united")` casse "Manchester United" → "manchester" | `coupon_generator.py:103` | 10 min |
| 🟠 5 | ROB-1 | Division par zéro possible dans `calculate_lambdas` si `avg == 0` | `coupon_generator.py:650` | 5 min |

---

## 3. Problèmes détaillés

### 3.1 SÉCURITÉ

---

### [SEC-1] `_TokenMaskFilter` ne masque pas les tracebacks d'exceptions
**Fichier** : `bot.py:91-108`  
**Sévérité** : 🟠 Important  
**Problème** : Le filtre masque `record.msg` et `record.args` mais pas `record.exc_info` ni `record.exc_text`. Si une exception contient le token Telegram dans sa trace (ex : `InvalidToken`), il apparaîtra en clair dans les logs.  
**Impact** : Fuite potentielle du token Telegram dans les logs Railway si une exception survient lors de l'authentification.  
**Correction recommandée** :
```python
def filter(self, record: logging.LogRecord) -> bool:
    # ... masquage existant ...
    # Masquer aussi dans le texte de l'exception formatée
    if record.exc_text and isinstance(record.exc_text, str):
        record.exc_text = _TOKEN_PATTERN.sub("***MASKED***", record.exc_text)
    # Forcer le formatage de exc_info pour pouvoir le masquer
    if record.exc_info:
        if not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = _TOKEN_PATTERN.sub("***MASKED***", record.exc_text)
        record.exc_info = None  # Éviter le re-formatage
    return True
```

---

### [SEC-2] ALLOWED_USERS vide = bot ouvert à tous (rappel de sécurité opérationnel)
**Fichier** : `config.py:250-253`  
**Sévérité** : 🟡 Mineur (documenté dans CLAUDE.md)  
**Problème** : En l'absence de `ALLOWED_USERS`, tout utilisateur Telegram peut accéder aux commandes. Le bot génère aussi des coûts API (odds-api : 500 req/mois).  
**Impact** : Épuisement du quota API si le bot est partagé publiquement ou découvert.  
**Correction recommandée** : Documenter dans le README que `ALLOWED_USERS` doit être configuré avant déploiement. Ajouter un warning au démarrage :
```python
if not ALLOWED_USERS:
    logger.warning("⚠️ ALLOWED_USERS non défini — bot ouvert à tous les utilisateurs Telegram")
```

---

### [SEC-3] Username Telegram loggé dans les avertissements d'accès refusé
**Fichier** : `bot.py:151-152`  
**Sévérité** : 🟡 Mineur  
**Problème** : `@{update.effective_user.username}` est inclus dans les logs de sécurité. Les usernames Telegram peuvent être des données personnelles (RGPD).  
**Impact** : Exposition de données personnelles dans les logs Railway (stockage tiers).  
**Correction recommandée** : Logger uniquement l'ID numérique :
```python
logger.warning(f"Accès refusé pour user_id={update.effective_user.id}")
```

---

### 3.2 QUALITÉ DU CODE

---

### [QUA-1] `logger_init` utilisé avant la configuration du logging
**Fichier** : `bot.py:59-69`  
**Sévérité** : 🟡 Mineur  
**Problème** : Les lignes 59-71 appellent `logging.getLogger("APEX-Bot")` et `.info()` **avant** `logging.basicConfig()` (ligne 75) et **avant** l'ajout du `_TokenMaskFilter` (ligne 111). Les messages ne seront pas formatés correctement et ne seront pas filtrés.  
**Impact** : Messages de démarrage du module `database`/`backtester` potentiellement non filtrés et non formatés.  
**Correction recommandée** : Déplacer les imports `database`/`backtester` **après** la configuration complète du logging (après la ligne 111).

---

### [QUA-2] `CONFIG_DEMO_MODE` importé mais jamais utilisé
**Fichier** : `bot.py:50`  
**Sévérité** : 🟡 Mineur  
**Problème** : `from config import DEMO_MODE as CONFIG_DEMO_MODE` — cette variable n'est jamais référencée dans le reste du fichier. Le DEMO_MODE opérationnel est celui dérivé de `os.getenv()` à la ligne 119.  
**Correction recommandée** : Supprimer l'import.

---

### [QUA-3] Double import redondant de `config` et `coupon_generator`
**Fichier** : `bot.py:139, 159`  
**Sévérité** : 🟡 Mineur  
**Problème** :  
- Ligne 139 : `import config` — alors que `config` a déjà été importé (ligne 50) via `from config import ...`  
- Ligne 159 : `import coupon_generator` dans un try/except — alors que l'import initial (ligne 49) aurait déjà échoué si le module était absent, stoppant le bot (ligne 52 : `sys.exit(1)`). Ce try/except est donc mort.  
**Correction recommandée** :
```python
# Ligne 139 : remplacer par
import config as _config_module
_config_module.DEMO_MODE = DEMO_MODE

# Supprimer lignes 158-162 (dead code)
```

---

### [QUA-4] Import `re` dupliqué dans une fonction
**Fichier** : `bot.py:507`  
**Sévérité** : 🟡 Mineur  
**Problème** : `import re as _re` à l'intérieur de `scheduled_coupon()`. Le module `re` est déjà importé au niveau module (ligne 26).  
**Correction recommandée** : Utiliser directement `re.sub(...)` (module-level import).

---

### [QUA-5] f-string manquant — TIMEZONE non interpolé dans le log
**Fichier** : `bot.py:634`  
**Sévérité** : 🔴 Critique (bug silencieux)  
**Problème** : 
```python
logger.info("Job resolution resultats planifie a 01:00 ({TIMEZONE})")
```
Il manque le préfixe `f`. Le log affichera littéralement `{TIMEZONE}` au lieu de la valeur.  
**Impact** : Log de démarrage trompeur — impossible de vérifier la timezone configurée depuis les logs Railway.  
**Correction recommandée** :
```python
logger.info(f"Job resolution resultats planifie a 01:00 ({TIMEZONE})")
```

---

### [QUA-6] `"Pas de matchs"` comme détection d'état — fragile
**Fichier** : `bot.py:286`  
**Sévérité** : 🟡 Mineur  
**Problème** : `if "Pas de matchs" in message` — détection d'état par sous-chaîne dans le message localisé. Si le texte du message change (traduction, reformulation), la condition casse silencieusement.  
**Correction recommandée** : `run_pipeline()` pourrait retourner un tuple `(coupon, texte, statut)` ou une exception dédiée.

---

### [QUA-7] `stars()` définie à l'intérieur de `format_coupon_telegram()`
**Fichier** : `bot.py:189-191`  
**Sévérité** : 🟡 Mineur  
**Problème** : Fonction utilitaire pure définie dans une autre fonction — recréée à chaque appel. Utilise des magic numbers (10, 3).  
**Correction recommandée** : Déplacer au niveau module, extraire les constantes.

---

### [QUA-8] `self.tomorrow` défini mais jamais utilisé dans `DataFetcher`
**Fichier** : `coupon_generator.py:184`  
**Sévérité** : 🟡 Mineur (dead code)  
**Problème** : `self.tomorrow = (datetime.now() + timedelta(days=1)).strftime(...)` est calculé au `__init__` mais n'est référencé nulle part dans la classe ou ailleurs dans le fichier.  
**Correction recommandée** : Supprimer cette ligne.

---

### [QUA-9] `normalize_team_name` casse "Manchester United" → "manchester"
**Fichier** : `coupon_generator.py:98-135`  
**Sévérité** : 🟠 Important  
**Problème** : La liste `_TEAM_SUFFIXES` contient `" united"`. "Manchester United" (après lowercase) vérifie `endswith(" united")` → normalise en `"manchester"`. Mais le nom canonique dans `TEAM_ALIASES` est `"manchester united"`. Résultat : une équipe nommée "Manchester United" dans football-data.org sera normalisée en `"manchester"`, ce qui ne correspond à rien dans l'index de cotes.  

Trace complète :
```
"Manchester United" → lower → "manchester united"
→ alias: pas dans TEAM_ALIASES
→ suffix: "manchester united".endswith(" united") == True
→ "manchester" ← NOM ERRONÉ
```

Les API the-odds-api envoient souvent `"Manchester United"` → lookup échoue → pas de cotes → pas de value bets sur ce match.  
**Impact** : Manchester United systématiquement exclu des value bets en mode réel.  
**Correction recommandée** : Revoir `_TEAM_SUFFIXES` pour n'inclure que des suffixes **non significatifs**. `" united"`, `" city"`, `" town"`, `" rovers"`, `" wanderers"` sont souvent des parties intégrantes du nom. Solution alternative : appliquer les suffixes seulement si le résultat n'est pas vide et si le nom d'origine n'est pas déjà dans les alias.

Suffixes véritablement génériques à conserver : `" fc"`, `" cf"`, `" sc"`, `" ac"`, `" as"`, `" ss"`, `" afc"`, `" bsc"`, `" rsc"`.

---

### [QUA-10] `API_FOOTBALL_LEAGUES` défini dans config.py mais jamais utilisé
**Fichier** : `config.py:47-55`  
**Sévérité** : 🟡 Mineur (dead code)  
**Problème** : `API_FOOTBALL_LEAGUES` est défini mais n'est importé ni dans `coupon_generator.py` ni dans `bot.py`. Aucune intégration api-football n'existe dans le code actuel.  
**Correction recommandée** : Commenter le bloc avec `# TODO: activer quand l'intégration api-football est implémentée`.

---

### [QUA-11] `DISPLAY` et `LINE_MOVEMENT` définis dans config.py mais jamais consommés
**Fichier** : `config.py:324-345`  
**Sévérité** : 🟡 Mineur  
**Problème** : Les deux sections de configuration sont définies mais ni importées ni utilisées dans aucun module.  
**Impact** : Configuration trompeuse — l'opérateur croit pouvoir activer `LINE_MOVEMENT_ENABLED` alors que la fonctionnalité n'est pas implémentée.  
**Correction recommandée** : Commenter en ajoutant un marqueur `# TODO: non implémenté`.

---

### [QUA-12] Indentation incorrecte dans `scheduled_coupon`
**Fichier** : `bot.py:499-512`  
**Sévérité** : 🟡 Mineur  
**Problème** : Le `try/except` interne (lignes 499-512) a un niveau d'indentation supplémentaire (8 espaces) par rapport au `for chunk` (4 espaces), créant une asymétrie visuelle et potentiellement inattendue.  
**Correction recommandée** : Normaliser l'indentation.

---

### 3.3 ROBUSTESSE / FIABILITÉ

---

### [ROB-1] Division par zéro dans `calculate_lambdas` si `avg == 0`
**Fichier** : `coupon_generator.py:650-656`  
**Sévérité** : 🔴 Critique  
**Problème** : 
```python
att_home = fixture["home_goals_avg"] / avg  # ZeroDivisionError si avg == 0
```
`avg` provient de `league_avg_goals` qui peut être `None` ou `0` si les standings retournent des données vides. Le `or` sur la ligne 707 ne protège pas contre `0` (falsy en Python mais sémantiquement différent).  
**Impact** : `ZeroDivisionError` non capturée dans la boucle de prédictions → fixture ignorée avec un warning (ligne 1937), comportement silencieux.  
**Correction recommandée** :
```python
avg = league_avg_goals if (league_avg_goals is not None and league_avg_goals > 0) \
      else self.league_avg_goals
if avg <= 0:
    avg = POISSON_PARAMS["default_league_avg_goals"]
```

---

### [ROB-2] `BacktestTracker._save()` non atomique
**Fichier** : `coupon_generator.py:1480-1484`  
**Sévérité** : 🟠 Important  
**Problème** : L'historique est écrit directement dans `coupon_history.json`. Si le process Railway redémarre ou crash pendant l'écriture, le fichier JSON sera corrompu (tronqué).  
**Impact** : Perte de tout l'historique backtest au prochain chargement (`JSONDecodeError` → réinitialisation silencieuse ligne 1474).  
**Correction recommandée** :
```python
def _save(self) -> None:
    if self._history is None:
        return
    tmp = self.history_file.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(self._history, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    tmp.replace(self.history_file)  # Atomique sur la plupart des OS
```

---

### [ROB-3] `TTLCache` non thread-safe pour les écritures concurrentes
**Fichier** : `coupon_generator.py:142-163`  
**Sévérité** : 🟡 Mineur  
**Problème** : Le cache global `_cache` peut être accédé simultanément si deux requêtes `/coupon` arrivent dans des threads différents (via `run_in_executor`). Le GIL Python protège les opérations dict élémentaires, mais `get()` contient un `del` conditionnel qui pourrait interférer.  
**Impact** : Race condition théorique, peu probable en pratique avec un seul bot.  
**Correction recommandée** : Ajouter un `threading.Lock` dans `TTLCache` ou utiliser `functools.lru_cache` pour le coupon.

---

### [ROB-4] `_evaluate_bet` — matching fuzzy insuffisant pour les équipes visiteurs
**Fichier** : `coupon_generator.py:1602-1607`  
**Sévérité** : 🟠 Important  
**Problème** : Le matching fuzzy du résultat :
```python
if match_key == key or (
    normalize_team_name(res["home"]) in normalize_team_name(match_key)
):
```
Ne vérifie que si **l'équipe domicile** du résultat est dans la clé du pari. L'équipe **visiteur** n'est pas vérifiée → faux positifs potentiels (ex : "Roma" matchant "Villarreal vs Oklahoma"). Si le problème QUA-9 est corrigé, ce matching pourrait aussi être affecté.  
**Correction recommandée** :
```python
home_norm = normalize_team_name(res["home"])
away_norm = normalize_team_name(res["away"])
match_key_norm = normalize_team_name(match_key)
if (home_norm in match_key_norm and away_norm in match_key_norm):
    result = res
    break
```

---

### [ROB-5] `DataFetcher.fetch_football_fixtures` docstring incorrecte
**Fichier** : `coupon_generator.py:271`  
**Sévérité** : 🟡 Mineur  
**Problème** : La docstring dit "Récupère les matchs de **demain**" mais le code utilise `self.today`. L'attribut `self.tomorrow` est défini mais jamais utilisé.  
**Impact** : Confusion pour les développeurs — le bot prédit les matchs **d'aujourd'hui**, pas de demain.  
**Correction recommandée** : Corriger la docstring.

---

### [ROB-6] Appels API football séquentiels (6 compétitions × 2 = 12 appels)
**Fichier** : `coupon_generator.py:1876-1896`  
**Sévérité** : 🟠 Important  
**Problème** : Pour chaque compétition football, `fetch_football_fixtures` et `fetch_football_standings` sont appelés séquentiellement. Avec `timeout=10s` et `max_retries=3`, le pire cas est `6 × 2 × 10 = 120 secondes` de blocage. Même `fetch_all_odds` appelle 8 sports séquentiellement.  
**Impact** : La génération du coupon peut prendre plus de 2 minutes en mode réel, dépassant potentiellement des limites de timeout Railway.  
**Correction recommandée** : Utiliser `concurrent.futures.ThreadPoolExecutor` :
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(fetcher.fetch_football_fixtures, code): code
        for code in FOOTBALL_COMPETITIONS
    }
    # ...
```

---

### [ROB-7] `EloModel` : les ratings de démo sont écrasés à chaque `predict()`
**Fichier** : `coupon_generator.py:897-900`  
**Sévérité** : 🟡 Mineur  
**Problème** :
```python
if "home_elo" in fixture:
    self.ratings[home] = fixture["home_elo"]  # Mutation d'état
```
Chaque appel à `predict()` met à jour le dict `self.ratings` avec les ELO du fixture. Si deux prédictions pour la même équipe avec des ELO différents sont faites, la seconde écraserait la première. Dans le contexte actuel (fixtures uniques), c'est sans conséquence, mais fragile.

---

### [ROB-8] `nba_elo_bootstrap.py` : pause `time.sleep(60)` sur quota 429 bloque le thread principal
**Fichier** : `nba_elo_bootstrap.py:103-104`  
**Sévérité** : 🟡 Mineur  
**Problème** : En cas de rate-limit BallDontLie (429), le script s'arrête 60 secondes en bloquant complètement. C'est acceptable pour un script standalone, mais devrait être `time.sleep(0.5)` entre les pages (ligne 175) pour les cas normaux.

---

### [ROB-9] `resolve_results` n'est pas idempotent
**Fichier** : `coupon_generator.py:1672-1698`  
**Sévérité** : 🟡 Mineur  
**Problème** : Si le job de résolution à 01h00 est exécuté deux fois (redémarrage Railway), les sélections déjà résolues sont bien ignorées (ligne 1675 : `if entry.get("result") is not None: continue`), mais les **sélections individuelles** sont relues sans guard équivalent (ligne 1682 : `if sel.get("result") is not None:` — il y a bien une continue, mais `updated_count` ne reflète pas un double-comptage). La logique est correcte mais mérite une vérification.

---

### 3.4 PERFORMANCES

---

### [PERF-1] Combinatorique CouponBuilder non optimisée pour grandes pools
**Fichier** : `coupon_generator.py:1327`  
**Sévérité** : 🟡 Mineur  
**Problème** : `combinations(pool[:15], target_size)` avec `target_size=6` donne C(15,6) = 5005 itérations, chacune exécutant un `reduce`. C'est marginal en temps CPU (~1ms total), mais si `target_size` est augmenté à 8, C(15,8) = 6435 — encore acceptable. La limite à 15 éléments (ligne 1321) est une bonne précaution.

---

### [PERF-2] `pandas` chargé à l'import pour un seul usage de logging
**Fichier** : `coupon_generator.py:43`  
**Sévérité** : 🟡 Mineur  
**Problème** : `import pandas as pd` au niveau module — pandas prend ~50-100ms au chargement et ~20MB en mémoire. Il n'est utilisé que dans `CouponBuilder.to_dataframe()` qui sert uniquement à afficher un récapitulatif dans les logs.  
**Correction recommandée** : Import paresseux ou supprimer le DataFrame si ce n'est que du logging :
```python
def to_dataframe(self, coupon: List[dict]) -> "pd.DataFrame":
    import pandas as pd  # Import paresseux
    ...
```

---

### [PERF-3] `fetch_all_odds` appelle séquentiellement 8 endpoints
**Fichier** : `coupon_generator.py:381-388`  
**Sévérité** : 🟠 Important  
**Impact** : Voir ROB-6 — même recommandation de parallélisation.

---

### 3.5 PRÉCISION DES PRÉDICTIONS (MODÈLES)

---

### [MET-1] `LEAGUE_HOME_ADVANTAGE` défini dans config.py mais jamais utilisé dans `PoissonModel`
**Fichier** : `config.py:292-303`, `coupon_generator.py:619`  
**Sévérité** : 🔴 Critique (régression fonctionnelle)  
**Problème** : `LEAGUE_HOME_ADVANTAGE` définit des facteurs d'avantage domicile spécifiques par ligue (PL: 1.10, SA: 1.15, etc.) mais **n'est pas importé** dans `coupon_generator.py` (ligne 48-52). Le `PoissonModel` utilise toujours la valeur générique `POISSON_PARAMS["home_advantage"] = 1.1` pour toutes les ligues.  
**Impact** : L'avantage domicile de la Serie A (1.15) et de La Liga (1.12) est sous-évalué ; celui de la Bundesliga (1.08) est sur-évalué. Peut biaiser systématiquement les prédictions 1X2.  
**Correction recommandée** : Importer et câbler dans `run_pipeline` :
```python
from config import LEAGUE_HOME_ADVANTAGE
# Dans la boucle d'enrichissement des fixtures :
home_adv = LEAGUE_HOME_ADVANTAGE.get(code, POISSON_PARAMS["home_advantage"])
fix["home_advantage"] = home_adv
```
Et dans `PoissonModel.calculate_lambdas` :
```python
home_adv = fixture.get("home_advantage", self.home_adv)
lambda_home = att_home * def_away * avg * home_adv
```

---

### [MET-2] `LEAGUE_AVG_GOALS` défini dans config.py mais jamais utilisé comme fallback
**Fichier** : `config.py:305-314`, `coupon_generator.py:707`  
**Sévérité** : 🟠 Important  
**Problème** : `LEAGUE_AVG_GOALS` fournit des moyennes de buts de référence par ligue (BL1: 3.10, SA: 2.60), mais en mode réel, si les standings ne sont pas disponibles, le fallback est `self.league_avg_goals = 2.65` (valeur générique), pas la valeur par ligue.  
**Impact** : Une prédiction de Bundesliga sans standings utilise 2.65 au lieu de 3.10 — sous-estime systématiquement le total de buts prédit (~15% d'erreur sur lambda).  
**Correction recommandée** : Dans `run_pipeline`, utiliser `LEAGUE_AVG_GOALS.get(code)` comme fallback secondaire avant la valeur générique :
```python
from config import LEAGUE_AVG_GOALS
league_avg = (
    league_avg_goals_map.get(code)
    or LEAGUE_AVG_GOALS.get(code)
    or POISSON_PARAMS["default_league_avg_goals"]
)
```

---

### [MET-3] `StatsModel` référencé dans la doc mais non implémenté
**Fichier** : `CLAUDE.md` (pipeline), `config.py:273-290`  
**Sévérité** : 🟠 Important  
**Problème** : `STATS_MARKETS` est défini dans `config.py` et le pipeline CLAUDE.md mentionne "StatsModel → Marchés stats (corners, fautes, cartons, tirs)". Mais cette classe **n'existe pas** dans `coupon_generator.py` et `STATS_MARKETS` n'est pas importé.  
**Impact** : Les marchés corners/cartons/fautes ne sont jamais modélisés ni proposés dans le coupon. La configuration est trompeuse.  
**Correction recommandée** : Soit implémenter StatsModel, soit supprimer `STATS_MARKETS` de config.py et la mention du pipeline dans CLAUDE.md.

---

### [MET-4] Over/Under basketball : seuil fixé à la moyenne NBA globale (224.5 pts)
**Fichier** : `coupon_generator.py:885`  
**Sévérité** : 🟠 Important  
**Problème** : Le seuil Over/Under NBA est `nba_avg_total = 224.5` (hardcodé), indépendant des `home_ppg`/`away_ppg` des équipes. Pour des équipes rapides (ex : Celtics vs Heat qui jouent ~230 pts combinés), le threshold de 224.5 donnera toujours `p_over > 0.5`, ce qui génère un biais systématique.  
**Correction recommandée** : Utiliser le total attendu des deux équipes comme seuil de base :
```python
natural_threshold = home_ppg + away_ppg  # Seuil naturel basé sur les équipes
threshold = (nba_avg_total + natural_threshold) / 2  # Moyenne pondérée
```

---

### [MET-5] Probabilités football ne couvrent pas correctement le marché BTTS
**Fichier** : `coupon_generator.py:735-739`  
**Sévérité** : 🟡 Mineur  
**Problème** : 
```python
p_btts = float(1 - np.sum(matrix[0, :]) - np.sum(matrix[:, 0]) + matrix[0, 0])
```
Cette formule est mathématiquement correcte (inclusion-exclusion : P(home>0 ET away>0) = 1 - P(home=0) - P(away=0) + P(home=0, away=0)). ✓  
Mais `p_btts_no = 1 - p_btts` est correct **uniquement si** p_btts + p_btts_no = 1, ce qui est assuré. ✓  

Pas d'erreur ici, mais noter que `p_btts` et `p_btts_no` sont tous deux proposés comme paris dans `extract_football_bets`. Avec la règle `select_best_bets` qui déduplique par marché, si `btts Yes` est sélectionné, `btts No` ne peut pas l'être. C'est correct.

---

### [MET-6] `TennisModel.ranking_to_elo` retourne une valeur négative pour ranking > 1467
**Fichier** : `coupon_generator.py:964`  
**Sévérité** : 🟡 Mineur  
**Problème** : `return max(1400, 2200 - ranking * 1.5)`. Pour ranking = 534 : `2200 - 534×1.5 = 1399` → clamped à 1400. Pour ranking = 534+, la valeur décroît encore. À ranking = 1467 : ELO = 2200 - 2200 = 0, puis négatif. Non réaliste.  
**Impact** : Un joueur classé 1000e aurait un ELO de max(1400, 700) = 1400 (même qu'un classé 534e). La discrimination est perdue.  
**Correction recommandée** : Utiliser une asymptote : `return max(1200, 2200 - ranking * 1.0)` avec un plancher plus bas.

---

### [MET-7] `ValueBetSelector.select_best_bets` — logique de déduplication incomplète
**Fichier** : `coupon_generator.py:1239-1263`  
**Sévérité** : 🟠 Important  
**Problème** : La règle de déduplication empêche deux paris du **même marché** sur le même match (ex : ne pas prendre à la fois `h2h` Victoire Home ET `h2h` Victoire Away). C'est correct.  
Mais des marchés **incompatibles** de catégories différentes peuvent être combinés sur le même match : "Victoire Arsenal" (h2h, cote 1.80) ET "Over 2.5" (totals, cote 2.10) ET "BTTS Oui" (btts, cote 1.90) → **3 paris sur le même match** dans le coupon. Cela crée une corrélation forte non modélisée dans la cote combinée.  
**Impact** : La cote totale du coupon est artificiellement gonflée par des sélections corrélées sur le même match, augmentant le risque réel au-delà de l'espérance théorique.  
**Correction recommandée** : Limiter à **1 pari par match** dans le coupon final, en conservant uniquement le meilleur `value` par match.

---

### 3.6 ARCHITECTURE / MAINTENABILITÉ

---

### [ARC-1] `bot.py` mute directement l'attribut de module `coupon_generator.DEMO_MODE`
**Fichier** : `bot.py:160`  
**Sévérité** : 🟡 Mineur  
**Problème** : `coupon_generator.DEMO_MODE = DEMO_MODE` modifie l'état global du module importé — couplage fort et difficile à tester.  
**Correction recommandée** : Passer `demo_mode` comme paramètre à `run_pipeline(demo_mode=DEMO_MODE)`.

---

### [ARC-2] Double système de persistance (JSON + SQLite)
**Fichier** : `coupon_generator.py:1456`, `bot.py:57`  
**Sévérité** : 🟡 Mineur  
**Problème** : `BacktestTracker` utilise `coupon_history.json`; `ApexDatabase` (database.py, absent localement) utilise SQLite. Les deux systèmes stockent des coupons de façon parallèle. La commande `/history` utilise SQLite ; `get_stats()` utilise JSON.  
**Impact** : Incohérence des données entre les deux stores si le bot tourne sans database.py.

---

### [ARC-3] `CouponBuilder.format_coupon()` duplique la logique de `format_coupon_telegram()`
**Fichier** : `coupon_generator.py:1375`, `bot.py:174`  
**Sévérité** : 🟡 Mineur  
**Problème** : Deux fonctions de formatage parallèles — l'une pour la console, l'autre pour Telegram. Les deux calculent `total_odd`, les étoiles de confiance, etc.

---

### 3.7 OBSERVABILITÉ

---

### [OBS-1] Pas de health check HTTP pour Railway
**Fichier** : `Procfile:1`  
**Sévérité** : 🟠 Important  
**Problème** : Le Procfile déclare `worker: python bot.py`. Railway avec un process `worker` n'a pas de HTTP endpoint → pas de health check automatique. En cas de crash silencieux (ex : thread bloqué sur une API), Railway ne redémarre pas le process.  
**Correction recommandée** : Ajouter un petit serveur HTTP de health check en parallèle :
```python
# Dans bot.py, démarrer un thread HTTP minimal
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args): pass  # Silencieux

def _start_health_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=_start_health_server, daemon=True).start()
```
Et modifier le Procfile : `web: python bot.py`

---

### [OBS-2] Aucun warning au démarrage si les clés API sont absentes
**Fichier** : `bot.py:578-643` (fonction `main`)  
**Sévérité** : 🟡 Mineur  
**Problème** : Le bot démarre sans signaler que `FOOTBALL_DATA_KEY` ou `ODDS_API_KEY` sont manquantes. Le mode réel tombera silencieusement en mode démo.  
**Correction recommandée** : Dans `main()`, après la vérification du token :
```python
missing_keys = [k for k, v in API_KEYS.items() if not v and k != "balldontlie"]
if missing_keys and not DEMO_MODE:
    logger.warning(f"⚠️ Clés API manquantes : {missing_keys} — fallback démo possible")
```

---

### [OBS-3] Circuit-breaker loggé en DEBUG — invisible en production
**Fichier** : `coupon_generator.py:215`  
**Sévérité** : 🟡 Mineur  
**Problème** : `logger.debug(f"API {api_name} en circuit-break — ignorée")` — ce message est invisible en production (niveau INFO). Un opérateur ne saura pas qu'une API est en circuit-break sans passer en DEBUG.  
**Correction recommandée** : Logger à WARNING lors de la **mise** en circuit-break (dans `_mark_api_broken`), pas lors de chaque appel ignoré.

---

### [OBS-4] `BacktestTracker` ne logue pas les coupons non résolubles
**Fichier** : `coupon_generator.py:1709-1712`  
**Sévérité** : 🟡 Mineur  
**Problème** : Si `updated_count == 0` après `resolve_results`, le log est en DEBUG (`logger.debug`). En production, impossible de distinguer "pas de coupons à résoudre" de "résolution silencieusement échouée".

---

### 3.8 DÉPLOIEMENT / DEVOPS

---

### [DEV-1] `.python-version` (3.12) incohérent avec CLAUDE.md ("Python 3.10+")
**Fichier** : `.python-version:1`  
**Sévérité** : 🟡 Mineur  
**Problème** : Le fichier impose Python 3.12, la doc dit 3.10+. `zoneinfo` (importé à bot.py:32) nécessite Python 3.9+. Pas de vrai problème fonctionnel, mais la doc est imprécise.  
**Correction recommandée** : Mettre à jour CLAUDE.md : "Python 3.9+ (3.12 recommandé)".

---

### [DEV-2] Dépendances de test incluses dans requirements.txt de production
**Fichier** : `requirements.txt:20-21`  
**Sévérité** : 🟡 Mineur  
**Problème** : `pytest==8.2.2` et `pytest-asyncio==0.23.7` sont installés dans le container Railway de production. Ces packages (~5MB) sont inutiles en runtime.  
**Correction recommandée** : Créer `requirements-dev.txt` pour les deps de test ; garder `requirements.txt` uniquement pour la production.

---

### [DEV-3] `apscheduler` non épinglé directement dans requirements.txt
**Fichier** : `requirements.txt:18`  
**Sévérité** : 🟡 Mineur  
**Problème** : `python-telegram-bot[job-queue]` installe `apscheduler` comme dépendance transitive. Si APScheduler sort une version majeure incompatible, le bot pourrait casser sans notice.  
**Correction recommandée** : Ajouter `apscheduler>=3.10,<4.0` dans requirements.txt.

---

### [DEV-4] `database.py` et `backtester.py` absents localement
**Fichier** : `bot.py:56-71`  
**Sévérité** : 🟡 Mineur (documenté comme dette technique)  
**Problème** : Les modules sont importés avec fallback gracieux, mais `/history` et `/stats` retournent "module non disponible" sans indiquer à l'utilisateur qu'il s'agit d'un problème de configuration, pas d'un bug.  
**Correction recommandée** : Le message d'erreur Telegram pourrait être plus explicite : "⚠️ Fonctionnalité non activée sur cette instance."

---

### [DEV-5] Pas de fichier `.env.example`
**Fichier** : (absent)  
**Sévérité** : 🟡 Mineur  
**Problème** : CLAUDE.md mentionne `.env.example` comme référence mais le fichier n'existe pas dans le repo.  
**Correction recommandée** : Créer `.env.example` avec toutes les variables documentées dans CLAUDE.md section 6.

---

## 4. Roadmap de corrections suggérée

### Sprint 1 — Corrections immédiates (< 2h)
1. **QUA-5** : Ajouter le `f` manquant → `logger.info(f"...{TIMEZONE}")` `bot.py:634`
2. **QUA-8** : Supprimer `self.tomorrow` mort `coupon_generator.py:184`
3. **QUA-2 + QUA-3** : Supprimer `CONFIG_DEMO_MODE`, simplifier les imports redondants `bot.py:50,139,159`
4. **QUA-4** : Supprimer `import re as _re` `bot.py:507`
5. **ROB-5** : Corriger la docstring `fetch_football_fixtures` "demain" → "aujourd'hui"
6. **OBS-2** : Ajouter warning si clés API manquantes au démarrage

### Sprint 2 — Corrections importantes (< 1j)
1. **QUA-9** : Revoir `_TEAM_SUFFIXES` pour ne pas casser "Manchester United" et équivalents
2. **ROB-1** : Guard contre `avg == 0` dans `calculate_lambdas`
3. **SEC-1** : Masquer `exc_info` dans `_TokenMaskFilter`
4. **ROB-2** : Rendre `BacktestTracker._save()` atomique
5. **MET-7** : Limiter à 1 pari par match dans le coupon final
6. **OBS-1** : Ajouter le health check HTTP pour Railway

### Sprint 3 — Améliorations de fond (1-3j)
1. **MET-1** : Câbler `LEAGUE_HOME_ADVANTAGE` dans `PoissonModel`
2. **MET-2** : Câbler `LEAGUE_AVG_GOALS` comme fallback secondaire
3. **ROB-6 + PERF-3** : Paralléliser les appels API avec `ThreadPoolExecutor`
4. **MET-4** : Améliorer le threshold Over/Under NBA
5. **DEV-1** : Séparer requirements prod/dev ; ajouter `.env.example`

### Sprint 4 — Améliorations long terme
1. **MET-3** : Implémenter StatsModel (corners, cartons) ou retirer de la doc
2. **ARC-1** : Passer `demo_mode` en paramètre à `run_pipeline()`
3. **MET-6** : Améliorer la courbe ELO tennis pour les classements > 500
4. **DEV-3** : Épingler apscheduler dans requirements.txt

---

## 5. Récapitulatif des problèmes par sévérité

### 🔴 Critique (3)
| Code | Titre | Fichier |
|------|-------|---------|
| QUA-5 | f-string manquant TIMEZONE | `bot.py:634` |
| MET-1 | LEAGUE_HOME_ADVANTAGE non câblé | `config.py`, `coupon_generator.py` |
| ROB-1 | Division par zéro si avg==0 | `coupon_generator.py:650` |

### 🟠 Important (12)
| Code | Titre | Fichier |
|------|-------|---------|
| SEC-1 | TokenMaskFilter ne masque pas exc_info | `bot.py:91` |
| QUA-9 | normalize_team_name casse "Man United" | `coupon_generator.py:103` |
| ROB-2 | BacktestTracker._save() non atomique | `coupon_generator.py:1480` |
| ROB-4 | _evaluate_bet fuzzy matching insuffisant | `coupon_generator.py:1602` |
| ROB-6 | Appels API football séquentiels (120s max) | `coupon_generator.py:1876` |
| PERF-3 | fetch_all_odds séquentiel (8 sports) | `coupon_generator.py:381` |
| MET-2 | LEAGUE_AVG_GOALS non utilisé | `config.py:305` |
| MET-3 | StatsModel absent malgré doc + config | `config.py:273` |
| MET-4 | Threshold Over/Under NBA hardcodé | `coupon_generator.py:885` |
| MET-7 | Plusieurs paris corrélés par match | `coupon_generator.py:1239` |
| OBS-1 | Pas de health check HTTP Railway | `Procfile` |
| QUA-1 | logger_init avant logging.basicConfig | `bot.py:59` |

### 🟡 Mineur (18)
SEC-2, SEC-3, QUA-2, QUA-3, QUA-4, QUA-6, QUA-7, QUA-8, QUA-10, QUA-11, QUA-12, ROB-3, ROB-5, ROB-7, ROB-8, MET-5, MET-6, ARC-1, ARC-2, ARC-3, OBS-2, OBS-3, OBS-4, DEV-1, DEV-2, DEV-3, DEV-4, DEV-5

---

*Rapport généré le 2026-04-14 — Audit APEX v6 — Total : 33 problèmes identifiés*
