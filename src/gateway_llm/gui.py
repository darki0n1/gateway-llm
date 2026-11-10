# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Application graphique unifiée : préparation, lancement, résultats."""

from __future__ import annotations

import contextlib
import json
import logging
import pathlib
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from gateway_llm.config import LocalMode, save_local_mode
from gateway_llm.intake import (
    intake_from_csv_multi,
    intake_from_folder,
    intake_from_text,
    intake_from_urls,
    intake_mixed,
)

log = logging.getLogger(__name__)

# ─── Drag & Drop (optionnel) ──────────────────────────────────
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore[import-not-found]

    _TkBase: Any = TkinterDnD.Tk
    _DND_AVAILABLE = True
except ImportError:
    _TkBase = tk.Tk
    DND_FILES = None  # type: ignore[assignment]
    _DND_AVAILABLE = False


# ─── Playwright Chromium : check + installation auto ──────────
def _playwright_chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def _install_playwright_chromium(timeout: int = 600) -> bool:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.error("Installation Chromium échouée : %s", e)
        return False
    if r.returncode != 0:
        log.error(
            "playwright install chromium a retourné %d : %s",
            r.returncode,
            (r.stderr or "").strip()[:200],
        )
        return False
    return True


# ─── Handler de logs vers widget Text (batché) ────────────────
class _TextHandler(logging.Handler):
    def __init__(self, text_widget: tk.Text) -> None:
        super().__init__()
        self._widget = text_widget
        self.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        self._queue: queue.Queue[str] = queue.Queue()
        self._widget.after(150, self._drain)

    def emit(self, record: logging.LogRecord) -> None:
        with contextlib.suppress(Exception):
            self._queue.put_nowait(self.format(record))

    def _drain(self) -> None:
        lines: list[str] = []
        try:
            for _ in range(200):
                lines.append(self._queue.get_nowait())
        except queue.Empty:
            pass

        if lines:
            try:
                self._widget.config(state="normal")
                self._widget.insert("end", "\n".join(lines) + "\n")
                total = int(self._widget.index("end-1c").split(".")[0])
                if total > 1000:
                    self._widget.delete("1.0", f"{total - 1000}.0")
                self._widget.see("end")
                self._widget.config(state="disabled")
            except tk.TclError:
                pass

        self._widget.after(150, self._drain)


# ─── Dialogue de premier lancement : mode d'exécution ─────────
class ModeDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title("Mode d'exécution")
        self.geometry("620x520")
        self.resizable(False, False)
        self.result: LocalMode | None = None

        ttk.Label(
            self,
            text="Comment voulez-vous utiliser gateway-llm ?",
            font=("", 12, "bold"),
        ).pack(pady=(16, 4), padx=20, anchor="w")

        ttk.Label(
            self,
            text=(
                "Ce choix détermine quels modèles sont téléchargés et utilisés.\n"
                "Vous pourrez le modifier plus tard dans ~/.gateway-llm/config.yaml."
            ),
            foreground="gray",
        ).pack(pady=(0, 12), padx=20, anchor="w")

        self.var = tk.StringVar(value=LocalMode.DEFAULT.value)
        options = [
            (
                LocalMode.CLOUD_ONLY,
                "100% cloud",
                "Utilise uniquement les API cloud. Clés API requises.\n"
                "Aucun modèle local téléchargé.",
            ),
            (
                LocalMode.LOCAL_ONLY,
                "100% local",
                "Télécharge les meilleurs modèles Ollama pour votre machine.\n"
                "Aucune donnée ne sort.",
            ),
            (
                LocalMode.HYBRID,
                "Hybride",
                "Utilise les modèles locaux déjà présents, complète avec le\n"
                "cloud quand un meilleur modèle cloud est disponible.",
            ),
            (
                LocalMode.DEFAULT,
                "Défaut (recommandé)",
                "Télécharge uniquement les modèles bootstrap (qwen légers).",
            ),
        ]
        for mode, title, desc in options:
            frame = ttk.Frame(self)
            frame.pack(fill="x", padx=20, pady=4)
            ttk.Radiobutton(frame, text=title, variable=self.var, value=mode.value).pack(anchor="w")
            ttk.Label(frame, text=desc, foreground="gray", justify="left").pack(
                anchor="w", padx=(24, 0)
            )

        ttk.Button(self, text="Valider", command=self._ok).pack(pady=16)
        self.transient(parent)
        self.grab_set()

    def _ok(self) -> None:
        self.result = LocalMode(self.var.get())
        save_local_mode(self.result)
        self.destroy()


