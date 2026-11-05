# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Application graphique unifiée : préparation, lancement, résultats."""

from __future__ import annotations

import json
import pathlib
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from llm_gateway.intake import (
    intake_from_csv,
    intake_from_folder,
    intake_from_text,
    intake_from_urls,
)


# ─── Onglet 1 : Préparation des données ────────────────────────
class PrepareTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=20)
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self, text="Type de source :", font=("", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.source_type = tk.StringVar(value="Dossier d'images")
        ttk.Combobox(
            self, textvariable=self.source_type, state="readonly",
            values=[
                "Dossier d'images",
                "Dossier de fichiers texte",
                "Fichier CSV",
                "Liste d'URLs (.txt)",
            ],
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        ttk.Label(self, text="Emplacement :").grid(
            row=2, column=0, sticky="w", pady=(0, 4),
        )
        self.path_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.path_var).grid(
            row=3, column=0, columnspan=2, sticky="ew",
        )
        ttk.Button(self, text="Parcourir…", command=self._pick_source).grid(
            row=3, column=2, padx=(6, 0),
        )

        ttk.Label(self, text="Colonne CSV (si applicable) :").grid(
            row=4, column=0, sticky="w", pady=(12, 4),
        )
        self.column_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.column_var).grid(
            row=5, column=0, columnspan=3, sticky="ew",
        )

        ttk.Label(self, text="Consigne envoyée au modèle :").grid(
            row=6, column=0, sticky="w", pady=(12, 4),
        )
        self.prompt_var = tk.StringVar(
            value="Analyse cette image et décris ce que tu vois.",
        )
        ttk.Entry(self, textvariable=self.prompt_var).grid(
            row=7, column=0, columnspan=3, sticky="ew",
        )

        ttk.Label(self, text="Fichier de sortie (.jsonl) :").grid(
            row=8, column=0, sticky="w", pady=(12, 4),
        )
        self.out_var = tk.StringVar(
            value=str(pathlib.Path.cwd() / "tasks.jsonl"),
        )
        ttk.Entry(self, textvariable=self.out_var).grid(
            row=9, column=0, columnspan=2, sticky="ew",
        )
        ttk.Button(
            self, text="Enregistrer sous…", command=self._pick_output,
        ).grid(row=9, column=2, padx=(6, 0))

        ttk.Button(
            self, text="Générer le fichier de tâches",
            command=self._generate,
        ).grid(row=10, column=0, columnspan=3, pady=20)

    def _pick_source(self) -> None:
        stype = self.source_type.get()
        if "Dossier" in stype:
            p = filedialog.askdirectory()
        else:
            p = filedialog.askopenfilename(
                filetypes=[("Fichier", "*.csv *.txt"), ("Tous", "*.*")],
            )
        if p:
            self.path_var.set(p)

    def _pick_output(self) -> None:
        p = filedialog.asksaveasfilename(
            defaultextension=".jsonl", filetypes=[("JSONL", "*.jsonl")],
        )
        if p:
            self.out_var.set(p)

    def _generate(self) -> None:
        try:
            src = pathlib.Path(self.path_var.get())
            out = pathlib.Path(self.out_var.get())
            prompt = self.prompt_var.get()
            stype = self.source_type.get()

            if stype == "Dossier d'images":
                n = intake_from_folder(src, out, prompt_template=prompt)
            elif stype == "Dossier de fichiers texte":
                n = intake_from_text(src, out, prompt_template=prompt)
            elif stype == "Fichier CSV":
                col = self.column_var.get().strip()
                if not col:
                    messagebox.showerror("Erreur", "Indiquez la colonne CSV.")
                    return
                n = intake_from_csv(src, out, column=col, prompt_template=prompt)
            else:
                n = intake_from_urls(src, out, prompt_template=prompt)

            messagebox.showinfo(
                "Succès", f"{n} tâches écrites dans :\n{out}",
            )
        except Exception as e:
            messagebox.showerror("Erreur", str(e))


