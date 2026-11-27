🇫🇷 Version française | [🇬🇧 English version](product-context.md)

---

# Contexte produit - JobFlow

## Concept

Une recherche d'emploi sur plusieurs plateformes, c'est jusqu'à une douzaine d'emails d'alerte par jour, chaque fournisseur avec son propre format, et la même annonce relayée par plusieurs d'entre eux. JobFlow transforme cette boîte de réception en un Google Sheet unique, dédoublonné, filtré et toujours à jour : il récupère les alertes dans Gmail, analyse les emails de chaque fournisseur, fusionne les doublons entre fournisseurs, exclut les offres qui ne correspondent pas, ajoute les nouvelles lignes au sheet et archive les emails traités. Le sheet sert ensuite de suivi des candidatures : contacts, statut, relances.

## Utilisateur cible

Un seul chercheur d'emploi, qui lance le pipeline sur sa propre machine, avec son propre compte Gmail et son propre sheet de suivi. Pas de multi-utilisateur, pas de service hébergé.

## Vocabulaire

| Terme | Sens |
|---|---|
| `provider` | Une plateforme d'emploi qui envoie des alertes, avec un parser chacune : LinkedIn, Indeed, France Travail, Jobijoba, JobLeads, Meteojob, Talent.com (un nouveau fournisseur = un module de parser de plus) |
| `ledger` | `logs/email_ledger.json` : chaque email récupéré et son état de traitement (ex. `PENDING`) |
| `Cle_dedup` | Clé de dédoublonnage entre fournisseurs, construite à partir de l'entreprise, de la ville et du titre normalisés, volontairement approximative |
| `Raison_exclusion` | Pourquoi une offre est exclue : `Hors profil` (titre en liste noire, par exemple un poste de directeur hôtelier), `Stage/Alternance`, `Hors stack` |
| `error gate` | Après une synchro en échec, chaque exécution suivante s'arrête tant que l'échec n'a pas été acquitté (`--ack-error`) |
| `Références tab` | L'onglet du sheet dont la mise en forme (listes déroulantes, couleurs) est copiée sur chaque nouvelle ligne |

## Fonctionnalités

- **Récupération Gmail** - récupération OAuth2 des nouvelles alertes, rangées par fournisseur, en incrémental à partir du ledger
- **Parsing par fournisseur** - un parser à base de regex par fournisseur, pas de scraper générique ; extensible en ajoutant un parser
- **Dédoublonnage à deux niveaux** - par Message-ID pour les emails, par `Cle_dedup` pour les annonces relayées par plusieurs fournisseurs
- **Exclusions** - les titres hors profil, les stages et alternances, et les offres hors stack technique sont exclus automatiquement ; ils restent dans le sheet avec leur `Raison_exclusion`, pour que la décision reste visible
- **Localisation** - ville rattachée à son département
- **Synchro du sheet** - nouvelles lignes ajoutées avec la mise en forme du sheet, protégées par l'error gate
- **Suivi des candidatures** - dans le sheet : contacts de chaque candidature et son statut (en attente, relance, etc.)
- **Nettoyage de la boîte** - emails traités marqués comme lus, labellisés et archivés
- **Pipeline fail-fast** - `run_pipeline.py` enchaîne les cinq étapes et s'arrête au premier échec

## Hors périmètre

- Scraper les sites d'emploi : seuls les emails d'alerte sont lus
- Envoyer les candidatures à la place de l'utilisateur
- Relancer automatiquement une synchro en échec : un humain acquitte d'abord l'erreur
- Une interface web : le Google Sheet est l'interface
