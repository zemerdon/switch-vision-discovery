"use strict";
// Exercise Hub rendering and actions with a tiny DOM/fetch harness (no browser/network).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor() {
    this.value = "";
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
  replaceChildren(...items) { this.options = items; }
  trigger(name) { assert.ok(this.listeners[name], name); return this.listeners[name](); }
}

async function run() {
  const ids = [
    "faceplateUpgradeSection", "faceplateUpgradeExpanded", "faceplateUpgradeSwitchSelect",
    "faceplateUpgradeCollapsedButton", "faceplateUpgradeKeepButton", "faceplateUpgradeApplyButton",
    "faceplateUpgradeMessage", "faceplateUpgradeDevice", "faceplateUpgradeOldImage",
    "faceplateUpgradeNewImage", "faceplateUpgradeOldDescription",
    "faceplateUpgradeNewDescription", "faceplateUpgradeExplanation",
  ];
  const nodes = Object.fromEntries(ids.map(id => [id, new Element()]));
  const docEvents = {};
  const winEvents = {};
  let timer = null;
  let reads = 0;
  let resets = 0;
  let failReset = false;
  let offers = [
    {device_key: "snmp:SW3", base_profile: "native_SW3", switch_name: "SW3", model: "Model A",
      current_file: "old-a.png", available_file: "new-a.png",
      current_sha256: "a".repeat(64), available_sha256: "b".repeat(64), collapsed: false},
    {device_key: "snmp:SW4", base_profile: "native_SW4", switch_name: "SW4", model: "Model B",
      current_file: "old-b.png", available_file: "new-b.png",
      current_sha256: "c".repeat(64), available_sha256: "d".repeat(64), collapsed: false},
  ];
  const document = {
    hidden: false,
    getElementById: id => nodes[id],
    createElement: () => new Element(),
    addEventListener: (name, fn) => { docEvents[name] = fn; },
  };
  const window = {
    confirm: () => true,
    addEventListener: (name, fn) => { winEvents[name] = fn; },
    setInterval: (fn, delay) => { assert.equal(delay, 300000); timer = fn; },
  };
  const fetch = async (_url, request) => {
    if (!request || !request.method || request.method === "GET") {
      reads++;
      return {ok: true, json: async () => ({ok: true, offers})};
    }
    const body = JSON.parse(request.body);
    const offer = offers.find(item => item.device_key === body.device_key &&
      item.available_sha256 === body.available_sha256);
    assert.ok(offer, "exact per-switch offer");
    assert.equal(body.base_profile, offer.base_profile, "exact artwork scope");
    if (body.action === "keep") offer.collapsed = true;
    else if (body.action === "upgrade") {
      resets++;
      if (failReset) return {ok: false, json: async () => ({error: "Core artwork approval failed"})};
      offers = offers.filter(item => item !== offer);
    } else throw Error("unexpected action");
    return {ok: true, json: async () => ({ok: true})};
  };
  const script = fs.readFileSync(path.join(__dirname, "faceplate_upgrades.js"), "utf8");
  vm.runInNewContext(script, {document, window, fetch, endpoint: x => x});
  const drain = () => new Promise(resolve => setImmediate(resolve));
  await drain();
  const get = id => nodes[id];

  assert.equal(get("faceplateUpgradeSwitchSelect").options.length, 2);
  assert.equal(get("faceplateUpgradeDevice").textContent, "SW3 · Model A");
  assert.match(get("faceplateUpgradeOldImage").src, /old-a\.png\?v=/);
  assert.ok(!get("faceplateUpgradeSection").classList.contains("hidden"));
  get("faceplateUpgradeSwitchSelect").value = "snmp:SW4";
  get("faceplateUpgradeSwitchSelect").trigger("change");
  assert.equal(get("faceplateUpgradeDevice").textContent, "SW4 · Model B");
  get("faceplateUpgradeKeepButton").trigger("click");
  await drain();
  assert.ok(get("faceplateUpgradeExpanded").hidden, "keep collapses the selected switch");
  assert.equal(resets, 0, "keep cannot call Core reset");
  get("faceplateUpgradeCollapsedButton").trigger("click");
  assert.ok(!get("faceplateUpgradeExpanded").hidden, "red button only reopens");
  assert.equal(resets, 0);
  failReset = true;
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  assert.equal(resets, 1);
  assert.match(get("faceplateUpgradeMessage").textContent, /Core artwork approval failed/);
  assert.equal(offers.length, 2, "failed action retains the offer");
  failReset = false;
  get("faceplateUpgradeApplyButton").trigger("click");
  await drain();
  assert.equal(resets, 2);
  assert.equal(offers.length, 1);
  assert.equal(get("faceplateUpgradeDevice").textContent, "SW3 · Model A");
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
  assert.match(get("faceplateUpgradeExplanation").textContent, /Saved Calibration geometry is untouched/);
  assert.match(get("faceplateUpgradeOldDescription").textContent, /previous SHA/);
  offers = [];
  timer();
  await drain();
  assert.ok(get("faceplateUpgradeSection").classList.contains("hidden"),
    "no offers hides the whole section");
  console.log("FACEPLATE_UPGRADE_UI_PASS");
}

run().catch(error => { console.error(error); process.exitCode = 1; });