# ─── Onglet 2 : Lancement du traitement ────────────────────────
class RunTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=20)
        self._thread: threading.Thread | None = None
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="Fichier d'entrée (.jsonl) :").grid(
            row=0, column=0, sticky="w", pady=(0, 4),
        )
        self.input_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.input_var).grid(
            row=1, column=0, columnspan=2, sticky="ew",
        )
        ttk.Button(
            self, text="Parcourir…", command=self._pick_input,
        ).grid(row=1, column=2, padx=(6, 0))

        ttk.Label(self, text="Fichier de résultats (.jsonl) :").grid(
            row=2, column=0, sticky="w", pady=(12, 4),
        )
        self.output_var = tk.StringVar(
            value=str(pathlib.Path.cwd() / "results.jsonl"),
        )
        ttk.Entry(self, textvariable=self.output_var).grid(
            row=3, column=0, columnspan=2, sticky="ew",
        )
        ttk.Button(
            self, text="Enregistrer sous…", command=self._pick_output,
        ).grid(row=3, column=2, padx=(6, 0))

        ttk.Label(self, text="Configuration (models.yaml) :").grid(
            row=4, column=0, sticky="w", pady=(12, 4),
        )
        self.config_var = tk.StringVar(
            value=str(pathlib.Path.cwd() / "config" / "models.yaml"),
        )
        ttk.Entry(self, textvariable=self.config_var).grid(
            row=5, column=0, columnspan=2, sticky="ew",
        )
        ttk.Button(
            self, text="Parcourir…", command=self._pick_config,
        ).grid(row=5, column=2, padx=(6, 0))

        ttk.Label(self, text="Budget maximal (€, optionnel) :").grid(
            row=6, column=0, sticky="w", pady=(12, 4),
        )
        self.max_cost_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.max_cost_var).grid(
            row=7, column=0, sticky="ew",
        )

        self.run_btn = ttk.Button(
            self, text="Lancer le traitement", command=self._launch,
        )
        self.run_btn.grid(row=8, column=0, columnspan=3, pady=20)

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.grid(row=9, column=0, columnspan=3, sticky="ew")

    def _pick_input(self) -> None:
        p = filedialog.askopenfilename(
            filetypes=[("JSONL", "*.jsonl"), ("Tous", "*.*")],
        )
        if p:
            self.input_var.set(p)

    def _pick_output(self) -> None:
        p = filedialog.asksaveasfilename(
            defaultextension=".jsonl", filetypes=[("JSONL", "*.jsonl")],
        )
        if p:
            self.output_var.set(p)

    def _pick_config(self) -> None:
        p = filedialog.askopenfilename(
            filetypes=[("YAML", "*.yaml *.yml"), ("Tous", "*.*")],
        )
        if p:
            self.config_var.set(p)

    def _launch(self) -> None:
        if self._thread and self._thread.is_alive():
            messagebox.showwarning("En cours", "Un traitement est déjà en cours.")
            return

        inp = pathlib.Path(self.input_var.get())
        out = pathlib.Path(self.output_var.get())
        cfg = pathlib.Path(self.config_var.get())
        if not inp.exists():
            messagebox.showerror("Erreur", f"Fichier d'entrée introuvable : {inp}")
            return
        if not cfg.exists():
            messagebox.showerror("Erreur", f"Configuration introuvable : {cfg}")
            return

        max_cost = None
        raw = self.max_cost_var.get().strip()
        if raw:
            try:
                max_cost = float(raw)
            except ValueError:
                messagebox.showerror("Erreur", "Budget invalide (nombre attendu).")
                return

        self.progress.start(10)
        self.run_btn.config(state="disabled")

        def worker() -> None:
            try:
                from llm_gateway.batch import BatchRunner
                from llm_gateway.config import load_config
                from llm_gateway.hardware import detect_vram

                config = load_config(cfg)
                hw = detect_vram()
                runner = BatchRunner(
                    config=config,
                    input_path=inp,
                    output_path=out,
                    hardware=hw,
                    max_cost_eur=max_cost,
                )
                runner.run()
                self.after(0, lambda: self._on_success(out))
            except Exception as e:
                self.after(0, lambda: self._on_error(e))

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _on_success(self, output: pathlib.Path) -> None:
        self.progress.stop()
        self.run_btn.config(state="normal")
        messagebox.showinfo(
            "Terminé", f"Traitement terminé.\nRésultats dans :\n{output}",
        )

    def _on_error(self, exc: Exception) -> None:
        self.progress.stop()
        self.run_btn.config(state="normal")
        messagebox.showerror("Erreur", f"Le traitement a échoué :\n{exc}")


