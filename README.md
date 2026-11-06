# gateway-llm

> **Quality-Gated Batch Router** — Routage LLM par cascade, guardrails, budget maîtrisé, résidence des données respectée.

[![CI](https://github.com/darki0n1/gateway-llm/actions/workflows/ci.yml/badge.svg)](https://github.com/<vous>/gateway-llm/actions/workflows/ci.yml)
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
2. **Guardrail en filtre final** — la vérification qualité (NeMo, NoOp) tourne **une fois** sur la première réponse réussie. Un guardrail en échec **termine** la chaîne et la tâche part en revue humaine. Il ne relance pas la cascade.
3. **Benchmarks dynamiques** — les scores de BenchLM / RankLLMs / F5 / RWS peuvent réordonner la chaîne automatiquement (`--rank-by-benchmarks`).
4. **Refresh automatique des benchmarks** — au démarrage d'un batch, si le cache a plus de 14 jours (configurable via `gateway_llm_BENCHMARK_TTL_DAYS`), il est rafraîchi automatiquement. Combiné au workflow GitHub Actions bi-hebdomadaire, l'utilisateur n'a jamais à lancer `benchmarks refresh` manuellement.
5. **Politique de résidence** — chaque tâche porte une sensibilité (`public`, `internal`, `confidential`) qui filtre les providers autorisés avant toute tentative.
6. **Budget par lot** — un plafond optionnel (`--max-cost-eur`) arrête d'escalader quand il serait dépassé.
7. **Checkpointing** — la sortie JSONL est écrite ligne par ligne avec `fsync`. `--resume` reprend après interruption.
8. **Hardware-aware** — la VRAM est détectée (`nvidia-smi`, `rocm-smi`) et un ratio taille/VRAM est loggé, **sans bloquer** par défaut.
9. **Secrets explicites** — aucun backend de secrets par défaut. L'utilisateur choisit entre PowerShell Vault, 1Password, HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, ou variables d'environnement (déconseillé).

## Installation

### Pour utiliser l'application

```bash
pip install gateway-llm
```
Puis lancer : 
```bash
python -m gateway_llm.gui
```

```bash
git clone https://github.com/<vous>/gateway-llm.git
cd gateway-llm

# Installation minimale (NoOpGuardrail par défaut, pas de backend cloud)
pip install -e .

# Avec guardrails NeMo (détection d'hallucinations)
pip install -e ".[guardrails]"

# Avec backend cloud AWS Secrets Manager
pip install -e ".[aws]"

# Avec backend cloud Azure Key Vault
pip install -e ".[azure]"

# Avec outils de dev
pip install -e ".[dev]"
```

## Quickstart

### 1. Configuration

```bash
cp config/models.example.yaml config/models.yaml
cp config/policy.example.yaml config/policy.yaml
```

`config/models.yaml` déclare les providers, les modèles, leurs prix et les chaînes par domaine. Il doit être **gitignoré** (ne jamais committer vos secrets ni vos chaînes de production). `config/policy.yaml` déclare les règles de résidence.

### 2. Configuration des secrets

Au premier lancement, `gateway-llm` exige un backend de secrets configuré. Aucune bascule silencieuse vers un `.env`.

```bash
gateway-llm setup-secrets
```

Un assistant interactif vous propose :

- **Machine personnelle** : PowerShell Vault (Windows, recommandé), 1Password CLI
- **Machine d'entreprise** : HashiCorp Vault, AWS Secrets Manager, Azure Key Vault
- **Fallback explicite** : variables d'environnement (averti comme non chiffré)

Le choix est persisté dans `~/.gateway-llm/secrets.yaml`. Ce fichier ne contient **jamais** de secret final : seulement le nom du backend et ses options de connexion (URL, région, vault). Les clés API restent dans le coffre-fort natif (PowerShell SecretStore, 1Password, HashiCorp, AWS, Azure).

### 3. Diagnostic et installation des modèles

```bash
# Vérifie deps Python, binaire Ollama, daemon, modèles locaux, stockage secrets
gateway-llm doctor --config config/models.yaml

# Télécharge les modèles Ollama manquants (interactif)
gateway-llm setup --config config/models.yaml
```

### 4. Lancer un batch

```bash
# Depuis la racine du projet
gateway-llm batch run \
  --input prompts.jsonl \
  --output results.jsonl \
  --config config/models.yaml \
  --policy config/policy.yaml \
  --max-cost-eur 5.0
```

Entrée `prompts.jsonl`, une tâche par ligne :

```jsonl
{"id": "t1", "prompt": "Corrige cette fonction Python : ...", "sensitivity": "internal"}
{"id": "t2", "prompt": "Extrais les KPI de ce screenshot", "sensitivity": "public", "image_path": "./screenshots/kpi_q3.png"}
```

Sortie enrichie `results.jsonl` :

```jsonl
{"id": "t1", "status": "approved", "response": "...", "model_used": "qwen-27bauto", "provider": "ollama", "guardrail_passed": true, "cost_eur": 0.0, "escalations": 0, "had_image": false}
{"id": "t2", "status": "approved", "response": "...", "model_used": "gemma-4-31b-it", "provider": "google_ai", "guardrail_passed": true, "cost_eur": 0.0, "escalations": 0, "had_image": true}
```

### 5. Estimer avant de lancer (dry-run)

```bash
gateway-llm batch run --input prompts.jsonl --dry-run --sample 20
```

Extrapole le coût total et le temps d'exécution **sans appeler** les modèles.

### 6. Reprendre après interruption

```bash
gateway-llm batch run --input prompts.jsonl --output results.jsonl --resume
```

Saute les IDs déjà présents dans `results.jsonl`.

### 7. Rafraîchir les benchmarks manuellement (optionnel)

```bash
gateway-llm benchmarks refresh
```

Récupère les derniers scores de BenchLM et RankLLMs. En pratique, rarement nécessaire : le refresh lazy (démarrage de batch) et le workflow GitHub Actions le font automatiquement.

## CLI — Vue d'ensemble

| Commande | Description |
| :--- | :--- |
| `gateway-llm doctor` | Diagnostic de l'environnement (deps, Ollama, secrets) |
| `gateway-llm setup` | Installation guidée des modèles Ollama manquants |
| `gateway-llm setup-secrets` | Choisir et configurer le backend de secrets |
| `gateway-llm batch run --input ... --output ...` | Lance un batch |
| `--resume` | Reprend un batch interrompu |
| `--dry-run --sample N` | Estime sans appeler |
| `--refresh-benchmarks` | Force le rafraîchissement immédiat |
| `--rank-by-benchmarks` | Réordonne les chaînes par benchmarks |
| `--max-cost-eur X` | Budget maximal en euros |
| `--no-classifier` | Désactive la classification automatique |
| `--classifier-model NAME` | Modèle Ollama de classification |
| `gateway-llm intake from-folder` | Dossier d'images → JSONL |
| `gateway-llm intake from-text` | Dossier de textes → JSONL |
| `gateway-llm intake from-csv` | CSV → JSONL |
| `gateway-llm intake from-urls` | URLs → JSONL (respecte robots.txt) |
| `gateway-llm benchmarks refresh` | Force le rafraîchissement du cache |

## Backends de secrets supportés

| Backend | Installation | Cas d'usage |
| :--- | :--- | :--- |
| PowerShell Vault | Natif Windows | Machine perso Windows (recommandé) |
| 1Password CLI | Binaire `op` à installer | Machine perso Mac/Linux |
| HashiCorp Vault | `requests` (déjà installé) | Entreprise DevOps |
| AWS Secrets Manager | `pip install -e ".[aws]"` | Cloud AWS |
| Azure Key Vault | `pip install -e ".[azure]"` | Cloud Azure |
| Variables d'environnement | Aucune | CI pure, déconseillé ailleurs |

La commande `setup-secrets` détecte automatiquement les dépendances manquantes et propose la commande d'installation adaptée.

## Multimodal — lecture de screenshots et KPI

Le domaine `multimodal_extraction` permet d'envoyer une image (screenshot, graphique, tableau) au modèle. Deux backends :

- **Cloud (Google AI Studio)** : `gemma-4-31b-it`, meilleur OCR et compréhension d'interface du panel 2026. Recommandé pour les KPI denses.
- **Local (Ollama)** : `qwen2.5vl:7b-q4_K_M` (~6 Go), tient sur un GPU 8 Go, fallback quand la politique interdit le cloud ou quand le réseau est absent.

Le champ `image_path` dans le JSONL d'entrée pointe vers un fichier local, ou `image_b64` contient directement la chaîne base64.

## Architecture

```
gateway-llm/
├── pyproject.toml
├── README.md · LICENSE · .gitignore
├── benchmarks_cache/           # caches BenchLM/RankLLMs (gitignored)
│                               # + f5_safety.json / rws_translation.json (commités, maj CI)
├── config/
│   ├── models.example.yaml     # providers, modèles, chaînes par domaine
│   └── policy.example.yaml     # politique de résidence
├── src/gateway_llm/
│   ├── providers/              # base, openai_compat, ollama, cloudflare
│   ├── guardrails/             # base, noop, nemo
│   ├── benchmarks/             # base, benchlm, rankllms, f5, rws, cache, aggregator, normalizer
│   ├── router.py               # cascade + guardrail + policy + hardware + budget + multimodal
│   ├── quota.py                # cooldown temporel (fix bug 429)
│   ├── budget.py               # plafond par lot
│   ├── policy.py               # résidence des données
│   ├── classifier.py           # classification par domaine
│   ├── checkpoint.py           # reprise après interruption
│   ├── hardware.py             # détection VRAM
│   ├── secrets.py              # 6 backends interchangeables
│   ├── config.py               # validation pydantic
│   ├── doctor.py               # diagnostic environnement
│   ├── installer.py            # téléchargement modèles Ollama
│   ├── intake.py               # convertisseur de données
│   ├── gui.py                  # application graphique unifiée (4 onglets)
│   ├── batch.py                # orchestrateur
│   ├── cli.py                  # argparse
│   └── logging.py              # NullHandler + dictConfig
├── tests/                      # tests unitaires (mocks, pas de réseau)
├── docs/
│   ├── THREAT_MODEL.md
│   ├── GUIDE_FR.md
│   └── GUIDE_EN.md
└── .github/workflows/          # CI + secret scan + update benchmarks
```

## Programmation orientée objet

Chaque responsabilité est une **classe** :

| Classe | Responsabilité |
| :--- | :--- |
| `Provider` (ABC) | Interface d'appel à un backend LLM |
| `OpenAICompatibleProvider` / `OllamaProvider` / `CloudflareProvider` | Implémentations concrètes (avec support multimodal) |
| `Router` | Cascade + filtres (policy, quota, hardware) + guardrail |
| `QuotaManager` | Cooldown par provider sur 429 |
| `BudgetTracker` | Coût cumulé + plafond |
| `PolicyConfig` | Filtre de résidence |
| `Guardrail` (ABC) | Interface de vérification qualité |
| `NoOpGuardrail` / `NemoGuardrail` | Implémentations |
| `BenchmarkSource` (ABC) | Interface d'une source de benchmarks |
| `BenchLMAdapter` / `RankLLMsAdapter` / `F5SafetyAdapter` / `RWSTranslationAdapter` | Implémentations |
| `BenchmarkCache` | Cache JSON avec TTL |
| `TaskClassifier` | Classification LLM + fallback regex (inclut `multimodal_extraction`) |
| `Checkpoint` | Reprise après interruption |
| `HardwareInfo` | Détection VRAM et fit |
| `SecretBackend` (ABC) | Interface de stockage de secrets |
| `PowerShellVaultBackend` / `OnePasswordBackend` / `HashiCorpVaultBackend` / `AWSSecretsManagerBackend` / `AzureKeyVaultBackend` / `EnvSecretBackend` | 6 implémentations |
| `Doctor` | Diagnostic de l'environnement |
| `Installer` | Téléchargement des modèles Ollama |
| `BatchRunner` | Orchestre le batch complet |

Aucune variable module-level mutable. Chaque instance est injectée explicitement.

## Application graphique (GUI)

Pour les utilisateurs non techniques :

```bash
python -m gateway_llm.gui
```

Quatre onglets :

0. **Configuration** : choix du backend de secrets (obligatoire au premier lancement, ensuite optionnel).
1. **Préparer les données** : dossier d'images, de fichiers texte, CSV, ou liste d'URLs → génération du JSONL de tâches.
2. **Lancer le traitement** : sélection input / output / config / budget, barre de progression.
3. **Voir les résultats** : rapport (approuvées / à revoir / échouées / coût), liste des tâches signalées avec boutons Accepter / Rejeter, vue complète.

## Tests

```bash
pytest
pytest -v --cov=gateway_llm
```

La CI GitHub Actions exécute :

- `pytest` sur Python 3.11, 3.12, 3.13
- `ruff check` + `ruff format --check`
- `mypy src/`
- `bandit -r src/` + `pip-audit --strict`
- `gitleaks` (workflow séparé, hebdomadaire)

## Documentation

- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) — modèle de menace complet.
- [`docs/GUIDE_FR.md`](docs/GUIDE_FR.md) — guide utilisateur non technique (français).
- [`docs/GUIDE_EN.md`](docs/GUIDE_EN.md) — guide utilisateur non technique (anglais).
- `config/models.example.yaml` — exemple de providers et chaînes.
- `config/policy.example.yaml` — exemple de politique de résidence.

## Contribuer

```bash
pip install -e ".[dev]"
ruff check src/ tests/
pytest
```

Inclure des tests pour toute nouvelle fonctionnalité. Ne jamais committer de secrets (voir `docs/THREAT_MODEL.md`).

## Licence

Apache License 2.0 — voir [`LICENSE`](LICENSE).