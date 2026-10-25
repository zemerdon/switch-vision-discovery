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
  const versionList = get("faceplateRevisionList");
  let currentOffer = null;
  let latestOffers = [];
  let selectedKey = '';
  let manuallyExpandedKey = '';
  let updating = false;
  let refreshInFlight = false;

  // Device Overview owns the always-available picker. This shares Hub's
  // existing SHA-verified Core response and per-switch approval endpoint.
  const expandedDeviceFaceplates = new Set();
  let selections = [];
  let selectingFaceplate = false;

  function populateDeviceFaceplates() {
    const hosts = typeof document.querySelectorAll === "function"
      ? document.querySelectorAll(".hub-device-faceplates[data-switch-key]") : [];
    for (const host of hosts) {
      const deviceKey = host.dataset.switchKey || "";
      const matches = selections.filter(row => row.device_key === deviceKey);
      host.replaceChildren();
      const sectionTitle = document.createElement("div");
      sectionTitle.className = "hub-faceplate-current-title";
      sectionTitle.textContent = "Faceplates";
      host.append(sectionTitle);
      if (!matches.length) {
        const unavailable = document.createElement("p");
        unavailable.className = "muted";
        unavailable.textContent = "Current faceplate not verified yet. Check that the updated Core is running and refresh Device Overview.";
        host.append(unavailable);
        continue;
      }
      const details = document.createElement("details");
      let hasAlternatives = false;
      details.className = "hub-device-faceplate-versions";
      details.open = expandedDeviceFaceplates.has(deviceKey);
      details.addEventListener("toggle", () => {
        if (details.open) expandedDeviceFaceplates.add(deviceKey);
        else expandedDeviceFaceplates.delete(deviceKey);
      });
      const heading = document.createElement("summary");
      heading.textContent = "View available faceplates";
      details.append(heading);
      for (const row of matches) {
        const caption = document.createElement("div");
        caption.className = "muted";
        caption.textContent = "Model: " + row.model +
          " · " + (row.base_profile.startsWith("native_") ? "Native" : "Custom") + " dashboard";
        host.append(caption);
        const currentInfo = document.createElement("div");
        currentInfo.className = "hub-faceplate-current";
        if (row.verified_current) {
          const artwork = document.createElement("img");
          artwork.src = imageUrl(row.current_file, row.current_sha256, row.current_path);
          artwork.alt = "Currently selected stock faceplate";
          artwork.loading = "lazy";
          if (artwork.src) currentInfo.append(artwork);
          const description = document.createElement("div");
          description.textContent = "Currently selected: " + row.current_file +
            (row.current_version ? " · " +
              (row.current_version.startsWith("sha-") ? "Revision " + row.current_version.slice(4,16) :
                "Core " + row.current_version) : "");
          currentInfo.append(description);
        } else {
          currentInfo.classList.add("muted");
          currentInfo.textContent = "Current stock faceplate not verified by Core. Existing Calibration is unchanged.";
        }
        host.append(currentInfo);
        const isCurrent = item => row.verified_current &&
          item.filename === row.current_file &&
          item.sha256 === row.current_sha256 &&
          (!row.current_version || row.current_version === item.version) &&
          (!row.current_geometry_sha256 ||
            row.current_geometry_sha256 === item.geometry_sha256);
        if (!row.options.some(item => !isCurrent(item))) {
          const note = document.createElement("p");
          note.className = "muted";
          note.textContent = row.verified_current ?
            "No other verified factory faceplate revisions are available for this switch." :
            "Faceplate selection is unavailable until Core verifies the switch's stock artwork.";
          host.append(note);
          continue;
        }
        hasAlternatives = true;
        const gallery = document.createElement("div");
        gallery.className = "hub-faceplate-device-gallery";
        for (const item of row.options) {
          const current = isCurrent(item);
          const card = document.createElement("div");
          card.className = "hub-faceplate-device-option";
          const preview = document.createElement("img");
          preview.src = imageUrl(item.filename, item.sha256, item.path);
          preview.alt = "Faceplate " + item.filename;
          preview.loading = "lazy";
          const label = document.createElement("div");
          label.textContent = item.filename +
            (item.version.startsWith("sha-") ?
              " · Revision " + item.version.slice(4, 16) :
              " · Core " + item.version);
          const button = document.createElement("button");
          button.type = "button";
          button.className = current ? "secondary" : "";
          button.textContent = current ? "Currently selected" : "Select faceplate";
          button.disabled = selectingFaceplate || current;
          button.addEventListener("click", async event => {
            event.stopPropagation();
            if (selectingFaceplate) return;
            const warning = "Use this faceplate for " +
              (row.display_name || row.switch_name) + "?\n\n" +
              "This will REPLACE this switch's saved visual Calibration with " +
              "the selected faceplate's matching factory geometry. " +
              "Custom port positions, labels and other Calibration adjustments " +
              "for this switch will be reset. Other switches and the physical " +
              "network equipment will not be changed.\n\nContinue?";
            if (!window.confirm(warning)) return;
            selectingFaceplate = true;
            populateDeviceFaceplates();
            try {
              const reply = await fetch(endpoint("api/faceplate-upgrades/action"), {
                method: "POST", headers: {"Content-Type":"application/json"},
                body: JSON.stringify({
                  action: "pick", device_key: row.device_key,
                  base_profile: row.base_profile,
                  available_sha256: row.current_sha256,
                  expected_filename: row.current_file,
                  expected_version: row.current_version,
                  selected_filename: item.filename,
                  selected_sha256: item.sha256,
                  selected_version: item.version,
                }),
              });
              const data = await reply.json();
              if (!reply.ok || !data.ok || data.calibration_reset !== true)
                throw new Error(data.error || "Core did not confirm the reset");
              await refresh();
            } catch (error) {
              window.alert("Faceplate change was not confirmed: " +
                (error.message || error));
            } finally {
              selectingFaceplate = false;
              populateDeviceFaceplates();
            }
          });
          card.append(preview,label,button);
          gallery.append(card);
        }
        details.append(gallery);
      }
      if (hasAlternatives) host.append(details);
    }
  }

  window.svPopulateFaceplateSelectors = populateDeviceFaceplates;

  function imageUrl(filename, sha, previousPath = "") {
    // A previous revision retains its real bytes outside the stock catalog.
    // Never use the new same-name stock URL to fake the previous image.
    if (!/^[a-z0-9][a-z0-9_.-]{0,140}\.(png|jpg|jpeg|webp)$/i.test(filename) ||
        !/^[a-f0-9]{64}$/.test(sha)) return "";
    if (previousPath === "faceplates/" + filename) {
      return "/local/switch-vision/faceplates/" + encodeURIComponent(filename) + "?v=" + sha.slice(0, 16);
    }
    if (previousPath) {
      const parts = previousPath.split("/");
      if (parts.length === 3 && parts[0] === "faceplates-old" && parts[2] === filename &&
          parts[1].split(".").length === 3 && parts[1].split(".").every(n => n.length > 0 && String(Number(n)) === n)) {
        return "/local/switch-vision/" + parts.map(encodeURIComponent).join("/") + "?v=" + sha.slice(0, 16);
      }
      if (parts.length === 4 && parts[0] === "faceplate-history" &&
          parts[1] === "revisions" && parts[3] === filename &&
          parts[2].split(".").length === 3 &&
          parts[2].split(".").every(n => n.length > 0 && String(Number(n)) === n)) {
        return "/local/switch-vision/" + parts.map(encodeURIComponent).join("/") + "?v=" + sha.slice(0, 16);
      }
      const localRevision = /^faceplate-history\/revisions\/sha\/([a-f0-9]{64})\/([a-z0-9][a-z0-9_.-]{0,140}\.png)$/i.exec(previousPath);
      if (localRevision && localRevision[2] === filename) {
        return "/local/switch-vision/" + previousPath.split("/").map(encodeURIComponent).join("/") +
          "?v=" + sha.slice(0, 16);
      }
      const allowed = /^faceplate-history\/(legacy|[a-f0-9]{64})\/([a-z0-9][a-z0-9_.-]{0,140}\.png)$/i.exec(previousPath);
      if (!allowed || allowed[2] !== filename ||
          (allowed[1] !== "legacy" && allowed[1] !== sha)) return "";
      return "/local/switch-vision/faceplate-history/" +
        encodeURIComponent(allowed[1]) + "/" + encodeURIComponent(allowed[2]) +
        "?v=" + sha.slice(0, 16);
    }
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
    const scopeName = "Native dashboard";
    get("faceplateUpgradeDevice").textContent = label + " · " + offer.model + " · " + scopeName;
    const legacy = offer.migration_kind === "legacy_saved_calibration";
    get("faceplateUpgradeHeading").textContent = legacy
      ? "Faceplate Calibration Upgrade Available" : "New Faceplate Upgrade Available";
    get("faceplateUpgradeOldTitle").textContent = legacy
      ? "Saved Calibration Artwork" : "Current Faceplate";
    const oldPreview = get("faceplateUpgradeOldImage");
    oldPreview.hidden = !legacy && offer.old_preview_unavailable === true;
    oldPreview.src = oldPreview.hidden ? "" : imageUrl(
      legacy ? offer.legacy_calibration_file : offer.current_file,
      legacy ? offer.legacy_calibration_sha256 : offer.current_sha256,
      legacy ? "" : (offer.current_preview || ""));
    get("faceplateUpgradeNewImage").src = imageUrl(offer.available_file, offer.available_sha256);
    get("faceplateUpgradeOldDescription").textContent = legacy
      ? offer.legacy_calibration_file + " · older saved layout"
      : offer.current_file +
        (offer.same_filename ? " · previous SHA " + offer.current_sha256.slice(0, 12) : "") +
        (offer.old_preview_unavailable ? " · historical preview unavailable" : "");
    get("faceplateUpgradeNewDescription").textContent = legacy
      ? offer.available_file + " · current verified factory layout"
      : offer.available_file +
        (offer.same_filename ? " · updated SHA " + offer.available_sha256.slice(0, 12) : "");
    get("faceplateUpgradeExplanation").textContent = legacy
      ? "The new stock faceplate is already selected, but this Native dashboard still has saved Calibration from the older faceplate. " +
        "Keep Current leaves that Calibration untouched. Upgrade Faceplate will replace only this switch's saved Native visual Calibration with the verified matching factory geometry. " +
        "Other switches and Custom dashboards are not changed."
      : "The existing image stays selected until you approve the updated stock artwork. Keep Current retains the verified earlier image and Calibration. " +
        "Upgrade Faceplate resets only this " + scopeName + "'s saved visual Calibration to the selected faceplate's verified factory geometry. " +
        "Hub upgrades are Native-only. Custom artwork and Calibration are never changed by this action.";
    if (versionList) {
      versionList.replaceChildren(...(Array.isArray(offer.versions) ? offer.versions : []).map(item => {
        const section = document.createElement("details");
        const heading = document.createElement("summary");
        heading.textContent = String(item.version || "").startsWith("sha-")
          ? "Stock revision " + item.version.slice(4, 16)
          : "Core " + item.version;
        const preview = document.createElement("img");
        preview.src = imageUrl(offer.available_file, item.sha256, item.path);
        preview.alt = "Faceplate revision " + item.version;
        const choose = document.createElement("button");
        const chosen = item.sha256 === offer.current_sha256 &&
          item.version === offer.current_version;
        choose.textContent = chosen ? "Currently selected" : "Use this version";
        choose.disabled = chosen;
        choose.addEventListener("click", () => act("select", item.sha256, item.version));
        section.replaceChildren(heading, preview, choose);
        return section;
      }));
    }
    if (!updating) status("");
  }

  async function refresh() {
    if (refreshInFlight || updating) return;
    refreshInFlight = true;
    try {
      const reply = await fetch(endpoint("api/faceplate-upgrades"), {cache: "no-store"});
      const data = await reply.json();
      if (!reply.ok || !data.ok) throw new Error(data.error || "Core is not ready");
      selections = Array.isArray(data.selections) ? data.selections : [];
      render(data.offers);
      populateDeviceFaceplates();
    } catch (_error) {
      // A Core restart/outage must not expose an unverified offer.
      root.classList.add("hidden");
      currentOffer = null;
      selections = [];
      populateDeviceFaceplates();
    } finally {
      refreshInFlight = false;
    }
  }

  async function act(action, selectedSha = "", selectedVersion = "") {
    const offer = currentOffer;
    if (!offer || updating) return;
    if ((action === "upgrade" || action === "select") && !window.confirm(
      "Upgrade the Native dashboard stock faceplate for " + (offer.display_name || offer.switch_name) +
      "?\n\nThis will replace this switch's saved visual Calibration with the selected faceplate's matching factory geometry. Other switches and physical equipment are unchanged."
    )) return;
    updating = true;
    keepButton.disabled = true;
    applyButton.disabled = true;
    collapsedButton.disabled = true;
    status(action === "keep" ? "Keeping current faceplate…" : "Approving the updated faceplate…");
    try {
      const reply = await fetch(endpoint("api/faceplate-upgrades/action"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action, device_key: offer.device_key, base_profile: offer.base_profile, available_sha256: offer.available_sha256, selected_sha256: selectedSha, selected_version: selectedVersion}),
      });
      const data = await reply.json();
      if (!reply.ok || !data.ok || (action !== "keep" && data.calibration_reset !== true))
        throw new Error(data.error || "Faceplate and factory Calibration reset could not be verified");
      if (action === "keep") {
        manuallyExpandedKey = "";
        expanded.hidden = true;
        collapsedButton.classList.remove("hidden");
        status("");
      } else {
        status("The Native dashboard factory faceplate was selected. Custom artwork and Calibration were not changed.");
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
