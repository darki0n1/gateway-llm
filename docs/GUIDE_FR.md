# Guide d'utilisation de l'application llm-gateway

## À quoi sert cette application ?

L'application llm-gateway vous permet de traiter automatiquement un grand nombre de tâches en utilisant des modèles d'intelligence artificielle. Vous fournissez vos données (images, textes, fichiers CSV, URLs) et une consigne. L'application choisit le modèle le plus adapté, vérifie la qualité de chaque réponse, et vous présente un rapport complet.

## Comment l'utiliser ?

### 1. Ouvrir l'application

Lancez l'application en tapant `python -m llm_gateway.gui` dans un terminal, ou double-cliquez sur le raccourci si vous en avez un.

Une fenêtre s'ouvre avec trois onglets.

### 2. Préparer vos données (onglet « Préparer les données »)

- **Type de source** : choisissez ce que vous voulez traiter (dossier d'images, dossier de fichiers texte, fichier CSV, ou liste d'URLs).
- **Emplacement** : cliquez sur « Parcourir » et sélectionnez votre dossier ou fichier.
- **Consigne** : laissez la consigne par défaut ou adaptez-la (par exemple « Extrais les chiffres clés de ce graphique »).
- **Fichier de sortie** : indiquez où sauvegarder le fichier de tâches (format `.jsonl`).
- Cliquez sur « Générer le fichier de tâches ». Un message confirme le nombre de tâches créées.

### 3. Lancer le traitement (onglet « Lancer le traitement »)

- **Fichier d'entrée** : sélectionnez le fichier `.jsonl` que vous venez de créer.
- **Fichier de résultats** : indiquez où sauvegarder les résultats.
- **Configuration** : sélectionnez le fichier `config/models.yaml` (fourni avec l'application).
- **Budget maximal** : optionnel, en euros. L'application s'arrête si le coût estimé dépasse ce montant.
- Cliquez sur « Lancer le traitement ». Une barre de progression affiche l'avancement.

### 4. Consulter les résultats (onglet « Voir les résultats »)

- **Résumé** : le nombre de tâches approuvées, à revoir, échouées, le coût total, et la répartition par modèle.
- **À revoir** : une liste des tâches dont la réponse n'a pas passé le contrôle qualité. Pour chacune, vous voyez la réponse produite, la raison du signalement, et deux boutons : « Accepter » ou « Rejeter ».
- **Tout** : la liste complète des tâches avec leur statut.

## Que faire en cas de signalement ?

Ouvrez l'onglet « À revoir ». Chaque ligne correspond à une tâche dont la réponse est jugée incertaine. Lisez la réponse et la raison (« chiffre incohérent », « hallucination suspectée », etc.). Décidez : acceptez la réponse, ou rejetez-la. Votre décision est enregistrée.

## Besoin d'aide ?

- Lancez `llm-gateway doctor --config config/models.yaml` pour vérifier que tout est en place.
- Consultez le `README.md` pour les aspects techniques.
- En cas de problème, vérifiez que le fichier `config/models.yaml` existe et que les modèles Ollama recommandés sont installés (`llm-gateway setup --config config/models.yaml`).