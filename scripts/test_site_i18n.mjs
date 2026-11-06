import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const publicRoot=process.argv[2]?path.resolve(process.argv[2]):path.join(root,'public');
const read=name=>fs.readFileSync(path.join(publicRoot,name),'utf8');
const scripts=['assets/js/i18n-catalog.js','assets/js/i18n.js','assets/js/i18n-redirect.js','assets/js/script.js','observabilidade/app.js'];
for(const name of scripts)new vm.Script(read(name),{filename:name});
const catalogContext={window:{}};
vm.runInNewContext(read('assets/js/i18n-catalog.js'),catalogContext);
const catalog=catalogContext.window.HARA_I18N_CATALOG;
assert.deepEqual(Object.keys(catalog).sort(),['en','pt']);
const placeholders=value=>[...String(value).matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)].map(m=>m[1]).sort();
for(const [key,value] of Object.entries(catalog.en)){
  assert.equal(typeof value,'string',key);
  assert.ok(value.trim(),key);
  assert.deepEqual(placeholders(catalog.pt[key]??key),placeholders(value),key);
}

function htmlFiles(directory){
  return fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>{
    const full=path.join(directory,entry.name);
    return entry.isDirectory()?htmlFiles(full):(entry.name.endsWith('.html')?[full]:[]);
  });
}
const pages=htmlFiles(publicRoot);
assert.ok(pages.length>=17,'PAGE_COVERAGE');
let headerPages=0,annotationCount=0;
for(const file of pages){
  const html=fs.readFileSync(file,'utf8');
  for(const match of html.matchAll(/data-i18n(?:-(?:title|aria-label|aria-description|placeholder|alt|content|page-title))?="([^"]+)"/g)){
    const key=match[1];
    assert.ok(Object.hasOwn(catalog.pt,key)&&Object.hasOwn(catalog.en,key),`${file}:${key}`);
    annotationCount++;
  }
  assert.match(html,/data-i18n-page-title="[^"]+"/);
  assert.match(html,/\/assets\/js\/i18n-catalog\.js\?v=/);
  assert.match(html,/\/assets\/js\/i18n\.js\?v=/);
  if(html.includes('class="neon-toggle"')){
    headerPages++;
    assert.match(html,/<button class="neon-toggle"[\s\S]*?<\/button>\s*<div class="language-switch"/,'LANGUAGE_NEXT_TO_NEON');
    assert.equal((html.match(/data-set-language="pt"/g)||[]).length,1);
    assert.equal((html.match(/data-set-language="en"/g)||[]).length,1);
    assert.match(html,/<div class="language-switch" role="group"/);
    assert.match(html,/<span class="brand-word">HARA <b>Labs<\/b><\/span>/,'CANONICAL_WORDMARK');
  }else{
    assert.ok(file.endsWith(path.join('privacy','index.html'))||file.endsWith(path.join('terms','index.html')));
    assert.match(html,/<noscript><meta http-equiv="refresh"/,'NO_JS_REDIRECT_FALLBACK');
    assert.match(html,/i18n-redirect\.js\?v=[^"]+" data-redirect-to="\/legal\/(?:privacidade|termos)\/"/);
  }
}
assert.equal(headerPages,pages.length-2);
assert.equal(read('404.html'),read('404/index.html'),'404_SOURCE_PARITY');
console.log(`HARA_SITE_I18N_CATALOG=PASS:${Object.keys(catalog.en).length}; PAGES=${pages.length}; ANNOTATIONS=${annotationCount}`);

