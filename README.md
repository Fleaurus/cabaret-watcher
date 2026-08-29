# Cabaret-watcher — Stadsschouwburg Utrecht

Checkt elk uur de agenda en pusht naar je telefoon zodra er iets **nieuws** bij komt
of een uitverkochte voorstelling **weer kaarten** heeft (returns).

## Gebruik

```bash
python3 ~/cabaret-watcher/watch.py            # check + melden
python3 ~/cabaret-watcher/watch.py --lijst    # hele agenda printen
python3 ~/cabaret-watcher/watch.py --init     # stand resetten, niks melden
```

Opties: `--genre theater` (of `alles`), `--meld-uitverkocht`, `--geen-mac-melding`.

## Config (`config.json`)

| veld | betekenis |
|---|---|
| `genre` | agendafilter, `alles` = hele agenda |
| `ntfy_topic` | geheime topicnaam voor push naar je telefoon |
| `meld_uitverkocht` | ook melden wanneer iets vól raakt |

## Push naar telefoon

Installeer de **ntfy**-app (iOS/Android, gratis) → *Subscribe to topic* → topicnaam uit
`config.json`. Die naam is je enige beveiliging, dus deel 'm niet.

De ntfy-app heeft een **home-screen widget** met de laatste meldingen; op iOS kun je
daarnaast via Shortcuts een widget maken die `watch.py` op afstand triggert.

## Bestanden

- `watch.py` — scraper + diff + notificaties
- `state.json` — laatst geziene stand (verwijderen = opnieuw beginnen)
- `watcher.log` — logregel per run
- `nl.floris.cabaretwatcher.plist` — launchd-job, draait elk uur
