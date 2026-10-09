#!/usr/bin/env node
import {spawn} from 'node:child_process';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
if(process.platform==='win32') {
  console.error('The monitor uses Unix sockets. Run it in WSL on Windows.');process.exit(1);
}
const groups=new Set();
let stopping=false;
function signalGroup(pid,name) {
  try {process.kill(-pid,name);return true;} catch(error) {
    if(error.code==='ESRCH'){groups.delete(pid);return false;}
    if(error.code!=='EPERM')console.error(error.message);
    return true;
  }
}
function stop(code=0) {
  if(stopping)return;
  stopping=true;process.exitCode=code;
  for(const pid of groups)signalGroup(pid,'SIGINT');
  const deadline=setTimeout(()=>{for(const pid of groups)signalGroup(pid,'SIGTERM');},6000);
  const finalDeadline=setTimeout(()=>{
    for(const pid of groups)signalGroup(pid,'SIGKILL');
    clearInterval(check); // Do not wait indefinitely for orphan zombies to be reaped by init.
  },9000);
  // Keep supervision alive when a launcher exits before its owned descendants.
  const check=setInterval(()=>{
    for(const pid of groups)signalGroup(pid,0);
    if(groups.size===0){clearInterval(check);clearTimeout(deadline);clearTimeout(finalDeadline);}
  },50);
}
for(const command of [['daemon'],['serve','--port','8765']]) {
  const child=spawn('uv',['run','--extra','dashboard','monitor',...command],{cwd:root,stdio:'inherit',detached:true,shell:false});
  if(child.pid)groups.add(child.pid);
  child.on('error',error=>{console.error(error.code==='ENOENT' ? 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' : error.message);stop(1);});
  child.on('exit',(code,reason)=>{if(!stopping)stop(code || (reason ? 1 : 0));});
}
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());
