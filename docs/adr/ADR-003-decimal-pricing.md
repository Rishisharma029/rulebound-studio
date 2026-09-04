# ADR-003: Why Decimal pricing?

**Status:** Accepted  
**Context:** Binary floats cannot represent Indian rupee basis-point uplifts without drift. Two runs that differ by ₹1 fail financial audit even if layouts match.

**Decision:** Quotes use `decimal.Decimal` with `ROUND_HALF_UP` quantization to integer INR. Quantity discounts, finish uplifts, labour bands, and freight tiers are table-driven (`RB-PRC-009`–`014`). A quote is blocked if invariants fail (`RB-PRC-013`).

**Consequences:** Line traces cite rule IDs and inputs. Pricing is deterministic for a given placement set and catalog digest, independent of hash seed. It is not a general ERP; tax, FX, and live vendor feeds are out of scope.
