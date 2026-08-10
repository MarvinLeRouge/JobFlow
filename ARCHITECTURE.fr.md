# Architecture

Ce document couvre le *pourquoi* des principaux choix de conception. Pour l'usage et la configuration, voir [README.fr.md](README.fr.md).

---

## Pipeline : quatre étapes indépendantes, fail-fast

```
fetch_gmail.py → rename_eml.py → extract_eml.py → sheets_sync.py
```

Chaque étape est un script autonome avec son propre mode dry-run, piloté par un unique fichier d'état partagé, `logs/email_ledger.json` (indexé par Message-ID), plutôt que par un re-scan complet de `sources/` à chaque run. Ça rend chaque étape idempotente : relancer `rename_eml.py` ou `extract_eml.py` après un échec partiel ne retraite que ce que le ledger marque encore en attente, au lieu de tout retraiter (et redédoublonner, réécrire).

`run_pipeline.py` enchaîne les quatre étapes et s'arrête à la première qui lève une exception, pour qu'une étape suivante ne s'exécute jamais sur un état laissé incohérent par un échec précédent (ex : `sheets_sync.py` ne tourne jamais sur un `import_YYYYMMDD.csv` qu'`extract_eml.py` n'aurait qu'à moitié écrit).

---

## Parseurs providers : un module par provider basé sur des regex, pas un scraper générique

`extract/providers/` contient un fichier par provider d'alerte emploi (France Travail, Indeed, LinkedIn, Meteojob, Jobijoba, Talent.com), chacun avec ses propres regex écrites à la main pour le template HTML spécifique de ce provider.

Un scraper HTML générique piloté par config n'aurait pas valu le coup : ce sont des emails marketing, pas une API publique, et le template de chaque provider a ses propres bizarreries qu'une abstraction partagée aurait dû gérer au cas par cas de toute façon (voir les commentaires inline dans `extract/providers/*.py` — ex : le lien de redirection de Jobijoba qui s'ouvre *avant* le titre auquel il appartient, ou la ligne entreprise/lieu de LinkedIn qui se trouve ~4200 caractères après le lien de l'offre dans le HTML brut). Six petites fonctions testables indépendamment se sont avérées plus simples qu'une seule fonction flexible.

---

## Déduplication : cross-provider, pas seulement cross-email

`rename_eml.py` dédoublonne déjà au niveau email, par Message-ID : le même email d'alerte ne peut pas être traité deux fois. Ça ne suffit pas en soi, car la *même offre* est régulièrement envoyée par plusieurs providers en même temps (ex : LinkedIn et Indeed relayant tous les deux la même annonce).

`extract_eml.py` ajoute une seconde clé de dédup cross-provider (`Cle_dedup`, voir [README.fr.md](README.fr.md#déduplication)) construite à partir de l'entreprise normalisée, de la ville et d'un slug de titre débarrassé des mots vides — volontairement floue (insensible à la casse/aux accents, sans ponctuation) plutôt qu'une correspondance exacte, car le texte titre/entreprise d'une même offre est rarement identique au caractère près entre les templates de deux providers.

---

## Découpage du package `extract/`

`extract_eml.py` était autrefois un unique fichier d'environ 1100 lignes mélangeant nettoyage de texte, résolution géo, les six parseurs providers, filtrage dédup/blacklist/stack, et écriture CSV/logs. Il est maintenant découpé par responsabilité (`text.py`, `filters.py`, `geo.py`, `io.py`, `providers/`), `extract_eml.py` restant un simple orchestrateur. Le découpage a été fait tests d'abord : des tests de caractérisation ont été écrits contre le fichier monolithique d'origine, puis utilisés comme filet de sécurité anti-régression pendant le déplacement du code — voir `tests/extract/`, qui reflète la structure du package.

---

## Le verrou d'erreur de `sheets_sync.py` : bloquer, pas réessayer en espérant

En cas d'échec, `sheets_sync.py` écrit l'erreur dans `logs/sheets_sync_error.json` et chaque run suivant (y compris via `run_pipeline.py`) refuse de resynchroniser tant qu'un humain n'a pas lancé `--ack-error`. Il ne réessaie pas automatiquement, et ne saute pas le run en échec pour continuer avec le suivant.

Le raisonnement : un échec de sync Sheets en plein milieu d'un lot de lignes est exactement la situation où "réessayer la prochaine fois" est dangereux — le plus grand ID d'offre de la feuille (utilisé pour calculer les lignes manquantes) pourrait se retrouver dans un état ambigu, et une re-tentative silencieuse pourrait dupliquer des lignes ou en sauter. Forcer un acquittement explicite échange un peu de friction contre la garantie que personne ne regarde la feuille de suivi en la croyant à jour alors qu'une sync échoue silencieusement depuis des jours.

---

## L'onglet Références : une dépendance vivante, pas un template one-shot

`sheets_sync.py` copie le formatage de cellules (listes déroulantes, couleurs) depuis un onglet dédié "Références" sur chaque ligne nouvellement ajoutée, à *chaque* run de sync — pas une seule fois à la configuration. C'est un contournement, pas la conception d'origine : l'API Sheets s'est avérée ne pas exposer du tout les *couleurs* des règles de validation/liste déroulante, donc le copier-coller en direct depuis deux cellules de référence connues était la seule façon fiable de les reproduire. Le compromis est documenté dans [README.fr.md](README.fr.md#important--longlet-références-est-une-dépendance-active) : la structure de cet onglet devient une dépendance silencieuse que rien ne vérifie ni ne signale en cas de casse.

---

## Compromis connus

- **La résolution ville→département** retombe sur l'API Nominatim (limitée à ~1 req/s, mise en cache en mémoire) pour les villes absentes de la table locale `ville_dept`. C'est une dépendance souple : elle échoue en mode ouvert (retourne un département vide plutôt que de bloquer l'extraction) si Nominatim est injoignable.
- **Les parseurs providers sont fragiles par construction** — basés sur des regex contre des emails reçus par une seule personne, non testés en intégration contre les templates actuels des providers. Quand un provider change son template d'email, le correctif est une fixture de test nouvelle/mise à jour dans `tests/extract/providers/` plus un ajustement de regex, pas une réécriture du scraper.
