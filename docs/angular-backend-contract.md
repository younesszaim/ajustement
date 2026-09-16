# Contrat de collaboration Angular–backend

## 1. Objectif

Ce document permet de développer le frontend Angular sans attendre l'implémentation finale du backend. Il part du parcours actuellement validé dans Streamlit, mais définit une API cible stable et versionnée sous `/api/v1`.

Le backend reste libre pour son architecture interne. En revanche, les routes, DTO, enums, erreurs et règles métier décrits ici constituent le contrat partagé.

Fichiers associés :

- [`contracts/limon-adjustment-v1.openapi.yaml`](contracts/limon-adjustment-v1.openapi.yaml) : contrat OpenAPI cible ;
- [`contracts/limon-adjustment-v1.examples.json`](contracts/limon-adjustment-v1.examples.json) : données de mock Angular.

## 2. Correspondance avec l'application Streamlit actuelle

| Besoin Angular | API cible | Route FastAPI actuelle | Écart à traiter |
|---|---|---|---|
| Dates disponibles | `GET /api/v1/contexts/asofdates` | `GET /contexts/asofdates` | Ajouter préfixe/version |
| Versions | `GET /api/v1/contexts/versions` | identique sans `/api/v1` | Aucun changement de payload |
| FO systems | `GET /api/v1/contexts/fo-systems` | identique sans `/api/v1` | Aucun changement de payload |
| Configuration UI | `GET /api/v1/adjustment-definition` | absent | Exposer le YAML métier |
| Recherche | `POST /api/v1/trades/search` | `GET /trades` | POST, filtres et pagination typés |
| Lignée | `GET /api/v1/trades/{id}/lineage` | incluse dans les résultats selon le store | Route dédiée |
| Preview | `POST /api/v1/adjustment-previews` | `POST /adjustments/preview-jobs` | Nom stable et DTO typé |
| Progression | `GET /api/v1/adjustment-previews/{id}` | `GET /adjustments/preview-jobs/{id}` | Persistance à préciser |
| Commit | `POST /api/v1/adjustments` | `POST /adjustments/commit` | Cible fondée sur `previewId` |
| Cancel | `POST /api/v1/cancellations` | `POST /adjustments/cancel` | Renommage |
| Registre | `GET /api/v1/operations` | `GET /adjustments` | Filtres et pagination |
| Review | `GET /api/v1/operations/{id}` | absent | Ajouter détail persistant |
| Revert | `POST /api/v1/operations/{id}/reverts` | `POST /adjustments/{id}/revert` | Renommage |

L'API existante peut continuer à fonctionner durant la migration. Angular doit toutefois consommer uniquement `/api/v1` pour ne pas dépendre de routes historiques.

## 2.1 Couverture par rapport à l'ancienne application React

Le premier draft du contrat couvrait le parcours Streamlit simplifié, mais pas
toute l'ancienne application React. La version courante du contrat ajoute les
capacités nécessaires à une maquette Angular à parité fonctionnelle.

| Fonction React | Données nécessaires au mock | Contrat v1 |
|---|---|---|
| Contexte date/version/FO/leg | listes de valeurs et contexte | Couvert |
| Find a trade + pagination | lignes, total, page, configuration des colonnes | Couvert |
| Selected trade | détail et lignée ordonnée | Couvert |
| Historique du trade | opérations filtrées par ligne/trade | Couvert via `/operations` |
| Ajustement unitaire | champs contrôlés, impact, preview et commit | Couvert |
| Progression des calculs | pipeline, étapes et statuts | Couvert |
| Cancel trade | preview reversal seul puis commit | Couvert |
| Proxy/new trade | formulaire, preview, IDs générés et commit | Couvert |
| Batch multi-trades | recherche, sélection, preview agrégé et commit | Couvert |
| Registre global | filtres, pagination, review et liens de revert | Couvert |
| Revert | éligibilité, preview de l'effet et commit | Couvert |
| Reconciliation required | statut, diagnostic et retry | Couvert |
| Ancienne consultation des mappings | table de mapping | Hors périmètre volontairement |
| SSO et rôles | utilisateur, rôles et permissions | Hors périmètre actuel à décider |

Pour une démonstration Angular, toutes les lignes marquées `Couvert` peuvent
être développées intégralement contre les mocks. SSO ne doit pas être inventé :
il faut décider avec l'équipe si un gateway fournit l'identité ou si l'API doit
exposer `/me`.

## 3. Décisions à faire valider par les deux équipes

### Identifiants et formats

- tous les identifiants sont des chaînes opaques ;
- les dates utilisent `YYYY-MM-DD` ;
- les timestamps utilisent ISO 8601 avec fuseau ;
- les montants JSON sont des nombres, jamais des chaînes formatées ;
- `legFlag` vaut `0` pour Cash et `1` pour Security ;
- les enums utilisent les valeurs exactes du contrat.

### Modèle de ligne

Les métadonnées stables sont séparées des colonnes métier :

```json
{
  "outputRecordId": "OUT-123",
  "tradeId": "TRADE-456",
  "recordType": "ADJUSTED",
  "active": true,
  "instrumentType": "SEC",
  "adjustmentReference": "ADJ-789",
  "sourceOutputRecordId": "OUT-100",
  "parentOutputRecordId": "OUT-100",
  "values": {
    "isinCode": "FR0000000001",
    "securityAmountEur": 1500000
  }
}
```

Angular manipule les clés sémantiques de `values`. Les noms physiques Vertica restent dans la configuration backend.