function runtime({url='https://haralabs.com.br/',saved=null,browserLanguage='pt-BR',blockedStorage=false,messages=catalog}={}){
  const location=new URL(url);
  const storage=new Map(saved?[['hara-language',saved]]:[]);
  const links=[
    '/empresa/#sobre',
    'https://www.haralabs.com.br/contato/',
    'https://commander.haralabs.com.br/?source=site#devices',
    'https://commander.haralabs.com.br/api/mcp?profile=simple',
    'https://auth.haralabs.com.br/',
    'mailto:contato@haralabs.com.br?subject=HARA',
    'https://www.linkedin.com/company/hara-labs/',
    '#conteudo',
  ].map(href=>({href,getAttribute(){return this.href;},setAttribute(name,value){assert.equal(name,'href');this.href=value;}}));
  const document={
    documentElement:{dataset:{},lang:'pt-BR',getAttribute(){return null;}},
    readyState:'complete',
    querySelectorAll(selector){return selector==='a[href]'?links:[];},
    querySelector(){return null;},
    getElementById(){return null;},
    addEventListener(){},
  };
  const events=[];
  const window={HARA_I18N_CATALOG:messages,dispatchEvent(event){events.push(event.type);}};
  const history={state:{preserve:true},replaceState(state,_title,url){assert.equal(state,this.state);location.href=new URL(url,location.href).href;}};
  const context={window,document,location,history,navigator:{language:browserLanguage,languages:[browserLanguage]},URL,
    CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},
    localStorage:{getItem(key){if(blockedStorage)throw Error('blocked');return storage.get(key)||null;},setItem(key,value){if(blockedStorage)throw Error('blocked');storage.set(key,value);}},
    fetch(){throw Error('LANGUAGE_CHANGE_MUST_NOT_FETCH');},
  };
  vm.runInNewContext(read('assets/js/i18n.js'),context);
  return {api:window.HARA_I18N,document,location,links,storage,events};
}

let sample=runtime({url:'https://haralabs.com.br/?lang=en&source=review#conteudo',saved:'pt'});
assert.equal(sample.api.getLanguage(),'en','QUERY_PRECEDENCE');
assert.equal(sample.api.getLocale(),'en-US');
assert.equal(sample.storage.get('hara-language'),'en');
assert.equal(sample.links[0].href,'/empresa/?lang=en#sobre');
assert.equal(sample.links[1].href,'https://www.haralabs.com.br/contato/?lang=en');
assert.equal(sample.links[2].href,'https://commander.haralabs.com.br/?source=site&lang=en#devices');
assert.equal(sample.links[3].href,'https://commander.haralabs.com.br/api/mcp?profile=simple');
assert.equal(sample.links[4].href,'https://auth.haralabs.com.br/');
assert.equal(sample.links[5].href,'mailto:contato@haralabs.com.br?subject=HARA');
assert.equal(sample.links[6].href,'https://www.linkedin.com/company/hara-labs/');
assert.equal(sample.links[7].href,'#conteudo');
assert.equal(sample.api.setLanguage('pt'),true);
assert.equal(sample.document.documentElement.lang,'pt-BR');
assert.equal(sample.location.searchParams.get('source'),'review');
assert.equal(sample.location.hash,'#conteudo');
assert.equal(sample.api.setLanguage('unknown'),false);
assert.equal(sample.api.getLanguage(),'pt');
assert.deepEqual(sample.events,['hara:languagechange']);
assert.equal(runtime({saved:'en'}).api.getLanguage(),'en');
assert.equal(runtime({browserLanguage:'en-GB'}).api.getLanguage(),'en');
assert.equal(runtime({browserLanguage:'es-ES'}).api.getLanguage(),'pt');
sample=runtime({blockedStorage:true});
assert.equal(sample.api.setLanguage('en'),true);
assert.equal(sample.api.getLanguage(),'en');
sample=runtime({url:'https://haralabs.com.br/?lang=en',messages:{pt:{},en:{}}});
assert.equal(sample.api.getLanguage(),'pt');
assert.equal(sample.api.setLanguage('en'),false);
console.log('HARA_SITE_I18N_RUNTIME=PASS; LANGUAGE_LINKS=PASS; OPERATIONAL_URLS_PRESERVED=PASS; STORAGE_FALLBACK=PASS');
