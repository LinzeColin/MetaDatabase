# Source and evidence policy

## Goal

Build a claim-level evidence graph that distinguishes independent verification from repeated narrative.

## Source tiers

### Tier A — primary, authoritative

- regulatory filings and exchange announcements;
- audited financial statements;
- official earnings releases and transcripts;
- customer and supplier contractual disclosures;
- government procurement, customs, permit, court, patent, and standards records;
- official technical documentation and certification databases;
- direct price, capacity, production, or shipment data from the responsible authority.

### Tier B — strong institutional or technical

- industry associations with disclosed methods;
- peer-reviewed papers and official conference proceedings;
- rating agencies and reputable market databases;
- technical presentations by named engineers or customers;
- government-sponsored research and national laboratories.

### Tier C — reputable secondary

- established financial press;
- specialized trade publications;
- sell-side or independent research with methods and sources;
- named expert interviews.

### Tier D — lead-generation OSINT

- job postings;
- partner pages and website changes;
- distributor checks;
- conference hallway commentary;
- social-media posts by identified specialists;
- satellite, shipping, or channel observations without official confirmation.

### Tier E — unverified

- anonymous claims;
- screenshots without provenance;
- rumor accounts;
- copied summaries;
- AI-generated claims without inspectable sources.

Tier D and E may generate hypotheses. They do not independently confirm a critical investment claim.

## Critical-claim rule

A critical factual claim should have:

- at least two independent source origins;
- at least one Tier A source when reasonably available;
- a current timestamp appropriate to the claim's decay rate;
- an explicit contradiction search;
- numerical units and definitions that reconcile.

Examples of critical claims:

- sole-source or market-share status;
- capacity, utilization, lead time, and backlog;
- customer identity or qualification;
- contract value and enforceability;
- ownership of IP, permits, or assets;
- segment revenue exposure;
- financing and dilution;
- current valuation and price-sensitive data.

## Independence rule

Sources are not independent when they derive from the same origin, such as:

- multiple news articles quoting one company release;
- an analyst note and a media article quoting that note;
- social posts linking the same conference slide;
- a database populated from the same filing.

Use `independence_group` in the evidence ledger.

## Fact taxonomy

- `fact` — directly supported and reproducible.
- `inference` — reasoned conclusion from cited facts.
- `assumption` — model input not established by evidence.
- `forecast` — future outcome with a probability or range.

Never write an inference as a fact.

## Freshness

Suggested maximum age before mandatory refresh:

| Claim | Refresh window |
|---|---:|
| price, market cap, options, short interest | 1 trading day |
| earnings, guidance, share count | latest reporting period |
| customer/contract status | 30–90 days or latest filing |
| capacity, lead time, allocation | 30–90 days in fast cycles |
| permits and construction | latest milestone |
| structural technical role | 6–18 months, sooner at architecture transitions |
| legal ownership or regulation | current law/registry |

## Negative evidence search

Every case must search for:

- announced competing capacity;
- substitute technologies and qualification milestones;
- customer dual sourcing and in-house programs;
- contract termination or cost-down clauses;
- inventory accumulation and falling lead times;
- quality, yield, recall, or certification failures;
- financing gaps, covenants, dilution, warrants, and SBC;
- sanctions, export controls, litigation, environmental limits;
- discrepancies between company claims and customer filings.

## Evidence ledger minimum fields

```json
{
  "claim_id": "C-001",
  "claim": "...",
  "claim_type": "fact",
  "critical": true,
  "status": "open",
  "sources": [
    {
      "url": "...",
      "publisher": "...",
      "date": "YYYY-MM-DD",
      "tier": "A",
      "source_type": "regulatory_filing",
      "independence_group": "issuer-filing-2026Q2",
      "stance": "supports",
      "excerpt_or_locator": "page/section",
      "limitations": ""
    }
  ],
  "contradictions": [],
  "confidence": "medium"
}
```

## Citation discipline

- Cite the claim, not a paragraph of unrelated claims.
- Prefer stable primary links.
- Record page, section, table, or line locators.
- Quote sparingly; paraphrase and preserve numerical definitions.
- Preserve archived copies or hashes where lawful and practical.
- Never fabricate a citation or infer a private relationship from a logo.
