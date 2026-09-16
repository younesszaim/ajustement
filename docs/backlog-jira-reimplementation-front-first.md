# Backlog Jira front-first — Réimplémentation de LiMon Adjustment Manager

## 1. Vision produit

Ce backlog reconstruit l'application à partir de ce que l'utilisateur doit voir et accomplir. L'architecture technique est introduite progressivement pour rendre chaque écran réellement fonctionnel.

L'utilisateur doit pouvoir :

1. définir le contexte LiMon dans lequel il travaille ;
2. rechercher et sélectionner une ligne active d'un trade ;
3. comprendre son historique et sa lignée ;
4. saisir les valeurs qu'il souhaite corriger ;
5. visualiser le résultat du recalcul avant toute écriture ;
6. confirmer puis enregistrer l'ajustement ;
7. annuler un trade sans créer de ligne ajustée ;
8. consulter et, si nécessaire, reverser une opération passée.

Le premier objectif n'est donc pas de « construire une API ». Il est de livrer successivement des parcours utilisateur démontrables, puis de brancher derrière eux les services nécessaires.

## 2. Principe métier à rendre visible

La table de sortie LiMon reste un journal append-only : aucune ligne métier n'est modifiée ou supprimée.

### Remplacement d'une ligne

```text
BASE active
  + REVERSAL, avec les montants opposés à la BASE
  + ADJUSTED, avec les valeurs demandées puis recalculées
  = nouvelle ligne ADJUSTED active
```

### Annulation d'une ligne

```text
BASE ou ADJUSTED active
  + REVERSAL, avec les montants opposés
  = aucune ligne active pour ce trade
```

### Revert d'un ajustement

Le revert ne supprime pas l'opération. Il ajoute les lignes compensatoires nécessaires et conserve l'opération initiale dans le registre avec l'état `REVERTED`.

### Règles à montrer dans l'interface

- `BASE`, `REVERSAL` et `ADJUSTED` sont toujours identifiables.
- La ligne actuellement active est clairement signalée.
- Preview et commit produisent exactement le même résultat métier.
- Le contexte `asofdate + version + FO system + leg flag` accompagne chaque recherche et chaque opération.
- Une nouvelle tentative identique ne doit jamais insérer les mêmes lignes une seconde fois.
- Une erreur d'écriture ou de recalcul est visible et ne doit jamais être présentée comme un succès.

## 3. Carte des écrans

| Écran ou zone | Question utilisateur | Action principale |
|---|---|---|
| En-tête et contexte | Sur quel arrêté suis-je ? | Choisir date, version, FO system et leg |
| Find a trade | Quelles lignes puis-je ajuster ? | Filtrer et sélectionner la ligne active |
| Selected trade | Quelle est la situation actuelle ? | Examiner détail, lignée et historique |
| Adjustment workspace | Que veux-je modifier ? | Renseigner les nouvelles valeurs et la justification |
| Calculation preview | Quel sera l'impact ? | Suivre le pipeline et comparer les trois lignes |
| Commit confirmation | Suis-je certain de l'écriture ? | Confirmer l'opération |
| Cancel trade | Veux-je neutraliser cette ligne ? | Confirmer la création du reversal seul |
| Adjustment register | Qu'est-ce qui a été passé ? | Filtrer, ouvrir, puis éventuellement revert |

## 4. Definition of Done commune

Chaque ticket d'écran est terminé lorsque :

- son état vide, chargé, en cours, réussi et en erreur est traité ;
- la navigation et les libellés peuvent être compris sans connaissance du code ;
- les données affichées viennent d'un contrat explicite, avec un fake avant le branchement réel ;
- les critères d'acceptation sont couverts par des tests Python ;
- les erreurs backend sont affichées à l'utilisateur ;
- aucun secret ni nom physique de colonne métier n'est codé dans l'écran ;
- la documentation et les exemples d'API concernés sont à jour.

Estimations indicatives : `S = 0,5–1 jour`, `M = 1–2 jours`, `L = 3–5 jours`.

---

# EPIC UX-A — Construire le parcours visible avec des données contrôlées

