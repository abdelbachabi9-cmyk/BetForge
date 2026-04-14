# Audit Complet du Dépôt BetForge (APEX Bot)

**Dépôt :** [github.com/abdelbachabi9-cmyk/BetForge](https://github.com/abdelbachabi9-cmyk/BetForge)  
**Date de l'audit :** 9 avril 2026  
**Auteur du dépôt :** rayann-epitech (Rayann' BCH)  
**Création du dépôt :** 21 mars 2026  
**Nombre de commits :** 5 (tous le même jour)  
**Langage :** Python 3.8+  
**Plateforme de déploiement :** Railway  

---

## 1. Architecture et Structure du Projet

### Observations

Le projet est un bot Telegram de prédiction sportive (paris) basé sur des modèles statistiques (Poisson-Dixon-Coles, ELO, Value Betting). La structure est plate, sans sous-dossiers :

```
├── __pycache__/          ← Commité par erreur
├── .env                  ← SECRETS EXPOSÉS
├── Procfile              ← Config Railway
├── README.md             ← Documentation
├── bot.py                ← Bot Telegram (394 lignes)
├── config.py             ← Configuration et clés API
├── coupon_generator.py   ← Moteur de prédiction (~900 lignes)
├── railway.toml          ← Config Railway
└── requirements.txt      ← Dépendances Python
```

**Points positifs :**

- Séparation claire des responsabilités : bot (interface Telegram), moteur de génération (coupon_generator), et configuration (config).
- Architecture compréhensible pour un projet de cette taille.
- README bien structuré avec instructions de déploiement.

**Points négatifs :**

- `coupon_generator.py` est un fichier monolithique de ~900 lignes contenant 5 classes (DataFetcher, PoissonModel, EloModel, ValueBetSelector, CouponBuilder) qui devraient être dans des modules séparés.
- Absence de dossier `tests/`, `src/`, ou toute organisation modulaire.
- Le dossier `__pycache__/` est versionné (artefact de compilation Python).
- Aucun fichier `.gitignore`.

### Suggestions

- **🔴 Critique** — Créer un `.gitignore` incluant au minimum : `__pycache__/`, `.env`, `*.pyc`, `*.pyo`, `__pycache__`, `.venv/`.
- **🔴 Critique** — Supprimer `__pycache__/` du dépôt avec `git rm -r --cached __pycache__/`.
- **🟠 Important** — Refactorer `coupon_generator.py` en plusieurs modules (par ex. `models/poisson.py`, `models/elo.py`, `data/fetcher.py`, `betting/selector.py`, `betting/builder.py`).
- **🟡 Nice-to-have** — Adopter une structure de package Python standard avec `src/apex/` et un `__init__.py`.

---

## 2. Qualité du Code

### Observations

**Points positifs :**

- Code bien commenté avec des docstrings détaillées en français.
- Utilisation de type hints (typing) dans `coupon_generator.py`.
- Bonne gestion des imports manquants avec messages d'erreur explicites.
- Bannière ASCII et logging structuré avec emojis pour la lisibilité des logs.
- Respect des conventions PEP 8 dans l'ensemble.
- Utilisation de constantes via `config.py` plutôt que des valeurs magiques.

**Points négatifs :**

- Utilisation de `__import__("functools")` inline dans `format_coupon_telegram()` au lieu d'un import en tête de fichier — mauvaise pratique.
- Utilisation de `__import__("datetime")` inline dans `generate_coupon_message()` — même problème.
- Dans `cmd_status`, calcul naïf de la date du lendemain (`next_send.replace(day=next_send.day + 1)`) qui plante en fin de mois.
- La fonction `esc()` pour échapper les caractères MarkdownV2 est définie comme fonction imbriquée dans `format_coupon_telegram` alors qu'elle pourrait être un utilitaire réutilisable.
- Pas de validation des entrées utilisateur sur les variables d'environnement (BOT_SEND_HOUR pourrait être une valeur invalide).
- `DEMO_MODE` est surchargé à la fois dans `.env`, `config.py`, et `bot.py` avec une logique de priorité confuse.

### Suggestions

- **🟠 Important** — Remplacer les `__import__()` inline par des imports standard en tête de fichier.
- **🟠 Important** — Corriger le bug du calcul de date fin de mois dans `cmd_status` en utilisant `timedelta(days=1)`.
- **🟠 Important** — Ajouter une validation des variables d'environnement au démarrage (vérifier que `BOT_SEND_HOUR` est entre 0 et 23, etc.).
- **🟡 Nice-to-have** — Extraire `esc()` comme utilitaire partagé.
- **🟡 Nice-to-have** — Simplifier la logique `DEMO_MODE` en une seule source de vérité (variable d'environnement uniquement).

---

## 3. Sécurité

### Observations

**🔴🔴🔴 ALERTE CRITIQUE — SECRETS EXPOSÉS EN CLAIR DANS UN DÉPÔT PUBLIC 🔴🔴🔴**

Le fichier `.env` est commité dans le dépôt **public** et contient des secrets réels :

- `TELEGRAM_TOKEN` — Token du bot Telegram (permet le contrôle total du bot)
- `TELEGRAM_CHAT_ID` — ID du chat cible

Le fichier `config.py` contient également des clés API en dur :

- `football_data` : clé API football-data.org en clair
- `odds_api` : clé API the-odds-api.com en clair

**Autres problèmes de sécurité :**

- Pas de `.gitignore` → tout fichier sensible ajouté par mégarde sera commité.
- Pas de `.env.example` séparé du vrai `.env` — le fichier `.env` lui-même sert de "template" avec les vrais secrets.
- Aucun mécanisme de rate limiting sur les commandes du bot Telegram → vulnérable aux abus (DoS).
- Les erreurs d'API sont loguées avec des détails potentiellement sensibles (`exc_info=True`).
- Pas de vérification que les commandes Telegram proviennent d'utilisateurs autorisés (n'importe qui peut utiliser le bot).
- Les appels API HTTP dans `DataFetcher._get()` ne vérifient pas explicitement les certificats SSL (utilise les défauts de `requests`, ce qui est correct, mais pas de `verify=True` explicite).

### Suggestions

- **🔴 Critique** — **IMMÉDIATEMENT** : Révoquer le token Telegram via @BotFather et générer un nouveau token.
- **🔴 Critique** — **IMMÉDIATEMENT** : Régénérer toutes les clés API (football-data.org, the-odds-api.com).
- **🔴 Critique** — Supprimer le fichier `.env` du dépôt et de l'historique Git (`git filter-branch` ou BFG Repo-Cleaner).
- **🔴 Critique** — Déplacer TOUTES les clés API de `config.py` vers des variables d'environnement.
- **🔴 Critique** — Créer un `.gitignore` avec `.env` en première ligne.
- **🟠 Important** — Ajouter un mécanisme d'authentification sur le bot (whitelist de chat_id autorisés).
- **🟠 Important** — Implémenter un rate limiter sur les commandes (`/coupon` est coûteux en ressources).
- **🟡 Nice-to-have** — Utiliser un outil comme `python-dotenv` pour charger les variables d'environnement de manière standard.
- **🟡 Nice-to-have** — Activer GitHub Secret Scanning sur le dépôt.

---

## 4. Performances

### Observations

- La génération du coupon est exécutée dans un thread séparé via `run_in_executor()` pour ne pas bloquer la boucle asyncio du bot — bonne pratique.
- Le message est découpé intelligemment via `split_message()` si > 4000 caractères — bonne gestion des limites Telegram.
- Les appels API dans `DataFetcher` ont un timeout configuré (10s) et un mécanisme de retry (2 tentatives) — correct.
- Cependant, les appels API sont séquentiels : chaque compétition football est récupérée une par une, ce qui ralentit le pipeline.
- Le modèle Poisson calcule une matrice de scores complète à chaque prédiction (boucle 0→10 pour home et away, soit 121 calculs) — acceptable mais non optimisé.
- Pas de cache : si plusieurs utilisateurs demandent `/coupon` dans la même minute, le pipeline complet est relancé à chaque fois.

### Suggestions

- **🟠 Important** — Implémenter un cache en mémoire du coupon (ex. : valide pendant 1 heure) pour éviter de relancer le pipeline à chaque `/coupon`.
- **🟠 Important** — Paralléliser les appels API avec `asyncio.gather()` ou `concurrent.futures.ThreadPoolExecutor`.
- **🟡 Nice-to-have** — Précalculer le coupon quotidien dans le job planifié et servir la version en cache aux commandes `/coupon`.
- **🟡 Nice-to-have** — Utiliser `aiohttp` au lieu de `requests` pour des appels HTTP non-bloquants natifs.

---

## 5. Tests et Couverture

### Observations

**Aucun test n'existe dans le dépôt.** Pas de dossier `tests/`, pas de fichier `test_*.py`, pas de configuration `pytest` ou `unittest`. La couverture de tests est de **0%**.

Le projet contient pourtant plusieurs composants complexes et testables :

- Modèle de Poisson : calculs mathématiques vérifiables.
- Modèle ELO : mise à jour des ratings et probabilités.
- ValueBetSelector : logique de filtrage et sélection.
- CouponBuilder : optimisation de la cote totale.
- Formatage MarkdownV2 : échappement des caractères spéciaux.
- DataFetcher : appels API mockables.

### Suggestions

- **🔴 Critique** — Créer un framework de tests avec `pytest` et ajouter au minimum des tests unitaires pour les modèles statistiques (Poisson, ELO).
- **🟠 Important** — Ajouter des tests d'intégration pour le pipeline complet en mode démo.
- **🟠 Important** — Configurer `pytest-cov` pour mesurer la couverture.
- **🟡 Nice-to-have** — Viser une couverture > 70% sur les modules critiques (`coupon_generator.py`, `config.py`).
- **🟡 Nice-to-have** — Ajouter des tests de régression pour le formatage Telegram MarkdownV2 (source fréquente de bugs).

---

## 6. Dépendances

### Observations

Fichier `requirements.txt` :

```
numpy>=1.21.0
scipy>=1.7.0
pandas>=1.3.0
requests>=2.26.0
python-telegram-bot[job-queue]>=20.0
```

**Problèmes identifiés :**

- Les versions sont spécifiées avec `>=` sans borne supérieure → risque de breaking changes lors des mises à jour automatiques.
- Pas de fichier `requirements.lock` ou `Pipfile.lock` pour garantir la reproductibilité des builds.
- `scipy` est importée dans `coupon_generator.py` mais son utilisation n'est pas évidente dans les extraits lus — possiblement sous-utilisée ou importée sans nécessité.
- `pandas` est utilisé uniquement pour un `to_DataFrame()` final dans `CouponBuilder` — dépendance lourde pour un usage minimal.
- Pas de scan de vulnérabilités connu (pas de Dependabot, pas de `safety`, pas de `pip-audit`).

### Suggestions

- **🟠 Important** — Pinner les versions majeures (ex. : `numpy>=1.21.0,<2.0.0`) ou utiliser un lockfile.
- **🟠 Important** — Activer Dependabot sur le dépôt GitHub pour les alertes de vulnérabilités.
- **🟡 Nice-to-have** — Évaluer si `pandas` et `scipy` sont vraiment nécessaires ; les remplacer par des calculs natifs réduirait la taille du déploiement.
- **🟡 Nice-to-have** — Migrer vers `pyproject.toml` + `pip-tools` pour une gestion moderne des dépendances.

---

## 7. CI/CD et Bonnes Pratiques DevOps

### Observations

**Aucun pipeline CI/CD n'est configuré.** Pas de GitHub Actions, pas de workflows `.github/workflows/`. Le déploiement se fait directement via push sur `main` → Railway détecte et redéploie automatiquement.

- Pas de branche de développement (`dev`) — tout est poussé directement sur `main`.
- 5 commits tous datés du 21 mars 2026 avec des messages de type correctif rapide (``fix: ...``) — aucune review de code.
- Pas de protection de branche configurée.
- Pas de linting automatisé (flake8, ruff, black).
- Pas de scanning de sécurité automatisé.
- Le `Procfile` et `railway.toml` sont correctement configurés pour un worker longue durée avec politique de redémarrage en cas d'échec.

### Suggestions

- **🟠 Important** — Créer un workflow GitHub Actions minimal : lint (ruff/flake8) + tests (pytest) à chaque push/PR.
- **🟠 Important** — Activer la protection de la branche `main` (require PR reviews, require status checks).
- **🟠 Important** — Adopter un workflow Git basique (feature branches + PR + review).
- **🟡 Nice-to-have** — Ajouter un job de scanning de sécurité (`pip-audit`, `bandit`) dans le CI.
- **🟡 Nice-to-have** — Ajouter un formatter automatique (`black` ou `ruff format`) avec pre-commit hooks.
- **🟡 Nice-to-have** — Configurer des déploiements staging/production séparés sur Railway.

---

## 8. Documentation

### Observations

**Points positifs :**

- Le `README.md` est complet et bien organisé avec des instructions pas-à-pas pour : créer le bot Telegram, déployer sur Railway, tester en local, et utiliser les commandes.
- Un fichier `.env.example` est mentionné dans le README (mais c'est en fait le `.env` réel qui sert de template — problème de sécurité).
- Les docstrings dans le code sont détaillées et en français.
- Les modèles statistiques utilisés sont documentés dans le README.

**Points négatifs :**

- Pas de documentation d'architecture ou de design du système.
- Pas de CHANGELOG.
- Pas de CONTRIBUTING.md.
- Pas de documentation API (comment les modèles Poisson/ELO fonctionnent exactement, quels paramètres les influencent).
- Le README mélange le nom "APEX" et "BetForge" — incohérence de nommage.

### Suggestions

- **🟠 Important** — Créer un vrai `.env.example` avec des valeurs placeholder (``TELEGRAM_TOKEN=votre_token_ici``) et supprimer le `.env` réel.
- **🟡 Nice-to-have** — Harmoniser le nommage : choisir entre "APEX" et "BetForge".
- **🟡 Nice-to-have** — Ajouter un CHANGELOG.md pour suivre les évolutions.
- **🟡 Nice-to-have** — Documenter les modèles statistiques dans un fichier dédié (ex. `docs/models.md`).

---

## Résumé Exécutif

### Score global : 3/10

| Catégorie | Note | Commentaire |
|---|---|---|
| Architecture | 5/10 | Lisible mais monolithique |
| Qualité du code | 6/10 | Bien commenté, quelques bugs et anti-patterns |
| **Sécurité** | **1/10** | **Secrets exposés dans un dépôt public — critique** |
| Performances | 5/10 | Correcte, manque de cache et parallélisation |
| Tests | 0/10 | Aucun test |
| Dépendances | 4/10 | Non pinnées, pas de scan de vulnérabilités |
| CI/CD | 1/10 | Inexistant |
| Documentation | 6/10 | README correct, incohérences de nommage |

### Actions prioritaires (Top 5)

1. **🔴 URGENCE ABSOLUE** — Révoquer immédiatement tous les tokens et clés API exposés (Telegram, football-data.org, the-odds-api.com), puis purger l'historique Git.
2. **🔴 CRITIQUE** — Créer un `.gitignore`, supprimer `.env` et `__pycache__/` du dépôt, déplacer les clés API dans des variables d'environnement exclusivement.
3. **🔴 CRITIQUE** — Écrire des tests unitaires pour les modèles statistiques.
4. **🟠 IMPORTANT** — Mettre en place un pipeline CI/CD minimal (lint + tests + scan sécurité).
5. **🟠 IMPORTANT** — Refactorer `coupon_generator.py` en modules séparés et ajouter un cache pour le coupon.

---

*Rapport généré le 9 avril 2026 par audit automatisé.*