# ─── Onglet 1 : Préparation des données ────────────────────────
class PrepareTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=20)
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=3)
        self.columnconfigure(2, weight=1)

        ttk.Label(self, text="Type de source :").grid(
            row=0, column=0, sticky="w", padx=(40, 0), pady=(20, 4)
        )
        self.source_type = tk.StringVar(value="Dossier d'images")
        ttk.Combobox(
            self,
            textvariable=self.source_type,
            state="readonly",
            values=[
                "Dossier d'images",
                "Dossier de fichiers texte (.txt, .md, .eml)",
                "Fichier(s) CSV",
                "Liste d'URLs (.txt)",
                "Mixte (images + textes + CSV)",
            ],
        ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=(40, 40), pady=(0, 12))

        hint = (
            "Emplacement(s) — glisser-déposer accepté :" if _DND_AVAILABLE else "Emplacement(s) :"
        )
        ttk.Label(self, text=hint).grid(row=2, column=0, sticky="w", padx=(40, 0), pady=(0, 4))

        list_frame = ttk.Frame(self)
        list_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=(40, 0))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.paths_listbox = tk.Listbox(list_frame, height=5, selectmode="extended")
        self.paths_listbox.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.paths_listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.paths_listbox.config(yscrollcommand=scroll.set)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=2, padx=(6, 40), sticky="n")
        ttk.Button(btn_frame, text="Ajouter…", command=self._add_sources).pack(fill="x")
        ttk.Button(btn_frame, text="Retirer", command=self._remove_selected).pack(
            fill="x", pady=(4, 0)
        )
        ttk.Button(
            btn_frame,
            text="Vider",
            command=lambda: self.paths_listbox.delete(0, "end"),
        ).pack(fill="x", pady=(4, 0))

        ttk.Label(self, text="Consigne envoyée au modèle :").grid(
            row=4, column=0, sticky="w", padx=(40, 0), pady=(12, 4)
        )
        self.prompt_text = tk.Text(self, height=3, wrap="word")
        self.prompt_text.grid(row=5, column=0, columnspan=3, sticky="ew", padx=(40, 40))
        self.prompt_text.insert(
            "1.0",
            "Analyse cette image et décris ce que tu vois.",
        )

        ttk.Label(self, text="Fichier de sortie (.jsonl) :").grid(
            row=6, column=0, sticky="w", padx=(40, 0), pady=(12, 4)
        )
        self.out_var = tk.StringVar(value=str(pathlib.Path.cwd() / "tasks.jsonl"))
        ttk.Entry(self, textvariable=self.out_var).grid(
            row=7, column=0, columnspan=2, sticky="ew", padx=(40, 0)
        )
        ttk.Button(self, text="Enregistrer sous…", command=self._pick_output).grid(
            row=7, column=2, padx=(6, 40)
        )

        ttk.Button(
            self,
            text="Générer le fichier de tâches",
            command=self._generate,
        ).grid(row=8, column=0, columnspan=3, pady=20)

    # ─── Drag & Drop ──────────────────────────────────────────
    def _on_drop(self, event) -> None:
        if not _DND_AVAILABLE:
            return
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            return
        for p in paths:
            self.paths_listbox.insert("end", p)

    # ─── Ajout / suppression ──────────────────────────────────
    def _add_sources(self) -> None:
        stype = self.source_type.get()
        if stype == "Fichier(s) CSV":
            self.prompt_text.delete("1.0", "end")
            self.prompt_text.insert("1.0", "Calcule le total de la recette.")
            paths = filedialog.askopenfilenames(filetypes=[("CSV", "*.csv"), ("Tous", "*.*")])
        elif stype.startswith("Dossier"):
            p = filedialog.askdirectory()
            paths = (p,) if p else ()
        elif stype == "Mixte (images + textes + CSV)":
            paths = filedialog.askopenfilenames(
                filetypes=[
                    (
                        "Tous supportés",
                        "*.png *.jpg *.jpeg *.gif *.webp *.bmp *.txt *.md *.html *.eml *.csv",
                    ),
                    ("Images", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                    ("Textes", "*.txt *.md *.html *.eml"),
                    ("CSV", "*.csv"),
                    ("Tous", "*.*"),
                ]
            )
        else:
            paths = filedialog.askopenfilenames(
                filetypes=[("Fichier", "*.csv *.txt *.jsonl"), ("Tous", "*.*")]
            )
        for p in paths:
            self.paths_listbox.insert("end", p)
        if stype == "Fichier(s) CSV" and paths:
            self._update_csv_columns(pathlib.Path(paths[0]))

    def _remove_selected(self) -> None:
        for i in reversed(self.paths_listbox.curselection()):
            self.paths_listbox.delete(i)

    def _update_csv_columns(self, csv_path: pathlib.Path) -> None:
        try:
            import csv as csv_mod

            with csv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv_mod.reader(f)
                next(reader, [])
            # On garde la colonne pour information, mais intake_from_csv_multi
            # lit de toute façon toutes les colonnes.
        except Exception:
            pass

    def _pick_output(self) -> None:
        p = filedialog.asksaveasfilename(
            defaultextension=".jsonl",
            filetypes=[("JSONL", "*.jsonl")],
        )
        if p:
            self.out_var.set(p)

    def _generate(self) -> None:
        try:
            out = pathlib.Path(self.out_var.get())
            prompt = self.prompt_text.get("1.0", "end-1c").strip()
            stype = self.source_type.get()
            sources = list(self.paths_listbox.get(0, "end"))

            if not sources:
                messagebox.showerror("Erreur", "Ajoutez au moins une source.")
                return

            if stype == "Dossier d'images":
                n = intake_from_folder(pathlib.Path(sources[0]), out, prompt_template=prompt)
            elif stype.startswith("Dossier de fichiers texte"):
                n = intake_from_text(pathlib.Path(sources[0]), out, prompt_template=prompt)
            elif stype == "Fichier(s) CSV":
                paths = [pathlib.Path(p) for p in sources]
                safe_prompt = prompt.replace("{", "{{").replace("}", "}}")
                final_template = (
                    f"Voici un tableau :\n\n{{table}}\n\nQuestion : {safe_prompt}"
                    if safe_prompt
                    else "Voici un tableau :\n\n{table}"
                )
                n = intake_from_csv_multi(paths, out, prompt_template=final_template)
            elif stype == "Mixte (images + textes + CSV)":
                n = intake_mixed(
                    [pathlib.Path(p) for p in sources],
                    out,
                    consigne=prompt,
                )
            else:  # URLs
                n = intake_from_urls(pathlib.Path(sources[0]), out, prompt_template=prompt)

            messagebox.showinfo(
                "Succès",
                f"{n} tâches écrites dans :\n{out}\n\nPassez à l'onglet « Lancer le traitement ».",
            )
        except Exception as e:
            messagebox.showerror("Erreur", str(e))


# ─── Onglet 2 : Lancement du traitement ────────────────────────
class RunTab(ttk.Frame):
    def __init__(self, master: tk.Misc, on_success=None) -> None:
        super().__init__(master, padding=20)
        self._thread: threading.Thread | None = None
        self._log_handler: _TextHandler | None = None
        self._cancel_event: threading.Event | None = None
        self._on_success_cb = on_success
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="Fichier d'entrée (.jsonl) :").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.input_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.input_var).grid(
            row=1, column=0, columnspan=2, sticky="ew"
        )
        ttk.Button(self, text="Parcourir…", command=self._pick_input).grid(
            row=1, column=2, padx=(6, 0)
        )

        ttk.Label(self, text="Fichier de résultats (auto si vide) :").grid(
            row=2, column=0, sticky="w", pady=(12, 4)
        )
        self.output_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.output_var).grid(
            row=3, column=0, columnspan=2, sticky="ew"
        )
        ttk.Button(self, text="Enregistrer sous…", command=self._pick_output).grid(
            row=3, column=2, padx=(6, 0)
        )

        self._advanced_frame = ttk.LabelFrame(self, text="Options avancées", padding=10)
        self._advanced_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self._advanced_frame.grid_remove()

        ttk.Label(
            self._advanced_frame,
            text="Configuration (models.yaml, vide = intégrée) :",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.config_var = tk.StringVar()
        ttk.Entry(self._advanced_frame, textvariable=self.config_var).grid(
            row=1, column=0, columnspan=2, sticky="ew"
        )
        ttk.Button(self._advanced_frame, text="Parcourir…", command=self._pick_config).grid(
            row=1, column=2, padx=(6, 0)
        )

        ttk.Label(self._advanced_frame, text="Budget maximal (€) :").grid(
            row=2, column=0, sticky="w", pady=(8, 4)
        )
        self.max_cost_var = tk.StringVar()
        ttk.Entry(self._advanced_frame, textvariable=self.max_cost_var).grid(
            row=3, column=0, sticky="ew"
        )

        self._advanced_btn = ttk.Button(
            self,
            text="Afficher les options avancées",
            command=self._toggle_advanced,
        )
        self._advanced_btn.grid(row=5, column=0, columnspan=3, pady=(8, 0))

        action_frame = ttk.Frame(self)
        action_frame.grid(row=6, column=0, columnspan=3, sticky="ew", pady=20)
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        self.run_btn = ttk.Button(action_frame, text="Lancer le traitement", command=self._launch)
        self.run_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.cancel_btn = ttk.Button(
            action_frame,
            text="Annuler",
            command=self._cancel,
            state="disabled",
        )
        self.cancel_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.grid(row=7, column=0, columnspan=3, sticky="ew")

        self.eta_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.eta_var, foreground="gray").grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

        log_frame = ttk.Frame(self)
        log_frame.grid(row=9, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
        self.rowconfigure(9, weight=1)
        self.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scroll.set)

    def _toggle_advanced(self) -> None:
        if self._advanced_frame.winfo_viewable():
            self._advanced_frame.grid_remove()
            self._advanced_btn.config(text="Afficher les options avancées")
        else:
            self._advanced_frame.grid()
            self._advanced_btn.config(text="Masquer les options avancées")

    def _append_log(self, msg: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _pick_input(self) -> None:
        p = filedialog.askopenfilename(filetypes=[("JSONL", "*.jsonl"), ("Tous", "*.*")])
        if p:
            self.input_var.set(p)

    def _pick_output(self) -> None:
        p = filedialog.asksaveasfilename(
            defaultextension=".jsonl",
            filetypes=[("JSONL", "*.jsonl")],
        )
        if p:
            self.output_var.set(p)

    def _pick_config(self) -> None:
        p = filedialog.askopenfilename(filetypes=[("YAML", "*.yaml *.yml"), ("Tous", "*.*")])
        if p:
            self.config_var.set(p)

    def _cancel(self) -> None:
        if self._cancel_event is not None and not self._cancel_event.is_set():
            self._cancel_event.set()
            self._append_log("⚠ Annulation demandée, arrêt après la tâche en cours…")

    def _update_progress(self, current: int, total: int, speed: float) -> None:
        if total <= 0:
            return
        pct = (current / total) * 100
        self.progress["value"] = pct

        if speed > 0:
            remaining = (total - current) / speed
            if remaining < 60:
                eta = f"{int(remaining)}s"
            elif remaining < 3600:
                eta = f"{int(remaining // 60)}m {int(remaining % 60)}s"
            else:
                eta = f"{int(remaining // 3600)}h {int((remaining % 3600) // 60)}m"
        else:
            eta = "…"

        self.eta_var.set(f"Progression : {current}/{total} ({pct:.1f}%) — reste ~{eta}")

    def _launch(self) -> None:
        if self._thread and self._thread.is_alive():
            messagebox.showwarning("En cours", "Un traitement est déjà en cours.")
            return

        inp = pathlib.Path(self.input_var.get())
        if not inp.exists():
            messagebox.showerror("Erreur", f"Fichier d'entrée introuvable : {inp}")
            return

        out_raw = self.output_var.get().strip()
        out = pathlib.Path(out_raw) if out_raw else inp.with_name("results.jsonl")

        cfg_raw = self.config_var.get().strip()
        cfg_file: pathlib.Path | None = pathlib.Path(cfg_raw) if cfg_raw else None
        if cfg_file is not None and not cfg_file.exists():
            messagebox.showerror("Erreur", f"Configuration introuvable : {cfg_file}")
            return

        max_cost = None
        raw = self.max_cost_var.get().strip()
        if raw:
            try:
                max_cost = float(raw)
            except ValueError:
                messagebox.showerror("Erreur", "Budget invalide (nombre attendu).")
                return

        try:
            from gateway_llm.secrets import get_backend

            backend = get_backend()
            if not backend.is_available():
                messagebox.showerror(
                    "Secrets indisponibles",
                    f"Le backend '{backend.name}' est configuré mais non "
                    "opérationnel.\n\nVérifiez l'onglet Configuration, ou "
                    "relancez setup-secrets.",
                )
                return
        except Exception as e:
            messagebox.showerror(
                "Secrets non configurés",
                f"{e}\n\nOuvrez l'onglet Configuration pour en choisir un.",
            )
            return

        self._cancel_event = threading.Event()
        self.progress["value"] = 0
        self.eta_var.set("Démarrage…")
        self.run_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self._append_log(f"Lancement sur {inp.name} → {out.name}")
        self._append_log(
            f"Config : {cfg_file}" if cfg_file is not None else "Config : intégrée (par défaut)"
        )

        if self._log_handler is None:
            self._log_handler = _TextHandler(self.log_text)
            logging.getLogger("gateway_llm").addHandler(self._log_handler)

        def _progress_cb(current: int, total: int, speed: float) -> None:
            self.after(0, self._update_progress, current, total, speed)

        def worker() -> None:
            try:
                from gateway_llm.batch import BatchRunner
                from gateway_llm.config import load_config
                from gateway_llm.hardware import detect_hardware
                from gateway_llm.logging import configure as configure_logging

                configure_logging(level="INFO")

                self.after(0, self._append_log, "Chargement de la config…")
                config = load_config(cfg_file)
                hw = detect_hardware()
                self.after(
                    0,
                    self._append_log,
                    f"VRAM={hw.vram_gb or '?'} Go, "
                    f"RAM dispo={hw.ram_available_gb or '?'} Go, "
                    f"disque={hw.disk_free_gb or '?'} Go",
                )
                runner = BatchRunner(
                    config=config,
                    input_path=inp,
                    output_path=out,
                    hardware=hw,
                    max_cost_eur=max_cost,
                    progress_callback=_progress_cb,
                )
                runner._cancel_event = self._cancel_event
                runner.run()
                self.after(0, self._on_success, out)
            except Exception as e:
                self.after(0, self._on_error, e)

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _on_success(self, output: pathlib.Path) -> None:
        self.progress["value"] = 100
        self.eta_var.set("Terminé")
        self.run_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self._append_log(f"✅ Terminé : {output}")
        if self._on_success_cb is not None:
            self._on_success_cb(output)
        messagebox.showinfo("Terminé", f"Traitement terminé.\nRésultats dans :\n{output}")

    def _on_error(self, exc: Exception) -> None:
        self.eta_var.set("Erreur")
        self.run_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self._append_log(f"❌ {exc}")
        messagebox.showerror("Erreur", f"Le traitement a échoué :\n{exc}")


# ─── Onglet 3 : Visualisation des résultats ────────────────────
class ResultsTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=20)
        self._results: list[dict] = []
        self._last_mtime: float = 0.0
        self._auto_path: pathlib.Path | None = None
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Fichier de résultats (.jsonl) :").pack(side="left")
        self.file_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.file_var).pack(
            side="left", fill="x", expand=True, padx=(8, 8)
        )
        ttk.Button(top, text="Parcourir…", command=self._pick).pack(side="left", padx=(0, 4))
        ttk.Button(top, text="Charger", command=self._load).pack(side="left")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # ─── Résumé ─────────────────────────────────────────────
        self.summary_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.summary_frame, text="Résumé")

        sum_frame = ttk.Frame(self.summary_frame)
        sum_frame.pack(fill="both", expand=True)
        self.summary_text = tk.Text(sum_frame, wrap="word", state="disabled")
        sum_scroll = ttk.Scrollbar(sum_frame, orient="vertical", command=self.summary_text.yview)
        self.summary_text.pack(side="left", fill="both", expand=True)
        sum_scroll.pack(side="right", fill="y")
        self.summary_text.config(yscrollcommand=sum_scroll.set)

        # ─── À revoir ───────────────────────────────────────────
        self.review_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.review_frame, text="À revoir")

        rev_frame = ttk.Frame(self.review_frame)
        rev_frame.pack(fill="both", expand=True)

        self.review_list = tk.Listbox(rev_frame)
        self.review_list.pack(fill="both", expand=True, side="left")
        list_scroll = ttk.Scrollbar(rev_frame, orient="vertical", command=self.review_list.yview)
        list_scroll.pack(side="right", fill="y")
        self.review_list.config(yscrollcommand=list_scroll.set)
        self.review_list.bind("<<ListboxSelect>>", self._on_review_select)

        self.detail_frame = ttk.Frame(self.review_frame, padding=10)
        self.detail_frame.pack(fill="both", expand=True, padx=(10, 0))

        det_frame = ttk.Frame(self.detail_frame)
        det_frame.pack(fill="both", expand=True)
        self.detail_text = tk.Text(det_frame, wrap="word", state="disabled")
        det_scroll = ttk.Scrollbar(det_frame, orient="vertical", command=self.detail_text.yview)
        self.detail_text.pack(side="left", fill="both", expand=True)
        det_scroll.pack(side="right", fill="y")
        self.detail_text.config(yscrollcommand=det_scroll.set)
        self._configure_tags(self.detail_text)

        btn_frame = ttk.Frame(self.detail_frame)
        btn_frame.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_frame, text="Accepter", command=self._accept).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Rejeter", command=self._reject).pack(side="left")

        # ─── Tout ───────────────────────────────────────────────
        self.all_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.all_frame, text="Tout")

        all_tree_frame = ttk.Frame(self.all_frame)
        all_tree_frame.pack(fill="both", expand=True)
        self.all_tree = ttk.Treeview(
            all_tree_frame,
            columns=("id", "domain", "model", "status", "cost"),
            show="headings",
            height=10,
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
        self.all_tree.pack(fill="both", expand=True, side="left")

        all_tree_scroll = ttk.Scrollbar(
            all_tree_frame, orient="vertical", command=self.all_tree.yview
        )
        all_tree_scroll.pack(side="right", fill="y")
        self.all_tree.config(yscrollcommand=all_tree_scroll.set)
        self.all_tree.bind("<<TreeviewSelect>>", self._on_all_select)

        self.all_detail_frame = ttk.Frame(self.all_frame, padding=10)
        self.all_detail_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.all_detail_text = tk.Text(
            self.all_detail_frame, wrap="word", state="disabled", height=8
        )
        all_det_scroll = ttk.Scrollbar(
            self.all_detail_frame,
            orient="vertical",
            command=self.all_detail_text.yview,
        )
        self.all_detail_text.pack(side="left", fill="both", expand=True)
        all_det_scroll.pack(side="right", fill="y")
        self.all_detail_text.config(yscrollcommand=all_det_scroll.set)
        self._configure_tags(self.all_detail_text)

    def _configure_tags(self, widget: tk.Text) -> None:
        widget.tag_configure("h1", font=("TkDefaultFont", 14, "bold"))
        widget.tag_configure("h2", font=("TkDefaultFont", 12, "bold"))
        widget.tag_configure("h3", font=("TkDefaultFont", 10, "bold"))
        widget.tag_configure("bold", font=("TkDefaultFont", 10, "bold"))
        widget.tag_configure("italic", font=("TkDefaultFont", 10, "italic"))
        widget.tag_configure("code", font=("Courier", 10), background="#f0f0f0")
        widget.tag_configure("codeblock", font=("Courier", 10), background="#f4f4f4")
        widget.tag_configure("quote", lmargin1=20, lmargin2=20, foreground="#666")

    def _render_markdown(self, widget: tk.Text, md_text: str) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")

        in_code = False
        for line in md_text.split("\n"):
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                widget.insert("end", line + "\n", "codeblock")
                continue
            if line.startswith("### "):
                widget.insert("end", line[4:] + "\n", "h3")
            elif line.startswith("## "):
                widget.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("# "):
                widget.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("> "):
                widget.insert("end", line[2:] + "\n", "quote")
            elif line.lstrip().startswith(("- ", "* ")):
                widget.insert("end", "  • " + line.lstrip()[2:] + "\n")
            else:
                self._insert_inline(widget, line + "\n")

        widget.config(state="disabled")

    def _insert_inline(self, widget: tk.Text, text: str) -> None:
        import re

        pattern = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")
        for part in pattern.split(text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**"):
                widget.insert("end", part[2:-2], "bold")
            elif part.startswith("*") and part.endswith("*"):
                widget.insert("end", part[1:-1], "italic")
            elif part.startswith("`") and part.endswith("`"):
                widget.insert("end", part[1:-1], "code")
            else:
                widget.insert("end", part)

    def start_auto_refresh(self, path: pathlib.Path) -> None:
        self._auto_path = path
        self.file_var.set(str(path))
        self._last_mtime = 0.0
        self._poll()

    def _poll(self) -> None:
        if self._auto_path is None:
            return
        try:
            mtime = self._auto_path.stat().st_mtime
            if mtime != self._last_mtime:
                self._last_mtime = mtime
                self._load()
        except FileNotFoundError:
            pass
        except Exception as e:
            log.debug("Poll échoué : %s", e)
        self.after(2000, self._poll)

    def _pick(self) -> None:
        p = filedialog.askopenfilename(filetypes=[("JSONL", "*.jsonl"), ("Tous", "*.*")])
        if p:
            self.file_var.set(p)
            self._auto_path = None
            self._load()

    def _load(self) -> None:
        raw = self.file_var.get().strip().strip('"').strip("'")
        if not raw:
            return
        path = pathlib.Path(raw)
        if path.is_dir():
            candidate = path / "results.jsonl"
            if candidate.exists():
                path = candidate
            else:
                return
        if not path.exists():
            return

        self._results = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return

        seen: dict[str, dict] = {}
        for r in self._results:
            rid = r.get("id")
            if rid:
                seen[rid] = r
        self._results = list(seen.values())
        self._refresh()

    def _refresh(self) -> None:
        total = len(self._results)
        approved = sum(1 for r in self._results if r.get("status") == "approved")
        review = sum(
            1
            for r in self._results
            if r.get("status") == "human_review" or r.get("guardrail_passed") is False
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

        self.review_list.delete(0, "end")
        for r in self._results:
            if r.get("status") == "human_review" or r.get("guardrail_passed") is False:
                rid = r.get("id", "?")
                reason = r.get("guardrail_reason", "—")
                self.review_list.insert("end", f"{rid}  —  {reason}")

        for item in self.all_tree.get_children():
            self.all_tree.delete(item)
        for r in self._results:
            self.all_tree.insert(
                "",
                "end",
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
            if r.get("status") == "human_review" or r.get("guardrail_passed") is False:
                if count == idx:
                    target = r
                    break
                count += 1
        if target is None:
            return
        header = (
            f"**ID :** `{target.get('id')}`\n"
            f"**Raison :** {target.get('guardrail_reason', '—')}\n\n"
            f"---\n\n"
        )
        self._render_markdown(
            self.detail_text, header + target.get("response", "_(pas de réponse)_")
        )

    def _on_all_select(self, _event) -> None:
        sel = self.all_tree.selection()
        if not sel:
            return
        item_id = sel[0]
        idx = self.all_tree.index(item_id)
        if 0 <= idx < len(self._results):
            target = self._results[idx]
            header = (
                f"**ID :** `{target.get('id')}`\n"
                f"**Modèle :** {target.get('model_used', '—')} | "
                f"**Statut :** {target.get('status', '—')}\n\n"
                f"---\n\n"
            )
            self._render_markdown(
                self.all_detail_text,
                header + target.get("response", "_(pas de réponse)_"),
            )

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
            if r.get("status") == "human_review" or r.get("guardrail_passed") is False:
                if count == idx:
                    target = r
                    break
                count += 1
        if target is None:
            return

        decisions_path = pathlib.Path("decisions.jsonl")
        with decisions_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": target.get("id"), "decision": decision}) + "\n")
        messagebox.showinfo(
            "Enregistré",
            f"Décision '{decision}' enregistrée pour {target.get('id')}",
        )


# ─── Onglet Configuration des secrets ──────────────────────────
class SecretsTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=20)
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self,
            text="Coffre-fort de secrets",
            font=("", 12, "bold"),
        ).pack(anchor="w", pady=(0, 12))

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
                self,
                text=label,
                variable=self.backend_var,
                value=val,
            ).pack(anchor="w", pady=2)

        self.options_frame = ttk.Frame(self)
        self.options_frame.pack(fill="x", pady=(12, 12))

        ttk.Button(
            self,
            text="Enregistrer la configuration",
            command=self._save,
        ).pack(pady=8)
        ttk.Button(self, text="Tester la connexion", command=self._test).pack(pady=4)

        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, foreground="gray").pack(
            anchor="w", pady=(8, 0)
        )

    def _save(self) -> None:
        from gateway_llm.secrets import save_backend_config

        backend = self.backend_var.get()
        options: dict[str, str] = {}
        save_backend_config(backend, options)
        self.status_var.set(f"✅ Backend '{backend}' enregistré.")

    def _test(self) -> None:
        try:
            from gateway_llm.secrets import get_backend

            b = get_backend()
            ok = b.is_available()
            if ok:
                self.status_var.set(f"✅ {b.name} : opérationnel")
            else:
                reason = getattr(b, "_error", None) or "raison inconnue"
                self.status_var.set(f"⚠ {b.name} : non disponible — {reason}")
        except Exception as e:
            self.status_var.set(f"❌ {e}")