## LIMON-UX-001 — Créer le shell de l'application

**User story**
En tant qu'utilisateur, je veux identifier immédiatement l'application, l'environnement et la zone dans laquelle je travaille.

**À afficher**

- le titre `LiMon Adjustment Manager` ;
- un indicateur d'environnement ;
- deux onglets distincts : `Adjustment workspace` et `Adjustment register` ;
- une zone principale large adaptée aux tableaux ;
- un style minimaliste cohérent.

**Travaux**

1. Créer le package Streamlit et le point d'entrée `app.py`.
2. Construire les deux onglets sans logique métier.
3. Initialiser un état de session centralisé.
4. Ajouter des composants pour les états vide, chargement et erreur.
5. Brancher temporairement des données Python contrôlées derrière une interface fake clairement isolée.

**Critères d'acceptation**

- les deux espaces sont visibles simultanément comme onglets distincts ;
- un rerun Streamlit ne fait pas perdre l'onglet et le contexte courant ;
- aucune connexion à une base n'est présente dans `app.py`.

**Dépendances** : aucune. **Estimation** : S.

## LIMON-UX-002 — Afficher et verrouiller le contexte de travail

**User story**
En tant qu'utilisateur, je veux choisir exactement la population LiMon sur laquelle rechercher un trade.

**À afficher**

- un date picker pour `asofdate` ;
- une liste des versions disponibles pour la date choisie ;
- un choix de `FO system` ;
- un choix de `leg flag` : `0 — Cash` ou `1 — Security` ;
- un bouton `Search` et un bouton `Clear search` alignés avec les filtres.

**Comportement**

1. Une date recharge les versions disponibles.
2. Changer le contexte efface la sélection et le preview précédents.
3. Une recherche est impossible tant que le contexte obligatoire est incomplet.
4. Le contexte reste visible pendant tout l'ajustement.

**Contrat de données nécessaire**

- `GET /api/asofdates` ;
- `GET /api/versions?asofdate=...` ;
- liste configurable des FO systems et legs.

**Critères d'acceptation**

- aucune date ou version inexistante n'est inventée par l'interface ;
- `Clear search` remet l'écran dans un état vide cohérent ;
- les erreurs de chargement sont visibles.

**Dépendances** : LIMON-UX-001. **Estimation** : M.

## LIMON-UX-003 — Construire l'écran Find a trade

**User story**
En tant qu'utilisateur, je veux filtrer la population choisie et sélectionner la ligne à ajuster sans charger toute la table Vertica dans le navigateur.

**À afficher**

- des critères de recherche métier configurables ;
- une AG Grid avec les colonnes utiles ;
- des badges compacts pour `BASE`, `REVERSAL`, `ADJUSTED` et `ACTIVE` ;
- une sélection à une ligne ;
- le nombre de résultats et un message si la recherche est vide.

**Comportement**

1. Les filtres sont envoyés au serveur avec le contexte complet.
2. Une limite serveur protège Vertica.
3. Toutes les lignes de lignée du trade peuvent être consultées, mais seule la ligne active peut être ajustée.
4. L'ordre d'une lignée est `BASE → REVERSAL → ADJUSTED` pour chaque batch.
5. Un changement de contexte annule la sélection.

**Critères d'acceptation**

- aucun chargement global de la table de sortie n'est effectué ;
- une ligne d'un autre contexte ne peut pas être sélectionnée silencieusement ;
- les colonnes affichées sont configurées, pas codées dans la grille.

**Dépendances** : LIMON-UX-002. **Estimation** : L.

## LIMON-UX-004 — Construire la vue Selected trade

**User story**
En tant qu'utilisateur, je veux comprendre la ligne sélectionnée avant de prendre une décision.

**À afficher**

- l'identifiant du trade et de la ligne ;
- les principales caractéristiques métier ;
- les montants et champs ajustables ;
- le type d'instrument `OST`, `SEC` ou `EQUITY` ;
- la lignée complète et la ligne active ;
- les opérations passées sur ce trade ;
- un bouton pour fermer la sélection.

**Critères d'acceptation**

