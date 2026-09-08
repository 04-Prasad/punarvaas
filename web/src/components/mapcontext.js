import { html, raw, mount } from "../lib/dom.js";
import { locatorGeometry, containsPoint } from "../map/geography.js";

export function renderMapContext(el, { geography, grid }) {
  if (!geography || !grid) { el.hidden = true; return mount(el, ""); }
  el.hidden = false;
  const shape = locatorGeometry(geography, grid.bbox);
  const b = grid.bbox;
  const centreOutside = !containsPoint(geography.state, [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]);
  return mount(el, html`
    <button class="state-locator" data-act="state" title="Show all of ${geography.stateName}"
            aria-label="Show ${geography.stateName} state map, with ${geography.districtName} highlighted">
      <span class="context-state">${geography.stateName}</span>
      <span class="context-district">${geography.districtName} district</span>
      <svg viewBox="0 0 160 116" aria-hidden="true">
        <path class="locator-state" d="${shape.state}" fill-rule="evenodd"/>
        <path class="locator-district" d="${shape.district}" fill-rule="evenodd"/>
        ${shape.point ? raw(`<circle cx="${shape.point[0]}" cy="${shape.point[1]}" r="3.5" class="locator-coverage"/>`) : ""}
      </svg>
    </button>
    <p>Dot: demo coverage. Uncoloured land is not assessed.</p>
    ${centreOutside ? html`<p class="coverage-note"><strong>Demo coordinates need validation:</strong>
      this window is centred outside the reference state outline.</p>` : ""}
    <a href="https://www.geoboundaries.org/" target="_blank" rel="noopener"
       title="DataMeet / ECI: CC BY 2.5 IN. Pathways / LGD: ODbL 1.0. Full attribution in docs/MAP_BOUNDARIES.md">geoBoundaries · DataMeet · Pathways</a>`);
}
