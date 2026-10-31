"use strict";
// Exercise Hub rendering and actions with a tiny DOM/fetch harness (no browser/network).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const hubHtml = fs.readFileSync(path.join(__dirname, "support_web.html"), "utf8");
assert.match(hubHtml, /\.hub-faceplate-current\{[^}]*flex-direction:column;[^}]*align-items:stretch;/,
  "current faceplate and revision label stack vertically at every viewport width");
assert.match(hubHtml, /\.hub-faceplate-current img\{[^}]*width:100%;[^}]*height:auto;/,
  "current stock preview fills its parent width with natural aspect ratio");
assert.doesNotMatch(hubHtml, /\.hub-faceplate-current img\{[^}]*(?:width:190px|height:72px)/,
  "current artwork must not regress to a fixed-size thumbnail");
assert.match(hubHtml, /\.hub-faceplate-device-option img\{[^}]*width:100%;[^}]*height:auto;/,
  "alternative revision previews also retain their aspect ratios");

class Element {
  constructor(tag = "div") {
    this.tag = tag;
    this.value = "";
    this.children = [];
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.style = {};
    this.listeners = {};
    this.classes = new Set(["hidden"]);
    this.classList = {
      add: name => this.classes.add(name),
      remove: name => this.classes.delete(name),
      contains: name => this.classes.has(name),
      toggle: (name, force) => {
        if (force === undefined ? !this.classes.has(name) : force) this.classes.add(name);
        else this.classes.delete(name);
      },
    };
  }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  setAttribute(name, value) { this[name] = value; }
  close() { this.open = false; }
  showModal() { this.open = true; }
  remove() { this.removed = true; }
  click() { if (this.listeners.click) return this.trigger("click"); this.clicked = true; }
  replaceChildren(...items) { this.options = items; this.children = items; }
  append(...items) { this.children.push(...items); }
  trigger(name) { assert.ok(this.listeners[name], name); return this.listeners[name](); }
}

