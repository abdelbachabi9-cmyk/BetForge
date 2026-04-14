# PROMPT CLAUDE CODE — Correction complète APEX Bot (Audit v5)

> **Copier-coller ce prompt dans Claude Code en étant positionné à la racine du projet APEX.**
> **Pré-requis :** avoir accès aux fichiers `coupon_generator.py`, `config.py`, `bot.py` et au repo GitHub `abdelbachabi9-cmyk/BetForge`.

---

## PROMPT

```
Tu es le développeur principal du bot Telegram APEX (prédiction sportive). Tu dois implémenter TOUTES les corrections identifiées dans l'audit v5 (fichier audit_apex_v5_modeles.md). Le code doit rester fonctionnel après chaque modification — pas de régression.

CONTEXTE DU PROJET :
- Bot Telegram Python 3.10+ (python-telegram-bot v21, async)
- 3 fichiers principaux : coupon_generator.py (~1530 lignes), config.py (~193 lignes), bot.py (~607 lignes)
- Moteur de prédiction : Poisson (football), ELO (basketball), Tennis (ELO-like)
- Pipeline : DataFetcher → Modèles → ValueBetSelector → CouponBuilder → Telegram
- Le repo GitHub (abdelbachabi9-cmyk/BetForge) contient des fichiers plus complets que le local (config.py de 313 lignes avec StatsModel, database.py, backtester.py)
- Hébergé sur Railway, secrets dans les variables d'environnement

RÈGLES ABSOLUES :
1. JAMAIS de secret/clé API en dur — toujours os.getenv()
2. JAMAIS de eval(), exec(), os.system(), subprocess avec input utilisateur
3. Timeout sur TOUS les appels API (NETWORK["timeout"])
4. try/except avec logging sur chaque appel externe
5. Paramètres configurables dans config.py, JAMAIS de valeur magique dans le code
6. Type hints sur toutes les signatures
7. Docstrings Google-style sur chaque classe/fonction publique
8. Commentaires métier en français, code technique en anglais acceptable
9. PEP 8 strict, lignes ≤ 120 caractères
10. Tester que le MarkdownV2 Telegram est correct (échapper _*[]()~`>#+-=|{}.!)

═══════════════════════════════════════════════════════
PHASE 1 — PRIORITÉ HAUTE (Impact direct sur les prédictions)
═══════════════════════════════════════════════════════

### R1 — Matching fuzzy des noms d'équipes entre APIs

PROBLÈME : Le matching cotes ↔ fixtures se fait par string exact "home vs away" (coupon_generator.py ligne 1458). Or les noms diffèrent entre APIs : football-data.org dit "Arsenal FC", the-odds-api dit "Arsenal", TheSportsDB dit "Arsenal London". Résultat : beaucoup de matchs réels n'ont pas de cotes associées.

ACTION :
1. Dans coupon_generator.py, ajouter une fonction normalize_team_name() au niveau module :

```python
def normalize_team_name(name: str) -> str:
    """Normalise le nom d'une équipe pour le matching cross-API."""
    # Suffixes courants à retirer
    suffixes = [" fc", " cf", " sc", " ac", " as", " ss",
                " london", " madrid", " munich", " milano",
                " de marseille", " saint-germain",
                " united", " city", " town", " rovers",
                " wanderers", " athletic", " albion"]
    normalized = name.lower().strip()
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()
    # Retirer les caractères spéciaux
    normalized = normalized.replace(".", "").replace("-", " ")
    return normalized
```

2. Modifier le matching dans run_pipeline() :
   - Lors de la construction de odds_index (ligne 1341), utiliser normalize_team_name() pour les clés
   - Lors du lookup (lignes 1458-1473), normaliser aussi la clé de recherche
   - Ajouter un fallback : si le match exact échoue, chercher par substring (home contenu dans la clé)

3. Ajouter un dictionnaire d'ALIAS manuels dans config.py pour les cas ambigus :

```python
TEAM_ALIASES = {
    "psg": "paris saint-germain",
    "man utd": "manchester united",
    "man city": "manchester city",
    "inter": "inter milan",
    "atletico": "atletico madrid",
    "spurs": "tottenham hotspur",
    "wolves": "wolverhampton",
    "bvb": "borussia dortmund",
}
```

VÉRIFICATION : Logger le nombre de matchs avec cotes associées vs total de matchs. Avant le fix, ce ratio devrait augmenter significativement.

---

### R2 — Enrichir le modèle ELO avec des données historiques NBA

