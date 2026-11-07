# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Point d'entrée CLI de gateway-llm."""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys

from gateway_llm import __version__
from gateway_llm.benchmarks.aggregator import BenchmarkAggregator
from gateway_llm.benchmarks.base import TaskCategory
from gateway_llm.benchmarks.benchlm import BenchLMAdapter
from gateway_llm.benchmarks.f5_safety import F5SafetyAdapter
from gateway_llm.benchmarks.rankllms import RankLLMsAdapter
from gateway_llm.benchmarks.rws_translation import RWSTranslationAdapter
from gateway_llm.classifier import TaskClassifier
from gateway_llm.config import load_config, load_policy
from gateway_llm.doctor import Doctor
from gateway_llm.hardware import detect_vram
from gateway_llm.installer import Installer
from gateway_llm.logging import configure as configure_logging

log = logging.getLogger("gateway_llm.cli")


# ─── Helpers ────────────────────────────────────────────────────
def _build_aggregator(force: bool) -> BenchmarkAggregator:
    sources = [
        BenchLMAdapter(),
        RankLLMsAdapter(),
        F5SafetyAdapter(),
        RWSTranslationAdapter(),
    ]
    return BenchmarkAggregator(sources, force_refresh=force)


def _get_required_ollama_models(config_path: str | None) -> list[str]:
    """Lit la config (fichier ou intégrée) et extrait les modèles Ollama requis."""
    try:
        cfg = load_config(config_path)  # gère None → config intégrée
    except Exception as e:
        log.debug("Impossible de lire %s : %s", config_path, e)
        return []
    result = []
    for key, model_cfg in cfg.models.items():
        provider = cfg.providers[model_cfg.provider]
        if provider.type == "ollama":
            result.append(model_cfg.model_name or key)
    return result


def _run_preflight(
    config_path: str | None,
    auto_install: bool,
    assume_yes: bool,
) -> bool:
    """Retourne True si on peut continuer, False si erreur critique."""
    required_models = _get_required_ollama_models(config_path)
    doctor = Doctor(required_models=required_models)
    print("\n🔍 Pre-flight check :")
    report = doctor.run()
    report.print_report()

    if report.has_errors:
        print("\n❌ Erreurs critiques. Corriger avant de continuer.")
        return False

    if report.missing_models and auto_install:
        print()
        installer = Installer(interactive=not assume_yes, assume_yes=assume_yes)
        n = installer.ensure_models(report.missing_models)
        if n:
            print(f"✅ {n} modèle(s) installé(s)")
        else:
            print("⚠️  Aucun modèle installé (cloud-only ou modèles absents).")

    return True


# ─── Commandes ──────────────────────────────────────────────────
def cmd_doctor(args: argparse.Namespace) -> int:
    configure_logging(level="INFO")
    required = _get_required_ollama_models(args.config)
    doctor = Doctor(required_models=required)
    print("\n=== DIAGNOSTIC ===")
    report = doctor.run()
    report.print_report()
    print()
    if report.has_errors:
        print("Statut : ERREURS CRITIQUES")
        return 1
    if report.has_warnings:
        print("Statut : AVERTISSEMENTS (le système peut fonctionner partiellement)")
        return 0
    print("Statut : TOUT EST OK")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    configure_logging(level="INFO")
    required = _get_required_ollama_models(args.config)
    if not required:
        print("ℹ️  Aucun modèle Ollama déclaré dans la config. Rien à installer.")
        return 0

    doctor = Doctor(required_models=required)
    print("\n=== SETUP ===")
    report = doctor.run()
    report.print_report()

    if report.has_errors:
        print("\n❌ Erreurs critiques, arrêt.")
        return 1
    if not report.missing_models:
        print("\n✅ Tous les modèles sont déjà installés.")
        return 0

    print()
    installer = Installer(interactive=not args.yes, assume_yes=args.yes)
    n = installer.ensure_models(report.missing_models)
    print(f"\n✅ {n} modèle(s) installé(s) sur {len(report.missing_models)}.")
    return 0


