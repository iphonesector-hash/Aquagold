/* Follow-up finance-only mobile fixes requested after iPhone QA. */
(()=>{'use strict';
const STYLE_ID='aqua-finance-followup-style';
const ROOT_ID='aqua-finance';
const arrow='<svg class="af-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
function installStyles(){
  if(document.getElementById(STYLE_ID))return;
  const style=document.createElement('style');
  style.id=STYLE_ID;
  style.textContent=`
#${ROOT_ID} .af-grid>*{min-width:0;max-width:100%}
#${ROOT_ID} #af-settlement-form label{min-width:0;max-width:100%}
#${ROOT_ID} .af-time-wrap{display:block;width:100%;min-width:0;max-width:100%;margin-top:7px;border:1px solid #34516e;border-radius:13px;background:#06172a;overflow:hidden;box-sizing:border-box}
#${ROOT_ID} #af-time{display:block!important;width:100%!important;min-width:0!important;max-width:100%!important;inline-size:100%!important;box-sizing:border-box!important;margin:0!important;border:0!important;border-radius:0!important;background:transparent!important;overflow:hidden!important;-webkit-appearance:none!important;appearance:none!important;direction:ltr!important;text-align:center!important;transform:none!important;position:static!important}
#${ROOT_ID} .af-card:has(.af-calendar){z-index:32!important}
#${ROOT_ID} .af-datewrap:has(.af-calendar){z-index:33!important}
#${ROOT_ID} .af-calendar{z-index:34!important;max-width:calc(100vw - 32px)}
#${ROOT_ID} [data-fold="settlement-form"].af-open>.af-fold>div{overflow:visible}
#${ROOT_ID} [data-fold="settlement-form"].af-open{z-index:20!important;scroll-margin-top:calc(env(safe-area-inset-top,0px) + 96px)}
@media(max-width:520px){
  #${ROOT_ID} #af-settlement-form .af-grid{grid-template-columns:1fr}
  #${ROOT_ID} #af-time{font-size:16px!important}
}
`;
  document.head.appendChild(style);
}
function containTimeField(root){
  const input=root.querySelector('#af-time');
  if(!input||input.parentElement?.classList.contains('af-time-wrap'))return;
  const wrap=document.createElement('span');
  wrap.className='af-time-wrap';
  input.parentNode.insertBefore(wrap,input);
  wrap.appendChild(input);
}
function makeSettlementAccordion(root){
  const form=root.querySelector('#af-settlement-form');
  const card=form?.closest('.af-card');
  const title=card?.querySelector('#af-form-title');
  if(!form||!card||!title||card.dataset.fold==='settlement-form')return;
  card.dataset.fold='settlement-form';
  card.classList.remove('af-pad');
  const toggle=document.createElement('button');
  toggle.type='button';
  toggle.className='af-toggle';
  toggle.dataset.toggle='settlement-form';
  toggle.setAttribute('aria-expanded','false');
  toggle.setAttribute('aria-controls','af-panel-settlement-form');
  const copy=document.createElement('span');
  copy.appendChild(title);
  const small=document.createElement('small');
  small.textContent='مبلغ، تاریخ شمسی، ساعت تهران و توضیحات';
  copy.appendChild(small);
  toggle.appendChild(copy);
  toggle.insertAdjacentHTML('beforeend',arrow);
  const fold=document.createElement('div');
  fold.className='af-fold';
  fold.id='af-panel-settlement-form';
  fold.inert=true;
  const inner=document.createElement('div');
  const pad=document.createElement('div');
  pad.className='af-fold-pad';
  inner.appendChild(pad);
  fold.appendChild(inner);
  pad.appendChild(form);
  card.prepend(fold);
  card.prepend(toggle);
}
function hideLegacyUnknownUi(root){
  root.querySelectorAll('#af-stats .af-stat').forEach(card=>{
    if(card.querySelector('small')?.textContent.trim()==='نامشخص')card.remove();
  });
  const unknown=root.querySelector('#af-payment-filter option[value="unknown"]');
  if(unknown)unknown.hidden=true;
}
function openSettlementForEdit(root){
  const card=root.querySelector('[data-fold="settlement-form"]');
  const toggle=card?.querySelector('[data-toggle="settlement-form"]');
  if(card&&toggle&&!card.classList.contains('af-open'))toggle.click();
}
function enhance(){
  installStyles();
  const root=document.getElementById(ROOT_ID);
  if(!root)return;
  makeSettlementAccordion(root);
  containTimeField(root);
  hideLegacyUnknownUi(root);
  if(!root.__aquaFinanceFollowupObserver){
    const observer=new MutationObserver(()=>{makeSettlementAccordion(root);containTimeField(root);hideLegacyUnknownUi(root)});
    observer.observe(root,{childList:true,subtree:true});
    root.__aquaFinanceFollowupObserver=observer;
  }
}
document.addEventListener('click',event=>{
  const edit=event.target?.closest?.('#aqua-finance [data-edit]');
  if(edit)setTimeout(()=>openSettlementForEdit(document.getElementById(ROOT_ID)),0);
},true);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',enhance,{once:true});else enhance();
setTimeout(enhance,250);
})();
