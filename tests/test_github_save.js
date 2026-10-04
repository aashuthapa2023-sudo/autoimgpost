const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync('index.html', 'utf8');
const store = new Map();
const context = {GITHUB_REPO: 'owner/repo', cachedConfig: {}, cachedChannels: [], configSha: null, localStorage: {getItem:k=>store.get(k)||null, setItem:(k,v)=>store.set(k,v), removeItem:k=>store.delete(k)}, updateHeaderStatus:()=>{}, renderChannelsHub:()=>{}, isLocalEnv:()=>false, getGitHubToken:()=> 'github_pat_test', utf8ToBase64:s=>Buffer.from(s).toString('base64'), showToast:()=>{}, calls:[]};
context.fetch = async (url, options) => {
 context.calls.push({url,options});
 if (options.method === 'PUT') return {ok:true,json:async()=>({content:{sha:'new'}})};
 return {ok:true,json:async()=>({sha:'current'})};
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('    let configSaveQueue'), source.indexOf('    // --- CONCURRENT')), context);
(async()=> {
 const config={channels:[{channel_id:'new-page',source_pages:['https://www.facebook.com/new']} ]};
 assert.equal(await context.saveConfigUniversal(config),true);
 const body=JSON.parse(context.calls[1].options.body);
 assert.equal(JSON.parse(Buffer.from(body.content,'base64').toString()).channels[0].channel_id,'new-page');
 assert.equal(body.branch,'main');
 assert.equal(store.has('autoimgpost_pending_config'),false);
 context.fetch=async()=>({ok:false,status:403,json:async()=>({message:'Permission denied'})});
 assert.equal(await context.saveConfigUniversal(config),false);
 assert.equal(JSON.parse(store.get('autoimgpost_pending_config')).channels[0].channel_id,'new-page');
 const prompt=source.slice(source.indexOf('    function setGitHubTokenPrompt'),source.indexOf('    function isLocalEnv'));
 assert(!prompt.includes('loadUnifiedConfig'));
 console.log('GitHub save, permission failure, and pending-page preservation passed');
})().catch(e=>{console.error(e);process.exitCode=1});
