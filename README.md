# gateway-llm

> **Quality-Gated Batch Router** — Routage LLM par cascade, guardrails, budget maîtrisé, résidence des données respectée.

[![CI](https://github.com/darki0n1/gateway-llm/actions/workflows/ci.yml/badge.svg)](https://github.com/darki0n1/gateway-llm/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)

---

## Pourquoi ce projet ?

Les gateways LLM existants (LiteLLM, OpenRouter, Portkey…) optimisent le routage **synchrone** : proxy, latence, streaming. Les workloads **batch** (enrichissement de bases, résumés massifs, classification de tickets, traduction de catalogues) ont des contraintes différentes :

- Le **coût unitaire** est critique : 100 000 appels × 0,01 € = 1 000 €.
- La **qualité** doit être **vérifiable** sur échantillon, pas seulement « le modèle a répondu ».
- La **résidence des données** (RGPD, AI Act) est un critère de routage à part entière.
- Le **budget** doit être planifié et arrêté proprement, pas découvert sur la facture.
- Un batch sur laptop doit pouvoir **reprendre après une coupure**.

`gateway-llm` répond à ces cinq besoins avec une thèse simple : **ne payer un modèle cher que lorsque le guardrail prouve qu'un modèle bon marché ne suffit pas**, et router selon des contraintes de souveraineté.

## Principes

1. **Cascade par qualité** — la chaîne de modèles est ordonnée par benchmarks (meilleurs d'abord), les free trials en tête pour être drainés en priorité.
2. **Guardrail en filtre final** — la vérification qualité tourne **une fois** sur la première réponse réussie. Un guardrail en échec **termine** la chaîne et la tâche part en revue humaine.
3. **Benchmarks dynamiques** — les scores de BenchLM / RankLLMs / F5 / RWS réordonnent la chaîne automatiquement.
4. **Refresh automatique des benchmarks** — au démarrage d'un batch, si le cache a plus de 14 jours (configurable via `GATEWAY_LLM_BENCHMARK_TTL_DAYS`), il est rafraîchi automatiquement.
5. **Politique de résidence** — chaque tâche porte une sensibilité (`public`, `internal`, `confidential`) qui filtre les providers autorisés avant toute tentative.
6. **Budget par lot** — un plafond optionnel (`--max-cost-eur`) arrête d'escalader quand il serait dépassé.
7. **Checkpointing** — la sortie JSONL est écrite ligne par ligne avec `fsync`. `--resume` reprend après interruption.
8. **Sélection locale dynamique** — les modèles Ollama à installer sont choisis en croisant benchmarks × hardware (VRAM + RAM + disque). Aucune liste de modèles en dur.
9. **Secrets explicites** — aucun backend de secrets par défaut. L'utilisateur choisit entre PowerShell Vault, 1Password, HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, ou variables d'environnement (déconseillé).
10. **Classification en cascade** — 3 étages (regex → embeddings → LLM) pour un coût 10× inférieur au LLM pur, sans sacrifier la précision.

## Installation

```bash
pip install gateway-llm
```

Le package inclut toutes les dépendances : `nemoguardrails`, `psutil`, `playwright`, `tkinterdnd2`, `boto3`, `azure-identity`, `beautifulsoup4`. Aucun extra à installer.

Le package est **typé** (`py.typed` inclus, PEP 561) : mypy et pyright fonctionnent out-of-the-box chez les consommateurs.

**Chromium (une seule fois)** : le scraping du catalogue Ollama utilise Playwright. La GUI installe Chromium automatiquement au premier lancement. Pour un usage CLI-only, lancez une fois :

```bash
playwright install chromium
```

**Depuis les sources (développement)** :

```bash
git clone https://github.com/darki0n1/gateway-llm.git
cd gateway-llm
pip install -e ".[dev]"
```

## Quickstart

### 1. Lancer la GUI

```bash
python -m gateway_llm.gui
```

Au premier lancement, deux étapes :

1. **Mode d'exécution** — choisissez entre `100% cloud`, `100% local`, `hybride`, ou `défaut` (bootstrap qwen). Le choix est persisté dans `~/.gateway-llm/config.yaml`.
2. **Configuration des secrets** — choisissez le coffre-fort (voir section suivante).

### 2. Configuration des secrets

```bash
gateway-llm setup-secrets
```

Assistant interactif :

- **Machine personnelle** : PowerShell Vault (Windows), 1Password CLI
- **Machine d'entreprise** : HashiCorp Vault, AWS Secrets Manager, Azure Key Vault
- **Fallback explicite** : variables d'environnement (averti comme non chiffré)

Le choix est persisté dans `~/.gateway-llm/secrets.yaml`. Ce fichier ne contient **jamais** de secret final : seulement le nom du backend et ses options de connexion.

### 3. Diagnostic

```bash
gateway-llm doctor
```

La configuration par défaut est embarquée dans le code (`_DEFAULT_CONFIG` dans `config.py`). Aucun fichier YAML à créer pour démarrer.

### 4. Intake (conversion des données)

```bash
gateway-llm intake from-folder --path ./screenshots --output tasks.jsonl
gateway-llm intake from-text --path ./emails --output tasks.jsonl
gateway-llm intake from-csv --path tickets.csv --output tasks.jsonl
gateway-llm intake from-urls --path urls.txt --output tasks.jsonl
```

### 5. Lancer un batch

```bash
gateway-llm batch run --input tasks.jsonl --output results.jsonl --max-cost-eur 5.0
```

Entrée `tasks.jsonl` :

```jsonl
{"id": "t1", "prompt": "Corrige cette fonction Python : ...", "sensitivity": "internal"}
{"id": "t2", "prompt": "Extrais les KPI de ce screenshot", "sensitivity": "public", "image_path": "./screenshots/kpi_q3.png"}
```

Sortie `results.jsonl` :

```jsonl
{"id": "t1", "status": "approved", "response": "...", "model_used": "qwen-27bauto", "provider": "ollama", "guardrail_passed": true, "cost_eur": 0.0, "escalations": 0, "had_image": false}
```

### 6. Estimer avant de lancer (dry-run)

```bash
gateway-llm batch run --input tasks.jsonl --dry-run --sample 20
```

### 7. Reprendre après interruption

```bash
gateway-llm batch run --input tasks.jsonl --output results.jsonl --resume
```

## CLI — Vue d'ensemble

| Commande | Description |
| :--- | :--- |
| `gateway-llm doctor` | Diagnostic de l'environnement (deps, Ollama, secrets) |
| `gateway-llm setup` | Installation guidée des modèles Ollama bootstrap |
| `gateway-llm setup-secrets` | Choisir et configurer le backend de secrets |
| `gateway-llm batch run --input ... --output ...` | Lance un batch |
| `--resume` | Reprend un batch interrompu |
| `--dry-run --sample N` | Estime sans appeler les modèles |
| `--max-cost-eur X` | Budget maximal en euros |
| `--no-classifier` | Désactive la classification automatique |
| `--classifier-model NAME` | Modèle de classification (défaut `qwen3:4b-instruct`) |
| `--no-markdown` | Désactive l'instruction « réponds en Markdown » |
| `--no-doctor` | Skip le pre-flight (utile en CI) |
| `--no-install` | Pre-flight sans installation auto |
| `gateway-llm intake from-folder` | Dossier d'images → JSONL |
| `gateway-llm intake from-text` | Dossier de textes → JSONL |
| `gateway-llm intake from-csv` | Un ou plusieurs CSV → JSONL (toutes les colonnes) |
| `gateway-llm intake from-urls` | URLs → JSONL (respecte robots.txt) |
| `gateway-llm benchmarks refresh` | Force le rafraîchissement du cache |

**Note** : `--config` et `--policy` sont optionnels. S'ils sont omis, la configuration embarquée (`_DEFAULT_CONFIG` / `_DEFAULT_POLICY`) est utilisée.

## Modes d'exécution

Sélectionnés au premier lancement de la GUI, persistés dans `~/.gateway-llm/config.yaml` :

| Mode | Comportement |
| :--- | :--- |
| **100% cloud** | Utilise uniquement les APIs cloud. Classification via `flexrouter` (bucket `low`). Aucun modèle local. |
| **100% local** | Télécharge les meilleurs modèles Ollama pour la machine (croisement benchmarks × VRAM + RAM + disque). Aucune donnée ne sort. |
| **Hybride** | Utilise les modèles locaux déjà présents, complète avec le cloud quand un meilleur modèle cloud est disponible. |
| **Défaut** | Modèles bootstrap uniquement (`qwen3:4b-instruct`, `nomic-embed-text`, plus les modèles des chaînes de domaine par défaut). |

## Sélection locale dynamique

Le mode **100% local** ne repose sur **aucune liste de modèles en dur**. L'algorithme :

1. Charge le catalogue Ollama (`benchmarks_cache/ollama_library.json`, scrapé par `scripts/refresh_ollama_library.py`).
2. Pour chaque domaine de la config, récupère les scores de benchmark (`BenchLM`, `RankLLMs`, `F5`, `RWS`).
3. Filtre les modèles dont la mémoire runtime (`taille_fichier × 1.3`) dépasse la capacité effective de la machine (`VRAM + RAM_disponible × 0.7`).
4. Classe par score décroissant, garde le top N par domaine.
5. Télécharge via `Installer.ensure_models()`.

Ainsi, si `qwen4.0-40b-q4_K_M` sort demain et surclasse le modèle actuel, il sera automatiquement choisi — à condition que la machine puisse le faire tourner.

## Classification en cascade

`TaskClassifier` implémente la cascade à 3 étages recommandée par la littérature 2026 :

1. **Règles déterministes** (regex) — détecte les blocages critiques (dates post-2024, sécurité, subjectif). Prime sur tout le reste.
2. **Embeddings** (`nomic-embed-text` via Ollama) — cosine similarity sur des phrases d'exemple par domaine. Seuils calibrés :
   - `score >= 0.82` → acceptation directe (`decision_layer="embedding"`)
   - `0.60 <= score < 0.82` → LLM tiebreaker si disponible, sinon embedding avec priorité humaine >= 4
   - `score < 0.60` → LLM direct (ou fallback regex si LLM indisponible)
3. **LLM** (`qwen3:4b-instruct` par défaut) — fallback pour les cas ambigus ou hors distribution.

Chaque résultat porte `confidence` (score) et `decision_layer` (`regex` | `embedding` | `llm` | `fallback`) pour l'audit.

## Backends de secrets supportés

| Backend | Installation | Cas d'usage |
| :--- | :--- | :--- |
| PowerShell Vault | Natif Windows | Machine perso Windows (recommandé) |
| 1Password CLI | Binaire `op` à installer | Machine perso Mac/Linux |
| HashiCorp Vault | `requests` (déjà installé) | Entreprise DevOps |
| AWS Secrets Manager | `boto3` (déjà installé) | Cloud AWS |
| Azure Key Vault | `azure-identity` (déjà installé) | Cloud Azure |
| Variables d'environnement | Aucune | CI pure, déconseillé ailleurs |

La commande `setup-secrets` détecte automatiquement les dépendances manquantes.

## Multimodal — lecture de screenshots et KPI

Le domaine `multimodal_extraction` envoie une image (screenshot, graphique, tableau) au modèle. Deux backends :

- **Cloud (Google AI Studio)** : `gemma-4-31b-it`, meilleur OCR et compréhension d'interface du panel 2026.
- **Local (Ollama)** : `qwen2.5vl:7b-q4_K_M` (~6 Go), tient sur un GPU 8 Go, fallback quand la politique interdit le cloud.

Le champ `image_path` dans le JSONL d'entrée pointe vers un fichier local, ou `image_b64` contient directement la chaîne base64.

## CSV — toutes les colonnes

`intake_from_csv` lit **tout le tableau** (toutes les colonnes + toutes les lignes), formaté en pseudo-JSON pour minimiser les tokens. Le modèle choisit lui-même les colonnes pertinentes selon la consigne utilisateur. Plus de sélection de colonne unique.

Pour les gros CSV, les lignes sont traitées par lots de 500 (`max_rows`) avec troncature à 30 000 caractères (`max_chars`).

**Multi-CSV** : `intake_from_csv_multi` fusionne plusieurs CSV en un seul JSONL, avec préfixe du nom de fichier sur les IDs pour éviter les collisions.

**Mixte** : `intake_mixed` accepte images + textes + CSV en une seule session. La consigne est appliquée à toutes les sources.

## Architecture

```
gateway-llm/
├── pyproject.toml
├── README.md · LICENSE.txt · CHANGELOG.md · CONTRIBUTING.md
├── benchmarks_cache/
│   ├── f5_safety.json
│   ├── rws_translation.json
│   ├── ollama_library.json
│   └── benchlm_*.json / rankllms_*.json
├── scripts/
│   ├── refresh_f5.py
│   ├── refresh_rws.py
│   └── refresh_ollama_library.py
├── src/gateway_llm/
│   ├── py.typed
│   ├── providers/
│   ├── guardrails/
│   ├── benchmarks/
│   ├── router.py
│   ├── quota.py
│   ├── budget.py
│   ├── policy.py
│   ├── classifier.py
│   ├── semantic_router.py
│   ├── local_selector.py
│   ├── checkpoint.py
│   ├── hardware.py
│   ├── secrets.py
│   ├── config.py
│   ├── doctor.py
│   ├── installer.py
│   ├── intake.py
│   ├── gui.py
│   ├── batch.py
│   ├── cli.py
│   └── logging.py
├── tests/
├── docs/
│   ├── THREAT_MODEL.md
│   ├── GUIDE_FR.md
│   ├── GUIDE_EN.md
│   └── adr/
└── .github/workflows/
```

## Programmation orientée objet

| Classe | Responsabilité |
| :--- | :--- |
| `Provider` (ABC) | Interface d'appel à un backend LLM |
| `OpenAICompatibleProvider` / `OllamaProvider` / `CloudflareProvider` | Implémentations concrètes |
| `Router` | Cascade + filtres (policy, quota, hardware) + guardrail |
| `QuotaManager` | Cooldown par provider sur 429 |
| `BudgetTracker` | Coût cumulé + plafond |
| `PolicyConfig` | Filtre de résidence |
| `Guardrail` (ABC) | Interface de vérification qualité |
| `NoOpGuardrail` / `NemoGuardrail` | Implémentations |
| `BenchmarkSource` (ABC) | Interface d'une source de benchmarks |
| `BenchLMAdapter` / `RankLLMsAdapter` / `F5SafetyAdapter` / `RWSTranslationAdapter` | Implémentations |
| `BenchmarkCache` | Cache JSON avec TTL |
| `BenchmarkAggregator` | Fusion multi-sources + re-ranking |
| `TaskClassifier` | Cascade 3 étages |
| `SemanticRouter` | Embeddings cosine via Ollama |
| `Checkpoint` | Reprise après interruption |
| `HardwareInfo` | Détection VRAM + RAM + disque + `effective_capacity_gb()` |
| `SecretBackend` (ABC) | Interface de stockage de secrets |
| `PowerShellVaultBackend` / `OnePasswordBackend` / `HashiCorpVaultBackend` / `AWSSecretsManagerBackend` / `AzureKeyVaultBackend` / `EnvSecretBackend` | 6 implémentations |
| `Doctor` | Diagnostic de l'environnement |
| `Installer` | Téléchargement Ollama + daemon |
| `LocalSelector` (module) | Sélection benchmarks × hardware |
| `BatchRunner` | Orchestre le batch complet |

Aucune variable module-level mutable. Chaque instance est injectée explicitement.

## Application graphique (GUI)

```bash
python -m gateway_llm.gui
```

Quatre onglets :

0. **Configuration** : choix du backend de secrets (obligatoire au premier lancement).
1. **Préparer les données** : dossier d'images, fichiers texte, CSV (multi), URLs, ou mode **Mixte**. Drag & drop accepté sur la liste.
2. **Lancer le traitement** : input / output / config / budget, barre de progression, bouton **Annuler**, logs en direct.
3. **Voir les résultats** : chargement automatique après un batch (auto-refresh 2s), rendu Markdown, boutons Accepter / Rejeter.

## Tests

```bash
pytest
pytest -v --cov=gateway_llm --cov-fail-under=60
```

La CI GitHub Actions exécute :

- `pytest` sur Python 3.11, 3.12, 3.13 avec seuil de couverture (60%)
- `ruff check` + `ruff format --check`
- `mypy src/ scripts/`
- `bandit -r src/` + `pip-audit --strict`
- `gitleaks` (workflow séparé, hebdomadaire)

Dependabot met à jour les dépendances pip et les actions GitHub chaque semaine.

## Documentation

- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) — modèle de menace complet (T1 à T20).
- [`docs/GUIDE_FR.md`](docs/GUIDE_FR.md) — guide utilisateur non technique (français).
- [`docs/GUIDE_EN.md`](docs/GUIDE_EN.md) — guide utilisateur non technique (anglais).
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — comment contribuer.
- [`CHANGELOG.md`](CHANGELOG.md) — historique des versions.
- [`docs/adr/`](docs/adr/) — Architecture Decision Records.

## Roadmap

### 0.2.0 — base actuelle ✅
Cascade router, guardrails, 6 backends de secrets, multimodal, CSV complet, GUI, CI complète, threat model T1–T20, `py.typed`.

### 0.3.0 — service & observabilité 🔜
- **FastAPI** : `BatchRunner` exposé en service HTTP (`/health`, `/route`, `/batch`, `/metrics`).
- **vLLM & AWQ** : provider `vllm` (OpenAI-compatible), modèle 7B/8B AWQ, gain x5–x10 vs Ollama.
- **Prometheus / Grafana** : métriques `gateway_llm_calls_total`, `gateway_llm_cost_eur`, `gateway_llm_latency_seconds`.
- **Docker Compose** : API + vLLM + Prometheus + Grafana + Qdrant + Langfuse.
- **Golden set & RAGAS CI** : régression qualité dans la CI.
- **Observabilité Langfuse** : tracing de chaque `provider.complete()`.

### 0.4.0 — production-grade 🔜
- **Shadow mode / rollout** : comparaison A/B sans impact utilisateur, canary progressif.
- **RAG end-to-end** : chunking, hybrid search (BM25 + dense), reranker.
- **MCP server** : gateway exposée comme outil pour Claude Desktop / Cursor.
- **OAuth 2.1 + webhooks signés** : auth utilisateur et notifications HMAC-SHA256.

## Contribuer

```bash
pip install -e ".[dev]"
ruff check src/ tests/
mypy src/
pytest
```

Inclure des tests pour toute nouvelle fonctionnalité. Ne jamais committer de secrets (voir `docs/THREAT_MODEL.md` et [`CONTRIBUTING.md`](CONTRIBUTING.md)).

## Licence

Apache License 2.0 — voir [`LICENSE.txt`](LICENSE.txt).