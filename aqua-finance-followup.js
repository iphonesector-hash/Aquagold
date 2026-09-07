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
#${ROOT_ID} #af-time{display:block;width:100%!important;min-width:0!important;max-width:100%!important;inline-size:100%!important;box-sizing:border-box;overflow:hidden}
#${ROOT_ID} .af-card:has(.af-calendar){z-index:420!important}
#${ROOT_ID} .af-datewrap:has(.af-calendar){z-index:430!important}
#${ROOT_ID} .af-calendar{z-index:440!important;max-width:calc(100vw - 32px)}
#${ROOT_ID} [data-fold="settlement-form"].af-open>.af-fold>div{overflow:visible}
#${ROOT_ID} [data-fold="settlement-form"].af-open{z-index:300}
@media(max-width:520px){
  #${ROOT_ID} #af-settlement-form .af-grid{grid-template-columns:1fr}
  #${ROOT_ID} #af-time{font-size:16px}
}
`;
  document.head.appendChild(style);
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
  hideLegacyUnknownUi(root);
  if(!root.__aquaFinanceFollowupObserver){
    const observer=new MutationObserver(()=>{makeSettlementAccordion(root);hideLegacyUnknownUi(root)});
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
