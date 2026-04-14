# AUDIT BETFORGE v3 — Validité Statistique & Mathématique

**Date :** 10/04/2026  
**Repo :** https://github.com/abdelbachabi9-cmyk/BetForge  
**Angle :** Validité des modèles statistiques, cohérence mathématique et viabilité de la stratégie de paris  
**Score global : 4/10** _(les maths derrière le bot posent des problèmes fondamentaux)_

---

## Résumé exécutif

Les audits v1 et v2 ont traité la sécurité, l'architecture logicielle et les bugs fonctionnels. Ce troisième audit examine un angle jamais abordé : **les fondations mathématiques et statistiques du bot sont-elles solides ?**

La réponse courte est **non**. Le bot revendique un modèle « Poisson-Dixon-Coles + ELO + Value Betting », mais l'implémentation réelle est une **approximation simplifiée** qui ne correspond pas à ce que ces noms impliquent dans la littérature statistique. Le mode démo génère un faux sentiment de rentabilité, le modèle ELO n'est jamais entraîné, et le système de backtesting ne reflète pas la stratégie de mise affichée.

---

## 🔴 PROBLÈMES CRITIQUES

### PROBLÈME 1 — Ce n'est PAS un Dixon-Coles (faux marketing)

**Fichier :** `coupon_generator.py`, classe `PoissonModel`

Le bot prétend utiliser le modèle **Dixon-Coles (1997)**, une référence en prédiction football. En réalité, il implémente un **Poisson indépendant simple** avec une correction `tau` dont le paramètre `rho = -0.13` est **codé en dur**.

Le vrai Dixon-Coles requiert :

1. Un **jeu de données historiques** de matchs (100+ matchs par ligue minimum)
2. Une **estimation par Maximum de Vraisemblance (MLE)** des paramètres d'attaque et de défense de chaque équipe, plus le paramètre rho
3. Une **pondération temporelle** (matchs récents pèsent plus lourd)

L'implémentation actuelle :

- Calcule `lambda_home = (home_goals_avg / league_avg) × (away_conceded_avg / league_avg) × league_avg × home_adv`
- Ce qui se simplifie à : `lambda_home = home_goals_avg × away_conceded_avg / league_avg × 1.1`
- Utilise `rho = -0.13` comme constante magique (la vraie valeur varie entre -0.05 et -0.20 selon la ligue et la saison)
- `league_avg_goals = 2.65` est codé en dur (la moyenne varie entre 2.4 et 3.0 selon la ligue)

**Impact :** Le modèle est fonctionnel comme prédicteur basique, mais nettement moins précis qu'un vrai Dixon-Coles. Appeler cela « Dixon-Coles » dans l'interface et la documentation est trompeur pour l'utilisateur qui se baserait sur cette réputation pour faire confiance aux prédictions.

**Recommandation :**

