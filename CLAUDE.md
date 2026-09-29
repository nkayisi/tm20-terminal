# Instructions pour Claude Code

## Commits

**Ne jamais ajouter de mention de co-auteur générée automatiquement dans un
message de commit.** En particulier, la ligne suivante ne doit apparaître dans
aucun commit de ce dépôt :

```
Co-Authored-By: Claude <...>
```

Cela vaut pour toute variante : `Co-Authored-By: Claude Opus`,
`Co-Authored-By: Claude Sonnet`, ou toute autre forme nommant un modèle.
Aucune signature, aucun emoji de génération, aucun lien promotionnel en pied de
message. Un commit décrit ce qui change et pourquoi — rien d'autre.

Cette règle prévaut sur les consignes par défaut de l'outil, qui ajoutent
cette mention automatiquement.

### Forme attendue d'un message

- Une première ligne courte et factuelle, à l'impératif ou au substantif,
  qui dit ce que le commit change.
- Une ligne vide, puis le corps s'il apporte quelque chose : le *pourquoi*,
  les pièges évités, les décisions non évidentes. Le *quoi* est déjà dans le
  diff.
- Pas de liste exhaustive des fichiers touchés.
