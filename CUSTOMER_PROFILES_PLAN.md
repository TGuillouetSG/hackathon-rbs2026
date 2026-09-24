# Two-customer demo plan

## Agreed behavior

- The demo has exactly two synthetic customer profiles: Annie and one new customer.
- `/` opens Annie's summary by default and shows a visible customer switcher.
- Each customer has a direct link to their summary and RDV page. The selected customer survives navigation, refresh, and back navigation.
- `/rdv` starts CSV analysis automatically for the selected customer.
- The page keeps the same overall layout for both customers. Facts, alerts, and suggested actions appear only when the selected profile supports them.
- If CSV analysis fails, the profile-based brief remains visible and the generated-topics area shows an error.
- Annie retains the missing-contact-information scenario, but unverified personal details become invented data. The second customer has complete contact details and transaction signals consistent with a possible property purchase. Do not present that possibility as a confirmed project.

## Implementation steps

1. **Define the demo data contract.** Give each customer a stable, URL-safe ID, display name, identity and relationship facts, contact and product facts, interaction history, and an explicit path to that customer's synthetic transaction CSV. Mark optional facts as absent rather than inventing placeholder values. Store the two profiles in one reviewed fixture, for example `starter/data/customers.json`, and use one CSV per customer with the existing agent-compatible columns.
2. **Resolve selection centrally.** Add a small customer catalog loader and lookup in `starter/server/`. Support `/?customer=<id>` and `/rdv?customer=<id>`, with Annie as the documented default when the parameter is absent. Return 404 for an unknown ID. Build links with Flask's `url_for` so the selected ID is carried to the RDV page and back. Add a visible, labelled switcher on the summary; show the current customer clearly on the RDV page.
3. **Render the summary from the selected profile.** Replace customer-specific values in `index.html`: identity, badges, contact and digital status, branch and adviser, relationship date, products, powers, and interactions. Calculate age and relationship tenure from dates, or omit them when dates are absent. Keep application-wide placeholders, such as adviser authorization messages, separate from customer facts.
4. **Render the RDV brief from the same profile.** Replace the hardcoded identity, facts, points of attention, and pre-meeting actions in `rdv.html`. Use explicit rules or evidence-backed fixture fields for recommendations. Render this portion immediately; reserve the workflow loading state for generated topics. Update French copy so it fits either customer without assuming gender.
5. **Bind analysis to the selected customer.** Pass the customer ID from `/rdv` to `POST /api/rdv/workflow`; resolve it on the server against the catalog and use only that customer's configured CSV. Remove `RDV_CSV_PATH` as the customer selector. Never accept a CSV path from the browser. Keep the agent's per-run output directory behavior, so simultaneous runs do not overwrite each other.
6. **Handle partial results and failures.** Keep the profile brief visible throughout analysis. Show up to three valid generated topics when available. If a successful agent run returns none, calculate a narrow topic from repeated external transfers or explicit property-project costs in that customer's CSV. Show an error confined to the topics area if the run fails. Do not show Annie's static alerts or values as a fallback for the second customer.
7. **Document and verify the demo.** Update `starter/README.md` with the two profiles, default, direct-link format, CSV mapping, and run command. Add route/template tests for default, each ID, unknown ID, and preserved navigation. Add workflow tests that assert each ID selects its own CSV, including two sequential requests and an analysis failure. Manually inspect both pages at desktop and narrow widths, then run both end-to-end RDV analyses in the configured demo environment.

## Acceptance checks

- Switching profiles changes all customer facts on `/` and `/rdv`; Annie appears on Marc's summary only as an option in the customer switcher, never as Marc's fact or post-analysis JavaScript state.
- A direct RDV link, refresh, and return to summary all retain the same customer.
- Each workflow request analyses the CSV assigned to its selected customer; an invalid ID cannot select a file.
- The new customer's complete contact details do not trigger Annie's contact warnings. Property purchase is phrased as a signal to explore, with the supporting transaction evidence visible in generated topics.
- A failed analysis leaves the selected customer's profile brief readable and displays a clear topics error.
