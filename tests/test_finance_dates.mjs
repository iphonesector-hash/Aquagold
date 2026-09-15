import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const context={window:{},document:{readyState:'loading',addEventListener(){}},Intl,Date,Map};
vm.runInNewContext(fs.readFileSync(new URL('../aqua-finance.js',import.meta.url),'utf8'),context);
const f=context.window.AquaFinanceMath;
test('Persian leap day, Nowruz and invalid dates',()=>{
 assert.equal(f.gregorian(1403,12,30),'2025-03-20');
 assert.equal(f.gregorian(1404,1,1),'2025-03-21');
 assert.equal(f.gregorian(1405,6,16),'2026-09-07');
 assert.throws(()=>f.gregorian(1404,12,30));
});
test('aggregation uses Persian months and preserves negative profit',()=>{
 const rows=f.groupedDays([{date:'2025-03-20',received:20,net_profit:-10},{date:'2025-03-21',received:30,net_profit:15}]);
 assert.equal(rows.length,2);assert.equal(rows[0].key,'1403/12');assert.equal(rows[1].key,'1404/01');assert.equal(rows[0].net_profit,-10);
});
test('Tehran day is independent of viewer timezone',()=>assert.equal(f.isoDay('2026-09-07T21:00:00Z'),'2026-09-08'));
