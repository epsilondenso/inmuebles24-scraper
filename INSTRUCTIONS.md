# Operational runbook

For portfolio overview and features, see [README.md](README.md).

## Resume after Cloudflare block

```bash
python main.py resume
```

## Re-export with latest parser

Close `properties.xlsx` in Excel first, then:

```bash
python main.py extract --force --output-dir output/proof_test
```

## Cost estimate (~10,000 listings)

| Item | Estimate |
|------|----------|
| Residential proxy (optional) | $30–80 USD |
| Local execution | Free |