### Source de vérité

- Angular ne calcule jamais un reversal.
- Angular ne recalcule jamais les enrichissements LiMon.
- Le backend détermine la ligne active.
- Le backend garantit que preview et commit reposent sur le même constructeur.
- Le commit référence le `previewId` affiché par Angular.
- Une clé d'idempotence correspond à une intention exacte et ne peut pas être réutilisée avec un autre contenu.

## 4. Parcours Angular prévu

### Initialisation

1. Charger `adjustment-definition`.
2. Charger les as-of dates.
3. Une date sélectionnée charge les versions.
4. Une version sélectionnée charge les FO systems.
5. Un changement de contexte efface recherche, sélection, brouillon et preview.

### Recherche et sélection

1. Envoyer le contexte, les filtres, la page et la taille à `trades/search`.
2. Construire AG Grid depuis `adjustment-definition.searchFields` et `displayFields`.
3. Sélectionner uniquement une ligne marquée `active=true`.
4. Charger sa lignée lorsque l'utilisateur ouvre `Selected trade`.

### Ajustement

1. Générer le formulaire depuis `editableFields`.
2. Envoyer uniquement les changements réels.
3. Créer un preview asynchrone.
4. Poller le preview tant qu'il est `PENDING` ou `RUNNING`.
5. Afficher Original, Reversal, Adjusted et les différences.
6. Après confirmation, committer ce `previewId` avec une clé d'idempotence.

### Batch multi-trades

1. Utiliser la même recherche paginée avec un FO system obligatoire.
2. Conserver la sélection entre les pages côté Angular.
3. Autoriser des changements propres à chaque ligne sélectionnée.
4. Envoyer tous les items dans un seul batch preview.
5. Présenter le nombre de trades, les lignes créées et les deltas agrégés.
6. Confirmer le `batchPreviewId` avec une seule clé d'idempotence.

### Proxy trade

1. Charger la définition des champs proxy depuis la configuration.
2. Envoyer un `draftId` stable pendant toute l'édition.
3. Laisser le backend générer le trade ID et l'output record ID.
4. Prévisualiser la ligne proxy recalculée avant son commit.

### Réconciliation

1. Une opération `RECONCILIATION_REQUIRED` reste visible dans le registre.
2. La review expose son diagnostic et les lignes éventuellement déjà écrites.
3. Le bouton retry appelle la route de réconciliation, pas le commit original.
4. Angular recharge ensuite l'opération pour afficher le statut final.

### Audit

1. Charger le registre paginé.
2. Ouvrir une opération via son identifiant.
3. N'afficher Revert que si `revertAllowed=true`.
4. Après revert, recharger le détail et le registre.

## 5. Gestion uniforme des erreurs

Toutes les erreurs `/api/v1` doivent respecter :

```json
{
  "error": {
    "code": "SOURCE_ROW_NO_LONGER_ACTIVE",
    "message": "The selected row is no longer active.",
    "field": null,
    "retryable": false,
    "correlationId": "REQ-123",
    "details": {}
  }
}
```

Codes minimaux :

| Code | HTTP | Réaction Angular |
|---|---:|---|
| `VALIDATION_ERROR` | 422 | Marquer le champ ou formulaire |
| `SOURCE_ROW_NOT_FOUND` | 404 | Fermer la sélection et relancer la recherche |
| `SOURCE_ROW_NO_LONGER_ACTIVE` | 409 | Invalider preview et sélection |
| `UNSUPPORTED_INSTRUMENT_TYPE` | 409 | Bloquer preview et afficher le type |
| `CALCULATION_FAILED` | 409/500 | Conserver le brouillon et afficher l'étape |
| `PREVIEW_EXPIRED` | 409 | Demander un nouveau preview |
| `IDEMPOTENCY_CONFLICT` | 409 | Ne jamais générer automatiquement une nouvelle clé |
| `OUTPUT_WRITE_FAILED` | 503 | Afficher échec, autoriser retry si indiqué |
| `RECONCILIATION_REQUIRED` | 409 | Interdire un nouveau commit et orienter vers support |
| `DATA_STORE_UNAVAILABLE` | 503 | Afficher indisponibilité globale |

L'API Streamlit actuelle renvoie encore principalement `{"detail": "..."}`. La normalisation ci-dessus est donc un travail backend préalable au branchement Angular réel.

## 6. Règles d'évolution du contrat

Changements compatibles sans nouvelle version :

- ajout d'un champ de réponse optionnel ;
- ajout d'une valeur de configuration dynamique que l'UI sait ignorer ;
- ajout d'un endpoint indépendant.

Changements cassants nécessitant concertation ou `/api/v2` :

- renommage/suppression d'un endpoint ou champ ;
- changement de type ou de nullabilité ;
- ajout d'un champ obligatoire dans une requête existante ;
- changement de la signification d'un statut ou identifiant ;
- modification du mécanisme preview/commit ;
- passage synchrone/asynchrone sans période de compatibilité.

## 7. Workflow d'équipe recommandé

1. Le contrat OpenAPI est modifié avant le code backend ou Angular.
2. Frontend et backend approuvent la pull request du contrat.
3. Angular génère ses types et son client depuis le fichier validé.
4. Angular travaille avec les exemples mock tant que l'API n'est pas disponible.
5. Le backend ajoute des tests garantissant sa conformité au contrat.
6. Une CI détecte les changements OpenAPI incompatibles.
7. Une démonstration commune valide chaque parcours complet.
