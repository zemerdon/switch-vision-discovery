/* Generated from Core Calibration theme code; do not hand-edit. */
(() => {
const SV_CAL_THEME_SELECTORS = Object.freeze({
  field_labels: ".cv-cal-tools .cv-cal-tools-row label",
  group_labels: ".cv-cal-tools .cv-cal-quick-label",
  subsection_headings: ".cv-cal-tools .cv-cal-subsection-divider > span",
  section_headings: ".cv-cal-tools .cv-cal-section > summary > span",
  hint_text: ".cv-cal-tools .cv-cal-section > summary > small, .cv-cal-tools .cv-cal-current, .cv-cal-tools .cv-cal-section-layout-help",
  global: ".cv-cal-tools",
  workspace: ".cv-cal-tools",
  section_headers: ".cv-cal-tools .cv-cal-section > summary",
  assets: ".cv-cal-tools .cv-cal-assets-row",
  selection: '.cv-cal-tools .cv-cal-section[data-cv-section=selection] .cv-cal-tools-row:not(.cv-cal-assets-row)',
  quick_selection: ".cv-cal-tools .cv-cal-quick-row, .cv-cal-tools .cv-cal-parity-row",
  labels_leds: '.cv-cal-tools .cv-cal-section[data-cv-section=labels-leds] .cv-cal-tools-row',
  status_boxes: '.cv-cal-tools .cv-cal-section[data-cv-section=status-boxes] .cv-cal-tools-row',
  switch_stack: '.cv-cal-tools .cv-cal-section[data-cv-section=switch-stack] .cv-cal-tools-row',
  geometry: '.cv-cal-tools .cv-cal-section[data-cv-section=position-size] .cv-cal-tools-row',
  profile_actions: '.cv-cal-tools .cv-cal-section[data-cv-section=profile-actions] .cv-cal-tools-row',
  buttons: ".cv-cal-tools button:not(.cv-cal-select-trigger):not(.cv-cal-toggle)",
  inputs: ".cv-cal-tools input.cv-cal-input",
  dropdown_closed: ".cv-cal-tools select.cv-cal-select, .cv-cal-tools .cv-cal-select-shell > button.cv-cal-select-trigger",
  dropdown_open: ".cv-cal-option-menu-item, .cv-cal-option-menu-heading",
});
const SV_CAL_THEME_LIMITS = Object.freeze({
  font_size: [7, 22], padding: [0, 24], padding_horizontal: [0, 24], padding_vertical: [0, 24], gap: [0, 24],
  height: [12, 48], width: [0, 480], row_height: [0, 64], max_height: [80, 600],
  button_height: [10, 48], input_height: [10, 48], line_height: [9, 28], button_min_width: [12, 96],
  row_spacing: [0, 24], label_spacing: [0, 24], text_input_width: [0, 260], number_input_width: [0, 120],
});
function normalizeCalibrationTheme(theme) {
  const result = { desktop: {}, mobile: {} };
  for (const device of Object.keys(result)) {
    const sections = theme?.[device];
    if (!sections || typeof sections !== "object" || Array.isArray(sections)) continue;
    for (const name of Object.keys(SV_CAL_THEME_SELECTORS)) {
      const raw = sections[name];
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
      const fields = {};
      for (const [key, value] of Object.entries(raw)) {
        if (key === "font_weight" && ["regular", "bold"].includes(value)) fields[key] = value;
        else if (SV_CAL_THEME_LIMITS[key] && Number.isInteger(value) &&
          value >= SV_CAL_THEME_LIMITS[key][0] && value <= SV_CAL_THEME_LIMITS[key][1]) fields[key] = value;
      }
      if (Object.keys(fields).length) result[device][name] = fields;
    }
  }
  return result;
}
function calibrationThemeCss(theme) {
  const devices = normalizeCalibrationTheme(theme);
  return Object.entries(devices).map(([device, sections]) => {
    const rules = [];
    const globalFields = sections.global || {};
    const globalOwns = (key) => Object.prototype.hasOwnProperty.call(globalFields, key);
    for (const [name, storedFields] of Object.entries(sections)) {
      if (["global", "field_labels", "group_labels", "subsection_headings", "section_headings", "hint_text"].includes(name)) continue;
      const selector = SV_CAL_THEME_SELECTORS[name];
      if (!selector) continue;
      const fields = {...storedFields};
      // Previously saved per-section preferences remain recoverable, but new
      // global values win for any property they explicitly configure.
      for (const key of ["font_size", "font_weight", "gap"]) {
        if (globalOwns(key)) delete fields[key];
      }
      if (["padding", "padding_horizontal", "padding_vertical"].some(globalOwns)) {
        delete fields.padding;
        if (globalOwns("padding") || globalOwns("padding_horizontal")) delete fields.padding_horizontal;
        if (globalOwns("padding") || globalOwns("padding_vertical")) delete fields.padding_vertical;
      }
      const declarations = [];
      if (fields.font_size !== undefined) declarations.push("font-size:" + fields.font_size + "px!important");
      if (fields.font_weight) declarations.push("font-weight:" + (fields.font_weight === "bold" ? 700 : 400) + "!important");
      if (fields.padding !== undefined) declarations.push("padding:" + fields.padding + "px!important");
      if (fields.padding_horizontal !== undefined) declarations.push("padding-inline:" + fields.padding_horizontal + "px!important");
      if (fields.padding_vertical !== undefined) declarations.push("padding-block:" + fields.padding_vertical + "px!important");
      if (fields.gap !== undefined) declarations.push("gap:" + fields.gap + "px!important");
      if (name === "dropdown_closed" && fields.height !== undefined) {
        declarations.push("height:" + fields.height + "px!important", "min-height:" + fields.height + "px!important", "max-height:" + fields.height + "px!important");
      }
      if (name === "dropdown_closed" && fields.width > 0) declarations.push("width:" + fields.width + "px!important", "max-width:100%!important");
      if (name === "dropdown_open" && fields.row_height !== undefined) declarations.push("min-height:" + fields.row_height + "px!important");
      if (!declarations.length) continue;
      rules.push(selector + "{" + declarations.join(";") + "}");
      if (fields.font_size !== undefined || fields.font_weight) {
        const typography = declarations.filter(d => d.startsWith("font-"));
        if (!["buttons", "inputs", "dropdown_closed", "dropdown_open"].includes(name)) {
          const descendants = selector.split(", ").map(s => s + " :is(label, span, small, b, button, select, input)").join(", ");
          rules.push(descendants + "{" + typography.join(";") + "}");
        }
      }
    }
    // Shared editor-wide values. Only the Calibration UI and its detached
    // option menu are targeted; normal cards and faceplates are unaffected.
    const type = [];
    if (globalFields.font_size !== undefined) type.push("font-size:" + globalFields.font_size + "px!important");
    if (globalFields.font_weight) type.push("font-weight:" + (globalFields.font_weight === "bold" ? 700 : 400) + "!important");
    if (type.length) {
      rules.push(".cv-cal-tools .cv-cal-tools-row button, .cv-cal-tools .cv-cal-tools-row input, " +
        ".cv-cal-tools .cv-cal-select-trigger, .cv-cal-tools .cv-cal-tools-row select, .cv-cal-option-menu-item{" + type.join(";") + "}");
    }
    const padding = [];
    if (globalFields.padding !== undefined) padding.push("padding:" + globalFields.padding + "px!important");
    if (globalFields.padding_horizontal !== undefined) padding.push("padding-inline:" + globalFields.padding_horizontal + "px!important");
    if (globalFields.padding_vertical !== undefined) padding.push("padding-block:" + globalFields.padding_vertical + "px!important");
    if (padding.length) {
      const controls = ".cv-cal-tools .cv-cal-tools-row button, .cv-cal-tools .cv-cal-tools-row input.cv-cal-input, " +
        ".cv-cal-tools .cv-cal-tools-row select.cv-cal-select, .cv-cal-tools .cv-cal-section > summary, " +
        ".cv-cal-option-menu-item, .cv-cal-option-menu-heading";
      rules.push(controls + "{" + padding.join(";") + "}");
    }
    const buttons = ".cv-cal-tools .cv-cal-tools-row button:not(.cv-cal-select-trigger)";
    const inputs = ".cv-cal-tools .cv-cal-tools-row input.cv-cal-input";
    // Rows must be able to grow and wrap on mobile. A global row height is
    // a minimum, not an overflow/clipping fixed height.
    if (globalFields.row_height !== undefined) {
      rules.push(".cv-cal-tools .cv-cal-tools-row{min-height:" + globalFields.row_height + "px!important}");
    }
    if (globalFields.row_spacing !== undefined) {
      rules.push(".cv-cal-tools .cv-cal-tools-row{margin-bottom:" + globalFields.row_spacing + "px!important}");
      rules.push(".cv-cal-tools .cv-cal-section-body > .cv-cal-tools-row:last-child{margin-bottom:0!important}");
    }
    if (padding.length || globalFields.button_height !== undefined) {
      const height = globalFields.button_height === undefined ? 16 : globalFields.button_height;
      rules.push(buttons + "{height:auto!important;min-height:" + height + "px!important}");
    }
    if (padding.length || globalFields.input_height !== undefined) {
      const height = globalFields.input_height === undefined ? 16 : globalFields.input_height;
      rules.push(inputs + "{height:auto!important;min-height:" + height + "px!important}");
    }
    if (globalFields.button_min_width !== undefined) {
      rules.push(buttons + "{min-width:" + globalFields.button_min_width + "px!important}");
    }
    if (globalFields.text_input_width !== undefined && globalFields.text_input_width > 0) {
      rules.push(".cv-cal-tools .cv-cal-port-meta-row input.cv-cal-input:not([type=number]){" +
        "width:" + globalFields.text_input_width + "px!important;max-width:100%!important}");
    }
    if (globalFields.number_input_width !== undefined && globalFields.number_input_width > 0) {
      rules.push(".cv-cal-tools .cv-cal-port-meta-row input.cv-cal-input[type=number], " +
        ".cv-cal-tools .cv-cal-geometry-row input.cv-cal-coordinate-input{" +
        "width:" + globalFields.number_input_width + "px!important;max-width:100%!important}");
    }
    if (globalFields.line_height !== undefined) {
      rules.push(".cv-cal-tools, .cv-cal-tools :is(summary,small,span,label,b,button,input,select), " +
        ".cv-cal-option-menu-item, .cv-cal-option-menu-heading{" +
        "line-height:" + globalFields.line_height + "px!important}");
    }
    if (globalFields.label_spacing !== undefined) {
      rules.push(".cv-cal-tools label{gap:" + globalFields.label_spacing + "px!important}");
    }
    if (globalFields.gap !== undefined) {
      rules.push(".cv-cal-tools, .cv-cal-tools .cv-cal-tools-row, .cv-cal-tools .cv-cal-section-body{" +
        "gap:" + globalFields.gap + "px!important}");
    }
    // Four semantic Calibration text roles are completely independent from
    // global control typography. Exact role settings also override legacy
    // per-section font styling, without changing stored legacy values.
    const roleSelectors = {
      field_labels: ".cv-cal-tools .cv-cal-section[data-cv-section] .cv-cal-section-body .cv-cal-tools-row label",
      group_labels: ".cv-cal-tools .cv-cal-section[data-cv-section] .cv-cal-section-body .cv-cal-tools-row .cv-cal-quick-label",
      subsection_headings: ".cv-cal-tools .cv-cal-section[data-cv-section] .cv-cal-subsection-divider > span",
      section_headings: ".cv-cal-tools .cv-cal-section[data-cv-section] > summary > span",
      hint_text: ".cv-cal-tools .cv-cal-section[data-cv-section] > summary > small, .cv-cal-tools .cv-cal-current, .cv-cal-tools .cv-cal-section-layout-help",
    };
    for (const [role, selector] of Object.entries(roleSelectors)) {
      const settings = sections[role] || {};
      const decl = [];
      if (settings.font_size !== undefined) decl.push("font-size:" + settings.font_size + "px!important");
      if (settings.font_weight) decl.push("font-weight:" + (settings.font_weight === "bold" ? 700 : 400) + "!important");
      if (decl.length) rules.push(selector + "{" + decl.join(";") + "}");
    }
    return rules.length
      ? "@media " + (device === "mobile" ? "(max-width:760px)" : "(min-width:761px)") + "{" + rules.join("") + "}"
      : "";
  }).join(String.fromCharCode(10));
}
window.SwitchVisionCalibrationThemeCoreCss = calibrationThemeCss;
})();
