/**
 * Entry point.
 *
 * No bundler, no transpiler, no build step. The console is served as the files
 * that were written, which means what a reviewer reads is exactly what the
 * browser runs — and a district IT department can deploy it by copying a folder.
 * Native ES modules over HTTP/1.1 cost a handful of extra requests on first load;
 * that is a smaller price than a toolchain nobody in the office can rebuild.
 */
import { Console } from "./console/app.js";
import * as Leaflet from '../vendor/leaflet/leaflet-src.esm.js';

globalThis.PunarvaasLeaflet = Leaflet;

const app = new Console();
window.__punarvaas = app;          // one handle, for debugging in the field
app.start();

// A module-level throw would otherwise vanish into the devtools console on a
// machine with no devtools open.
addEventListener("error", (e) => {
  if (document.querySelector("#banner")?.hidden !== false) {
    const b = document.querySelector("#banner");
    if (!b) return;
    b.hidden = false;
    b.className = "banner bad";
    b.textContent = `Console error: ${e.message}`;
  }
});
