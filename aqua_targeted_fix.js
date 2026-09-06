/* Minimal branch-only edit state/actions. Reuses existing AquaGold classes and API helper. */
(()=>{
  const previous=window.app;
  if(typeof previous!=='function')return;
  window.app=function(){
    const state=previous();
    Object.assign(state,{
      serviceEditOpen:false,
      serviceEditBusy:false,
      serviceEdit:{id:null,service_type:'',description:'',invoice_amount:'',received_amount:'',status:'completed'},
      expenseEditOpen:false,
      expenseEditBusy:false,
      expenseEdit:{id:null,category:'other',title:'',amount:'',notes:''},
    });

    state.openServiceEdit=function(job){
      this.serviceEdit={
        id:job?.id||null,
        service_type:job?.service_type||'',
        description:job?.description||'',
        invoice_amount:Number(job?.invoice_amount||0),
        received_amount:Number(job?.received_amount||0),
        status:job?.status||'completed',
      };
      this.serviceEditOpen=true;
    };

    state.saveServiceEdit=async function(){
      if(!this.serviceEdit?.id||this.serviceEditBusy)return;
      this.serviceEditBusy=true;
      try{
        const payload={
          service_type:this.serviceEdit.service_type||'',
          description:this.serviceEdit.description||'',
          invoice_amount:this.num(this.serviceEdit.invoice_amount),
          received_amount:this.num(this.serviceEdit.received_amount),
          status:this.serviceEdit.status||'completed',
        };
        const result=await this.api('/jobs/'+this.serviceEdit.id,{method:'PATCH',body:JSON.stringify(payload)});
        if(result?.queued){
          const id=String(this.serviceEdit.id);
          this.jobs=this.jobs.map(j=>String(j.id)===id?{...j,...payload,offline_pending:true}:j);
          this.serviceEditOpen=false;
          alert('ویرایش سرویس روی گوشی ذخیره شد و بعد از اتصال همگام می‌شود');
          return;
        }
        await this.refreshAll();
        if(this.page==='customer-detail'&&this.selectedCustomer){
          try{const d=await this.api(`/customers/${this.selectedCustomer.id}/jobs?per_page=100`);this.selectedCustomerJobsRemote=d.items||[]}catch{}
        }
        this.serviceEditOpen=false;
        alert('سرویس و مبلغ‌ها ویرایش شد');
      }catch(error){alert(error?.message||'ویرایش سرویس انجام نشد')}
      finally{this.serviceEditBusy=false}
    };

    state.openExpenseEdit=function(expense){
      this.expenseEdit={
        id:expense?.id||null,
        category:expense?.category||'other',
        title:expense?.title||'',
        amount:Number(expense?.amount||0),
        notes:expense?.notes||'',
      };
      this.expenseEditOpen=true;
    };

    state.saveExpenseEdit=async function(){
      if(!this.expenseEdit?.id||this.expenseEditBusy)return;
      if(!String(this.expenseEdit.title||'').trim())return alert('عنوان هزینه لازم است');
      this.expenseEditBusy=true;
      try{
        const payload={
          category:this.expenseEdit.category||'other',
          title:String(this.expenseEdit.title||'').trim(),
          amount:this.num(this.expenseEdit.amount),
          notes:this.expenseEdit.notes||'',
        };
        const result=await this.api('/expenses/'+this.expenseEdit.id,{method:'PATCH',body:JSON.stringify(payload)});
        if(result?.queued){
          const id=String(this.expenseEdit.id);
          this.expenses=this.expenses.map(e=>String(e.id)===id?{...e,...payload,offline_pending:true}:e);
          this.expenseEditOpen=false;
          alert('ویرایش هزینه روی گوشی ذخیره شد و بعد از اتصال همگام می‌شود');
          return;
        }
        await this.refreshAll();
        this.expenseEditOpen=false;
        alert('هزینه ویرایش شد');
      }catch(error){alert(error?.message||'ویرایش هزینه انجام نشد')}
      finally{this.expenseEditBusy=false}
    };

    return state;
  };
})();
