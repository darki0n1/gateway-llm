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

Au tout premier lancement, l'application vous pose d'abord une question sur le **mode d'exécution** (voir section suivante), puis ouvre l'onglet **Configuration** pour savoir où stocker vos clés d'accès aux services d'IA. Une fois ces deux étapes faites, elles ne sont plus demandées.

## 1. Mode d'exécution (premier lancement uniquement)

Avant la configuration des clés, l'application vous demande comment vous voulez l'utiliser. Ce choix détermine quels modèles seront utilisés et éventuellement téléchargés.

Une fenêtre s'ouvre avec quatre options :

- **100% cloud** — utilise uniquement les services d'IA en ligne (Groq, Mistral, OpenRouter, Google…). Aucun modèle n'est installé sur votre machine. Idéal si vous avez une bonne connexion et des clés API.
- **100% local** — télécharge les meilleurs modèles qui peuvent tourner sur votre machine, en fonction de sa mémoire et de son espace disque. Aucune donnée ne sort de votre ordinateur. Idéal pour la confidentialité.
- **Hybride** — utilise les modèles déjà présents sur votre machine, et complète avec le cloud quand un meilleur modèle en ligne est disponible. Meilleur compromis qualité/coût.
- **Défaut (recommandé)** — télécharge uniquement les quelques modèles légers nécessaires au fonctionnement de base de l'application (routage, classification). Vous pourrez toujours ajouter d'autres modèles plus tard.

