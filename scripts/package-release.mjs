#!/usr/bin/env node
import {existsSync,mkdirSync,readFileSync,writeFileSync,cpSync,rmSync} from 'node:fs';
import {resolve,join,dirname} from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {copyProject} from '../lib/distribution.mjs';

const root=resolve(import.meta.dirname,'..');
const args=process.argv.slice(2);
if(args.length>1)throw new Error('Usage: npm run release:build -- [new output directory]');
const metadata=JSON.parse(readFileSync(join(root,'package.json'),'utf8'));
const output=resolve(args[0] || join(root,'dist',`agent-monitor-${metadata.version}`));
if(existsSync(output))throw new Error(`Release directory already exists: ${output}`);
for(const required of ['LICENSE','CONTRIBUTING.md','SECURITY.md'])if(!existsSync(join(root,required)))throw new Error(`Missing ${required}`);
mkdirSync(dirname(output),{recursive:true});
mkdirSync(output); // Exclusive creation makes cleanup safe if another build races us.
try {
  const source=join(output,'agent-monitor');
  copyProject(root,source);
  const publisher=join(output,'npm');
  mkdirSync(publisher);
  cpSync(source,join(publisher,'app'),{recursive:true});
  for(const item of ['bin','lib','LICENSE','README.md'])cpSync(join(source,item),join(publisher,item),{recursive:true});
  writeFileSync(join(publisher,'app','.npmignore'),''); // Preserve prebuilt assets excluded from source control.
  writeFileSync(join(publisher,'package.json'),JSON.stringify({
    name:metadata.distribution?.name || metadata.name,version:metadata.version,description:metadata.description,
    license:metadata.license,type:'module',engines:metadata.engines,bin:metadata.bin,
    repository:metadata.repository,files:['bin','lib','app','LICENSE','README.md'],
    publishConfig:{access:'public'},
  },null,2)+'\n');
  const pack=spawnSync('npm',['pack','--ignore-scripts','--json','--pack-destination',output],{cwd:publisher,encoding:'utf8',shell:false});
  if(pack.error || pack.status!==0)throw new Error(pack.error?.message || pack.stderr);
  const report=JSON.parse(pack.stdout);
  writeFileSync(join(output,'npm-pack.json'),JSON.stringify(report,null,2)+'\n');
  const archive=join(output,`agent-monitor-${metadata.version}-source.zip`);
  const zip=spawnSync('zip',['-q','-r',archive,'agent-monitor'],{cwd:output,encoding:'utf8',shell:false});
  if(zip.error || zip.status!==0)throw new Error(zip.error?.message || zip.stderr);
  const files=[report[0].filename,`agent-monitor-${metadata.version}-source.zip`];
  writeFileSync(join(output,'SHA256SUMS'),files.map(name=>
    `${createHash('sha256').update(readFileSync(join(output,name))).digest('hex')}  ${name}`
  ).join('\n')+'\n');
  console.log(JSON.stringify({source,archive,npm:join(output,report[0].filename),published:false},null,2));
} catch(error) {
  rmSync(output,{recursive:true,force:true});
  console.error(error.message);process.exitCode=1;
}
