# Guide d'utilisation de l'application gateway-llm

## À quoi sert cette application ?

L'application gateway-llm traite automatiquement un grand nombre de tâches en utilisant des modèles d'intelligence artificielle. Vous fournissez des données (images, textes, fichiers CSV, URLs) et une consigne. L'application sélectionne le modèle adapté, vérifie la qualité de chaque réponse et produit un rapport complet.

## Ce que vous voyez à l'ouverture

L'application s'ouvre en tapant `python -m gateway_llm.gui` dans un terminal, ou en double-cliquant sur le raccourci si vous en avez un.

Une fenêtre s'affiche avec quatre onglets :

- **Configuration**
- **Préparer les données**
- **Lancer le traitement**
- **Voir les résultats**

Au premier lancement, l'onglet **Configuration** s'ouvre automatiquement, parce qu'il faut indiquer à l'application où sont stockées vos clés d'accès aux services d'IA. Une fois cette étape faite, elle n'est plus demandée.

## 1. Configuration (première fois uniquement)

L'application a besoin d'accéder à des services d'IA externes ou à des modèles installés sur votre machine. Ces services demandent des clés d'accès. Ces clés doivent être stockées dans un endroit sécurisé, jamais dans un fichier texte visible.

L'onglet Configuration propose plusieurs options :

- **PowerShell Vault** — la solution recommandée sur Windows. Les clés sont stockées dans le gestionnaire de secrets intégré à Windows.
- **1Password** — si vous utilisez déjà ce gestionnaire de mots de passe.
- **HashiCorp Vault, AWS Secrets Manager, Azure Key Vault** — si votre entreprise utilise l'un de ces services.
- **Variables d'environnement** — déconseillé, car non chiffré.

Choisissez l'option adaptée à votre situation. Cliquez sur **Enregistrer la configuration**, puis sur **Tester la connexion** pour vérifier que tout fonctionne. L'application vous indique alors si les clés sont bien accessibles.

## 2. Préparer les données

Cet onglet transforme vos fichiers en une liste de tâches que l'application sait traiter.

- **Type de source** : sélectionnez ce que vous voulez traiter.
  - Dossier d'images (screenshots, graphiques, tableaux)
  - Dossier de fichiers texte
  - Fichier CSV
  - Liste d'URLs
- **Emplacement** : cliquez sur **Parcourir** et sélectionnez votre dossier ou fichier.
- **Colonne CSV** : à remplir uniquement si vous avez choisi un fichier CSV. Indiquez le nom de la colonne qui contient le texte à traiter.
- **Consigne** : ce que vous demandez au modèle. Pour un dossier d'images, la consigne par défaut est « Analyse cette image et décris ce que tu vois ». Pour extraire des chiffres d'un graphique, remplacez par « Extrais les chiffres clés de ce graphique ».
- **Fichier de sortie** : indiquez où sauvegarder la liste des tâches (extension `.jsonl`).

Cliquez sur **Générer le fichier de tâches**. Un message confirme le nombre de tâches préparées.

## 3. Lancer le traitement

Cet onglet envoie les tâches aux modèles d'IA.

- **Fichier d'entrée** : sélectionnez le fichier `.jsonl` préparé à l'étape précédente.
- **Fichier de résultats** : indiquez où sauvegarder les réponses.
- **Configuration** : sélectionnez le fichier `config/models.yaml` fourni avec l'application. Il contient la liste des modèles disponibles et les règles de sélection.
- **Budget maximal** : optionnel. Indiquez un montant en euros pour que l'application s'arrête si le coût dépasse ce plafond.

Cliquez sur **Lancer le traitement**. Une barre de progression indique l'avancement. Selon la quantité de tâches et les modèles utilisés, le traitement peut prendre de quelques minutes à plusieurs heures.

Si le traitement est interrompu (coupure, fermeture de la fenêtre), relancez-le avec le même fichier de résultats : l'application reprend là où elle s'était arrêtée.

## 4. Voir les résultats

Cet onglet affiche ce qui a été produit.

- **Résumé** : nombre de tâches approuvées, à revoir, échouées, coût total, répartition par modèle.
- **À revoir** : liste des tâches dont la réponse n'a pas passé le contrôle automatique de qualité. Chaque ligne montre l'identifiant de la tâche et la raison du signalement. Cliquez sur une ligne pour voir la réponse produite et décider : **Accepter** ou **Rejeter**.
- **Tout** : liste complète des tâches avec leur statut, le modèle utilisé et le coût.

## Que faire en cas de signalement ?

Ouvrez l'onglet **À revoir**. Chaque signalement indique pourquoi la réponse a été jugée incertaine : « chiffre incohérent avec la source », « hallucination suspectée », « citation non vérifiée ».

Lisez la réponse produite, comparez-la au document ou à l'image d'origine, puis décidez : **Accepter** (la réponse est validée, elle rejoint les résultats définitifs) ou **Rejeter** (la réponse est écartée).

C'est le seul moment où votre jugement personnel est requis. Toutes les autres tâches sont traitées automatiquement.

## Traiter des screenshots et des images

L'application peut analyser des images : captures d'écran, graphiques financiers, tableaux de bord, documents scannés.

Pour cela :

1. Dans l'onglet **Préparer les données**, choisissez **Dossier d'images**.
2. Sélectionnez le dossier qui contient vos images (formats supportés : `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`).
3. Adaptez la consigne : par exemple « Extrais le chiffre d'affaires trimestriel et la marge opérationnelle affichés sur ce graphique ».
4. Cliquez sur **Générer le fichier de tâches**, puis lancez le traitement normalement.

**Point important concernant la confidentialité** : si vos images contiennent des données sensibles (chiffres non publics, informations personnelles, identifiants visibles), ouvrez l'onglet Configuration avant de lancer le traitement et vérifiez que la sensibilité par défaut est bien `confidential`. Cela garantit que les images seront traitées uniquement par un modèle local, sans envoi sur Internet.

## Ce que vous n'avez pas à faire

- Écrire manuellement des fichiers de configuration.
- Comprendre le fonctionnement interne des modèles d'IA.
- Choisir quel modèle utiliser : l'application le fait automatiquement selon la nature de chaque tâche.
- Installer des composants techniques : la personne qui a installé l'application s'en est chargée une fois.

## Besoin d'aide

- Pour vérifier que tout est en place : `gateway-llm doctor --config config/models.yaml` dans un terminal.
- Pour installer les modèles locaux manquants : `gateway-llm setup --config config/models.yaml`.
- Pour les aspects techniques : consulter le fichier `README.md`.
- Si une erreur apparaît, elle indique en général la cause. Les problèmes les plus courants sont : un modèle manquant, un fichier introuvable, ou un manque d'espace disque.