- les valeurs nulles restent distinguables des chaînes vides et des zéros ;
- committed et reverted sont présentés avec le même modèle visuel ;
- fermer la sélection ne modifie aucune donnée.

**Dépendances** : LIMON-UX-003. **Estimation** : M.

---

# EPIC UX-B — Rendre l'ajustement compréhensible

## LIMON-UX-010 — Construire l'Adjustment workspace

**User story**
En tant qu'utilisateur, je veux saisir une ou plusieurs corrections sur la ligne active sélectionnée.

**À afficher**

- un dialogue large ouvert depuis `Create adjustment` ;
- les champs ajustables organisés sur trois colonnes ;
- la valeur originale à proximité de chaque saisie ;
- des listes contrôlées pour les champs catégoriels ;
- des champs numériques pour les montants ;
- une justification obligatoire ;
- un bouton `Preview impact`.

**Comportement**

1. Seuls les champs définis dans la configuration sont éditables.
2. Plusieurs champs peuvent être modifiés dans la même opération.
3. Une valeur identique à l'original n'est pas considérée comme un changement.
4. Au moins un changement réel est obligatoire.
5. Les colonnes techniques ne sont jamais éditables.

**Critères d'acceptation**

- ajouter un champ configurable ne nécessite pas de modifier manuellement la disposition ;
- les valeurs sélectionnées restent présentes après les reruns Streamlit ordinaires ;
- le preview est désactivé lorsqu'un calcul est déjà en cours.

**Dépendances** : LIMON-UX-004. **Estimation** : L.

## LIMON-UX-011 — Expliquer le preview et le pipeline de calcul

**User story**
En tant qu'utilisateur, je veux comprendre quelles étapes sont exécutées et comparer le résultat avant de confirmer.

**À afficher**

- le pipeline choisi selon le type d'instrument ;
- la liste ordonnée de toutes les étapes ;
- l'étape courante, les étapes terminées et la progression globale ;
- les onglets `Original`, `Reversal` et `Adjusted` ;
- une synthèse des champs modifiés directement et recalculés indirectement ;
- les erreurs de calcul avec un message exploitable.

**Principe de calcul**

1. Le type d'instrument sélectionne strictement le pipeline `OST`, `SEC` ou `EQUITY`.
2. Le pipeline complet repart des colonnes d'entrée disponibles.
3. Les choix explicites de l'utilisateur sont réappliqués après chaque étape et ne sont pas écrasés.
4. La cardinalité du dataframe ne peut pas changer pendant un ajustement unitaire.
5. Un type absent ou non supporté bloque le preview.

**Critères d'acceptation**

- le bouton ne peut pas lancer deux jobs simultanés ;
- le résultat affiché est celui conservé pour le futur commit ;
- fermer ou modifier le formulaire invalide explicitement un ancien preview ;
- les trois lignes sont faciles à comparer.

**Dépendances** : LIMON-UX-010. **Estimation** : L.

## LIMON-UX-012 — Confirmer et suivre le commit

**User story**
En tant qu'utilisateur, je veux confirmer une écriture sensible et savoir sans ambiguïté si elle a réussi.

**À afficher**

- un dialogue récapitulatif au-dessus de l'espace d'ajustement ;
- le contexte, la ligne source, les changements et la justification ;
- `Cancel` et `Confirm commit` ;
- un écran bloquant/progressif pendant le commit ;
- un message final avec l'identifiant d'opération.

**Comportement**

1. Le commit utilise le brouillon exact ayant produit le preview.
2. Le backend relit la ligne active avant l'écriture.
3. Une clé d'idempotence stable protège des doubles clics et retries.
4. Un remplacement écrit exactement `REVERSAL + ADJUSTED`.
5. Les actions restent verrouillées jusqu'à la réponse finale.

**Critères d'acceptation**

- le dialogue de confirmation est au premier plan ;
- un double clic ne crée pas de doublon ;
- succès, échec Vertica et échec de confirmation PostgreSQL sont distingués ;
- un commit réussi actualise la lignée et le registre.

**Dépendances** : LIMON-UX-011. **Estimation** : L.

