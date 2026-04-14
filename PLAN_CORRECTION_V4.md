# PLAN DE CORRECTION ULTRA-DÉTAILLÉ — BetForge / APEX Bot v4

**Date :** 13 avril 2026
**Basé sur :** Audit v4 global + Audit GitHub (repo `abdelbachabi9-cmyk/BetForge`) + Audit Railway (service `successful-quietude`)
**Objectif :** Corriger TOUS les problèmes identifiés sans en créer de nouveaux, dans un ordre corrélé.

---

## CONSTAT CLÉS DE L'AUDIT GITHUB / RAILWAY

| Découverte | Impact |
|-----------|--------|
| `database.py`, `backtester.py`, `line_movement.py` **EXISTENT sur GitHub** mais pas dans les fichiers locaux | Les fichiers locaux sont désynchronisés du repo — l'audit initial surestimait les manques |
| `config.py` GitHub = **313 lignes** (vs 183 local) — contient STATS_MARKETS, LEAGUE_HOME_ADVANTAGE, LEAGUE_AVG_GOALS, DATABASE, LINE_MOVEMENT, DISPLAY | Le config déployé est bien plus complet que la copie locale |
| `coupon_generator.py` GitHub = mis à jour avec **StatsModel** (corners, fautes, cartons, tirs) | L'ajout marchés stats est déjà commencé |
| **Token Telegram visible dans les logs Railway** (URLs de polling en clair) | FUITE DE SÉCURITÉ — le token `bot8655664704:AAFI...` apparaît dans chaque ligne de log |
| Railway **8 jours / $3.75 restants** (Limited Trial) | Le bot va s'arrêter sans upgrade |
| **1 change pending** non déployé sur Railway | Désynchronisation entre repo et déploiement |
| `bot.py` GitHub = **identique** au local — AUCUN des bugs bot n'est corrigé | Les bugs identifiés dans l'audit sont bien présents en production |

---

## ORDRE D'EXÉCUTION DES TÂCHES

Les tâches sont ordonnées par **dépendances** pour éviter qu'une correction casse une autre.

```
PHASE 1 — SÉCURITÉ CRITIQUE (bloquante)
  T1: Token dans les logs
  T2: Contrôle d'accès ALLOWED_USERS
  T3: Régénérer le token Telegram (le token actuel est compromis)

PHASE 2 — BUG CRITIQUE MATHÉMATIQUE
  T4: Inversion p_home/p_away dans PoissonModel

PHASE 3 — CORRECTIONS BOT.PY (dépend de T2)
  T5: Compléter post_init (7 commandes)
  T6: Corriger /result message d'aide
  T7: Supprimer duplication _esc/esc
  T8: Remplacer asyncio.get_event_loop() par get_running_loop()
  T9: Supprimer bot_patched.py

PHASE 4 — CORRECTIONS CONFIG.PY
  T10: Ajouter TENNIS_PARAMS dans config.py GitHub
  T11: Vérifier cohérence STATS_MARKETS vs coupon_generator.py

PHASE 5 — CORRECTIONS COUPON_GENERATOR.PY (dépend de T4, T10)
  T12: Intégrer LEAGUE_HOME_ADVANTAGE dynamique dans PoissonModel
  T13: Vérifier que StatsModel utilise correctement les nouvelles config
  T14: Supprimer BacktestTracker JSON (remplacé par database.py SQLite)

PHASE 6 — INTÉGRATION MODULES EXISTANTS (dépend de T14)
  T15: Connecter database.py au pipeline run_pipeline()
  T16: Vérifier backtester.py et son intégration avec bot.py

PHASE 7 — NETTOYAGE & QUALITÉ
  T17: Nettoyer les fichiers .txt dupliqués du repo local
  T18: Ajouter un GitHub Actions workflow (lint + tests)
  T19: Mettre à jour README avec les nouvelles commandes

PHASE 8 — VÉRIFICATION FINALE
  T20: Audit de régression — vérifier que rien n'est cassé
```

---

## PHASE 1 — SÉCURITÉ CRITIQUE

### T1 — Supprimer le token Telegram des logs Railway

