# AUDIT GLOBAL v4 — BetForge / APEX Bot

**Date :** 13 avril 2026
**Auditeur :** Claude (audit #4)
**Périmètre :** Sécurité, architecture, modèles statistiques, données, value betting, bot Telegram, modules manquants
**Fichiers audités :** `bot.py` (549 L), `coupon_generator.py` (1527 L), `config.py` (183 L), `requirements.txt`, `SECURITY.md`

---

## TABLEAU DE BORD — SCORES PAR DOMAINE

| Domaine | Score | Tendance | Commentaire |
|---------|-------|----------|-------------|
| Sécurité | **7/10** | ↗ (était 3→8) | Secrets OK, mais contrôle d'accès NON implémenté |
| Architecture | **7/10** | ↗ (était 6) | Propre, modulaire, mais 3 modules manquants |
| Modèle Poisson (Football) | **6/10** | = (était 6) | Correct mais rho empirique fixe, pas de MLE |
| Modèle ELO (Basketball) | **4/10** | = | Jamais entraîné, inutile en mode réel |
| Modèle Tennis | **5/10** | = | Bon design, mais aucune source de données réelles |
| Données & Statistiques | **5/10** | ↘ | APIs football OK, basket/tennis = 0 données réelles |
| Value Betting & Coupon | **7/10** | ↗ (était 4) | Kelly corrigé, cotes indépendantes en démo |
| Bot Telegram | **8/10** | ↗↗ (était 5) | Refonte affichage terminée, fallback robuste |
| **SCORE GLOBAL** | **6.1/10** | ↗ (était ~5) | Fonctionnel, mais lacunes structurelles |

---

## 1. SÉCURITÉ — 7/10

### ✅ Points conformes
- Secrets lus via `os.getenv()` partout — aucun secret en dur
- `TELEGRAM_TOKEN` crash explicite si absent (`sys.exit(1)`)
- `.env` dans `.gitignore`, `.env.example` documenté
- Timeouts sur tous les appels API (`NETWORK["timeout"]`)
- `try/except` systématique avec logging serveur, messages génériques à l'utilisateur
- Exponential backoff et circuit breaker sur les retries
- Pas de `eval()`, `exec()`, `os.system()`, `subprocess` dans le code
- Versions épinglées dans `requirements.txt`

### 🔴 CRITIQUE — Contrôle d'accès NON implémenté
`config.py` définit `ALLOWED_USERS` (lignes 170-174), mais **`bot.py` ne l'utilise nulle part**. Aucune commande ne vérifie `update.effective_user.id`.

Le fichier `bot.py.txt` (ancienne version) contient une fonction `is_authorized()` et un check dans le handler, mais le **`bot.py` actuel déployé** n'a aucun contrôle d'accès.

**Impact :** N'importe qui peut utiliser le bot, y compris `/result` qui modifie l'état.

**Correction recommandée :**
```python
from config import ALLOWED_USERS

def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True  # Pas de whitelist = ouvert
    return user_id in ALLOWED_USERS

# Dans chaque handler sensible :
if not is_authorized(update.effective_user.id):
    await update.message.reply_text("⛔ Accès non autorisé.")
    return
```

### 🟡 MOYEN — Pas d'échappement HTML/injection Telegram
Les valeurs utilisateur (ex: `args[0]` dans `/result`) sont passées à `_esc()` pour MarkdownV2, ce qui est correct. Mais il n'y a pas de `html.escape()` car le bot utilise `ParseMode.MARKDOWN_V2`, pas HTML. C'est cohérent — **OK**.

### 🟡 MOYEN — `TELEGRAM_TOKEN` a un fallback `""`
```python
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")  # ligne 82
```
Le SECURITY.md dit "pas de valeur par défaut". Techniquement, le `""` est rattrapé par le check `if not TELEGRAM_TOKEN` ligne 492, donc le bot crashe bien — mais il serait plus propre d'avoir :
```python
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # None si absent
```

---

## 2. ARCHITECTURE — 7/10

### ✅ Points forts
- Séparation claire : `bot.py` (interface), `coupon_generator.py` (moteur), `config.py` (paramètres)
- Classes bien découpées : `DataFetcher`, `PoissonModel`, `EloModel`, `TennisModel`, `ValueBetSelector`, `CouponBuilder`, `BacktestTracker`
- Pipeline linéaire clair en 5 étapes dans `run_pipeline()`
- Cache TTL intégré pour réduire les appels API
- Logging structuré à chaque étape

### 🔴 CRITIQUE — 3 modules importés mais inexistants
Les fichiers suivants sont importés dans `bot.py` mais **n'existent pas** dans le dossier :
- `database.py` → `ApexDatabase` (persistance SQLite)
- `backtester.py` → `ApexBacktester` (backtesting)
- `line_movement.py` (mentionné dans la mémoire projet)

**Impact :**
- Les commandes `/history`, `/stats`, `/result` sont **mortes** — elles affichent toujours "Module non disponible"
- Le tracking des résultats n'a aucune persistance réelle
- Le `BacktestTracker` dans `coupon_generator.py` écrit dans un JSON local, mais **rien ne lit ces résultats** côté bot

Les imports sont protégés par `try/except ImportError` donc le bot ne crashe pas, mais ces fonctionnalités sont des coquilles vides.

### 🟡 MOYEN — Duplication `_esc()` / `esc()`
`bot.py` définit `_esc()` au niveau module (ligne 118) ET `esc()` localement dans `format_coupon_telegram()` (ligne 136). Les deux font exactement la même chose. Supprimer la version locale et utiliser `_esc()` partout.

### 🟡 MOYEN — `bot_patched.py` = copie exacte de `bot.py`
Les deux fichiers font 26 521 octets exactement. Ce fichier devrait être supprimé pour éviter la confusion.

---

## 3. MODÈLES STATISTIQUES — ANALYSE DÉTAILLÉE

### 3.1 Modèle Poisson (Football) — 6/10

#### ✅ Ce qui fonctionne
- Calcul des lambdas basé sur att/def relatifs × moyenne ligue × avantage domicile
- Matrice de scores complète (11×11) avec normalisation
- Correction de dépendance sur les faibles scores (tau factor, inspiré Dixon-Coles)
- Moyenne de buts calculée dynamiquement par ligue (pas hardcodée)
- Marchés couverts : 1X2, Over/Under 2.5, BTTS, score le plus probable

#### 🟡 Limitations connues (documentées)
- **Rho fixe (-0.13)** : pas estimé par MLE sur données historiques. Un vrai Dixon-Coles estimerait rho par maximum de vraisemblance sur les résultats passés.
- **Pas de pondération temporelle** : les stats de la saison sont traitées uniformément. Les 5 derniers matchs ont autant de poids que les 5 premiers.
- **Pas de prise en compte** : blessures, suspensions, météo, motivation (ex: équipe déjà qualifiée)

#### 🔴 Problème — Over/Under utilise `>` au lieu de `>=`
```python
if i + j > self.goals_thresh:  # goals_thresh = 2.5
    p_over += matrix[i][j]
```
Pour un seuil de 2.5, `i + j > 2.5` est correct (3 buts = over). **OK, pas de bug ici** après vérification.

#### 🟡 Problème — `p_home_win` et `p_away_win` inversés ?
```python
p_home = float(np.sum(np.tril(matrix, -1)))  # Triangle inférieur
p_away = float(np.sum(np.triu(matrix, 1)))   # Triangle supérieur
```
Dans la matrice `matrix[i][j]`, `i` = buts domicile, `j` = buts extérieur.
- `np.tril(matrix, -1)` = éléments sous la diagonale = cas où `i < j` = **extérieur marque plus**
- `np.triu(matrix, 1)` = éléments au-dessus de la diagonale = cas où `i > j` = **domicile marque plus**

**⚠️ BUG CONFIRMÉ : `p_home` contient en réalité `p_away` et vice-versa !**

Les noms sont inversés. `tril` (triangle inférieur) capture les cas où la colonne (away) > ligne (home), donc c'est `p_away_win`. Le code a les labels inversés.

**Impact :** Toutes les prédictions 1X2 du modèle Poisson sont **inversées**. Un match où le domicile est favori sera affiché comme victoire extérieure favorite. Cela affecte la sélection des value bets et la confiance affichée.

**Correction :**
```python
p_home = float(np.sum(np.triu(matrix, 1)))   # home > away = triangle supérieur
p_away = float(np.sum(np.tril(matrix, -1)))   # away > home = triangle inférieur
```

### 3.2 Modèle ELO (Basketball) — 4/10

#### ✅ Ce qui fonctionne
- Formule ELO standard (logistic, K=20, bonus domicile)
- Forme récente pondérée (récent = plus lourd)
- Ajustement forme ±10% sur la probabilité

#### 🔴 Problème majeur — Jamais entraîné
Le modèle ELO démarre à 1500 pour toutes les équipes et n'est **jamais mis à jour avec des résultats réels**. La méthode `update()` existe mais n'est jamais appelée.

En mode réel, le basketball est **explicitement désactivé** (ligne 1417 : `if is_demo`). Ce qui est honnête, mais signifie que le modèle ne sert à rien en production.

En mode démo, les ratings ELO sont injectés en dur (`home_elo: 1650`), ce qui simule un modèle entraîné mais ne l'est pas.

#### 🟡 Marchés limités
Seulement victoire domicile/extérieur. Pas de spread, pas de totaux (over/under points), pas de handicap.

### 3.3 Modèle Tennis — 5/10

#### ✅ Bon design
- Ranking → ELO interpolé (table réaliste)
- Surface, forme, H2H, fatigue — tous les facteurs pertinents
- Pénalité de fatigue non-linéaire (progressive)

#### 🔴 Aucune source de données réelles
Comme le basketball, le tennis est désactivé en mode réel. Aucune API ne fournit les données nécessaires (ranking, surface winrate, H2H, matchs récents).

#### 🟡 `TENNIS_PARAMS` absent de `config.py`
`config.py` ne définit pas `TENNIS_PARAMS`. Le fallback dans `coupon_generator.py` le définit si l'import échoue, mais quand `config.py` est importé normalement, `TENNIS_PARAMS` n'est pas dans les exports → **`ImportError` silencieux**.

En fait, `coupon_generator.py` importe `TENNIS_PARAMS` depuis `config` (ligne 49). Comme `config.py` ne le définit pas, **l'import de `TENNIS_PARAMS` échoue** et le fallback global (lignes 53-85) prend le relais avec toutes les valeurs par défaut. Mais cela signifie que si l'import partiel réussit pour d'autres variables, `TENNIS_PARAMS` pourrait être manquant → crash.

**Correction :** Ajouter `TENNIS_PARAMS` dans `config.py`.

---

## 4. DONNÉES ET STATISTIQUES — 5/10

### 4.1 Sources de données

| Source | Sport | Données | Statut |
|--------|-------|---------|--------|
| football-data.org | Football | Fixtures + standings | ✅ Actif |
| the-odds-api.com | Multi | Cotes bookmaker | ✅ Actif |
| TheSportsDB | Multi | Événements | ✅ Actif (mais pas utilisé dans le pipeline) |
| api-football (RapidAPI) | Football | Fixtures détaillés | ⚠️ Configuré mais pas utilisé |
| balldontlie | Basketball | Stats NBA | ⚠️ Endpoint dans config, jamais appelé |

### 🔴 TheSportsDB récupéré mais jamais injecté dans le pipeline
`DataFetcher.fetch_thesportsdb_events()` existe mais n'est **jamais appelé** dans `run_pipeline()`. Les données TheSportsDB ne sont jamais utilisées.

### 🔴 api-football configuré mais jamais utilisé
`config.py` définit `API_FOOTBALL_LEAGUES` et `api_football_base`, mais aucune méthode dans `DataFetcher` ne fait d'appel à cette API. C'est du code mort.

### 🔴 Basketball et Tennis = 0 données réelles
En mode réel, seul le football est traité. Le basketball et le tennis sont limités au mode démo avec des données hardcodées.

### 🟡 Statistiques couvertes vs manquantes

**Football — Statistiques prises en compte :**
- ✅ Buts marqués / encaissés (moyennes par équipe)
- ✅ Nombre de matchs joués
- ✅ Moyenne de buts par ligue (dynamique)
- ✅ Avantage domicile (facteur multiplicatif)
- ✅ Classement (via standings)

**Football — Statistiques NON prises en compte :**
- ❌ Forme récente (5 derniers matchs) — disponible via api-football
- ❌ Blessures / suspensions — disponible via api-football
- ❌ Confrontations directes (H2H)
- ❌ Corners, fautes, cartons, tirs cadrés, possession
- ❌ xG (Expected Goals) — pas d'API gratuite fiable
- ❌ Performances domicile vs extérieur séparées
- ❌ Stats par mi-temps

**Basketball — Statistiques prises en compte :**
- ✅ Rating ELO (simulé en démo)
- ✅ Forme récente (5 derniers matchs)
- ❌ Tout le reste (points/match, rebonds, assists, etc.)

**Tennis — Statistiques prises en compte :**
- ✅ Classement ATP/WTA
- ✅ Surface winrate
- ✅ Forme récente, H2H, fatigue
- ❌ Tout est simulé, aucune donnée réelle

### 🟡 Marchés couverts vs possibles

| Marché | Football | Basketball | Tennis |
|--------|----------|-----------|--------|
| 1X2 / Vainqueur | ✅ | ✅ | ✅ |
| Over/Under 2.5 | ✅ | ❌ | ❌ |
| BTTS | ✅ | N/A | N/A |
| Spread / Handicap | ❌ | ❌ | ❌ |
| Over/Under points | N/A | ❌ | N/A |
| Score exact | Calculé mais pas un marché | N/A | N/A |
| Mi-temps | ❌ | ❌ | ❌ |
| Corners | ❌ | N/A | N/A |
| Cartons | ❌ | N/A | N/A |
| Sets (tennis) | N/A | N/A | ❌ |

---

## 5. VALUE BETTING & COUPON — 7/10

### ✅ Points forts
- Cotes indépendantes en mode démo (bookmaker_error=0.025, marge 5%) — pas de raisonnement circulaire
- Kelly Criterion fractionné (quart de Kelly) — variance maîtrisée
- Pas de minimum forcé sur Kelly — si l'edge est marginal, la mise est basse
- Score de confiance basé sur Kelly (pas arbitraire)
- Recherche combinatoire pour optimiser la cote totale vers la cible (5.0)
- Déduplication par match/marché (pas deux paris incompatibles sur le même match)

### 🔴 CRITIQUE — Inversion 1X2 cascade sur le value betting
Le bug d'inversion `p_home`/`p_away` dans le Poisson impacte directement les value bets football :
```python
(f"Victoire {home}", prediction["p_home_win"], "h2h", home),
```
Si `p_home_win` est en réalité `p_away_win`, le modèle va chercher de la value sur "victoire domicile" avec la proba de l'extérieur. Cela génère des value bets **faux**.

### 🟡 Fourchette de cotes élargie
`min_odd: 1.30` à `max_odd: 4.00` — raisonnable. La cote max à 4.0 limite le risque de sélections trop improbables.

### 🟡 Pool combinatoire limité à 15
`pool = candidates[:min(len(candidates), 15)]` — raisonnable pour éviter l'explosion combinatoire (C(15,6) = 5005), mais pourrait exclure des bets de meilleure valeur si le tri initial rate.

---

## 6. BOT TELEGRAM — 8/10

### ✅ Points forts
- Format MarkdownV2 propre avec étoiles de confiance
- Fallback texte brut si MarkdownV2 échoue (dans `send_long_message` et `scheduled_coupon`)
- Découpage automatique des messages > 4000 caractères
- Job planifié quotidien avec timezone configurable
- Validation des variables numériques (heure, minute) avec fallback
- Message d'attente pendant la génération (supprimé après)
- Exécution en thread séparé (`run_in_executor`) pour ne pas bloquer

### 🟡 Commandes `/history`, `/stats`, `/result` = mortes
Comme les modules `database.py` et `backtester.py` n'existent pas, ces commandes retournent toujours "Module non disponible". L'utilisateur ne peut pas tracker ses résultats.

### 🟡 Commandes non enregistrées dans le menu Telegram
`post_init()` enregistre seulement 4 commandes (`start`, `coupon`, `status`, `aide`) mais le bot en a 7. Les commandes `history`, `stats`, `result` ne sont pas visibles dans le menu Telegram.

### 🟡 `/result` — message d'aide incomplet
```python
await update.message.reply_text(
    "ℹ️ Usage : \n"
    "Exemple : ",
```
Les placeholders sont vides — l'utilisateur ne voit pas la syntaxe attendue.

### 🟡 `asyncio.get_event_loop()` deprecated
`asyncio.get_event_loop()` est deprecated depuis Python 3.10. Utiliser `asyncio.get_running_loop()` à la place.

---

## 7. MODULES MANQUANTS — IMPACT

| Module | Statut | Impact |
|--------|--------|--------|
| `database.py` | ❌ Absent | Pas de persistance SQLite, `/history` et `/result` morts |
| `backtester.py` | ❌ Absent | Pas de rapport de performance, `/stats` mort |
| `line_movement.py` | ❌ Absent | Pas de détection de mouvements de cotes |

Le `BacktestTracker` dans `coupon_generator.py` écrit dans `coupon_history.json`, mais :
- Ce fichier est local (pas partagé entre instances Railway)
- Rien ne lit ce fichier côté bot
- Les résultats ne sont jamais enregistrés automatiquement

---

## 8. BUG CRITIQUE DÉCOUVERT

### 🔴🔴 Inversion home/away dans le modèle Poisson

**Fichier :** `coupon_generator.py`, lignes 579-581
**Gravité :** CRITIQUE — affecte toutes les prédictions football

```python
# ACTUEL (FAUX) :
p_home = float(np.sum(np.tril(matrix, -1)))  # tril = triangle inférieur = i < j = away gagne
p_away = float(np.sum(np.triu(matrix, 1)))   # triu = triangle supérieur = i > j = home gagne

# CORRECT :
p_home = float(np.sum(np.triu(matrix, 1)))   # i > j = domicile marque plus
p_draw = float(np.sum(np.diag(matrix)))       # i == j (inchangé, correct)
p_away = float(np.sum(np.tril(matrix, -1)))   # j > i = extérieur marque plus
```

**Explication :** Dans `matrix[i][j]`, `i` = buts domicile, `j` = buts extérieur.
- Le triangle supérieur (i > j) correspond aux cas où le domicile marque plus → victoire domicile
- Le triangle inférieur (i < j) correspond aux cas où l'extérieur marque plus → victoire extérieur
- Le code actuel assigne `tril` (extérieur gagne) à `p_home` — c'est inversé

**Conséquences en cascade :**
1. Les probabilités 1X2 sont inversées
2. Les value bets sont calculés avec les mauvaises probas
3. Les confiances affichées sont fausses
4. Le coupon sélectionne potentiellement les mauvais paris

---

## 9. SYNTHÈSE DES ACTIONS PRIORITAIRES

### 🔴 Priorité 1 — Bugs critiques (à corriger immédiatement)

1. **Corriger l'inversion `p_home`/`p_away`** dans `PoissonModel.predict()` — swap `tril` et `triu`
2. **Implémenter le contrôle d'accès** `ALLOWED_USERS` dans `bot.py` — middleware ou check dans chaque handler

### 🟠 Priorité 2 — Fonctionnalités cassées

3. **Créer `database.py`** — persistance SQLite pour les coupons et résultats
4. **Créer `backtester.py`** — rapports de performance basés sur la BDD
5. **Ajouter `TENNIS_PARAMS`** dans `config.py`
6. **Corriger le message `/result`** — ajouter la syntaxe dans le message d'aide
7. **Enregistrer les 7 commandes** dans `post_init()` (pas seulement 4)

### 🟡 Priorité 3 — Améliorations

8. Supprimer `bot_patched.py` (doublon)
9. Supprimer la duplication `_esc()`/`esc()` dans `bot.py`
10. Remplacer `asyncio.get_event_loop()` par `get_running_loop()`
11. Intégrer TheSportsDB et api-football dans le pipeline (ou supprimer le code mort)
12. Ajouter la forme récente football (5 derniers matchs)
13. Ajouter les stats domicile/extérieur séparées pour le Poisson
14. Implémenter les marchés corners/fautes (objectif déjà identifié)

---

## 10. ÉVOLUTION DEPUIS LES AUDITS PRÉCÉDENTS

| Audit | Date | Focus | Score |
|-------|------|-------|-------|
| v1 | 9 avril | Architecture + sécurité | 3/10 |
| v2 | 10 avril | Bugs logiques | 6→8/10 |
| v3 | 10 avril | Validité statistique | 4/10 |
| **v4** | **13 avril** | **Audit global** | **6.1/10** |

**Progrès :** Le bot est fonctionnel, la sécurité des secrets est bonne, le formatage Telegram est propre, et le pipeline Poisson est cohérent (sauf le bug d'inversion). Les corrections du 12 avril (7 bugs) ont stabilisé le bot.

**Risques restants :** Le bug d'inversion home/away est le plus critique — il fausse toutes les prédictions football. Le manque de contrôle d'accès expose le bot. Et les 3 modules manquants rendent 3 commandes inutiles.

---

*Audit réalisé le 13 avril 2026 — BetForge / APEX Bot v2.0*
