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
  const BASE = [["font_size","Text size",7,22,1],["font_weight","Text weight"],["padding","Padding",0,24,1],["gap","Spacing",0,24,1]];
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
      else if (key==="gap") el.style.gap=val+"px";
      else if (key==="height") el.style.height=val+"px";
      else if (key==="width" && val>0) el.style.width=val+"px";
      else if (key==="row_height") el.style.minHeight=val+"px";
      else if (key==="max_height") el.style.maxHeight=val+"px";
    }
  }
  function preview() {
    const el=one(".cal-theme-preview");
    if (!el) return;
    el.style.maxWidth=mode==="mobile"?"300px":"100%";
    const heading=one(".cal-theme-target-name");
    if (heading) heading.textContent=GROUPS.flatMap(group=>group[2]).find(cat=>cat[0]===focusCategory)?.[1] || focusCategory;
    const examples={
      workspace:["Calibration", "Settings", "Refresh"],
      section_headers:["Selection", "Section", "Reset layout"],
      assets:["Assets", "Logo", "Refresh files"],
      selection:["Targets", "RJ45 Port", "Add RJ45"],
      quick_selection:["Quick select", "Status LEDs", "Select all"],
      labels_leds:["Port Labels", "Link LED", "Show labels"],
      status_boxes:["Status Box", "CPU / Temperature", "Show field"],
      switch_stack:["Switch & stack", "Member", "Apply"],
      geometry:["Position / size", "X / Y", "Nudge"],
      profile_actions:["Profile", "Saved profile", "Save profile"],
      buttons:["Actions", "Port manager", "Refresh files"],
      inputs:["Inputs", "RJ45 key", "Renumber"],
      dropdown_closed:["Dropdown", "Misc Targets", "Select"],
      dropdown_open:["Open menu", "Faceplate", "Select"],
    };
    const example=examples[focusCategory]||examples.assets;
    const assetsExample=one(".cal-theme-assets");
    if(assetsExample?.children[0])assetsExample.children[0].textContent=example[0];
    if(assetsExample?.children[1])assetsExample.children[1].textContent=example[1];
    const exampleButton=one(".cal-theme-button");if(exampleButton)exampleButton.textContent=example[2];
    const targets={workspace:one(".cal-theme-workspace"),section_headers:one(".cal-theme-section-head"),assets:one(".cal-theme-assets"),
      selection:one(".cal-theme-assets"),quick_selection:one(".cal-theme-assets"),labels_leds:one(".cal-theme-assets"),
      status_boxes:one(".cal-theme-assets"),switch_stack:one(".cal-theme-assets"),geometry:one(".cal-theme-assets"),
      profile_actions:one(".cal-theme-assets"),buttons:one(".cal-theme-button"),inputs:one(".cal-theme-input"),
      dropdown_closed:one(".cal-theme-dropdown"),dropdown_open:one(".cal-theme-open-menu")};
    for (const target of new Set(Object.values(targets))) if (target) target.removeAttribute("style");
    for (const opt of container().querySelectorAll(".cal-theme-option")) opt.removeAttribute("style");
    for (const category of ["workspace","section_headers","assets","buttons","inputs","dropdown_closed","dropdown_open"]) {
      apply(targets[category],values(category));
    }
    apply(targets[focusCategory],values(focusCategory));
    for (const opt of container().querySelectorAll(".cal-theme-option")) apply(opt,values("dropdown_open"));
    const menu=targets.dropdown_open;
    if (menu) menu.hidden=!one(".cal-theme-open-toggle")?.checked;
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
    const workspace=node("div","cal-theme-workspace");
    workspace.append(node("div","cal-theme-section-head","☰ Selection"));
    const assets=node("div","cal-theme-assets");
    assets.append(node("span","","Assets"),node("span","","Logo"),node("span","cal-theme-dropdown","Use card default  ▾"));
    workspace.append(assets,node("div","cal-theme-input","Port 1"),node("div","cal-theme-button","Refresh files"));
    const show=node("label","cal-theme-menu-label"), checkbox=node("input","cal-theme-open-toggle");
    checkbox.type="checkbox";checkbox.checked=true;checkbox.onchange=preview;
    show.append(checkbox,node("span","","Show open dropdown"));
    workspace.append(show);
    const menu=node("div","cal-theme-open-menu");
    for(const title of ["Use card default","Cisco 3650","Custom faceplate","Other options"]) menu.append(node("div","cal-theme-option",title));
    workspace.append(menu);pv.append(workspace);previewPanel.append(pv);
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
