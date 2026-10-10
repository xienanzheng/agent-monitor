import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,existsSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawnSync,spawn} from 'node:child_process';
import {once} from 'node:events';
import {createHash} from 'node:crypto';

const root=resolve(import.meta.dirname,'../..');

test('packed npm artifact includes built assets and source without local evidence',t=>{
  const temp=mkdtempSync(join(tmpdir(),'agent-monitor-pack-'));
  t.after(()=>rmSync(temp,{recursive:true,force:true}));
  const out=join(temp,'release');
  const built=spawnSync(process.execPath,[join(root,'scripts/package-release.mjs'),out],{encoding:'utf8'});
  assert.equal(built.status,0,built.stderr);
  const report=JSON.parse(readFileSync(join(out,'npm-pack.json'),'utf8'))[0];
  const paths=report.files.map(file=>file.path);
  for(const file of ['app/dashboard/dist/index.html','app/monitor/cli.py','app/uv.lock','app/tests/test_judge_recovery.py','LICENSE','bin/agent-monitor.mjs'])assert.ok(paths.includes(file),file);
  assert.ok(!paths.some(path=>/(^|\/)(logs|results|real|node_modules|\.git|\.superpowers)(\/|$)/.test(path)));
  assert.ok(!paths.some(path=>path.includes('screenshots/')));
  const tarball=join(out,report.filename);
  const installed=spawnSync('npm',['install','--ignore-scripts','--no-audit','--no-fund','--prefix',join(temp,'consumer'),tarball],{encoding:'utf8'});
  assert.equal(installed.status,0,installed.stderr);
  const cli=join(temp,'consumer/node_modules/@xienanzheng/agent-monitor/bin/agent-monitor.mjs');
  const dest=join(temp,'download');
  const initialized=spawnSync(process.execPath,[cli,'init',dest],{encoding:'utf8'});
  assert.equal(initialized.status,0,initialized.stderr);
  assert.ok(existsSync(join(dest,'dashboard/dist/index.html')));
  assert.match(readFileSync(join(dest,'LICENSE'),'utf8'),/MIT License/);
  assert.ok(existsSync(join(dest,'docs/architecture.md')));
  assert.ok(existsSync(join(dest,'.github/workflows/ci.yml')));
  assert.equal(existsSync(join(dest,'logs')),false);
  assert.equal(readFileSync(join(dest,'.gitignore'),'utf8'),readFileSync(join(root,'.gitignore'),'utf8'));
  assert.ok(existsSync(join(out,'agent-monitor-0.1.0-source.zip')));
  for(const line of readFileSync(join(out,'SHA256SUMS'),'utf8').trim().split('\n')){
    const [hash,file]=line.split('  ');
    assert.equal(createHash('sha256').update(readFileSync(join(out,file))).digest('hex'),hash);
  }
  // GitHub npx packs the source workspace, rather than the separate scoped publisher.
  const source=join(out,'agent-monitor');
  const packedSource=spawnSync('npm',['pack','--ignore-scripts','--json','--pack-destination',out],{cwd:source,encoding:'utf8'});
  assert.equal(packedSource.status,0,packedSource.stderr);
  const sourcePackage=JSON.parse(packedSource.stdout)[0];
  assert.ok(sourcePackage.files.some(file=>file.path==='dashboard/dist/index.html'));
  const fromSource=join(temp,'source-download');
  const exec=spawnSync('npm',['exec','--yes','--package',join(out,sourcePackage.filename),'--','agent-monitor','init',fromSource],{encoding:'utf8'});
  assert.equal(exec.status,0,exec.stderr);
  assert.ok(existsSync(join(fromSource,'dashboard/dist/index.html')));
  assert.ok(existsSync(join(fromSource,'.github/workflows/ci.yml')));
});

