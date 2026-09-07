# Ubiquitous Language

## Buyer and decision

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Primary Buyer** | A South Florida general-contractor/developer acquisition or preconstruction lead evaluating whether to pursue or control a parcel. | Generic user, contractor |
| **Opportunity** | A parcel-specific acquisition candidate paired with one explicit Development Program. | Property, deal |
| **Decision Recommendation** | The evidence-bound outcome `pursue`, `control`, `pass`, or `abstain`. | AI answer, go/no-go |
| **Verified Ceiling** | The highest acquisition price supported by verified Local Truth, market evidence, underwriting inputs, and municipality support receipts. | Offer price, appraisal, estimated value |
| **Decision Contract** | The shared inputs, evidence rules, dimensions, and outputs used by private investors, land developers, and the Primary Buyer. | Investor mode, contractor mode |

## Readiness and release

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Processing Status** | Whether deterministic processing is not started, running, complete, or blocked. | Readiness |
| **Decision Readiness** | Whether the evidence set is blocked, provisional, or ready to drive a decision. | Processing status, confidence |
| **Pricing Readiness** | Whether the result is unpriced, provisional, or evidence-supported. | Decision readiness |
| **Review Status** | Whether a distinct Reviewer has approved the result for release. | Ready, complete |
| **Release Status** | Whether a result is blocked, eligible, or released for external sharing. | Published, approved |
| **Decision Status** | The aggregate blocked, provisional, or released state that may never exceed its component dimensions. | Workflow status |

## Coverage and evidence

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Municipality Lane** | One named municipality or unincorporated jurisdiction evaluated independently for support. | County coverage |
| **Support Coordinate** | One Municipality Lane × Workflow × Fact Family tuple. | County flag, market boolean |
| **Evidence Receipt** | An identifier issued by the trusted runtime registry and bound to one county, Municipality Lane, Workflow, Fact Family, source, evidence digest, issuer/key version, and validity window. Reuse across coordinates is forbidden. | Checkbox, arbitrary string, self-report |
| **Supported** | A Support Coordinate with one or more passing Evidence Receipts. | Available, live |
| **Unsupported** | The default state of a Support Coordinate before its evidence gates pass. | Not configured |
| **Private Beta** | The paid, narrowly labeled Miami-Dade release after every required Miami-Dade Support Coordinate passes. | South Florida launch |
| **External Action** | Seller contact, lender delivery, offer submission, contract language, or fund movement outside PlotLot. | Automation |

## Relationships

- One **Opportunity** belongs to exactly one **Municipality Lane** and one Development Program.
- A **Verified Ceiling** exists only when **Decision Readiness** is ready and **Pricing Readiness** is evidence-supported.
- A released **Decision Status** requires complete processing, ready evidence, evidence-supported pricing, distinct review approval, and released **Release Status**.
- A county contains multiple **Municipality Lanes**, but county membership never creates **Supported** coverage.
- Miami-Dade, Broward, and Palm Beach promotion decisions are independent.
- Every **Support Coordinate** begins **Unsupported** and can become **Supported** only through Evidence Receipts.
- A repeated identical promotion is idempotent; duplicate coordinates, duplicate receipts, and conflicting re-promotions fail closed.
- Aggregate **Decision Status**, recommendation, and release are derived from the five component dimensions and evidence; callers cannot widen them.

## Example dialogue

> **Developer:** “The Miami-Dade adapter is live. Can we call the county supported?”
>
> **Domain expert:** “No. Each **Municipality Lane** still needs passing **Support Coordinates** for every required Workflow and Fact Family.”
>
> **Developer:** “If the Miami lanes pass, can the **Private Beta** expose the **Verified Ceiling**?”
>
> **Domain expert:** “Only after **Decision Readiness**, **Pricing Readiness**, **Review Status**, and **Release Status** independently pass. Broward and Palm Beach remain **Unsupported**.”

## Flagged ambiguities

- “Ready” previously mixed processing, evidence, pricing, review, and release; use the five named dimensions.
- “County supported” previously implied that one adapter or source path granted coverage; use **Support Coordinate** and **Municipality Lane**.
- “Price” could mean an assumption, estimate, offer, or evidence-backed limit; use **Verified Ceiling** only for the decision-driving maximum supported by evidence.
- “Automatic outreach” could include internal drafting or an external business action; only signed webhooks for already released results are automatic, while every **External Action** remains disabled.
