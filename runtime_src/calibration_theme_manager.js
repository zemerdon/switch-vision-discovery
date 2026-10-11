/* Calibration-editor-only presentation, separate from saved switch geometry. */
(() => {
  "use strict";
  const SETTINGS = [
    ["Global Calibration Controls", "global", [
      ["font_size","Text size",7,22,1],["font_weight","Text weight"],
      ["padding","All-side padding",0,24,1],["padding_horizontal","Horizontal padding",0,24,1],
      ["padding_vertical","Vertical padding",0,24,1],["gap","Control spacing",0,24,1],
      ["row_height","Minimum row height",0,64,1],["row_spacing","Space between rows",0,24,1],
      ["button_height","Minimum button height",10,48,1],["button_min_width","Minimum button width",12,96,1],
      ["input_height","Minimum input height",10,48,1],["line_height","Text line height",9,28,1],
      ["label_spacing","Label spacing",0,24,1],
      ["text_input_width","Text input width",0,260,5],["number_input_width","Number input width",0,120,1],
    ]],
    ["Field Labels — RJ45 Targets", "field_labels", [
      ["font_size","Text size",7,22,1],["font_weight","Text weight"],
    ]],
    ["Group Labels — Port manager", "group_labels", [
      ["font_size","Text size",7,22,1],["font_weight","Text weight"],
    ]],
    ["Subsection Headings — Quick selection", "subsection_headings", [
      ["font_size","Text size",7,22,1],["font_weight","Text weight"],
    ]],
    ["Section Headings — Selection", "section_headings", [
      ["font_size","Text size",7,22,1],["font_weight","Text weight"],
    ]],
    ["Hint Text — Section descriptions and help", "hint_text", [
      ["font_size","Text size",7,22,1],["font_weight","Text weight"],
    ]],
    ["Closed Dropdowns", "dropdown_closed", [
      ["height","Control height",12,48,1],["width","Control width",0,480,10],
    ]],
    ["Open Dropdown Menu", "dropdown_open", [
      ["row_height","Option row height",12,64,1],
      ["width","Open menu width",0,480,10],["max_height","Maximum menu height",80,600,20],
    ]],
  ];
  // Describe the installed Core starting points, not invented uniform defaults.
  // Every numeric size with a fixed baseline has options on BOTH sides.
  const CORE_DEFAULTS = Object.freeze({
    font_size:"11–12 px (varies)", font_weight:"Core defaults (varies)",
    padding:"Core defaults (1px vertical, 2px horizontal)",
    padding_horizontal:"2 px (typical)", padding_vertical:"1 px (typical)",
    gap:"5–8 px (varies)", row_height:"Auto (content height)",
    row_spacing:"6 px", button_height:"16 px", button_min_width:"30 px",
    input_height:"16 px", line_height:"12 px", label_spacing:"5 px",
    text_input_width:"127 px", number_input_width:"110 px (X/Y/W/H), 61 px (other)",
    height:"16 px", width:"Auto / content width",
    max_height:"320 px, viewport-limited",
  });
  let mode = "desktop", theme = {desktop:{},mobile:{}}, loaded = false, dirty = false;
  let corePreviewCss = "";

  const container = () => document.getElementById("hubCalibrationThemeSettings");
  const one = (selector) => container()?.querySelector(selector);
  const node = (tag, cls, text) => {
    const el=document.createElement(tag);
    if (cls) el.className=cls;
    if (text !== undefined) el.textContent=text;
    return el;
  };
  const values = category => theme[mode]?.[category] || {};
  const clone = value => JSON.parse(JSON.stringify(value));
  function status(message, cls="") {
    const el=one(".cal-theme-status");
    if (el) {el.className="cal-theme-status muted "+cls;el.textContent=message;}
  }
  // Real Calibration class names, read-only sample values, and exact Core CSS.
  // No card instance, MQTT state, profile calls or Calibration event handlers.
  // Mirror Core's in-page dropdown shell after Calibration initializes.
  // Values and labels come only from the static read-only preview fixtures.
  function materializePreviewSelectShells(html) {
    const template=document.createElement("template");
    template.innerHTML=html;
    for (const select of template.content.querySelectorAll("select.cv-cal-select")) {
      if (select.parentElement?.classList.contains("cv-cal-select-shell")) continue;
      const shell=document.createElement("span");
      shell.className="cv-cal-select-shell";
      const trigger=document.createElement("button");
      trigger.type="button";
      trigger.className="cv-cal-select-trigger";
      trigger.textContent=select.selectedOptions?.[0]?.textContent?.trim()||"Select";
      select.setAttribute("aria-hidden","true");
      select.tabIndex=-1;
      select.parentElement.replaceChild(shell,select);
      shell.append(select,trigger);
    }
    for(const button of template.content.querySelectorAll("button:not(.cv-cal-select-trigger)")) button.remove();
    return template.innerHTML;
  }
  // Each preview is a tiny, read-only example of its real Calibration
  // control. Multi-button rows are drawn from Core's verified inventory.
  function buttonRow(name="cv-cal-port-manager-row", limit=4) {
    const fixture=window.SwitchVisionCalibrationSelectionButtons;
    const row=fixture?.rows?.find(item=>item.css.includes(name));
    if(!row)return "";
    const div=document.createElement("div");
    div.className=row.css;
    for(const token of row.tokens) {
      if(token[0]==="label") {
        const label=document.createElement("span");
        label.className="cv-cal-quick-label";label.textContent=token[1];
        div.append(label);
      } else if(div.querySelectorAll("button").length<limit) {
        const button=document.createElement("button");
        button.type="button";button.textContent=token[2];
        div.append(button);
      }
    }
    return div.outerHTML;
  }
  function exampleHtml(category,key,selected) {
    const buttons=buttonRow("cv-cal-port-manager-row",4);
    const quick=buttonRow("cv-cal-quick-row",4);
    const field=materializePreviewSelectShells(
      '<div class="cv-cal-tools-row cv-cal-port-manager-row cv-cal-port-manager-main">'+
      '<label>RJ45 Targets<select class="cv-cal-select cv-cal-target-select"><option>Port 1</option></select></label></div>'
    );
    const input='<div class="cv-cal-tools-row cv-cal-port-meta-row">'+
      '<label>RJ45 key<input class="cv-cal-input" type="number" value="1" readonly></label>'+
      '<label>Display name<input class="cv-cal-input" value="Port 1" readonly></label></div>';
    if(category==="field_labels")return field;
    if(category==="group_labels")return buttons;
    if(category==="subsection_headings")return '<div class="cv-cal-subsection-divider"><span>Quick selection</span></div>'+quick;
    if(category==="section_headings")return '<details class="cv-cal-section" data-cv-section="selection" open>'+
      '<summary><span>Selection</span><small>Port 1 · 24 ports</small></summary></details>';
    if(category==="hint_text")return '<details class="cv-cal-section" data-cv-section="selection" open>'+
      '<summary><span>Selection</span><small>Port 1 · 24 ports</small></summary>'+
      '<div class="cv-cal-section-body"><span class="cv-cal-current">Detected image dimensions appear after selection.</span></div></details>';
    if(category==="dropdown_closed")return field;
    if(category==="dropdown_open") {
      const options=selected.dropdown_open||{};
      const width=options.width||220, maxHeight=options.max_height||320;
      return field+
      '<div class="cv-cal-option-menu" role="listbox" aria-label="Port choices" '+
      'style="position:relative!important;inset:auto!important;margin:4px 0;width:'+width+'px;max-width:100%;max-height:'+maxHeight+'px;">'+
      '<div class="cv-cal-option-menu-heading">RJ45 Targets</div>'+
      Array.from({length:key==="max_height"?64:3},(_,i)=>'<button class="cv-cal-option-menu-item"'+
        (i===0?' aria-selected="true"':'')+'>Port '+(i+1)+'</button>').join("")+
      '</div>';
    }
    if(["input_height","text_input_width","number_input_width","label_spacing"].includes(key)) return input;
    if(["row_height","row_spacing"].includes(key))return buttons+quick;
    // Four genuine adjacent action buttons reveal text size, weight, padding,
    // width and wrapping much better than a solitary mock button.
    return buttons;
  }
  function preview() {
    const selected=theme[mode]||{};
    const css=window.SwitchVisionCalibrationThemeCoreCss?.({desktop:selected,mobile:selected})||"";
    for(const frame of container()?.querySelectorAll(".cal-theme-sample-frame")||[]) {
      const category=frame.dataset.category, key=frame.dataset.field;
      const html=exampleHtml(category,key,selected);
      // Frames contain only static, inert Core-styled controls; sandboxed
      // scripts remain disabled. Read back the rendered document height so
      // tall rows and the real open-menu max height cannot be clipped.
      frame.style.height="80px";
      frame.srcdoc='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'+
        '<style>'+corePreviewCss+'</style><style>'+
        ':root{--cv-text:#eef7ff;--cv-muted:#b9d7ea;}html,body{margin:0;padding:0;background:#101a22;color:#eef7ff;font:12px Arial,sans-serif;}'+
        '.cv-cal-tools{margin:0;min-height:0;padding:4px!important} .cv-cal-tools-row{flex-wrap:wrap!important}'+
        '.cv-cal-option-menu{z-index:1!important;overflow:auto;}'+
        css+'</style></head><body><div class="cv-cal-tools" inert>'+
        '<div class="cv-cal-section" data-cv-section="selection"><div class="cv-cal-section-body">'+
        html+'</div></div></div></body></html>';
    }
  }
  function optionsSelect(category, [key, title, min, max, step]) {
    const field=node("div","cal-theme-setting-with-preview");
    const label=node("label","cal-theme-setting"), text=node("span","",title), select=node("select");
    select.setAttribute("aria-label",category+" "+title);
    const add=(value,label)=>{const opt=node("option","",label);opt.value=String(value);select.append(opt);};
    const baseline = category==="dropdown_open" && key==="row_height" ? "32 px" : CORE_DEFAULTS[key] || "Core defaults";
    add("","Core default (" + baseline + ")");
    if (key==="font_weight") {add("regular","Regular");add("bold","Bold");}
    else {
      for (let i=min;i<=max;i+=step) add(i,i===0&&["width","text_input_width","number_input_width","row_height"].includes(key)?"Auto / no extra minimum":i+" px");
      const actual=values(category)[key];
      if (actual!==undefined && !Array.from(select.options).some(o=>o.value===String(actual))) add(actual,actual+" px");
    }
    select.value=values(category)[key]===undefined?"":String(values(category)[key]);
    select.onchange=()=>{
      const group={...values(category)};
      if (select.value==="") delete group[key];
      else group[key]=key==="font_weight"?select.value:Number(select.value);
      if (Object.keys(group).length) theme[mode][category]=group;
      else delete theme[mode][category];
      dirty=true;
      const save=one(".cal-theme-save");if(save)save.disabled=false;
      preview();status("Unsaved "+mode+" Calibration Theme changes.");
    };
    label.append(text,select);field.append(label);
    const sample=node("div","cal-theme-inline-sample");
    const frame=node("iframe","cal-theme-sample-frame");
    // Same-origin permits parent-only layout measurement. Sandboxed scripts,
    // navigation and form submission are still prohibited; content is inert.
    frame.setAttribute("sandbox","allow-same-origin");
    frame.setAttribute("title","Read-only Calibration "+title+" example");
    frame.dataset.category=category;frame.dataset.field=key;
    frame.addEventListener("load",()=>{
      if(!frame.isConnected)return;
      let height=0;
      try {
        const doc=frame.contentDocument;
        height=Math.max(doc?.body?.scrollHeight||0,doc?.documentElement?.scrollHeight||0);
      } catch(_) { /* Use the bounded fallback if a browser restricts access. */ }
      if(!height) {
        const selected=theme[mode]||{};
        height=category==="dropdown_open"?
          (key==="max_height"?(selected.dropdown_open?.max_height||320)+100:260):
          (key==="row_height"||key==="row_spacing"?
            2*(selected.global?.row_height||64)+3*(selected.global?.row_spacing||12)+220:200);
      }
      frame.style.height=Math.ceil(Math.max(80,height)+12)+"px";
    });
    sample.append(frame);field.append(sample);
    return field;
  }
  function draw() {
    const root=container();if(!root)return;
    root.textContent="";
    root.append(
      node("h3","","Calibration Theme"),
      node("p","muted","One set of global Calibration controls per device. Saved switch geometry, dashboards and profiles are unchanged.")
    );
    const modes=node("div","cal-theme-modes");
    for(const device of ["desktop","mobile"]){
      const button=node("button",device===mode?"selected":"",device==="desktop"?"Desktop":"Mobile");
      button.type="button";
      button.setAttribute("aria-pressed",String(device===mode));
      button.onclick=()=>{mode=device;draw();};
      modes.append(button);
    }
    root.append(modes);
    const layout=node("div","cal-theme-layout");
    const settings=node("section","cal-theme-all-settings");
    settings.append(node("h4","","Global Settings"));
    for(const [heading,category,fields] of SETTINGS){
      settings.append(node("h5","cal-theme-settings-heading",heading));
      const grid=node("div","cal-theme-fields");
      for(const field of fields)grid.append(optionsSelect(category,field));
      settings.append(grid);
    }
    settings.append(node("p","muted","Global controls apply throughout Calibration. Closed and open dropdown measurements are separate only where needed. Older detailed preferences are retained, with global values taking priority."));
    layout.append(settings);
    root.append(layout);
    const actions=node("div","cal-theme-actions");
    const save=node("button","primary cal-theme-save","Save Calibration Theme");
    save.type="button";save.disabled=!dirty;save.onclick=saveChanges;
    const reset=node("button","","Reset "+mode);
    reset.type="button";reset.onclick=()=>{theme[mode]={};dirty=true;draw();status(mode+" settings reset; save to apply.");};
    const discard=node("button","","Discard changes");
    discard.type="button";discard.onclick=()=>{loaded=false;dirty=false;void load();};
    actions.append(save,reset,discard);
    root.append(actions,node("p","cal-theme-status muted",""));
    status(dirty?"Unsaved Calibration Theme changes.":"Settings loaded from Core.");
    preview();
  }
  async function load() {
    if(loaded)return;
    const root=container();if(!root)return;
    root.textContent="Loading Calibration Theme…";
    try {
      const [res,cssResponse]=await Promise.all([
        fetch(endpoint("api/settings/core"),{cache:"no-store"}),
        fetch(endpoint("calibration_theme_core.css"),{cache:"no-store"}),
      ]);
      if(!cssResponse.ok)throw Error("Core Calibration preview stylesheet unavailable");
      const cssText=await cssResponse.text();
      if(!cssText.includes(".cv-cal-tools{")||cssText.toLowerCase().includes("</style")||typeof window.SwitchVisionCalibrationThemeCoreCss!=="function")
        throw Error("Core Calibration preview assets are invalid");
      if((window.SwitchVisionCalibrationSelectionButtons?.count||0)<48)
        throw Error("Core Selection preview button inventory is incomplete");
      corePreviewCss=cssText;
      const body=await res.json();
      if(!res.ok||!body.settings)throw Error(body.error||"Core settings unavailable");
      theme=clone(body.settings.calibration_theme?.calibration_theme||{desktop:{},mobile:{}});
      if(!theme.desktop||!theme.mobile)theme={desktop:{},mobile:{}};
      loaded=true;dirty=false;draw();
    } catch(err) {root.textContent="Cannot load Calibration Theme: "+(err?.message||err);}
  }
  async function saveChanges() {
    const button=one(".cal-theme-save");if(button)button.disabled=true;
    status("Saving Calibration Theme…");
    try {
      const res=await fetch(endpoint("api/settings/core"),{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({settings:{calibration_theme:{calibration_theme:theme}}})});
      const body=await res.json();
      if(!res.ok||!body.settings)throw Error(body.error||"Save failed");
      theme=clone(body.settings.calibration_theme.calibration_theme);
      dirty=false;draw();status("Calibration Theme saved to Core.","success");
    } catch(err) {
      if(button)button.disabled=false;
      status("Save failed: "+(err?.message||err),"failure");
    }
  }
  window.SwitchVisionCalibrationTheme={load};
})();
