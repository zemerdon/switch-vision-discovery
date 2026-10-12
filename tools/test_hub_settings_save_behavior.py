#!/usr/bin/env python3
"""Host-only executable regression for the shared Hub/Calibration Theme save action."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
node = shutil.which("node")
if not node:
    raise SystemExit("Node.js is required by the host-only Hub save behavior gate")

html = (ROOT / "runtime_src/support_web.html").read_text(encoding="utf-8")
fragment = html.split("async function save(){if(!dirty.size", 1)[1].split(
    "async function resetCore()", 1
)[0]
fragment = "async function save(){if(!dirty.size" + fragment

harness = r"""
const assert=require("node:assert/strict");
const dirty=new Set(), b={disabled:false}, states=[];
let pending=true, writes=0, fail=false;
const window={SwitchVisionCalibrationTheme:{
  isDirty:()=>pending,
  savePending:async()=>{writes++;if(fail)throw Error("Theme write blocked");pending=false;return true;}
}};
const q=(key)=>key==="hubSettingsSave"?b:null;
const status=(message,kind)=>states.push({message,kind});
const syncCalibrationThemeSave=()=>{b.disabled=!dirty.size&&!window.SwitchVisionCalibrationTheme?.isDirty?.()};
const noop=()=>{};
const save=new Function("dirty","q","status","req","state","clone","captureSavedCoreActivity","clear",
  "renderCore","renderSnmp","renderDiscovery","renderDeviceConfiguration",
  "renderDiscoveryBackupSettings","cleanDiscovery","window","syncCalibrationThemeSave",
  "return ("+%s+")")(
  dirty,q,status,async()=>({}),{},x=>x,noop,noop,noop,noop,noop,noop,noop,noop,window,syncCalibrationThemeSave);
(async()=>{
  await save();
  assert.equal(writes,1);
  assert.equal(pending,false);
  assert.equal(b.disabled,true);
  pending=true;fail=true;syncCalibrationThemeSave();
  await save();
  assert.equal(writes,2);
  assert.equal(pending,true);
  assert.equal(b.disabled,false);
  assert.match(states.at(-1).message,/Theme write blocked/);
  console.log("HUB_COMBINED_SAVE_BEHAVIOR_PASS");
})().catch(err=>{console.error(err);process.exit(1)});
""" % json.dumps(fragment)

result = subprocess.run([node, "-e", harness], text=True, capture_output=True, timeout=15)
if result.returncode:
    raise SystemExit(result.stdout + result.stderr)
assert "HUB_COMBINED_SAVE_BEHAVIOR_PASS" in result.stdout
print("HUB_COMBINED_SAVE_BEHAVIOR_PASS")
