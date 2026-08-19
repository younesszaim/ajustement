# Guide — ajouter des colonnes à LiMon Adjustment Manager

Ce guide décrit comment ajouter une colonne à la recherche, à la description
d'un trade, aux filtres ou au formulaire d'ajustement. Il s'applique au modèle
actuel : output dans `vertica_sim`, métadonnées dans `adjustment_meta`, API en
camelCase et noms physiques centralisés dans le dictionnaire sémantique.

## 1. Principe général

Une colonne traverse les couches suivantes :

```text
Colonne physique Vertica/PostgreSQL
    → backend/config/data_dictionary.yaml
    → adaptateur de stockage
    → réponse FastAPI
    → frontend/src/types.ts
    → AG Grid, description ou formulaire d'ajustement
```

Chaque nom a un rôle différent :

```yaml
business_line_code:
  api: businessLineCode
  db: BusinessLineCode
  label: Business line
  type: string
```

- `business_line_code` : identifiant sémantique interne stable ;
- `api` : nom JSON stable utilisé par React et FastAPI ;
- `db` : colonne physique dans l'output ;
- `label` : libellé utilisateur ;
- `type` : type métier utilisé par les adaptateurs et le frontend.

La propriété `parquet` n'est ajoutée que si une fonction d'enrichissement doit
lire une colonne dans une table de paramètres. Une colonne simplement stockée
ou affichée n'en a pas besoin.

## 2. Ajouter une colonne affichée dans Search Trade

Exemple : afficher `BusinessLineCode`.

### Étape 1 — Dictionnaire sémantique

Ajouter dans `backend/config/data_dictionary.yaml` :

```yaml
business_line_code:
  api: businessLineCode
  db: BusinessLineCode
  label: Business line
  type: string
```

Pour le simulateur PostgreSQL, le nom physique peut être normalisé :

```yaml
db: business_line_code
```

L'adaptateur Vertica de production pourra traduire ce champ vers le nom réel.

### Étape 2 — Schéma simulé

Si la colonne n'existe pas dans `vertica_sim.output_completude_table`, créer la
prochaine migration numérotée :

```sql
ALTER TABLE vertica_sim.output_completude_table
ADD COLUMN IF NOT EXISTS business_line_code text;
```

Ne jamais modifier une migration déjà appliquée.

### Étape 3 — Adaptateur backend

Vérifier que la requête lit la colonne (`SELECT o.*` ou sélection explicite).
L'adaptateur générique traduit ensuite les champs ayant une propriété `db` en
noms API. La réponse doit contenir :

```json
{"businessLineCode": "GMD"}
```

Ajouter une conversion explicite seulement si le type ou la sémantique le
nécessite.

### Étape 4 — Type frontend

Dans `frontend/src/types.ts` :

```ts
export interface Trade {
  businessLineCode: string;
}
```

### Étape 5 — Métadonnées générées

Exécuter :

```bash
make generate-fields
```

Ne jamais modifier `frontend/src/generated/fields.ts` manuellement.

### Étape 6 — Colonne AG Grid

Dans `searchGridColumns` de `frontend/src/App.tsx` :

```tsx
{
  field: "businessLineCode",
  headerName: fieldLabel("businessLineCode"),
  minWidth: 140,
}
```

Le header vient du dictionnaire, pas d'une chaîne dupliquée.

### Étape 7 — Vérifications

- tester `GET /api/trades` ;
- vérifier BASE, reversal et replacement ;
- vérifier les valeurs nulles et longues ;
- vérifier pagination et responsive ;
- exécuter `make check`.

## 3. Ajouter une colonne à la description Selected Trade

Après les étapes backend précédentes, ajouter le nom API dans la liste
`summary` de `frontend/src/App.tsx` :

```ts
const summary = [
  // ...
  "businessLineCode",
];
```

Vérifier que `GET /api/trades/{rowId}` contient le champ. Une valeur descriptive
non additive est recopiée dans la reversal et ne change que dans la replacement
si elle fait partie de l'ajustement.

## 4. Ajouter une colonne comme filtre

Afficher une colonne dans AG Grid ne rend pas automatiquement le backend
capable de la filtrer.

### Étape 1 — Liste blanche backend

Dans `backend/app/config.py` :

```python
BATCH_FILTER_FIELDS = {
    # ...
    "businessLineCode": {"type": "text"},
}
```

### Étape 2 — Repository et SQL

Ajouter le champ à la traduction des filtres. En production, filtrer dans la
requête Vertica :

```sql
WHERE BusinessLineCode ILIKE :business_line
```

Ne jamais charger un snapshot complet pour le filtrer dans React ou en mémoire.

### Étape 3 — Contrat TypeScript

```ts
export interface BatchTradeFilters {
  businessLineCode?: string;
}
```

### Étape 4 — AG Grid

```tsx
{
  field: "businessLineCode",
  headerName: fieldLabel("businessLineCode"),
  filter: "agTextColumnFilter",
}
```

### Étape 5 — Tests

Tester le nouveau filtre conjointement avec :

