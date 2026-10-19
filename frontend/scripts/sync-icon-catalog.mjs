import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {icons}=require('@gravity-ui/icons/metadata.json');
const names=icons.map(icon=>icon.componentName).sort();
writeFileSync(new URL('../../runtime/icon_catalog.json',import.meta.url),JSON.stringify(names,null,2)+'\n');
console.log(`Synced ${names.length} Gravity UI icon identifiers.`);