PROBLÈME : EloModel.update() n'est jamais appelé. En mode réel, tous les ratings sont à 1500 (initial) → 50/50 pour chaque match. Basketball est désactivé en mode réel (ligne 1442).

ACTION :
1. Créer un fichier nba_elo_bootstrap.py qui :
   a. Télécharge les résultats NBA de la saison en cours via BallDontLie API (GET /games?seasons[]=2025&per_page=100)
   b. Itère sur les matchs chronologiquement et appelle EloModel.update() pour chaque résultat
   c. Sauvegarde les ratings finaux dans un fichier JSON (nba_elo_ratings.json)

2. Modifier EloModel pour :
   a. Accepter un fichier de ratings pré-entraînés dans __init__() :
   ```python
   def __init__(self, ratings_file: Optional[str] = None):
       ...
       if ratings_file and Path(ratings_file).exists():
           self.ratings = json.loads(Path(ratings_file).read_text())
           logger.info(f"ELO ratings chargés : {len(self.ratings)} équipes")
   ```
   b. Ajouter une méthode save_ratings() pour persister les ratings

3. Modifier run_pipeline() pour :
   a. Charger les ratings ELO NBA au démarrage (si le fichier existe)
   b. Réactiver le basketball en mode réel SI des ratings sont disponibles
   c. Récupérer les fixtures NBA du jour via BallDontLie (GET /games?dates[]={today})

4. Ajouter dans config.py :
```python
ELO_PARAMS = {
    ...
    "ratings_file": os.getenv("ELO_RATINGS_FILE", "nba_elo_ratings.json"),
    "bootstrap_seasons": [2025, 2026],
}
```

VÉRIFICATION : Après bootstrap, les ratings doivent varier significativement (1400-1700) et le top 5 NBA devrait avoir les ratings les plus élevés.

---

### R3 — Estimer rho par ligue au lieu d'une constante fixe

PROBLÈME : rho = -0.13 est une constante unique pour toutes les ligues. La vraie valeur varie entre -0.05 (Bundesliga, scoring élevé) et -0.20 (Serie A, scoring faible). Erreur propagée : ~1-2% sur les probabilités 1X2.

ACTION :
1. Dans config.py, remplacer le rho unique par une table par ligue :

```python
POISSON_PARAMS = {
    ...
    # rho par ligue — valeurs calibrées sur données 2023-2025
    # Source : analyse des fréquences de scores 0-0, 0-1, 1-0, 1-1
    # vs prédiction Poisson indépendant, par ligue
    "league_rho": {
        "PL":  -0.11,   # Premier League — scoring moyen-haut (~2.8 buts/match)
        "PD":  -0.12,   # La Liga — scoring moyen (~2.6)
        "BL1": -0.09,   # Bundesliga — scoring élevé (~3.1)
        "SA":  -0.15,   # Serie A — scoring faible, plus de 0-0 (~2.5)
        "FL1": -0.14,   # Ligue 1 — scoring faible (~2.5)
        "CL":  -0.10,   # Champions League — matchs ouverts
    },
    # Fallback si la ligue n'est pas dans la table
    "default_rho": -0.13,
}
```

2. Modifier PoissonModel.__init__() pour accepter un rho optionnel :
```python
def __init__(self, league_avg_goals: float = None, rho: float = None):
    ...
    self.rho = rho or POISSON_PARAMS.get("default_rho", -0.13)
```

3. Modifier run_pipeline() pour passer le bon rho selon la ligue du match :
```python
for fixture in data.get("football", []):
    league_code = fixture.get("league_code", "")
    rho = POISSON_PARAMS.get("league_rho", {}).get(league_code, POISSON_PARAMS.get("default_rho", -0.13))
    poisson_model = PoissonModel(rho=rho)
    pred = poisson_model.predict(fixture)
```

4. Propager le league_code dans les fixtures (s'il n'y est pas déjà) — le code mode réel le fait déjà via team_stats["league_code"] (ligne 1367).

VÉRIFICATION : Comparer les probabilités de Arsenal-Chelsea (PL, rho=-0.11) et Inter-Milan (SA, rho=-0.15) — la différence de P(0-0) devrait être visible (~1-2%).

═══════════════════════════════════════════════════════
PHASE 2 — PRIORITÉ MOYENNE (Fiabilité long terme)
═══════════════════════════════════════════════════════

### R4 — Connecter le backtesting aux résultats réels

PROBLÈME : BacktestTracker enregistre les coupons (coupon_history.json) mais les résultats ne sont jamais alimentés. Le ROI calculé est toujours vide.

