#!/usr/bin/env node
import {existsSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {copyProject} from '../lib/distribution.mjs';

const packageRoot=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const bundled=existsSync(join(packageRoot,'app/monitor/cli.py')) ? join(packageRoot,'app') : packageRoot;
const args=process.argv.slice(2);
try {
  if(args[0]==='init') {
    if(args.length>2)throw new Error('Usage: agent-monitor init [directory]');
    const dest=resolve(args[1] || 'agent-monitor');
    if(existsSync(dest))throw new Error(`Directory already exists: ${dest}. Choose a new directory.`);
    copyProject(bundled,dest);
    console.log(`Downloaded Agent Monitor to ${dest}\nNext: cd ${JSON.stringify(dest)}, npm run setup, then npm start.\nHooks are installed only when you run agent-monitor install-hooks.`);
  } else if(args.length===0 || args[0]==='help') {
    console.log('Agent Monitor\n\nagent-monitor init [directory]  Download the complete project\nInside the project: npm run setup; npm start\nagent-monitor <command>         Run the Python monitor CLI from that project\n\nRequires Node 22+, uv/Python 3.11+, and local Ollama. Hook installation is opt-in.');
  } else {
    const cwd=process.cwd();
    if(!existsSync(join(cwd,'monitor/cli.py')) || !existsSync(join(cwd,'pyproject.toml')))
      throw new Error('Run this command inside an initialized Agent Monitor project. Use agent-monitor init first.');
    const command=args[0]==='setup' ? ['sync','--extra','dashboard'] : ['run','--extra','dashboard','monitor',...args];
    const result=spawnSync('uv',command,{cwd,stdio:'inherit',shell:false});
    if(result.error?.code==='ENOENT')throw new Error('Install uv first: https://docs.astral.sh/uv/getting-started/installation/');
    if(result.error)throw result.error;
    process.exitCode=result.status ?? 1;
    if(args[0]==='setup' && result.status===0)
      console.log('Python environment ready. Start local Ollama and install qwen3:4b and qwen3:8b, then run npm start. Install agent hooks explicitly with npm run monitor -- install-hooks --agent claude.');
  }
} catch(error) {console.error(error.message);process.exitCode=1;}
