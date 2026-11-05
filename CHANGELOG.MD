# Changelog

Toutes les évolutions notables de ce projet sont documentées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère à [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

_(Rien pour l'instant — les prochaines évolutions seront ajoutées ici.)_

## [0.1.0] - 2026-01-01

Première version publique de `llm-gateway`, après refactorisation complète
du projet initial (`pipeline/`, `process_batch.py` de 880 lignes).

### Added

#### Architecture

- Package Python installable (`src/llm_gateway/`, `pyproject.toml` avec hatchling).
- Layout `src/` pour éviter les imports accidentels et supprimer les `sys.path.insert` dans les tests.
- Exports publics centralisés dans `llm_gateway/__init__.py`.

#### Providers

- Classe abstraite `Provider` avec `complete(model, prompt, max_tokens, temperature, image_b64)`.
- `OpenAICompatibleProvider` couvrant Groq, OpenRouter, Mistral, NVIDIA, Google AI Studio.
- `OllamaProvider` avec désactivation du Thinking (`think: false`) et support multimodal (`images`).
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
- `normalize_model_name()` et `fuzzy_match()` pour appariement automatique des noms de modèles sans table d'alias manuelle.
- **Refresh lazy au démarrage d'un batch** : si le cache a plus de 14 jours (`LLM_GATEWAY_BENCHMARK_TTL_DAYS`), il est rafraîchi automatiquement.
- Workflow GitHub Actions `.github/workflows/update-benchmarks.yml` pour mise à jour bi-hebdomadaire des caches F5 et RWS.

#### Secrets

- Classe abstraite `SecretBackend` avec `get()`, `is_available()`, `set()` (défaut : retourne `False`).
- **6 backends** :
  - `PowerShellVaultBackend` (Windows)
  - `OnePasswordBackend` (multi-OS)
  - `HashiCorpVaultBackend` (entreprise)
  - `AWSSecretsManagerBackend` (cloud AWS)
  - `AzureKeyVaultBackend` (cloud Azure)
  - `EnvSecretBackend` (fallback explicite, déconseillé)
- Imports cloud **lazy** : `import llm_gateway.secrets` fonctionne sans `boto3` ni `azure`.
- `get_backend()` avec résolution explicite (aucune bascule silencieuse vers `.env`).
- `save_backend_config()` qui persiste le choix dans `~/.llm-gateway/secrets.yaml` (hors repo, non commité).
- `missing_requirements()` qui détecte les packages pip manquants avant que l'utilisateur ne choisisse un backend.
- Commande CLI `llm-gateway setup-secrets` avec assistant interactif (machine perso / entreprise / cloud).

#### Classification

- `TaskClassifier` avec mode LLM (qwen3:4b-instruct) + fallback regex.
- 9 domaines supportés dont `multimodal_extraction` (images, screenshots, KPI).
- Priorité humaine, flags de risque (`MULTIMODAL_BLOCKED` supprimé, `POST_2024_FACT_CHECK`, `HIGH_RISK`, `SUBJECTIVE_NORMAL`).

#### Guardrails

- Classe abstraite `Guardrail` avec `GuardrailResult`.
- `NoOpGuardrail` (défaut, aucune dépendance).
- `NemoGuardrail` (extra `[guardrails]`), avec normalisation `str` / `dict` / `GenerationResponse` et fail-open sur exception.

#### Intake (convertisseur de données)

- `intake_from_folder` : dossier d'images → JSONL.
- `intake_from_text` : dossier de fichiers texte → JSONL.
- `intake_from_csv` : colonne CSV → JSONL.
- `intake_from_urls` : liste d'URLs → JSONL, avec vérification `robots.txt` par défaut.
- Commande CLI `llm-gateway intake from-folder|from-text|from-csv|from-urls`.

#### Diagnostic et installation

- `Doctor` avec checks deps Python, binaire Ollama, daemon Ollama, modèles locaux, stockage des secrets.
- `Installer` avec téléchargement `ollama pull` interactif ou automatique (`--yes`).
- Commande CLI `llm-gateway doctor` et `llm-gateway setup`.

#### Interface graphique

- Application `tkinter` unifiée (`python -m llm_gateway.gui`) avec **4 onglets** :
  1. Configuration (backend de secrets)
  2. Préparer les données (intake)
  3. Lancer le traitement (batch)
  4. Voir les résultats (rapport, à revoir, tout)
- Ouverture automatique de l'onglet Configuration au premier lancement.
- Boutons Accepter / Rejeter pour les tâches `human_review`, décisions écrites dans `decisions.jsonl`.

#### CLI

- `llm-gateway doctor` : diagnostic.
- `llm-gateway setup` : installation des modèles Ollama manquants.
- `llm-gateway setup-secrets` : configuration du backend de secrets.
- `llm-gateway intake` : convertisseur de données (4 sous-commandes).
- `llm-gateway benchmarks refresh` : rafraîchissement forcé.
- `llm-gateway batch run` : traitement par lot avec `--resume`, `--dry-run`, `--max-cost-eur`, `--no-classifier`, `--classifier-model`, `--no-doctor`, `--no-install`, `--yes`, `--verbose`.
- `--help` exhaustif pour chaque commande avec épilogues et exemples.

#### Tests

- Suite complète de tests unitaires avec mocks (aucun réseau requis).
- `test_router.py`, `test_quota.py`, `test_budget.py`, `test_policy.py`, `test_classifier.py`, `test_checkpoint.py`, `test_benchmarks.py`, `test_hardware.py`, `test_providers.py`, `test_security.py`, `test_doctor.py`, `test_installer.py`.
- Tests de sécurité explicites : pas de `shell=True`, échappement d'apostrophes, absence d'import cloud au niveau module.

#### CI/CD

- `.github/workflows/ci.yml` : matrice Python 3.11/3.12/3.13, ruff, mypy, bandit, pip-audit.
- `.github/workflows/secret-scan.yml` : gitleaks hebdomadaire.
- `.github/workflows/update-benchmarks.yml` : mise à jour automatique F5/RWS tous les 14 jours.

#### Documentation

- `README.md` : installation, quickstart, CLI complet, architecture, OOP, GUI, tests.
- `docs/THREAT_MODEL.md` : 15 menaces documentées (T1 à T15), actifs, hors périmètre, recommandations.
- `docs/GUIDE_FR.md` : guide utilisateur non technique (français).
- `docs/GUIDE_EN.md` : guide utilisateur non technique (anglais).
- `benchmarks_cache/f5_safety.json` et `rws_translation.json` : exemples documentés, mis à jour par CI.

### Changed

- **Refactorisation complète** du projet initial (`process_batch.py` de 880 lignes) en 20+ modules de < 200 lignes chacun.
- **Programmation orientée objet** systématique : chaque responsabilité est une classe, aucune variable module-level mutable.
- **Logging** remplace les 92 `print` du projet initial : `NullHandler` sur le logger racine, `dictConfig` pour le CLI, format texte ou JSON.
- `guardrail_passed=False` **arrête la cascade** au lieu de relancer sur le modèle suivant (comportement fidèle au projet original, corrigé par rapport à une première itération erronée).
- Le fichier de sortie JSONL contient désormais `status` (`approved` / `human_review` / `failed` / `budget_exceeded`) au lieu d'un booléen `success`.
- `models.example.yaml` : `qwen2.5vl:7b` remplacé par `qwen2.5vl:7b-q4_K_M` (quantification explicite Q4_K_M, ~6 Go).
- `policy.yaml` accepte trois formes : `{allowed_providers: [...]}`, `[...]`, ou `ResidencyRule`.

### Removed

- `Playwright` et toutes les dépendances de navigateur (`playwright`, `playwright-stealth`).
- Patches de stealth (`add_stealth_patches`, `USER_AGENT_BRAVE`, `PROFIL_ISOLE`, `BRAVE_PATH`).
- `extract_sources.py`, `auto_detect_selectors.py`, `config_urls.json` (scraping web).
- `Nemoguardrails` en dépendance obligatoire → devenu extra `[guardrails]`.
- Dossiers `approved/`, `sent/`, `human_review/`, `history/`, `site/` du projet initial.
- Scripts `run_batch.bat` et `run_batch.sh` (remplacés par la GUI et le CLI).
- `APScheduler` (le refresh lazy + GitHub Actions couvrent le besoin).
- Toute trace de `shell=True` dans le code.
- Compteur 429 cumulatif (`_PROVIDER_CALLS["__429_xxx"]`) remplacé par cooldown temporel.

### Fixed

- **Bug du compteur 429** : le compteur original n'était jamais remis à zéro, bannissant un provider pour la session entière après 2× 429. Corrigé par `QuotaManager` avec `time.monotonic()` et expiration naturelle.
- **`shell=True` avec f-string** dans `_get_secret` : remplacé par `subprocess.run([...])` avec liste d'arguments et échappement d'apostrophes.
- **`sys.path.insert` dans les tests** : supprimé par le layout `src/` + installation editable.
- **État global mutable** (`_SECRET_CACHE`, `_GUARDRAILS_APP`, `_PROVIDER_CALLS`) : encapsulé dans des instances injectables.
- **Imports Azure au niveau module** : déplacés en lazy import pour ne pas casser `import llm_gateway.secrets` si azure n'est pas installé.
- **Incohérence `success` booléen vs réponse partielle** : introduction du champ `status` explicite.

### Security

- Modèle de menace documenté (`docs/THREAT_MODEL.md`) avec 15 entrées T1–T15.
- Vérification `gitleaks` en CI (workflow hebdomadaire).
- `pip-audit --strict` en CI.
- `bandit -r src/` en CI.
- Pas de `shell=True` nulle part.
- Backends de secrets à choix explicite : aucune bascule silencieuse vers `.env`.
- `~/.llm-gateway/secrets.yaml` ne contient jamais de secret final, seulement la config du backend.
- Recommendation `chmod 600` documentée pour le fichier de config.
- Support `confidential` → `[ollama]` uniquement pour les données sensibles (y compris screenshots avec KPI).

---

## Notes de migration depuis le projet original

Si vous venez du projet `pipeline/` initial, voici les correspondances :

| Projet original | `llm-gateway` |
| :--- | :--- |
| `process_batch.py` (880 lignes) | 15+ modules sous `src/llm_gateway/` |
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

[Unreleased]: https://github.com/Darki0n1/llm-gateway/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Darki0n1/llm-gateway/releases/tag/v0.1.0