test('npm start shuts down only its own daemon and dashboard on interruption',async t=>{
  const temp=mkdtempSync(join(tmpdir(),'agent-monitor-supervise-'));
  t.after(()=>rmSync(temp,{recursive:true,force:true}));
  const calls=join(temp,'calls');
  writeFileSync(join(temp,'uv'),`#!${process.execPath}\nconst fs=require('node:fs');\nfs.appendFileSync(process.env.CAPTURE,JSON.stringify({kind:'start',pid:process.pid,args:process.argv.slice(2)})+'\\n');\nprocess.on('SIGINT',()=>{fs.appendFileSync(process.env.CAPTURE,JSON.stringify({kind:'stop',pid:process.pid})+'\\n');process.exit(0);});\nsetInterval(()=>{},1000);\n`,{mode:0o755});
  const child=spawn(process.execPath,[join(root,'bin/start.mjs')],{env:{...process.env,PATH:temp,CAPTURE:calls},stdio:'pipe'});
  let stderr='';child.stderr.on('data',chunk=>stderr+=chunk);
  t.after(()=>{if(child.exitCode===null)child.kill('SIGKILL');});
  const deadline=Date.now()+5000;
  while((!existsSync(calls) || readFileSync(calls,'utf8').trim().split('\n').length<2) && Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,25));
  assert.ok(existsSync(calls),stderr);
  const started=readFileSync(calls,'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(started.length,2,stderr);
  assert.deepEqual(started.map(row=>row.args.slice(4)).sort(),[['daemon'],['serve','--port','8765']].sort());
  const exited=once(child,'exit');child.kill('SIGINT');
  const [code]=await exited;
  assert.equal(code,0,stderr);
  const rows=readFileSync(calls,'utf8').trim().split('\n').map(JSON.parse);
  assert.deepEqual(rows.filter(row=>row.kind==='stop').map(row=>row.pid).sort(),started.map(row=>row.pid).sort());
});

test('npm start reports missing uv without invalid process-group signals',()=>{
  const child=spawnSync(process.execPath,[join(root,'bin/start.mjs')],{encoding:'utf8',env:{...process.env,PATH:'/nonexistent-agent-monitor-path'}});
  assert.equal(child.status,1);
  assert.match(child.stderr,/Install uv/);
  assert.doesNotMatch(child.stderr,/NaN|out of range|ERR_OUT_OF_RANGE/);
});

test('supervisor stays alive to terminate descendants after uv leaders exit',async t=>{
  const temp=mkdtempSync(join(tmpdir(),'agent-monitor-descendant-'));
  t.after(()=>rmSync(temp,{recursive:true,force:true}));
  const calls=join(temp,'calls');
  const descendant=join(temp,'worker.cjs');
  writeFileSync(descendant,`const fs=require('node:fs');fs.appendFileSync(process.env.CAPTURE,process.pid+'\\n');process.on('SIGINT',()=>{});setInterval(()=>{},1000);`);
  writeFileSync(join(temp,'uv'),`#!${process.execPath}\nconst {spawn}=require('node:child_process');spawn(process.execPath,[process.env.WORKER],{stdio:'ignore'});process.on('SIGINT',()=>process.exit(0));setInterval(()=>{},1000);\n`,{mode:0o755});
  const child=spawn(process.execPath,[join(root,'bin/start.mjs')],{env:{...process.env,PATH:temp,CAPTURE:calls,WORKER:descendant},stdio:'pipe'});
  t.after(()=>{if(child.exitCode===null)child.kill('SIGKILL');if(existsSync(calls))for(const pid of readFileSync(calls,'utf8').trim().split('\n').map(Number))try{process.kill(pid,'SIGKILL');}catch{}});
  const deadline=Date.now()+5000;
  while((!existsSync(calls) || readFileSync(calls,'utf8').trim().split('\n').length<2) && Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,25));
  assert.ok(existsSync(calls));
  const workers=readFileSync(calls,'utf8').trim().split('\n').map(Number);
  assert.equal(workers.length,2);
  const exited=once(child,'exit');child.kill('SIGINT');
  const [code]=await exited;
  assert.equal(code,0);
  for(const pid of workers)assert.throws(()=>process.kill(pid,0),{code:'ESRCH'});
});