# ─── Application principale ────────────────────────────────────
class App(_TkBase):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.title("gateway-llm — Traitement par lot")
        self.geometry("950x700")

        self.status_var = tk.StringVar(value="Prêt")
        self.status_bar = ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken")
        self.status_bar.pack(side="bottom", fill="x")

        mode_file = pathlib.Path.home() / ".gateway-llm" / "config.yaml"
        if not mode_file.exists():
            dialog = ModeDialog(self)
            self.wait_window(dialog)

        self._ensure_playwright_async()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.secrets_tab = SecretsTab(notebook)
        notebook.add(self.secrets_tab, text="Configuration")

        self.prepare_tab = PrepareTab(notebook)
        notebook.add(self.prepare_tab, text="1. Préparer les données")

        self.results_tab = ResultsTab(notebook)

        def _on_batch_done(output: pathlib.Path) -> None:
            self.results_tab.start_auto_refresh(output)
            notebook.select(self.results_tab)

        self.run_tab = RunTab(notebook, on_success=_on_batch_done)
        notebook.add(self.run_tab, text="2. Lancer le traitement")

        notebook.add(self.results_tab, text="3. Voir les résultats")

        if _DND_AVAILABLE and DND_FILES is not None:
            try:
                lb: Any = self.prepare_tab.paths_listbox
                lb.drop_target_register(DND_FILES)
                lb.dnd_bind("<<Drop>>", self.prepare_tab._on_drop)
            except Exception as e:
                log.info("Activation drag & drop échouée : %s", e)

        secrets_file = pathlib.Path.home() / ".gateway-llm" / "secrets.yaml"
        if not secrets_file.exists():
            notebook.select(self.secrets_tab)
            messagebox.showinfo(
                "Configuration requise",
                "Avant de commencer, choisissez où stocker vos clés API "
                "dans l'onglet Configuration.",
            )

    def _ensure_playwright_async(self) -> None:
        def worker() -> None:
            try:
                from playwright.sync_api import sync_playwright  # noqa: F401, type: ignore[import-not-found]
            except ImportError:
                log.info("Playwright non installé, scraping utilisera l'API de secours")
                self.after(
                    0,
                    self.status_var.set,
                    "Playwright absent (fallback API pour le catalogue Ollama)",
                )
                return

            self.after(0, self.status_var.set, "Vérification de Chromium (Playwright)…")

            if _playwright_chromium_ok():
                self.after(0, self.status_var.set, "Chromium (Playwright) : prêt")
                return

            self.after(
                0,
                self.status_var.set,
                "Installation de Chromium (Playwright) — quelques minutes…",
            )
            ok = _install_playwright_chromium()
            if ok:
                self.after(
                    0,
                    self.status_var.set,
                    "Chromium (Playwright) installé",
                )
            else:
                self.after(
                    0,
                    self.status_var.set,
                    "⚠ Installation Chromium échouée (fallback API)",
                )

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