ACTION :
1. Ajouter une méthode dans DataFetcher pour récupérer les résultats des matchs passés :

```python
def fetch_match_results(self, date: str) -> List[dict]:
    """Récupère les scores finaux des matchs d'une date donnée via football-data.org."""
    results = []
    for code in FOOTBALL_COMPETITIONS:
        url = f"{ENDPOINTS['football_data_base']}/competitions/{code}/matches"
        headers = {"X-Auth-Token": API_KEYS["football_data"]}
        params = {"dateFrom": date, "dateTo": date, "status": "FINISHED"}
        data = self._get(url, headers=headers, params=params, api_name="football_data")
        if data:
            for match in data.get("matches", []):
                results.append({
                    "home": match["homeTeam"]["name"],
                    "away": match["awayTeam"]["name"],
                    "score_home": match["score"]["fullTime"]["home"],
                    "score_away": match["score"]["fullTime"]["away"],
                    "competition": code,
                })
    return results
```

2. Ajouter une méthode dans BacktestTracker pour résoudre automatiquement les résultats :

```python
def resolve_results(self, match_results: List[dict]) -> int:
    """Compare les résultats réels aux prédictions et met à jour l'historique.
    Retourne le nombre de sélections résolues."""
    history = self._load()
    resolved_count = 0
    for entry in history:
        if entry.get("result") is not None:
            continue  # Déjà résolu
        for sel in entry.get("selections", []):
            if sel.get("result") is not None:
                continue
            # Chercher le match correspondant
            for result in match_results:
                match_key = f"{result['home']} vs {result['away']}"
                if normalize_team_name(match_key) in normalize_team_name(sel["match"]):
                    sel["result"] = self._evaluate_bet(sel, result)
                    resolved_count += 1
        # Si toutes les sélections sont résolues, résoudre le coupon
        all_resolved = all(s.get("result") is not None for s in entry.get("selections", []))
        if all_resolved:
            all_won = all(s["result"] == "win" for s in entry["selections"])
            entry["result"] = "win" if all_won else "loss"
    self._save()
    return resolved_count

def _evaluate_bet(self, selection: dict, result: dict) -> str:
    """Évalue si un pari individuel est gagné ou perdu."""
    bet_type = selection["bet_type"].lower()
    score_h = result["score_home"]
    score_a = result["score_away"]
    total_goals = score_h + score_a

    if "victoire" in bet_type and result["home"].lower() in bet_type.lower():
        return "win" if score_h > score_a else "loss"
    elif "victoire" in bet_type and result["away"].lower() in bet_type.lower():
        return "win" if score_a > score_h else "loss"
    elif "match nul" in bet_type:
        return "win" if score_h == score_a else "loss"
    elif "over 2.5" in bet_type:
        return "win" if total_goals > 2.5 else "loss"
    elif "under 2.5" in bet_type:
        return "win" if total_goals < 2.5 else "loss"
    elif "btts" in bet_type and "non" not in bet_type:
        return "win" if score_h > 0 and score_a > 0 else "loss"
    elif "btts" in bet_type and "non" in bet_type:
        return "win" if score_h == 0 or score_a == 0 else "loss"
    return "unknown"
```

3. Ajouter un job quotidien dans bot.py qui résout les résultats de la veille :
```python
async def scheduled_resolve_results(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Résout les résultats des coupons de la veille."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    loop = asyncio.get_running_loop()
    resolved = await loop.run_in_executor(None, lambda: _resolve_yesterday(yesterday))
    logger.info(f"📊 {resolved} sélections résolues pour {yesterday}")
```

Planifier ce job 1h après la fin des matchs (ex: 01h00).

VÉRIFICATION : Après 1 semaine de fonctionnement, get_stats() doit retourner un ROI non-vide avec wins, losses et win_rate.

---

### R5 — Ajouter un facteur d'incertitude à la confiance

PROBLÈME : Le score de confiance est basé uniquement sur le Kelly. Il ne reflète pas la quantité/qualité des données sous-jacentes. Un modèle avec 5 matchs a la même confiance qu'un modèle avec 28 matchs.

ACTION :
Dans ValueBetSelector._confidence_score() (coupon_generator.py ligne 858), ajouter un paramètre data_quality :

