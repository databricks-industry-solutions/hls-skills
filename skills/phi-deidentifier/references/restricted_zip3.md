# Restricted 3-Digit ZIP Prefixes (Safe Harbor)

Under Safe Harbor, the first 3 digits of a ZIP code may be retained **only if**
the geographic unit formed by all ZIPs with the same 3 digits contains **more
than 20,000 people**. For 3-digit prefixes at or below that population, the
initial 3 digits must be changed to `000`.

The classic reference list (17 prefixes, from the original HHS/Census-based
determination) that must be zeroed:

```
036  059  063  102  203  556  692  790  821  823
830  831  878  879  884  890  893
```

Notes & confidence:
- Confidence: high that Safe Harbor requires the >20,000 test and 000 substitution;
  **moderate** on this exact 17-prefix list — it derives from a specific Census
  vintage and HHS guidance and can shift with new population data.
- Before a customer engagement, re-derive the restricted set from current Census
  population by ZIP3 rather than trusting a static list. Treat the list above as a
  demo default and say so in the audit report.