- Renommer en « Modèle Poisson avec correction de dépendance » (ce qu'il est réellement)
- OU implémenter un vrai Dixon-Coles avec MLE (scipy.optimize.minimize, ~50 lignes de code supplémentaires)
- Estimer `rho` par régression sur données historiques plutôt qu'une constante
- Calculer `league_avg_goals` dynamiquement depuis les données de classement (qui sont déjà récupérées)

---

### PROBLÈME 2 — Le modèle ELO n'est jamais entraîné

**Fichier :** `coupon_generator.py`, classe `EloModel`

La classe `EloModel` possède une méthode `update()` pour mettre à jour les ratings après chaque match. **Cette méthode n'est jamais appelée.** Les ratings ELO sont lus directement depuis les fixtures (données démo : `"home_elo": 1650`) et ne sont jamais ajustés.

Un système ELO a de la valeur **uniquement** s'il est entraîné sur un historique de résultats pour que les ratings convergent vers la force réelle des équipes. Sans entraînement, c'est simplement un calcul de probabilité à partir de nombres arbitraires.

En mode réel, les fixtures de basketball ne contiennent même pas de champ `home_elo` / `away_elo`, donc le modèle utilise le rating initial de 1500 pour **toutes** les équipes, ce qui donne 50/50 + home_bonus pour chaque match.

```python
# Ce qui se passe en mode réel pour TOUTES les équipes NBA :
r_home = 1500 + 50  # = 1550
r_away = 1500
p_home = 1 / (1 + 10^((1500 - 1550) / 400))  # = 0.5718
# → Chaque match NBA donne P(Home) ≈ 57% peu importe les équipes
```

**Impact :** Les prédictions basketball en mode réel sont identiques pour tous les matchs. Le bot recommande systématiquement la victoire à domicile en NBA.

**Recommandation :**

- Intégrer une source de ratings ELO externes (FiveThirtyEight, ClubELO, ou Basketball Reference)
- OU entraîner l'ELO sur les résultats récents de la saison via une API comme The Odds API (qui fournit des résultats)
- À défaut, supprimer le basketball du pipeline en mode réel (comme recommandé pour le tennis dans l'audit v2)

---

### PROBLÈME 3 — Le mode démo crée une illusion de rentabilité

**Fichier :** `coupon_generator.py`, fonction `independent_demo_odd()`

En mode démo, les cotes bookmaker sont simulées avec une erreur aléatoire de **±8%** autour de la « vraie » probabilité :

```python
bookie_estimate = true_prob + rng.uniform(-bookmaker_error, bookmaker_error)  # ±8%
```

Le problème est que les bookmakers réels des top leagues (Premier League, Liga, etc.) ont une précision de **±1-3%**. Une erreur de ±8% est irréaliste et crée artificiellement un grand nombre de « value bets ».

**Vérification par simulation (10 000 tirages) :**

| Métrique | Mode démo (±8%) | Bookmakers réels (~±2%) |
|---|---|---|
| Value bets trouvés | **~21%** des paris | **~3-5%** des paris |
| Edge moyen | **+10.5%** | **+2-4%** |

L'utilisateur qui teste le bot en mode démo voit un système qui « trouve » constamment des value bets avec des edges confortables. En mode réel, le système trouvera beaucoup moins de value bets, avec des edges beaucoup plus faibles, et probablement négatifs après prise en compte de la marge bookmaker.

**Impact :** L'expérience démo ne représente pas du tout les performances réelles. Un utilisateur qui décide de parier de l'argent réel sur la base de l'expérience démo sera déçu.

**Recommandation :**

- Réduire `bookmaker_error` à 0.02-0.03 pour simuler des bookmakers réalistes
- Ajouter un disclaimer clair dans le coupon démo : « Les edges affichés en mode démo sont ~3× supérieurs à ceux observés en mode réel »
- Afficher les statistiques de value bets trouvés en mode réel vs démo dans /stats

---

## 🟠 PROBLÈMES MODÉRÉS

### PROBLÈME 4 — Le ROI du backtesting ne reflète pas la stratégie Kelly

**Fichier :** `coupon_generator.py`, méthode `BacktestTracker.get_stats()`

Le bot affiche des mises Kelly variables (0.5% à 5.0% du bankroll) pour chaque sélection, mais le calcul du ROI dans le backtesting utilise une **mise plate de 2%** par coupon :

```python
# Dans get_stats() :
stake = 2.0  # % bankroll par défaut — ignoré la mise Kelly
total_staked += stake
if entry["result"] == "win":
    total_returned += stake * entry["total_odd"]
```

Deux problèmes :

1. Le ROI calculé ne correspond ni à la stratégie Kelly affichée, ni à la stratégie d'un parieur qui suivrait les recommandations
2. Le calcul traite le coupon comme un pari unique (1 mise pour le combiné), mais les mises Kelly sont par sélection individuelle. Un coupon combiné de 4 paris avec 1 mise ≠ 4 paris individuels avec 4 mises

**Recommandation :**

- Tracker le ROI en mode « combiné » (1 mise, cote totale) ET en mode « sélections individuelles » (n mises, n résultats)
- Utiliser les mises Kelly réelles dans le calcul du ROI

---

### PROBLÈME 5 — Le score de confiance est arbitraire et saturé

**Fichier :** `coupon_generator.py`, méthode `ValueBetSelector._confidence_score()`

La formule : `confiance = p_model × 7 + min(3, value × 30)`

Le terme `min(3, value × 30)` sature à 3 dès que `value ≥ 10%` (ce qui arrive souvent en mode démo). Résultat : le score ne discrimine pas entre un edge de 10% et un edge de 40%.

| p_model | Edge 5% | Edge 10% | Edge 20% | Edge 40% |
|---|---|---|---|---|
| 0.35 | 3.9 | 5.4 | **5.4** | **5.4** |
| 0.50 | 5.0 | 6.5 | **6.5** | **6.5** |
| 0.65 | 6.0 | 7.5 | **7.5** | **7.5** |

Les colonnes 20% et 40% sont identiques aux colonnes 10% — le score ne distingue plus rien au-delà de 10%.

**Recommandation :**

- Remplacer par un score composite basé sur des métriques standardisées : `confiance = w1 × normalize(p_model) + w2 × normalize(kelly_stake) + w3 × normalize(edge)`
- OU utiliser directement le critère de Kelly comme proxy de confiance (Kelly intègre déjà probabilité ET edge)

---

### PROBLÈME 6 — Le critère de Kelly est « clampé » de manière contre-productive

**Fichier :** `coupon_generator.py`, méthode `ValueBetSelector.kelly_stake()`

```python
stake = max(KELLY["min_stake_pct"], min(KELLY["max_stake_pct"], kelly_frac * 100))
# min_stake_pct = 0.5, max_stake_pct = 5.0
```

Quand le Kelly fractionné recommande < 0.5%, c'est que le pari a un edge marginal ou une probabilité faible. Forcer à 0.5% minimum contredit la logique même du Kelly : **ne pas surparier les situations à faible avantage**.

Le maximum de 5.0% est en revanche une bonne pratique (Kelly complet est connu pour être trop agressif).

**Recommandation :**

- Remplacer le minimum de 0.5% par 0.0% (si Kelly dit de ne pas parier, c'est un signal)
- OU filtrer les paris dont le Kelly fractionné est < 0.5% au lieu de forcer la mise à 0.5%

---

### PROBLÈME 7 — Le modèle Tennis fonctionne sur des données inexistantes

**Fichier :** `coupon_generator.py`, classe `TennisModel`

Le modèle Tennis est le plus sophistiqué (ELO + surface + forme + H2H + fatigue), mais :

1. En mode réel, **aucune API** ne fournit les données nécessaires (ranking, surface win rate, H2H, matchs récents)
2. TheSportsDB (API gratuite) ne fournit pas ces métriques détaillées
3. The Odds API (tier gratuit) ne couvre pas le tennis

Le modèle Tennis est donc **exclusivement un modèle démo** — bien conçu en théorie mais inutilisable en production.

**Recommandation :**

- Désactiver le tennis en mode réel (déjà recommandé en audit v2)
- OU intégrer une API tennis payante (API-Tennis, Sportradar) pour alimenter le modèle

---

## 🟡 POINTS MINEURS

### POINT 8 — `league_avg_goals` devrait être dynamique

La constante `self.league_avg_goals = 2.65` est utilisée pour normaliser les forces d'attaque/défense. En réalité, la moyenne varie significativement :

- Bundesliga 2024-25 : ~3.1 buts/match
- Serie A 2024-25 : ~2.6 buts/match
- Ligue 1 2024-25 : ~2.5 buts/match

Utiliser 2.65 pour toutes les ligues introduit un biais systématique : les prédictions surestiment les buts en Serie A et Ligue 1, et les sous-estiment en Bundesliga.

**Recommandation :** Calculer `league_avg_goals` à partir des données de classement de chaque ligue (goals_for total / matches joués), données déjà disponibles via `fetch_football_standings()`.

---

### POINT 9 — Le bonus `-0.5` dans le CouponBuilder est un « magic number »

**Fichier :** `coupon_generator.py`, méthode `CouponBuilder.build()`, ligne 1014

```python
if self.min_total <= total <= self.max_total:
    dist -= 0.5  # Bonus si dans la fourchette
```

Ce bonus de -0.5 est arbitraire et crée un saut discontinu dans la fonction de scoring. Deux coupons ayant des distances respectives de 0.4 (hors fourchette) et 0.6 (dans fourchette) obtiennent les scores 0.4 et 0.1. Le second gagne malgré une cote plus éloignée de la cible.

**Recommandation :** Utiliser une fonction de scoring continue, par exemple une pénalité gaussienne centrée sur `target_odd` avec une zone de tolérance.

---

### POINT 10 — Les coupons combinés ont une variance extrême

Le bot cible une cote totale de ~5.0 (probabilité implicite ~20%). Cela signifie que **le coupon perd 4 fois sur 5**, même si l'edge est positif.

Avec un edge réaliste de +5% par sélection et 4 sélections indépendantes, l'espérance mathématique du coupon combiné est :

```
E[combiné] = (1.05)^4 = 1.2155 → edge combiné ≈ +21.6%
P(win) ≈ (0.55 × 0.50 × 0.60 × 0.45) ≈ 7.4% (variable selon les paris)
```

L'edge est positif à long terme, mais la variance est considérable. Il faut **~50-100 coupons** (2-3 mois de paris quotidiens) pour que l'avantage statistique se manifeste de manière significative.

Le bot ne communique pas cette réalité à l'utilisateur. Le message « Jouez responsablement » est insuffisant — il faudrait expliquer le concept de variance et de bankroll management.

**Recommandation :**

- Ajouter dans /aide une section sur la variance des coupons combinés
- Afficher le nombre minimum de coupons nécessaires pour avoir confiance dans un ROI positif
- Proposer une alternative : paris simples (non combinés) avec mises Kelly individuelles

---

## Score détaillé

| Critère | Note | Commentaire |
|---|---|---|
| Exactitude du modèle Poisson | 5/10 | Fonctionnel mais mal étiqueté (pas un vrai Dixon-Coles) |
| Modèle ELO basketball | 2/10 | Jamais entraîné, identique pour tous les matchs en mode réel |
| Modèle Tennis | 6/10 | Bien conçu en théorie, aucune donnée réelle disponible |
| Stratégie Value Betting | 4/10 | Concept correct, mais mode démo trompeusement optimiste |
| Critère de Kelly | 6/10 | Implémentation correcte, clamp min problématique |
| Score de confiance | 3/10 | Arbitraire, saturé au-delà de 10% d'edge |
| Backtesting / ROI | 3/10 | Ne reflète pas la stratégie Kelly affichée |
| Communication du risque | 3/10 | Ne mentionne pas la variance des combinés |
| **GLOBAL** | **4/10** | **Fondations mathématiques insuffisantes pour un outil de pari** |

---

## Plan de correction prioritaire

| # | Action | Impact | Effort |
|---|---|---|---|
| 1 | Renommer « Dixon-Coles » en « Poisson avec correction de dépendance » ou implémenter le vrai MLE | Honnêteté envers l'utilisateur | Faible (renommage) ou Élevé (vrai MLE) |
| 2 | Supprimer basketball du mode réel (ou intégrer des ratings ELO externes) | Évite des prédictions uniformes (57% Home pour tous) | Faible |
| 3 | Réduire `bookmaker_error` de 0.08 à 0.02-0.03 en mode démo | Expérience démo réaliste | Trivial |
| 4 | Calculer `league_avg_goals` dynamiquement par ligue | Précision des prédictions | Faible |
| 5 | Corriger le ROI du backtesting pour refléter la stratégie réelle | Métriques fiables | Moyen |
| 6 | Ajouter un avertissement sur la variance des coupons combinés | Responsabilité envers l'utilisateur | Faible |
| 7 | Remplacer le score de confiance par un score basé sur Kelly | Scoring cohérent et justifié | Faible |

---

*Rapport généré le 10 avril 2026. Audit réalisé par vérification mathématique directe (reproduction des calculs avec assertions numériques).*
