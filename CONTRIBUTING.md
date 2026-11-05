# Contribuer à llm-gateway

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
git clone https://github.com/<vous>/llm-gateway.git
cd llm-gateway

python -m venv .venv
source .venv/bin/activate       # Linux / macOS
# .venv\Scripts\activate        # Windows

pip install -e ".[dev]"
```

L'installation en mode **editable** (`-e`) est obligatoire : elle permet à
`pytest` et à Pylance de résoudre `import llm_gateway` directement depuis
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
src/llm_gateway/        # code du package (layout src/)
tests/                  # tests unitaires (mocks, pas de réseau)
docs/                   # documentation utilisateur et technique
config/                 # exemples de configuration (YAML)
benchmarks_cache/       # caches de benchmarks
.github/workflows/      # CI, scan de secrets, mise à jour benchmarks
```

Les règles de dépendance entre modules :

- `providers/` ne dépend de rien (sauf `base.py`).
- `router.py` peut importer `providers/`, `guardrails/`, `benchmarks/`,
  `quota.py`, `budget.py`, `policy.py`, `hardware.py`, `config.py`.
- `batch.py` orchestre tout, mais ne doit pas être importé par les autres
  modules.
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
  **anglais** pour les identifiants (variables, fonctions, classes). Cette
  règle reflète le projet existant.
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
  `# type: ignore[import-not-found]`. Sinon, `import llm_gateway.secrets`
  casse pour tous les utilisateurs qui n'ont pas installé ces extras.

### Vérifications avant commit

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/
pytest
```

### Conventional Commits

Les messages de commit suivent [Conventional Commits](https://www.conventionalcommits.org/).
Format : `<type>(<scope>): <description>`.

Types acceptés :
- `feat` : nouvelle fonctionnalité
- `fix` : correction de bug
- `docs` : documentation seule
- `style` : formatage (sans changement sémantique)
- `refactor` : refactorisation (sans changement de comportement)
- `test` : ajout ou modification de tests
- `chore` : tâches diverses (CI, dépendances, etc.)
- `security` : correction de sécurité

Exemples :
```
feat(router): support multimodal via image_b64
fix(quota): cooldown basé sur time.monotonic au lieu de compteur cumulatif
docs(guide): section configuration des secrets
```

## Tests

### Lancer les tests

```bash
pytest                          # tout
pytest tests/test_router.py     # un fichier
pytest -v --cov=llm_gateway     # avec couverture
pytest -k "quota"               # filtrer par nom
```

### Règles

- **Aucun réseau dans les tests.** Mockez systématiquement `requests.get`,
  `requests.post`, `subprocess.run`, etc.
- **Un test = une assertion significative.** Évitez les tests qui vérifient
  cinq choses à la fois.
- **Les tests de régression sont critiques.** Si vous corrigez un bug,
  ajoutez un test qui échoue **avant** votre correction et passe **après**.
  Exemple : `test_no_azure_import_at_module_level` protège contre la
  réintroduction d'un import au niveau module.
- **Nommage** : `test_<action>_<condition>_<expected_result>`. Exemple :
  `test_router_escalates_on_rate_limit`.

### Tests de sécurité

Les tests `test_security.py` couvrent :

- Absence de `shell=True` dans les backends de secrets.
- Échappement des apostrophes (PowerShell).
- Absence d'import cloud au niveau module.
- Comportement de `get_backend()` sans configuration.

**Ne modifiez jamais un test de sécurité pour le faire passer sans corriger le
code sous-jacent.** Si un test de sécurité échoue, c'est que la sécurité est
cassée.

## Ajouter une fonctionnalité

### Ajouter un provider LLM

1. Créez `src/llm_gateway/providers/<nom>.py` héritant de `Provider`.
2. Implémentez `complete(model, prompt, max_tokens, temperature, image_b64)`.
3. Levez `RateLimitError` sur 429, `ProviderUnavailableError` sur les autres
   erreurs non récupérables.
4. Ajoutez la classe dans `BatchRunner._build_providers()`.
5. Ajoutez le type au `Literal` dans `ProviderConfig.type` (dans `config.py`).
6. Ajoutez un exemple dans `config/models.example.yaml`.
7. Testez dans `tests/test_providers.py` avec `@patch` sur l'appel HTTP.

### Ajouter un backend de secrets

1. Créez une classe héritant de `SecretBackend`.
2. Implémentez `get()`, `is_available()`, et `set()` si le backend supporte
   l'écriture.
3. Importez les dépendances SDK **à l'intérieur** des méthodes, avec
   `# type: ignore[import-not-found]`.
4. Ajoutez la factory dans `_BACKEND_FACTORIES` et le mapping dans
   `_BACKEND_REQUIREMENTS`.
5. Documentez dans `docs/THREAT_MODEL.md` (menace T2 et T14 au minimum).
6. Testez dans `tests/test_security.py` (au moins : `is_available()` avec SDK
   absent, `get()` avec SDK absent).

### Ajouter une source de benchmarks

1. Créez une classe héritant de `BenchmarkSource`.
2. Implémentez `fetch(category)` et `supports(category)`.
3. Utilisez `normalize_model_name()` pour normaliser les noms.
4. Ajoutez l'instance dans `_build_aggregator()` (dans `cli.py`) et dans
   `_maybe_refresh_benchmarks()` (dans `batch.py`).
5. Si la source n'a pas d'API et nécessite un scraping, ajoutez un script
   `scripts/refresh_<nom>.py` et intégrez-le au workflow
   `.github/workflows/update-benchmarks.yml`.

### Ajouter un domaine de tâche

1. Ajoutez la catégorie dans `TaskCategory` (dans `benchmarks/base.py`).
2. Ajoutez l'entrée dans `DOMAINS` (dans `classifier.py`) et dans le prompt
   de classification.
3. Ajoutez la chaîne dans `config/models.example.yaml` (section `domains`).
4. Si nécessaire, ajoutez le mapping dans `_BENCHLM_CATEGORY` ou
   `_RANKLLMS_CATEGORY`.
5. Testez la détection dans `tests/test_classifier.py`.

## Documentation

- Toute nouvelle fonctionnalité publique doit être documentée dans
  `README.md` (section CLI ou Architecture).
- Toute nouvelle menace ou surface d'attaque doit être ajoutée à
  `docs/THREAT_MODEL.md` avec un numéro T<n> séquentiel.
- Les changements notables doivent être ajoutés à `CHANGELOG.md` sous
  `[Unreleased]`.
- Les guides utilisateur (`docs/GUIDE_FR.md`, `docs/GUIDE_EN.md`) doivent
  rester **non techniques**. Si vous ajoutez une fonctionnalité GUI, mettez à
  jour les deux versions.

## Sécurité

### Ne jamais committer de secret

- Pas de `.env`, pas de `config/models.yaml` avec des clés, pas de
  `~/.llm-gateway/secrets.yaml`.
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