```python
def _confidence_score(self, p_model: float, value: float,
                      odd: float = 2.0, matches_played: int = 20) -> float:
    """
    Score de confiance /10 basé sur Kelly × facteur d'incertitude.

    Le facteur d'incertitude pénalise les prédictions basées sur peu de données :
    - 5 matchs → facteur 0.50 (confiance divisée par 2)
    - 10 matchs → facteur 0.71
    - 20+ matchs → facteur 1.0 (pleine confiance)
    """
    b = odd - 1
    if b <= 0:
        return 0.0
    q = 1 - p_model
    kelly_full = (b * p_model - q) / b
    if kelly_full <= 0:
        return 0.0
    kelly_frac = kelly_full * KELLY["fraction"]
    raw_score = min(10.0, (kelly_frac * 100) / KELLY["max_stake_pct"] * 10)

    # Facteur d'incertitude : sqrt(min(matches, 20) / 20)
    uncertainty_factor = min(1.0, (min(matches_played, 20) / 20) ** 0.5)

    return round(raw_score * uncertainty_factor, 1)
```

Propager matches_played depuis les fixtures dans extract_bets() et les méthodes d'extraction par sport.

VÉRIFICATION : Un pari Arsenal (28 matchs) doit avoir une confiance plus élevée qu'un pari sur une équipe promue (8 matchs) à edge identique.

---

### R6 — Diversification du coupon par sport/ligue

PROBLÈME : CouponBuilder optimise uniquement la cote totale sans contrainte de diversification. Un coupon pourrait contenir 6 matchs de la même ligue.

ACTION :
Dans CouponBuilder.build() (coupon_generator.py ligne 1034), ajouter un filtre de diversification :

```python
def _is_diversified(self, combo: List[dict], max_per_league: int = 3) -> bool:
    """Vérifie qu'un coupon est suffisamment diversifié."""
    league_counts: Dict[str, int] = {}
    for bet in combo:
        league = bet.get("competition", "unknown")
        league_counts[league] = league_counts.get(league, 0) + 1
        if league_counts[league] > max_per_league:
            return False
    return True
```

Intégrer ce filtre dans la boucle combinatoire :
```python
for combo in combinations(pool, target_size):
    combo_list = list(combo)
    if not self._is_diversified(combo_list):
        continue  # Skip les combos trop concentrés
    total = self.total_odd(combo_list)
    ...
```

Ajouter le paramètre dans config.py :
```python
VALUE_BETTING = {
    ...
    "max_per_league": 3,  # Max 3 sélections par ligue
    "min_sports": 1,       # Minimum 1 sport (relaxé si un seul sport dispo)
}
```

VÉRIFICATION : Aucun coupon ne devrait avoir plus de 3 sélections de la même ligue.

═══════════════════════════════════════════════════════
PHASE 3 — PRIORITÉ BASSE (Améliorations)
═══════════════════════════════════════════════════════

### R7 — Passer league_avg_goals en paramètre (thread-safety)

PROBLÈME : PoissonModel.predict() mute self.league_avg_goals temporairement (save-modify-restore). Thread-unsafe.

ACTION :
Modifier calculate_lambdas() pour accepter league_avg_goals en paramètre :

```python
def calculate_lambdas(self, fixture: dict,
                      league_avg_goals: Optional[float] = None) -> Tuple[float, float]:
    avg = league_avg_goals or self.league_avg_goals
    att_home = fixture["home_goals_avg"] / avg
    ...
    lambda_home = att_home * def_away * avg * self.home_adv
    lambda_away = att_away * def_home * avg
    return round(lambda_home, 4), round(lambda_away, 4)
```

Et dans predict() :
```python
def predict(self, fixture: dict) -> Dict[str, Any]:
    league_avg = fixture.get("league_avg_goals") or self.league_avg_goals
    lambda_h, lambda_a = self.calculate_lambdas(fixture, league_avg_goals=league_avg)
    matrix = self.score_matrix(lambda_h, lambda_a)
    ...
```

Supprimer le pattern save-restore (lignes 571-575).

---

### R8 — Ajouter un marché Over/Under basketball

ACTION :
1. Ajouter dans EloModel.predict() une estimation du total de points :
```python
# Estimation simplifiée du total points
home_ppg = fixture.get("home_ppg", 110)  # Points per game
away_ppg = fixture.get("away_ppg", 108)
projected_total = (home_ppg + away_ppg) / 2 * 1.02  # Léger boost domicile
threshold = fixture.get("total_threshold", 220.5)
p_over = 1 / (1 + math.exp(-(projected_total - threshold) / 8))  # Sigmoïde
```