## LIMON-UX-013 — Ajouter Cancel trade

**User story**
En tant qu'utilisateur, je veux neutraliser l'effet d'une ligne active sans créer de remplacement.

**À afficher**

- un bouton rouge `Cancel trade` ;
- un dialogue décrivant clairement la création d'un reversal seul ;
- la ligne active concernée et la justification ;
- une confirmation explicite.

**Critères d'acceptation**

- aucune ligne `ADJUSTED` n'est créée ;
- les mesures additives du reversal sont opposées à la source ;
- l'opération apparaît dans le registre ;
- l'action est idempotente.

**Dépendances** : LIMON-UX-004, LIMON-UX-012. **Estimation** : M.

---

# EPIC UX-C — Donner une vision d'audit exploitable

## LIMON-UX-020 — Construire l'Adjustment register

**User story**
En tant qu'utilisateur, je veux une synthèse des ajustements passés et pouvoir retrouver une opération précise.

**À afficher**

- un filtre `All asofdates` ou une date choisie dans un calendrier ;
- des filtres version, FO system, statut et type d'opération ;
- une carte ou ligne de synthèse par opération, et non les lignes techniques empilées ;
- date/heure, auteur, contexte, trade, type, statut et justification ;
- les boutons `Review` et, lorsque permis, `Revert`.

**Critères d'acceptation**

- le registre global fonctionne sans charger toute la sortie Vertica ;
- une opération initiale et son revert sont visuellement reliés ;
- `COMMITTED`, `REVERTED`, `FAILED` et `RECONCILIATION_REQUIRED` sont distinguables ;
- seuls les états légalement réversibles affichent le bouton Revert.

**Dépendances** : LIMON-UX-012. **Estimation** : L.

## LIMON-UX-021 — Construire Review adjustment

**User story**
En tant qu'utilisateur, je veux ouvrir une opération dans un grand dialogue et comprendre exactement ce qu'elle a écrit.

**À afficher**

- le contexte et les métadonnées de l'opération ;
- les changements demandés ;
- le pipeline et sa version ;
- les lignes source, reversal et adjusted ;
- les identifiants de lignée ;
- l'éventuelle opération de revert liée.

**Critères d'acceptation**

- la review utilise les données persistées, pas le dernier état de session ;
- les différences métier sont mises en évidence ;
- le dialogue reste lisible sur un écran de travail standard.

**Dépendances** : LIMON-UX-020. **Estimation** : M.

## LIMON-UX-022 — Ajouter Revert adjustment

**User story**
En tant qu'utilisateur, je veux compenser un ajustement erroné tout en conservant une piste d'audit complète.

**À afficher**

- un bouton rouge `Revert` à côté de `Review` ;
- un dialogue d'avertissement ;
- l'opération ciblée, l'effet attendu et une justification ;
- la progression puis le résultat.

**Critères d'acceptation**

- aucune ligne existante n'est supprimée ou mise à jour ;
- le revert crée une nouvelle opération liée au commit initial ;
- une opération déjà reverted ne peut pas l'être une seconde fois ;
- le registre montre clairement le lien entre les deux opérations.

**Dépendances** : LIMON-UX-021. **Estimation** : L.

---

# EPIC TECH-D — Remplacer les fakes par le système réel

Ces tickets arrivent après validation des écrans. Ils ne changent pas le parcours utilisateur : ils remplacent les sources temporaires par les couches de production.

## LIMON-TECH-030 — Formaliser les contrats entre l'écran et l'API

Définir les modèles de contexte, recherche, draft, preview, commit, cancel, registre et revert. Ajouter exemples Swagger, codes d'erreur stables et tests de validation HTTP.

**Dépendances** : UX-A à UX-C. **Estimation** : M.

## LIMON-TECH-031 — Implémenter le catalogue de champs YAML

Déclarer les noms physiques, labels, champs affichés, filtres, champs ajustables, options, mesures additives et pipelines par type d'instrument. Les mêmes clés sémantiques doivent fonctionner pour Vertica réel et Supabase simulé.

**Dépendances** : LIMON-TECH-030. **Estimation** : M.

