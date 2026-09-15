import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const finalSource=readFileSync(new URL('../aqua-round8-mic-edit-only.js',import.meta.url),'utf8');
function makeState(api){
 const document={querySelectorAll:()=>[],addEventListener(){},hidden:false};
 const state={api,baleTab:'new',token:false,toast(){}};
 const window={app:()=>state,addEventListener(){}};
 vm.runInNewContext(finalSource,{window,document,navigator:{},setInterval(){},setTimeout,clearTimeout,Promise});
 return window.app();
}
test('a late completed response cannot replace the selected cancelled tab',async()=>{
 const resolvers=[];
 const s=makeState(()=>new Promise(resolve=>resolvers.push(resolve)));
 const a=s.loadBaleJobs('completed'),b=s.loadBaleJobs('cancelled');
 resolvers[1]({items:[{id:'cancelled'}],counts:{new:2,completed:1,cancelled:3}});await b;
 resolvers[0]({items:[{id:'completed'}],counts:{new:4,completed:1,cancelled:1}});await a;
 assert.equal(s.baleJobs[0].id,'cancelled');assert.equal(s.baleCounts.new,2);
});
test('refresh and counters use one in-flight snapshot',async()=>{
 let calls=0,resolve;
 const s=makeState(()=>{calls++;return new Promise(r=>resolve=r)});
 const a=s.loadBaleJobs('new'),b=s.loadBaleCounts();assert.equal(calls,1);
 resolve({items:[{id:'review',status:'review'}],counts:{new:1}});await Promise.all([a,b]);
 assert.equal(s.baleJobs[0].status,'review');assert.equal(s.baleCounts.new,1);
});
test('expense submission preserves Persian and Arabic amounts',async()=>{
 const source=readFileSync(new URL('../ui-v3-base.js',import.meta.url),'utf8');
 const context=vm.createContext({window:{},localStorage:{getItem:()=>null},navigator:{onLine:true},alert(){},document:{}});
 vm.runInContext(source,context);
 const s=vm.runInContext('app()',context);let submitted;
 s.api=async(path,opts)=>{submitted=JSON.parse(opts.body);return{id:'test'}};s.refreshAll=async()=>{};
 for(const amount of ['۱۲۳٬۴۵۶','١٢٣٬٤٥٦']){
 s.expenseForm={category:'fuel',title:'آزمایش',amount};await s.createExpense();assert.equal(submitted.amount,123456);
 }
});
