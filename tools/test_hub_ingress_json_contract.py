#!/usr/bin/env python3
"""Guard Hub ingress URL construction and non-JSON response handling."""
from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "runtime_src" / "support_web.html"
BACKEND = ROOT / "runtime_src" / "support_web.py"


class HubIngressJsonContractTests(unittest.TestCase):
    def test_status_reader_is_checked_before_json_decoding(self) -> None:
        source = HTML.read_text(encoding="utf-8")
        self.assertIn("const d=await fetchHubStatus();", source)
        self.assertIn("if(!response.ok)throw new Error", source)
        self.assertIn("response.headers.get('content-type')", source)
        self.assertIn("Hub status returned malformed JSON", source)
        self.assertIn("base.hash='';base.search='';", source)
        backend = BACKEND.read_text(encoding="utf-8")
        self.assertIn('elif path == "/api/status":', backend)
        self.assertIn('"application/json; charset=utf-8"', backend)

    def test_browser_ingress_paths_and_response_errors(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js unavailable: source contract checked separately")
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const text=fs.readFileSync(process.argv[1],'utf8');
const lines=text.split('\n');
const a=lines.find(x=>x.startsWith('function endpoint('));
const b=lines.find(x=>x.startsWith('async function fetchHubStatus('));
assert(a&&b,'Hub functions missing');
function init(href,response){
 const context={location:{href},URL,fetch:async()=>response};
 vm.createContext(context);vm.runInContext(a+'\n'+b,context);return context;
}
function res(status,type,json){
 return {ok:status>=200&&status<300,status,
   headers:{get:()=>type},json};
}
(async()=>{
 const url='https://example.test/api/hassio_ingress/abc123?panel=1#home';
 const c=init(url,res(200,'application/json; charset=utf-8',async()=>({version:'3.1.14'})));
 assert.equal(c.endpoint('api/status'),'https://example.test/api/hassio_ingress/abc123/api/status');
 assert.equal((await c.fetchHubStatus()).version,'3.1.14');
 let called=false;
 const bad=init(url,res(404,'text/plain',async()=>{called=true;throw Error('404: Not Found')}));
 await assert.rejects(bad.fetchHubStatus(),/HTTP 404/);
 assert.equal(called,false,'must reject HTTP error before JSON parse');
 const nonJson=init(url,res(200,'text/plain',async()=>{throw Error('invalid')}));
 await assert.rejects(nonJson.fetchHubStatus(),/non-JSON/);
 const malformed=init(url,res(200,'application/json',async()=>{throw Error('SyntaxError')}));
 await assert.rejects(malformed.fetchHubStatus(),/malformed JSON/);
 console.log('Hub ingress JSON browser regression: PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
        result = subprocess.run(
            [node, "-e", script, str(HTML)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