2. Ajouter les marchés O/U dans extract_basketball_bets() :
```python
markets = [
    (f"Victoire {fix['home']}", prediction["p_home_win"], "h2h", fix["home"]),
    (f"Victoire {fix['away']}", prediction["p_away_win"], "h2h", fix["away"]),
    (f"Over {prediction.get('total_threshold', 220.5)}", prediction.get("p_over_total", 0.5), "totals", "Over"),
    (f"Under {prediction.get('total_threshold', 220.5)}", prediction.get("p_under_total", 0.5), "totals", "Under"),
]
```

---

### R9 — Synchroniser le StatsModel depuis GitHub

PROBLÈME : Le config.py GitHub (313 lignes) contient STATS_MARKETS, LEAGUE_HOME_ADVANTAGE, LEAGUE_AVG_GOALS, DATABASE, LINE_MOVEMENT, DISPLAY. Le coupon_generator.py GitHub contient un StatsModel pour les marchés stats (corners, fautes, cartons, tirs). Rien de tout cela n'est dans le code local.

ACTION :
1. Récupérer le config.py complet depuis GitHub :
   git show origin/main:config.py > config_github.py
   Fusionner les sections manquantes dans le config.py local :
   - STATS_MARKETS (corners, fautes, cartons, tirs, passes, touches)
   - LEAGUE_HOME_ADVANTAGE (table par ligue)
   - LEAGUE_AVG_GOALS (table par ligue — remplace default_league_avg_goals)
   - DATABASE (config SQLite)

2. Récupérer le StatsModel depuis le coupon_generator.py GitHub et l'intégrer dans le fichier local, entre TennisModel et ValueBetSelector.

3. Intégrer le StatsModel dans run_pipeline() :
   - Après l'étape 3 (modélisation ELO+Tennis), ajouter une étape 3.5 :
   ```python
   logger.info("📐 Étape 3.5/6 : Marchés statistiques (corners, fautes)…")
   stats_model = StatsModel()
   stats_predictions = []
   for pred in football_predictions:
       try:
           stats_pred = stats_model.predict(pred)
           stats_predictions.append(stats_pred)
       except Exception as e:
           logger.warning(f"Erreur stats : {e}")
   ```
   - Extraire les paris stats dans l'étape 4

4. Récupérer database.py et backtester.py depuis GitHub :
   git checkout origin/main -- database.py backtester.py
   S'assurer que les imports dans bot.py fonctionnent (les try/except sont déjà en place).

VÉRIFICATION : Après l'intégration, le pipeline doit afficher les marchés stats dans les logs et le coupon peut contenir des paris corners/fautes.

═══════════════════════════════════════════════════════
PHASE 4 — NETTOYAGE FINAL
═══════════════════════════════════════════════════════

### N1 — Supprimer bot_patched.py (fichier vide, vestige)
### N2 — Mettre à jour CLAUDE.md avec les nouvelles fonctionnalités
### N3 — Mettre à jour requirements.txt si de nouvelles dépendances sont ajoutées

═══════════════════════════════════════════════════════
ORDRE D'EXÉCUTION RECOMMANDÉ
═══════════════════════════════════════════════════════

1. R7 (thread-safety, 5 min, 0 risque de régression)
2. R3 (rho par ligue, 15 min, changement config + modèle)
3. R1 (matching fuzzy, 30 min, touche DataFetcher + pipeline)
4. R5 (facteur incertitude, 15 min, touche ValueBetSelector)
5. R6 (diversification coupon, 20 min, touche CouponBuilder)
6. R8 (O/U basketball, 30 min, touche EloModel + ValueBetSelector)
7. R9 (sync GitHub StatsModel, 45 min, touche config + generator + pipeline)
8. R2 (ELO NBA bootstrap, 1h, nouveau fichier + intégration)
9. R4 (backtesting résultats, 1h, touche DataFetcher + BacktestTracker + bot.py)
10. N1-N3 (nettoyage, 10 min)

Après CHAQUE modification :
- Vérifier que `python coupon_generator.py` s'exécute sans erreur en mode démo
- Vérifier que les probabilités 1X2 somment à ~100%
- Vérifier que le coupon généré contient 4-10 sélections avec cote totale 3.0-8.0
- Logger un avant/après pour les métriques impactées

COMMIT après chaque phase (pas après chaque correction) :
- Phase 1 : "feat: matching fuzzy + rho par ligue + ELO NBA bootstrap"
- Phase 2 : "feat: backtesting auto + incertitude confiance + diversification coupon"
- Phase 3 : "feat: O/U basketball + StatsModel intégré + thread-safety Poisson"
- Phase 4 : "chore: nettoyage bot_patched + MAJ CLAUDE.md"
```
