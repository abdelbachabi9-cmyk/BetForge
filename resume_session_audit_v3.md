# Résumé de Session — Application des Corrections Audit v3

**Date :** 10 avril 2026  
**Projet :** BetForge / APEX Bot  
**Repo :** https://github.com/abdelbachabi9-cmyk/BetForge  
**Déploiement :** Railway (successful-quietude, worker, us-east4)  
**Objectif :** Appliquer les corrections statistiques et mathématiques identifiées dans l'audit v3

---

## Contexte

L'audit v3 (validité statistique & mathématique) avait attribué un score de **4/10** au bot et identifié 7 problèmes. Cette session a porté sur l'implémentation des corrections retenues : C1, C3, C4, C6 et C7.

---

## Corrections appliquées

### C1 — Renommage Dixon-Coles → Poisson (correction scores faibles)

**Problème :** Le bot revendiquait un modèle « Dixon-Coles » alors que l'implémentation est un Poisson indépendant simple avec correction tau à rho fixe — pas un vrai MLE Dixon-Coles.

**Correction :**
- **coupon_generator.py** : 9 occurrences de "Dixon-Coles" renommées en "Poisson (correction scores faibles)"
- **bot.py** : 3 occurrences de "Poisson-Dixon-Coles" renommées en "Poisson (correction scores faibles)"

**Impact :** Honnêteté intellectuelle — le nom du modèle reflète maintenant ce qu'il fait réellement.

---

### C3 — Réduction du bruit bookmaker en mode démo (±5% → ±2%)

**Problème :** Le mode démo générait des cotes fictives avec un bruit de ±5%, créant artificiellement des "value bets" inexistants et donnant une fausse impression de rentabilité.

**Correction dans coupon_generator.py :**
```python
# Avant
noise = rng.uniform(0.95, 1.05)

# Après
noise = rng.uniform(0.98, 1.02)
```

**Impact :** Le mode démo produit des résultats beaucoup plus réalistes. Les faux value bets sont fortement réduits.

---

### C4 — league_avg_goals dynamique par ligue

**Problème :** La moyenne de buts par ligue était codée en dur à 2.65, valeur incorrecte pour certaines ligues (Ligue 1 ≈ 2.4, Bundesliga ≈ 3.1).

**Correction :**
- **config.py** : Ajout du paramètre `default_league_avg_goals: 2.65` dans `POISSON_PARAMS`
- **coupon_generator.py** : La classe `PoissonModel` accepte désormais un paramètre `league_avg_goals`. La valeur est calculée dynamiquement à partir des données de classement (`standings`) de chaque ligue. Formule : `total_goals / total_matches` si données disponibles, sinon fallback sur la valeur par défaut.

**Impact :** Les probabilités Poisson sont calibrées par ligue, améliorant la précision des prédictions.

---

### C6 — Avertissement de variance

**Problème :** Aucun avertissement sur la variance naturelle des paris sportifs. Un utilisateur pouvait croire qu'un seul coupon devait être gagnant.

**Correction dans bot.py :**
- Ajout dans la commande `/aide` :
  > 🔉 *Variance : ~20% de chances de gain par coupon. L'edge se manifeste sur 50-100 coupons.*
- Même message ajouté dans le footer de chaque coupon généré

**Impact :** Gestion des attentes utilisateur. Le bot communique clairement que l'avantage statistique se mesure sur le long terme.

---

### C7 — Confidence scoring basé sur le critère de Kelly

**Problème :** Le score de confiance (0-10) utilisait une formule arbitraire sans fondement mathématique.

**Correction :**
- **config.py** : Nouvelle section `KELLY` avec `fraction: 0.25` (Kelly fractionnel) et `max_stake_pct: 5.0`
- **coupon_generator.py** : Nouvelle méthode `_confidence_score()` basée sur le critère de Kelly :

```python
def _confidence_score(self, p_model, value, odd=2.0):
    b = odd - 1
    q = 1 - p_model
    kelly_full = (b * p_model - q) / b
    kelly_frac = kelly_full * KELLY["fraction"]  # 0.25×
    score = min(10.0, (kelly_frac * 100) / KELLY["max_stake_pct"] * 10)
    return round(score, 1)
```

**Impact :** Le score de confiance a désormais un fondement mathématique solide. Un score élevé signifie que le Kelly Criterion recommande une mise plus importante, ce qui traduit un vrai edge perçu.

---

## Fichiers modifiés et commits

| Fichier | Commit | Statut |
|---|---|---|
| `config.py` | `fix(config): add KELLY params, low_score_rho, dynamic league_avg_goals` | ✅ Déployé |
| `coupon_generator.py` | `Audit v3: Corrections stats/maths (Poisson, Kelly, demo noise, league_avg dynamique)` | ✅ Déployé |
| `bot.py` | `Audit v3: bot.py corrections (Poisson rename, variance warning)` | ✅ Déployé |

---

## Méthode de déploiement

Les fichiers ont été injectés directement dans l'éditeur GitHub via le navigateur Chrome, en utilisant une stratégie d'injection base64 par chunks (nécessaire pour contourner les limitations de taille de CodeMirror 6). Chaque fichier a été encodé en base64, découpé en chunks de 8000 caractères, injecté progressivement dans l'éditeur, puis décodé et collé via `document.execCommand('insertText')`.

Le push sur la branche `main` a déclenché automatiquement le déploiement sur Railway.

---

## Vérification du déploiement

Les trois commits sont **ACTIVE** sur Railway (service worker, projet successful-quietude). Le statut final est **Deployment successful** pour chacun.

---

## Corrections NON implémentées (hors scope de cette session)

- **C2 — ELO fantôme** : Le système ELO existe dans le code mais n'est jamais entraîné sur des données réelles. Nécessiterait une source de données historiques et un pipeline d'entraînement.
- **C5 — Backtesting biaisé** : Le backtesting simule des résultats sans refléter la stratégie de mise réelle. Nécessiterait une refonte du module de simulation.

---

## Score estimé post-corrections

| Critère | Avant | Après |
|---|---|---|
| Honnêteté du modèle (C1) | 🔴 | 🟢 |
| Réalisme mode démo (C3) | 🔴 | 🟡 |
| Calibration par ligue (C4) | 🔴 | 🟢 |
| Communication variance (C6) | 🔴 | 🟢 |
| Fondement du scoring (C7) | 🔴 | 🟢 |
| ELO entraîné (C2) | 🔴 | 🔴 |
| Backtesting réaliste (C5) | 🔴 | 🔴 |

**Score estimé : 6.5/10** (contre 4/10 avant corrections). Les deux points restants (C2, C5) nécessitent des données historiques et une refonte plus profonde.
