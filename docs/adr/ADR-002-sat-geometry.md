# ADR-002: Why SAT geometry?

**Status:** Accepted  
**Context:** Axis-aligned AABB tests miss rotated desks, door swing polygons, and chair pull-out envelopes. False negatives would silently pass overlapping footprints.

**Decision:** All hard spatial rules use convex polygon tests via the Separating Axis Theorem (SAT), plus explicit corridor and swing polygons derived from the room spec. Measurements are millimeters, not pixels.

**Consequences:** Collision depth and clearance deficit are first-class numbers that feed Lyapunov energy Φ. Door swings remain a polygonal approximation of a circular arc (see Known Limitations). SAT is exact for the convex shapes we emit, not for arbitrary concave CAD solids.
