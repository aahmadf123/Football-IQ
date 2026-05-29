# Toledo Label Taxonomy v1 (Phase 0)

This v1 taxonomy maps Toledo football terminology to generic football analytics labels for model training and reporting.

## Core Label Set

| Label Domain | Toledo Term(s) | Generic Term(s) | Phase 0 Values (examples) |
|---|---|---|---|
| Formation | Rocket, Trips, Doubles, Ace | Formation family | 2x2, 3x1, 2x1, Empty, Condensed |
| Motion | Jet, Orbit, Return, Yo-Yo | Pre-snap motion type | Jet, Orbit, Return, Shift, None |
| Route | Glance, Sail, Snag, Mesh, Go | Route concept / route tree | Slant, Out, Corner, Drag, Go, Screen |
| Coverage | Cloud, Buzz, Quarters, 3 Match | Coverage shell + match family | Cover 0, 1, 2, 3, 4, Match |
| Front | Even, Odd, Mint, Bear, Tite | Defensive front structure | 4-down even, 3-down odd, Bear, Tite |
| Pressure | Field Fire, Boundary Dog, Cross | Pressure type | 4-man rush, 5-man pressure, simulated pressure, blitz stunt |
| Run Concept | Inside Zone, Duo, Counter, Dart, GT | Run concept family | Zone, Gap, Power, Counter, QB run |
| Pass Concept | Flood, Smash, Stick, Mesh, Y-Cross | Pass concept family | Flood, Smash, Stick, Mesh, Cross, RPO |
| Event | Explosive, TFL, PBU, Pressure Won | Tagged play event | Snap, handoff, throw, catch, tackle, sack, penalty, TD |

## Labeling Rules
- Apply both **Toledo term** and **generic term** whenever known.
- If uncertain on scheme-level call, set `confidence=low` and assign best-fit generic family.
- Motion labels are assigned at snap.
- Coverage/front/pressure are defense labels from post-snap confirmation.
- Event labels are timestamped and can have multiple tags per play.

## Team Color Classification
- Visual team labels use bounded k=3 CIELab clustering over existing tracklet bounding boxes: `offense`, `defense`, and `official`.
- The first viable frame locks jersey-color centroids; later frames use nearest-centroid assignment and EMA updates with `alpha=0.95` to absorb lighting drift.
- Officials have a stripe-pattern guard, and helmet color is used only as a tiebreaker when jersey CIELab distances are close.
- Fallback: if no readable frames or bbox track points are available, the label stage leaves team classification empty and keeps the existing positional label behavior.
- Limitation: these are visual clusters, not roster-confirmed identities; similar uniforms, occlusion, bad exposure, or too few visible tracklets can still require coach correction.

## JSON Shape (Reference)
```json
{
  "clip_id": "TOL_P0_012",
  "formation": { "toledo": "Trips", "generic": "3x1", "confidence": "high" },
  "motion": { "toledo": "Jet", "generic": "Jet", "confidence": "high" },
  "run_concept": { "toledo": "Inside Zone", "generic": "Zone", "confidence": "medium" },
  "coverage": { "toledo": "Buzz", "generic": "Cover 3 Match", "confidence": "low" },
  "events": ["snap", "handoff", "tackle"]
}
```