**Problème :** La librairie `python-telegram-bot` logue les URLs des requêtes HTTP, qui contiennent le token dans le chemin (`/bot<TOKEN>/getUpdates`). Chaque ligne de log Railway expose le token en clair.

**Fichier :** `bot.py`
**Priorité :** CRITIQUE
**Dépendances :** Aucune

**Prompt de tâche :**
```
TÂCHE T1 — Supprimer le token Telegram des logs Railway

Contexte : Les logs Railway affichent les URLs complètes des requêtes Telegram, exposant le token dans chaque ligne. La librairie python-telegram-bot v21 utilise httpx en interne, et c'est le logger httpx qui affiche les URLs.

Action à faire dans bot.py, APRÈS la ligne `logging.basicConfig(...)` (ligne 74-78) :

Ajouter ces lignes pour filtrer les loggers qui exposent le token :

    # Empêcher httpx/httpcore de logger les URLs contenant le token
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext._updater").setLevel(logging.WARNING)

Vérification : Après déploiement, les logs Railway ne doivent plus afficher de lignes contenant "bot8655664704" ou "/getUpdates".

ATTENTION : Ne PAS toucher au logger "APEX-Bot" — seuls les loggers de librairies tierces doivent être réduits.
```

---

### T2 — Implémenter le contrôle d'accès ALLOWED_USERS

**Problème :** `config.py` définit `ALLOWED_USERS` mais `bot.py` ne l'utilise jamais. N'importe qui peut utiliser le bot, y compris `/result` qui modifie l'état.

**Fichier :** `bot.py`
**Priorité :** CRITIQUE
**Dépendances :** Aucune

**Prompt de tâche :**
```
TÂCHE T2 — Implémenter le contrôle d'accès ALLOWED_USERS dans bot.py

Contexte : config.py définit ALLOWED_USERS (liste d'entiers = Telegram user IDs). bot.py ne vérifie jamais cette liste. Le bot est ouvert à tous.

Actions :

1. Dans la section imports de bot.py (après ligne 49), ajouter :
   from config import ALLOWED_USERS

2. Après la section "Variables d'environnement" (après ligne 111), ajouter :

    def is_authorized(update: Update) -> bool:
        """Vérifie si l'utilisateur est autorisé."""
        if not ALLOWED_USERS:
            return True  # Pas de whitelist = ouvert à tous
        user_id = update.effective_user.id if update.effective_user else None
        return user_id in ALLOWED_USERS

3. Au DÉBUT de chaque handler de commande (cmd_start, cmd_coupon, cmd_status, cmd_aide, cmd_history, cmd_stats, cmd_result), ajouter :

    if not is_authorized(update):
        await update.message.reply_text("⛔ Accès non autorisé\\.")
        return

4. Ajouter un log de sécurité dans is_authorized si l'accès est refusé :
    logger.warning(f"Accès refusé pour user_id={user_id}")

IMPORTANT : Utiliser update.effective_user.id (entier), JAMAIS update.effective_user.username (string manipulable).
NE PAS toucher à scheduled_coupon (c'est un job interne, pas un handler utilisateur).
```

---

### T3 — Régénérer le token Telegram

**Problème :** Le token `bot8655664704:AAFIu1OIzUZLIjC70_t82qMRUP32fLYVmh4` a été exposé dans les logs Railway (visibles dans le dashboard). Il doit être considéré comme compromis.

**Priorité :** CRITIQUE
**Dépendances :** T1 (filtrage des logs doit être en place AVANT de mettre le nouveau token)

**Prompt de tâche :**
```
TÂCHE T3 — Régénérer le token Telegram (MANUELLE)

⚠️ CETTE TÂCHE EST MANUELLE — elle ne peut pas être automatisée.

Étapes :
1. Ouvrir Telegram → chercher @BotFather
2. Envoyer /revoke
3. Sélectionner le bot APEX
4. BotFather génère un NOUVEAU token
5. Copier ce nouveau token
6. Aller sur Railway → projet successful-quietude → Variables
7. Mettre à jour TELEGRAM_TOKEN avec le nouveau token
8. Redéployer (le commit T1 doit être déjà poussé pour que le nouveau token ne fuite pas dans les logs)

IMPORTANT : S'assurer que T1 est déployé AVANT de mettre le nouveau token.
L'ancien token reste utilisable tant qu'il n'est pas révoqué.
```

