# Contributing to gateway-llm

Merci de l'intérêt porté au projet ! Ce document décrit comment contribuer efficacement, en respectant les conventions et la sécurité.

## Table des matières

- [Code de conduite](#code-de-conduite)
- [Mise en place de l'environnement](#mise-en-place-de-lenvironnement)
- [Workflow de contribution](#workflow-de-contribution)
- [Style de code](#style-de-code)
- [Tests](#tests)
- [Ajouter un provider](#ajouter-un-provider)
- [Ajouter un guardrail](#ajouter-un-guardrail)
- [Ajouter une source de benchmarks](#ajouter-une-source-de-benchmarks)
- [Ajouter un domaine](#ajouter-un-domaine)
- [Sécurité — ne jamais committer de secrets](#sécurité--ne-jamais-committer-de-secrets)
- [Architecture Decision Records (ADR)](#architecture-decision-records-adr)
- [Signaler un bug / proposer une fonctionnalité](#signaler-un-bug--proposer-une-fonctionnalité)

## Code de conduite

Ce projet suit le [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). En participant, vous vous engagez à respecter ce code. Les comportements inacceptables peuvent être signalés à `dennieau.amandine@proton.me`.

## Mise en place de l'environnement

Prérequis : Python ≥ 3.11, Git, Ollama (optionnel mais recommandé pour les tests locaux).

```bash
git clone https://github.com/darki0n1/gateway-llm.git
cd gateway-llm
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

Vérifier que tout est en place :

```bash
gateway-llm doctor
pytest
ruff check src/ tests/ scripts/
mypy src/ scripts/
```

## Workflow de contribution

1. **Ouvrir une issue** avant de coder (bug, feature, refactor). Décrire le contexte, le comportement attendu, et — si pertinent — une piste d'implémentation.
2. **Forker** et créer une branche depuis `main` : `git checkout -b feat/mon-sujet` (ou `fix/…`, `docs/…`, `refactor/…`, `chore/…`).
3. **Coder** en respectant le style et en ajoutant des tests.
4. **Vérifier localement** :

```bash
ruff check src/ tests/ scripts/
ruff format src/ tests/ scripts/
mypy src/ scripts/
pytest
```

5. **Commiter** en suivant [Conventional Commits](https://www.conventionalcommits.org/) :
   - `feat: add vllm provider`
   - `fix: quota cooldown not reset after 429`
   - `docs: update threat model T16–T20`
   - `test: add golden set for fact_checking`
   - `refactor: extract router filters into functions`
   - `chore: bump deps`
6. **Pousser** et ouvrir une Pull Request vers `main`. Décrire le changement, cocher la checklist, lier l'issue (`Closes #42`).
7. **Attendre la review**. La CI doit être verte (`test`, `lint`, `typecheck`, `security`, `gitleaks`).

### Checklist PR

- [ ] Tests ajoutés ou mis à jour
- [ ] `ruff check` + `ruff format --check` passent
- [ ] `mypy` passe
- [ ] `pytest --cov-fail-under=60` passe
- [ ] Aucun secret committé (`gitleaks detect` propre)
- [ ] Documentation mise à jour si comportement public modifié
- [ ] `CHANGELOG.md` mis à jour sous `[Unreleased]`
- [ ] Si nouvelle décision architecturale : ADR ajouté (`docs/adr/`)

## Style de code

- **Ruff** (config dans `pyproject.toml`) : `E`, `F`, `I`, `B`, `UP`, `S`, `SIM`, `RUF`. Line length 100.
- **Mypy strict-ish** : `check_untyped_defs = true`, `warn_return_any = true`. Pas de `# type: ignore` sans commentaire justificatif.
- **Docstrings** : une ligne pour les fonctions publiques, plus si la logique est non triviale. En français ou en anglais, cohérent au sein d'un fichier.
- **Nommage** : `snake_case` (fonctions, variables), `PascalCase` (classes), `SCREAMING_SNAKE_CASE` (constantes).
- **Imports** : stdlib, puis third-party, puis `gateway_llm.*` (ruff `I` s'en occupe).
- **Pas de dépendances nouvelles** sans discussion préalable dans une issue. Vérifier la licence (Apache 2.0 compatible) et l'activité du projet.
- **Pas de `print()`** dans le code bibliothèque. Le CLI peut utiliser `print()` à la rigueur, jamais `logging` interdit.
- **Pas de logique réseau dans les tests unitaires** : mocker via `unittest.mock` ou `responses`. Les tests de bout en bout (avec providers réels) sont dans `tests/e2e/` et skippés par défaut.

## Tests

- **Structure** : `tests/` à la racine, miroir de `src/gateway_llm/`.
- **Framework** : `pytest` + `pytest-cov`. Pas de `unittest.TestCase` (sauf besoin de mocker des méthodes spéciales).
- **Nommage** : `test_<module>_<comportement>` (ex. `test_router_policy_blocks_cloud_for_confidential`).
- **Fixtures** : préférer les fixtures `pytest` aux `setUp`/`tearDown`. Les fixtures partagées dans `conftest.py`.
- **Mocks** : `Mock()` d'`unittest.mock` pour les providers et `requests` (`responses` ou `monkeypatch`).
- **Couverture** : seuil CI 60%. Toute nouvelle branche logique (if/else significatif) doit être testée.

Exemple minimal :

```python
def test_policy_blocks_cloud_for_confidential():
    policy = PolicyConfig(residency={
        "confidential": {"allowed_providers": ["ollama"]},
    })
    assert policy.is_allowed("ollama", "confidential") is True
    assert policy.is_allowed("groq", "confidential") is False
```

## Ajouter un provider

1. Créer `src/gateway_llm/providers/mon_provider.py` qui hérite de `Provider` (dans `providers/base.py`).
2. Implémenter `complete(model, prompt, max_tokens, temperature, image_b64)`.
3. Lever les bonnes exceptions : `RateLimitError` (429), `ProviderUnavailableError` (5xx, timeout, réponse malformée), `ProviderError` (autres).
4. Ajouter le `type` dans `ProviderConfig` (`config.py`).
5. Ajouter la factory dans `BatchRunner._build_providers()`.
6. Ajouter un test `tests/test_providers_mon.py` (mock `requests`).
7. Documenter dans `README.md` (section « Backends ») et `CHANGELOG.md`.

## Ajouter un guardrail

1. Créer `src/gateway_llm/guardrails/mon_guardrail.py` qui hérite de `Guardrail` (`guardrails/base.py`).
2. Implémenter `check(task_text, response) -> GuardrailResult`. **Ne jamais lever d'exception** : fail-open (`is_valid=True`) en cas d'erreur, logger un `warning`.
3. Documenter la dépendance optionnelle dans `pyproject.toml` `[optional-dependencies]` si besoin.
4. Ajouter un test avec et sans la dépendance (mock `ImportError`).
5. Documenter dans `README.md` (section « Guardrails ») et `CHANGELOG.md`.

## Ajouter une source de benchmarks

1. Créer `src/gateway_llm/benchmarks/mon_benchmark.py` qui hérite de `BenchmarkSource` (`benchmarks/base.py`).
2. Implémenter `fetch(category) -> list[BenchmarkResult]` et `supports(category) -> bool`.
3. Normaliser les noms via `normalize_model_name()` (`benchmarks/normalizer.py`).
4. Si la source n'a pas d'API JSON : fournir un script de scraping dans `scripts/refresh_mon_benchmark.py` + cache JSON dans `benchmarks_cache/mon_benchmark.json`.
5. Si scraping : **jamais en runtime**, toujours via GitHub Actions planifié ou script manuel. Documenter dans `docs/THREAT_MODEL.md` (menace T11/T12 par analogie).
6. Ajouter l'adaptateur dans `BatchRunner._build_default_benchmarks()`.
7. Ajouter un test avec un cache JSON factice.
8. Documenter dans `README.md` (section « Benchmarks ») et `CHANGELOG.md`.

## Ajouter un domaine

1. Ajouter la valeur dans `TaskCategory` (`benchmarks/base.py`) et `DOMAINS` (`classifier.py`).
2. Ajouter le domaine dans `_DEFAULT_CONFIG` (`config.py`) avec sa chaîne de modèles.
3. Ajouter les utterances dans `SemanticRouter.DOMAIN_UTTERANCES` (`semantic_router.py`).
4. Ajouter les règles regex dans `TaskClassifier._fallback` (`classifier.py`) si pertinent.
5. Ajouter le mapping dans l'adaptateur benchmark qui supporte la catégorie.
6. **Mettre à jour `docs/THREAT_MODEL.md`** : la revue de sécurité est obligatoire à chaque ajout de domaine (ex. `multimodal_extraction` a introduit T15).
7. Ajouter des tests de classification sur des phrases représentatives.
8. Documenter dans `README.md` et `CHANGELOG.md`.

## Sécurité — ne jamais committer de secrets

- **Jamais** de clé API dans le code, les tests, les configs, les logs.
- Utiliser `gateway-llm setup-secrets` pour choisir un backend (PowerShell Vault, 1Password, HashiCorp, AWS, Azure). Jamais `.env` en usage quotidien.
- Le fichier `~/.gateway-llm/secrets.yaml` ne contient **jamais** de secret final — seulement le nom du backend et ses options de connexion.
- Avant chaque push : `gitleaks detect --source .` (ou installer le pre-commit hook).
- Si un secret est commité par erreur : **révoquer immédiatement** la clé chez le provider, puis réécrire l'historique (`git filter-repo`). Ne pas se contenter d'un nouveau commit.
- Lire `docs/THREAT_MODEL.md` avant toute modification touchant `secrets.py`, `router.py`, `intake.py`, `batch.py`, `gui.py`.

## Architecture Decision Records (ADR)

Toute décision architecturale non triviale doit être documentée dans `docs/adr/`, au format [MADR](https://adr.github.io/madr/) :

```
docs/adr/
├── 0001-cascade-router.md
├── 0002-guardrail-filtre-final.md
├── 0003-secrets-explicites.md
└── ...
```

Structure minimale :

```markdown
# ADR-0001 : Cascade router avec guardrail en filtre final

## Statut
Accepté (2026-06-01)

## Contexte
...

## Décision
...

## Conséquences
- Positives : ...
- Négatives : ...
```

## Signaler un bug / proposer une fonctionnalité

- **Bug** : ouvrir une issue avec le template `bug_report`. Inclure version (`gateway-llm --version`), OS, Python, sortie de `gateway-llm doctor`, extrait de log (`INFO`), et étapes de reproduction.
- **Feature** : ouvrir une issue avec le template `feature_request`. Décrire le cas d'usage, la valeur ajoutée, et — si possible — une piste d'implémentation.
- **Question** : utiliser les Discussions GitHub.

## Licence

En contribuant, vous acceptez que vos contributions soient placées sous licence Apache 2.0 (voir `LICENSE.txt`). Le projet n'a pas de CLA : l'acceptation de la PR vaut acceptation de la licence.