def cmd_setup_secrets(args: argparse.Namespace) -> int:
    from gateway_llm.secrets import get_backend, save_backend_config

    print("\n=== Configuration des secrets ===\n")
    print("Sur quelle machine travaillez-vous ?")
    print("  1) Machine personnelle (Windows / Mac / Linux)")
    print("  2) Machine d'entreprise (Windows / Mac / Linux)")
    print("  3) Cloud (AWS, Azure)")
    print("  4) CI/CD (variables d'environnement)")

    choice = input("\nVotre choix [1-4] : ").strip()

    if choice == "1":
        print("\nCoffres disponibles :")
        print("  a) PowerShell Vault (Windows, recommandé)")
        print("  b) 1Password CLI (Mac / Linux / Windows)")
        sub = input("Choix [a-b] : ").strip().lower()

        if sub == "a":
            backend = "powershell_vault"
            options = {}
            print("\nInstructions PowerShell (à lancer une fois dans un terminal) :")
            print("  Install-Module Microsoft.PowerShell.SecretManagement -Scope CurrentUser")
            print("  Install-Module Microsoft.PowerShell.SecretStore -Scope CurrentUser")
            print(
                "  Register-SecretVault -Name LocalVault "
                "-ModuleName Microsoft.PowerShell.SecretStore -DefaultVault"
            )
        elif sub == "b":
            backend = "1password"
            vault = input("Nom du vault 1Password (défaut: Private) : ").strip() or "Private"
            options = {"vault": vault}
        else:
            print("❌ Choix invalide.")
            return 1

    elif choice == "2":
        print("\nCoffres entreprise :")
        print("  a) HashiCorp Vault")
        print("  b) AWS Secrets Manager")
        print("  c) Azure Key Vault")
        sub = input("Choix [a-c] : ").strip().lower()

        if sub == "a":
            backend = "hashicorp_vault"
            options = {
                "url": input("URL Vault : ").strip(),
                "token": input("Token Vault : ").strip(),
                "mount": input("Mount (défaut: secret) : ").strip() or "secret",
            }
        elif sub == "b":
            backend = "aws_secrets_manager"
            options = {
                "region": input("Région AWS (défaut: us-east-1) : ").strip() or "us-east-1",
                "prefix": input("Préfixe (défaut: gateway-llm/) : ").strip() or "gateway-llm/",
            }
        elif sub == "c":
            backend = "azure_key_vault"
            options = {"vault_url": input("URL du Key Vault : ").strip()}
        else:
            print("❌ Choix invalide.")
            return 1

    elif choice == "3":
        print("\nCoffres cloud :")
        print("  a) AWS Secrets Manager")
        print("  b) Azure Key Vault")
        sub = input("Choix [a-b] : ").strip().lower()

        if sub == "a":
            backend = "aws_secrets_manager"
            options = {
                "region": input("Région AWS (défaut: us-east-1) : ").strip() or "us-east-1",
                "prefix": input("Préfixe (défaut: gateway-llm/) : ").strip() or "gateway-llm/",
            }
        elif sub == "b":
            backend = "azure_key_vault"
            options = {"vault_url": input("URL du Key Vault : ").strip()}
        else:
            print("❌ Choix invalide.")
            return 1

    elif choice == "4":
        print(
            "\n⚠️  Variables d'environnement : les clés seront lues depuis "
            "des variables définies dans le shell ou par la plateforme CI.\n"
            "    Ce mode est déconseillé pour un usage quotidien "
            "(variables visibles par les autres processus du même utilisateur).\n"
            "    Recommandé uniquement pour CI/CD (GitHub Actions, GitLab, etc.)."
        )
        cont = input("Continuer ? [y/N] : ").strip().lower()
        if cont not in ("y", "yes"):
            print("Abandon.")
            return 0
        backend = "env"
        options = {}

    else:
        print("❌ Choix invalide.")
        return 1

    save_backend_config(backend, options)

    # Test immédiat
    print("\nTest du backend…")
    try:
        b = get_backend()
        if b.is_available():
            print(f"✅ Backend '{b.name}' opérationnel.")
        else:
            print(
                f"⚠️  Backend '{b.name}' enregistré mais non disponible.\n"
                f"    Causes possibles : credentials invalides, réseau, "
                f"ou URL mal configurée."
            )
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return 1

    # Saisie des clés API (sauf backend env, où les clés sont déjà dans le shell)
    if backend != "env":
        print("\nSaisie des clés API (laisser vide pour ignorer) :")
        for key in [
            "GROQ_API_KEY",
            "MISTRAL_API_KEY",
            "OPENROUTER_API_KEY",
            "GOOGLE_API_KEY",
            "NVIDIA_API_KEY",
            "CLOUDFLARE_API_KEY",
            "CLOUDFLARE_ACCOUNT_ID",
        ]:
            val = input(f"  {key} : ").strip()
            if not val:
                continue
            if b.set(key, val):
                print(f"    ✓ {key} enregistrée")
            else:
                print(f"    ⚠️  Échec écriture {key}")
    else:
        print(
            "\n💡 Rappel : exportez vos clés dans le shell avant de lancer "
            "le batch :\n"
            "    export GROQ_API_KEY=gsk_xxx\n"
            "    export MISTRAL_API_KEY=xxx\n"
            "    (ou définissez-les dans votre workflow CI)"
        )

    print("\n✅ Configuration terminée.")
    return 0


