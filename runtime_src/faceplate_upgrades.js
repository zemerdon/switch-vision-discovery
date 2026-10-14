"use strict";
/* Hub's optional faceplate upgrade offer. Detection is read-only and restarts
 * after Home Assistant Core is ready; no Discovery rerun is required.
 */
(() => {
  const root = document.getElementById("faceplateUpgradeSection");
  if (!root) return;
  const get = id => document.getElementById(id);
  const expanded = get("faceplateUpgradeExpanded");
  const collapsedButton = get("faceplateUpgradeCollapsedButton");
  const selector = get("faceplateUpgradeSwitchSelect");
  const keepButton = get("faceplateUpgradeKeepButton");
  const applyButton = get("faceplateUpgradeApplyButton");
  const message = get("faceplateUpgradeMessage");
  let currentOffer = null;
  let latestOffers = [];
  let selectedKey = '';
  let manuallyExpandedKey = '';
  let updating = false;
  let refreshInFlight = false;

  function imageUrl(filename, sha) {
    // Only consume server-validated filenames and digests.
    if (!/^[a-z0-9][a-z0-9_.-]{0,140}\.(png|jpg|jpeg|webp)$/i.test(filename) ||
        !/^[a-f0-9]{64}$/.test(sha)) return "";
    return "/local/switch-vision/faceplates/" + encodeURIComponent(filename) + "?v=" + sha.slice(0, 16);
  }

  function status(text, error = false) {
    message.textContent = text || "";
    message.style.color = error ? "var(--bad)" : "";
  }

  function render(offers) {
    latestOffers = Array.isArray(offers) ? offers : [];
    const offer = latestOffers.find(item => item.device_key === selectedKey) ||
                  latestOffers.find(item => !item.collapsed) || latestOffers[0] || null;
    currentOffer = offer;
    selectedKey = offer ? offer.device_key : '';
    selector.classList.toggle("hidden", latestOffers.length < 2);
    selector.replaceChildren(...latestOffers.map(item => {
      const option = document.createElement("option");
      option.value = item.device_key;
      option.textContent = (item.display_name || item.switch_name || "Switch") + " · " + item.model;
      return option;
    }));
    selector.value = selectedKey;
    root.classList.toggle("hidden", !offer);
    if (!offer) {
      status("");
      return;
    }
    const shouldCollapse = Boolean(offer.collapsed) && manuallyExpandedKey !== offer.device_key;
    expanded.hidden = shouldCollapse;
    collapsedButton.classList.toggle("hidden", !shouldCollapse);
    const label = offer.display_name || offer.switch_name || "Switch";
    get("faceplateUpgradeDevice").textContent = label + " · " + offer.model;
    get("faceplateUpgradeOldImage").src = imageUrl(offer.current_file, offer.current_sha256);
    get("faceplateUpgradeNewImage").src = imageUrl(offer.available_file, offer.available_sha256);
    get("faceplateUpgradeOldDescription").textContent = offer.current_file;
    get("faceplateUpgradeNewDescription").textContent = offer.available_file;
    if (!updating) status("");
  }

  async function refresh() {
    if (refreshInFlight || updating) return;
    refreshInFlight = true;
    try {
      const reply = await fetch(endpoint("api/faceplate-upgrades"), {cache: "no-store"});
      const data = await reply.json();
      if (!reply.ok || !data.ok) throw new Error(data.error || "Core is not ready");
      render(data.offers);
    } catch (_error) {
      // A Core restart/outage must not expose an unverified offer.
      root.classList.add("hidden");
      currentOffer = null;
    } finally {
      refreshInFlight = false;
    }
  }

  async function act(action) {
    const offer = currentOffer;
    if (!offer || updating) return;
    if (action === "upgrade" && !window.confirm(
      "Upgrade the stock faceplate for " + (offer.display_name || offer.switch_name) +
      "?\n\nThis uses the existing Reset Current Switch behavior. " +
      "All saved faceplate-specific Calibration for this switch will be removed. " +
      "Other switches are unchanged."
    )) return;
    updating = true;
    keepButton.disabled = true;
    applyButton.disabled = true;
    collapsedButton.disabled = true;
    status(action === "keep" ? "Keeping current faceplate…" : "Restoring the latest factory faceplate…");
    try {
      const reply = await fetch(endpoint("api/faceplate-upgrades/action"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action, device_key: offer.device_key, available_sha256: offer.available_sha256}),
      });
      const data = await reply.json();
      if (!reply.ok || !data.ok) throw new Error(data.error || "Faceplate action failed");
      if (action === "keep") {
        manuallyExpandedKey = "";
        expanded.hidden = true;
        collapsedButton.classList.remove("hidden");
        status("");
      } else {
        status("The new factory faceplate was selected.");
      }
    } catch (err) {
      status("Faceplate upgrade was not completed: " + (err.message || err), true);
    } finally {
      updating = false;
      keepButton.disabled = false;
      applyButton.disabled = false;
      collapsedButton.disabled = false;
      // Allow messages to be read before the next background pass, but on a
      // successful upgrade the next fetch immediately removes a completed offer.
      if (!message.style.color) await refresh();
    }
  }

  selector.addEventListener("change", () => {
    if (updating) return;
    selectedKey = selector.value;
    manuallyExpandedKey = '';
    render(latestOffers);
  });
  collapsedButton.addEventListener("click", () => {
    // Red button only reopens the offer; it never applies silently.
    manuallyExpandedKey = currentOffer?.device_key || "";
    expanded.hidden = false;
    collapsedButton.classList.add("hidden");
  });
  keepButton.addEventListener("click", () => act("keep"));
  applyButton.addEventListener("click", () => act("upgrade"));
  window.addEventListener("focus", () => { if (!document.hidden) void refresh(); });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) void refresh();
  });
  void refresh();
  window.setInterval(() => {
    if (!document.hidden) void refresh();
  }, 300000);
})();
