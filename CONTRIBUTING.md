# Contribuer à gateway-llm

Merci de l'intérêt porté au projet. Ce document décrit comment installer
l'environnement de développement, quel est le style de code attendu, comment
tester, et comment proposer une contribution.

## Code de conduite

Ce projet suit une règle simple : **respect, patience, précision technique**.
Les désaccords sont bienvenus, les attaques personnelles ne le sont pas. Si
un désaccord technique persiste, il se tranche par un test, un benchmark, ou
un consensus mainteneur — pas par la force de frappe argumentative.

## Mise en route

### Prérequis

- Python 3.11 ou supérieur (3.13 recommandé).
- Git.
- Optionnel : Ollama (pour les modèles locaux), PowerShell (pour
  `PowerShellVaultBackend`), ou un binaire `op` (pour 1Password).

### Installation

```bash
git clone https://github.com/Darki0n1/gateway-llm.git
cd gateway-llm

python -m venv .venv
source .venv/bin/activate       # Linux / macOS
# .venv\Scripts\activate        # Windows

pip install -e ".[dev]"
playwright install chromium     # une seule fois, pour le scraping du catalogue
```

L'installation en mode **editable** (`-e`) est obligatoire : elle permet à
`pytest` et à Pylance de résoudre `import gateway_llm` directement depuis
`src/`, sans `sys.path.insert`.

### Vérifier que tout fonctionne

```bash
pytest
ruff check src/ tests/
mypy src/
```

Les trois doivent passer sans erreur avant de commencer à coder.

## Structure du projet

```
src/gateway_llm/        # code du package (layout src/)
tests/                  # tests unitaires (mocks, pas de réseau)
docs/                   # documentation utilisateur et technique
benchmarks_cache/       # caches de benchmarks (f5/rws committés, ollama_library.json gitignored)
scripts/                # scripts de scraping pour la CI
.github/workflows/      # CI, scan de secrets, mise à jour benchmarks
```

Les règles de dépendance entre modules :

- `providers/` ne dépend de rien (sauf `base.py`).
- `router.py` peut importer `providers/`, `guardrails/`, `benchmarks/`,
  `quota.py`, `budget.py`, `policy.py`, `hardware.py`, `config.py`.
- `batch.py` orchestre tout, mais ne doit pas être importé par les autres
  modules.
- `local_selector.py` peut importer `benchmarks/`, `hardware.py`.
- `cli.py` et `gui.py` sont les seuls points d'entrée exécutables.

Aucun module ne doit avoir de **variable au niveau module** mutable. Si vous
avez besoin d'un état partagé, faites une classe avec un `__init__` propre,
injectable.

## Style de code

### Outils

- **ruff** pour le lint et le formatage (`line-length = 100`).
- **mypy** en mode `strict` (voir `pyproject.toml`).
- **type hints obligatoires** sur toutes les signatures publiques (fonctions,
  méthodes, attributs de classe).

### Règles générales

- **Noms en français** pour les docstrings et commentaires de code métier,
  **anglais** pour les identifiants (variables, fonctions, classes).
- **Une classe = une responsabilité.** Si une classe a plus de 200 lignes,
  c'est probablement deux classes.
- **Une fonction = une action.** Si une fonction a plus de 40 lignes, c'est
  probablement deux fonctions.
- **Pas de `print`** dans le code de production. Utilisez
  `logging.getLogger(__name__)`. Seuls `cli.py`, `gui.py` et `batch.py`
  (rapport final) utilisent `print` pour la sortie utilisateur.
- **Pas de `shell=True`.** Toujours `subprocess.run([...])` avec liste
  d'arguments.
- **Pas d'import cloud au niveau module.** `import boto3`, `import azure.*`
  doivent être **dans la méthode** qui les utilise, avec
  `# type: ignore[import-not-found]`.
- **Paramètres inutilisés** : utiliser `*_args: object` (callbacks Tkinter)
  ou préfixer par `_` pour Ruff. Pour Pylance, `*_args` est la seule forme
  qui ne déclenche aucun warning.