# ─── Onglet 3 : Visualisation des résultats ────────────────────
class ResultsTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=20)
        self._results: list[dict] = []
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Fichier de résultats (.jsonl) :").pack(
            side="left",
        )
        self.file_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.file_var).pack(
            side="left", fill="x", expand=True, padx=(8, 8),
        )
        ttk.Button(top, text="Charger", command=self._load).pack(side="left")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # Onglet Résumé
        self.summary_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.summary_frame, text="Résumé")
        self.summary_text = tk.Text(
            self.summary_frame, wrap="word", height=20, state="disabled",
        )
        self.summary_text.pack(fill="both", expand=True)

        # Onglet À revoir
        self.review_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.review_frame, text="À revoir")
        self.review_list = tk.Listbox(self.review_frame)
        self.review_list.pack(fill="both", expand=True, side="left")
        scroll = ttk.Scrollbar(
            self.review_frame, orient="vertical",
            command=self.review_list.yview,
        )
        scroll.pack(side="right", fill="y")
        self.review_list.config(yscrollcommand=scroll.set)
        self.review_list.bind("<<ListboxSelect>>", self._on_review_select)

        self.detail_frame = ttk.Frame(self.review_frame, padding=10)
        self.detail_frame.pack(fill="both", expand=True, padx=(10, 0))
        self.detail_text = tk.Text(
            self.detail_frame, wrap="word", height=12, state="disabled",
        )
        self.detail_text.pack(fill="both", expand=True)
        btn_frame = ttk.Frame(self.detail_frame)
        btn_frame.pack(fill="x", pady=(6, 0))
        ttk.Button(
            btn_frame, text="Accepter", command=self._accept,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            btn_frame, text="Rejeter", command=self._reject,
        ).pack(side="left")

        # Onglet Tout
        self.all_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.all_frame, text="Tout")
        self.all_tree = ttk.Treeview(
            self.all_frame,
            columns=("id", "domain", "model", "status", "cost"),
            show="headings",
        )
        for col, label in [
            ("id", "ID"),
            ("domain", "Domaine"),
            ("model", "Modèle"),
            ("status", "Statut"),
            ("cost", "Coût (€)"),
        ]:
            self.all_tree.heading(col, text=label)
            self.all_tree.column(col, width=120)
        self.all_tree.pack(fill="both", expand=True)

    def _load(self) -> None:
        path = pathlib.Path(self.file_var.get())
        if not path.exists():
            messagebox.showerror("Erreur", f"Fichier introuvable : {path}")
            return
        self._results = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        self._refresh()

    def _refresh(self) -> None:
        # Résumé
        total = len(self._results)
        approved = sum(1 for r in self._results if r.get("status") == "approved")
        review = sum(
            1 for r in self._results
            if r.get("status") == "human_review"
            or r.get("guardrail_passed") is False
        )
        failed = total - approved - review
        total_cost = sum(r.get("cost_eur", 0.0) for r in self._results)

        summary = (
            f"Total : {total}\n"
            f"Approuvées : {approved}\n"
            f"À revoir : {review}\n"
            f"Échecs : {failed}\n"
            f"Coût total : {total_cost:.4f} €\n"
        )
        self.summary_text.config(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", summary)
        self.summary_text.config(state="disabled")

        # À revoir
        self.review_list.delete(0, "end")
        for r in self._results:
            if (
                r.get("status") == "human_review"
                or r.get("guardrail_passed") is False
            ):
                rid = r.get("id", "?")
                reason = r.get("guardrail_reason", "—")
                self.review_list.insert("end", f"{rid}  —  {reason}")

        # Tout
        for item in self.all_tree.get_children():
            self.all_tree.delete(item)
        for r in self._results:
            self.all_tree.insert(
                "", "end",
                values=(
                    r.get("id", "?"),
                    r.get("domain", "?"),
                    r.get("model_used", "—"),
                    r.get("status", "?"),
                    f"{r.get('cost_eur', 0.0):.4f}",
                ),
            )

    def _on_review_select(self, _event) -> None:
        sel = self.review_list.curselection()
        if not sel:
            return
        idx = sel[0]
        target = None
        count = 0
        for r in self._results:
            if (
                r.get("status") == "human_review"
                or r.get("guardrail_passed") is False
            ):
                if count == idx:
                    target = r
                    break
                count += 1
        if target is None:
            return
        text = (
            f"ID : {target.get('id')}\n"
            f"Raison : {target.get('guardrail_reason', '—')}\n\n"
            f"Réponse :\n{target.get('response', '—')}"
        )
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.config(state="disabled")

    def _accept(self) -> None:
        self._decision("accepted")

    def _reject(self) -> None:
        self._decision("rejected")

    def _decision(self, decision: str) -> None:
        sel = self.review_list.curselection()
        if not sel:
            return
        idx = sel[0]
        target = None
        count = 0
        for r in self._results:
            if (
                r.get("status") == "human_review"
                or r.get("guardrail_passed") is False
            ):
                if count == idx:
                    target = r
                    break
                count += 1
        if target is None:
            return

        decisions_path = pathlib.Path("decisions.jsonl")
        with decisions_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": target.get("id"),
                "decision": decision,
            }) + "\n")
        messagebox.showinfo(
            "Enregistré",
            f"Décision '{decision}' enregistrée pour {target.get('id')}",
        )


