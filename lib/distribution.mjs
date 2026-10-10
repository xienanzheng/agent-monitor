import {cpSync,existsSync,lstatSync,mkdirSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {join,relative} from 'node:path';

// Release an explicit source subset; local traffic and historic screenshots are never copied.
export const entries=['monitor','rules','prompts','data/labelled','dashboard/src','dashboard/dist',
  'dashboard/e2e/prepare_logs.py','dashboard/e2e/smoke.spec.ts','dashboard/package.json',
  'dashboard/package-lock.json','dashboard/index.html','dashboard/tsconfig.json',
  'dashboard/vite.config.ts','dashboard/playwright.config.ts','tests','scripts',
  'bin','lib','pyproject.toml','uv.lock','.gitignore','LICENSE','CONTRIBUTING.md','SECURITY.md'];
const excluded=new Set(['.git','.venv','node_modules','__pycache__','.pytest_cache','.superpowers',
  'logs','results','real','.tmp-logs','.tmp-home','test-results','playwright-report','.DS_Store']);

export function copyProject(source,dest) {
  for(const file of ['monitor/cli.py','rules/rules.json','prompts/triage.txt','dashboard/dist/index.html','pyproject.toml','uv.lock']) {
    if(!existsSync(join(source,file)))throw new Error(`Release asset missing: ${file}. Build the dashboard first.`);
  }
  mkdirSync(dest,{recursive:false}); // Never overwrite an existing project, even an empty one.
  try {
  const filter=path=>!relative(source,path).split(/[\\/]/).some(part=>excluded.has(part)) &&
    !lstatSync(path).isSymbolicLink() && !path.endsWith('.pyc');
  for(const file of entries) {
    const from=join(source,file);
    if(existsSync(from))cpSync(from,join(dest,file),{recursive:true,filter});
  }
  const ignore=readFileSync(existsSync(join(source,'.gitignore'))
    ? join(source,'.gitignore') : join(source,'lib/project-ignore.txt'),'utf8');
  // npm strips .gitignore from tarballs; preserve a normal-named template and restore it.
  writeFileSync(join(dest,'lib/project-ignore.txt'),ignore);
  writeFileSync(join(dest,'.gitignore'),ignore);
  const publicReadme=join(source,'release/public/README.md');
  const readme=existsSync(publicReadme) ? publicReadme : join(source,'README.md');
  cpSync(readme,join(dest,'README.md'));
  const publicDocs=join(source,'release/public/docs');
  const docs=existsSync(publicDocs) ? publicDocs :
    (existsSync(join(source,'lib/project-ignore.txt')) ? join(source,'docs') : null);
  if(docs && existsSync(docs))cpSync(docs,join(dest,'docs'),{recursive:true});
  const publicWorkflows=join(source,'release/public/.github');
  const workflows=existsSync(publicWorkflows) ? publicWorkflows :
    (existsSync(join(source,'lib/project-ignore.txt')) ? join(source,'.github') : null);
  if(workflows && existsSync(workflows))cpSync(workflows,join(dest,'.github'),{recursive:true});
  const metadata=JSON.parse(readFileSync(join(source,'package.json'),'utf8'));
  writeFileSync(join(dest,'package.json'),JSON.stringify({...metadata,name:'agent-monitor-workspace',private:true,
    files:[...entries,'README.md','docs','.github']},null,2)+'\n');
  } catch(error) {
    // Only this function owns the directory after successful exclusive creation.
    rmSync(dest,{recursive:true,force:true});
    throw error;
  }
}
