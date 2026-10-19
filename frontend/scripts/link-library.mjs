import {spawnSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {resolve,join} from 'node:path';
const root=process.argv[2]||process.env.HEROUI_LOCAL_ROOT;
if(!root||!existsSync(join(root,'packages/ui-pro/dist/data-grid.js'))){
  console.error('请设置 HEROUI_LOCAL_ROOT，或运行 npm run link:library -- <HeroUI共享库目录>。共享库需要已构建 Data Grid 和 Action Bar。');process.exit(1);
}
if(!process.env.npm_execpath){console.error('请通过 npm run link:library 调用。');process.exit(1)}
const result=spawnSync(process.execPath,[process.env.npm_execpath,'install',resolve(root,'packages/ui-pro'),'--no-save','--package-lock=false','--install-links=false','--ignore-scripts','--no-audit','--no-fund'],{stdio:'inherit'});
process.exit(result.status??1);
