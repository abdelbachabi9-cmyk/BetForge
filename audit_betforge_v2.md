# AUDIT BETFORGE — Rapport v2
**Date :** 10/04/2026  
**Repo :** https://github.com/abdelbachabi9-cmyk/BetForge  
**Score global : 6 / 10** _(contre 3/10 à l'audit v1 — +3 points grâce aux corrections de sécurité et de stabilité)_

---

## Résumé exécutif

Depuis l'audit v1, les corrections de sécurité critique ont été appliquées avec succès : les secrets ne sont plus dans le code, le fichier `.env` exposé a été supprimé, le mode réel est activé, et plusieurs crashes ont été corrigés. Le bot est désormais fonctionnel et déployé sur Railway.

**Cependant**, une erreur logique majeure persiste : le bot génère des coupons pour les matchs de **demain** au lieu des matchs d'**aujourd'hui**. Cette erreur est présente dans 5 endroits du code et rend le coupon inutilisable pour parier le jour même.

---

## 🔴 BUGS CRITIQUES (3 problèmes)

### BUG 1 — Le bot envoie les matchs de DEMAIN, pas d'aujourd'hui
**Fichier :** `coupon_generator.py`, lignes 102, 146, 216, 252, 371  
**Fichier :** `bot.py`, ligne 172

Le bot utilise `self.tomorrow` (demain) partout où il devrait utiliser `self.today` (aujourd'hui). Résultat : quand l'utilisateur reçoit le coupon le matin du 10/04, il reçoit les matchs du **11/04** — trop tard pour parier sur les matchs d'aujourd'hui.

```python
# ❌ ACTUEL — cherche les matchs de demain
params = {"dateFrom": self.tomorrow, "dateTo": self.tomorrow}        # ligne 146
if game.get("commence_time", "")[:10] != self.tomorrow: continue     # ligne 216
if event.get("dateEvent") == self.tomorrow:                          # ligne 252
"date": self.tomorrow                                                 # ligne 371

# ✅ CORRIGÉ — cherche les matchs d'aujourd'hui
params = {"dateFrom": self.today, "dateTo": self.today}
if game.get("commence_time", "")[:10] != self.today: continue
if event.get("dateEvent") == self.today:
"date": self.today
```

**Impact :** Fonctionnalité principale incorrecte.

---

### BUG 2 — Basketball non connecté aux vraies APIs en mode réel
**Fichier :** `coupon_generator.py`, lignes 1225–1234

En mode réel, le football est bien récupéré depuis football-data.org. Mais le **basketball** reste sur les données de démo (`get_demo_data()`) — il n'y a aucun appel réel à The Odds API pour les matchs NBA ou EuroLeague, même si la clé est configurée. La méthode `fetch_odds("basketball_nba")` existe mais n'est jamais appelée dans le pipeline réel.

**Impact :** Les prédictions basketball en mode réel sont fictives.

---

### BUG 3 — Fallback silencieux vers les données démo en mode réel
**Fichier :** `coupon_generator.py`, ligne 1155

```python
# ❌ ACTUEL — en mode réel, on part quand même des données démo
data = fetcher.get_demo_data()  # Fallback si APIs non configurées
```

Même quand les APIs fonctionnent, la base de données est toujours `get_demo_data()`. Les données réelles ne viennent que **s'enrichir par-dessus**, ce qui signifie que si une API retourne 0 match (ex: jour sans compétition), le coupon continue de tourner avec des matchs inventés sans avertissement.

**Impact :** L'utilisateur peut croire parier sur de vraies données alors qu'il parie sur des données fictives.

---

## 🟠 PROBLÈMES MODÉRÉS (3 problèmes)

### PROBLÈME 4 — Pas de message "Pas de matchs aujourd'hui"
**Fichier :** `bot.py`, ligne 100

Quand le coupon est vide (aucun match trouvé), le message envoyé est :
> `"⚠️ Aucune sélection valide générée aujourd'hui."`

Ce message est trop vague. Il ne distingue pas "aucun match aujourd'hui" de "matchs trouvés mais aucune value bet". L'utilisateur ne sait pas si le bot a un problème ou si c'est normal.

---

### PROBLÈME 5 — Tennis toujours dans le pipeline
**Fichier :** `coupon_generator.py`, lignes 1236–1244

Le modèle tennis tourne encore en mode réel. The Odds API ne fournit pas de données tennis sur le tier gratuit, et football-data.org non plus. Résultat : le tennis génère des prédictions à partir de données inexistantes (liste vide → aucun pari ajouté, mais traitement inutile).

---

### PROBLÈME 6 — `requirements.txt` sans versions épinglées
**Fichier :** `requirements.txt`

```
python-telegram-bot[job-queue]
numpy
scipy
pandas
requests
```

Aucune version fixée. Un `pip install` demain pourrait installer une version incompatible et casser le bot silencieusement.

**Recommandation :**
```
python-telegram-bot[job-queue]>=20.0,<21.0
numpy>=1.24,<2.0
scipy>=1.10,<2.0
pandas>=2.0,<3.0
requests>=2.28,<3.0
```

---

## 🟡 POINTS MINEURS (3 problèmes)

### POINT 7 — Aucun retry sur les appels API
**Fichier :** `coupon_generator.py`, méthode `_get()` (ligne ~100)

Si une API répond 429 (trop de requêtes) ou 503 (indisponible), le bot abandonne immédiatement. Un système de retry avec délai exponentiel éviterait des coupons vides à cause d'une erreur temporaire.

---

### POINT 8 — `railway.toml` sans health check
**Fichier :** `railway.toml`

Le fichier configure le builder mais pas de health check. Si le bot plante silencieusement après démarrage, Railway ne le détecte pas toujours. Ajouter un `healthcheckPath` ou configurer une alerte via les logs Railway serait utile.

---

### POINT 9 — Logs insuffisants sur les erreurs API
**Fichier :** `coupon_generator.py`

Quand une API retourne une erreur (mauvaise clé, quota dépassé), le log indique `"Aucun match réel trouvé"` au lieu du code d'erreur HTTP. Difficile de diagnostiquer un problème de clé API épuisée.

---

## ✅ POINTS POSITIFS (améliorations depuis v1)

| Élément | Statut |
|---|---|
| Secrets supprimés du code | ✅ Fait |
| `.env` exposé supprimé | ✅ Fait |
| `__pycache__` supprimé | ✅ Fait |
| `.gitignore` en place | ✅ Fait |
| `DEMO_MODE=false` par défaut | ✅ Fait |
| Import `functools` propre | ✅ Fait |
| `timedelta` importé correctement | ✅ Fait |
| Crash fin de mois corrigé | ✅ Fait |
| Validation `BOT_SEND_HOUR` | ✅ Fait |
| Railway configuré avec vraies clés | ✅ Fait |
| Déploiement Railway réussi | ✅ Online |

---

## Plan de correction (appliqué dans cette session)

| # | Fichier | Action | Priorité |
|---|---|---|---|
| 1 | `coupon_generator.py` | Remplacer `self.tomorrow` → `self.today` (5 occurrences) | 🔴 Critique |
| 2 | `coupon_generator.py` | Ajouter fetch NBA/EuroLeague via Odds API en mode réel | 🔴 Critique |
| 3 | `coupon_generator.py` | Corriger le fallback démo silencieux | 🔴 Critique |
| 4 | `bot.py` | Corriger la date du coupon (aujourd'hui, pas demain) | 🔴 Critique |
| 5 | `bot.py` | Message clair "Pas de matchs aujourd'hui" | 🟠 Modéré |
| 6 | `coupon_generator.py` | Supprimer tennis du pipeline en mode réel | 🟠 Modéré |

---

## Score détaillé

| Catégorie | v1 | v2 (avant fix) | v2 (après fix) |
|---|---|---|---|
| Sécurité | 1/10 | 9/10 | 9/10 |
| Exactitude fonctionnelle | 2/10 | 3/10 | 8/10 |
| Qualité du code | 4/10 | 6/10 | 7/10 |
| Robustesse / gestion d'erreurs | 2/10 | 5/10 | 6/10 |
| Déploiement | 3/10 | 8/10 | 8/10 |
| **GLOBAL** | **3/10** | **6/10** | **8/10** |