- `asofdate` ;
- `asofdateflow` ;
- FO system ;
- leg Cash/Titre ;
- pagination ;
- filtre inconnu retournant HTTP `422`.

## 5. Ajouter une colonne comme critère d'ajustement

Cette évolution nécessite une décision métier. Avant de coder, préciser :

1. valeur source ou calculée ;
2. texte libre ou liste contrôlée ;
3. étapes recalculées après modification ;
4. champ additif ou non ;
5. comportement de la reversal ;
6. fonction ou table de paramètres qui le consomme ;
7. champ réellement modifiable ou seulement contexte de sélection.

### 5.1 Champ modifiable simple

```yaml
business_line_code:
  api: businessLineCode
  db: BusinessLineCode
  label: Business line
  type: string
  editable: true
  starts: [reporting_lines]
```

`editable: true` alimente automatiquement `EDITABLE_FIELDS`. `starts` indique
la première étape de recalcul. Le graphe peut ensuite produire :

```text
reporting_lines → lcr_impacts → ldp_impacts
```

### 5.2 Champ additif

Ajouter `additive: true` uniquement pour une mesure sommable : montant, bucket,
impact ou réserve. Le service construit alors :

```text
BASE.amount = 100
REVERSAL.amount = -100
REPLACEMENT.amount = 120
```

Ne jamais rendre additifs les codes, dates, devises, classifications ou
reporting lines.

### 5.3 Liste contrôlée

Déclarer les valeurs dans `backend/app/project_config.py` :

```python
CONTROLLED_FIELD_OPTIONS = {
    A("business_line_code"): {
        "displayName": "Business line",
        "options": ("GMD", "DOD", "RPC"),
        "producerStage": "business_line",
        "downstreamStages": (
            "reporting_lines", "lcr_impacts", "ldp_impacts"
        ),
    }
}
```

Le frontend charge ces options via `GET /api/adjustment-options`. Le backend
les revalide pendant preview et commit.

### 5.4 Contexte immuable

Un contexte n'est pas un ajustement. Exemple actuel : `security_leg_flag`.

```text
Leg Cash/Titre sélectionné avant la recherche
    → filtre serveur
    → trade correspondant
    → seul CashAmount_EUR ou SecurityAmount_EUR est modifiable
```

Dans ce cas, ne pas mettre `editable: true` et refuser sa présence dans
`changes`. BASE, reversal et replacement conservent la même valeur de contexte.

### 5.5 Fonction de recalcul

Si une nouvelle étape est nécessaire :

1. créer une fonction DataFrame dans `backend/lib/enrichments/` ;
2. déclarer entrées et sorties dans `registry.py` ;
3. ajouter l'étape à `STAGE_DEPENDENCIES` ;
4. déclarer `starts` sur les champs déclencheurs ;
5. tester cardinalité, erreurs, résultats et métadonnées d'exécution.

Une fonction de règle reçoit seulement le DataFrame et le contexte. Une
fonction paramétrée reçoit en plus la table fournie par le manifest. React ne
recalcule aucune valeur métier.

### 5.6 Formulaires single et batch

Ajouter le champ à la configuration `editable` du workspace single, puis à la
configuration des champs du batch. Utiliser :

- `text` pour une valeur réellement libre ;
- `number` pour une mesure ;
- `date` pour une date ;
- `controlled` pour une liste fournie par `/api/adjustment-options`.

Toute modification doit invalider la preview et la clé de retry. Preview et
commit doivent continuer à utiliser le même builder backend.

### 5.7 Tests obligatoires

- champ accepté et champ interdit ;
- valeur contrôlée valide/invalide ;
- chemin de recalcul ;
- original, reversal et replacement ;
- négation des mesures additives ;
- preview identique au résultat du commit ;
- retry idempotent et version obsolète ;
- batch ;
- revert ;
- historique et lineage.

## 6. Checklists

### Affichage uniquement

```text
[ ] data_dictionary.yaml
[ ] migration si nécessaire
[ ] adaptateur DB → API
[ ] Trade dans types.ts
[ ] make generate-fields
[ ] AG Grid ou summary
[ ] tests API et UI
```

### Nouveau filtre

```text
[ ] étapes d'affichage
[ ] BATCH_FILTER_FIELDS ou paramètre de recherche
[ ] traduction repository/SQL
[ ] BatchTradeFilters et api.ts
[ ] filtre UI
[ ] test du scope date + version + FO + leg
```

### Nouveau champ ajustable

```text
[ ] étapes d'affichage
[ ] editable: true
[ ] additive uniquement si mesure sommable
[ ] starts et dépendances de calcul
[ ] options contrôlées si nécessaire
[ ] formulaires single et batch
[ ] validation backend
[ ] preview original/reversal/replacement
[ ] commit, retry, revert et lineage
[ ] make check
```

## 7. Commandes finales

```bash
make generate-fields
make check
git diff --check
```

Une colonne d'affichage est une évolution de présentation. Une colonne
ajustable est une évolution métier : elle doit toujours définir validation,
dépendances, recalcul, audit et comportement de reversal.
