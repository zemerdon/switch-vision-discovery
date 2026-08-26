(() => {
  "use strict";

  const state = {
    items: [],
    selected: new Set(),
    loading: false,
    loaded: false,
  };

  const $ = (id) => document.getElementById(id);

  function endpoint(path) {
    const href = location.href.endsWith("/")
      ? location.href
      : location.href + "/";
    return new URL(path, href).toString();
  }

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  async function request(path, method = "GET", body = undefined) {
    const options = {
      method,
      cache: "no-store",
      headers: {},
    };

    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    const response = await fetch(endpoint(path), options);

    let data = {};

    try {
      data = await response.json();
    } catch (_error) {
      data = {};
    }

    if (!response.ok) {
      throw new Error(
        data.error || `Request failed with HTTP ${response.status}`
      );
    }

    return data;
  }

  function message(text = "", error = false) {
    const target = $("svProfilesMessage");
    if (!target) return;

    target.textContent = text;
    target.className = text
      ? (error ? "failure" : "success")
      : "";
  }

  function installStyles() {
    if ($("svCalibrationProfileStyles")) return;

    const style = document.createElement("style");

    style.id = "svCalibrationProfileStyles";
    style.textContent = `
      .sv-profiles-toolbar{
        display:flex;
        align-items:center;
        gap:8px;
        flex-wrap:nowrap;
        margin:0 0 10px;
        padding:7px 8px;
        border:1px solid var(--line-soft);
        border-radius:10px;
        background:var(--surface-inset);
        overflow-x:auto
      }

      .sv-profiles-stats{
        display:flex;
        align-items:center;
        gap:7px;
        margin-right:auto;
        color:var(--muted);
        font-size:var(--sv-font-small);
        white-space:nowrap
      }

      .sv-profiles-separator{opacity:.65}

      .sv-profiles-toolbar-actions{
        display:flex;
        align-items:center;
        justify-content:flex-end;
        gap:6px;
        flex:0 0 auto;
        margin-left:auto;
        white-space:nowrap
      }

      .sv-profiles-toolbar button,
      .sv-profile-actions button{
        min-height:32px;
        padding:4px 8px
      }

      .sv-profiles-list{
        display:grid;
        gap:8px
      }

      .sv-profile-card{
        display:grid;
        grid-template-columns:auto minmax(0,1fr);
        grid-template-areas:
          "select meta"
          "title actions";
        column-gap:12px;
        row-gap:6px;
        border:1px solid var(--line-soft);
        border-radius:10px;
        padding:12px;
        background:var(--surface-inset)
      }

      .sv-profile-card.active{
        border-left:4px solid var(--ok)
      }

      .sv-profile-card.stale{
        border-left:4px solid var(--bad)
      }

      .sv-profile-card.duplicate{
        border-left:4px solid var(--warn)
      }

      .sv-profile-select{
        grid-area:select;
        display:flex;
        align-items:center;
        gap:7px;
        margin:0;
        color:var(--muted);
        font-size:var(--sv-font-small);
        white-space:nowrap
      }

      .sv-profile-title{
        grid-area:title;
        display:flex;
        align-items:center;
        gap:8px;
        min-width:0;
        font-weight:700
      }

      .sv-profile-top-meta{
        grid-area:meta;
        display:flex;
        align-items:center;
        justify-content:flex-end;
        gap:8px;
        min-width:0;
        overflow-x:auto;
        white-space:nowrap
      }

      .sv-profile-badges{
        display:flex;
        align-items:center;
        gap:6px;
        flex:0 0 auto;
        flex-wrap:nowrap
      }

      .sv-profile-badge{
        border:1px solid var(--line-soft);
        border-radius:999px;
        padding:3px 7px;
        font-size:.72rem;
        font-weight:700;
        background:var(--neutral-soft)
      }

      .sv-profile-badge.active{
        border-color:var(--ok);
        background:var(--ok-soft)
      }

      .sv-profile-badge.warning{
        border-color:var(--warn);
        background:var(--warn-soft)
      }

      .sv-profile-badge.danger{
        border-color:var(--bad);
        background:var(--bad-soft)
      }

      .sv-profile-summary-line{
        margin:0;
        color:var(--muted);
        font-size:var(--sv-font-small);
        white-space:nowrap
      }

      .sv-profile-meta-actions{
        grid-area:actions;
        display:block;
        margin:0;
        min-width:0;
        align-self:start
      }

      .sv-profile-actions{
        display:flex;
        justify-content:flex-end;
        align-items:center;
        gap:6px;
        flex-wrap:nowrap;
        margin:0;
        max-width:100%;
        overflow-x:auto
      }

      .sv-profile-actions select{
        max-width:220px
      }

      @media(max-width:900px){
        .sv-profile-card{column-gap:8px;padding:10px}
        .sv-profile-top-meta{justify-content:flex-end;overflow-x:auto}
        .sv-profile-actions{justify-content:flex-end;width:100%;overflow-x:auto}
      }

      .sv-profile-empty{
        border:1px solid var(--line-soft);
        border-radius:10px;
        padding:14px;
        background:var(--surface-inset)
      }
    `;

    document.head.appendChild(style);
  }

  function renderShell() {
    installStyles();

    const root = $("calibrationProfilesRoot");

    if (!root || root.dataset.ready === "true") return;

    root.dataset.ready = "true";

    root.innerHTML = `
      <div class="sv-profiles-toolbar">
        <div class="sv-profiles-stats">
          <span
            id="svProfilesSummary"
            class="sv-profiles-summary"
          >
            Calibration profiles have not been loaded yet.
          </span>
          <span class="sv-profiles-separator" aria-hidden="true">·</span>
          <span
            id="svProfilesSelectionSummary"
            class="sv-selection-summary"
          >
            0 selected
          </span>
        </div>

        <div class="sv-profiles-toolbar-actions">
        <button
          id="svProfilesRefresh"
          type="button"
        >
          Refresh Profiles
        </button>

        <button
          id="svProfilesSelectStale"
          type="button"
        >
          Select Stale
        </button>

        <button
          id="svProfilesCleanStale"
          class="danger"
          type="button"
        >
          Clean Stale Profiles
        </button>

        <button
          id="svProfilesClearSelection"
          type="button"
        >
          Clear Selection
        </button>

        <button
          id="svProfilesDeleteSelected"
          class="danger"
          type="button"
          disabled
        >
          Delete Selected
        </button>
        </div>
      </div>

      <div id="svProfilesMessage"></div>

      <div
        id="svProfilesList"
        class="sv-profiles-list"
      ></div>
    `;

    $("svProfilesRefresh").addEventListener(
      "click",
      () => load(true)
    );

    $("svProfilesSelectStale").addEventListener(
      "click",
      () => {
        state.selected = new Set(
          state.items
            .filter(
              (item) =>
                item.stale === true &&
                item.active !== true &&
                item.scope !== "factory"
            )
            .map(
              (item) =>
                String(item.profile || "").trim()
            )
            .filter(Boolean)
        );

        render();
      }
    );

    $("svProfilesCleanStale").addEventListener(
      "click",
      async () => {
        state.selected = new Set(
          state.items
            .filter(
              (item) =>
                item.stale === true &&
                item.active !== true &&
                item.scope !== "factory"
            )
            .map(
              (item) =>
                String(item.profile || "").trim()
            )
            .filter(Boolean)
        );

        render();

        if (!state.selected.size) {
          message("No stale calibration profiles found.");
          return;
        }

        await deleteSelected();
      }
    );

    $("svProfilesClearSelection").addEventListener(
      "click",
      () => {
        state.selected.clear();
        render();
      }
    );

    $("svProfilesDeleteSelected").addEventListener(
      "click",
      deleteSelected
    );
  }

  function updateSelection() {
    const count = state.selected.size;

    if ($("svProfilesSelectionSummary")) {
      $("svProfilesSelectionSummary").textContent =
        `${count} selected`;
    }

    if ($("svProfilesDeleteSelected")) {
      $("svProfilesDeleteSelected").disabled =
        count === 0 || state.loading;
    }
  }

  function render() {
    renderShell();

    const root = $("svProfilesList");
    const summary = $("svProfilesSummary");

    if (!root) return;

    const items = Array.isArray(state.items)
      ? state.items
      : [];

    const selectable = new Set(
      items
        .filter(
          (item) =>
            item.active !== true &&
            item.scope !== "factory"
        )
        .map(
          (item) =>
            String(item.profile || "").trim()
        )
        .filter(Boolean)
    );

    for (const profile of [...state.selected]) {
      if (!selectable.has(profile)) {
        state.selected.delete(profile);
      }
    }

    updateSelection();

    if (!items.length) {
      root.innerHTML =
        `<div class="sv-profile-empty">` +
        `<b>No saved calibration profiles.</b>` +
        `</div>`;

      if (summary) {
        summary.textContent =
          "0 saved calibration profiles";
      }

      return;
    }

    const activeCount =
      items.filter(
        (item) => item.active === true
      ).length;

    const staleCount =
      items.filter(
        (item) => item.stale === true
      ).length;

    const duplicateCount =
      items.filter(
        (item) =>
          item.duplicate_faceplate_content === true
      ).length;

    const summaryParts = [
      `${items.length} saved`,
      `${activeCount} active`,
    ];

    if (staleCount) {
      summaryParts.push(
        `${staleCount} missing faceplate`
      );
    }

    if (duplicateCount) {
      summaryParts.push(
        `${duplicateCount} duplicate-content`
      );
    }

    if (summary) {
      summary.textContent =
        summaryParts.join(" · ");
    }

    root.innerHTML = items
      .map((item, index) => {
        const profile =
          String(item.profile || "").trim();

        const base =
          String(item.base_profile || "").trim();

        const scope =
          String(item.scope || "other");

        const faceplate =
          String(
            item.faceplate || "__default__"
          );

        const model =
          String(
            item.model || "Unknown model"
          );

        const protectedProfile =
          item.active === true ||
          scope === "factory";

        const badges = [];

        badges.push(
          `<span class="sv-profile-badge">` +
          `${esc(scope.toUpperCase())}` +
          `</span>`
        );

        badges.push(
          item.active === true
            ? `<span class="sv-profile-badge active">ACTIVE</span>`
            : `<span class="sv-profile-badge">UNUSED</span>`
        );

        if (item.stale === true) {
          badges.push(
            `<span class="sv-profile-badge danger">` +
            `MISSING FACEPLATE` +
            `</span>`
          );
        }

        if (
          item.duplicate_faceplate_content === true
        ) {
          badges.push(
            `<span class="sv-profile-badge warning">` +
            `DUPLICATE FACEPLATE` +
            `</span>`
          );
        }

        const classes = [
          "sv-profile-card"
        ];

        if (item.active === true) {
          classes.push("active");
        }

        if (item.stale === true) {
          classes.push("stale");
        } else if (
          item.duplicate_faceplate_content === true
        ) {
          classes.push("duplicate");
        }

        const copyTargets =
          items
            .map(
              (candidate, targetIndex) => ({
                candidate,
                targetIndex,
              })
            )
            .filter(
              ({ candidate }) =>
                String(
                  candidate.profile || ""
                ).trim() !== profile &&
                candidate.scope !== "factory" &&
                candidate.stale !== true &&
                String(
                  candidate.base_profile || ""
                ) === base
            );

        const copyOptions =
          copyTargets
            .map(
              ({
                candidate,
                targetIndex,
              }) => {
                const targetFaceplate =
                  String(
                    candidate.faceplate ||
                    "__default__"
                  );

                const active =
                  candidate.active === true
                    ? " · ACTIVE"
                    : "";

                return (
                  `<option value="${targetIndex}">` +
                  `${esc(targetFaceplate + active)}` +
                  `</option>`
                );
              }
            )
            .join("");

        return `
          <article class="${classes.join(" ")}">

            <label class="sv-profile-select">
              <input
                type="checkbox"
                data-profile-select="${index}"
                ${protectedProfile ? "disabled" : ""}
                ${state.selected.has(profile) ? "checked" : ""}
              >

              ${
                scope === "factory"
                  ? "Factory profile protected"
                  : item.active === true
                    ? "Active profile protected"
                    : "Select profile"
              }
            </label>

            <div class="sv-profile-top-meta">
              <span class="sv-profile-badges">
                ${badges.join("")}
              </span>

              <span class="sv-profile-summary-line">
                ${esc(model)}
                · ${Number(item.port_count || 0)} RJ45
                · ${Number(item.sfp_count || 0)} SFP/uplink
                · Faceplate: ${esc(faceplate)}
              </span>
            </div>

            <div class="sv-profile-title">
              <span>${esc(base || profile)}</span>
            </div>

            <div class="sv-profile-meta-actions">
              <div class="sv-profile-actions">
                <button
                  type="button"
                  data-profile-export="${index}"
                >
                  Export Profile
                </button>

                ${
                  scope !== "factory" &&
                  item.stale !== true
                    ? `
                      <button
                        type="button"
                        data-profile-import="${index}"
                      >
                        Import Into Profile
                      </button>

                      <input
                        type="file"
                        accept="application/json,.json"
                        data-profile-import-file="${index}"
                        hidden
                      >
                    `
                    : ""
                }

                ${
                  copyTargets.length
                    ? `
                      <select
                        data-profile-copy-target="${index}"
                      >
                        <option value="">
                          Copy to…
                        </option>
                        ${copyOptions}
                      </select>

                      <button
                        type="button"
                        data-profile-copy="${index}"
                      >
                        Copy Profile
                      </button>
                    `
                    : ""
                }

                ${
                  protectedProfile
                    ? ""
                    : `
                      <button
                        type="button"
                        class="danger"
                        data-profile-delete="${index}"
                      >
                        Delete Profile
                      </button>
                    `
                }
              </div>
            </div>
          </article>
        `;
      })
      .join("");

    root
      .querySelectorAll(
        "[data-profile-select]"
      )
      .forEach((checkbox) => {
        checkbox.addEventListener(
          "change",
          () => {
            const index =
              Number.parseInt(
                checkbox.dataset.profileSelect ||
                "",
                10
              );

            const item =
              state.items[index];

            if (
              !Number.isInteger(index) ||
              !item ||
              item.active === true ||
              item.scope === "factory"
            ) {
              checkbox.checked = false;
              return;
            }

            const profile =
              String(
                item.profile || ""
              ).trim();

            if (!profile) return;

            if (checkbox.checked) {
              state.selected.add(profile);
            } else {
              state.selected.delete(profile);
            }

            updateSelection();
          }
        );
      });

    root
      .querySelectorAll(
        "[data-profile-delete]"
      )
      .forEach((button) => {
        button.addEventListener(
          "click",
          () => {
            const index =
              Number.parseInt(
                button.dataset.profileDelete ||
                "",
                10
              );

            if (Number.isInteger(index)) {
              deleteOne(index);
            }
          }
        );
      });

    root
      .querySelectorAll(
        "[data-profile-export]"
      )
      .forEach((button) => {
        button.addEventListener(
          "click",
          () => {
            const index =
              Number.parseInt(
                button.dataset.profileExport ||
                "",
                10
              );

            if (Number.isInteger(index)) {
              exportProfile(index);
            }
          }
        );
      });

    root
      .querySelectorAll(
        "[data-profile-import]"
      )
      .forEach((button) => {
        button.addEventListener(
          "click",
          () => {
            const index =
              Number.parseInt(
                button.dataset.profileImport ||
                "",
                10
              );

            if (!Number.isInteger(index)) {
              return;
            }

            const input =
              root.querySelector(
                `[data-profile-import-file="${index}"]`
              );

            if (input) input.click();
          }
        );
      });

    root
      .querySelectorAll(
        "[data-profile-import-file]"
      )
      .forEach((input) => {
        input.addEventListener(
          "change",
          () => {
            const index =
              Number.parseInt(
                input.dataset.profileImportFile ||
                "",
                10
              );

            const file =
              input.files?.[0] || null;

            input.value = "";

            if (
              Number.isInteger(index) &&
              file
            ) {
              importProfile(index, file);
            }
          }
        );
      });

    root
      .querySelectorAll(
        "[data-profile-copy]"
      )
      .forEach((button) => {
        button.addEventListener(
          "click",
          () => {
            const sourceIndex =
              Number.parseInt(
                button.dataset.profileCopy ||
                "",
                10
              );

            if (
              !Number.isInteger(sourceIndex)
            ) {
              return;
            }

            const select =
              root.querySelector(
                `[data-profile-copy-target="${sourceIndex}"]`
              );

            const targetIndex =
              Number.parseInt(
                select?.value || "",
                10
              );

            if (
              Number.isInteger(targetIndex)
            ) {
              copyProfile(
                sourceIndex,
                targetIndex
              );
            }
          }
        );
      });
  }

  async function load(force = false) {
    renderShell();

    if (state.loading) return;

    state.loading = true;

    const refresh =
      $("svProfilesRefresh");

    const summary =
      $("svProfilesSummary");

    if (refresh) {
      refresh.disabled = true;
      refresh.textContent =
        "Refreshing…";
    }

    if (summary) {
      summary.textContent =
        force
          ? "Refreshing calibration profiles…"
          : "Loading calibration profiles…";
    }

    message("");

    try {
      const result =
        await request(
          "api/calibration-profiles"
        );

      state.items =
        Array.isArray(result?.items)
          ? result.items
          : [];

      state.loaded = true;

      render();
    } catch (error) {
      state.items = [];
      state.loaded = false;

      if (summary) {
        summary.textContent =
          "Calibration profiles unavailable";
      }

      message(
        "Calibration profiles could not be loaded: " +
        String(error.message || error),
        true
      );
    } finally {
      state.loading = false;

      if (refresh) {
        refresh.disabled = false;
        refresh.textContent =
          "Refresh Profiles";
      }

      updateSelection();
    }
  }

  async function getCalibration(profile) {
    return request(
      "api/calibration-profiles/get",
      "POST",
      { profile }
    );
  }

  async function saveCalibration(
    profile,
    calibration
  ) {
    return request(
      "api/calibration-profiles/save",
      "POST",
      {
        profile,
        calibration,
      }
    );
  }

  async function deleteCalibration(profile) {
    return request(
      "api/calibration-profiles/delete",
      "POST",
      { profile }
    );
  }

  async function deleteOne(index) {
    const item = state.items[index];

    if (!item || state.loading) return;

    if (
      item.active === true ||
      item.scope === "factory"
    ) {
      message(
        item.scope === "factory"
          ? "Factory profiles are protected from deletion."
          : "Active profiles are protected from deletion.",
        true
      );

      return;
    }

    const profile =
      String(item.profile || "").trim();

    const faceplate =
      String(
        item.faceplate || "__default__"
      );

    if (!profile) return;

    const confirmed =
      window.confirm(
        "Delete this calibration profile?\n\n" +
        "Internal profile:\n" +
        profile +
        "\n\nFaceplate:\n" +
        faceplate +
        "\n\nThis cannot be undone."
      );

    if (!confirmed) return;

    state.loading = true;

    try {
      await deleteCalibration(profile);

      state.selected.delete(profile);

      message(
        `Deleted calibration profile: ${profile}`
      );
    } catch (error) {
      message(
        "Calibration profile deletion failed: " +
        String(error.message || error),
        true
      );
    } finally {
      state.loading = false;
      await load(true);
    }
  }

  async function deleteSelected() {
    if (
      state.loading ||
      !state.selected.size
    ) {
      return;
    }

    const selectedItems =
      state.items.filter((item) => {
        const profile =
          String(
            item.profile || ""
          ).trim();

        return (
          profile &&
          state.selected.has(profile)
        );
      });

    if (
      selectedItems.some(
        (item) =>
          item.active === true ||
          item.scope === "factory"
      )
    ) {
      message(
        "Bulk deletion stopped: an active or factory profile was selected.",
        true
      );

      render();
      return;
    }

    const profiles =
      selectedItems
        .map(
          (item) =>
            String(
              item.profile || ""
            ).trim()
        )
        .filter(Boolean);

    if (!profiles.length) return;

    const list =
      profiles
        .map(
          (profile) =>
            `• ${profile}`
        )
        .join("\n");

    const confirmed =
      window.confirm(
        `Delete ${profiles.length} calibration profile` +
        `${profiles.length === 1 ? "" : "s"}?\n\n` +
        list +
        "\n\nThis cannot be undone."
      );

    if (!confirmed) return;

    state.loading = true;

    try {
      for (const profile of profiles) {
        await deleteCalibration(profile);
      }

      state.selected.clear();

      message(
        `Deleted ${profiles.length} calibration profile` +
        `${profiles.length === 1 ? "" : "s"}.`
      );
    } catch (error) {
      message(
        "Bulk calibration profile deletion failed: " +
        String(error.message || error),
        true
      );
    } finally {
      state.loading = false;
      await load(true);
    }
  }

  async function exportProfile(index) {
    const item = state.items[index];

    if (!item || state.loading) return;

    const profile =
      String(item.profile || "").trim();

    if (!profile) return;

    try {
      const result =
        await getCalibration(profile);

      if (
        result?.exists !== true ||
        !result?.calibration
      ) {
        throw new Error(
          "Calibration profile no longer exists."
        );
      }

      const payload =
        clone(result.calibration);

      payload.schema_version = 2;

      payload.transfer_type =
        "switch-vision-faceplate-profile-v2";

      payload.generated_by =
        "Switch Vision Discovery v2.1.25";

      payload.source_scope =
        String(item.scope || "");

      payload.source_profile =
        profile;

      payload.source_base_profile =
        String(item.base_profile || "");

      payload.required_faceplate =
        String(
          item.faceplate ||
          "__default__"
        );

      payload.faceplate_included =
        false;

      delete payload.profile_name;
      delete payload.profile_scope;
      delete payload.base_profile_name;

      const safeName =
        profile
          .replace(
            /[^A-Za-z0-9_.-]+/g,
            "-"
          )
          .replace(
            /^-+|-+$/g,
            ""
          )
          .slice(0, 120) ||
        "profile";

      const blob =
        new Blob(
          [
            JSON.stringify(
              payload,
              null,
              2
            ) + "\n"
          ],
          {
            type:
              "application/json"
          }
        );

      const url =
        URL.createObjectURL(blob);

      const link =
        document.createElement("a");

      link.href = url;

      link.download =
        `switch-vision-profile-${safeName}.json`;

      document.body.appendChild(link);

      link.click();
      link.remove();

      URL.revokeObjectURL(url);

      message(
        `Exported calibration profile: ${profile}`
      );
    } catch (error) {
      message(
        "Export Profile failed: " +
        String(error.message || error),
        true
      );
    }
  }

  async function copyProfile(
    sourceIndex,
    targetIndex
  ) {
    if (
      state.loading ||
      sourceIndex === targetIndex
    ) {
      return;
    }

    const source =
      state.items[sourceIndex];

    const target =
      state.items[targetIndex];

    if (!source || !target) return;

    const sourceProfile =
      String(
        source.profile || ""
      ).trim();

    const targetProfile =
      String(
        target.profile || ""
      ).trim();

    const sourceBase =
      String(
        source.base_profile || ""
      ).trim();

    const targetBase =
      String(
        target.base_profile || ""
      ).trim();

    if (
      !sourceProfile ||
      !targetProfile ||
      sourceBase !== targetBase ||
      target.scope === "factory" ||
      target.stale === true
    ) {
      message(
        "Copy Profile rejected: invalid source or destination.",
        true
      );

      return;
    }

    const sourceFaceplate =
      String(
        source.faceplate ||
        "__default__"
      );

    const targetFaceplate =
      String(
        target.faceplate ||
        "__default__"
      );

    const activeWarning =
      target.active === true
        ? "\n\nWARNING: The destination profile is currently ACTIVE."
        : "";

    const confirmed =
      window.confirm(
        "Copy calibration profile?\n\n" +
        "SOURCE:\n" +
        sourceProfile +
        "\nFaceplate: " +
        sourceFaceplate +
        "\n\nDESTINATION:\n" +
        targetProfile +
        "\nFaceplate: " +
        targetFaceplate +
        activeWarning +
        "\n\nThe destination calibration will be overwritten." +
        "\nIts faceplate identity will be preserved."
      );

    if (!confirmed) return;

    state.loading = true;

    try {
      const [
        sourceResult,
        targetResult
      ] = await Promise.all([
        getCalibration(sourceProfile),
        getCalibration(targetProfile),
      ]);

      if (
        sourceResult?.exists !== true ||
        !sourceResult?.calibration ||
        targetResult?.exists !== true ||
        !targetResult?.calibration
      ) {
        throw new Error(
          "Source or destination calibration no longer exists."
        );
      }

      const copied =
        clone(
          sourceResult.calibration
        );

      const targetCalibration =
        targetResult.calibration;

      copied.ui =
        copied.ui || {};

      copied.ui.faceplate =
        clone(
          targetCalibration?.ui?.faceplate ||
          {
            show: true,
            source: "custom",
            file: targetFaceplate,
          }
        );

      copied.base_profile_name =
        targetBase;

      if (
        targetCalibration.profile !==
        undefined
      ) {
        copied.profile =
          targetCalibration.profile;
      }

      if (
        targetCalibration.management !==
        undefined
      ) {
        copied.management =
          clone(
            targetCalibration.management
          );
      }

      if (
        targetCalibration.stack !==
        undefined
      ) {
        copied.stack =
          clone(
            targetCalibration.stack
          );
      }

      await saveCalibration(
        targetProfile,
        copied
      );

      message(
        `Copied ${sourceProfile} → ${targetProfile}`
      );
    } catch (error) {
      message(
        "Copy Profile failed: " +
        String(error.message || error),
        true
      );
    } finally {
      state.loading = false;
      await load(true);
    }
  }

  async function importProfile(
    index,
    file
  ) {
    if (
      state.loading ||
      !file
    ) {
      return;
    }

    const target =
      state.items[index];

    if (
      !target ||
      target.scope === "factory" ||
      target.stale === true
    ) {
      message(
        "Import rejected: unsafe destination profile.",
        true
      );

      return;
    }

    if (
      file.size >
      2 * 1024 * 1024
    ) {
      message(
        "Import rejected: profile file exceeds 2 MB.",
        true
      );

      return;
    }

    const targetProfile =
      String(
        target.profile || ""
      ).trim();

    const targetBase =
      String(
        target.base_profile || ""
      ).trim();

    const targetFaceplate =
      String(
        target.faceplate ||
        "__default__"
      );

    if (
      !targetProfile ||
      !targetBase
    ) {
      return;
    }

    state.loading = true;

    try {
      const raw =
        JSON.parse(
          await file.text()
        );

      if (
        !raw ||
        typeof raw !== "object" ||
        Array.isArray(raw)
      ) {
        throw new Error(
          "Profile file must contain one JSON object."
        );
      }

      const schemaVersion =
        Number(
          raw.schema_version || 0
        );

      if (
        schemaVersion &&
        ![1, 2].includes(
          schemaVersion
        )
      ) {
        throw new Error(
          `Unsupported schema_version ${schemaVersion}.`
        );
      }

      if (
        raw.transfer_type &&
        raw.transfer_type !==
        "switch-vision-faceplate-profile-v2"
      ) {
        throw new Error(
          "Unsupported Switch Vision transfer type."
        );
      }

      if (
        raw.schema &&
        raw.schema !==
        "switch-vision-interactive-calibration-v1"
      ) {
        throw new Error(
          "Unsupported calibration schema."
        );
      }

      const targetResult =
        await getCalibration(
          targetProfile
        );

      if (
        targetResult?.exists !== true ||
        !targetResult?.calibration
      ) {
        throw new Error(
          "Destination calibration no longer exists."
        );
      }

      const targetCalibration =
        targetResult.calibration;

      const sourceModel =
        String(
          raw.model || ""
        ).trim();

      const targetModel =
        String(
          targetCalibration.model ||
          target.model ||
          ""
        ).trim();

      if (
        sourceModel &&
        targetModel &&
        sourceModel !== targetModel
      ) {
        throw new Error(
          `Model mismatch: ${sourceModel} → ${targetModel}`
        );
      }

      const requiredFaceplate =
        String(
          raw.required_faceplate ||
          raw.ui?.faceplate?.file ||
          "__default__"
        ).trim();

      const duplicates =
        Array.isArray(
          target.duplicate_faceplates
        )
          ? target.duplicate_faceplates
          : [];

      const faceplateMatches =
        requiredFaceplate ===
          targetFaceplate ||
        duplicates.includes(
          requiredFaceplate
        );

      const sourceProfile =
        String(
          raw.source_profile ||
          "unknown"
        );

      const faceplateWarning =
        faceplateMatches
          ? ""
          : "\n\nWARNING: The exported profile references a different faceplate filename.";

      const activeWarning =
        target.active === true
          ? "\n\nWARNING: This destination profile is currently ACTIVE."
          : "";

      const confirmed =
        window.confirm(
          "Import calibration profile?\n\n" +
          "FILE SOURCE:\n" +
          sourceProfile +
          "\nModel: " +
          (sourceModel ||
           "unspecified") +
          "\nRequired faceplate: " +
          requiredFaceplate +
          "\n\nDESTINATION:\n" +
          targetProfile +
          "\nFaceplate: " +
          targetFaceplate +
          faceplateWarning +
          activeWarning +
          "\n\nThe destination calibration will be overwritten." +
          "\nDestination identity and faceplate will be preserved."
        );

      if (!confirmed) {
        state.loading = false;
        return;
      }

      const imported =
        clone(raw);

      delete imported.transfer_type;
      delete imported.source_scope;
      delete imported.source_profile;
      delete imported.source_base_profile;
      delete imported.required_faceplate;
      delete imported.faceplate_included;
      delete imported.profile_name;
      delete imported.profile_scope;
      delete imported.base_profile_name;

      imported.ui =
        imported.ui || {};

      imported.ui.faceplate =
        clone(
          targetCalibration.ui?.faceplate ||
          {
            show: true,
            source: "custom",
            file: targetFaceplate,
          }
        );

      imported.base_profile_name =
        targetBase;

      if (
        targetCalibration.profile !==
        undefined
      ) {
        imported.profile =
          targetCalibration.profile;
      }

      if (
        targetCalibration.management !==
        undefined
      ) {
        imported.management =
          clone(
            targetCalibration.management
          );
      }

      if (
        targetCalibration.stack !==
        undefined
      ) {
        imported.stack =
          clone(
            targetCalibration.stack
          );
      }

      await saveCalibration(
        targetProfile,
        imported
      );

      message(
        `Imported profile into ${targetProfile}`
      );
    } catch (error) {
      message(
        "Import Profile failed: " +
        String(error.message || error),
        true
      );
    } finally {
      state.loading = false;
      await load(true);
    }
  }

  window.SwitchVisionCalibrationProfiles = {
    load,
  };
})();
