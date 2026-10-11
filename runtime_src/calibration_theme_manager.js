/* Calibration-editor-only presentation, separate from saved switch geometry. */
(() => {
  "use strict";
  const GROUPS = [
    ["workspace", "Workspace & Sections", [["workspace","Workspace"],["section_headers","Section headers"]]],
    ["selection", "Assets & Selection", [["assets","Assets"],["selection","Targets & ports"],["quick_selection","Quick selection"]]],
    ["fields", "Labels & Fields", [["labels_leds","Port labels & LEDs"],["status_boxes","Status boxes"],["switch_stack","Switch & stack"],["geometry","Position & size"],["profile_actions","Profile actions"]]],
    ["controls", "Buttons & Inputs", [["buttons","Buttons"],["inputs","Inputs"]]],
    ["dropdown", "Dropdowns", [["dropdown_closed","Closed control"],["dropdown_open","Open menu & options"]]],
  ];
  const BASE = [["font_size","Text size",7,22,1],["font_weight","Text weight"],["padding","All-side padding",0,24,1],["padding_horizontal","Horizontal padding",0,24,1],["padding_vertical","Vertical padding",0,24,1],["gap","Spacing",0,24,1]];
  const EXTRA = {
    dropdown_closed: [["height","Control height",12,48,1],["width","Control width",0,480,10]],
    dropdown_open: [["row_height","Option row height",20,64,2],["width","Open menu width",0,480,10],["max_height","Maximum menu height",80,600,20]],
  };
  let mode = "desktop", theme = {desktop:{},mobile:{}}, loaded = false, dirty = false, focusCategory = "assets";
  const opened = new Set(["workspace","dropdown"]);
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
  function apply(el, fields) {
    if (!el) return;
    for (const [key,val] of Object.entries(fields || {})) {
      if (key==="font_size") el.style.fontSize=val+"px";
      else if (key==="font_weight") el.style.fontWeight=val==="bold"?"700":"400";
      else if (key==="padding") el.style.padding=val+"px";
      else if (key==="padding_horizontal") el.style.paddingInline=val+"px";
      else if (key==="padding_vertical") el.style.paddingBlock=val+"px";
      else if (key==="gap") el.style.gap=val+"px";
      else if (key==="height") el.style.height=val+"px";
      else if (key==="width" && val>0) el.style.width=val+"px";
      else if (key==="row_height") el.style.minHeight=val+"px";
      else if (key==="max_height") el.style.maxHeight=val+"px";
    }
  }
  // Real Calibration class names, read-only sample values, and exact Core CSS.
  // No card instance, MQTT state, profile calls or Calibration event handlers.
  const FIELD_EXAMPLES = {
    workspace: '<div class="cv-cal-context-grid"><span><small>Switch</small><b>SW1</b></span><span><small>Model</small><b>Cisco 3650</b></span><span><small>Faceplate</small><b>Default</b></span><span><small>Profile</small><b>Factory</b></span></div><div class="cv-cal-section-layout-help"><span>Drag <b>☰</b> to arrange sections for your current job.</span><button type="button">Reset section layout</button></div>',
    section_headers: '<div class="cv-cal-tools-row cv-cal-port-manager-row"><label>RJ45 Targets<select class="cv-cal-select"><option>Port 1</option></select></label><button type="button">Add RJ45</button></div>',
    assets: '<div class="cv-cal-tools-row cv-cal-style-row cv-cal-assets-row"><span class="cv-cal-quick-label">Assets</span><label>Logo<select class="cv-cal-select" data-cv-field="logo-file"><option>Use card default</option></select></label><label>Faceplate<select class="cv-cal-select" data-cv-field="faceplate-file"><option>Cisco 3650 (Default / recommended)</option></select></label><button type="button">Refresh files</button><span class="cv-cal-current">2 assets available</span></div>',
    selection: '<div class="cv-cal-tools-row cv-cal-port-manager-row cv-cal-port-manager-main"><label>Misc Targets<select class="cv-cal-select cv-cal-target-select"><option>Logo</option></select></label><label>RJ45 Targets<select class="cv-cal-select cv-cal-target-select"><option>Port 1</option></select></label><label>SFP Targets<select class="cv-cal-select cv-cal-target-select"><option>SFP1</option></select></label><label>Part<select class="cv-cal-select"><option>Entire Port</option></select></label><span class="cv-cal-quick-label">Port manager</span><button type="button">Add RJ45</button><button type="button">Add SFP</button><button type="button">Duplicate selected</button><button type="button">Remove selected</button></div>',
    quick_selection: '<div class="cv-cal-subsection-divider"><span>Quick selection</span></div><div class="cv-cal-tools-row cv-cal-quick-row"><span class="cv-cal-quick-label">Quick select</span><button type="button">Status LEDs</button><button type="button">All RJ45</button><button type="button">All SFP</button><button type="button">Port Labels</button><button type="button">All Link LEDs</button><button type="button">All Activity LEDs</button><button type="button">RJ45 Link</button></div>',
    labels_leds: '<div class="cv-cal-tools-row cv-cal-style-row cv-cal-port-presentation-row"><span class="cv-cal-quick-label">Port Label</span><button type="button">Show labels</button><label>Port label<select class="cv-cal-select"><option>Port Number</option></select></label><span class="cv-cal-quick-label">Link LED</span><label>Shape<select class="cv-cal-select"><option>Circle</option></select></label><span class="cv-cal-quick-label">Activity LED</span><label>Shape<select class="cv-cal-select"><option>Circle</option></select></label></div>',
    status_boxes: '<div class="cv-cal-tools-row cv-cal-status-quick-row"><span class="cv-cal-quick-label">Status Box 1</span><button type="button">Box</button><button type="button">All fields</button><button type="button">All labels</button><button type="button">All values</button><span class="cv-cal-quick-label">Status Box 2</span><button type="button">Box</button><button type="button">All fields</button><button type="button">All labels</button><button type="button">All values</button></div>',
    switch_stack: '<div class="cv-cal-tools-row cv-cal-switch-stack-row"><span class="cv-cal-quick-label">Switch &amp; Stack</span><label>Switch label<input class="cv-cal-input" value="SW1" readonly></label><label>Stack member<input class="cv-cal-input" value="1" readonly></label><button type="button">Apply</button></div>',
    geometry: '<div class="cv-cal-tools-row cv-cal-geometry-row"><span class="cv-cal-quick-label">Nudge</span><button type="button">←</button><button type="button">↑</button><button type="button">↓</button><button type="button">→</button><label>Step<select class="cv-cal-select"><option>1px</option></select></label><label>X<input class="cv-cal-input cv-cal-coordinate-input" value="120" readonly></label><label>Y<input class="cv-cal-input cv-cal-coordinate-input" value="20" readonly></label></div>',
    profile_actions: '<div class="cv-cal-tools-row cv-cal-profile-controls"><span class="cv-cal-quick-label">Profile</span><label>Calibration profile<select class="cv-cal-select"><option>Factory</option></select></label><button type="button">Save profile</button><button type="button">Load profile</button><button type="button">Reset</button></div>',
    buttons: '<div class="cv-cal-tools-row cv-cal-port-manager-row"><span class="cv-cal-quick-label">Port manager</span><button type="button">Add RJ45</button><button type="button">Add SFP</button><button type="button">Duplicate selected</button><button type="button" class="cv-cal-primary">Refresh files</button><button type="button" class="cv-cal-warning">Remove selected</button></div>',
    inputs: '<div class="cv-cal-tools-row cv-cal-port-meta-row"><label>RJ45 key<input class="cv-cal-input" type="number" value="1" readonly></label><button type="button">Renumber</button><label>SFP key<input class="cv-cal-input" value="SFP1" readonly></label><button type="button">Rename</button><label>Display name<input class="cv-cal-input" value="Port 1" readonly></label><button type="button">Set name</button></div>',
    dropdown_closed: '<div class="cv-cal-tools-row cv-cal-style-row cv-cal-assets-row"><span class="cv-cal-quick-label">Assets</span><label>Logo<span class="cv-cal-select-shell"><select class="cv-cal-select" aria-hidden="true"><option>Use card default</option></select><button type="button" class="cv-cal-select-trigger">Use card default</button></span></label><label>Faceplate<span class="cv-cal-select-shell"><select class="cv-cal-select" aria-hidden="true"><option>Cisco 3650</option></select><button type="button" class="cv-cal-select-trigger">Cisco 3650</button></span></label></div>',
    dropdown_open: '<div class="cv-cal-tools-row cv-cal-style-row cv-cal-assets-row"><span class="cv-cal-quick-label">Assets</span><label>Faceplate<span class="cv-cal-select-shell"><select class="cv-cal-select" aria-hidden="true"><option>Use card default</option></select><button type="button" class="cv-cal-select-trigger">Use card default</button></span></label></div>',
  };
  const REAL_SECTIONS = {
    geometry:"position-size",labels_leds:"labels-leds",status_boxes:"status-boxes",
    switch_stack:"switch-stack",profile_actions:"profile-actions",
  };
  function preview() {
    const frame=one(".cal-theme-real-iframe");
    if (!frame) return;
    const mobile=mode==="mobile", selected=theme[mode]||{};
    frame.style.width=mobile?"360px":"850px";
    frame.style.height=focusCategory==="dropdown_open"?"440px":"345px";
    const caption=one(".cal-theme-target-name");
    if (caption) caption.textContent=GROUPS.flatMap(g=>g[2]).find(c=>c[0]===focusCategory)?.[1] || focusCategory;
    // This is generated directly from the actual Core card function.
    // Matching the selected values on both media sides lets the iframe's own
    // viewport choose the real Desktop/Mobile media breakpoint.
    const css=window.SwitchVisionCalibrationThemeCoreCss?.({desktop:selected,mobile:selected})||"";
    const options=selected.dropdown_open||{};
    const menuWidth=options.width||220, menuHeight=options.max_height||320;
    const showMenu=focusCategory==="dropdown_open" || (one(".cal-theme-open-toggle")?.checked||false);
    const menu=showMenu?'<div class="cv-cal-option-menu" role="listbox" aria-label="Faceplate options" style="position:relative!important;inset:auto!important;width:'+menuWidth+'px;max-height:'+menuHeight+'px;margin:8px 0;"><div class="cv-cal-option-menu-heading">Faceplates</div><button class="cv-cal-option-menu-item" aria-selected="true">Use card default</button><button class="cv-cal-option-menu-item">Cisco 3650</button><button class="cv-cal-option-menu-item">Custom faceplate</button></div>':"";
    const name=REAL_SECTIONS[focusCategory]||"selection";
    const field=FIELD_EXAMPLES[focusCategory]||FIELD_EXAMPLES.assets;
    const section='<details class="cv-cal-section" data-cv-section="'+name+'" open><summary><span>'+
      (focusCategory==="geometry"?"Position & Size":focusCategory==="labels_leds"?"Port Labels & LEDs":focusCategory==="status_boxes"?"Status Boxes":focusCategory==="switch_stack"?"Switch & Stack":focusCategory==="profile_actions"?"Profiles":"Selection")+
      '</span><small>Port 1 · 24 ports</small></summary><div class="cv-cal-section-body">'+field+'</div></details>';
    const url=String(endpoint("calibration_theme_core.css")).replace(/&/g,"&amp;").replace(/"/g,"&quot;");
    frame.srcdoc='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="'+url+'"><style>'+
      ':root{--cv-text:#eef7ff;--cv-muted:#b9d7ea;}html,body{margin:0;background:#101a22;color:#eef7ff;font:12px Arial,sans-serif;}'+
      '.cv-cal-tools{margin:0;min-height:100px}.cv-cal-option-menu{max-width:calc(100% - 16px);}' +
      css+'</style></head><body><div class="cv-cal-tools" inert>'+
      (focusCategory==="workspace"?field:section)+menu+'</div></body></html>';
  }
  function optionsSelect(category, [key, title, min, max, step]) {
    const label=node("label","cal-theme-setting"), text=node("span","",title), select=node("select");
    select.setAttribute("aria-label",category+" "+title);
    const add=(value,label)=>{const opt=node("option","",label);opt.value=String(value);select.append(opt);};
    add("","Default (unchanged)");
    if (key==="font_weight") {add("regular","Regular");add("bold","Bold");}
    else {
      for (let i=min;i<=max;i+=step) add(i,i===0&&key==="width"?"Auto":i+" px");
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
      dirty=true;focusCategory=category;
      const save=one(".cal-theme-save");if(save)save.disabled=false;
      preview();status("Unsaved "+mode+" Calibration Theme changes.");
    };
    label.append(text,select);return label;
  }
  function draw() {
    const root=container();if(!root)return;
    root.textContent="";
    root.append(node("h3","","Calibration Theme"),node("p","muted","Calibration editor only. Desktop and Mobile settings are independent; switch geometry, cards and profiles never change."));
    const modes=node("div","cal-theme-modes");
    for (const name of ["desktop","mobile"]) {
      const button=node("button",name===mode?"selected":"",name==="desktop"?"Desktop":"Mobile");
      button.type="button";button.setAttribute("aria-pressed",String(name===mode));
      button.onclick=()=>{
        for (const el of root.querySelectorAll("[data-cal-theme-group]")) el.open?opened.add(el.dataset.calThemeGroup):opened.delete(el.dataset.calThemeGroup);
        mode=name;draw();
      };
      modes.append(button);
    }
    root.append(modes);
    const layout=node("div","cal-theme-layout"), list=node("div","cal-theme-list");
    for (const [id,title,categories] of GROUPS) {
      const group=node("details","cal-theme-group");
      group.dataset.calThemeGroup=id;group.open=opened.has(id);
      group.addEventListener("toggle",()=>group.open?opened.add(id):opened.delete(id));
      group.append(node("summary","",title));
      for (const [category,label] of categories) {
        const section=node("details","cal-theme-category");
        section.open=focusCategory===category;
        section.append(node("summary","",label));
        section.addEventListener("toggle",()=>{if(section.open){focusCategory=category;preview();}});
        const fields=node("div","cal-theme-fields");
        for (const field of [...BASE,...(EXTRA[category]||[])]) fields.append(optionsSelect(category,field));
        const reset=node("button","cal-theme-reset-section","Reset section");
        reset.type="button";
        reset.onclick=()=>{delete theme[mode][category];dirty=true;focusCategory=category;draw();status("Section reset; save to apply.");};
        section.append(fields,reset);group.append(section);
      }
      list.append(group);
    }
    const previewPanel=node("div","cal-theme-preview-panel");
    previewPanel.append(node("h4","","Live preview — "+mode),node("p","muted","Try settings here before saving to Core."));
    const pv=node("div","cal-theme-preview");
    pv.append(node("div","cal-theme-target-name","Assets"));
    const show=node("label","cal-theme-menu-label"), checkbox=node("input","cal-theme-open-toggle");
    checkbox.type="checkbox";checkbox.checked=false;checkbox.onchange=preview;
    show.append(checkbox,node("span","","Show the real open dropdown menu"));
    pv.append(show);
    const viewport=node("div","cal-theme-viewport");
    const frame=node("iframe","cal-theme-real-iframe");
    frame.setAttribute("sandbox","");
    frame.setAttribute("title","Read-only Core Calibration field preview");
    frame.setAttribute("loading","eager");
    viewport.append(frame);pv.append(viewport);previewPanel.append(pv);
    layout.append(list,previewPanel);root.append(layout);
    const actions=node("div","cal-theme-actions");
    const save=node("button","primary cal-theme-save","Save Calibration Theme");
    save.type="button";save.disabled=!dirty;save.onclick=saveChanges;
    const reset=node("button","","Reset "+mode);
    reset.type="button";reset.onclick=()=>{theme[mode]={};dirty=true;draw();status(mode+" reset to defaults; save to apply.");};
    const reload=node("button","","Discard changes");
    reload.type="button";reload.onclick=()=>{loaded=false;dirty=false;void load();};
    actions.append(save,reset,reload);root.append(actions,node("p","cal-theme-status muted",""));
    status(dirty?"Unsaved Calibration Theme changes.":"Settings loaded from Core.");preview();
  }
  async function load() {
    if(loaded)return;
    const root=container();if(!root)return;
    root.textContent="Loading Calibration Theme…";
    try {
      const res=await fetch(endpoint("api/settings/core"),{cache:"no-store"});
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