Choisissez l'option qui correspond à votre usage, puis cliquez sur **Valider**. Vous pouvez changer d'avis plus tard en éditant le fichier `~/.gateway-llm/config.yaml` (demandez de l'aide si besoin).

**Astuce** : si vous ne savez pas quoi choisir, prenez **Défaut**. C'est le plus simple et le plus rapide à mettre en place.

## 2. Configuration des clés d'accès (premier lancement uniquement)

L'application a besoin d'accéder à des services d'IA externes ou à des modèles installés sur votre machine. Ces services demandent des clés d'accès. Ces clés doivent être stockées dans un endroit sécurisé, jamais dans un fichier texte visible.

L'onglet Configuration propose plusieurs options :

- **PowerShell Vault** — la solution recommandée sur Windows. Les clés sont stockées dans le gestionnaire de secrets intégré à Windows.
- **1Password** — si vous utilisez déjà ce gestionnaire de mots de passe.
- **HashiCorp Vault, AWS Secrets Manager, Azure Key Vault** — si votre entreprise utilise l'un de ces services.
- **Variables d'environnement** — déconseillé, car non chiffré.

Choisissez l'option adaptée à votre situation. Cliquez sur **Enregistrer la configuration**, puis sur **Tester la connexion** pour vérifier que tout fonctionne. L'application vous indique alors si les clés sont bien accessibles.

**Si vous êtes en mode 100% local**, vous pouvez ignorer cette étape : aucune clé API n'est nécessaire.

## 3. Préparer les données

Cet onglet transforme vos fichiers en une liste de tâches que l'application sait traiter.

- **Type de source** : sélectionnez ce que vous voulez traiter.
  - Dossier d'images (screenshots, graphiques, tableaux)
  - Dossier de fichiers texte
  - Fichier(s) CSV — un ou plusieurs, toutes les colonnes seront lues par le modèle
  - Liste d'URLs
  - **Mixte** — pour combiner images, textes et CSV en une seule fois
- **Emplacement(s)** : cliquez sur **Ajouter…** pour choisir vos fichiers ou dossiers. Vous pouvez en ajouter plusieurs. Le **glisser-déposer** fonctionne aussi : faites glisser vos fichiers depuis l'explorateur Windows vers la liste.
- **Retirer / Vider** : pour enlever un élément sélectionné ou tout vider.
- **Consigne** : ce que vous demandez au modèle. Par exemple :
  - Pour un dossier d'images : « Analyse cette image et décris ce que tu vois. »
  - Pour extraire des chiffres d'un graphique : « Extrais les chiffres clés de ce graphique. »
  - Pour un CSV : « Voici un tableau. Calcule le total de la recette. » (le modèle lit toutes les colonnes et choisit celles qui comptent)
  - En mode **Mixte** : « Avec ce tableau et ces KPI, détermine la bonne décision à prendre dans ce fichier texte. »
- **Fichier de sortie** : indiquez où sauvegarder la liste des tâches (extension `.jsonl`).

Cliquez sur **Générer le fichier de tâches**. Un message confirme le nombre de tâches préparées.

**Conseil pour les CSV** : plus besoin de choisir une colonne. L'application envoie **tout le tableau** au modèle, qui comprend seul quelles colonnes sont pertinentes pour votre consigne. Cela permet des questions comme « calcule le total de la recette » ou « quelle est la ligne avec le plus gros chiffre d'affaires » sans réglage supplémentaire.

## 4. Lancer le traitement

Cet onglet envoie les tâches aux modèles d'IA.

- **Fichier d'entrée** : sélectionnez le fichier `.jsonl` préparé à l'étape précédente.
- **Fichier de résultats** : indiquez où sauvegarder les réponses. Si vous laissez vide, un fichier `results.jsonl` sera créé à côté de votre fichier d'entrée.
- **Options avancées** (cachées par défaut, bouton « Afficher les options avancées ») :
  - **Configuration** : laissez vide pour utiliser la configuration intégrée. Utile seulement pour les utilisateurs avancés qui veulent un fichier de modèles personnalisé.
  - **Budget maximal** : optionnel. Indiquez un montant en euros pour que l'application s'arrête si le coût dépasse ce plafond.

Cliquez sur **Lancer le traitement**. Une barre de progression indique l'avancement, et une zone de **journal en direct** affiche tout ce qui se passe : chargement de la configuration, téléchargement éventuel de modèles, progression des tâches, coût cumulé, etc.

**Annuler** : si vous changez d'avis, cliquez sur le bouton **Annuler** à côté de « Lancer le traitement ». L'application termine la tâche en cours puis s'arrête proprement, sans perdre les résultats déjà produits.

Si le traitement est interrompu (coupure, fermeture de la fenêtre), relancez-le avec le même fichier de résultats : l'application reprend là où elle s'était arrêtée.

## 5. Voir les résultats

Cet onglet affiche ce qui a été produit. Après un traitement, **il s'ouvre automatiquement** avec le fichier de résultats déjà chargé et mis à jour toutes les 2 secondes pendant que le batch tourne.

- **Résumé** : nombre de tâches approuvées, à revoir, échouées, coût total.
- **À revoir** : liste des tâches dont la réponse n'a pas passé le contrôle automatique de qualité. Chaque ligne montre l'identifiant de la tâche et la raison du signalement. Cliquez sur une ligne pour voir la réponse produite (affichée en **Markdown** : titres, gras, listes, code, etc.) et décider : **Accepter** ou **Rejeter**.
- **Tout** : liste complète des tâches avec leur statut, le modèle utilisé et le coût.

## Que faire en cas de signalement ?

Ouvrez l'onglet **À revoir**. Chaque signalement indique pourquoi la réponse a été jugée incertaine : « chiffre incohérent avec la source », « hallucination suspectée », « citation non vérifiée ».

Lisez la réponse produite, comparez-la au document ou à l'image d'origine, puis décidez : **Accepter** (la réponse est validée, elle rejoint les résultats définitifs) ou **Rejeter** (la réponse est écartée).

C'est le seul moment où votre jugement personnel est requis. Toutes les autres tâches sont traitées automatiquement.

## Traiter des screenshots et des images

L'application peut analyser des images : captures d'écran, graphiques financiers, tableaux de bord, documents scannés.

Pour cela :

1. Dans l'onglet **Préparer les données**, choisissez **Dossier d'images** (ou **Mixte** si vous avez aussi du texte ou un CSV à combiner).
2. Ajoutez le dossier ou les fichiers qui contiennent vos images (formats supportés : `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`).
3. Adaptez la consigne : par exemple « Extrais le chiffre d'affaires trimestriel et la marge opérationnelle affichés sur ce graphique ».
4. Cliquez sur **Générer le fichier de tâches**, puis lancez le traitement normalement.

**Point important concernant la confidentialité** : si vos images contiennent des données sensibles (chiffres non publics, informations personnelles, identifiants visibles), choisissez le mode **100% local** ou **Hybride** et vérifiez que la sensibilité par défaut est bien `confidential`. Cela garantit que les images seront traitées uniquement par un modèle local, sans envoi sur Internet.

## Traiter un CSV avec plusieurs colonnes

L'application envoie **tout le tableau** (toutes les colonnes et toutes les lignes) au modèle, par lots de 500 lignes. Vous n'avez pas à choisir une colonne.

Quelques exemples de consignes qui fonctionnent :

- « Calcule le total de la recette en multipliant la colonne "prix" par la colonne "ventes". »
- « Résume les informations principales de ce tableau. »
- « Quelle ligne a le chiffre d'affaires le plus élevé ? »
- « Y a-t-il des valeurs incohérentes dans ce tableau ? »

**Plusieurs CSV** : vous pouvez ajouter plusieurs fichiers CSV en une seule fois. Chacun sera traité séparément, et les résultats seront concaténés dans le fichier de sortie.

## Combiner plusieurs types de fichiers (mode Mixte)

Si vous voulez qu'un même traitement prenne en compte une image, un fichier texte et un CSV, choisissez **Mixte** dans le type de source, puis ajoutez tous vos fichiers.

Exemple concret : vous avez un graphique (`kpi.png`), un rapport trimestriel (`rapport.txt`) et un tableau de ventes (`ventes.csv`). Vous écrivez la consigne suivante :

> « Avec ce tableau et ces KPI, détermine la bonne décision à prendre dans ce fichier texte. »

L'application va :
- envoyer l'image au modèle multimodal ;
- inclure le texte du rapport et le tableau CSV dans le prompt ;
- produire une réponse unique qui synthétise le tout.

## Ce que vous n'avez pas à faire

- Écrire manuellement des fichiers de configuration.
- Comprendre le fonctionnement interne des modèles d'IA.
- Choisir quel modèle utiliser : l'application le fait automatiquement selon la nature de chaque tâche et selon votre matériel.
- Installer des composants techniques : l'application télécharge elle-même les modèles locaux dont elle a besoin et, si nécessaire, Chromium pour ses outils internes.
- Télécharger des modèles à la main : c'est automatique en fonction de votre mode d'exécution.

## Besoin d'aide

- Pour vérifier que tout est en place : `gateway-llm doctor` dans un terminal.
- Pour installer les modèles locaux manquants : `gateway-llm setup`.
- Pour les aspects techniques : consulter le fichier `README.md`.
- Si une erreur apparaît dans le journal en direct, elle indique en général la cause. Les problèmes les plus courants sont : un modèle manquant (l'application le télécharge automatiquement), un fichier introuvable (vérifiez le chemin), ou un manque d'espace disque (les modèles prennent plusieurs gigaoctets).