# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format s'appuie sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Planned (0.3.0 — service & observabilité)
- **FastAPI** : `BatchRunner` exposé en service HTTP (`/health`, `/route`, `/batch`, `/metrics`).
- **Provider `vllm`** (OpenAI-compatible) + modèle 7B/8B AWQ, gain x5–x10 vs Ollama.
- **Prometheus / Grafana** : métriques `gateway_llm_calls_total`, `gateway_llm_cost_eur`, `gateway_llm_latency_seconds`.
- **Docker Compose** : API + vLLM + Prometheus + Grafana + Qdrant + Langfuse.
- **Golden set & RAGAS CI** : régression qualité dans la CI.
- **Observabilité Langfuse** : tracing de chaque `provider.complete()`.

### Planned (0.4.0 — production-grade)
- **Shadow mode / rollout** : comparaison A/B sans impact utilisateur, canary progressif.
- **RAG end-to-end** : chunking, hybrid search (BM25 + dense), reranker.
- **MCP server** : gateway exposée comme outil pour Claude Desktop / Cursor.
- **OAuth 2.1 + webhooks signés** : auth utilisateur et notifications HMAC-SHA256.

## [0.2.0] — 2026-11-07

### Added
- **Domain `multimodal_extraction`** : traitement des images (screenshots, graphiques, tableaux) via `gemma-4-31b-it` (cloud) ou `qwen2.5vl:7b-q4_K_M` (local Ollama). Nouvelle entrée `image_path` / `image_b64` dans le JSONL d'entrée.
- **4 modes d'exécution** (`LocalMode`) : `CLOUD_ONLY`, `LOCAL_ONLY`, `HYBRID`, `DEFAULT`. Persistés dans `~/.gateway-llm/config.yaml`. Contraignent le routage au niveau providers.
- **`local_selector`** : sélection dynamique des modèles Ollama à installer en croisant benchmarks × hardware (VRAM + RAM + disque). Aucune liste en dur.
- **`intake_mixed`** : combine images, textes et CSV en une seule session.
- **`intake_from_csv_multi`** : fusion multi-CSV en un seul JSONL, avec préfixe des IDs.
- **`intake_from_csv`** : lit **tout le tableau** (toutes les colonnes), plus de sélection de colonne unique. `max_rows=500`, `max_chars=30_000`.
- **`_DEFAULT_CONFIG`** embarquée dans `config.py` : aucun fichier YAML requis pour démarrer.
- **`_DEFAULT_POLICY`** embarquée : `public → [cloud…]`, `internal → [mistral, ollama]`, `confidential → [ollama]`.
- **`Doctor`** : diagnostic complet (deps Python, binaire Ollama, daemon, modèles, stockage secrets).
- **`Installer.ensure_ollama_daemon`** : démarrage automatique du daemon Ollama en subprocess (sans shell).
- **`SemanticRouter`** : embeddings `nomic-embed-text` via Ollama, cosine similarity sur utterances par domaine.
- **`TaskClassifier`** : cascade 3 étages (regex → embeddings → LLM) avec seuils calibrés (`HIGH=0.82`, `LOW=0.60`, `GAP=0.10`) et champs `confidence` / `decision_layer` pour l'audit.
- **`py.typed`** (PEP 561) : marqueur pour distribution typée.
- **Dependabot** : mises à jour hebdomadaires pip + GitHub Actions.
- **`.github/workflows/ci.yml`** : `--cov-fail-under=60`, `types-requests`, vérification `py.typed`.
- **Threat model T1–T20** : documentation des 20 menaces et leurs mitigations (`docs/THREAT_MODEL.md`).
- **GUIDE FR/EN** : documentation utilisateur non technique pour la GUI.

### Changed
- `README.md` mis à jour (roadmap 0.3.0 / 0.4.0, threat model T1–T20, architecture `py.typed`).
- `pyproject.toml` : version `0.2.0`, ajout `types-requests` dans `[dev]`.
- `src/gateway_llm/__init__.py` : `__version__ = "0.2.0"`.
- `models.yaml` / `models.example.yaml` : ajout du domaine `multimodal_extraction`, clés Ollama alignées sur les vrais tags (`qwen3.6:27b-q4_K_M`).
- `policy.example.yaml` : providers alignés sur la config par défaut.

### Security
- **T1–T20** documentés, avec tests `test_vault_no_shell_true` sur chaque backend.
- **CI** : `bandit -r src/ -c pyproject.toml`, `pip-audit --strict`, `gitleaks` hebdomadaire.
- **Secrets** : 6 backends interchangeables, aucun fallback silencieux.
- **`intake_from_csv`** : bornage strict (`max_rows=500`, `max_chars=30_000`) contre le Denial of Wallet.

## [0.1.0] — 2026-06-01

### Added
- Version initiale.
- **Cascade router** : `Router`, `QuotaManager`, `BudgetTracker`, `PolicyConfig`.
- **Providers** : `OpenAICompatibleProvider`, `OllamaProvider`, `CloudflareProvider`.
- **Guardrails** : `NoOpGuardrail`, `NemoGuardrail` (optionnel).
- **Benchmarks** : `BenchLMAdapter`, `RankLLMsAdapter`, `F5SafetyAdapter`, `RWSTranslationAdapter`, `BenchmarkCache` (TTL 24h), `BenchmarkAggregator`.
- **Secrets** : `PowerShellVaultBackend`, `OnePasswordBackend`, `HashiCorpVaultBackend`, `AWSSecretsManagerBackend`, `AzureKeyVaultBackend`, `EnvSecretBackend`.
- **Intake** : `intake_from_folder`, `intake_from_text`, `intake_from_csv`, `intake_from_urls`.
- **Orchestrateur** : `BatchRunner` avec checkpoint (`--resume`), dry-run (`--dry-run --sample N`), budget (`--max-cost-eur`).
- **CLI** : `gateway-llm` (argparse) — `doctor`, `setup`, `setup-secrets`, `intake`, `benchmarks`, `batch`.
- **GUI** : 4 onglets (Configuration / Préparer / Lancer / Voir les résultats), drag & drop, rendu Markdown, auto-refresh 2s.
- **Scripts** : `refresh_f5.py`, `refresh_rws.py`, `refresh_ollama_library.py` (Playwright + BS4 + fallback API).
- **CI** : `pytest`, `ruff`, `mypy`, `bandit`, `pip-audit`.
- **Docs** : `README.md`, `docs/THREAT_MODEL.md` (T1–T15), `docs/GUIDE_FR.md`, `docs/GUIDE_EN.md`.

[Unreleased]: https://github.com/darki0n1/gateway-llm/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/darki0n1/gateway-llm/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/darki0n1/gateway-llm/releases/tag/v0.1.0