### Vérifications avant commit

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/
pytest
```

### Conventional Commits

Format : `<type>(<scope>): <description>`.

Types acceptés : `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`,
`security`.

Exemples :

```
feat(classifier): cascade 3 étages regex → embeddings → LLM
fix(ollama): transmettre les images via le champ `message`
docs(guide): section configuration des secrets
```

## Tests

### Lancer les tests

```bash
pytest                          # tout
pytest tests/test_router.py     # un fichier
pytest -v --cov=gateway_llm     # avec couverture
pytest -k "quota"               # filtrer par nom
```

### Règles

- **Aucun réseau dans les tests.** Mockez systématiquement `requests.get`,
  `requests.post`, `subprocess.run`, `subprocess.Popen`,
  `ensure_ollama_daemon`, etc.
- **Un test = une assertion significative.**
- **Les tests de régression sont critiques.** Si vous corrigez un bug, ajoutez
  un test qui échoue **avant** votre correction et passe **après**.
- **Nommage** : `test_<action>_<condition>_<expected_result>`.

### Tests de sécurité

`test_security.py` couvre :

- Absence de `shell=True` dans les backends de secrets.
- Échappement des apostrophes (PowerShell).
- Absence d'import cloud au niveau module.
- Comportement de `get_backend()` sans configuration.
- Comportement `PowerShellVaultBackend` quand PowerShell est absent (retourne
  `False`, ne lève pas).

**Ne modifiez jamais un test de sécurité pour le faire passer sans corriger le
code sous-jacent.**

## Ajouter une fonctionnalité

### Ajouter un provider LLM

1. Créez `src/gateway_llm/providers/<nom>.py` héritant de `Provider`.
2. Implémentez `complete(model, prompt, max_tokens, temperature, image_b64)`.
3. Levez `RateLimitError` sur 429, `ProviderUnavailableError` sur les autres
   erreurs non récupérables.
4. Ajoutez la classe dans `BatchRunner._build_providers()`.
5. Ajoutez le type au `Literal` dans `ProviderConfig.type` (dans `config.py`).
6. Ajoutez la config par défaut dans `_DEFAULT_CONFIG` (dans `config.py`,
   section `providers` et `models`).
7. Testez dans `tests/test_providers.py` avec `@patch` sur l'appel HTTP.

### Ajouter un backend de secrets

1. Créez une classe héritant de `SecretBackend`.
2. Implémentez `get()`, `is_available()`, et `set()` si le backend supporte
   l'écriture.
3. Importez les dépendances SDK **à l'intérieur** des méthodes, avec
   `# type: ignore[import-not-found]`.
4. Ajoutez la factory dans `_BACKEND_FACTORIES`.
5. Documentez dans `docs/THREAT_MODEL.md` (menace T2 et T14 au minimum).
6. Testez dans `tests/test_security.py`.

### Ajouter une source de benchmarks

1. Créez une classe héritant de `BenchmarkSource`.
2. Implémentez `fetch(category)` et `supports(category)`.
3. Utilisez `normalize_model_name()` pour normaliser les noms.
4. Renseignez `BenchmarkResult.size_gb` et `BenchmarkResult.param_count_b` si
   la source les expose (indispensable pour `local_selector`).
5. Ajoutez l'instance dans `_build_default_benchmarks()` (dans `batch.py`) et
   dans `_build_aggregator()` (dans `cli.py`).
6. Si la source n'a pas d'API et nécessite un scraping, ajoutez un script
   `scripts/refresh_<nom>.py` et intégrez-le au workflow
   `.github/workflows/update-benchmarks.yml`.

### Ajouter un domaine de tâche

1. Ajoutez la catégorie dans `TaskCategory` (dans `benchmarks/base.py`).
2. Ajoutez l'entrée dans `DOMAINS` (dans `classifier.py`), dans le prompt de
   classification LLM (`_classify_llm`) et dans les règles regex
   (`_fallback`).
3. Ajoutez la chaîne dans `_DEFAULT_CONFIG["domains"]` (dans `config.py`).
4. Ajoutez des utterances d'exemple dans `DOMAIN_UTTERANCES`
   (`semantic_router.py`) pour que les embeddings puissent reconnaître le
   domaine.