async function run() {
  const ids = [
    "faceplateUpgradeSection", "faceplateUpgradeExpanded", "faceplateUpgradeSwitchSelect",
    "faceplateUpgradeCollapsedButton", "faceplateUpgradeKeepButton", "faceplateUpgradeApplyButton",
    "faceplateUpgradeMessage", "faceplateUpgradeDevice", "faceplateUpgradeOldImage",
    "faceplateUpgradeHeading", "faceplateUpgradeOldTitle",
    "faceplateUpgradeNewImage", "faceplateUpgradeOldDescription",
    "faceplateUpgradeNewDescription", "faceplateUpgradeExplanation", "faceplateRevisionList",
  ];
  const nodes = Object.fromEntries(ids.map(id => [id, new Element()]));
  const hosts = ["snmp:SW3", "snmp:SW5"].map(deviceKey => {
    const element = new Element();
    element.dataset.switchKey = deviceKey;
    return element;
  });
  const docEvents = {};
  const winEvents = {};
  let timer = null;
  let reads = 0;
  let resets = 0;
  let failReset = false;
  const selections = [{
    device_key: "snmp:SW3", base_profile: "native_SW3", switch_name: "SW3",
    model: "Model A", verified_current: true, current_file: "old-a.png",
    current_sha256: "a".repeat(64), current_path: "faceplates/old-a.png",
    current_version: "", current_geometry_sha256: "",
    options: [{filename:"old-a.png",version:"sha-"+ "1".repeat(20),
      sha256:"a".repeat(64),geometry_sha256:"c".repeat(64),path:"faceplates/old-a.png"}],
  },{
    device_key: "snmp:SW5", base_profile: "", model: "", verified_current: false,
    current_file: "", current_sha256: "", current_path: "", options: [],
  }];
  let offers = [
    {device_key: "snmp:SW3", base_profile: "native_SW3", switch_name: "SW3", model: "Model A",
      current_file: "old-a.png", available_file: "new-a.png",
      current_sha256: "a".repeat(64), available_sha256: "b".repeat(64), collapsed: false,
      versions: [
        {filename:"new-a.png",version:"2.7.90",sha256:"a".repeat(64),geometry_sha256:"c".repeat(64),path:"faceplates-old/2.7.90/new-a.png"},
        {filename:"new-a.png",version:"2.7.93",sha256:"b".repeat(64),geometry_sha256:"d".repeat(64),path:"faceplates/new-a.png"}]},
    {device_key: "snmp:SW4", base_profile: "native_SW4", switch_name: "SW4", model: "Model B",
      current_file: "old-b.png", available_file: "new-b.png",
      current_sha256: "c".repeat(64), available_sha256: "d".repeat(64), collapsed: false},
  ];
  const document = {
    hidden: false,
    getElementById: id => nodes[id],
    createElement: tag => new Element(tag),
    body: new Element("body"),
    querySelectorAll: selector => selector === ".hub-device-faceplates[data-switch-key]" ? hosts : [],
    addEventListener: (name, fn) => { docEvents[name] = fn; },
  };
  const window = {
    confirm: () => true,
    addEventListener: (name, fn) => { winEvents[name] = fn; },
    setInterval: (fn, delay) => { assert.equal(delay, 300000); timer = fn; },
    setTimeout: fn => fn(),
  };
  const fetch = async (_url, request) => {
    if (!request || !request.method || request.method === "GET") {
      reads++;
      return {ok: true, json: async () => ({ok: true, offers, selections})};
    }
    const body = JSON.parse(request.body);
    const offer = offers.find(item => item.device_key === body.device_key &&
      item.base_profile === body.base_profile &&
      item.available_sha256 === body.available_sha256);
    assert.ok(offer, "exact per-switch offer");
    assert.equal(body.base_profile, offer.base_profile, "exact artwork scope");
    if (body.action === "export") {
      return {ok: true, json: async () => ({
        ok: true, action: "exported", base_profile: offer.base_profile,
        geometry: {schema: "switch-vision-interactive-calibration-v1", ports: {"1": {center: [12,24]}}},
      })};
    }
    if (body.action === "keep") offer.collapsed = true;
    else if (body.action === "upgrade") {
      resets++;
      if (failReset) return {ok: false, json: async () => ({error: "Core artwork approval failed"})};
      offers = offers.filter(item => item !== offer);
    } else throw Error("unexpected action");
    return {ok: true, json: async () => ({ok: true, calibration_reset: body.action !== "keep"})};
  };
  let exportedBlob = null;
  const script = fs.readFileSync(path.join(__dirname, "faceplate_upgrades.js"), "utf8");
  vm.runInNewContext(script, {document, window, fetch, Blob, URL: {
    createObjectURL: blob => {exportedBlob = blob;return "blob:fixture";}, revokeObjectURL: () => {},
  }, endpoint: x => x});
  const drain = () => new Promise(resolve => setImmediate(resolve));
  await drain();
  const get = id => nodes[id];

  assert.equal(hosts[0].children[0].textContent, "Faceplates");
  assert.ok(hosts[0].children.length >= 3, "single faceplate row should include current artwork");
  assert.match(hosts[0].children[2].children[1].textContent,
    /Currently selected: old-a.png/, "single current revision remains visible");
  assert.ok(!hosts[0].children.some(item => item.className === "hub-device-faceplate-versions"),
    "no extra selector for one choice");
  assert.equal(hosts[1].children[0].textContent, "Faceplates");
  assert.match(hosts[1].children[2].textContent, /not verified by Core/,
    "registered device without verified art shows a safe status");
  assert.equal(get("faceplateUpgradeSwitchSelect").options.length, 2);
  assert.equal(get("faceplateRevisionList").options.length, 2, "both Core revisions expandable");
  assert.match(get("faceplateRevisionList").options[0].options[1].src, /faceplates-old\/2\.7\.90\/new-a\.png/);
  assert.ok(get("faceplateRevisionList").options[1].options[2].listeners.click, "revision selector wired");
  assert.equal(get("faceplateUpgradeDevice").textContent, "SW3 · Model A · Native dashboard");
  assert.match(get("faceplateUpgradeOldImage").src, /old-a\.png\?v=/);
  assert.ok(!get("faceplateUpgradeSection").classList.contains("hidden"));
  get("faceplateUpgradeSwitchSelect").value = "snmp:SW4@native_SW4";
  get("faceplateUpgradeSwitchSelect").trigger("change");
  assert.equal(get("faceplateUpgradeDevice").textContent, "SW4 · Model B · Native dashboard");
  get("faceplateUpgradeKeepButton").trigger("click");
  await drain();
  assert.ok(get("faceplateUpgradeExpanded").hidden, "keep collapses the selected switch");
  assert.equal(resets, 0, "keep cannot call Core reset");
  get("faceplateUpgradeCollapsedButton").trigger("click");
  assert.ok(!get("faceplateUpgradeExpanded").hidden, "red button only reopens");
  assert.equal(resets, 0);
  const currentDialog = () => document.body.children.filter(
    item => item.tag === "dialog" && !item.removed).at(-1);
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  let dialog = currentDialog();
  assert.ok(dialog?.open, "upgrade opens a real three-choice popup");
  assert.equal(dialog.children[4].children[0].textContent, "Export Geometry");
  assert.equal(dialog.children[4].children[1].textContent, "Cancel");
  assert.equal(dialog.children[4].children[2].textContent, "Confirm Upgrade");
  dialog.children[4].children[0].trigger("click");
  await drain();
  assert.match(dialog.children[3].textContent, /Geometry export started/);
  assert.ok(exportedBlob, "browser download must contain real Geometry bytes");
  assert.deepEqual(JSON.parse(await exportedBlob.text()), {
    schema: "switch-vision-interactive-calibration-v1", ports: {"1": {center: [12,24]}},
  }, "exported file must be valid JSON and include current Geometry");
  assert.equal(resets, 0, "export must never approve or reset");
  dialog.children[4].children[1].trigger("click");
  await drain();
  assert.equal(resets, 0, "cancel cannot reset a switch");
  failReset = true;
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  dialog = currentDialog();
  dialog.children[4].children[2].trigger("click");
  await drain();
  assert.equal(resets, 1);
  assert.match(get("faceplateUpgradeMessage").textContent, /Core artwork approval failed/);
  assert.equal(offers.length, 2, "failed action retains the offer");
  failReset = false;
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  dialog = currentDialog();
  dialog.children[4].children[2].trigger("click");
  await drain();
  assert.equal(resets, 2);
  assert.equal(offers.length, 1);
  assert.equal(get("faceplateUpgradeDevice").textContent, "SW3 · Model A · Native dashboard");
  assert.ok(get("faceplateUpgradeSwitchSelect").classList.contains("hidden"),
    "single remaining offer needs no switch selector");

  const before = reads;
  winEvents.focus();
  await drain();
  assert.ok(reads > before, "window focus triggers fresh check");
  const beforeTick = reads;
  timer();
  await drain();
  assert.ok(reads > beforeTick, "periodic check triggers");
  const beforeVisible = reads;
  docEvents.visibilitychange();
  await drain();
  assert.ok(reads > beforeVisible, "tab visibility triggers check");
  offers = [{
    device_key: "snmp:SW3", base_profile: "native_SW3", switch_name: "SW3", model: "Model A",
    current_file: "same.png", available_file: "same.png",
    current_sha256: "a".repeat(64), available_sha256: "b".repeat(64),
    current_preview: "faceplate-history/" + "a".repeat(64) + "/same.png",
    same_filename: true, collapsed: false,
  }];
  timer();
  await drain();
  assert.match(get("faceplateUpgradeOldImage").src,
    /faceplate-history\/[a-f0-9]{64}\/same\.png\?v=/,
    "old image must come from historical bytes, not new same-name stock art");
  assert.match(get("faceplateUpgradeNewImage").src, /faceplates\/same\.png\?v=/);
  assert.match(get("faceplateUpgradeExplanation").textContent, /resets only this Native dashboard's saved visual Calibration/);
  assert.match(get("faceplateUpgradeOldDescription").textContent, /previous SHA/);
  offers = [{
    device_key: "snmp:SW3", base_profile: "native_SW3", switch_name: "SW3", model: "Model A",
    current_file: "same.png", available_file: "same.png",
    current_sha256: "a".repeat(64), available_sha256: "a".repeat(64),
    current_preview: "faceplate-history/revisions/2.7.70/same.png",
    current_version: "2.7.70", available_version: "2.7.99", same_filename: true,
    collapsed: false,
    versions: [
      {filename:"same.png",version:"2.7.70",sha256:"a".repeat(64),geometry_sha256:"c".repeat(64),path:"faceplates-old/2.7.70/same.png"},
      {filename:"same.png",version:"2.7.99",sha256:"a".repeat(64),geometry_sha256:"d".repeat(64),path:"faceplates/same.png"},
    ],
  }];
  timer();
  await drain();
  assert.ok(get("faceplateUpgradeOldImage").src.includes("faceplate-history/revisions/2.7.70/same.png"));
  assert.equal(get("faceplateRevisionList").options[0].options[2].disabled, true);
  assert.equal(get("faceplateRevisionList").options[1].options[2].disabled, false);
  offers = [{
    device_key: "snmp:SW3", base_profile: "native_SW3", switch_name: "SW3", model: "Model A",
    migration_kind: "legacy_saved_calibration", collapsed: false,
    legacy_calibration_file: "old-a.png", legacy_calibration_sha256: "a".repeat(64),
    current_file: "new-a.png", available_file: "new-a.png",
    current_sha256: "b".repeat(64), available_sha256: "b".repeat(64),
    current_version: "2.8.16", available_version: "2.8.16", versions: [],
  }];
  timer();
  await drain();
  assert.equal(get("faceplateUpgradeHeading").textContent, "Faceplate Calibration Upgrade Available");
  assert.equal(get("faceplateUpgradeOldTitle").textContent, "Saved Calibration Artwork");
  assert.match(get("faceplateUpgradeOldImage").src, /faceplates\/old-a\.png\?v=/);
  assert.match(get("faceplateUpgradeNewImage").src, /faceplates\/new-a\.png\?v=/);
  assert.match(get("faceplateUpgradeExplanation").textContent, /saved Calibration from the older faceplate/);
  get("faceplateUpgradeKeepButton").trigger("click");
  await drain();
  assert.equal(resets, 2, "keeping legacy saved Calibration cannot reset");
  get("faceplateUpgradeCollapsedButton").trigger("click");
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  currentDialog().children[4].children[2].trigger("click");
  await drain();
  assert.equal(resets, 3, "same-art approval must still reset obsolete Native Calibration");
  assert.equal(offers.length, 0);
  // Same artwork can still have a verified obsolete saved factory Geometry.
  // The popup describes the Geometry difference, without faking old pixels.
  offers = [{
    device_key: "snmp:SW3", base_profile: "native_SW3",
    switch_name: "SW3", model: "WS-C3650-48PD-E",
    migration_kind: "legacy_saved_geometry", collapsed: false,
    saved_geometry_width: 6000, saved_geometry_height: 1325,
    latest_geometry_width: 6000, latest_geometry_height: 900,
    current_file: "48rj45-4sfp.png", available_file: "48rj45-4sfp.png",
    current_sha256: "a".repeat(64), available_sha256: "a".repeat(64),
    current_version: "sha-" + "b".repeat(20),
    available_version: "sha-" + "b".repeat(20), versions: [],
  }];
  timer();
  await drain();
  assert.equal(get("faceplateUpgradeHeading").textContent,
    "Saved Geometry Upgrade Available");
  assert.equal(get("faceplateUpgradeOldImage").hidden, true,
    "never pretend the current stock PNG is the old saved Geometry preview");
  assert.match(get("faceplateUpgradeOldDescription").textContent, /6000 × 1325/);
  assert.match(get("faceplateUpgradeNewDescription").textContent, /6000 × 900/);
  assert.match(get("faceplateUpgradeExplanation").textContent, /Export Geometry first/);
  const beforeGeometryReset = resets;
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  dialog = currentDialog();
  assert.ok(dialog.open, "stale Geometry requires the same explicit confirmation");
  dialog.children[4].children[1].trigger("click");
  await drain();
  assert.equal(resets, beforeGeometryReset, "cancel preserves legacy saved Geometry");
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  dialog = currentDialog();
  dialog.children[4].children[2].trigger("click");
  await drain();
  assert.equal(resets, beforeGeometryReset + 1, "one confirmed per-switch visual reset");
  // SW5 and SW6 are Native members of the SAME SNMP stack. Their selector
  // and reset actions must use the unique Native base, not only the stack key.
  const stackBase = {
    device_key: "snmp:stack", switch_name: "3650-stack",
    display_name: "3650 Stack", model: "WS-C3650-48PD-E",
    migration_kind: "legacy_saved_geometry", collapsed: false,
    saved_geometry_width: null, saved_geometry_height: null,
    latest_geometry_width: 6000, latest_geometry_height: 900,
    current_file: "48rj45-4sfp.png", available_file: "48rj45-4sfp.png",
    current_sha256: "a".repeat(64), available_sha256: "a".repeat(64),
    current_version: "sha-" + "b".repeat(20),
    available_version: "sha-" + "b".repeat(20), versions: [],
  };
  offers = [
    {...stackBase, base_profile: "native_SW5"},
    {...stackBase, base_profile: "native_SW6"},
  ];
  timer();
  await drain();
  const options = get("faceplateUpgradeSwitchSelect").options;
  assert.equal(options.length, 2, "two same-device Native members are separately selectable");
  assert.equal(options[0].value, "snmp:stack@native_SW5");
  assert.equal(options[1].value, "snmp:stack@native_SW6");
  assert.match(options[0].textContent, /SW5/);
  assert.match(options[1].textContent, /SW6/);
  assert.match(get("faceplateUpgradeOldDescription").textContent,
    /Saved legacy port Geometry/, "missing saved image dimensions must not be invented");
  get("faceplateUpgradeSwitchSelect").value = options[1].value;
  get("faceplateUpgradeSwitchSelect").trigger("change");
  assert.match(get("faceplateUpgradeDevice").textContent, /SW6/);
  const beforeStackReset = resets;
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  dialog = currentDialog();
  assert.match(dialog.children[1].textContent, /SW6/, "confirmation names exact member");
  dialog.children[4].children[1].trigger("click");
  await drain();
  assert.equal(resets, beforeStackReset, "stack member cancellation is no-op");
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  dialog = currentDialog();
  dialog.children[4].children[2].trigger("click");
  await drain();
  assert.equal(resets, beforeStackReset + 1, "only confirmed stack member resets");
  assert.deepEqual(offers.map(item => item.base_profile), ["native_SW5"],
    "SW5 remains untouched after SW6 upgrade");
  offers = [];
  timer();
  await drain();
  assert.ok(get("faceplateUpgradeSection").classList.contains("hidden"),
    "no offers hides the whole section");
  console.log("FACEPLATE_UPGRADE_UI_PASS");
}

run().catch(error => { console.error(error); process.exitCode = 1; });
