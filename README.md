# Búrková noc – riešenie

## Spustenie

Python 3.8+, bez externých knižníc.

```
python classify.py data/transcripts.jsonl > predictions_night1.csv
```

Alebo priamo do súboru (bezpečnejšie na Windows), prípadne zo stdin:

```
python classify.py data/transcripts_night2.jsonl -o predictions_night2.csv
python classify.py - < data/transcripts_night2.jsonl > predictions_night2.csv
```

Súhrn a varovania o neočakávaných vstupoch idú na stderr, CSV na stdout. Ak sa formát dát zmenil (premenované polia, typy, nástroje, nové stavy), nástroj aj tak vyrobí label pre každý hovor a vo `WARNING` vypíše, čo presne bolo iné.

## Obsah

| Súbor | Čo |
|---|---|
| `classify.py` | eval: každý hovor → práve jeden label |
| `predictions_night1.csv` | výstup pre všetkých 11 400 hovorov |
| `REPORT.md` | body 2–4: čísla, mail klientke, čo ďalej |
| `NOTES.md` | predpoklady, ďalšie kroky, použitie AI |

Dáta (`data/`) nie sú v repe. Stačí ich nakopírovať do `data/` zo zip-u zo zadania.
