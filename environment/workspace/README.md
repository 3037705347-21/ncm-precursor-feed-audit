# NCM precursor feed reconciliation

The `precursor_feed` package turns four laboratory-adjusted sulfate streams
and one campaign file into a mixed-feed and reaction material sheet.

```bash
python -m precursor_feed.cli data/stocks.csv data/campaign.json /tmp/plan.json
```

The files under `data/` are reproducible simulated records for checking the
command and report shape. They are not plant laboratory records.
