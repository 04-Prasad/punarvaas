# Geographic zones and map performance

The map opens on the zoned demo window, with semi-transparent cells over satellite imagery and place labels. **Streets** offers a road map; **Zones only** keeps the local risk display without external tiles. The **Zone opacity** slider reveals the ground beneath the colours. When **Only where people live** is enabled, empty cells are transparent rather than an opaque rectangular backdrop. The site-selection tab still exposes all assessed cells so candidate ground can be inspected.

State and district navigation remain optional context views. The small locator warns if a supplied window is centred outside the state. Existing cell explanations, habitation selection, candidate sites, links, risk metrics, zone filters, themes and keyboard navigation are retained.

## Rendering changes

The former canvas renderer rebuilt geographic paths and iterated every cell on each hover, pan and zoom repaint. The new adapter retains the console's `HexMap` interface and uses a locally bundled **Leaflet 1.9.4** with a custom canvas `GridLayer`.

- Each original longitude/latitude hex vertex is projected to Web Mercator once per grid load. The API coordinates and risk data are not rewritten.
- A spatial index restricts each tile to its intersecting cells. Canvas tiles are cached and translated/scaled with the basemap during gestures. Risk tile updates wait for gesture completion; one buffer row/column is retained outside the visible tile range.
- Hover and selection update separate vector overlays. They do not rebuild the risk tile layer.
- Metrics, population filtering and zone filtering rebuild colours only when those settings change. Opacity changes use layer compositing without generating new cell geometry.
- Pointer hover is coalesced to animation frames. Status counts are updated after movement rather than on every pointer event.
- Touch pinch zoom, inertial drag, wheel zoom, keyboard navigation and responsive resize use Leaflet. Reduced-motion preferences disable the initial map animations and inertia, with a CSS fallback for preference changes.
- No WebGL, OffscreenCanvas, worker, Google Maps key, or runtime library CDN is required. Satellite and street tiles require a network connection. A visible retry notice covers base tile errors and slow responses; zones remain usable while background tiles fail.

The server and hazard/capacity/priority algorithms were not changed by this update. Web Mercator is a display projection; pipeline cell area and capacity remain based on the existing numerical model.

## Verification and practical limits

The 27 frontend tests pass: 12 existing controller/component regressions, seven state/extent tests updated to use Leaflet's actual CRS math, and eight new tile-layer tests. Coverage includes every stored fixture vertex against Leaflet projection, edge-crossing cells on adjacent tiles, transparent/unpickable open ground, filtered cells, opacity without tile rebuilds, regional framing at five stage dimensions, and stale provider failures after switching basemaps.

`node scripts/benchmark_map.mjs` uses the actual running API data. The following historical sample predates the Odisha geography correction and used the original snapshot. Its recorded local sample is in `out/sih-review/map-performance.json`:

| Pilot | Cells | One-time projection | Candidates for sample zoom-14 tile | Mean tile-index query |
| --- | ---: | ---: | ---: | ---: |
| Chamoli | 20,317 | 22.28 ms | 448 | 0.0187 ms |
| Kendrapara | 27,791 | 16.64 ms | 525 | 0.0093 ms |

Those measurements are **Node CPU/index diagnostics**, not browser frame-rate measurements. They exclude rasterization, GPU/compositor behaviour and network latency. The diagnostic also verified selection at 384 Chamoli and 525 Kendrapara cell centres without changing the projected buffers.

The production Vite build passes, the local frontend/modules and both API grids respond, and one satellite tile was downloaded and visually inspected to verify that the configured source supplies geographic imagery. That tile check is not a screenshot of the application.

The browser connection was unavailable in this session. Therefore actual browser layout, touch gestures and frame rates remain unverified. The intended support target is maintained versions of Chrome, Edge, Firefox and Safari, including Android Chrome and iOS Safari. **Universal browser compatibility or a fixed 60 fps is not certified.** Old browsers without native ES modules or required application language features are outside the existing application's support target.

Before release, check each target browser with both pilots: repeated pan/pinch/scroll zoom, overlay alignment during and after gestures, opacity 0/50/100%, all metrics, district switching, site selection, network failure/retry, reduced motion, and narrow/short viewports. Check that `window.__punarvaas.map.stats.tilesRendered` stays unchanged while hovering an already loaded map; it may increase when new map tiles enter view or filters change.

The original synthetic Kendrapara window was centred outside the reference coastline. A subsequent [Odisha geography correction](ODISHA_GEOGRAPHY_FIX.md) rebuilt its source coordinates and excludes sea, mapped water and wetlands before risk calculations. The renderer continues to display the supplied geographic coordinates without offsets.

## Deployment

Run `npm ci` and `npm run build` in `web`. The existing Vercel build command and `Dockerfile.vercel` already build this directory. Serve `web/dist` with the API available at the same `/api` origin, as in the existing deployment setup. Production hosting should enable normal compression and cache hashed assets; keep index HTML revalidated. A deployment itself was not performed or certified in this change.

The local FastAPI server continues serving native source modules, which work without a build. Refresh the local page after editing. Leaflet is bundled under `web/vendor/leaflet`, including its BSD 2-Clause licence and stylesheet assets.

Configure provider URLs, native zoom limits and attribution in [web/map-config.js](../web/map-config.js) before deploying, then rebuild. The supplied satellite option uses Esri World Imagery plus its reference labels; source metadata was checked on 2026-09-08. Visible attribution includes Esri, Vantor, Earthstar Geographics and the GIS User Community for imagery, and Esri, HERE, Garmin and OpenStreetMap contributors for labels.

Provider availability and usage terms apply separately from the local rendering code. Choose a provider arrangement appropriate to expected production traffic; these public endpoints are not a service-availability commitment. See [Esri World Imagery](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer) and [Esri reference labels](https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer).

The Streets option follows the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/): HTTPS, visible attribution, ordinary browser Referer and HTTP caching, no bulk download or offline prefetch. Do not deploy it behind a policy that strips the Referer. For high traffic, configure an appropriate hosted or self-hosted tile service.

Boundary-data provenance and licensing are retained in [MAP_BOUNDARIES.md](MAP_BOUNDARIES.md). Leaflet's [GridLayer and interaction reference](https://leafletjs.com/reference.html) describes the caching/animation options used here.
