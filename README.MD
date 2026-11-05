# llm-gateway

> **Quality-Gated Batch Router** — Routage LLM par cascade, guardrails, budget maîtrisé, résidence des données respectée.

[![CI](https://github.com/<vous>/llm-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/<vous>/llm-gateway/actions/workflows/ci.yml)
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

`llm-gateway` répond à ces cinq besoins avec une thèse simple : **ne payer un modèle cher que lorsque le guardrail prouve qu'un modèle bon marché ne suffit pas**, et router selon des contraintes de souveraineté.

## Principes

1. **Cascade par qualité** — la chaîne de modèles est ordonnée par benchmarks (meilleurs d'abord), les free trials en tête pour être drainés en priorité.
2. **Guardrail en filtre final** — la vérification qualité (NeMo, NoOp) tourne **une fois** sur la première réponse réussie. Un guardrail en échec **termine** la chaîne et la tâche part en revue humaine. Il ne relance pas la cascade.
3. **Benchmarks dynamiques** — les scores de BenchLM / RankLLMs / F5 / RWS peuvent réordonner la chaîne automatiquement (`--rank-by-benchmarks`).
4. **Politique de résidence** — chaque tâche porte une sensibilité (`public`, `internal`, `confidential`) qui filtre les providers autorisés avant toute tentative.
5. **Budget par lot** — un plafond optionnel (`--max-cost-eur`) arrête d'escalader quand il serait dépassé.
6. **Checkpointing** — la sortie JSONL est écrite ligne par ligne avec `fsync`. `--resume` reprend après interruption.
7. **Hardware-aware** — la VRAM est détectée (`nvidia-smi`, `rocm-smi`) et un ratio taille/VRAM est loggé, **sans bloquer** par défaut.

## Installation

```bash
git clone https://github.com/<vous>/llm-gateway.git
cd llm-gateway

# Installation minimale (NoOpGuardrail par défaut)
pip install -e .

# Avec guardrails NeMo
pip install -e ".[guardrails]"

# Avec outils de dev
pip install -e ".[dev]"
```

## Quickstart

### 1. Configuration

```bash
cp config/models.example.yaml config/models.yaml
cp config/policy.example.yaml config/policy.yaml
```

`config/models.yaml` déclare les providers, les modèles, leurs prix et les chaînes par domaine. `config/policy.yaml` déclare les règles de résidence (`confidential → ollama uniquement`, etc.).

### 2. Diagnostic et installation

```bash
# Vérifie que tout est en place (deps, Ollama, modèles locaux)
llm-gateway doctor --config config/models.yaml

# Télécharge les modèles Ollama manquants (interactif)
llm-gateway setup --config config/models.yaml
```

### 3. Lancer un batch

```bash
# Depuis la racine du projet (important pour la résolution des chemins)
llm-gateway batch run \
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
{"id": "t1", "status": "approved", "response": "...", "model_used": "qwen-27bauto", "provider": "ollama", "guardrail_passed": true, "cost_eur": 0.0, "escalations": 0}
```

### 4. Estimer avant de lancer (dry-run)

```bash
llm-gateway batch run --input prompts.jsonl --dry-run --sample 20
```

Extrapole le coût total et le temps d'exécution **sans appeler** les modèles.

### 5. Reprendre après interruption

```bash
llm-gateway batch run --input prompts.jsonl --output results.jsonl --resume
```

Saute les IDs déjà présents dans `results.jsonl`.

### 6. Rafraîchir les benchmarks

```bash
llm-gateway benchmarks refresh
```

Récupère les derniers scores de BenchLM et RankLLMs, écrit le cache avec TTL 24h.

## CLI — Vue d'ensemble

| Commande | Description |
| :--- | :--- |
| `llm-gateway doctor` | Diagnostic de l'environnement |
| `llm-gateway setup` | Installation guidée des modèles manquants |
| `llm-gateway batch run --input ... --output ...` | Lance un batch |
| `--resume` | Reprend un batch interrompu |
| `--dry-run --sample N` | Estime sans appeler |
| `--refresh-benchmarks` | Force le rafraîchissement des scores |
| `--rank-by-benchmarks` | Réordonne les chaînes par benchmarks |
| `--max-cost-eur X` | Budget maximal en euros |
| `--no-classifier` | Désactive la classification automatique |
| `--classifier-model NAME` | Modèle Ollama utilisé pour classifier |
| `llm-gateway intake from-folder` | Convertit un dossier d'images en JSONL |
| `llm-gateway intake from-text` | Convertit un dossier de textes en JSONL |
| `llm-gateway intake from-csv` | Convertit un CSV en JSONL |
| `llm-gateway intake from-urls` | Convertit une liste d'URLs en JSONL |
| `llm-gateway benchmarks refresh` | Force le rafraîchissement du cache |

## Architecture

```
llm-gateway/
├── pyproject.toml
├── README.md · LICENSE · .gitignore
├── benchmarks_cache/           # exemples manuels + caches auto-générés
├── config/
│   ├── models.example.yaml     # providers, modèles, chaînes par domaine
│   └── policy.example.yaml     # politique de résidence
├── src/llm_gateway/
│   ├── providers/              # base, openai_compat, ollama, cloudflare
│   ├── guardrails/             # base, noop, nemo
│   ├── benchmarks/             # base, benchlm, rankllms, f5, rws, cache, aggregator, normalizer
│   ├── router.py               # cascade + guardrail + policy + hardware + budget
│   ├── quota.py                # cooldown temporel (fix bug 429)
│   ├── budget.py               # plafond par lot
│   ├── policy.py               # résidence des données
│   ├── classifier.py           # classification par domaine
│   ├── checkpoint.py           # reprise après interruption
│   ├── hardware.py             # détection VRAM
│   ├── secrets.py              # env ou PowerShell Vault
│   ├── config.py               # validation pydantic
│   ├── doctor.py               # diagnostic environnement
│   ├── installer.py            # téléchargement modèles Ollama
│   ├── intake.py               # convertisseur de données
│   ├── gui.py                  # application graphique unifiée (3 onglets)
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
| `TaskClassifier` | Classification LLM + fallback regex |
| `Checkpoint` | Reprise après interruption |
| `HardwareInfo` | Détection VRAM et fit |
| `SecretBackend` (ABC) | Interface de stockage de secrets |
| `EnvSecretBackend` / `PowerShellVaultBackend` | Implémentations |
| `Doctor` | Diagnostic de l'environnement |
| `Installer` | Téléchargement des modèles Ollama |
| `BatchRunner` | Orchestre le batch complet |

Aucune variable module-level mutable. Chaque instance est injectée explicitement, ce qui rend le code testable et reproductible.

## Application graphique (GUI)

Pour les utilisateurs non techniques, une application graphique unifiée est disponible :

```bash
python -m llm_gateway.gui
```

Trois onglets :

1. **Préparer les données** : sélection d'un dossier d'images, de fichiers texte, d'un CSV ou d'une liste d'URLs, et génération du fichier JSONL de tâches.
2. **Lancer le traitement** : sélection du fichier d'entrée, du fichier de sortie, de la configuration, et lancement du batch avec barre de progression.
3. **Voir les résultats** : affichage du rapport final (tâches approuvées, à revoir, échouées, coût total), liste des tâches à examiner avec possibilité d'accepter ou rejeter chaque cas.

## Tests

```bash
pytest
pytest -v --cov=llm_gateway
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