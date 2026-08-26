# SRS — GROUPE LEPAD — Application web de gestion des stocks, ventes et distribution

## Module M00 — Vision, architecture et conventions transverses

| Champ | Valeur |
| --- | --- |
| Projet | Digitalisation de la gestion des stocks, ventes et distribution — GROUPE LEPAD |
| Nom de code applicatif | `lepad` |
| Document | Software Requirements Specification — Module M00 (cadrage) |
| Version | 1.1 |
| Source de référence | Cahier des charges fonctionnel et technique v1.0 (Eric José Sioténé, Directeur Général) |
| Destinataire | Équipe de développement / Claude Code |
| Statut | À valider par le Maître d'ouvrage |

### Modifications de la version 1.1

Décision du Maître d'ouvrage : **l'application est exclusivement web**. Trois retraits de périmètre en découlent et sont intégrés dans tout le document.

| Retrait | Conséquence |
| --- | --- |
| Application mobile native (Android / iOS) | Supprimée. Tous les écrans, y compris la vente et l'inventaire, sont des écrans web responsive utilisables sur smartphone, tablette et ordinateur. Plus de développement React Native / Expo, plus de notifications push, plus d'impression Bluetooth. |
| Mode hors-ligne et synchronisation différée | Supprimé. L'application exige une connexion réseau active. Plus de base locale, plus de file d'opérations, plus de résolution de conflits de synchronisation. L'ancien module M20 est supprimé et les modules suivants sont renumérotés (28 modules au total). |
| Liens avec des systèmes tiers | Supprimés. Aucune interface, API publique, connecteur ou synchronisation avec un système externe (logiciel comptable, opérateur mobile money, ERP, plateforme scolaire). Les données sortent uniquement sous forme de fichiers Excel/PDF téléchargés par l'utilisateur depuis l'application. |

> **Note de lecture pour Claude Code.** Ce document est normatif. Tout ce qui est écrit ici s'applique à **tous** les modules du SRS et ne sera pas répété dans les documents de module. En cas de contradiction entre un document de module et le présent document, le document de module l'emporte uniquement s'il déclare explicitement `DÉROGATION À M00`. Sinon, M00 fait foi.

---

## 1. Vision générale du projet

### 1.1 Objectif métier

GROUPE LEPAD (LEPAD GROUPE, RCCM CI-ABJ-2017-A-19145) distribue des fournitures scolaires en Côte d'Ivoire sous forme de **kits scolaires** définis par établissement et par niveau. L'activité repose aujourd'hui sur des supports papier (fiche de vente journalière, fiche d'inventaire, fiche de demande d'achat, bordereau de dépense, table de formation de kits, fiche de non-conformité).

L'application web doit remplacer intégralement ces supports par un système unique permettant :

1. la visibilité en temps réel du stock de chaque magasin et de chaque école ;
2. la fiabilisation de la chaîne inventaire → demande d'achat → validation → commande fournisseur → réception ;
3. la centralisation des kits par établissement et par niveau avec calculs automatiques ;
4. la traçabilité individuelle de chaque vente (vendeuse, école, mode de paiement) ;
5. le suivi des dépenses par site, par zone et au global ;
6. des tableaux de bord consolidés pour la Direction Générale ;
7. la réduction de la charge administrative des équipes terrain ;
8. une architecture de données capable d'absorber l'ouverture de nouveaux magasins et écoles.

### 1.2 Chiffres de dimensionnement (mise en production)

| Élément | Volume initial | Croissance à 3 ans |
| --- | --- | --- |
| Zones | 4 | 8 |
| Magasins | 4 (Bingerville, Cocody, Yopougon, Marcory/Koumassi) | 10 |
| Écoles partenaires | ~30 | 100 |
| Références produit | ~30 | 200 |
| Kits (école × niveau) | ~30 × 10 = 300 | 1 000 |
| Utilisateurs | ~50 | 200 |
| Ventes / jour hors rentrée | ~200 | 800 |
| Ventes / jour en pic de rentrée | ~3 000 | 10 000 |
| Sessions web concurrentes en pic | 40 | 150 |

Le **pic de rentrée scolaire** est le cas de charge dimensionnant. Toute décision d'architecture doit être prise en fonction de ce pic, et non de la charge moyenne.

