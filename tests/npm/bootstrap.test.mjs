import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,existsSync,writeFileSync,mkdirSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';

const root=resolve(import.meta.dirname,'../..');
const cli=join(root,'bin/agent-monitor.mjs');

test('init downloads a complete runnable project without local evidence',t=>{
  const folder=mkdtempSync(join(tmpdir(),'agent-monitor-download-'));t.after(()=>rmSync(folder,{recursive:true,force:true}));
  const dest=join(folder,'my monitor');
  const result=spawnSync(process.execPath,[cli,'init',dest],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
  for(const file of ['monitor/cli.py','rules/rules.json','prompts/triage.txt','dashboard/dist/index.html','dashboard/src/App.tsx','pyproject.toml','uv.lock','bin/start.mjs'])assert.ok(existsSync(join(dest,file)),file);
  assert.equal(readFileSync(join(dest,'monitor/cascade.py'),'utf8'),readFileSync(join(root,'monitor/cascade.py'),'utf8'));
  for(const path of ['logs','results','data/real','.venv','.git','.superpowers','docs/screenshots','dashboard/node_modules'])assert.equal(existsSync(join(dest,path)),false,path);
  const metadata=JSON.parse(readFileSync(join(dest,'package.json'),'utf8'));
  assert.equal(metadata.scripts.start,'node bin/start.mjs');
});

test('init refuses to overwrite an existing directory',t=>{
  const folder=mkdtempSync(join(tmpdir(),'agent-monitor-preserve-'));t.after(()=>rmSync(folder,{recursive:true,force:true}));
  writeFileSync(join(folder,'keep.txt'),'existing content');
  const result=spawnSync(process.execPath,[cli,'init',folder],{encoding:'utf8'});
  assert.notEqual(result.status,0);
  assert.equal(readFileSync(join(folder,'keep.txt'),'utf8'),'existing content');
  assert.equal(existsSync(join(folder,'monitor')),false);
});

test('CLI forwards arguments unchanged to uv using the selected project',t=>{
  const folder=mkdtempSync(join(tmpdir(),'agent-monitor-launch-'));t.after(()=>rmSync(folder,{recursive:true,force:true}));
  const executable=join(folder,'uv');
  writeFileSync(executable,'#!/usr/bin/env node\nrequire("node:fs").writeFileSync(process.env.CAPTURE,JSON.stringify({args:process.argv.slice(2),cwd:process.cwd()}));\n',{mode:0o755});
  const capture=join(folder,'call.json');
  const text='literal $(touch should-not-exist); `whoami`';
  const result=spawnSync(process.execPath,[cli,'report','--out',text],{cwd:root,encoding:'utf8',env:{...process.env,PATH:folder+':'+process.env.PATH,CAPTURE:capture}});
  assert.equal(result.status,0,result.stderr);
  const call=JSON.parse(readFileSync(capture,'utf8'));
  assert.deepEqual(call.args,['run','--extra','dashboard','monitor','report','--out',text]);
  assert.equal(call.cwd,root);
  assert.equal(existsSync(join(root,'should-not-exist')),false);
});

test('missing uv gives a useful setup error',t=>{
  const folder=mkdtempSync(join(tmpdir(),'agent-monitor-no-uv-'));t.after(()=>rmSync(folder,{recursive:true,force:true}));
  const result=spawnSync(process.execPath,[cli,'doctor'],{cwd:root,encoding:'utf8',env:{...process.env,PATH:folder}});
  assert.equal(result.status,1);
  assert.match(result.stderr,/Install uv/);
});
