(() => {
  "use strict";

  const CACHE_KEY = "switch-vision-custom-themes-v1";
  const SELECTED_KEY = "switch-vision-management-theme-v1";
  const BUILTIN_THEMES = [
    ["switch-vision", "Switch Vision"],
    ["cisco-classic", "Cisco Classic"],
    ["cisco-nexus", "Cisco Nexus"],
    ["unifi", "UniFi"],
  ];
  const ROLE_GROUPS = [
    ["Application structure", [
      ["page", "Page background"],
      ["card", "Card / panel background"],
      ["card_strong", "Card header / strong surface"],
      ["surface_input", "Input / select background"],
      ["surface_button", "Button / tab background"],
      ["surface_inset", "Inset / nested panel background"],
      ["surface_hover", "Hover background"],
      ["line", "Primary border"],
      ["line_soft", "Secondary border / divider"],
      ["shadow", "Card shadow"],
    ]],
    ["Text & navigation", [
      ["text", "Primary body text"],
      ["muted", "Muted / helper text"],
      ["field_label", "Field / option labels"],
      ["link", "Link text"],
      ["link_hover", "Link hover text"],
      ["on_accent", "Text on accent"],
      ["on_primary", "Text on primary button"],
      ["heart", "Sponsor heart"],
    ]],
    ["Headings & accent", [
      ["accent", "Accent / focus"],
      ["accent_strong", "Strong accent / active border"],
      ["accent_dark", "Primary button lower colour"],
      ["accent_dark_hover", "Primary button upper colour"],
      ["accent_soft", "Selected / focus background"],
      ["heading", "Section heading"],
      ["heading_strong", "Page title / strong heading"],
      ["heading_line", "Heading rail / navigation line"],
      ["heading_soft", "Heading tint / page glow"],
      ["heading_glow", "Heading glow"],
    ]],
    ["Status & feedback", [
      ["ok", "Success / online"],
      ["ok_soft", "Success background"],
      ["warn", "Warning / pending"],
      ["warn_soft", "Warning background"],
      ["bad", "Error / danger"],
      ["bad_soft", "Error background"],
      ["neutral_soft", "Neutral badge background"],
      ["status_bg", "Status / terminal background"],
      ["code_bg", "Code preview background"],
    ]],
    ["Buttons & chips", [
      ["button_primary_bg", "Primary button background"],
      ["button_primary_text", "Primary button text"],
      ["button_secondary_bg", "Secondary button background"],
      ["button_secondary_text", "Secondary button text"],
      ["button_danger_bg", "Danger button background"],
      ["button_danger_text", "Danger button text"],
      ["chip_bg", "Chip / pill background"],
      ["chip_hover", "Chip / pill hover background"],
    ]],
  ];
  const ROLE_KEYS = ROLE_GROUPS.flatMap(([, rows]) => rows.map(([key]) => key));
  const FALLBACK = {
    page:"#071525",card:"#0b1d31",card_strong:"#0e233b",surface_input:"#08192b",
    surface_button:"#0a1a2c",surface_inset:"#091a2d",surface_hover:"#102a44",
    text:"#edf5fc",muted:"#9bb0c7",field_label:"#b8c7d9",line:"#214766",
    line_soft:"#183750",accent:"#2196f3",accent_strong:"#2f83bd",accent_dark:"#0f4f7d",
    accent_dark_hover:"#146698",accent_soft:"#12314a",heading:"#69c8ff",
    heading_strong:"#a6e3ff",heading_line:"#2787c7",heading_soft:"#10283a",
    heading_glow:"#17466a",warn:"#ffb74d",warn_soft:"#332819",ok:"#45d483",
    ok_soft:"#123629",bad:"#ff6b6b",bad_soft:"#351d24",neutral_soft:"#1a2633",
    on_accent:"#ffffff",on_primary:"#ffffff",shadow:"#030910",status_bg:"#07101d",
    code_bg:"#08131f",chip_bg:"#102033",chip_hover:"#172b40",heart:"#ff6ea9",
    link:"#69c8ff",link_hover:"#a6e3ff",button_primary_bg:"#0f4f7d",
    button_primary_text:"#ffffff",button_secondary_bg:"#0a1a2c",
    button_secondary_text:"#edf5fc",button_danger_bg:"#0a1a2c",button_danger_text:"#ff6b6b",
  };

  const qs = (id) => document.getElementById(id);
  const endpoint = (path) => {
    const href = location.href.endsWith("/") ? location.href : location.href + "/";
    return new URL(path, href).toString();
  };
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const safeId = (name) => {
    const base = String(name || "custom-theme").trim().toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 42) || "custom_theme";
    return `${base}_${Date.now().toString(36)}`;
  };
  const isHex = (value) => /^#[0-9a-f]{6}$/i.test(String(value || ""));
  const cssVar = (key) => "--" + key.replaceAll("_", "-");

  let authoritative = { selected: "switch-vision", custom_themes: [] };
  let editingId = "";
  let draft = null;
  let initialized = false;

  function cacheState(state = authoritative) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(state));
      localStorage.setItem(SELECTED_KEY, String(state.selected || "switch-vision"));
    } catch (_error) {}
  }

  function normalizeState(raw) {
    const group = raw?.settings?.management_theme || raw?.management_theme || {};
    const themes = Array.isArray(group.custom_themes) ? group.custom_themes
      .filter((row) => row && typeof row === "object" && row.id && row.name && row.colors)
      .map((row) => ({ id:String(row.id), name:String(row.name), colors:{...row.colors} })) : [];
    const selected = String(group.management_theme_selected || group.selected || "switch-vision");
    return { selected, custom_themes: themes };
  }

  async function coreRequest(method = "GET", body = null) {
    const response = await fetch(endpoint("api/settings/core"), {
      method,
      cache: "no-store",
      headers: body ? { "Content-Type":"application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = {};
    try { data = await response.json(); } catch (_error) {}
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }

  async function saveAuthoritative(state, message = "Theme saved.") {
    const payload = {
      settings: {
        management_theme: {
          management_theme_selected: state.selected,
          custom_themes: state.custom_themes,
        },
      },
    };
    const data = await coreRequest("POST", payload);
    authoritative = normalizeState(data);
    cacheState(authoritative);
    populateThemeDropdown();
    applySelectedTheme(authoritative.selected);
    renderBuilder();
    setStatus(message, "success");
    if (!qs("settingsCard")?.classList.contains("hidden")) {
      try { await window.SwitchVisionHubSettings?.load?.(); } catch (_error) {}
    }
    return data;
  }

  function setStatus(text, cls = "") {
    const node = qs("customThemeStatus");
    if (!node) return;
    node.textContent = text;
    node.className = `muted custom-theme-status ${cls}`.trim();
  }

  function applySelectedTheme(value) {
    if (typeof applyManagementTheme === "function") applyManagementTheme(value);
  }

  function populateThemeDropdown() {
    const select = qs("themeSelect");
    if (!select) return;
    const previous = String(authoritative.selected || select.value || "switch-vision");
    select.querySelector('optgroup[data-custom-themes="true"]')?.remove();
    if (authoritative.custom_themes.length) {
      const group = document.createElement("optgroup");
      group.label = "Custom Themes";
      group.dataset.customThemes = "true";
      for (const theme of authoritative.custom_themes) {
        const option = document.createElement("option");
        option.value = "custom:" + theme.id;
        option.textContent = theme.name;
        group.append(option);
      }
      select.append(group);
    }
    const allowed = new Set([
      ...BUILTIN_THEMES.map(([id]) => id),
      ...authoritative.custom_themes.map((row) => "custom:" + row.id),
    ]);
    select.value = allowed.has(previous) ? previous : "switch-vision";
  }

  function parseRgb(value) {
    const match = String(value || "").match(/rgba?\(\s*([\d.]+)[, ]+([\d.]+)[, ]+([\d.]+)(?:\s*[,/]\s*([\d.]+))?\s*\)/i);
    if (!match) return null;
    return [Number(match[1]), Number(match[2]), Number(match[3]), match[4] === undefined ? 1 : Number(match[4])];
  }
  function toHexChannel(value) {
    return Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, "0");
  }
  function resolveRoleHex(key, pageHex = FALLBACK.page) {
    const probe = document.createElement("span");
    probe.style.cssText = `position:fixed;left:-9999px;color:var(${cssVar(key)});`;
    document.body.append(probe);
    const rgba = parseRgb(getComputedStyle(probe).color);
    probe.remove();
    if (!rgba) return FALLBACK[key] || "#000000";
    let [r,g,b,a] = rgba;
    if (a < 1 && isHex(pageHex)) {
      const br = parseInt(pageHex.slice(1,3),16), bg = parseInt(pageHex.slice(3,5),16), bb = parseInt(pageHex.slice(5,7),16);
      r = r*a + br*(1-a); g = g*a + bg*(1-a); b = b*a + bb*(1-a);
    }
    return "#" + toHexChannel(r) + toHexChannel(g) + toHexChannel(b);
  }
  function captureCurrentPalette() {
    const page = resolveRoleHex("page", FALLBACK.page);
    const colors = {};
    for (const key of ROLE_KEYS) colors[key] = resolveRoleHex(key, page);
    return colors;
  }
  function completeColors(raw = {}) {
    const result = {};
    for (const key of ROLE_KEYS) result[key] = isHex(raw[key]) ? String(raw[key]).toLowerCase() : FALLBACK[key];
    return result;
  }

  function currentTheme() {
    return authoritative.custom_themes.find((row) => row.id === editingId) || null;
  }

  function createThemeFromCurrent() {
    const existingNames = new Set(authoritative.custom_themes.map((row) => row.name.toLowerCase()));
    let n = authoritative.custom_themes.length + 1;
    let name = `Custom Theme ${n}`;
    while (existingNames.has(name.toLowerCase())) name = `Custom Theme ${++n}`;
    const row = { id:safeId(name), name, colors:captureCurrentPalette() };
    authoritative.custom_themes.push(row);
    editingId = row.id;
    draft = clone(row);
    cacheState(authoritative);
    populateThemeDropdown();
    renderBuilder();
    setStatus("New theme created locally. Choose colours, then Save Theme.", "");
  }

  function duplicateTheme() {
    const source = draft || currentTheme();
    if (!source) return;
    const names = new Set(authoritative.custom_themes.map((row) => row.name.toLowerCase()));
    let base = `${source.name} Copy`, name = base, n = 2;
    while (names.has(name.toLowerCase())) name = `${base} ${n++}`;
    const row = { id:safeId(name), name, colors:completeColors(source.colors) };
    authoritative.custom_themes.push(row);
    editingId = row.id;
    draft = clone(row);
    renderBuilder();
    setStatus("Theme duplicated locally. Save Theme to persist it.", "");
  }

  async function deleteTheme() {
    const theme = currentTheme();
    if (!theme) return;
    if (!confirm(`Delete custom theme “${theme.name}”?`)) return;
    const nextThemes = authoritative.custom_themes.filter((row) => row.id !== theme.id);
    let selected = authoritative.selected;
    if (selected === "custom:" + theme.id) selected = "switch-vision";
    authoritative = { selected, custom_themes: nextThemes };
    editingId = nextThemes[0]?.id || "";
    draft = editingId ? clone(nextThemes[0]) : null;
    try {
      setStatus("Deleting theme…");
      await saveAuthoritative(authoritative, "Theme deleted.");
    } catch (error) {
      setStatus("Delete failed: " + (error.message || error), "failure");
    }
  }

  async function saveTheme(apply = false) {
    if (!draft) return;
    const name = String(draft.name || "").trim();
    if (!name) return setStatus("Enter a theme name.", "failure");
    if (name.length > 64) return setStatus("Theme name must be 64 characters or fewer.", "failure");
    if (/[<>&"]/g.test(name)) return setStatus("Theme name contains an unsupported character.", "failure");
    if (authoritative.custom_themes.some((row) => row.id !== draft.id && row.name.toLowerCase() === name.toLowerCase())) {
      return setStatus("Theme names must be unique.", "failure");
    }
    const saved = { id:draft.id, name, colors:completeColors(draft.colors) };
    const index = authoritative.custom_themes.findIndex((row) => row.id === saved.id);
    if (index >= 0) authoritative.custom_themes[index] = saved;
    else authoritative.custom_themes.push(saved);
    if (apply) authoritative.selected = "custom:" + saved.id;
    try {
      setStatus(apply ? "Saving and applying theme…" : "Saving theme…");
      await saveAuthoritative(authoritative, apply ? "Theme saved and applied to Discovery and Installer." : "Theme saved.");
      editingId = saved.id;
      draft = clone(saved);
      renderBuilder();
    } catch (error) {
      setStatus("Save failed: " + (error.message || error), "failure");
    }
  }

  async function selectGlobalTheme(value) {
    const allowed = new Set([
      ...BUILTIN_THEMES.map(([id]) => id),
      ...authoritative.custom_themes.map((row) => "custom:" + row.id),
    ]);
    if (!allowed.has(value)) return;
    authoritative.selected = value;
    cacheState(authoritative);
    applySelectedTheme(value);
    try {
      await saveAuthoritative(authoritative, "Theme applied to Discovery and Installer.");
    } catch (error) {
      setStatus("Theme selection could not be saved: " + (error.message || error), "failure");
    }
  }

  function applyPreviewVars(node, colors) {
    if (!node) return;
    for (const key of ROLE_KEYS) node.style.setProperty(cssVar(key), completeColors(colors)[key]);
  }

  function previewMarkup() {
    return `
      <div class="theme-sample-topbar">
        <div><span class="theme-role-tag">Page title · heading strong</span><h2>Switch Vision Discovery</h2></div>
        <span class="theme-sample-chip"><span class="theme-role-tag">Chip</span>My Custom Theme</span>
      </div>
      <div class="theme-sample-nav">
        <button class="theme-sample-tab active"><span class="theme-role-tag">Active tab</span>Devices</button>
        <button class="theme-sample-tab"><span class="theme-role-tag">Tab</span>Topology</button>
        <a href="#" onclick="return false"><span class="theme-role-tag">Link</span>Settings help</a>
      </div>
      <section class="theme-sample-card">
        <span class="theme-role-tag">Card · primary border</span>
        <h3>Section heading</h3>
        <p>Primary body text. <span class="theme-sample-muted">Muted helper text.</span></p>
        <div class="theme-sample-form">
          <label><span>Field label</span><input value="Input / select surface" readonly></label>
          <label><span>Field label</span><select><option>Selected value</option></select></label>
        </div>
        <div class="theme-sample-actions">
          <button class="primary">Primary button</button>
          <button class="secondary">Secondary button</button>
          <button class="danger">Danger button</button>
        </div>
      </section>
      <div class="theme-sample-grid">
        <section class="theme-sample-card"><span class="theme-role-tag">Success</span><div class="theme-sample-status ok">● Online / Success</div><div class="theme-sample-status warn">▲ Pending / Warning</div><div class="theme-sample-status bad">● Offline / Error</div></section>
        <section class="theme-sample-card"><span class="theme-role-tag">Nested surface</span><div class="theme-sample-row"><b>Device row</b><span class="theme-sample-muted">Muted metadata</span></div><div class="theme-sample-row hover">Hover surface</div></section>
      </div>
      <section class="theme-sample-card">
        <span class="theme-role-tag">Status / code background</span>
        <pre>Discovery ready
Core: connected
Installer: shared theme enabled</pre>
      </section>
      <section class="theme-installer-sample">
        <span class="theme-role-tag">Installer sample · same shared palette</span>
        <div class="theme-installer-header"><b>SV</b><div><h3>Switch Vision Installer</h3><span class="theme-sample-muted">Install and manage components safely.</span></div></div>
        <div class="theme-sample-grid"><div class="theme-sample-row"><span>Installed Core</span><strong>v2.7.x</strong></div><div class="theme-sample-row"><span>Status</span><strong class="ok">Up to date</strong></div></div>
      </section>`;
  }

  function renderColorGroups(container) {
    for (const [groupName, rows] of ROLE_GROUPS) {
      const group = document.createElement("section");
      group.className = "theme-color-group";
      const heading = document.createElement("h4");
      heading.textContent = groupName;
      group.append(heading);
      for (const [key, labelText] of rows) {
        const row = document.createElement("label");
        row.className = "theme-color-row";
        const label = document.createElement("span");
        label.textContent = labelText;
        const color = document.createElement("input");
        color.type = "color";
        color.value = completeColors(draft?.colors)[key];
        color.setAttribute("aria-label", labelText + " colour");
        const hex = document.createElement("input");
        hex.type = "text";
        hex.maxLength = 7;
        hex.value = color.value;
        hex.setAttribute("aria-label", labelText + " hex value");
        const set = (value) => {
          if (!isHex(value) || !draft) return;
          const normalized = value.toLowerCase();
          draft.colors[key] = normalized;
          color.value = normalized;
          hex.value = normalized;
          applyPreviewVars(qs("customThemePreview"), draft.colors);
          setStatus("Unsaved theme changes.");
        };
        color.addEventListener("input", () => set(color.value));
        hex.addEventListener("change", () => {
          if (!isHex(hex.value)) { hex.value = color.value; return; }
          set(hex.value);
        });
        row.append(label, color, hex);
        group.append(row);
      }
      container.append(group);
    }
  }

  function renderBuilder() {
    const root = qs("hubCustomThemeSettings");
    if (!root) return;
    root.innerHTML = "";
    if (!editingId && authoritative.custom_themes.length) editingId = authoritative.custom_themes[0].id;
    const existing = currentTheme();
    if (existing && (!draft || draft.id !== existing.id)) draft = clone(existing);

    const intro = document.createElement("div");
    intro.className = "custom-theme-intro";
    intro.innerHTML = "<h3>Custom Theme</h3><p class=\"muted\">Create named management themes and control the shared colours used by Switch Vision Discovery / Hub and Installer. Generated switch dashboards and faceplates are not changed.</p>";
    root.append(intro);

    const layout = document.createElement("div");
    layout.className = "custom-theme-layout";
    const editor = document.createElement("div");
    editor.className = "custom-theme-editor";
    const preview = document.createElement("div");
    preview.className = "custom-theme-preview-wrap";

    const library = document.createElement("section");
    library.className = "theme-library";
    library.innerHTML = "<h4>Theme library</h4>";
    const select = document.createElement("select");
    select.id = "customThemeLibrary";
    const none = document.createElement("option");
    none.value = "";
    none.textContent = authoritative.custom_themes.length ? "Choose a custom theme" : "No custom themes yet";
    select.append(none);
    for (const theme of authoritative.custom_themes) {
      const option = document.createElement("option");
      option.value = theme.id; option.textContent = theme.name; option.selected = theme.id === editingId;
      select.append(option);
    }
    select.addEventListener("change", () => {
      editingId = select.value;
      draft = editingId ? clone(currentTheme()) : null;
      renderBuilder();
    });
    const libraryActions = document.createElement("div");
    libraryActions.className = "actions";
    const newButton = document.createElement("button");
    newButton.type = "button"; newButton.textContent = "＋ New";
    newButton.addEventListener("click", createThemeFromCurrent);
    const duplicateButton = document.createElement("button");
    duplicateButton.type = "button"; duplicateButton.textContent = "Duplicate"; duplicateButton.disabled = !draft;
    duplicateButton.addEventListener("click", duplicateTheme);
    const deleteButton = document.createElement("button");
    deleteButton.type = "button"; deleteButton.className = "danger"; deleteButton.textContent = "Delete"; deleteButton.disabled = !draft;
    deleteButton.addEventListener("click", deleteTheme);
    libraryActions.append(newButton, duplicateButton, deleteButton);
    library.append(select, libraryActions);
    editor.append(library);

    if (draft) {
      const nameSection = document.createElement("section");
      nameSection.className = "theme-name-section";
      const nameLabel = document.createElement("label");
      nameLabel.className = "field";
      nameLabel.innerHTML = "<span><b>Theme name</b></span>";
      const nameInput = document.createElement("input");
      nameInput.type = "text"; nameInput.maxLength = 64; nameInput.value = draft.name;
      nameInput.addEventListener("input", () => { draft.name = nameInput.value; setStatus("Unsaved theme changes."); });
      nameLabel.append(nameInput);
      nameSection.append(nameLabel);
      editor.append(nameSection);

      const colors = document.createElement("div");
      colors.className = "theme-color-groups";
      renderColorGroups(colors);
      editor.append(colors);

      const actions = document.createElement("div");
      actions.className = "actions custom-theme-actions";
      const save = document.createElement("button");
      save.type = "button"; save.className = "secondary"; save.textContent = "Save Theme";
      save.addEventListener("click", () => saveTheme(false));
      const saveApply = document.createElement("button");
      saveApply.type = "button"; saveApply.className = "primary"; saveApply.textContent = "Save & Apply";
      saveApply.addEventListener("click", () => saveTheme(true));
      actions.append(save, saveApply);
      editor.append(actions);
    } else {
      const empty = document.createElement("div");
      empty.className = "theme-empty";
      empty.innerHTML = "<h4>Create your first theme</h4><p class=\"muted\">New themes start from the colours currently shown in the Hub.</p>";
      editor.append(empty);
    }

    const previewHead = document.createElement("div");
    previewHead.className = "custom-theme-preview-head";
    previewHead.innerHTML = "<h4>Live sample page</h4><p class=\"muted\">Every sample is labelled by the role it represents. Colour changes update this sample immediately.</p>";
    const sample = document.createElement("div");
    sample.id = "customThemePreview";
    sample.className = "custom-theme-preview";
    sample.innerHTML = previewMarkup();
    if (draft) applyPreviewVars(sample, draft.colors);
    preview.append(previewHead, sample);
    layout.append(editor, preview);
    root.append(layout);

    const status = document.createElement("p");
    status.id = "customThemeStatus";
    status.className = "muted custom-theme-status";
    status.textContent = draft ? "Ready. Changes are local until you save." : "Create a custom theme to begin.";
    root.append(status);
  }

  function installStyles() {
    if (qs("customThemeManagerStyles")) return;
    const style = document.createElement("style");
    style.id = "customThemeManagerStyles";
    style.textContent = `
      .custom-theme-intro{margin-bottom:12px}.custom-theme-intro h3{margin-bottom:4px}
      .custom-theme-layout{display:grid;grid-template-columns:minmax(300px,430px) minmax(420px,1fr);gap:14px;align-items:start}
      .custom-theme-editor,.custom-theme-preview-wrap{min-width:0}
      .theme-library,.theme-name-section,.theme-color-group,.theme-empty{border:1px solid var(--line-soft);border-radius:10px;padding:10px;margin-bottom:10px;background:var(--surface-inset)}
      .theme-library h4,.theme-color-group h4,.custom-theme-preview-head h4{margin:0 0 8px;color:var(--heading)}
      .theme-library>select{width:100%}.theme-name-section{padding-top:6px}
      .theme-color-groups{display:grid;gap:8px}.theme-color-row{display:grid;grid-template-columns:minmax(0,1fr) 42px 88px;gap:7px;align-items:center;min-height:36px}
      .theme-color-row>span{color:var(--field-label);font-size:var(--sv-font-small)}
      .theme-color-row input[type=color]{width:42px;height:30px;padding:2px;border:1px solid var(--line);border-radius:6px;background:var(--surface-input)}
      .theme-color-row input[type=text]{width:88px;height:30px;min-height:30px;padding:4px 6px;font-family:ui-monospace,monospace;font-size:12px}
      .custom-theme-actions{position:sticky;bottom:60px;padding:8px;border:1px solid var(--line-soft);border-radius:9px;background:var(--card)}
      .custom-theme-preview-head{margin-bottom:8px}.custom-theme-preview-head p{margin:0 0 8px}
      .custom-theme-preview{background:var(--page);color:var(--text);border:1px solid var(--line);border-radius:12px;padding:12px;display:grid;gap:10px;box-shadow:0 12px 28px var(--shadow)}
      .theme-role-tag{display:block;color:var(--muted);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px}
      .theme-sample-topbar{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px;background:var(--card-strong);border:1px solid var(--line-soft);border-radius:9px}
      .theme-sample-topbar h2{margin:0;color:var(--heading-strong)}.theme-sample-chip{padding:6px 9px;border:1px solid var(--line-soft);border-radius:999px;background:var(--chip-bg);color:var(--text)}
      .theme-sample-nav{display:flex;gap:6px;align-items:end;flex-wrap:wrap;border-bottom:1px solid var(--line-soft);padding-bottom:7px}
      .theme-sample-tab{background:var(--surface-button)!important;color:var(--muted)!important;border:1px solid var(--line-soft)!important}.theme-sample-tab.active{background:var(--accent-soft)!important;color:var(--heading-strong)!important;border-color:var(--accent-strong)!important}
      .theme-sample-nav a{margin-left:auto;color:var(--link)}.theme-sample-card,.theme-installer-sample{background:linear-gradient(180deg,var(--card-strong),var(--card) 70px);border:1px solid var(--line);border-radius:10px;padding:10px}
      .theme-sample-card h3,.theme-installer-sample h3{margin:2px 0 6px;color:var(--heading)}.theme-sample-card p{margin:4px 0 8px}.theme-sample-muted{color:var(--muted)}
      .theme-sample-form{display:grid;grid-template-columns:1fr 1fr;gap:8px}.theme-sample-form label{display:grid;gap:3px;color:var(--field-label);font-size:12px}.theme-sample-form input,.theme-sample-form select{width:100%;background:var(--surface-input);color:var(--text);border:1px solid var(--line);height:32px;min-height:32px}
      .theme-sample-actions{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}.theme-sample-actions button{min-height:30px;padding:5px 9px}
      .theme-sample-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.theme-sample-status{padding:6px 8px;border-radius:6px;margin-top:5px}.theme-sample-status.ok{color:var(--ok);background:var(--ok-soft)}.theme-sample-status.warn{color:var(--warn);background:var(--warn-soft)}.theme-sample-status.bad{color:var(--bad);background:var(--bad-soft)}
      .theme-sample-row{display:flex;justify-content:space-between;gap:8px;padding:7px;background:var(--surface-inset);border:1px solid var(--line-soft);border-radius:6px;margin-top:5px}.theme-sample-row.hover{background:var(--surface-hover)}
      .theme-sample-card pre{margin:5px 0 0;padding:8px;border-radius:6px;background:var(--code-bg);color:var(--text);white-space:pre-wrap}
      .theme-installer-header{display:flex;align-items:center;gap:9px}.theme-installer-header>b{display:grid;place-items:center;width:34px;height:34px;border:1px solid var(--accent-strong);border-radius:9px;background:var(--accent-soft);color:var(--heading-strong)}
      .theme-installer-header h3{margin:0}.theme-installer-header+ .theme-sample-grid{margin-top:8px}.theme-installer-sample .ok{color:var(--ok)}
      .custom-theme-status.success{color:var(--ok)}.custom-theme-status.failure{color:var(--bad)}
      @media(max-width:1000px){.custom-theme-layout{grid-template-columns:1fr}.custom-theme-preview-wrap{order:-1}.custom-theme-actions{position:static}}
      @media(max-width:600px){.theme-sample-grid,.theme-sample-form{grid-template-columns:1fr}.theme-color-row{grid-template-columns:minmax(0,1fr) 40px 82px}}
    `;
    document.head.append(style);
  }

  async function initialize() {
    if (initialized) return;
    initialized = true;
    installStyles();
    try {
      const data = await coreRequest();
      authoritative = normalizeState(data);
      cacheState(authoritative);
      populateThemeDropdown();
      applySelectedTheme(authoritative.selected);
      editingId = authoritative.custom_themes[0]?.id || "";
      draft = editingId ? clone(authoritative.custom_themes[0]) : null;
      renderBuilder();
    } catch (error) {
      const cache = (() => { try { return JSON.parse(localStorage.getItem(CACHE_KEY) || "{}"); } catch (_e) { return {}; } })();
      authoritative = {
        selected:String(cache.selected || "switch-vision"),
        custom_themes:Array.isArray(cache.custom_themes) ? cache.custom_themes : [],
      };
      populateThemeDropdown();
      renderBuilder();
      setStatus("Core theme settings are unavailable: " + (error.message || error), "failure");
    }

    const select = qs("themeSelect");
    if (select && !select.dataset.customThemePersistence) {
      select.dataset.customThemePersistence = "true";
      select.addEventListener("change", () => selectGlobalTheme(select.value));
    }
  }

  window.SwitchVisionCustomThemes = {
    initialize,
    refresh: async () => {
      const data = await coreRequest();
      authoritative = normalizeState(data);
      cacheState(authoritative);
      populateThemeDropdown();
      applySelectedTheme(authoritative.selected);
      renderBuilder();
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once:true });
  } else {
    initialize();
  }
})();
