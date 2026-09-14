/* Independent Persian-calendar year/month/day controls for expense editing. */
(()=>{
  const previous=window.app;if(typeof previous!=='function')return;
  const persianParts=value=>{const parts=new Intl.DateTimeFormat('en-US-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date(value));const out={};for(const p of parts)if(['year','month','day','hour','minute'].includes(p.type))out[p.type]=Number(p.value);return out};
  const gFromJ=(jy,jm,jd)=>{const start=Date.UTC(Number(jy)+621,2,1,8,0,0);for(let i=0;i<400;i++){const d=new Date(start+i*86400000),p=persianParts(d);if(p.year===Number(jy)&&p.month===Number(jm)&&p.day===Number(jd))return{year:d.getUTCFullYear(),month:d.getUTCMonth()+1,day:d.getUTCDate()}}return null};
  const pad=n=>String(Number(n)||0).padStart(2,'0');
  const monthNames=['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
  window.app=function(){
    const state=previous();
    state.expenseJalali={year:'',month:'',day:'',hour:'',minute:''};
    const oldOpen=state.openExpenseEdit?.bind(state);
    const oldSave=state.saveExpenseEdit?.bind(state);

    state.daysInJalaliMonth=function(year,month){if(Number(month)<=6)return 31;if(Number(month)<=11)return 30;return gFromJ(Number(year),12,30)?30:29};
    state.syncExpenseJalaliToTimestamp=function(){
      const p=this.expenseJalali||{},g=gFromJ(p.year,p.month,p.day);if(!g)return false;
      this.expenseEdit.expense_date=`${g.year}-${pad(g.month)}-${pad(g.day)}T${pad(p.hour)}:${pad(p.minute)}:00+03:30`;return true;
    };

    state.ensureExpenseJalaliPicker=function(){
      const modal=[...document.querySelectorAll('label')].find(el=>el.textContent?.includes('تاریخ و ساعت هزینه'));
      if(!modal)return;
      modal.style.display='none';
      let host=document.getElementById('expenseJalaliPicker');
      if(!host){host=document.createElement('div');host.id='expenseJalaliPicker';host.className='glass rounded-2xl p-3';modal.insertAdjacentElement('afterend',host)}
      host.replaceChildren();
      const title=document.createElement('div');title.className='text-sm muted mb-2';title.textContent='تاریخ شمسی هزینه';host.appendChild(title);
      const grid=document.createElement('div');grid.className='grid grid-cols-3 gap-2';host.appendChild(grid);
      const make=(label,values,current,onchange)=>{const wrap=document.createElement('label');wrap.className='text-xs muted';wrap.append(document.createTextNode(label));const select=document.createElement('select');select.className='field mt-1 min-h-11';for(const item of values){const option=document.createElement('option');option.value=String(item.value);option.textContent=item.label;option.selected=String(item.value)===String(current);select.appendChild(option)}select.addEventListener('change',()=>onchange(select.value));wrap.appendChild(select);grid.appendChild(wrap);return select};
      const p=this.expenseJalali,years=[];for(let y=Number(p.year)-3;y<=Number(p.year)+3;y++)years.push({value:y,label:Number(y).toLocaleString('fa-IR',{useGrouping:false})});
      make('سال',years,p.year,v=>{p.year=Number(v);const max=this.daysInJalaliMonth(p.year,p.month);if(Number(p.day)>max)p.day=max;this.ensureExpenseJalaliPicker()});
      make('ماه',monthNames.map((name,i)=>({value:i+1,label:name})),p.month,v=>{p.month=Number(v);const max=this.daysInJalaliMonth(p.year,p.month);if(Number(p.day)>max)p.day=max;this.ensureExpenseJalaliPicker()});
      const days=Array.from({length:this.daysInJalaliMonth(p.year,p.month)},(_,i)=>({value:i+1,label:Number(i+1).toLocaleString('fa-IR',{useGrouping:false})}));
      make('روز',days,p.day,v=>{p.day=Number(v);this.syncExpenseJalaliToTimestamp()});
      const time=document.createElement('div');time.className='grid grid-cols-2 gap-2 mt-2';host.appendChild(time);
      const timeSelect=(label,max,current,key)=>{const wrap=document.createElement('label');wrap.className='text-xs muted';wrap.append(document.createTextNode(label));const select=document.createElement('select');select.className='field mt-1 min-h-11';for(let i=0;i<=max;i++){const option=document.createElement('option');option.value=String(i);option.textContent=Number(i).toLocaleString('fa-IR',{minimumIntegerDigits:2,useGrouping:false});option.selected=Number(current)===i;select.appendChild(option)}select.addEventListener('change',()=>{p[key]=Number(select.value);this.syncExpenseJalaliToTimestamp()});wrap.appendChild(select);time.appendChild(wrap)};
      timeSelect('ساعت',23,p.hour,'hour');timeSelect('دقیقه',59,p.minute,'minute');this.syncExpenseJalaliToTimestamp();
    };

    state.openExpenseEdit=function(expense){
      const result=oldOpen?.(expense);const source=expense?.expense_date||new Date().toISOString(),p=persianParts(source);
      this.expenseJalali={year:p.year,month:p.month,day:p.day,hour:p.hour||0,minute:p.minute||0};
      setTimeout(()=>this.ensureExpenseJalaliPicker(),0);return result;
    };
    state.saveExpenseEdit=async function(...args){if(!this.syncExpenseJalaliToTimestamp())return alert('تاریخ شمسی معتبر نیست');return oldSave?.(...args)};
    return state;
  };
})();