def cmd_benchmarks_refresh(args: argparse.Namespace) -> int:
    configure_logging(level="INFO")
    agg = _build_aggregator(force=True)
    for cat in TaskCategory:
        scores = agg.get_scores(cat)
        log.info("%s: %d modèles scorés", cat.value, len(scores))
    print("✅ Cache benchmarks mis à jour.")
    return 0


def cmd_intake(args: argparse.Namespace) -> int:
    from gateway_llm import intake as m

    if args.intake_cmd == "from-folder":
        n = m.intake_from_folder(
            pathlib.Path(args.path),
            pathlib.Path(args.output),
            prompt_template=args.prompt,
            domain=args.domain,
            sensitivity=args.sensitivity,
        )
    elif args.intake_cmd == "from-text":
        n = m.intake_from_text(
            pathlib.Path(args.path),
            pathlib.Path(args.output),
            prompt_template=args.prompt,
            domain=args.domain,
            sensitivity=args.sensitivity,
        )
    elif args.intake_cmd == "from-csv":
        n = m.intake_from_csv(
            pathlib.Path(args.path),
            pathlib.Path(args.output),
            id_column=args.id_column,
            prompt_template=args.prompt,
            sensitivity=args.sensitivity,
        )
    else:
        n = m.intake_from_urls(
            pathlib.Path(args.path),
            pathlib.Path(args.output),
            prompt_template=args.prompt,
            sensitivity=args.sensitivity,
            respect_robots=not args.no_robots,
        )
    print(f"✅ {n} tâches écrites dans {args.output}")
    return 0


def cmd_batch_run(args: argparse.Namespace) -> int:
    configure_logging(level="DEBUG" if args.verbose else "INFO")

    # Pre-flight (sauf dry-run ou --no-doctor)
    if not args.dry_run and not args.no_doctor:
        ok = _run_preflight(
            config_path=args.config,
            auto_install=not args.no_install,
            assume_yes=args.yes,
        )
        if not ok:
            return 1

    cfg = load_config(args.config)
    # Policy de résidence : toujours appliquée (défaut embarqué si --policy absent).
    # Sans policy, un task 'confidential' pourrait partir vers un cloud.
    policy = load_policy(args.policy)

    hw = detect_vram()
    log.info("VRAM détectée: %s Go (%s)", hw.vram_gb, hw.source)

    agg = None
    if args.refresh_benchmarks or args.rank_by_benchmarks:
        agg = _build_aggregator(force=args.refresh_benchmarks)

    classifier: TaskClassifier | None = None

    from gateway_llm.batch import BatchRunner

    runner = BatchRunner(
        config=cfg,
        policy=policy,
        benchmarks=agg,
        hardware=hw,
        input_path=pathlib.Path(args.input),
        output_path=pathlib.Path(args.output),
        resume=args.resume,
        dry_run=args.dry_run,
        classifier=classifier,
        classifier_model=args.classifier_model,
        disable_classifier=args.no_classifier,
        ensure_markdown=not args.no_markdown,
        max_cost_eur=args.max_cost_eur,
    )
    runner.run()
    return 0


