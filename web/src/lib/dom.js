/**
 * The smallest useful DOM helper set.
 *
 * `h()` builds elements; `html` escapes interpolations. Two rules, because the
 * console renders text that came from a database:
 *
 *   · anything interpolated into markup goes through `esc()`. A village name is
 *     data, and data is never trusted as markup — even data we generated, since
 *     the whole point of this system is that the inputs get replaced with real
 *     ones from someone else's GIS.
 *   · SVG we build ourselves is inserted with `raw()`, explicitly, so every
 *     unescaped insertion is greppable.
 */
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const RAW = Symbol("raw");
export const raw = (s) => ({ [RAW]: String(s ?? "") });
const flat = (v) => Array.isArray(v) ? v.map(flat).join("")
  : (v && v[RAW] !== undefined) ? v[RAW]
  : (v === null || v === undefined || v === false) ? "" : esc(v);

/** Tagged template that escapes by default. */
export const html = (strings, ...vals) =>
  raw(strings.reduce((out, s, i) => out + s + (i < vals.length ? flat(vals[i]) : ""), ""));

export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = (v && v[RAW] !== undefined) ? v[RAW] : esc(v);
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(3)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid && kid[RAW] !== undefined ? fragFrom(kid[RAW]) : (kid.nodeType ? kid : String(kid)));
  }
  return el;
}

function fragFrom(markup) {
  const t = document.createElement("template");
  t.innerHTML = markup;
  return t.content;
}

/** Replace a container's children with markup or nodes. */
export function mount(el, content) {
  el.replaceChildren();
  if (content === null || content === undefined) return el;
  el.append(content && content[RAW] !== undefined ? fragFrom(content[RAW])
            : (content.nodeType ? content : String(content)));
  return el;
}

export const qs = (sel, root = document) => root.querySelector(sel);
export const qsa = (sel, root = document) => [...root.querySelectorAll(sel)];

export function on(root, type, selector, fn) {
  root.addEventListener(type, (e) => {
    const t = e.target.closest(selector);
    if (t && root.contains(t)) fn(e, t);
  });
}

/** requestAnimationFrame-coalesced callback — for pointer and resize storms. */
export function raf(fn) {
  let queued = false, lastArgs;
  return (...args) => {
    lastArgs = args;
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; fn(...lastArgs); });
  };
}

export const debounce = (fn, ms = 180) => {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
};
