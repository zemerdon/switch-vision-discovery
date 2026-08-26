(() => {
  "use strict";

  const managerState = {
    activeIndex: null,
    observer: null,
    enhanceQueued: false,
    tooltipTimer: null,
  };

  const $ = (id) => document.getElementById(id);

  function installStyles() {
    if ($("svProfileManagerStyles")) return;

    const style = document.createElement("style");
    style.id = "svProfileManagerStyles";
    style.textContent = `
      .sv-profiles-toolbar-actions{
        display:none!important
      }

      .sv-profile-manager-actions{
        display:flex;
        align-items:center;
        justify-content:flex-end;
        gap:6px;
        flex:0 0 auto;
        margin-left:auto;
        white-space:nowrap
      }

      .sv-profile-manager-actions button,
      .sv-profile-manager-actions select{
        min-height:32px;
        padding:4px 8px
      }

      .sv-profile-manager-context{
        transition:
          border-color .15s ease,
          background .15s ease,
          opacity .15s ease
      }

      .sv-profile-manager-context:disabled,
      .sv-profile-manager-copy-target:disabled{
        opacity:.42;
        filter:saturate(.15);
        cursor:not-allowed
      }

      .sv-profile-manager-context:not(:disabled){
        border-color:var(--heading-line);
        background:var(--accent-soft)
      }

      .sv-profile-manager-context.danger:not(:disabled){
        border-color:var(--bad);
        background:var(--bad-soft)
      }

      .sv-profiles-list{
        display:grid!important;
        gap:14px!important;
        min-width:0
      }

      .sv-profile-section{
        display:grid;
        gap:8px;
        min-width:0
      }

      .sv-profile-section-heading{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:10px;
        padding:8px 4px 5px;
        border-bottom:1px solid var(--heading-line);
        color:var(--heading);
        font-size:.82rem;
        font-weight:800;
        letter-spacing:.06em
      }

      .sv-profile-subgroup{
        display:grid;
        gap:6px;
        min-width:0
      }

      .sv-profile-subheading{
        padding:4px 4px 1px;
        color:var(--muted);
        font-size:.76rem;
        font-weight:750;
        letter-spacing:.05em
      }

      .sv-profile-group-list{
        display:grid;
        gap:7px;
        min-width:0
      }

      .sv-profile-card{
        grid-template-columns:minmax(90px,auto) minmax(0,1fr)!important;
        grid-template-areas:"title meta"!important;
        align-items:center!important;
        column-gap:10px!important;
        row-gap:0!important;
        min-width:0!important;
        max-width:100%!important;
        overflow:hidden!important;
        cursor:pointer
      }

      .sv-profile-card.manager-selected{
        border-color:var(--heading-line)!important;
        background:var(--accent-soft)!important;
        box-shadow:0 0 0 1px var(--heading-line)
      }

      .sv-profile-select,
      .sv-profile-meta-actions{
        display:none!important
      }

      .sv-profile-title{
        grid-area:title!important;
        min-width:0!important;
        overflow:hidden!important;
        text-overflow:ellipsis!important;
        white-space:nowrap!important
      }

      .sv-profile-top-meta{
        grid-area:meta!important;
        display:flex!important;
        align-items:center!important;
        justify-content:flex-end!important;
        gap:7px!important;
        min-width:0!important;
        max-width:100%!important;
        overflow:hidden!important;
        white-space:nowrap!important
      }

      .sv-profile-badges{
        flex:0 0 auto!important
      }

      .sv-profile-summary-line{
        flex:0 1 auto!important;
        min-width:0!important;
        max-width:clamp(90px,30vw,420px)!important;
        overflow:hidden!important;
        text-overflow:ellipsis!important;
        white-space:nowrap!important;
        cursor:help
      }

      .sv-profile-manager-tooltip{
        position:fixed;
        left:12px;
        right:12px;
        bottom:16px;
        z-index:1000;
        max-width:760px;
        margin:0 auto;
        padding:10px 12px;
        border:1px solid var(--heading-line);
        border-radius:10px;
        background:var(--surface);
        color:var(--text);
        box-shadow:0 8px 28px rgba(0,0,0,.34);
        font-size:var(--sv-font-small);
        line-height:1.35
      }

      @media(max-width:700px){
        .sv-profile-card{
          grid-template-columns:minmax(78px,110px) minmax(0,1fr)!important;
          column-gap:7px!important;
          padding:9px!important
        }

        .sv-profile-top-meta{
          gap:5px!important
        }

        .sv-profile-summary-line{
          max-width:clamp(88px,30vw,210px)!important
        }

        .sv-profile-badge{
          padding:2px 5px!important;
          font-size:.68rem!important
        }
      }
    `;

    document.head.appendChild(style);
  }

  function fullSummary(card) {
    const summary =
      card?.querySelector(".sv-profile-summary-line");

    return String(summary?.textContent || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function cardIndex(card) {
    const input =
      card?.querySelector("[data-profile-select]");

    return Number.parseInt(
      input?.dataset.profileSelect || "",
      10
    );
  }

  function allCards() {
    const root = $("svProfilesList");

    if (!root) return [];

    return [
      ...root.querySelectorAll(
        "article.sv-profile-card"
      ),
    ];
  }

  function cardByIndex(index) {
    return allCards().find(
      (card) => cardIndex(card) === index
    ) || null;
  }

  function checkedCards() {
    return allCards().filter((card) => {
      const input =
        card.querySelector(
          "[data-profile-select]"
        );

      return Boolean(input?.checked);
    });
  }

  function selectedCards() {
    const checked = checkedCards();

    if (checked.length) {
      return checked;
    }

    if (
      Number.isInteger(
        managerState.activeIndex
      )
    ) {
      const card =
        cardByIndex(
          managerState.activeIndex
        );

      return card ? [card] : [];
    }

    return [];
  }

  function hideTooltip() {
    const tooltip =
      $("svProfileManagerTooltip");

    if (!tooltip) return;

    tooltip.hidden = true;
    tooltip.textContent = "";

    if (managerState.tooltipTimer) {
      window.clearTimeout(
        managerState.tooltipTimer
      );
      managerState.tooltipTimer = null;
    }
  }

  function showTooltip(text) {
    const tooltip =
      $("svProfileManagerTooltip");

    if (!tooltip) return;

    tooltip.textContent = text;
    tooltip.hidden = false;

    if (managerState.tooltipTimer) {
      window.clearTimeout(
        managerState.tooltipTimer
      );
    }

    managerState.tooltipTimer =
      window.setTimeout(
        hideTooltip,
        5000
      );
  }

  function installToolbar() {
    installStyles();

    const toolbar =
      document.querySelector(
        ".sv-profiles-toolbar"
      );

    if (
      !toolbar ||
      $("svProfileManagerActions")
    ) {
      return;
    }

    const actions =
      document.createElement("div");

    actions.id =
      "svProfileManagerActions";
    actions.className =
      "sv-profile-manager-actions";

    actions.innerHTML = `
      <button
        id="svProfileManagerRefresh"
        type="button"
      >Refresh</button>

      <button
        id="svProfileManagerExport"
        class="sv-profile-manager-context"
        type="button"
        disabled
      >Export</button>

      <button
        id="svProfileManagerImport"
        class="sv-profile-manager-context"
        type="button"
        disabled
      >Import</button>

      <select
        id="svProfileManagerCopyTarget"
        class="sv-profile-manager-copy-target"
        disabled
      >
        <option value="">Copy to…</option>
      </select>

      <button
        id="svProfileManagerCopy"
        class="sv-profile-manager-context"
        type="button"
        disabled
      >Copy Profile</button>

      <button
        id="svProfileManagerSelectStale"
        class="sv-profile-manager-context"
        type="button"
        disabled
      >Select Stale</button>

      <button
        id="svProfileManagerCleanStale"
        class="danger sv-profile-manager-context"
        type="button"
        disabled
      >Clean Stale</button>

      <button
        id="svProfileManagerClear"
        class="sv-profile-manager-context"
        type="button"
        disabled
      >Clear Selection</button>

      <button
        id="svProfileManagerDelete"
        class="danger sv-profile-manager-context"
        type="button"
        disabled
      >Delete Selected</button>
    `;

    toolbar.appendChild(actions);

    let tooltip =
      $("svProfileManagerTooltip");

    if (!tooltip) {
      tooltip =
        document.createElement("div");

      tooltip.id =
        "svProfileManagerTooltip";
      tooltip.className =
        "sv-profile-manager-tooltip";
      tooltip.setAttribute(
        "role",
        "tooltip"
      );
      tooltip.hidden = true;

      document.body.appendChild(
        tooltip
      );

      tooltip.addEventListener(
        "click",
        hideTooltip
      );
    }

    $("svProfileManagerRefresh")
      .addEventListener(
        "click",
        () => {
          $("svProfilesRefresh")?.click();
        }
      );

    $("svProfileManagerExport")
      .addEventListener(
        "click",
        () => {
          const selected =
            selectedCards();

          if (selected.length === 1) {
            selected[0]
              .querySelector(
                "[data-profile-export]"
              )
              ?.click();
          }
        }
      );

    $("svProfileManagerImport")
      .addEventListener(
        "click",
        () => {
          const selected =
            selectedCards();

          if (selected.length === 1) {
            selected[0]
              .querySelector(
                "[data-profile-import]"
              )
              ?.click();
          }
        }
      );

    $("svProfileManagerCopyTarget")
      .addEventListener(
        "change",
        () => {
          const selected =
            selectedCards();

          if (selected.length === 1) {
            const hidden =
              selected[0]
                .querySelector(
                  "[data-profile-copy-target]"
                );

            if (hidden) {
              hidden.value =
                $("svProfileManagerCopyTarget")
                  .value;
            }
          }

          syncActions();
        }
      );

    $("svProfileManagerCopy")
      .addEventListener(
        "click",
        () => {
          const selected =
            selectedCards();

          if (selected.length === 1) {
            selected[0]
              .querySelector(
                "[data-profile-copy]"
              )
              ?.click();
          }
        }
      );

    $("svProfileManagerSelectStale")
      .addEventListener(
        "click",
        () => {
          managerState.activeIndex = null;
          $("svProfilesSelectStale")?.click();
          scheduleEnhance();
        }
      );

    $("svProfileManagerCleanStale")
      .addEventListener(
        "click",
        () => {
          managerState.activeIndex = null;
          $("svProfilesCleanStale")?.click();
          scheduleEnhance();
        }
      );

    $("svProfileManagerClear")
      .addEventListener(
        "click",
        () => {
          managerState.activeIndex = null;
          $("svProfilesClearSelection")
            ?.click();
          scheduleEnhance();
        }
      );

    $("svProfileManagerDelete")
      .addEventListener(
        "click",
        () => {
          const hidden =
            $("svProfilesDeleteSelected");

          if (
            hidden &&
            !hidden.disabled
          ) {
            hidden.click();
          }
        }
      );
  }

  function selectCard(card) {
    const index = cardIndex(card);

    if (!Number.isInteger(index)) {
      return;
    }

    const input =
      card.querySelector(
        "[data-profile-select]"
      );

    const alreadySelected =
      Boolean(input?.checked) ||
      managerState.activeIndex === index;

    managerState.activeIndex = null;

    const clear =
      $("svProfilesClearSelection");

    if (clear) {
      clear.click();
    }

    window.setTimeout(
      () => {
        if (alreadySelected) {
          scheduleEnhance();
          return;
        }

        const current =
          cardByIndex(index);

        const currentInput =
          current?.querySelector(
            "[data-profile-select]"
          );

        if (
          currentInput &&
          !currentInput.disabled
        ) {
          currentInput.checked = true;
          currentInput.dispatchEvent(
            new Event(
              "change",
              { bubbles: true }
            )
          );
        } else {
          managerState.activeIndex =
            index;
        }

        scheduleEnhance();
      },
      0
    );
  }

  function wireCard(card) {
    if (
      card.dataset.managerReady ===
      "true"
    ) {
      return;
    }

    card.dataset.managerReady = "true";
    card.setAttribute(
      "role",
      "button"
    );
    card.tabIndex = 0;

    const summary =
      card.querySelector(
        ".sv-profile-summary-line"
      );

    if (summary) {
      const text = fullSummary(card);
      summary.title = text;
      summary.tabIndex = 0;
      summary.setAttribute(
        "role",
        "button"
      );
      summary.setAttribute(
        "aria-label",
        "Show full profile summary"
      );

      const show = (event) => {
        event.stopPropagation();
        showTooltip(text);
      };

      summary.addEventListener(
        "click",
        show
      );

      summary.addEventListener(
        "keydown",
        (event) => {
          if (
            event.key === "Enter" ||
            event.key === " "
          ) {
            event.preventDefault();
            show(event);
          }
        }
      );
    }

    card.addEventListener(
      "click",
      (event) => {
        if (
          event.target.closest(
            "button,select,input,[data-profile-summary]"
          )
        ) {
          return;
        }

        selectCard(card);
      }
    );

    card.addEventListener(
      "keydown",
      (event) => {
        if (
          event.key === "Enter" ||
          event.key === " "
        ) {
          event.preventDefault();
          selectCard(card);
        }
      }
    );
  }

  function sectionHeading(
    label,
    count
  ) {
    const heading =
      document.createElement("div");

    heading.className =
      "sv-profile-section-heading";

    heading.innerHTML =
      `<span>${label}</span>` +
      `<span>${count}</span>`;

    return heading;
  }

  function listFor(cards) {
    const list =
      document.createElement("div");

    list.className =
      "sv-profile-group-list";

    for (const card of cards) {
      list.appendChild(card);
    }

    return list;
  }

  function subgroup(label, cards) {
    const group =
      document.createElement("div");

    group.className =
      "sv-profile-subgroup";

    const heading =
      document.createElement("div");

    heading.className =
      "sv-profile-subheading";

    heading.textContent =
      `${label} · ${cards.length}`;

    group.appendChild(heading);
    group.appendChild(
      listFor(cards)
    );

    return group;
  }

  function groupRows() {
    const root =
      $("svProfilesList");

    if (!root) return;

    const bareCards = [
      ...root.children,
    ].filter(
      (node) =>
        node.matches?.(
          "article.sv-profile-card"
        )
    );

    if (!bareCards.length) {
      return;
    }

    const active = [];
    const activeCustom = [];
    const activeNative = [];
    const unused = [];

    for (const card of bareCards) {
      wireCard(card);

      const badges =
        card.querySelector(
          ".sv-profile-badges"
        );

      const badgeNodes =
        badges
          ? [
              ...badges.querySelectorAll(
                ".sv-profile-badge"
              ),
            ]
          : [];

      if (
        badgeNodes[0]?.textContent
          ?.trim()
          .toUpperCase() ===
        "FACTORY"
      ) {
        badgeNodes[0].textContent =
          "NATIVE";
      }

      const badgeText =
        badgeNodes
          .map(
            (node) =>
              node.textContent
                .trim()
                .toUpperCase()
          )
          .join(" ");

      const isActive =
        card.classList.contains(
          "active"
        ) ||
        badgeText.includes("ACTIVE");

      if (isActive) {
        active.push(card);

        if (
          badgeText.includes("CUSTOM")
        ) {
          activeCustom.push(card);
        } else {
          activeNative.push(card);
        }
      } else {
        unused.push(card);
      }
    }

    const activeSection =
      document.createElement("section");
    activeSection.className =
      "sv-profile-section";
    activeSection.appendChild(
      sectionHeading(
        "ACTIVE PROFILES",
        active.length
      )
    );

    if (activeCustom.length) {
      activeSection.appendChild(
        subgroup(
          "CUSTOM",
          activeCustom
        )
      );
    }

    if (activeNative.length) {
      activeSection.appendChild(
        subgroup(
          "NATIVE",
          activeNative
        )
      );
    }

    if (!active.length) {
      const empty =
        document.createElement("div");
      empty.className =
        "sv-profile-empty";
      empty.textContent =
        "No active calibration profiles.";
      activeSection.appendChild(empty);
    }

    const unusedSection =
      document.createElement("section");
    unusedSection.className =
      "sv-profile-section";
    unusedSection.appendChild(
      sectionHeading(
        "UNUSED PROFILES",
        unused.length
      )
    );

    if (unused.length) {
      unusedSection.appendChild(
        listFor(unused)
      );
    } else {
      const empty =
        document.createElement("div");
      empty.className =
        "sv-profile-empty";
      empty.textContent =
        "No unused calibration profiles.";
      unusedSection.appendChild(empty);
    }

    root.replaceChildren(
      activeSection,
      unusedSection
    );
  }

  function syncVisualSelection() {
    const selected =
      new Set(
        selectedCards()
      );

    for (const card of allCards()) {
      const on =
        selected.has(card);

      card.classList.toggle(
        "manager-selected",
        on
      );

      card.setAttribute(
        "aria-selected",
        on ? "true" : "false"
      );
    }

    const selectionSummary =
      $("svProfilesSelectionSummary");

    if (selectionSummary) {
      selectionSummary.textContent =
        `${selected.size} selected`;
    }
  }

  function syncCopyTarget(card) {
    const manager =
      $("svProfileManagerCopyTarget");

    if (!manager) return false;

    const source =
      card?.querySelector(
        "[data-profile-copy-target]"
      );

    const preferred =
      manager.value ||
      source?.value ||
      "";

    manager.innerHTML =
      '<option value="">Copy to…</option>';

    if (!source) {
      manager.disabled = true;
      return false;
    }

    for (const option of source.options) {
      if (!option.value) continue;

      manager.appendChild(
        option.cloneNode(true)
      );
    }

    if (
      [...manager.options].some(
        (option) =>
          option.value === preferred
      )
    ) {
      manager.value = preferred;
    }

    manager.disabled =
      manager.options.length <= 1;

    return !manager.disabled;
  }

  function syncActions() {
    installToolbar();

    const selected =
      selectedCards();
    const single =
      selected.length === 1
        ? selected[0]
        : null;

    const exportButton =
      $("svProfileManagerExport");
    const importButton =
      $("svProfileManagerImport");
    const copyButton =
      $("svProfileManagerCopy");
    const copyTarget =
      $("svProfileManagerCopyTarget");
    const selectStale =
      $("svProfileManagerSelectStale");
    const cleanStale =
      $("svProfileManagerCleanStale");
    const clearButton =
      $("svProfileManagerClear");
    const deleteButton =
      $("svProfileManagerDelete");

    if (exportButton) {
      exportButton.disabled =
        !single ||
        !single.querySelector(
          "[data-profile-export]"
        );
    }

    if (importButton) {
      importButton.disabled =
        !single ||
        !single.querySelector(
          "[data-profile-import]"
        );
    }

    const copyAvailable =
      single
        ? syncCopyTarget(single)
        : (
            copyTarget
              ? (
                  copyTarget.innerHTML =
                    '<option value="">Copy to…</option>',
                  copyTarget.disabled = true,
                  false
                )
              : false
          );

    if (copyButton) {
      copyButton.disabled =
        !copyAvailable ||
        !copyTarget?.value;
    }

    const hiddenSelectStale =
      $("svProfilesSelectStale");
    const hiddenCleanStale =
      $("svProfilesCleanStale");
    const hiddenDelete =
      $("svProfilesDeleteSelected");

    if (selectStale) {
      selectStale.disabled =
        !hiddenSelectStale ||
        hiddenSelectStale.disabled;
    }

    if (cleanStale) {
      cleanStale.disabled =
        !hiddenCleanStale ||
        hiddenCleanStale.disabled;
    }

    if (clearButton) {
      clearButton.disabled =
        selected.length === 0;
    }

    if (deleteButton) {
      deleteButton.disabled =
        selected.length === 0 ||
        !hiddenDelete ||
        hiddenDelete.disabled;

      deleteButton.textContent =
        selected.length === 1
          ? "Delete Profile"
          : "Delete Selected";
    }

    syncVisualSelection();
  }

  function enhance() {
    managerState.enhanceQueued = false;

    const root =
      $("svProfilesList");

    if (!root) return;

    installToolbar();
    groupRows();

    for (const card of allCards()) {
      wireCard(card);
    }

    syncActions();
  }

  function scheduleEnhance() {
    if (managerState.enhanceQueued) {
      return;
    }

    managerState.enhanceQueued = true;

    window.setTimeout(
      enhance,
      0
    );
  }

  function observeProfiles() {
    const root =
      $("svProfilesList");

    if (
      !root ||
      managerState.observer
    ) {
      return;
    }

    managerState.observer =
      new MutationObserver(
        scheduleEnhance
      );

    managerState.observer.observe(
      root,
      {
        childList: true,
        subtree: true,
      }
    );
  }

  function install() {
    const api =
      window.SwitchVisionCalibrationProfiles;

    if (
      !api ||
      typeof api.load !== "function"
    ) {
      window.setTimeout(
        install,
        50
      );
      return;
    }

    if (api.__managerV2317) {
      return;
    }

    const originalLoad =
      api.load.bind(api);

    api.load = async (...args) => {
      const result =
        await originalLoad(...args);

      observeProfiles();
      scheduleEnhance();

      return result;
    };

    api.__managerV2317 = true;

    installStyles();
  }

  document.readyState === "loading"
    ? document.addEventListener(
        "DOMContentLoaded",
        install,
        { once: true }
      )
    : install();
})();