# ─── Main ───────────────────────────────────────────────────────
_MAIN_EPILOG = """\
Commandes disponibles :
  doctor       Diagnostic de l'environnement (deps, Ollama, modèles)
  setup        Installation guidée (télécharge les modèles manquants)
  intake       Convertir des données hétérogènes en JSONL de tâches
  benchmarks   Gérer le cache des benchmarks
  batch        Traiter un lot de tâches

Exemples rapides :
  gateway-llm doctor
      Vérifie que tout est en place (config intégrée par défaut).

  gateway-llm setup
      Télécharge les modèles Ollama manquants (config intégrée).

  gateway-llm intake from-folder --path ./screenshots --output tasks.jsonl
      Convertit un dossier d'images en fichier de tâches.

  gateway-llm batch run --input tasks.jsonl --output results.jsonl
      Lance le traitement avec la config intégrée.

  gateway-llm batch run ... --config config/models.yaml
      Idem avec une config personnalisée.

  gateway-llm batch run ... --dry-run
      Estime le coût sans appeler les modèles.

  gateway-llm batch run ... --resume
      Reprend après une interruption.

Pour l'aide détaillée d'une commande : gateway-llm <commande> --help
Documentation : https://github.com/<vous>/gateway-llm
"""


def _epilog_for(cmd: str) -> str:
    return {
        "doctor": """\
Exemples :
  gateway-llm doctor
  gateway-llm doctor --config config/models.yaml

Sortie :
  ✓ / ⚠ / ✗ par item (deps Python, binaire Ollama, daemon, modèles, secrets).
  Code retour 1 si erreurs critiques, 0 sinon.
""",
        "setup": """\
Exemples :
  gateway-llm setup
      Interactif : config intégrée + demande confirmation avant chaque pull.

  gateway-llm setup --yes
      Non-interactif : installe tout ce qui manque.

  gateway-llm setup --config config/models.yaml
      Utilise une config personnalisée.

Sans --config, la config bootstrap intégrée est utilisée.
""",
        "setup-secrets": """\
Assistant interactif pour choisir et configurer un backend de secrets :

  - Machine personnelle : PowerShell Vault (Windows) ou 1Password
  - Machine d'entreprise : HashiCorp Vault, AWS Secrets Manager,
    ou Azure Key Vault
  - CI/CD : variables d'environnement (déconseillé en usage quotidien,
    recommandé en CI)

Le choix est persisté dans ~/.gateway-llm/secrets.yaml (hors repo).
""",
        "intake": """\
Sous-commandes :
  from-folder    Une tâche par image dans un dossier (récursif)
  from-text      Une tâche par fichier texte (.txt, .md, .html, .eml)
  from-csv       Une tâche par ligne d'un CSV
  from-urls      Une tâche par URL (respecte robots.txt par défaut)

Exemples :
  gateway-llm intake from-folder --path ./screenshots --output tasks.jsonl
  gateway-llm intake from-text --path ./emails --output tasks.jsonl
  gateway-llm intake from-csv --path ./tickets.csv --column description --output tasks.jsonl
  gateway-llm intake from-urls --path ./urls.txt --output tasks.jsonl
""",
        "benchmarks": """\
Sous-commandes :
  refresh    Force le rafraîchissement du cache BenchLM + RankLLMs

Le cache local a un TTL de 24h. `batch run --refresh-benchmarks` force
aussi un refresh au démarrage. Le refresh lazy tourne automatiquement
au démarrage d'un batch si le cache a plus de 14 jours.
""",
        "batch": """\
Sous-commandes :
  run        Lance un batch JSONL

Options principales de `batch run` :
  --input PATH               Fichier d'entrée JSONL (une tâche par ligne)
  --output PATH              Fichier de sortie JSONL
  --config PATH              Config YAML (défaut : config intégrée)
  --policy PATH              Politique de résidence (YAML, défaut : intégrée)
  --resume                   Reprend un batch interrompu
  --dry-run                  Estime sans appeler les modèles
  --refresh-benchmarks       Rafraîchit les scores avant de router
  --rank-by-benchmarks       Réordonne les chaînes par benchmarks
  --max-cost-eur X           Budget maximal en euros (arrêt contrôlé)
  --no-classifier            Désactive la classification automatique
  --classifier-model NAME    Modèle Ollama pour classifier (défaut: qwen3:4b-instruct)
  --no-doctor                Skip le pre-flight (utile en CI)
  --no-install               Pre-flight sans installation auto
  --yes, -y                  Auto-confirme toutes les installations
  --verbose, -v              Logs DEBUG
""",
    }.get(cmd, "")


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gateway-llm",
        description=(
            "Quality-Gated Batch Router — routage LLM par cascade, "
            "guardrails, budget et résidence des données."
        ),
        epilog=_MAIN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")

    # ─── doctor ────────────────────────────────────────────────
    d = sub.add_parser(
        "doctor",
        help="Vérifier l'environnement (deps, Ollama, modèles)",
        description=(
            "Vérifie les dépendances Python, la présence d'Ollama, "
            "son daemon, et les modèles locaux déclarés dans la config."
        ),
        epilog=_epilog_for("doctor"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    d.add_argument(
        "--config",
        default=None,
        help="Config YAML pour découvrir les modèles requis (défaut : intégrée)",
    )
    d.set_defaults(func=cmd_doctor)

    # ─── setup ─────────────────────────────────────────────────
    s = sub.add_parser(
        "setup",
        help="Installation guidée (télécharge les modèles manquants)",
        description=(
            "Diagnostique l'environnement puis télécharge les modèles "
            "Ollama manquants déclarés dans la config."
        ),
        epilog=_epilog_for("setup"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument(
        "--config",
        default=None,
        help="Config YAML des providers/modèles (défaut : intégrée)",
    )
    s.add_argument("--yes", "-y", action="store_true", help="Auto-confirme chaque installation")
    s.set_defaults(func=cmd_setup)

    # ─── intake ────────────────────────────────────────────────
    i = sub.add_parser(
        "intake",
        help="Convertir des données en JSONL de tâches",
        description="Convertisseur de données hétérogènes en JSONL de tâches.",
        epilog=_epilog_for("intake"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    i_sub = i.add_subparsers(dest="intake_cmd", required=True, metavar="<source>")

    f = i_sub.add_parser("from-folder", help="Dossier d'images (récursif)")
    f.add_argument("--path", required=True)
    f.add_argument("--output", required=True)
    f.add_argument("--prompt", default="Analyse cette image et décris ce que tu vois.")
    f.add_argument("--domain", default="multimodal_extraction")
    f.add_argument("--sensitivity", default="public")

    t = i_sub.add_parser("from-text", help="Dossier de fichiers texte")
    t.add_argument("--path", required=True)
    t.add_argument("--output", required=True)
    t.add_argument("--prompt", default="Traite le contenu suivant :\n\n{content}")
    t.add_argument("--domain", default=None)
    t.add_argument("--sensitivity", default="public")

    c = i_sub.add_parser("from-csv", help="Fichier CSV")
    c.add_argument("--path", required=True)
    c.add_argument("--output", required=True)
    c.add_argument("--id-column", default=None, help="Nom de la colonne d'ID (optionnel)")
    c.add_argument("--prompt", default="{content}")
    c.add_argument("--sensitivity", default="public")

    u = i_sub.add_parser("from-urls", help="Liste d'URLs")
    u.add_argument("--path", required=True, help="Fichier .txt avec une URL par ligne")
    u.add_argument("--output", required=True)
    u.add_argument("--prompt", default="Résume la page suivante :\n\n{content}")
    u.add_argument("--sensitivity", default="public")
    u.add_argument(
        "--no-robots", action="store_true", help="Ne pas vérifier robots.txt (à vos risques)"
    )

    i.set_defaults(func=cmd_intake)

    # ─── benchmarks ────────────────────────────────────────────
    b = sub.add_parser(
        "benchmarks",
        help="Gérer le cache des benchmarks",
        description="Gère le cache local des scores de benchmarks.",
        epilog=_epilog_for("benchmarks"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    b_sub = b.add_subparsers(dest="bench_cmd", required=True, metavar="<action>")
    br = b_sub.add_parser("refresh", help="Forcer le rafraîchissement")
    br.set_defaults(func=cmd_benchmarks_refresh)

    # ─── batch ─────────────────────────────────────────────────
    ba = sub.add_parser(
        "batch",
        help="Traiter un lot de tâches",
        description="Orchestrateur de traitement par lot (JSONL → JSONL).",
        epilog=_epilog_for("batch"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ba_sub = ba.add_subparsers(dest="batch_cmd", required=True, metavar="<action>")
    run = ba_sub.add_parser(
        "run",
        help="Lancer un batch JSONL",
        description="Lance un batch de traitement avec pre-flight automatique.",
    )
    run.add_argument(
        "--no-markdown",
        action="store_true",
        help="Désactive l'instruction 'Réponds en Markdown'",
    )
    run.add_argument("--input", required=True, help="Fichier d'entrée JSONL")
    run.add_argument("--output", required=True, help="Fichier de sortie JSONL")
    run.add_argument(
        "--config",
        default=None,
        help="Config YAML (défaut : config intégrée)",
    )
    run.add_argument(
        "--policy",
        default=None,
        help="Politique de résidence YAML (défaut : politique intégrée)",
    )
    run.add_argument("--resume", action="store_true", help="Reprendre un batch interrompu")
    run.add_argument("--dry-run", action="store_true", help="Estimer sans appeler les modèles")
    run.add_argument(
        "--refresh-benchmarks", action="store_true", help="Rafraîchir les scores avant de router"
    )
    run.add_argument(
        "--rank-by-benchmarks",
        action="store_true",
        help="Réordonner les chaînes selon les benchmarks",
    )
    run.add_argument("--max-cost-eur", type=float, default=None, help="Budget maximal en euros")
    run.add_argument(
        "--no-classifier", action="store_true", help="Désactiver la classification automatique"
    )
    run.add_argument(
        "--classifier-model", default="qwen3:4b-instruct", help="Modèle Ollama de classification"
    )
    run.add_argument("--no-doctor", action="store_true", help="Skip le pre-flight (utile en CI)")
    run.add_argument(
        "--no-install", action="store_true", help="Pre-flight sans installation automatique"
    )
    run.add_argument("--yes", "-y", action="store_true", help="Auto-confirmer les installations")
    run.add_argument("--verbose", "-v", action="store_true")
    run.set_defaults(func=cmd_batch_run)

    # ─── setup-secrets ─────────────────────────────────────────
    ss = sub.add_parser(
        "setup-secrets",
        help="Configurer le coffre-fort de secrets",
        description=(
            "Guide interactif pour choisir et configurer un backend de secrets : "
            "PowerShell Vault, 1Password, HashiCorp Vault, AWS Secrets Manager, "
            "Azure Key Vault, ou variables d'environnement."
        ),
    )
    ss.set_defaults(func=cmd_setup_secrets)

    return p


def main(argv: list[str] | None = None) -> int:
    p = _make_parser()
    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())