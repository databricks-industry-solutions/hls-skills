# Literature MCP Servers — Discovery & Use

This skill's literature-review step calls **workspace-approved MCP servers** that
Genie Code is connected to. Do not assume any specific server exists — discover
what is connected, then use it. If none is connected, skip the review step and
say so explicitly in the output (no silent degradation).

## Typical HLS-relevant MCP servers
| Server | Purpose | Key identifiers returned |
|--------|---------|--------------------------|
| PubMed / Europe PMC | Published phenotype definitions, validation studies | **PMID**, DOI |
| ClinicalTrials.gov | Trial eligibility criteria for comparable studies | **NCT ID** |
| openFDA | Drug labeling, indications, adverse events | product/label id |

Sources: Databricks Marketplace MCP listings (Public Preview), Databricks-managed
MCP servers, and workspace-hosted custom MCP servers (e.g. a Databricks App).
Availability is workspace-admin controlled.

## Usage rules in this skill
1. **Discover first** — check which literature servers are connected before relying on one.
2. **Cite everything** — every literature-derived claim carries a PMID / NCT ID.
3. **Recommend, don't rewrite** — surface sourced refinements to the user's
   criteria; apply changes only on explicit confirmation.
4. **Degrade loudly** — if no server is available, state that the cohort was built
   from data only, without literature validation.

Confidence: high that Genie Code consumes workspace-approved MCP servers and that
Marketplace MCP is in Public Preview; the specific catalog of available servers is
workspace-dependent and must be checked at runtime.