5. Si nécessaire, ajoutez le mapping dans `_BENCHLM_CATEGORY` ou
   `_RANKLLMS_CATEGORY`.
6. Testez la détection dans `tests/test_classifier.py`.

### Ajouter une étape à la cascade de classification

La cascade actuelle est : regex → embeddings → LLM. Si vous ajoutez une étape :

1. Respectez les seuils (`HIGH_CONFIDENCE`, `LOW_CONFIDENCE`, `AMBIGUITY_GAP`).
2. Renseignez `ClassificationResult.decision_layer` pour tracer la décision.
3. Renseignez `ClassificationResult.confidence` quand applicable.
4. Testez chaque zone (haute confiance, zone grise, bas score).

## Documentation

- Toute nouvelle fonctionnalité publique doit être documentée dans
  `README.md`.
- Toute nouvelle menace ou surface d'attaque doit être ajoutée à
  `docs/THREAT_MODEL.md` avec un numéro T<n> séquentiel.
- Les changements notables doivent être ajoutés à `CHANGELOG.md` sous
  `[Unreleased]`.
- Les guides utilisateur (`docs/GUIDE_FR.md`, `docs/GUIDE_EN.md`) doivent
  rester **non techniques**.

## Sécurité

### Ne jamais committer de secret

- Pas de `.env`, pas de `models.yaml` avec des clés, pas de
  `~/.gateway-llm/secrets.yaml`.
- Si vous voyez un secret dans une PR, signalez-le immédiatement en commentaire
  et n'approuvez pas la PR.

### Avant chaque push

```bash
gitleaks detect --source . --no-git --verbose
```

Si vous voulez scanner tout l'historique :

```bash
gitleaks detect --source . --verbose --redact
```

La CI exécute gitleaks automatiquement chaque lundi et sur chaque PR.

### Signaler une vulnérabilité

Pour les vulnérabilités de sécurité, **n'ouvrez pas d'issue publique**.
Contactez le mainteneur par email privé (voir `pyproject.toml`, champ
`authors[].email`). Vous recevrez une réponse sous 72h.

## Pull requests

### Avant d'ouvrir

1. Votre branche part de `main` à jour.
2. `pytest`, `ruff check`, `mypy` passent localement.
3. Vous avez ajouté des tests pour votre changement (ou justifié pourquoi ce
   n'est pas nécessaire).
4. Vous avez mis à jour `CHANGELOG.md`.
5. Vous avez mis à jour la documentation si pertinent.

### Description de PR

Utilisez ce template :

```markdown
## Résumé

Description en 2-3 phrases de ce que fait la PR.

## Type de changement

- [ ] Bug fix (non-breaking)
- [ ] Nouvelle fonctionnalité (non-breaking)
- [ ] Breaking change (impact utilisateurs)
- [ ] Documentation
- [ ] Refactorisation
- [ ] Sécurité

## Motivation

Pourquoi ce changement est nécessaire. Lien vers une issue si applicable.

## Tests

Comment vous avez testé (tests unitaires ajoutés, tests manuels, etc.).

## Checklist

- [ ] `pytest` passe
- [ ] `ruff check` passe
- [ ] `mypy` passe
- [ ] `CHANGELOG.md` mis à jour
- [ ] Documentation mise à jour si pertinent
```

### Revue

Une PR est fusionnable quand :

- La CI est verte (tests + lint + type + sécurité).
- Au moins un mainteneur a approuvé.
- Les commentaires de revue ont été adressés (ou explicitement ignorés avec
  justification).

Les débats techniques se règlent par des arguments ou des benchmarks, pas par
l'insistance.

## Licence

En contribuant, vous acceptez que votre code soit distribué sous
[Apache License 2.0](LICENSE). Vous conservez votre copyright sur les
contributions que vous produisez, mais vous accordez une licence perpétuelle,
mondiale, non exclusive et gratuite au projet et à ses utilisateurs.

## Questions

- Pour les questions d'utilisation : ouvrez une **issue** avec le label
  `question`.
- Pour les bugs : ouvrez une **issue** avec le label `bug` et un exemple
  reproductible.
- Pour les fonctionnalités : ouvrez une **issue** avec le label `enhancement`
  avant de coder, pour valider la direction.