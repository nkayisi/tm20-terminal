# Corps envoyé aux services tiers — pointages

Contrat du `POST` que `tm20_server` émet vers un service tiers pour
synchroniser les pointages. Document destiné à l'équipe qui écrit le
récepteur.

Les deux exemples ci-dessous ne sont pas recopiés à la main : ils sortent du
code d'envoi lui-même (`AttendanceSyncService._log_to_attendance_data` →
`AttendanceData.to_dict()` → `HTTPAdapter.send_attendance`), rejoué sur des
trames `sendlog` réelles. Ils sont donc exacts au champ près.

## Enveloppe HTTP

```
POST {base_url}{attendance_endpoint}        ex. https://rh.example.com/api/v1/attendance
Content-Type: application/json
Authorization: Bearer <token>               selon auth_type / auth_header_name
```

L'authentification suit `ThirdPartyConfig.auth_type` : `none`, `bearer`,
`api_key` (le token nu dans le header nommé) ou `basic`. Le nom du header est
configurable (`Authorization` par défaut), et `extra_headers` s'ajoute par
dessus.

Codes acceptés comme succès : `200`, `201`, `202`. Tout le reste fait repartir
le lot en file de retry.

## Deux formes de corps, pas une de plus

Le récepteur en service (`data_recev.php`) n'aiguille que sur deux branches :

```php
if (is_object($datareceive))        // UN pointage, l'objet nu
else if (is_array($datareceive))    // un tableau RACINE, qu'il parcourt
```

D'où :

| Taille du lot | Corps envoyé |
| --- | --- |
| 1 pointage | l'objet nu `{ … }` |
| 2 et plus | un tableau **racine** `[ { … }, { … } ]` |

**Jamais d'enveloppe** `{"attendances": [...]}`. `json_decode` en ferait un
objet, le récepteur partirait dans sa branche « un seul pointage », y
chercherait `timestamp` et `external_user_id` qui n'y sont pas, n'insérerait
rien — et répondrait quand même `200`. Le lot entier disparaîtrait sans trace.
Verrouillé par `devices/tests/test_attendance_payload.py`.

Le lot d'un seul élément est le cas normal : la synchronisation tourne chaque
minute et il est rare que deux personnes badgent dans le même intervalle. La
forme tableau est celle qu'on ne voit presque jamais passer.

## Exemple 1 — un pointage seul

Une entrée, agent rapproché côté tiers.

```json
{
  "log_id": 1,
  "terminal_sn": "ZYTJ20128568",
  "enrollid": 7,
  "external_user_id": "EMP-00142",
  "user_name": "KAYISIRIRYA Nelson",
  "timestamp": "2026-10-16T07:02:11+01:00",
  "mode": 8,
  "inout": 0,
  "event": 0,
  "temperature": null,
  "access_granted": true,
  "metadata": {
    "enrollid": 7,
    "time": "2026-10-16 07:02:11",
    "mode": 8,
    "inout": 0,
    "event": 0,
    "temp": null,
    "verifymode": 1
  }
}
```

## Exemple 2 — lot groupé

Trois lignes : une sortie, une entrée, et un événement de porte — seul cas où
`external_user_id` vaut `null` dans un corps émis.

```json
[
  {
    "log_id": 2,
    "terminal_sn": "ZYTJ20128568",
    "enrollid": 7,
    "external_user_id": "EMP-00142",
    "user_name": "KAYISIRIRYA Nelson",
    "timestamp": "2026-10-16T12:31:04+01:00",
    "mode": 8,
    "inout": 1,
    "event": 0,
    "temperature": 36.4,
    "access_granted": true,
    "metadata": {
      "enrollid": 7,
      "time": "2026-10-16 12:31:04",
      "mode": 8,
      "inout": 1,
      "event": 0,
      "temp": 36.4,
      "verifymode": 1
    }
  },
  {
    "log_id": 3,
    "terminal_sn": "ZYTJ20128568",
    "enrollid": 12,
    "external_user_id": "EMP-00210",
    "user_name": "MUKENDI Grace",
    "timestamp": "2026-10-16T12:31:52+01:00",
    "mode": 3,
    "inout": 0,
    "event": 0,
    "temperature": null,
    "access_granted": true,
    "metadata": {
      "enrollid": 12,
      "time": "2026-10-16 12:31:52",
      "mode": 3,
      "inout": 0,
      "event": 0,
      "temp": null,
      "verifymode": 3
    }
  },
  {
    "log_id": 4,
    "terminal_sn": "ZYTJ20128568",
    "enrollid": 0,
    "external_user_id": null,
    "user_name": "User#0",
    "timestamp": "2026-10-16T14:05:09+01:00",
    "mode": 0,
    "inout": 0,
    "event": 0,
    "temperature": null,
    "access_granted": true,
    "metadata": {
      "enrollid": 0,
      "time": "2026-10-16 14:05:09",
      "mode": 0,
      "inout": 0,
      "event": 0,
      "temp": null,
      "verifymode": 0
    }
  }
]
```

## Champs

