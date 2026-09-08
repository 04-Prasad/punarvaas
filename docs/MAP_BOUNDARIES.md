# State maps

The console places the existing demo risk cells over satellite or street tiles, with state and district outlines for context. See [terrain map implementation and verification](TERRAIN_MAP.md).

| Pilot | State | Default view |
| --- | --- | --- |
| Chamoli | Uttarakhand | Zoned demo area over satellite imagery |
| Kendrapara | Odisha | Zoned demo area over satellite imagery |

Use **State**, **District**, or **Risk area** above the map to change extent. The small state locator marks the demo window; clicking it returns to the state view. Zoom, pan, cell selection, habitation navigation, metrics, and zone filters remain available. Display controls collapse at regional scales and can be opened manually. Press `f` while the canvas is focused to fit the risk area.

The original state-map feature did not change hazard scores, population estimates, capacity numbers, pipeline geometry, or planning results. For display, every geographic hex vertex is projected to Web Mercator, the same coordinate system as the imagery and street tiles. Screen areas are not survey measurements. The subsequent [Odisha geography correction](ODISHA_GEOGRAPHY_FIX.md) rebuilt the coastal source data and screens whole cells against a land mask before analysis. Land outside the demo window has **no risk assessment** in this prototype.

Chamoli's window centre (79.59 E, 30.56 N) is inside both reference boundaries. Kendrapara's former synthetic centre (86.98 E, 20.635 N) was outside both, offshore. The corrected window is centred at 86.78 E, 20.61 N on land. The locator continues to flag any supplied window centred outside the state outline.

## Boundary provenance and licences

Downloaded on 2026-09-08 through [geoBoundaries](https://www.geoboundaries.org/). Source metadata is preserved in [boundary-sources.json](../web/src/map/boundary-sources.json). The bundled features retain their source properties and identifiers.

| Layer | Source attribution | Licence | Reference year reported by source |
| --- | --- | --- | --- |
| State / ADM1 | DataMeet India community; Election Commission of India; distributed by geoBoundaries | [Creative Commons Attribution 2.5 India](https://creativecommons.org/licenses/by/2.5/in/) | 2011 |
| District / ADM2 | Pathways Data Pvt. Ltd.; lgdirectory.gov.in; distributed by geoBoundaries | [Open Data Commons Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) | 2021 |

Original downloads:

- [India simplified ADM1, source commit 9469f09](https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/IND/ADM1/geoBoundaries-IND-ADM1_simplified.geojson)
- [India simplified ADM2, source commit 9469f09](https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/IND/ADM2/geoBoundaries-IND-ADM2_simplified.geojson)

Changes to the boundary data: selected the two pilot states and districts, normalized names for matching, grouped features by pilot, and rounded coordinates to five decimal places. No vertices were moved for alignment with demo cells. The derived district database is made available under ODbL 1.0 in the readable [state-boundaries.js](../web/src/map/state-boundaries.js); the state features retain CC BY 2.5 IN attribution and terms. These licences concern the boundary data, not the application's original code. These simplified reference outlines are not certified current administrative or cadastral boundaries.

To refresh the bundled data, run `python scripts/fetch_map_boundaries.py` with network access and review the new metadata and geometry. Refreshing uses the provider's current release and can change the reported reference years. Boundary outlines remain bundled. Satellite and street backgrounds use external tile requests configured in `web/map-config.js`; **Zones only** disables these requests.

## Verification

- Seven new map tests cover pilot selection, state/district fit across five map-stage dimensions, coordinate preservation through zoom, filter/refit behaviour, polygon holes/islands, locator coordinates, and the coastal coverage mismatch.
- The existing 12 frontend regression tests remain passing.
- Eight tiled-overlay regressions verify alignment against Leaflet's projection, tile seams, transparent ground, filtering, opacity updates, bounded buffering, and failed/stale basemap requests.
- The Vite production build succeeds with the bundled boundaries.
- Browser connection was unavailable. The extent tests check numeric projection bounds; they do not certify visual layout, touch behaviour or browser rendering.
