# ADR-005: Why RequirementIR?

**Status:** Accepted  
**Context:** Natural-language briefs ("12-person studio, paired desks, oak") must drive SKU selection and satisfaction scoring without putting an LLM on the authority path.

**Decision:** `rulebound/ir.py` extracts a typed RequirementIR (occupancy, workstations, storage, collaboration, accessories, preferences) with rule-based parsers. SKU selection and a 7-metric satisfaction score consume only the IR plus catalog facts.

**Consequences:** Briefs in the released pack are covered. Open-ended prose, sarcasm, and unspecified constraints will not be understood. That is intentional: extraction is inspectable and frozen for a given brief text. Downstream verification still does not trust the IR to waive geometry or price rules.
