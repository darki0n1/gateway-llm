# Changelog

Toutes les évolutions notables de ce projet sont documentées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère à [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

_(Rien pour l'instant.)_

## [0.2.0] - 2026-11-07

Version majeure : architecture de classification en cascade, sélection
dynamique des modèles locaux, modes d'exécution cloud/local/hybride, GUI
enrichie (drag & drop, annulation, rendu Markdown).

### Added

#### Modes d'exécution

- `LocalMode` (enum) : `CLOUD_ONLY`, `LOCAL_ONLY`, `HYBRID`, `DEFAULT`.
  Sélectionné au premier lancement de la GUI, persisté dans `~/.gateway-llm/config.yaml`.
- `load_local_mode()` / `save_local_mode()` dans `config.py`.
- `ModeDialog` (GUI) : dialogue de premier lancement avec descriptions des 4 modes.
- `BatchRunner._apply_local_mode()` : ajuste les providers et téléchargements selon le mode.
- En `CLOUD_ONLY`, le `TaskClassifier` utilise `flexrouter` (bucket `low`) au lieu d'Ollama.

#### Sélection locale dynamique

- Module `local_selector.py` : croise benchmarks × hardware × catalogue Ollama
  pour choisir les modèles à installer. Aucune liste en dur.
- `OllamaModelInfo` (dataclass) : nom, tag, taille, quantification, capabilities.
- `load_ollama_catalog()` : charge `benchmarks_cache/ollama_library.json`.
- `select_local_models()` : filtre par `effective_capacity_gb()`, classe par score.
- Script `scripts/refresh_ollama_library.py` : scraping `ollama.com/library`
  via Playwright + BeautifulSoup, fallback sur l'API `akazwz/ollama-models`.
- Workflow CI mis à jour pour scraper le catalogue toutes les 2 semaines.

#### Hardware

- `HardwareInfo` étendu : `ram_total_gb`, `ram_available_gb`, `disk_free_gb`.
- `effective_capacity_gb()` : VRAM + 70% de la RAM disponible (offload Ollama).
- `can_run(size_gb)` : vérifie si un modèle (runtime × 1.3) tient.
- `detect_hardware()` (remplace `detect_vram`) : détection complète via `psutil` + `shutil.disk_usage`.
- `detect_vram` conservé en alias pour compatibilité.

#### Classification

- `TaskClassifier` refondu en cascade à 3 étages :
  - Étage 1 : regex (blocages critiques, prime sur tout).
  - Étage 2 : embeddings cosine avec seuils calibrés
    (`HIGH_CONFIDENCE=0.82`, `LOW_CONFIDENCE=0.60`, `AMBIGUITY_GAP=0.10`).
  - Étage 3 : LLM (tiebreaker zone grise ou fallback bas score).
- `ClassificationResult.confidence` : score du sémantique (0.0–1.0).
- `ClassificationResult.decision_layer` : `regex` | `embedding` | `llm` | `fallback`.
- `_second_best()` : détecte l'ambiguïté (top-2 trop proche du top-1).
- Seuils configurables au constructeur (`high_confidence=`, `low_confidence=`, `ambiguity_gap=`).
- Comportement zone grise : retour embedding avec priorité humaine >= 4 si pas de LLM.

#### Installation Ollama

- `ensure_ollama_daemon()` (nouveau dans `installer.py`) :
  - Teste `/api/tags`, lance `ollama serve` sinon, attend 20s.
  - Message clair si le binaire est absent (URL de téléchargement).
- `Installer.ensure_models()` appelle `ensure_ollama_daemon()` en premier.
- `BatchRunner._ensure_ollama_models()` : bootstrap des modèles déclarés
  dans les chaînes de domaine + `nomic-embed-text` + le classifieur.

#### Intake — CSV et mixte

- `intake_from_csv()` refondu : lit **toutes les colonnes** (plus de sélection
  unique). Formatage pseudo-JSON compact, traitement par lots (`max_rows=500`,
  `max_chars=30_000`).
- `intake_from_csv_multi()` : fusion de plusieurs CSV en un seul JSONL avec
  préfixe du nom de fichier sur les IDs.
- `intake_mixed()` : images + textes + CSV en une seule session (une tâche par
  image, une tâche par CSV).
- CLI `intake from-csv` : suppression de `--column`, `--prompt` par défaut `{table}`.

#### GUI

- **Drag & drop** : accepter des fichiers/dossiers sur la liste de sources
  (via `tkinterdnd2`, fallback silencieux si absent).
- **Multi-sélection** dans la liste de sources + boutons Retirer / Vider.
- Mode **Mixte** (images + textes + CSV).
- Bouton **Annuler** : arrête le batch après la tâche en cours
  (`BatchRunner._cancel_event`).
- **Rendu Markdown** dans les résultats : titres, gras, italique, code inline,
  blocs de code, citations, listes.
- **Auto-refresh** des résultats : polling toutes les 2s après un batch.
- **Logs en direct** dans la fenêtre (handler `_TextHandler` branché sur le
  logger `gateway_llm`).
- Vérification/installation automatique de Chromium Playwright au démarrage
  (en arrière-plan, statut affiché en bas).

#### Markdown

- Instruction de format prependée par défaut au prompt (`Router.route(ensure_markdown=True)`).
- Flag CLI `--no-markdown` pour désactiver.
- `BatchRunner(ensure_markdown=True)` pour propagation.

#### Configuration

- `_DEFAULT_CONFIG` embarqué dans `config.py` : la config bootstrap fonctionne
  sans fichier YAML (`load_config(None)`).
- `_DEFAULT_POLICY` embarqué : politique de résidence par défaut.
- Provider `flexrouter` ajouté à `_DEFAULT_CONFIG` (routeur cloud gratuit).
- `--config` et `--policy` deviennent **optionnels** en CLI.

#### Providers

- `OllamaProvider.complete()` : bug fixé (le payload reconstruisait un message
  au lieu d'utiliser `message` avec `images`). Les images sont maintenant
  transmises.
- Suppression de `"think": False` (n'est pas un paramètre valide de `/api/chat`).

#### Secrets

- `PowerShellVaultBackend` : détection automatique entre `powershell.exe`
  (PS 5.1) et `pwsh.exe` (PS 7) — teste le chargement du module
  `SecretManagement` sur chacun et garde celui qui réussit.
- `is_available()` ne vérifie plus qu'un vault est enregistré (bug original
  qui refusait les clés accessibles mais sans vault "registered").
- `__init__` ne lève plus `RuntimeError` si PowerShell est absent : l'objet
  reste constructible, `is_available()` retourne `False`, `get()` retourne `None`.

#### Tests

- `test_classifier.py` réécrit pour couvrir la cascade 3 étages.
- `test_installer.py` : mock `ensure_ollama_daemon` pour éviter les sleeps.
- `test_router.py` : ajout de 2 tests Markdown (`test_markdown_prepended_by_default`, `test_markdown_disabled`).
- `test_security.py` : `test_vault_no_powershell_unavailable` et
  `test_vault_is_available_fails_when_module_missing` (remplacent les anciens
  tests basés sur `stdout="null"`).

### Changed

- **`intake_from_csv` : breaking** — signature sans `column`, `prompt_template`
  par défaut `{table}`.
- **`Router.route`** : nouveau paramètre `ensure_markdown: bool = True`.
- **`HardwareInfo`** : constructeur accepte maintenant `ram_total_gb`,
  `ram_available_gb`, `disk_free_gb` (tous optionnels).
- **`BatchRunner`** : nouveaux paramètres `ensure_markdown`, `_cancel_event`.
- `README` simplifié : installation `pip install -e .` (plus d'extras
  `[guardrails]` / `[aws]` / `[azure]`, tout est dans `dependencies`).

### Removed

- `config/models.example.yaml` et `config/policy.example.yaml` : plus
  nécessaires, la configuration par défaut est embarquée.
- Instruction « `cp config/models.example.yaml ...` » du README.
- `--column` de la commande `intake from-csv`.
- Le paramètre `"think": False` du payload Ollama (n'existe pas).

### Fixed

- **Ollama multimodal** : les images n'étaient jamais transmises à `/api/chat`
  (le payload reconstruisait `messages` sans le champ `images`).
- **PowerShell Vault** : `is_available()` renvoyait `False` quand le module
  n'était pas trouvé, même si les clés étaient accessibles via `Get-Secret`.
- **Google AI 500** : ajout de retry avec backoff sur 5xx (transitoire).
- **Pylance gui.py** : `_on_review_select` signé avec `*_args: object` pour
  ignorer l'event Tkinter sans warning.
- **`gui.py` mypy** : `ModeDialog.result` correctement typé `LocalMode | None`,
  import `LocalMode` / `save_local_mode` en haut du fichier.
- **Pylance intake.py** : `_format_table` accepte `Sequence[str]` au lieu de
  `list[str]` (compatibilité `csv.DictReader.fieldnames`).

### Security

- Aucun `shell=True` nulle part (vérifié par `test_security.py`).
- `ensure_ollama_daemon` utilise `subprocess.Popen([...])` avec liste
  d'arguments et `start_new_session=True`.
- `scripts/refresh_ollama_library.py` : ne logge jamais le HTML brut, User-Agent
  identifié.

## [0.1.0] - 2026-01-01

Première version publique de `gateway-llm`, après refactorisation complète
du projet initial (`pipeline/`, `process_batch.py` de 880 lignes).

### Added

#### Architecture

- Package Python installable (`src/gateway_llm/`, `pyproject.toml` avec hatchling).
- Layout `src/` pour éviter les imports accidentels et supprimer les `sys.path.insert` dans les tests.
- Exports publics centralisés dans `gateway_llm/__init__.py`.

#### Providers

- Classe abstraite `Provider` avec `complete(model, prompt, max_tokens, temperature, image_b64)`.
- `OpenAICompatibleProvider` couvrant Groq, OpenRouter, Mistral, NVIDIA, Google AI Studio.
- `OllamaProvider` avec support multimodal (`images`).
- `CloudflareProvider` avec format de réponse spécifique.
- Support multimodal : `image_b64` transmis à `/chat/completions` (format OpenAI) ou `/api/chat` (format Ollama).

#### Router et orchestration

- Classe `Router` avec cascade par domaine, filtres policy/quota/hardware, guardrail en filtre final.
- `QuotaManager` avec **cooldown temporel** par provider (corrige le bug de compteur 429 cumulatif).
- `BudgetTracker` avec plafond en euros et arrêt contrôlé (`budget_exceeded`).
- `PolicyConfig` avec wildcards (`groq-*`), règle `default`, et `default_allow`.
- `HardwareInfo` avec détection VRAM (`nvidia-smi`, `rocm-smi`) et estimation de fit non bloquante.
- `BatchRunner` avec checkpointing, reprise (`--resume`), dry-run, et rapport final.
- `Checkpoint` avec écriture append + fsync.

#### Benchmarks dynamiques

- Module `benchmarks/` avec `BenchmarkSource` (ABC) et 4 adaptateurs :
  - `BenchLMAdapter` (BenchLM.ai)
  - `RankLLMsAdapter` (RankLLMs)
  - `F5SafetyAdapter` (F5 Labs CASI/ARS)
  - `RWSTranslationAdapter` (RWS TrainAI M-GATE)
- `BenchmarkCache` avec TTL 24h et refetch forcé.
- `BenchmarkAggregator` avec fusion multi-sources (moyenne) et re-ranking des chaînes.
- `normalize_model_name()` et `fuzzy_match()` pour appariement automatique des noms de modèles.
- **Refresh lazy au démarrage d'un batch** : si le cache a plus de 14 jours, il est rafraîchi automatiquement.
- Workflow GitHub Actions pour mise à jour bi-hebdomadaire des caches F5 et RWS.

#### Secrets

- Classe abstraite `SecretBackend` avec `get()`, `is_available()`, `set()` (défaut : retourne `False`).
- **6 backends** : PowerShell Vault, 1Password, HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Variables d'environnement.
- Imports cloud **lazy** : `import gateway_llm.secrets` fonctionne sans `boto3` ni `azure`.
- `get_backend()` avec résolution explicite (aucune bascule silencieuse vers `.env`).
- `save_backend_config()` qui persiste le choix dans `~/.gateway-llm/secrets.yaml`.
- Commande CLI `gateway-llm setup-secrets` avec assistant interactif.

#### Classification

- `TaskClassifier` avec mode LLM (qwen3:4b-instruct) + fallback regex.
- 9 domaines supportés dont `multimodal_extraction`.
- Priorité humaine, flags de risque (`POST_2024_FACT_CHECK`, `HIGH_RISK`, `SUBJECTIVE_NORMAL`).

#### Guardrails

- Classe abstraite `Guardrail` avec `GuardrailResult`.
- `NoOpGuardrail` (défaut, aucune dépendance).
- `NemoGuardrail`, avec normalisation `str` / `dict` / `GenerationResponse` et fail-open sur exception.

#### Intake (convertisseur de données)

- `intake_from_folder` : dossier d'images → JSONL.
- `intake_from_text` : dossier de fichiers texte → JSONL.
- `intake_from_csv` : colonne CSV → JSONL.
- `intake_from_urls` : liste d'URLs → JSONL, avec vérification `robots.txt` par défaut.
- Commande CLI `gateway-llm intake from-folder|from-text|from-csv|from-urls`.

#### Diagnostic et installation

- `Doctor` avec checks deps Python, binaire Ollama, daemon Ollama, modèles locaux, stockage des secrets.
- `Installer` avec téléchargement `ollama pull` interactif ou automatique (`--yes`).
- Commandes CLI `gateway-llm doctor` et `gateway-llm setup`.

#### Interface graphique

- Application `tkinter` unifiée (`python -m gateway_llm.gui`) avec 4 onglets.
- Ouverture automatique de l'onglet Configuration au premier lancement.
- Boutons Accepter / Rejeter pour les tâches `human_review`.

#### CLI

- `gateway-llm doctor`, `setup`, `setup-secrets`, `intake`, `benchmarks refresh`, `batch run`.
- `--help` exhaustif pour chaque commande avec épilogues et exemples.

#### Tests

- Suite complète de tests unitaires avec mocks (aucun réseau requis).
- Tests de sécurité explicites : pas de `shell=True`, échappement d'apostrophes, absence d'import cloud au niveau module.

#### CI/CD

- Matrice Python 3.11/3.12/3.13, ruff, mypy, bandit, pip-audit.
- `gitleaks` hebdomadaire.
- Mise à jour automatique F5/RWS tous les 14 jours.

#### Documentation

- `README.md`, `docs/THREAT_MODEL.md`, `docs/GUIDE_FR.md`, `docs/GUIDE_EN.md`.

### Changed

- **Refactorisation complète** du projet initial (`process_batch.py` de 880 lignes) en 20+ modules de < 200 lignes chacun.
- **Programmation orientée objet** systématique.
- **Logging** remplace les 92 `print` du projet initial.
- `guardrail_passed=False` **arrête la cascade** au lieu de relancer sur le modèle suivant.
- Le fichier de sortie JSONL contient `status` (`approved` / `human_review` / `failed` / `budget_exceeded`).
- `policy.yaml` accepte trois formes : `{allowed_providers: [...]}`, `[...]`, ou `ResidencyRule`.

### Removed

- `Playwright` et toutes les dépendances de navigateur du projet initial.
- Patches de stealth (`add_stealth_patches`, `USER_AGENT_BRAVE`, `PROFIL_ISOLE`, `BRAVE_PATH`).
- `extract_sources.py`, `auto_detect_selectors.py`, `config_urls.json`.
- Dossiers `approved/`, `sent/`, `human_review/`, `history/`, `site/`.
- Scripts `run_batch.bat` et `run_batch.sh`.
- `APScheduler`.
- Toute trace de `shell=True`.
- Compteur 429 cumulatif (`_PROVIDER_CALLS["__429_xxx"]`) remplacé par cooldown temporel.

### Fixed

- **Bug du compteur 429** : bannissait un provider pour la session entière après 2× 429.
- **`shell=True` avec f-string** dans `_get_secret`.
- **`sys.path.insert` dans les tests**.
- **État global mutable** (`_SECRET_CACHE`, `_GUARDRAILS_APP`, `_PROVIDER_CALLS`).
- **Imports Azure au niveau module**.
- **Incohérence `success` booléen vs réponse partielle**.

### Security

- Modèle de menace documenté (T1 à T15).
- `gitleaks` en CI.
- `pip-audit --strict` en CI.
- `bandit -r src/` en CI.
- Pas de `shell=True` nulle part.
- Backends de secrets à choix explicite.
- `~/.gateway-llm/secrets.yaml` ne contient jamais de secret final.
- Support `confidential` → `[ollama]` uniquement.

---

## Notes de migration depuis le projet original

| Projet original | `gateway-llm` |
| :--- | :--- |
| `process_batch.py` (880 lignes) | 20+ modules sous `src/gateway_llm/` |
| `_get_secret()` | `PowerShellVaultBackend.get()` |
| `call_llm_with_fallback()` | `Router.route()` |
| `classify_and_route_task()` | `TaskClassifier.classify()` |
| `check_response_with_guardrails()` | `NemoGuardrail.check()` |
| `generate_summary_report()` | `BatchRunner._print_report()` + `ResultsTab._refresh()` |
| `tasks.json` | `tasks.jsonl` (une ligne par tâche) |
| `approved/`, `sent/` | `results.jsonl` (champ `status`) |
| `human_review/human_review_summary.*` | `ResultsTab` onglet « À revoir » |
| `history/tasks_*.json` | Non conservé (chaque sortie JSONL est un historique) |
| `scrape.py` / `auto_detect_selectors.py` | Non conservé (supprimé) |

## Notes de migration de 0.1.0 vers 0.2.0

- `intake_from_csv()` n'accepte plus `column=` : toutes les colonnes sont lues.
  Le `prompt_template` par défaut est `{table}`.
- `Router.route()` accepte un nouveau paramètre `ensure_markdown: bool = True`.
  Pour désactiver, passer `ensure_markdown=False` ou utiliser `--no-markdown` en CLI.
- `detect_vram()` reste disponible (alias de `detect_hardware()`), mais
  retourne maintenant un `HardwareInfo` complet (RAM + disque inclus).
- `config/models.example.yaml` et `config/policy.example.yaml` sont supprimés.
  La config par défaut est embarquée dans `config.py` (`_DEFAULT_CONFIG`).
- `pyproject.toml` : `nemoguardrails` passe dans `dependencies` principal
  (plus d'extra `[guardrails]`).

[Unreleased]: https://github.com/Darki0n1/gateway-llm/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Darki0n1/gateway-llm/releases/tag/v0.2.0
[0.1.0]: https://github.com/Darki0n1/gateway-llm/releases/tag/v0.1.0