---

## PHASE 2 — BUG CRITIQUE MATHÉMATIQUE

### T4 — Corriger l'inversion p_home/p_away dans PoissonModel

**Problème :** Dans `coupon_generator.py`, `PoissonModel.predict()` assigne `np.tril` (triangle inférieur = extérieur gagne) à `p_home` et `np.triu` (triangle supérieur = domicile gagne) à `p_away`. C'est inversé.

**Fichier :** `coupon_generator.py` (GitHub version)
**Priorité :** CRITIQUE
**Dépendances :** Aucune (correction isolée, 2 lignes)

**Prompt de tâche :**
```
TÂCHE T4 — Corriger l'inversion p_home/p_away dans PoissonModel.predict()

Fichier : coupon_generator.py
Méthode : PoissonModel.predict()

CONTEXTE MATHÉMATIQUE :
La matrice matrix[i][j] représente P(domicile marque i buts, extérieur marque j buts).
- Triangle supérieur (i > j) = domicile marque plus = VICTOIRE DOMICILE
- Diagonale (i == j) = MATCH NUL
- Triangle inférieur (i < j) = extérieur marque plus = VICTOIRE EXTÉRIEUR

np.triu(matrix, 1) = somme du triangle supérieur = P(home win)
np.tril(matrix, -1) = somme du triangle inférieur = P(away win)

CORRECTION : Dans la méthode predict(), trouver ces lignes :

    p_home = float(np.sum(np.tril(matrix, -1)))
    p_draw = float(np.sum(np.diag(matrix)))
    p_away = float(np.sum(np.triu(matrix, 1)))

Et les remplacer par :

    p_home = float(np.sum(np.triu(matrix, 1)))
    p_draw = float(np.sum(np.diag(matrix)))
    p_away = float(np.sum(np.tril(matrix, -1)))

VÉRIFICATION : Après correction, pour Arsenal (home_goals_avg=2.1) vs Chelsea (away_goals_avg=1.6) :
- p_home DOIT être > p_away (Arsenal favori à domicile)
- p_home devrait être ~45-55%, p_draw ~25%, p_away ~20-30%
Si p_away > p_home sur ce match, le bug est toujours là.

ATTENTION : Ne modifier QUE ces 2 lignes. Ne pas toucher p_draw, la matrice, ni les lambdas.
```

---

## PHASE 3 — CORRECTIONS BOT.PY

### T5 — Enregistrer les 7 commandes dans post_init