**Conséquence directe de la suppression du mode hors-ligne :** la qualité de la connexion sur les stands devient une dépendance opérationnelle critique. Le point est traité en §1.6 (risques) et doit être traité côté organisation (forfaits data, partage de connexion, point d'accès de secours), non côté logiciel.

### 1.3 Architecture fonctionnelle — carte des modules

Le SRS est découpé en 28 modules répartis en 8 domaines. Chaque module fait l'objet d'un document `Mxx-*.md` distinct. Toute la portée est **Web** : la colonne « Support » précise seulement la taille d'écran cible principale.

**Domaine A — Socle & administration**

| Code | Module | Priorité | Support cible |
| --- | --- | --- | --- |
| M01 | Authentification & sécurité | Must | Bureau + mobile |
| M02 | Utilisateurs, rôles, permissions & périmètres | Must | Bureau |
| M03 | Paramétrage système | Must | Bureau |
| M04 | Journal d'audit & traçabilité | Must | Bureau |

**Domaine B — Référentiels**

| Code | Module | Priorité | Support cible |
| --- | --- | --- | --- |
| M05 | Organisation : zones, magasins, écoles, niveaux | Must | Bureau |
| M06 | Référentiel produit | Must | Bureau |
| M07 | Fournisseurs & prix d'achat | Must | Bureau |
| M08 | Kits scolaires & tarification | Must | Bureau |

**Domaine C — Stock**

| Code | Module | Priorité | Support cible |
| --- | --- | --- | --- |
| M09 | Stock & mouvements | Must | Bureau + tablette |
| M10 | Inventaires | Must | **Mobile/tablette prioritaire** |
| M11 | Transferts | Must | Bureau + tablette |
| M12 | Ajustements, pertes & casse | Must | Bureau |

**Domaine D — Achats**

| Code | Module | Priorité | Support cible |
| --- | --- | --- | --- |
| M13 | Demandes d'achat (workflow 3 niveaux) | Must | Bureau |
| M14 | Commandes fournisseurs | Must | Bureau |
| M15 | Réceptions & contrôle de conformité | Must | Bureau + tablette |

**Domaine E — Ventes**

| Code | Module | Priorité | Support cible |
| --- | --- | --- | --- |
| M16 | Ventes (kit / détail) | Must | **Mobile/tablette prioritaire** |
| M17 | Reçus, avoirs & livraisons partielles | Must | Mobile + bureau |
| M18 | Annulations & mouvements compensatoires | Must | Bureau |
| M19 | Clôture de caisse journalière | Must | Mobile/tablette |

**Domaine F — Dépenses & qualité**

| Code | Module | Priorité | Support cible |
| --- | --- | --- | --- |
| M20 | Dépenses (workflow 3 niveaux) | Must | Mobile + bureau |
| M21 | Non-conformités | Should | Mobile + bureau |
| M22 | Réunions & comptes rendus | Could | Bureau |

**Domaine G — Pilotage**

| Code | Module | Priorité | Support cible |
| --- | --- | --- | --- |
| M23 | Tableaux de bord par rôle | Must | Bureau + mobile |
| M24 | Rapports & exports Excel/PDF | Must | Bureau |
| M25 | Alertes & notifications (in-app + email) | Must | Bureau + mobile |

**Domaine H — Transverse**

| Code | Module | Priorité | Support cible |
| --- | --- | --- | --- |
| M26 | Pièces jointes & stockage documentaire | Must | Mobile + bureau |
| M27 | Reprise de données & imports initiaux | Must | Bureau |
| M28 | Recherche globale & navigation | Should | Bureau + mobile |

> Le code **M20 désigne désormais le module Dépenses**. L'ancien module « Mode hors-ligne & synchronisation » est supprimé, et non renuméroté.

### 1.4 Écarts assumés par rapport au cahier des charges

| N° | Exigence du CDC | Décision retenue | Justification |
| --- | --- | --- | --- |
| E-01 | Application mobile Android prioritaire puis iOS (§6, §9, Tableau 6 lignes 8/10/17) | **Retirée.** Application web responsive uniquement, optimisée pour usage smartphone sur les écrans de vente, d'inventaire et de dépense. | Décision du Maître d'ouvrage. Divise par deux la surface technique, supprime les cycles de publication sur les magasins d'applications, et permet une mise à jour instantanée pour tous les utilisateurs. |
| E-02 | Fonctionnement en mode dégradé hors-ligne avec synchronisation différée (§5.2, §5.3, §7.8, §9, §11, critère de recette n°8) | **Retirée.** Connexion réseau obligatoire. | Décision du Maître d'ouvrage. Le critère de recette n°8 est retiré du plan de recette. |
| E-03 | Interopérabilité : export exploitable par un logiciel comptable tiers (§9) | **Retirée en tant qu'interface.** Aucun connecteur ni format d'échange contractuel avec un système tiers. Les exports Excel/CSV/PDF restent disponibles pour un usage humain (M24). | Décision du Maître d'ouvrage. Un export téléchargé n'est pas une interface système et n'engage aucune compatibilité. |
| E-04 | Notifications push mobiles (§7.14, §8.1) | **Remplacées** par notification in-app (cloche) + email. | Conséquence de E-01. |
| E-05 | Modules M12 (ajustements, pertes & casse), M18 (annulations & mouvements compensatoires) et M19 (clôture de caisse) | **Ajoutés.** | Le CDC les suppose sans les spécifier : il mentionne les « pertes » et « ajustements » comme types de mouvement (§7.2) sans dire qui les crée ; il pose la règle du mouvement compensatoire (§10) sans définir le mécanisme ; il décrit la fiche journalière de vente visée par le chef de groupe puis le superviseur (§4.2) sans module correspondant. |

### 1.5 Hors périmètre

- Application mobile native (Android, iOS) et publication sur les magasins d'applications.
- Fonctionnement hors connexion, synchronisation différée, base de données locale.
- Toute interface, API publique, connecteur ou synchronisation avec un système tiers : logiciel comptable, opérateur de mobile money, ERP, plateforme de gestion scolaire, service de SMS. Le système est **fermé** : les seules sorties de données sont des fichiers téléchargés par un utilisateur authentifié.
- Comptabilité générale.
- Paie du personnel.
- Vente en ligne aux particuliers (e-commerce grand public).
- Facturation fiscale normalisée / certification DGI (à traiter dans une phase ultérieure si l'obligation s'applique).
- Impression sur imprimante thermique Bluetooth. L'impression des reçus se fait par la fonction d'impression du navigateur ou par génération d'un PDF, vers une imprimante installée sur le poste ou le réseau.

### 1.6 Risques induits par le choix « web uniquement »

| Risque | Gravité | Mesure d'atténuation (organisationnelle, hors logiciel) |
| --- | --- | --- |
| Coupure réseau sur un stand pendant la rentrée : arrêt total de l'enregistrement des ventes | Élevée | Double opérateur data sur les terminaux des stands ; procédure papier de secours conservée pour les coupures longues, avec ressaisie a posteriori dans l'application ; point d'accès mobile de secours par stand. |
| Latence élevée en zone mal couverte : temps de vente dégradé | Moyenne | Interface de vente optimisée pour charge légère (§3.14) ; mise en cache navigateur agressive des référentiels ; indication visuelle de perte de connexion. |
| Consommation data des terminaux terrain | Faible | Charges utiles JSON compactes, pas d'images dans les écrans de saisie, référentiels mis en cache. |
| Perte de saisie en cours si la connexion tombe pendant la validation | Moyenne | Sauvegarde du panier de vente en cours dans le `sessionStorage` du navigateur, restauré au retour ; idempotence côté serveur (§3.9) pour éviter les doubles ventes lors d'un renvoi. |

> Ces mesures ne réintroduisent **pas** un mode hors-ligne : la conservation d'un panier en cours dans le navigateur ne permet ni de valider une vente ni de décrémenter un stock sans réseau.

### 1.7 Flux de données principaux

| Flux | Enchaînement | Modules |
| --- | --- | --- |
| F1 — Approvisionnement fournisseur | Inventaire → détection sous-seuil → demande d'achat → validation superviseur → validation DG → commande fournisseur → réception et contrôle → entrée en stock magasin | M10, M13, M14, M15, M09 |
| F2 — Réapprovisionnement école | Besoin école → transfert magasin→école → validation site source → sortie stock magasin → réception école → entrée stock école | M11, M09 |
| F3 — Vente | Sélection kit ou détail → contrôle stock → encaissement → validation → décrémentation stock école → reçu numérique → alerte si seuil atteint | M16, M17, M09, M25 |
| F4 — Remontée de pilotage | Vente / mouvement / dépense / inventaire → agrégation temps réel → tableaux de bord école, magasin, zone, national | M23, M24 |
| F5 — Alertes | Événement métier (rupture, seuil, retard, écart, dépense au-delà du seuil) → règle d'alerte → destinataires par rôle et périmètre → cloche in-app et/ou email | M25 |

### 1.8 Workflow global (vue macro)

```
FOURNISSEUR ──cmd validée──> MAGASIN ──transfert──> ÉCOLE ──vente──> CLIENT
     ▲                          │                     │                │
     │                          │                     │                │
  M13/M14/M15               M09/M10/M11/M12      M09/M10/M16/M17    M17 reçu
     │                          │                     │
     └──────── proposition automatique ◄──── inventaire sous-seuil ───┘

TOUS SITES ──dépenses (M20) / non-conformités (M21)──> SUPERVISEUR ──> DIRECTION
TOUS ÉVÉNEMENTS ──> M04 audit ──> M23 tableaux de bord ──> M24 exports / M25 alertes
```

---

## 2. Stack technique prescrite

Cette stack est **imposée**. Elle n'est pas une suggestion : elle existe pour éliminer les arbitrages en cours de développement.

### 2.1 Vue d'ensemble

| Couche | Technologie imposée | Version cible |
| --- | --- | --- |
| Monorepo | pnpm workspaces + Turborepo | pnpm 9+ |
| Langage | TypeScript, mode `strict` | 5.5+ |
| Application | Next.js App Router + React | Next 15, React 19 |
| UI | Tailwind CSS + shadcn/ui + lucide-react | Tailwind 3.4+ |
| État serveur / cache | TanStack Query | v5 |
| Formulaires | react-hook-form + Zod | — |
| Graphiques | Recharts | v2 |
| API interne | REST versionnée, Next.js Route Handlers sous `/api/v1` — **consommée uniquement par le front-end de l'application**, non publique | — |
| Validation d'entrée | Zod, schémas partagés front-end / API | — |
| ORM | Prisma | 5.20+ |
| Base de données | PostgreSQL | 16 |
| Authentification | Auth.js (NextAuth v5), session par cookie `httpOnly` | — |
| Hachage mot de passe | Argon2id (`argon2` node) | — |
| 2FA | TOTP RFC 6238 (`otplib`) + codes de secours | — |
| Notifications | Cloche in-app (base de données) + email SMTP via Nodemailer | — |
| Stockage fichiers | Objet S3-compatible (Cloudflare R2, Scaleway ou MinIO auto-hébergé), URL pré-signées | — |
| Capture photo justificatif | `<input type="file" accept="image/*" capture="environment">` — appareil photo du téléphone via le navigateur | — |
| Export Excel | ExcelJS | — |
| Export PDF | `@react-pdf/renderer` | — |
| Impression reçu | Feuille de style `@media print` (format A6/A5) et génération PDF ; imprimante installée sur le poste ou le réseau | — |
| Tâches planifiées | `pg-boss` (file de travaux dans PostgreSQL) | — |
| Journalisation | `pino` structuré JSON | — |
| Tests unitaires | Vitest | — |
| Tests API | Vitest + `supertest` sur base de test éphémère | — |
| Tests E2E | Playwright, y compris en émulation de viewport mobile | — |
| CI | GitHub Actions | — |

Technologies explicitement **exclues** : React Native, Expo, Capacitor, Cordova, PWA installable avec cache hors-ligne, service worker de mise en cache d'écritures, IndexedDB/SQLite côté client, notifications push Web Push ou Expo, WebSocket de synchronisation, passerelle SMS, connecteur comptable.

### 2.2 Structure du monorepo

```
lepad/
├─ apps/
│  └─ web/                  Next.js 15 — interface complète + API /api/v1
├─ packages/
│  ├─ db/                   Prisma schema, migrations, seeds
│  ├─ shared/               Types, schémas Zod, codes d'erreur, permissions, constantes
│  ├─ domain/               Logique métier pure (calculs kit, stock, workflows) — sans I/O
│  └─ ui/                   Composants partagés
├─ docs/
│  └─ srs/                  Ce SRS
└─ turbo.json, pnpm-workspace.yaml
```

**Règle d'architecture impérative :** toute règle métier (`RG-*`) est implémentée dans `packages/domain` sous forme de fonction pure et testée unitairement, puis appelée par l'API. Aucune règle métier ne doit vivre uniquement dans un composant React ni dans un handler HTTP. Le front-end peut réutiliser la même fonction pour un retour immédiat à l'utilisateur, mais le serveur reste seul juge.

### 2.3 Environnements

| Environnement | Usage | Base de données |
| --- | --- | --- |
| `local` | Développement | PostgreSQL Docker + seed de démonstration |
| `test` | CI, tests automatisés | PostgreSQL éphémère, réinitialisée à chaque exécution |
| `recette` | Recette fonctionnelle LEPAD | Copie anonymisée de la production |
| `production` | Exploitation | PostgreSQL managé, sauvegarde quotidienne (rétention 30 j) + hebdomadaire (12 mois) |

---

## 3. Conventions transverses (normatives)

### 3.1 Identifiants et clés

- Clé primaire de toute table : `id UUID` généré côté application (UUID v7 pour l'ordonnancement temporel).
- Aucune clé métier n'est utilisée comme clé primaire. Les codes métier (`code`) sont uniques mais mutables sous contrôle.
- Clés étrangères toujours nommées `<entite>_id`.
- Aucune suppression physique en cascade : `ON DELETE RESTRICT` par défaut.

### 3.2 Numérotation des documents

Chaque type de document reçoit un numéro lisible, unique, généré par le serveur (jamais par le client), au moment de la **validation** et non de la création du brouillon.

| Document | Format | Portée de la séquence | Exemple |
| --- | --- | --- | --- |
| Vente | `VTE-{codeEcole}-{AAMM}-{NNNNN}` | par école et par mois | `VTE-MFB-2609-00147` |
| Reçu | identique au numéro de vente | — | `VTE-MFB-2609-00147` |
| Avoir / solde à livrer | `AVR-{codeEcole}-{AAMM}-{NNNN}` | par école et par mois | `AVR-MFB-2609-0012` |
| Annulation (compensation) | `ANN-{codeEcole}-{AAMM}-{NNNN}` | par école et par mois | `ANN-MFB-2609-0003` |
| Transfert | `TRF-{codeSiteOrigine}-{AAMM}-{NNNN}` | par site origine et par mois | `TRF-MAGBIN-2609-0021` |
| Inventaire | `INV-{codeSite}-{AAAAMMJJ}-{NN}` | par site et par jour | `INV-MAGBIN-20260915-01` |
| Demande d'achat | `DA-{AAMM}-{NNNN}` | nationale, par mois | `DA-2609-0034` |
| Commande fournisseur | `CF-{AAMM}-{NNNN}` | nationale, par mois | `CF-2609-0019` |
| Réception | `REC-{codeMagasin}-{AAMM}-{NNNN}` | par magasin et par mois | `REC-MAGBIN-2609-0008` |
| Dépense | `DEP-{codeSite}-{AAMM}-{NNNN}` | par site et par mois | `DEP-MAGBIN-2609-0027` |
| Non-conformité | `NC-{AAMM}-{NNNN}` | nationale, par mois | `NC-2609-0005` |
| Clôture de caisse | `CLO-{codeEcole}-{AAAAMMJJ}` | une par école et par jour | `CLO-MFB-20260915` |

Implémentation : table `sequence_compteur (cle TEXT PRIMARY KEY, valeur BIGINT)` incrémentée dans la **même transaction** que la création du document, via `UPDATE ... RETURNING` (verrou de ligne). Aucun trou de séquence toléré en fonctionnement normal ; un trou est admis si la transaction échoue après incrémentation, mais doit être journalisé.

Le numéro étant attribué par le serveur au moment de la validation, aucun numéro provisoire n'existe et aucune renumérotation n'est jamais nécessaire.

### 3.3 Dates, heures et fuseau

- Stockage systématique en `timestamptz`, valeurs en UTC.
- Fuseau d'affichage et de calcul métier : `Africa/Abidjan` (UTC+00, sans heure d'été).
- Une « journée d'activité » court de 00:00:00 à 23:59:59 heure d'Abidjan. Toute agrégation journalière (clôture de caisse, ventes du jour, inventaire du jour) utilise cette définition.
- Champs d'horodatage obligatoires sur toute table : `created_at`, `updated_at`. Sur toute table documentaire : `created_by_id`, `updated_by_id`.
- **Une seule date fait foi par document : l'horodatage serveur.** L'horloge du poste client n'est jamais utilisée pour un calcul métier, ni pour l'ordonnancement, ni pour le rattachement d'une vente à une journée d'activité.
- Cas particulier de la ressaisie a posteriori (procédure papier de secours, §1.6) : le document porte `date_operation` (déclarée par l'utilisateur, obligatoirement dans le passé, au maximum 7 jours en arrière) distincte de `created_at` (horodatage serveur de la saisie). Le champ `saisie_retroactive = true` est positionné, le motif est obligatoire, et l'audit conserve les deux dates. Seuls les rôles habilités (voir M02) peuvent effectuer une saisie retroactive.

### 3.4 Montants, quantités et arrondis

- Devise unique : **Franc CFA (XOF)**, sans sous-unité.
- Tous les montants sont stockés en **entiers** (`INTEGER` ou `BIGINT`), en francs CFA. Aucun type flottant n'est autorisé pour un montant, nulle part, jamais.
- Toutes les quantités sont des entiers positifs ou nuls. Aucune quantité fractionnaire.
- Affichage : séparateur de milliers = espace insécable, suffixe ` F CFA`. Exemple : `9 300 F CFA`.
- Arrondi des prix calculés : au multiple de **5 F CFA** le plus proche, seuil 2,5 arrondi vers le haut (la plus petite pièce en circulation est de 5 F). Le pas d'arrondi est paramétrable dans M03 (`arrondi_prix_pas`, défaut 5).
- Les pourcentages (remises, taux) sont stockés en points de base entiers (`3500` = 35,00 %) pour éviter tout flottant.
- Toute somme affichée à l'écran doit être recalculable par le serveur ; le client ne fait jamais autorité sur un montant.

### 3.5 Immutabilité et archivage

- **Aucune suppression physique** de donnée métier. Toute entité de référentiel possède `archived_at TIMESTAMPTZ NULL` et `archived_by_id UUID NULL`.
- Une entité archivée reste lisible, reste liée à son historique, mais n'est plus proposée dans les listes de sélection.
- Une entité référencée par au moins un document validé ne peut jamais être archivée sans contrôle : voir RG-M00-004.
- Les documents validés (vente, transfert, inventaire validé, réception, dépense validée) sont **immuables**. Toute correction passe par un document compensatoire (M18) qui référence le document d'origine par `document_origine_id`.
- Le statut `BROUILLON` est le seul état modifiable et supprimable d'un document.

### 3.6 Cycle de vie standard des documents

Tous les documents à workflow partagent le même vocabulaire de statut. Aucun module ne doit inventer d'autres valeurs sans le déclarer.

| Statut | Signification | Modifiable | Compte dans les agrégats |
| --- | --- | --- | --- |
| `BROUILLON` | En cours de saisie, non soumis | Oui | Non |
| `SOUMIS` | Soumis au premier niveau de validation | Non | Non |
| `VALIDE_N1` | Validé au niveau 1 (superviseur), en attente du niveau 2 | Non | Non |
| `VALIDE` | Validé définitivement / effectif | Non | Oui |
| `REJETE` | Rejeté avec motif obligatoire | Non (recopie possible) | Non |
| `ANNULE` | Annulé par document compensatoire | Non (le compensatoire, oui) | Non |
| `CLOTURE` | Cycle terminé (ex. commande entièrement réceptionnée) | Non | Oui |

Transitions autorisées : `BROUILLON → SOUMIS → VALIDE_N1 → VALIDE → CLOTURE`, plus `SOUMIS|VALIDE_N1 → REJETE`, plus `VALIDE → ANNULE`. Toute autre transition renvoie l'erreur `TRANSITION_STATUT_INTERDITE`.

Chaque changement de statut écrit une ligne dans `document_visa (document_type, document_id, etape, acteur_id, decision, motif, horodatage)`. C'est le remplacement numérique des visas manuscrits.

### 3.7 Modèle de périmètre (scoping) — règle transverse critique

Le cloisonnement des données est une exigence de recette (critère n°5 du CDC). Il est implémenté une fois, de façon transverse, et jamais réinventé module par module.

Chaque utilisateur porte un **périmètre** composé d'un niveau et d'un ensemble de cibles :

| Niveau de périmètre | Cibles | Rôles concernés |
| --- | --- | --- |
| `NATIONAL` | toutes zones, tous magasins, toutes écoles | Directeur Général, Manager Général |
| `ZONE` | une ou plusieurs zones, et par héritage tous les magasins et écoles de ces zones | Superviseur de zone |
| `MAGASIN` | un magasin, et par héritage les écoles rattachées à ce magasin en lecture seule | Gestionnaire de magasin |
| `ECOLE` | une ou plusieurs écoles | Chef d'équipe, Commercial / Caissière |

**Règles d'implémentation impératives :**

1. Toute requête de lecture d'une entité rattachée à un site applique un filtre de périmètre **côté serveur**, jamais côté client.
2. Le filtre est appliqué par une couche unique (`packages/domain/scope.ts` + extension de client Prisma), pas par du filtrage recopié dans chaque endpoint.
3. Une tentative d'accès hors périmètre à une ressource existante renvoie `403 HORS_PERIMETRE` et non `404`, et l'événement est journalisé dans l'audit avec le niveau `ALERTE_SECURITE`.
4. Aucun paramètre de requête ne peut élargir un périmètre. `?ecoleId=` ne fait que restreindre à l'intérieur du périmètre autorisé.
5. Aucune donnée hors périmètre ne doit transiter jusqu'au navigateur, y compris dans une charge utile plus large ou un état pré-rendu côté serveur.

### 3.8 Permissions — nomenclature

Chaque droit est un code `module.ressource.action`, où l'action appartient à l'ensemble fermé suivant :

`consulter`, `creer`, `modifier`, `archiver`, `valider`, `rejeter`, `annuler`, `reouvrir`, `exporter`, `imprimer`, `parametrer`.

Une permission accordée est toujours évaluée **conjointement** avec le périmètre : `peut(utilisateur, 'ventes.vente.consulter', { ecoleId })` retourne vrai seulement si le droit est accordé au rôle **et** que `ecoleId` est dans le périmètre. Le détail exhaustif des permissions par rôle et par écran figure dans M02 §11.

### 3.9 Contrat d'API interne

L'API n'est pas publique : elle est consommée exclusivement par le front-end de l'application. Aucun tiers ne s'y connecte, aucun jeton d'API applicatif n'est émis, aucune documentation externe n'est publiée. Le contrat reste néanmoins formalisé pour la cohérence du code et des tests.

- Base : `https://<host>/api/v1`. Le versionnement est dans le chemin ; aucune rupture de contrat sans passage à `/api/v2`.
- Encodage : JSON UTF-8. Clés en `camelCase`. Dates en ISO 8601 avec fuseau (`2026-09-15T08:12:03.000Z`).
- Authentification : cookie de session `httpOnly` `Secure` `SameSite=Lax`. Protection CSRF par jeton double-soumission sur toute écriture.
- En-têtes obligatoires côté client : `X-Request-Id`, et `Idempotency-Key` sur toute écriture (protection contre le double-clic, le rechargement de page et le renvoi après timeout réseau).

**Réponse de succès (ressource unique)**

```json
{
  "data": { "id": "…", "…": "…" },
  "meta": { "requestId": "…", "serverTime": "2026-09-15T08:12:03.000Z" }
}
```

**Réponse de succès (collection)**

```json
{
  "data": [ { "…": "…" } ],
  "pagination": { "page": 1, "perPage": 50, "total": 1284, "totalPages": 26 },
  "meta": { "requestId": "…", "serverTime": "…" }
}
```

**Réponse d'erreur**

```json
{
  "error": {
    "code": "STOCK_INSUFFISANT",
    "message": "Stock insuffisant pour la référence C200 : 3 disponibles, 7 demandés.",
    "details": [ { "champ": "lignes[2].quantite", "code": "STOCK_INSUFFISANT", "disponible": 3, "demande": 7 } ],
    "requestId": "…"
  }
}
```

- Pagination : `?page=1&perPage=50`, `perPage` maximum 200. Les exports ne passent pas par la pagination mais par un endpoint dédié `/export`.
- Tri : `?tri=date:desc,montant:asc` sur les champs explicitement déclarés triables par le module.
- Filtres : nommage `?dateDebut=&dateFin=&zoneId=&magasinId=&ecoleId=&q=`. `q` est la recherche libre.
- Codes HTTP : `200` lecture, `201` création, `204` suppression logique, `400` validation, `401` non authentifié, `403` non autorisé ou hors périmètre, `404` inexistant dans le périmètre, `409` conflit métier (statut, doublon, idempotence divergente), `422` règle métier violée, `429` quota, `500` erreur serveur.
- **Idempotence** : toute écriture accepte `Idempotency-Key`. La paire (clé, utilisateur) est stockée 7 jours avec le corps de la réponse. Un rejeu identique renvoie la réponse d'origine avec `200` et l'en-tête `X-Idempotent-Replay: true`. Un rejeu avec un corps différent renvoie `409 IDEMPOTENCE_DIVERGENTE`.

### 3.10 Catalogue transverse des codes d'erreur

Les codes propres à chaque module sont définis dans le document du module. Les codes suivants sont transverses et réutilisables partout.

| Code | HTTP | Message utilisateur (fr) |
| --- | --- | --- |
| `NON_AUTHENTIFIE` | 401 | Votre session a expiré. Veuillez vous reconnecter. |
| `IDENTIFIANTS_INVALIDES` | 401 | Identifiant ou mot de passe incorrect. |
| `COMPTE_DESACTIVE` | 403 | Votre compte est désactivé. Contactez votre superviseur. |
| `DROIT_INSUFFISANT` | 403 | Vous n'avez pas les droits nécessaires pour cette action. |
| `HORS_PERIMETRE` | 403 | Cette donnée ne fait pas partie de votre périmètre. |
| `RESSOURCE_INTROUVABLE` | 404 | Élément introuvable. |
| `VALIDATION_ECHOUEE` | 400 | Certains champs sont invalides. Vérifiez le formulaire. |
| `CHAMP_OBLIGATOIRE` | 400 | Ce champ est obligatoire. |
| `VALEUR_DUPLIQUEE` | 409 | Cette valeur existe déjà. |
| `TRANSITION_STATUT_INTERDITE` | 409 | Cette action n'est pas possible dans l'état actuel du document. |
| `DOCUMENT_IMMUABLE` | 409 | Ce document est validé et ne peut plus être modifié. Créez une annulation. |
| `IDEMPOTENCE_DIVERGENTE` | 409 | Une opération différente a déjà été enregistrée avec cette clé. |
| `CONFLIT_CONCURRENCE` | 409 | Ce document a été modifié entre-temps. Rechargez la page. |
| `REGLE_METIER_VIOLEE` | 422 | Opération refusée : {détail}. |
| `ENTITE_UTILISEE` | 422 | Impossible d'archiver : cet élément est utilisé par des documents existants. |
| `QUOTA_DEPASSE` | 429 | Trop de tentatives. Réessayez dans {n} secondes. |
| `ERREUR_SERVEUR` | 500 | Une erreur technique est survenue. L'incident a été enregistré. |
| `RESEAU_INDISPONIBLE` | — (client) | Connexion perdue. Vérifiez votre réseau : l'opération n'a pas été enregistrée. |

> `RESEAU_INDISPONIBLE` est un état purement client. Il indique explicitement que **rien n'a été enregistré**, et n'ouvre aucune file d'attente. C'est le remplacement du message hors-ligne de la version 1.0 du SRS.

### 3.11 Contrôle de concurrence

Toute entité modifiable porte un champ `version INTEGER` incrémenté à chaque écriture. Les requêtes `PATCH`/`PUT` transmettent `version` ; une divergence renvoie `409 CONFLIT_CONCURRENCE`. Pour les opérations de stock, le verrouillage est plus fort : voir §3.12.

### 3.12 Intégrité du stock — règle transverse fondamentale

Le stock est la donnée la plus sensible du système. Trois principes non négociables :

1. **Le solde de stock n'est jamais écrit directement.** Il est toujours la conséquence d'un `mouvement_stock` inséré. La table `stock` porte un solde matérialisé, mis à jour dans la même transaction que le mouvement, jamais indépendamment.
2. **Toute opération affectant le stock est transactionnelle et sérialisée par site et référence.** Implémentation : `SELECT ... FOR UPDATE` sur la ligne `stock (site_id, produit_id)` avant tout contrôle de disponibilité et toute écriture. Le contrôle « stock suffisant » et la décrémentation doivent être dans la même transaction, sinon deux ventes simultanées peuvent créer un stock négatif.
3. **Le stock ne peut jamais devenir négatif.** Contrainte de base de données `CHECK (quantite >= 0)` en plus du contrôle applicatif. Si le CHECK se déclenche, c'est un défaut logiciel : l'incident est journalisé en `ERREUR` et remonté.

La suppression du mode hors-ligne renforce cette garantie : toute vente étant validée en ligne dans une transaction, le contrôle de disponibilité est toujours exact au moment de la validation. Le cas « vente acceptée alors que le stock est devenu insuffisant » disparaît, et avec lui le mouvement d'ajustement `ECART_SYNC`.

Un job de contrôle quotidien recalcule, pour chaque couple (site, produit), la somme des mouvements et la compare au solde matérialisé. Tout écart génère une alerte `INCOHERENCE_STOCK` (M25) et n'est jamais corrigé automatiquement.

### 3.13 Journal d'audit

Toute écriture sur une donnée métier écrit une ligne d'audit (détail dans M04) :

`audit_log (id, horodatage, acteur_id, acteur_role, ip, user_agent, action, entite_type, entite_id, site_id, valeurs_avant JSONB, valeurs_apres JSONB, request_id, niveau)`

Niveaux : `INFO` (lecture sensible, export), `MODIFICATION`, `VALIDATION`, `ALERTE_SECURITE`, `ERREUR`. Le journal d'audit est en **ajout seul** : aucune mise à jour ni suppression, y compris par le Directeur Général. Rétention minimale 24 mois.

Actions systématiquement auditées (CDC §10) : création/modification/archivage d'utilisateur, changement de droits, validation de commande, validation de dépense, ajustement de stock hors vente, annulation de vente, modification de kit, export de données, échec d'authentification, accès hors périmètre, saisie retroactive.

### 3.14 Conventions d'interface

- Langue unique : **français** (fr-CI). Aucune chaîne en dur dans le code : tous les libellés passent par `packages/shared/i18n/fr.ts`, clés en `snake_case` hiérarchique (`ventes.ecran.bouton_valider`).
- **Conception responsive obligatoire, avec approche mobile d'abord pour les écrans de terrain.** Trois points de rupture : `< 640 px` (smartphone), `640–1 024 px` (tablette), `> 1 024 px` (bureau).
- Répartition des cibles : les écrans de vente (M16), d'inventaire (M10), de dépense (M20) et de non-conformité (M21) sont conçus **d'abord** pour smartphone en portrait, puis étendus au bureau. Les écrans de paramétrage, de référentiel, de workflow d'achat et de rapport sont conçus pour le bureau et restent consultables sur tablette.
- Navigateurs supportés : Chrome, Edge, Firefox et Safari, deux dernières versions majeures. Chrome Android et Safari iOS pour les terminaux terrain.
- Ergonomie terrain (usage debout, à une main, en extérieur) : cibles tactiles ≥ 48 px, contraste ≥ 4,5:1, police de base 16 px, actions principales en bas d'écran et atteignables au pouce, aucun survol requis, aucun geste complexe.
- L'application doit être ajoutable à l'écran d'accueil (manifeste web, icône, mode `standalone`) pour un lancement en plein écran, **sans mise en cache d'écriture ni fonctionnement hors connexion**.
- Indicateur de connectivité permanent : bandeau `Connexion perdue — les enregistrements sont impossibles` dès détection de la perte de réseau, disparaissant au retour.
- Le panier de vente en cours de saisie est conservé dans le `sessionStorage` et restauré après un rechargement accidentel de la page. Cette conservation est locale, temporaire, non validante et ne concerne aucune autre donnée.
- Toute action destructive ou irréversible (validation de vente, archivage, annulation) demande une confirmation explicite avec récapitulatif.
- Aucun double-clic ne doit produire deux documents : les boutons de soumission se désactivent pendant la requête et l'`Idempotency-Key` protège le serveur.
- États d'écran obligatoires pour chaque liste : `chargement`, `vide` (avec message explicite et action suggérée), `erreur` (avec bouton Réessayer), `hors périmètre`, `nominal`.
- Poids des écrans de saisie terrain : charge utile JavaScript initiale ≤ 250 Ko compressée, aucune image décorative, référentiels mis en cache par TanStack Query avec `staleTime` de 15 minutes.

### 3.15 Performance

| Opération | Exigence |
| --- | --- |
| Enregistrement d'une vente | < 2 s bout en bout, dont < 400 ms serveur (p95) |
| Retour visuel après appui sur « Valider » | < 150 ms (état de chargement immédiat) |
| Consultation d'un stock de site | < 2 s (p95) |
| Chargement initial de l'écran de vente sur 3G | < 5 s |
| Tableau de bord national, période 1 mois | < 3 s (p95), agrégats précalculés autorisés |
| Export Excel 50 000 lignes | < 30 s, généré en tâche de fond avec notification in-app |

Les tableaux de bord peuvent s'appuyer sur des tables d'agrégats rafraîchies par job (`agregat_vente_jour_site`, `agregat_stock_jour_site`) à condition d'afficher l'horodatage de dernier rafraîchissement, et que le détail par site reste cohérent avec les totaux consolidés (critère de recette n°6).

### 3.16 Sécurité

- HTTPS/TLS obligatoire partout ; HSTS activé.
- Mots de passe : Argon2id, 12 caractères minimum, contrôle contre une liste de mots de passe compromis, expiration non forcée mais rotation possible à l'initiative de l'administrateur.
- 2FA TOTP obligatoire pour les rôles `DIRECTEUR_GENERAL` et `MANAGER_GENERAL`, optionnelle et activable pour `SUPERVISEUR_ZONE`.
- Limitation de débit : 5 tentatives de connexion par identifiant et par 15 minutes, puis verrouillage temporaire de 15 minutes ; 10 par IP et par minute sur les endpoints d'authentification.
- Sessions : cookie `httpOnly` `Secure` `SameSite=Lax`, durée glissante de 12 heures d'inactivité, durée absolue de 7 jours. La désactivation d'un utilisateur invalide immédiatement toutes ses sessions actives.
- Protection CSRF par jeton double-soumission sur toute requête d'écriture.
- En-têtes de sécurité : `Content-Security-Policy` stricte sans `unsafe-inline`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy` limitant l'accès à la caméra aux seuls écrans de capture de justificatif.
- **Aucune donnée métier persistée dans le navigateur** en dehors du cookie de session et du panier de vente temporaire en `sessionStorage`. Pas de `localStorage`, pas d'IndexedDB, pas de cache d'écriture.
- Pièces justificatives : stockage objet privé, accès uniquement par URL pré-signée de 15 minutes, jamais d'URL publique. Contrôle du type MIME réel et de la taille (10 Mo maximum), recompression des images côté serveur.
- Aucune donnée réelle de production dans les environnements de développement ; anonymisation obligatoire pour la recette.
- Journalisation : aucun mot de passe, jeton, ni contenu de pièce justificative dans les logs.
- Procédure de révocation rapide des accès en cas de départ d'un collaborateur : désactivation du compte par le DG ou le Manager Général, effet immédiat sur les sessions.

### 3.17 Sauvegarde et reprise

- Sauvegarde complète quotidienne de PostgreSQL, rétention 30 jours glissants.
- Sauvegarde hebdomadaire archivée, rétention 12 mois.
- Archivage continu des WAL permettant une restauration à un instant donné (PITR).
- RTO < 4 h, RPO < 24 h (RPO effectif < 15 min avec PITR).
- Sauvegarde du stockage objet (pièces justificatives) alignée sur la même politique de rétention.
- Procédure de restauration documentée et **testée trimestriellement**, avec compte rendu.
- L'application étant intégralement en ligne, aucune donnée métier ne réside sur un poste client : il n'existe pas de sauvegarde côté terminal, et une panne de terminal n'entraîne aucune perte de donnée validée.

### 3.18 Règles générales transverses

| Code | Règle |
| --- | --- |
| RG-M00-001 | Aucune donnée métier n'est supprimée physiquement. L'archivage logique est le seul mécanisme de retrait. |
| RG-M00-002 | Aucun document validé n'est modifiable. Toute correction se fait par document compensatoire référençant l'original. |
| RG-M00-003 | Tout document, tout mouvement de stock et toute validation portent l'identité de leur auteur et un horodatage serveur. |
| RG-M00-004 | Une entité de référentiel utilisée par au moins un document non brouillon ne peut être ni supprimée ni archivée sans que le système affiche le nombre et la nature des documents concernés. L'archivage reste possible ; la suppression jamais. |
| RG-M00-005 | Le stock d'un site ne peut jamais être négatif. |
| RG-M00-006 | Un contrôle de disponibilité de stock n'a de valeur que dans la transaction qui décrémente ce stock. |
| RG-M00-007 | Le périmètre d'un utilisateur est évalué côté serveur à chaque requête. Aucun paramètre client ne peut l'élargir. |
| RG-M00-008 | Un utilisateur ne peut jamais valider un document dont il est l'émetteur, sauf si son rôle est explicitement autorisé à l'auto-validation pour ce type de document (aucun ne l'est en version 1). |
| RG-M00-009 | Toute étape de workflow rejetée exige un motif textuel de 10 caractères minimum. |
| RG-M00-010 | Tout montant affiché à l'utilisateur est calculé par le serveur. Le client ne fait jamais autorité. |
| RG-M00-011 | Toute écriture est idempotente vis-à-vis de la clé `Idempotency-Key` et rejouable sans effet de bord. |
| RG-M00-012 | Le journal d'audit est en ajout seul et n'est modifiable par aucun rôle. |
| RG-M00-013 | Les libellés visibles par l'utilisateur sont en français et centralisés ; aucune chaîne en dur. |
| RG-M00-014 | Toute liste exportable produit un export strictement identique aux données filtrées à l'écran (critère de recette n°9). |
| RG-M00-015 | Les prix de détail ne sont jamais affichés publiquement sur un écran client ; ils restent internes (politique commerciale, CDC §7.7). |
| RG-M00-016 | Aucune opération d'écriture n'est enregistrée ni mise en file d'attente en l'absence de connexion. L'utilisateur est informé sans ambiguïté que rien n'a été enregistré. |
| RG-M00-017 | Aucune donnée métier n'est persistée durablement sur le poste client. |
| RG-M00-018 | Le système n'expose aucune interface à un tiers. Toute sortie de donnée est un fichier téléchargé par un utilisateur authentifié, tracé dans l'audit. |
| RG-M00-019 | Une saisie retroactive (procédure papier de secours) est limitée à 7 jours, exige un motif, est réservée aux rôles habilités et est systématiquement auditée et signalée au superviseur. |

---

## 4. Modèle de données global

Vue d'ensemble des tables par module. Le détail des champs, contraintes et index est donné dans le document de chaque module.

### 4.1 Tables par domaine

| Domaine | Tables |
| --- | --- |
| A — Socle | `utilisateur`, `role`, `permission`, `role_permission`, `utilisateur_perimetre`, `session`, `mfa_secret`, `mfa_code_secours`, `tentative_connexion`, `parametre_systeme`, `audit_log`, `sequence_compteur`, `idempotence` |
| B — Référentiels | `zone`, `magasin`, `ecole`, `niveau_scolaire`, `ecole_niveau`, `categorie_produit`, `marque`, `unite`, `produit`, `fournisseur`, `produit_fournisseur`, `kit`, `kit_version`, `kit_ligne`, `tarif_detail`, `convention_remise` |
| C — Stock | `site` (unification magasin/école/stand), `stock`, `stock_seuil`, `mouvement_stock`, `inventaire`, `inventaire_ligne`, `transfert`, `transfert_ligne`, `ajustement`, `ajustement_ligne` |
| D — Achats | `demande_achat`, `demande_achat_ligne`, `commande_fournisseur`, `commande_fournisseur_ligne`, `reception`, `reception_ligne` |
| E — Ventes | `vente`, `vente_ligne`, `vente_kit_ligne`, `paiement`, `recu`, `avoir`, `avoir_ligne`, `annulation`, `cloture_caisse` |
| F — Dépenses & qualité | `depense`, `categorie_depense`, `non_conformite`, `non_conformite_action`, `reunion`, `reunion_compte_rendu` |
| G — Pilotage | `alerte`, `alerte_regle`, `alerte_destinataire`, `notification`, `rapport_modele`, `export_job`, `agregat_vente_jour_site`, `agregat_stock_jour_site` |
| H — Transverse | `piece_jointe`, `import_job`, `import_ligne_rejet`, `document_visa` |

Tables supprimées par rapport à la version 1.0 du SRS : `refresh_token` (plus de jetons mobiles) et `sync_operation` (plus de file de synchronisation).

### 4.2 Notion de « site »

Le CDC gère le stock à trois niveaux (magasin, école, stand temporaire) et les transferts peuvent relier n'importe quels deux d'entre eux. Pour éviter la duplication de toute la logique de stock, on introduit une abstraction :

```
site (id, type ENUM('MAGASIN','ECOLE','STAND'), magasin_id NULL, ecole_id NULL, zone_id, code, libelle, actif)
```

- Chaque `magasin` et chaque `ecole` possède exactement un `site` (créé automatiquement, même transaction).
- Le stock, les mouvements, les inventaires, les transferts, les dépenses et les ajustements référencent **toujours** `site_id`, jamais `magasin_id` ni `ecole_id`.
- Les ventes référencent `ecole_id` **et** `site_id` (l'école est l'entité commerciale, le site est l'entité de stock).
- Contrainte : `CHECK ((type='MAGASIN' AND magasin_id IS NOT NULL AND ecole_id IS NULL) OR (type='ECOLE' AND ecole_id IS NOT NULL AND magasin_id IS NULL) OR (type='STAND' AND ecole_id IS NOT NULL))`.

### 4.3 Relations structurantes

- `zone` 1—N `magasin` ; `magasin` 1—N `ecole` ; `ecole` N—1 `zone` (dénormalisée pour la performance des filtres, cohérence garantie par déclencheur).
- `site` 1—N `stock` ; `stock` N—1 `produit`. Unicité `(site_id, produit_id)`.
- `mouvement_stock` N—1 `site`, N—1 `produit`, N—1 `utilisateur`, et porte `document_type` + `document_id` (référence polymorphe vers vente, transfert, réception, inventaire, ajustement).
- `kit` N—1 `ecole`, N—1 `niveau_scolaire` ; `kit` 1—N `kit_version` ; `kit_version` 1—N `kit_ligne` ; `kit_ligne` N—1 `produit`. Unicité `(ecole_id, niveau_id)` pour le kit actif.
- `vente` N—1 `ecole`, N—1 `utilisateur` (vendeuse), 1—N `vente_ligne`, 1—N `paiement`, N—1 `kit_version` lorsque la vente porte un kit (le prix et la composition sont figés par référence à la version).
- `transfert` N—1 `site` origine, N—1 `site` destination, 1—N `transfert_ligne`, et génère 2 `mouvement_stock` par ligne.
- `demande_achat` 1—N `demande_achat_ligne` ; 0..1 `commande_fournisseur` ; `commande_fournisseur` 1—N `reception`.
- `document_visa` référence polymorphe vers tout document à workflow.
- Tout document référence son auteur (`created_by_id`) ; aucune exception.

### 4.4 Index obligatoires (transverses)

- `mouvement_stock (site_id, produit_id, created_at DESC)` — historique de mouvements.
- `vente (ecole_id, date_operation DESC)`, `vente (vendeuse_id, date_operation DESC)`, `vente (numero)` unique.
- `stock (site_id, produit_id)` unique ; index partiel sur `quantite <= seuil_alerte` pour les écrans d'alerte.
- `audit_log (entite_type, entite_id, horodatage DESC)` et `audit_log (acteur_id, horodatage DESC)`.
- `idempotence (cle, utilisateur_id)` unique.
- Tout champ utilisé comme filtre standard (§3.9) est indexé.

---

## 5. Notifications et alertes (cadre transverse)

Détail en M25. Cadre imposé :

- Canaux : **cloche in-app** (canal principal) et **email** (canal de relais pour les alertes de niveau élevé et les destinataires non connectés). Aucune notification push, aucun SMS.
- Toute alerte est **matérialisée en base** (`alerte`) avant d'être diffusée : une alerte non lue reste visible dans l'application même si l'email a échoué.
- Les destinataires ne sont jamais des personnes codées en dur mais une combinaison (rôle × périmètre), résolue au moment du déclenchement.
- Regroupement obligatoire : une même règle ne peut pas générer plus d'une notification par destinataire, par site et par heure. Les occurrences suivantes sont agrégées (« 12 références en rupture à Bingerville »).
- Les 7 types d'alerte du CDC §7.14 sont : `RUPTURE_STOCK`, `SEUIL_SECURITE_ATTEINT`, `INVENTAIRE_NON_REALISE`, `VENTE_ANORMALE`, `TRANSFERT_EN_ATTENTE_24H`, `DEPENSE_IMPORTANTE`, `INCOHERENCE_STOCK`.
- Un type supplémentaire est ajouté au titre de RG-M00-019 : `SAISIE_RETROACTIVE`, notifiant le superviseur de zone de toute vente ou dépense saisie avec une date antérieure.
- Un email sortant est un message transactionnel vers un utilisateur nommé du système ; ce n'est pas une interface avec un système tiers au sens de §1.5.

---

## 6. Calculs transverses

Toutes les formules ci-dessous sont implémentées dans `packages/domain/calculs.ts`, en arithmétique entière, et testées unitairement avec les valeurs de contrôle indiquées.

| Code | Grandeur | Formule | Contrôle |
| --- | --- | --- | --- |
| CAL-M00-001 | Coût de revient d'un kit | `Σ (kit_ligne.quantite × produit.cout_achat_reference)` | Kit 6e Mamie Fétaï : 14 cahiers, à vérifier contre la table réelle |
| CAL-M00-002 | Somme des prix de détail d'un kit | `Σ (kit_ligne.quantite × tarif_detail.prix)` | Doit être `>` au prix du kit (RG-M08) |
| CAL-M00-003 | Marge unitaire kit | `kit.prix_vente − CAL-M00-001` | Peut être négative → blocage à la publication |
| CAL-M00-004 | Taux de marge | `arrondi(marge × 10000 / prix_vente)` en points de base | 9 300 / 6 000 → 3548 (35,48 %) |
| CAL-M00-005 | Montant d'une ligne de vente détail | `quantite × prix_unitaire` | — |
| CAL-M00-006 | Montant total d'une vente | `Σ montants lignes − remise` | Remise ≤ montant total |
| CAL-M00-007 | Valorisation du stock d'un site | `Σ (stock.quantite × produit.cout_achat_reference)` | — |
| CAL-M00-008 | Écart d'inventaire | `quantite_physique − quantite_theorique` | Signe conservé |
| CAL-M00-009 | Taux d'écart d'inventaire | `abs(ecart) × 10000 / max(quantite_theorique, 1)` | Comparé au seuil de tolérance (M03) |
| CAL-M00-010 | Quantité à commander | `max(0, stock_maximum − quantite_disponible)` sur les références à `quantite <= stock_securite` | Jamais négative |
| CAL-M00-011 | Chiffre d'affaires d'un périmètre et d'une période | `Σ vente.montant_total` sur ventes `VALIDE`, moins les annulations `VALIDE` de la période | Les ventes annulées ne comptent jamais |
| CAL-M00-012 | Panier moyen | `CA / nombre de ventes` (ventes valides, hors annulées) | Division entière, arrondi au franc |
| CAL-M00-013 | Taux de rupture | `nombre de couples (site, produit) à quantite = 0 × 10000 / nombre de couples suivis` | — |
| CAL-M00-014 | Taux kit vs détail | `montant kits × 10000 / CA total` | — |
| CAL-M00-015 | Taux de conformité fournisseur | `lignes reçues conformes × 10000 / lignes commandées` sur la période | — |
| CAL-M00-016 | Délai moyen de livraison fournisseur | `moyenne(date_reception − date_commande)` en jours | — |
| CAL-M00-017 | Marge d'un périmètre | `CA − coût des marchandises vendues − dépenses validées` | Le CDC parle de « marge » sans la définir : cette définition est proposée et doit être validée par le DG |
| CAL-M00-018 | Coût des marchandises vendues | `Σ (quantite vendue × cout_achat_reference)` | Méthode de valorisation : coût de référence, pas FIFO/CMUP (à confirmer) |

**Point ouvert à trancher par le Maître d'ouvrage :** la méthode de valorisation du stock. Le CDC dit « quantité × coût unitaire » sans préciser si le coût unitaire est un coût de référence figé, un coût moyen pondéré (CMUP) ou un FIFO. Le SRS retient par défaut le **coût d'achat de référence du produit**, plus simple et suffisant pour le pilotage, avec historisation du coût pour ne pas réécrire le passé. À arbitrer avant M09.

---

## 7. Feuille de route de rédaction du SRS et de développement

Ordre imposé par les dépendances. Chaque module ne peut être développé que si ses prérequis sont livrés.

| Lot | Modules | Prérequis | Correspondance CDC (planning §17) |
| --- | --- | --- | --- |
| L0 | M00 (ce document), M03, M04 | — | Phase 1 |
| L1 | M01, M02 | L0 | Phase 2 |
| L2 | M05, M06, M07 | L1 | Phase 2 |
| L3 | M08 (kits & tarification), M27 (reprise de données) | L2 | Phase 2 |
| L4 | M09, M12 | L3 | Phase 3 |
| L5 | M10, M11 | L4 | Phase 3 |
| L6 | M13, M14, M15 | L5 | Phase 3 |
| L7 | M16, M17, M18, M19, M26 | L4, L3 | Phase 4 |
| L8 | M20, M21, M22 | L2, M26 | Phase 4 |
| L9 | M23, M24, M25, M28 | tous | Phase 5 |

La suppression de l'application mobile et du mode hors-ligne retire la charge la plus lourde du lot L7 et supprime toute dépendance à un cycle de publication sur les magasins d'applications. Le planning indicatif du CDC (24 à 33 semaines) peut être révisé à la baisse par le prestataire.

---

## 8. Définition de « terminé » (Definition of Done)

Un module n'est livré que si **tous** les points suivants sont vrais :

1. Le schéma Prisma et la migration sont écrits, appliqués et réversibles.
2. Chaque règle `RG-*` du module est implémentée dans `packages/domain` et couverte par au moins un test unitaire nominal et un test de violation.
3. Chaque endpoint documenté existe, respecte le contrat §3.9, et est couvert par un test d'API incluant un cas `403 HORS_PERIMETRE` et un cas `403 DROIT_INSUFFISANT`.
4. Chaque écran documenté est implémenté avec ses cinq états obligatoires (§3.14) et vérifié sur les trois points de rupture responsive.
5. Chaque validation `VAL-*` est appliquée côté client **et** côté serveur, avec le même schéma Zod partagé.
6. Chaque message `MSG-*` est présent dans le fichier i18n et affiché au bon moment.
7. L'audit écrit une ligne pour chaque action sensible du module.
8. Les données de démonstration (`seed`) couvrent le module et permettent de rejouer les cas d'utilisation.
9. Un test E2E Playwright couvre le parcours principal du module, exécuté en viewport bureau et en viewport smartphone pour les écrans de terrain.
10. La couverture de tests de `packages/domain` est ≥ 90 % pour le module.
11. Aucune écriture dans `localStorage`, `IndexedDB` ou un service worker de cache : contrôle automatisé en CI (RG-M00-017).

---

## 9. Conventions de traçabilité du SRS

Chaque élément spécifié porte un identifiant stable, utilisé dans le code (commentaires), les tests (noms de tests) et les tickets.

| Préfixe | Objet | Exemple |
| --- | --- | --- |
| `ECR-Mxx-nn` | Écran | `ECR-M16-01` écran de vente |
| `UC-Mxx-nn` | Cas d'utilisation | `UC-M16-01` enregistrer une vente |
| `WF-Mxx-nn` | Workflow | `WF-M13-01` validation d'une demande d'achat |
| `RG-Mxx-nnn` | Règle métier | `RG-M16-004` |
| `VAL-Mxx-nnn` | Règle de validation de champ | `VAL-M02-012` |
| `MSG-Mxx-nnn` | Message utilisateur | `MSG-M16-007` |
| `NOT-Mxx-nn` | Notification / alerte | `NOT-M25-03` |
| `API-Mxx-nn` | Endpoint | `API-M16-03` |
| `CAL-Mxx-nnn` | Calcul / formule | `CAL-M00-001` |
| `FRM-Mxx-nn` | Formulaire | `FRM-M02-01` |
| `LST-Mxx-nn` | Liste / tableau | `LST-M02-01` |
| `FIL-Mxx-nn` | Jeu de filtres | `FIL-M16-01` |

Chaque document de module se termine par une **matrice de traçabilité** reliant ses éléments aux exigences du cahier des charges et aux critères de recette (§20 du CDC).

---

## 10. Glossaire

| Terme | Définition |
| --- | --- |
| Kit scolaire | Ensemble de fournitures prédéfini pour un niveau scolaire donné dans un établissement donné. |
| Table de formation de kits | Document définissant, pour un établissement et un niveau, la composition exacte du kit. Devient `kit_version` + `kit_ligne`. |
| Stock de sécurité | Niveau minimal en-deçà duquel un réapprovisionnement doit être déclenché. |
| Stock maximum | Niveau au-delà duquel il n'est pas recommandé de commander. |
| Stock d'alerte | Seuil intermédiaire, supérieur ou égal au stock de sécurité, déclenchant un avertissement préventif. |
| Site | Entité porteuse d'un stock : magasin, école ou stand temporaire. |
| Stand | Point de vente physique installé dans un établissement. |
| Zone | Ensemble géographique de magasins et d'écoles piloté par un superviseur. |
| Avoir / livraison partielle | Situation où une partie de la commande client n'a pu être livrée, avec engagement de livrer le solde. |
| Mouvement compensatoire | Mouvement de sens inverse annulant l'effet d'un document validé, sans le modifier. |
| Non-conformité (NC) | Tout événement indésirable ou écart par rapport à la procédure établie. |
| Visa | Acte de validation d'un acteur à une étape de workflow, remplaçant la signature manuscrite. |
| Périmètre (scope) | Ensemble des sites sur lesquels un utilisateur a le droit d'agir ou de consulter. |
| Vente au détail | Vente d'articles à l'unité hors kit, autorisée à titre exceptionnel. |
| Saisie retroactive | Enregistrement d'une opération avec une date antérieure à la date de saisie, dans le cadre de la procédure papier de secours. |
| Responsive | Interface web unique s'adaptant à la taille de l'écran, du smartphone au poste de bureau. |
| CMUP | Coût moyen unitaire pondéré (méthode de valorisation alternative, non retenue par défaut). |
| F CFA / XOF | Franc CFA, devise unique du système, sans sous-unité. |

---

## 11. Matrice de traçabilité — M00

| Exigence CDC | Traitement dans M00 |
| --- | --- |
| §3 Objectifs stratégiques 1–8 | §1.1 |
| §5.2 Accès mobile pour les équipes terrain | §1.3, §1.4 E-01, §3.14 — traité par une interface web responsive mobile-first, non par une application native |
| §5.3 Exigences non fonctionnelles | §3.15 performance, §3.16 sécurité, §3.14 ergonomie et compatibilité, §3.4 localisation |
| §5.3 Fonctionnement en mode dégradé / hors-ligne | §1.4 E-02 — exigence retirée par le Maître d'ouvrage |
| §6 Périmètre et priorisation MoSCoW | §1.3, §1.4, §1.5 |
| §7.8 Mode dégradé de la vente | §1.4 E-02, §1.6 (mesures organisationnelles de continuité) |
| §7.14 Alertes | §5 |
| §8 Architecture en trois niveaux | §2.1, §2.2 |
| §9 Contraintes techniques | §2.1, §3.14, §3.15 |
| §9 Interopérabilité comptable | §1.4 E-03 — exigence retirée ; exports fichiers conservés en M24 |
| §10 Sécurité (7 points) | §3.16, §3.13, §3.7, §3.5 |
| §11 Sauvegardes (5 points) | §3.17 |
| §14 MCD — entités et relations | §4 |
| §15 Matrice des rôles | §3.7, §3.8, détail dans M02 |
| §19 Livrables | §8 (Definition of Done), livrable « application mobile » retiré |
| §20 Critères de recette 1–10 | 1→§3.12 ; 2→CAL-M00-008/009 ; 3→§3.6 + RG-M00-008 ; 4→§4.3 transferts ; 5→§3.7 ; 6→§3.15 agrégats ; 7→§5 ; **8→retiré (E-02)** ; 9→RG-M00-014 ; 10→§3.15 |
| Annexe D Glossaire | §10 |

---

## 12. Points ouverts nécessitant un arbitrage du Maître d'ouvrage

| N° | Question | Impact | Défaut retenu dans le SRS |
| --- | --- | --- | --- |
| PO-01 | Méthode de valorisation du stock : coût de référence, CMUP ou FIFO ? | M09, M23, calculs de marge | Coût d'achat de référence historisé |
| PO-02 | Définition exacte de la « marge » de pilotage : marge commerciale brute ou nette des dépenses ? | M23 | CA − coût des marchandises vendues − dépenses validées |
| PO-03 | Le module Réunions & comptes rendus (M22) est-il dans le périmètre de la version 1 ? | Charge | Hors version 1, spécifié en léger |
| PO-04 | Une facture normalisée / certifiée DGI est-elle exigée pour les ventes ? | M17, conformité fiscale | Non, reçu interne uniquement |
| PO-05 | Les remises conventionnelles au personnel administratif sont-elles un pourcentage, un tarif dédié, ou les deux ? | M08, M16 | Pourcentage paramétrable par école |
| PO-06 | Un stand temporaire porte-t-il un stock distinct de celui de l'école, ou est-il confondu avec elle ? | M09, M11 | Site distinct, optionnel, rattaché à l'école |
| PO-07 | Qui peut vendre au détail, et sous quel contrôle (le CDC dit « uniquement sur demande insistante ») ? | M16, M02 | Commercial autorisé, traçage systématique et indicateur de suivi |
| PO-08 | Seuil de « dépense importante » déclenchant l'alerte : montant unique national ou par site ? | M20, M25 | Montant national paramétrable, surchargeable par zone |
| PO-09 | Durée de conservation des données de vente avant archivage froid ? | Exploitation | 24 mois en base chaude, archivage ensuite |
| PO-10 | **Nouveau (v1.1)** — Quelle procédure de secours officielle en cas de coupure réseau prolongée sur un stand en période de rentrée ? | Continuité d'activité, RG-M00-019 | Fiche papier de secours conservée, ressaisie retroactive sous 7 jours par un rôle habilité, avec motif et notification au superviseur |
| PO-11 | **Nouveau (v1.1)** — Qui est habilité à la saisie retroactive : chef d'équipe, superviseur, ou les deux ? | M02, M16, M20 | Chef d'équipe et superviseur de zone ; jamais le commercial seul |

---

*Fin du module M00 — version 1.1 (application web uniquement).*