## LIMON-TECH-032 — Implémenter la lecture Vertica

Créer un repository paginé pour contextes, recherche, lignée, ligne active et contrôle des références. Aucun SQL ne doit remonter dans l'API ou Streamlit.

**Dépendances** : LIMON-TECH-031. **Estimation** : L.

## LIMON-TECH-033 — Implémenter le journal PostgreSQL

Créer l'unique table d'opérations avec clé d'idempotence, contexte, source, statut, payload JSON, identifiants écrits, erreurs et lien vers l'opération initiale.

**Dépendances** : LIMON-TECH-031. **Estimation** : L.

## LIMON-TECH-034 — Implémenter le service métier append-only

Centraliser validation, construction reversal/adjusted, relecture de la ligne active, commit idempotent, cancel, revert et réconciliation. Preview et commit doivent appeler le même constructeur.

**Dépendances** : LIMON-TECH-032, LIMON-TECH-033. **Estimation** : L.

## LIMON-TECH-035 — Brancher les pipelines complets par instrument

Configurer et appeler les pipelines globaux OST, SEC et EQUITY. Valider les colonnes d'entrée, préserver les champs ajustés, publier la progression et conserver le nom/version du pipeline dans l'opération.

**Dépendances** : LIMON-TECH-034. **Estimation** : L.

## LIMON-TECH-036 — Implémenter les jobs longs

Sortir les calculs longs du cycle de rerun Streamlit : création de job, polling, progression, résultat, expiration et reprise après rafraîchissement.

**Dépendances** : LIMON-TECH-035. **Estimation** : L.

## LIMON-TECH-037 — Qualifier Supabase puis Vertica/PostgreSQL

Tester d'abord le parcours complet sur les schémas simulés, puis effectuer la recette des types, transactions, performances, droits et reprises sur les bases réelles.

**Dépendances** : LIMON-TECH-036. **Estimation** : L.

---

# EPIC QA-E — Recette par scénarios utilisateur

## LIMON-QA-040 — Recetter un remplacement nominal

Rechercher une BASE active, modifier plusieurs champs, suivre tout le pipeline, comparer les trois lignes, confirmer, puis retrouver l'opération dans la lignée et le registre.

## LIMON-QA-041 — Recetter annulation et revert

Annuler une ligne active, vérifier le reversal seul, puis tester le revert d'un remplacement et les liens d'audit.

## LIMON-QA-042 — Recetter les erreurs et retries

Couvrir contexte périmé, ligne devenue inactive, type d'instrument absent, pipeline en erreur, timeout, double clic, retry identique, retry modifié, échec Vertica et confirmation PostgreSQL incomplète.

## LIMON-QA-043 — Recetter volumétrie et ergonomie

Mesurer recherche paginée, temps de preview, consommation mémoire, comportement des grands tableaux, lisibilité des dialogues et stabilité lors des reruns Streamlit.

---

## 5. Ordre recommandé de réalisation

```text
Démo du parcours
UX-001 → UX-002 → UX-003 → UX-004
       → UX-010 → UX-011 → UX-012 → UX-013
       → UX-020 → UX-021 → UX-022

Industrialisation derrière les écrans validés
TECH-030 → TECH-031 → TECH-032 + TECH-033
         → TECH-034 → TECH-035 → TECH-036 → TECH-037

Recette transverse
QA-040 → QA-041 → QA-042 → QA-043
```

## 6. Stratégie de livraison

- **Jalon 1 — Maquette interactive** : contexte, recherche, sélection et workspace sur fakes.
- **Jalon 2 — Démonstrateur métier** : preview, remplacement et annulation sur simulation Supabase.
- **Jalon 3 — Audit complet** : registre, review, revert et gestion des incidents.
- **Jalon 4 — Production** : Vertica, PostgreSQL, pipelines LiMon, volumétrie et exploitation.

Cette approche permet aux utilisateurs de valider très tôt les écrans et le principe d'ajustement. Elle évite de terminer plusieurs semaines de backend avant de découvrir que le parcours ou les informations affichées ne répondent pas au besoin.