**Fichier :** `bot.py`
**Dépendances :** T2 (contrôle d'accès en place)

**Prompt de tâche :**
```
TÂCHE T5 — Compléter post_init() avec les 7 commandes

Fichier : bot.py
Fonction : post_init()

Remplacer la liste actuelle (4 commandes) :

    commands = [
        BotCommand("start",  "Démarrer le bot"),
        BotCommand("coupon", "Générer le coupon du jour"),
        BotCommand("status", "Statut et prochaine génération"),
        BotCommand("aide",   "Aide et documentation"),
    ]

Par la liste complète (7 commandes) :

    commands = [
        BotCommand("start",   "Démarrer le bot"),
        BotCommand("coupon",  "Générer le coupon du jour"),
        BotCommand("status",  "Statut et prochaine génération"),
        BotCommand("aide",    "Aide et documentation"),
        BotCommand("history", "Historique des 30 derniers jours"),
        BotCommand("stats",   "Statistiques de performance"),
        BotCommand("result",  "Enregistrer un résultat"),
    ]

ATTENTION : Ne modifier QUE la liste commands. Ne pas toucher le reste de post_init().
```

---

### T6 — Corriger le message d'aide /result

**Fichier :** `bot.py`
**Dépendances :** Aucune

**Prompt de tâche :**
```
TÂCHE T6 — Corriger les messages d'aide vides dans cmd_result

Fichier : bot.py
Fonction : cmd_result()

Il y a DEUX endroits avec des messages d'aide incomplets :

1. Premier (quand args manquants) — remplacer :
    "ℹ️ Usage : \n"
    "Exemple : ",
   Par :
    "ℹ️ Usage : `/result <id> <won|lost|void>`\n"
    "Exemple : `/result 42 won`",

2. Deuxième (quand format invalide) — remplacer :
    "❌ Format invalide\\. Usage : ",
   Par :
    "❌ Format invalide\\. Usage : `/result <id> <won|lost|void>`",

ATTENTION : Ces messages sont en MarkdownV2. Les caractères spéciaux dans les backticks sont auto-échappés par Telegram à l'intérieur de ` `. Vérifier le rendu.
```

---

### T7 — Supprimer la duplication _esc/esc

**Fichier :** `bot.py`
**Dépendances :** Aucune

**Prompt de tâche :**
```
TÂCHE T7 — Supprimer la duplication _esc/esc dans bot.py

Fichier : bot.py

Le fichier définit _esc() au niveau module (ligne 118) et esc() localement dans format_coupon_telegram() (ligne 136). Les deux font exactement la même chose.

Action : Dans format_coupon_telegram(), supprimer la définition locale de esc() et remplacer TOUS les appels esc(...) par _esc(...) dans cette fonction.

Lignes à modifier dans format_coupon_telegram() :
- Supprimer les lignes 136-139 (définition de esc())
- Remplacer : esc(date) → _esc(date)
- Remplacer : esc(home) → _esc(home)
- Remplacer : esc(away) → _esc(away)
- Remplacer : esc(bet['bet_type']) → _esc(bet['bet_type'])
- Remplacer : esc(odd_str) → _esc(odd_str)
- Remplacer : esc(f"{total_odd:.2f}") → _esc(f"{total_odd:.2f}")

ATTENTION : La fonction stars() locale dans format_coupon_telegram() doit être CONSERVÉE (elle est différente de _esc).
```

---

### T8 — Remplacer asyncio.get_event_loop()

**Fichier :** `bot.py`
**Dépendances :** Aucune

**Prompt de tâche :**
```
TÂCHE T8 — Remplacer asyncio.get_event_loop() par get_running_loop()

Fichier : bot.py

asyncio.get_event_loop() est deprecated depuis Python 3.10. Il y a 3 occurrences :
- cmd_coupon() : loop = asyncio.get_event_loop()
- cmd_stats() : loop = asyncio.get_event_loop()
- scheduled_coupon() : loop = asyncio.get_event_loop()

Remplacer chaque occurrence par :
    loop = asyncio.get_running_loop()

VÉRIFICATION : Pas besoin de modifier l'import, asyncio contient déjà get_running_loop().
get_running_loop() est disponible depuis Python 3.7, donc compatible avec Python 3.10+.
```

---

### T9 — Supprimer bot_patched.py

**Fichier :** `bot_patched.py` (local uniquement, pas sur GitHub)
**Dépendances :** Aucune

**Prompt de tâche :**
```
TÂCHE T9 — Supprimer le fichier bot_patched.py

Ce fichier est une copie exacte de bot.py (26 521 octets identiques).
Il n'existe pas sur GitHub et crée de la confusion dans le workspace local.

Action : Supprimer /sessions/pensive-hopeful-pasteur/mnt/Bot/bot_patched.py

ATTENTION : Vérifier que bot.py existe et est intact avant de supprimer bot_patched.py.
```

---

## PHASE 4 — CORRECTIONS CONFIG.PY

### T10 — Ajouter TENNIS_PARAMS dans config.py

**Fichier :** `config.py` (GitHub)
**Dépendances :** Aucune

**Prompt de tâche :**
```
TÂCHE T10 — Ajouter TENNIS_PARAMS dans config.py

Fichier : config.py (version GitHub, 313 lignes)

coupon_generator.py importe TENNIS_PARAMS depuis config (ligne 49) :
    from config import (..., TENNIS_PARAMS, ...)

Mais config.py ne définit pas TENNIS_PARAMS → l'import échoue et le fallback dans coupon_generator.py prend le relais avec TOUTES les valeurs par défaut (pas seulement TENNIS_PARAMS).

Action : Ajouter APRÈS la section ELO_PARAMS (après la ligne "home_bonus": 50 }) :

    # ─── PARAMÈTRES TENNIS ────────────────────────────────────────
    # [v2.0] Poids des facteurs dans le modèle de prédiction tennis
    TENNIS_PARAMS = {
        # Poids du taux de victoire sur la surface (clay, hard, grass)
        "surface_weight": 0.15,
        # Poids de la forme récente (derniers 10 matchs)
        "form_weight": 0.08,
        # Poids des confrontations directes (head-to-head)
        "h2h_weight": 0.10,
    }

VÉRIFICATION : Après ajout, l'import dans coupon_generator.py ligne 49 doit réussir :
    from config import (..., TENNIS_PARAMS, ...)
Tester en local avec : python -c "from config import TENNIS_PARAMS; print(TENNIS_PARAMS)"

ATTENTION : L'import dans coupon_generator.py est un import groupé. Si TENNIS_PARAMS manque, TOUT l'import échoue et le fallback définit TOUTES les variables avec des valeurs par défaut différentes de config.py. C'est pourquoi cette correction est importante.
```

---

### T11 — Vérifier cohérence STATS_MARKETS vs StatsModel

**Fichier :** `config.py` + `coupon_generator.py` (GitHub)
**Dépendances :** T10

**Prompt de tâche :**
```
TÂCHE T11 — Vérifier la cohérence STATS_MARKETS entre config.py et coupon_generator.py

Contexte : config.py définit STATS_MARKETS avec corners, fouls, cards, shots_on_target.
coupon_generator.py a été mis à jour le 13 avril avec StatsModel.

Actions de vérification :
1. Ouvrir coupon_generator.py sur GitHub et vérifier que StatsModel importe STATS_MARKETS depuis config
2. Vérifier que les noms de marchés dans StatsModel correspondent exactement à ceux dans STATS_MARKETS.markets
3. Vérifier que LEAGUE_AVG_CORNERS, LEAGUE_AVG_FOULS, LEAGUE_AVG_CARDS, LEAGUE_AVG_SHOTS_ON_TARGET sont importés
4. Vérifier que les lignes Over/Under dans STATS_MARKETS.markets.corners.lines correspondent à ce que StatsModel utilise
5. S'assurer que le pipeline run_pipeline() appelle StatsModel et intègre les stats bets dans all_bets

Si incohérence trouvée : documenter et corriger pour que les imports et les noms de clés soient alignés entre config.py et coupon_generator.py.

ATTENTION : Ne pas changer les valeurs numériques dans STATS_MARKETS — elles ont été calibrées.
```

---

## PHASE 5 — CORRECTIONS COUPON_GENERATOR.PY

### T12 — Intégrer LEAGUE_HOME_ADVANTAGE dans PoissonModel

**Fichier :** `coupon_generator.py`
**Dépendances :** T4 (inversion corrigée d'abord)

**Prompt de tâche :**
```
TÂCHE T12 — Utiliser LEAGUE_HOME_ADVANTAGE dynamique dans PoissonModel

Contexte : config.py GitHub définit LEAGUE_HOME_ADVANTAGE par ligue (Premier League: 1.08, Bundesliga: 1.14, etc.). Mais PoissonModel utilise un home_advantage fixe (POISSON_PARAMS["home_advantage"] = 1.1) pour toutes les ligues.

Action dans coupon_generator.py :

1. Importer LEAGUE_HOME_ADVANTAGE depuis config (ajouter à l'import groupé ligne 47-51) :
   from config import (..., LEAGUE_HOME_ADVANTAGE, ...)

2. Modifier PoissonModel.__init__() pour accepter un paramètre optionnel :
   def __init__(self, league_avg_goals=None, home_advantage=None):
       ...
       self.home_adv = home_advantage or POISSON_PARAMS["home_advantage"]

3. Dans run_pipeline(), lors de la création du PoissonModel pour chaque match, passer l'avantage domicile de la ligue :
   Pour chaque fixture dans data["football"]:
       competition = fixture.get("competition", "")
       home_adv = LEAGUE_HOME_ADVANTAGE.get(competition, POISSON_PARAMS["home_advantage"])
       # Passer au modèle ou modifier le fixture

Approche alternative (plus simple) : modifier PoissonModel.predict() pour lire le home_advantage depuis le fixture :
   if fixture.get("league_home_advantage"):
       self.home_adv = fixture["league_home_advantage"]

Et enrichir les fixtures dans run_pipeline() :
   fix["league_home_advantage"] = LEAGUE_HOME_ADVANTAGE.get(fix["competition"])

ATTENTION : Restaurer self.home_adv après chaque predict (comme c'est fait pour league_avg_goals).
Ne pas casser le mode démo — les fixtures démo n'ont pas "competition" dans le bon format.
```

---

### T13 — Vérifier l'intégration StatsModel dans le pipeline

**Fichier :** `coupon_generator.py` (GitHub)
**Dépendances :** T11

**Prompt de tâche :**
```
TÂCHE T13 — Vérifier que StatsModel est correctement intégré dans run_pipeline()

Contexte : Le commit "Ajout moteur paris statistiques : StatsModel, fetch_stats, extract_stats_bets" a été fait le 13 avril. Il faut vérifier son intégration.

Points de vérification :
1. StatsModel est instancié dans run_pipeline()
2. Les stats sont fetchées (fetch_stats ou équivalent) pour chaque match
3. Les stats bets sont extraits (extract_stats_bets)
4. Les stats bets sont ajoutés à all_bets AVANT le select_best_bets
5. Les cotes stats sont récupérées depuis the-odds-api OU simulées en mode démo
6. Le CouponBuilder gère correctement les bets avec sport="Football" et market="corners"/"fouls" etc.
7. Le format_coupon_telegram affiche correctement les marchés stats

Si l'intégration est incomplète, documenter ce qui manque pour la tâche suivante.
```

---

### T14 — Supprimer le BacktestTracker JSON legacy

**Fichier :** `coupon_generator.py`
**Dépendances :** T15 (database.py doit être connecté d'abord)

**Prompt de tâche :**
```
TÂCHE T14 — Remplacer BacktestTracker JSON par la persistance SQLite

Contexte : coupon_generator.py contient une classe BacktestTracker (lignes 1172-1298) qui écrit dans un fichier JSON local. Le repo GitHub a database.py avec une persistance SQLite bien plus robuste.

Actions :
1. Dans run_pipeline(), remplacer l'utilisation de BacktestTracker par un appel à database.save_coupon()
2. Modifier la section backtesting (lignes 1496-1501) :

   AVANT :
   if BACKTEST.get("auto_track") and coupon:
       tracker = BacktestTracker()
       tracker.record_coupon(coupon, data.get("date", ""), is_demo=is_demo)

   APRÈS :
   if coupon:
       try:
           from database import ApexDatabase
           db = ApexDatabase()
           avg_edge = round(sum(b["value"] for b in coupon) / len(coupon), 2)
           avg_conf = round(sum(b["confidence"] for b in coupon) / len(coupon), 1)
           total = CouponBuilder.total_odd(coupon)
           db.save_coupon(coupon, total, avg_edge, avg_conf)
       except ImportError:
           logger.warning("database.py non disponible — coupon non sauvegardé")
       except Exception as e:
           logger.warning(f"Erreur sauvegarde coupon : {e}")

3. Garder la classe BacktestTracker et get_stats() comme code legacy (ne pas supprimer encore) mais commenter l'appel dans run_pipeline().

ATTENTION : Ne pas casser le pipeline si database.py n'est pas importable (protection try/except).
```

---

## PHASE 6 — INTÉGRATION MODULES

### T15 — Connecter database.py au pipeline

**Fichier :** `coupon_generator.py` + `bot.py`
**Dépendances :** T14

**Prompt de tâche :**
```
TÂCHE T15 — Vérifier et consolider la connexion database.py → pipeline → bot.py

Vérifications :
1. bot.py importe ApexDatabase → _db est instancié → VÉRIFIER QUE ÇA FONCTIONNE sur Railway
   (database.py EXISTE sur GitHub, donc l'import devrait réussir)
2. Vérifier que _db.save_coupon() est appelé après chaque génération (T14)
3. Vérifier que cmd_history utilise _db.get_history() correctement
4. Vérifier que cmd_result utilise _db.update_coupon_result() correctement
5. Vérifier que cmd_stats utilise _backtester.performance_report() correctement

Test :
- Exécuter /coupon sur Telegram
- Vérifier que le coupon est sauvegardé dans la DB
- Exécuter /history → doit afficher le coupon
- Exécuter /result 1 won → doit mettre à jour le résultat
```

---

### T16 — Vérifier backtester.py

**Fichier :** `backtester.py` (GitHub)
**Dépendances :** T15

**Prompt de tâche :**
```
TÂCHE T16 — Auditer backtester.py pour cohérence avec database.py et bot.py

Fichier : backtester.py (existe sur GitHub, créé le 10 avril)

Vérifications :
1. ApexBacktester.__init__ accepte un ApexDatabase en paramètre
2. performance_report(days) retourne un dict compatible avec format_report_telegram()
3. format_history_telegram(history, limit) retourne un string MarkdownV2 valide
4. format_report_telegram(report) retourne un string MarkdownV2 valide
5. Tous les caractères spéciaux MarkdownV2 sont échappés (. ! - # + = | { } ( ) > ~)
6. Les calculs ROI et win_rate sont mathématiquement corrects

Si des problèmes sont trouvés dans le formatage MarkdownV2, les corriger en utilisant la même fonction _esc() que bot.py (ou une copie locale).
```

---

## PHASE 7 — NETTOYAGE & QUALITÉ

### T17 — Nettoyer les fichiers dupliqués

**Prompt de tâche :**
```
TÂCHE T17 — Supprimer les fichiers .txt dupliqués et bot_patched.py

Les fichiers suivants dans le workspace local sont des copies obsolètes :
- bot.py.txt (copie ancienne de bot.py)
- config.py.txt (copie ancienne de config.py)
- coupon_generator.py.txt (copie ancienne de coupon_generator.py)
- .env.example.txt (devrait être .env.example sans .txt)
- .gitignore.txt (devrait être .gitignore sans .txt)
- railway.toml.txt (devrait être railway.toml sans .txt)
- test_models.py.txt (devrait être test_models.py sans .txt)
- bot_patched.py (copie exacte de bot.py)

Action : Supprimer tous ces fichiers du workspace local.
NE PAS les supprimer du repo GitHub (ils n'y sont probablement pas).
```

---

### T18 — Ajouter GitHub Actions CI

**Prompt de tâche :**
```
TÂCHE T18 — Créer un workflow GitHub Actions basique

Créer .github/workflows/ci.yml avec :
- Trigger : push sur main + pull requests
- Python 3.12
- pip install -r requirements.txt
- python -m py_compile bot.py
- python -m py_compile coupon_generator.py
- python -m py_compile config.py
- python -m py_compile database.py
- python -m py_compile backtester.py
- pip audit -r requirements.txt (optionnel, peut échouer)

Cela détectera au minimum les erreurs de syntaxe avant déploiement.
```

---

### T19 — Mettre à jour le README

**Prompt de tâche :**
```
TÂCHE T19 — Mettre à jour README.md avec les commandes v2.0

Le README actuel ne liste que 4 commandes. Ajouter :
- /history : Historique des 30 derniers jours
- /stats : Statistiques de performance (ROI, win rate)
- /result <id> <won|lost|void> : Enregistrer un résultat

Ajouter aussi une section sur les marchés statistiques (corners, fautes, cartons, tirs).
```

---

## PHASE 8 — VÉRIFICATION FINALE

### T20 — Audit de régression

**Prompt de tâche :**
```
TÂCHE T20 — Audit de régression post-corrections

Après TOUTES les corrections déployées, vérifier :

SÉCURITÉ :
□ Les logs Railway ne contiennent plus le token Telegram
□ ALLOWED_USERS est vérifié dans chaque handler
□ Le token a été régénéré via BotFather
□ Aucun secret en dur dans le code

MATHÉMATIQUES :
□ p_home > p_away pour Arsenal vs Chelsea (domicile favori)
□ Les value bets sélectionnés ont du sens (pas de "Victoire Chelsea" quand Arsenal est favori à domicile)
□ La cote totale du coupon est entre 3.0 et 8.0

BOT TELEGRAM :
□ /start affiche toutes les commandes
□ /coupon génère un coupon formaté
□ /status affiche le bon mode (Démo/Temps réel)
□ /aide affiche l'explication
□ /history affiche l'historique (pas "Module non disponible")
□ /stats affiche les statistiques (pas "Module non disponible")
□ /result 1 won enregistre un résultat
□ Menu Telegram affiche 7 commandes
□ Messages d'aide /result affichent la syntaxe

INTÉGRATION :
□ database.py est importé sans erreur
□ backtester.py est importé sans erreur
□ Les coupons sont sauvegardés en SQLite après génération
□ TENNIS_PARAMS est importé depuis config.py sans erreur
□ StatsModel fonctionne (si implémenté)

PROCESSUS :
□ Pas de fichiers .txt dupliqués
□ Pas de bot_patched.py
□ GitHub Actions CI passe au vert
```

---

## RÉSUMÉ DES 20 TÂCHES

| # | Tâche | Fichier | Priorité | Dépend de |
|---|-------|---------|----------|-----------|
| T1 | Filtrer token des logs | bot.py | 🔴 CRITIQUE | — |
| T2 | Contrôle d'accès ALLOWED_USERS | bot.py | 🔴 CRITIQUE | — |
| T3 | Régénérer token Telegram | MANUEL | 🔴 CRITIQUE | T1 |
| T4 | Corriger inversion p_home/p_away | coupon_generator.py | 🔴 CRITIQUE | — |
| T5 | Compléter post_init 7 commandes | bot.py | 🟠 HAUTE | T2 |
| T6 | Corriger /result message aide | bot.py | 🟠 HAUTE | — |
| T7 | Supprimer duplication _esc/esc | bot.py | 🟡 MOYENNE | — |
| T8 | asyncio.get_running_loop() | bot.py | 🟡 MOYENNE | — |
| T9 | Supprimer bot_patched.py | local | 🟡 BASSE | — |
| T10 | Ajouter TENNIS_PARAMS config | config.py | 🟠 HAUTE | — |
| T11 | Vérifier cohérence STATS_MARKETS | config.py + coupon_gen | 🟡 MOYENNE | T10 |
| T12 | LEAGUE_HOME_ADVANTAGE dynamique | coupon_generator.py | 🟡 MOYENNE | T4 |
| T13 | Vérifier intégration StatsModel | coupon_generator.py | 🟡 MOYENNE | T11 |
| T14 | Remplacer BacktestTracker JSON | coupon_generator.py | 🟡 MOYENNE | T15 |
| T15 | Connecter database.py au pipeline | coupon_gen + bot.py | 🟠 HAUTE | T14 |
| T16 | Vérifier backtester.py | backtester.py | 🟡 MOYENNE | T15 |
| T17 | Nettoyer fichiers dupliqués | local | 🟡 BASSE | — |
| T18 | GitHub Actions CI | .github/workflows/ | 🟡 BASSE | — |
| T19 | Mettre à jour README | README.md | 🟡 BASSE | T5, T6 |
| T20 | Audit de régression | TOUS | 🔴 CRITIQUE | T1→T19 |

---

## STRATÉGIE ANTI-RÉGRESSION

Pour éviter que les corrections créent de nouveaux bugs :

1. **T1 et T3 sont liées** : T1 DOIT être déployé AVANT T3, sinon le nouveau token fuiterait aussi
2. **T4 est isolée** : la correction de 2 lignes ne peut pas casser autre chose
3. **T2 et T5 sont liées** : T5 (menu) doit refléter les mêmes commandes que T2 (handlers)
4. **T10 et T11 sont liées** : ajouter TENNIS_PARAMS peut changer le comportement de l'import groupé
5. **T14 et T15 sont circulaires** : résolu en faisant T15 d'abord (vérifier database.py) puis T14 (switcher)
6. **Toutes les tâches bot.py** (T1, T2, T5, T6, T7, T8) doivent être commitées ensemble pour éviter des déploiements intermédiaires cassés

**Recommandation de commits :**
- Commit 1 : T1 + T2 + T5 + T6 + T7 + T8 (toutes les corrections bot.py)
- Commit 2 : T4 + T10 + T12 (corrections coupon_generator.py + config.py)
- Commit 3 : T14 (switch vers database.py)
- Commit 4 : T18 + T19 (CI + README)
- Manuel : T3 (régénérer token), T9 + T17 (nettoyage local), T20 (audit final)

---

*Plan rédigé le 13 avril 2026 — 20 tâches, 8 phases, 4 commits recommandés*
