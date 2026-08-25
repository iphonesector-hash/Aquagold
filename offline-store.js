/* AquaGold offline cache + ordered mutation queue (IndexedDB, no external dependency). */
(()=>{
const DB_NAME='aquagold-offline-v1',DB_VERSION=1;
function open(){return new Promise((resolve,reject)=>{const r=indexedDB.open(DB_NAME,DB_VERSION);r.onupgradeneeded=()=>{const db=r.result;if(!db.objectStoreNames.contains('cache'))db.createObjectStore('cache',{keyPath:'key'});if(!db.objectStoreNames.contains('queue')){const q=db.createObjectStore('queue',{keyPath:'id'});q.createIndex('created_at','created_at')}};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)})}
async function tx(store,mode,run){const db=await open();return new Promise((resolve,reject)=>{const t=db.transaction(store,mode),s=t.objectStore(store);let result;try{result=run(s)}catch(e){db.close();reject(e);return}t.oncomplete=()=>{db.close();resolve(result)};t.onerror=()=>{db.close();reject(t.error)};t.onabort=()=>{db.close();reject(t.error)}})}
function requestResult(req){return new Promise((resolve,reject)=>{req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error)})}
async function cachePut(key,value){return tx('cache','readwrite',s=>s.put({key,value,updated_at:Date.now()}))}
async function cacheGet(key){const db=await open();try{return await requestResult(db.transaction('cache').objectStore('cache').get(key)).then(x=>x?.value)}finally{db.close()}}
async function enqueue(entry){const item={...entry,id:entry.id||crypto.randomUUID(),created_at:entry.created_at||Date.now(),attempts:0};await tx('queue','readwrite',s=>s.put(item));return item}
async function list(){const db=await open();try{return (await requestResult(db.transaction('queue').objectStore('queue').index('created_at').getAll())).sort((a,b)=>a.created_at-b.created_at)}finally{db.close()}}
async function remove(id){return tx('queue','readwrite',s=>s.delete(id))}
async function count(){const db=await open();try{return await requestResult(db.transaction('queue').objectStore('queue').count())}finally{db.close()}}
async function clear(){const db=await open();return new Promise((resolve,reject)=>{const t=db.transaction(['cache','queue'],'readwrite');t.objectStore('cache').clear();t.objectStore('queue').clear();t.oncomplete=()=>{db.close();resolve()};t.onerror=()=>{db.close();reject(t.error)}})}
async function sync(send){const items=await list(),result={sent:0,failed:0,remaining:items.length};for(const item of items){try{await send(item.path,{method:item.method,body:item.body,headers:{...(item.headers||{}),'Idempotency-Key':item.id},offlineReplay:true});await remove(item.id);result.sent++}catch(e){result.failed++;if(!e?.status||e.status>=500)break;item.attempts=(item.attempts||0)+1;item.last_error=e.message;await tx('queue','readwrite',s=>s.put(item));break}}result.remaining=await count();return result}
window.AquaOffline={cachePut,cacheGet,enqueue,list,remove,count,clear,sync};
})();