# ─── Application principale ────────────────────────────────────
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("llm-gateway — Traitement par lot")
        self.geometry("900x650")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Onglet Configuration EN PREMIER (obligatoire avant le reste)
        self.secrets_tab = SecretsTab(notebook)
        notebook.add(self.secrets_tab, text="Configuration")

        self.prepare_tab = PrepareTab(notebook)
        notebook.add(self.prepare_tab, text="1. Préparer les données")

        self.run_tab = RunTab(notebook)
        notebook.add(self.run_tab, text="2. Lancer le traitement")

        self.results_tab = ResultsTab(notebook)
        notebook.add(self.results_tab, text="3. Voir les résultats")

        # Au premier lancement, ouvrir directement l'onglet Configuration
        config_file = pathlib.Path.home() / ".llm-gateway" / "secrets.yaml"
        if not config_file.exists():
            notebook.select(self.secrets_tab)
            messagebox.showinfo(
                "Configuration requise",
                "Avant de commencer, choisissez où stocker vos clés API "
                "dans l'onglet Configuration.",
            )

class SecretsTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=20)
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="Coffre-fort de secrets",
                  font=("", 12, "bold")).pack(anchor="w", pady=(0, 12))

        self.backend_var = tk.StringVar(value="powershell_vault")
        backends = [
            ("PowerShell Vault (Windows)", "powershell_vault"),
            ("1Password CLI", "1password"),
            ("HashiCorp Vault", "hashicorp_vault"),
            ("AWS Secrets Manager", "aws_secrets_manager"),
            ("Azure Key Vault", "azure_key_vault"),
            ("Variables d'environnement (⚠ non chiffré)", "env"),
        ]
        for label, val in backends:
            ttk.Radiobutton(
                self, text=label, variable=self.backend_var, value=val,
            ).pack(anchor="w", pady=2)

        self.options_frame = ttk.Frame(self)
        self.options_frame.pack(fill="x", pady=(12, 12))

        ttk.Button(self, text="Enregistrer la configuration",
                   command=self._save).pack(pady=8)
        ttk.Button(self, text="Tester la connexion",
                   command=self._test).pack(pady=4)

        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var,
                  foreground="gray").pack(anchor="w", pady=(8, 0))

    def _save(self) -> None:
        from llm_gateway.secrets import save_backend_config
        backend = self.backend_var.get()
        options = {}  # à enrichir avec champs si HashiCorp/AWS/Azure
        save_backend_config(backend, options)
        self.status_var.set(f"✅ Backend '{backend}' enregistré.")

    def _test(self) -> None:
        try:
            from llm_gateway.secrets import get_backend
            b = get_backend()
            ok = b.is_available()
            self.status_var.set(
                f"{'✅' if ok else '⚠'} {b.name} : "
                f"{'opérationnel' if ok else 'non disponible'}"
            )
        except Exception as e:
            self.status_var.set(f"❌ {e}")

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()