| Champ | Type | Sens |
| --- | --- | --- |
| `log_id` | entier | Clé du pointage côté `tm20_server`. Stable, utilisable comme clé d'idempotence. |
| `terminal_sn` | chaîne | Numéro de série du terminal émetteur. |
| `enrollid` | entier | ID d'enrôlement **interne au terminal**. Unique par terminal seulement, jamais globalement. `0` = événement de porte. |
| `external_user_id` | chaîne \| `null` | Matricule de l'agent dans le système tiers. `null` uniquement pour un événement de porte. Voir plus bas. |
| `user_name` | chaîne | Nom tel que connu du serveur, ou `User#<enrollid>` si l'enrôlement est inconnu. |
| `timestamp` | ISO 8601 | Heure murale du terminal, offset du site inclus. |
| `mode` | entier | Moyen de vérification : `0`/`1` empreinte, `2` mot de passe, `3` carte, `8` visage, `13` QR code. |
| `inout` | entier | `0` entrée, `1` sortie. Dérivé par le serveur. |
| `event` | entier | `0` normal, `1`–`4` touches F1–F4. |
| `temperature` | décimal \| `null` | Température relevée, si le terminal en remonte une. |
| `access_granted` | booléen | Décision d'accès du serveur au moment du pointage. |
| `metadata` | objet | Trame telle que le terminal l'a émise, `inout` mis à part (voir plus bas). |

## Trois points qui coûtent cher s'ils sont mal lus

### `inout` porte la même valeur aux deux niveaux

Le terminal émet **toujours** `inout: 0` : la spec réserve ce champ au couple
lecteur maître / lecteur esclave (section 6.1-1). C'est donc le serveur qui
tient le sens de passage, par alternance bornée à la journée civile du site —
le premier pointage d'un jour est toujours une entrée, de sorte qu'une sortie
oubliée laisse une journée à un seul pointage au lieu de décaler d'un cran tout
l'historique suivant.

La racine et `metadata` portent désormais cette valeur dérivée, identiques.
Auparavant `metadata.inout` recopiait le `0` du terminal : le même pointage se
lisait « entrée » ou « sortie » selon le niveau ouvert, et une sortie lue dans
`metadata` se comptait comme une entrée sans rien pour le signaler. Voir
l'exemple 2, `log_id: 2` : `inout` vaut `1` aux deux niveaux.

L'alignement se fait à l'envoi, pas à l'insertion : la colonne `raw_payload`
garde en base la trame exacte du terminal, et les pointages déjà enregistrés —
dont le `0` est figé — partent eux aussi avec la bonne valeur.

### `timestamp` est l'heure de l'écran, pas de l'UTC

La base stocke de l'UTC (`USE_TZ=True`), mais le corps porte l'heure murale du
terminal avec l'offset du site (`+01:00`, `Africa/Kinshasa`) : c'est l'heure que
l'agent a lue sur l'écran en badgeant. Un récepteur qui fait
`new DateTime($data->timestamp)->format('H:i:s')` lit les chiffres littéralement
et tombe juste, sans rien convertir.

`metadata.time` est l'horodatage brut du terminal, **sans fuseau**. Ne pas s'en
servir pour dater quoi que ce soit : c'est `timestamp` qui fait foi.

### Sans `external_user_id`, le pointage ne part pas

`external_user_id` est le seul identifiant qui ait un sens dans le système
tiers. `enrollid` ne le remplace pas : c'est un compteur interne au terminal,
il se recycle, et deux terminaux attribuent le même `enrollid` à deux personnes
différentes. Le couple `terminal_sn` + `enrollid` identifie bien la ligne, mais
il n'identifie pas un agent dans le référentiel tiers.

Un pointage dont l'agent n'a pas de matricule n'est donc **pas émis**. Le
récepteur ne verra jamais de chaîne vide dans ce champ, et ne le verra à `null`
que pour les événements de porte.

| Situation | Comportement |
| --- | --- |
| Agent avec `external_id` | Émis normalement. |
| Agent connu, `external_id` non renseigné | Écarté, compté en `skipped`, laissé `pending`. |
| Enrôlement inconnu du serveur | Écarté de même. |
| Événement de porte (`enrollid: 0`) | Émis, avec `external_user_id: null`. |

Écarté ne veut pas dire perdu : le pointage reste `pending` en base. Le jour où
l'`external_id` est renseigné sur l'agent, la passe suivante l'emporte sans
reprise manuelle, horodatage d'origine compris.

Le filtre se fait à l'émission, et c'est délibéré : émis quand même, ces
pointages recevaient un `200` sans que le récepteur ait rien enregistré faute de
matricule, et basculaient `sent`. Ils comptaient pour synchronisés d'un côté et
n'existaient pas de l'autre — la perte silencieuse exacte que le reste de cette
chaîne s'emploie à éviter.

Chaque passe journalise les agents concernés :

```
WARNING  3 pointage(s) ecarte(s), matricule (external_id) absent --
         non rattachables cote API RH : ZYTJ20128568#12, ZYTJ20128568#31
```

Les événements de porte échappent à la règle : aucun agent n'est en cause et
aucun matricule ne leur viendra jamais, donc les retenir les laisserait
`pending` pour toujours.

## Cycle de vie et retry

Chaque pointage porte un `sync_status` : `pending` → `sent`, ou `failed` après
épuisement des tentatives. En cas d'échec HTTP, le lot repart avec un backoff
de 1, 5, 15, 60 puis 240 minutes ; au-delà de 5 tentatives le pointage bascule
en `failed` et attend une relance manuelle (dead-letter).

Un pointage écarté faute de matricule ne suit pas ce cycle : il n'a pas été
émis, donc il ne compte pas comme un échec. Son compteur de tentatives reste à
zéro et il demeure `pending`. Le compteur `skipped` du résultat de
synchronisation est le seul endroit où il apparaît.

Un `200` vaut acquittement : le serveur n'inspecte pas le corps de la réponse
pour décider du statut. Un récepteur qui rejette une ligne doit donc le
signaler par un code HTTP, sinon la ligne est perdue en silence.
