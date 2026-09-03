"""Scoped UI stability hotfix for the isolated AquaGold test branch.

This module intentionally changes only presentation/runtime helpers:
- exact Persian/Jalali date-time wording with Tehran time and seconds;
- prioritised dashboard shortcuts for Smart Register, Aqua AI and new Bale jobs;
- one coherent aqua/blue visual language for dashboard action cards.
"""
from __future__ import annotations

import re

from flask import Response, request

import app_v3


SCOPED_UI_JS = r"""
(()=>{
 const previous=window.app;if(typeof previous!=='function')return;
 const faDigits=value=>String(value??'').replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[Number(d)]);
 const asDate=value=>{
  if(value instanceof Date)return value;
  if(typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value))return new Date(value+'T12:00:00+03:30');
  return new Date(value);
 };
 const jalaliWords=(value,withTime=false)=>{
  if(value===null||value===undefined||value==='')return'';
  try{
   const date=asDate(value);if(Number.isNaN(date.getTime()))return String(value);
   const options={timeZone:'Asia/Tehran',calendar:'persian',numberingSystem:'latn',weekday:'long',year:'numeric',month:'long',day:'numeric'};
   if(withTime)Object.assign(options,{hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
   const map={};
   new Intl.DateTimeFormat('fa-IR',options).formatToParts(date).forEach(part=>{if(part.type!=='literal')map[part.type]=part.value});
   const dateText=[map.weekday,faDigits(map.day),map.month,faDigits(map.year)].filter(Boolean).join(' ');
   if(!withTime)return dateText;
   const timeText=`${faDigits(map.hour).padStart(2,'۰')}:${faDigits(map.minute).padStart(2,'۰')}:${faDigits(map.second).padStart(2,'۰')}`;
   return `${dateText} ساعت \u2066${timeText}\u2069`;
  }catch{return String(value)}
 };
 const style=document.createElement('style');style.id='aqua-scoped-dashboard-style';style.textContent=`
 .aqua-action[data-tone="priority"]{border-color:rgba(74,221,255,.5)!important;background:radial-gradient(circle at 50% 8%,rgba(38,207,255,.28),transparent 48%),linear-gradient(155deg,rgba(7,73,129,.98),rgba(3,27,58,.99))!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.12),0 16px 38px rgba(0,137,225,.22),0 0 26px rgba(35,211,255,.08)!important}
 .aqua-action[data-tone="priority"] .aqua-action-orb{color:#eafbff!important;background:radial-gradient(circle at 35% 22%,#dffaff 0,#3bdbff 24%,#087fcf 52%,#05254d 82%)!important;border-color:rgba(151,239,255,.66)!important;box-shadow:inset 0 2px 4px rgba(255,255,255,.34),0 14px 32px rgba(0,157,238,.34),0 0 25px rgba(42,218,255,.18)!important}
 .aqua-action[data-tone="priority"] .aqua-action-label{font-size:1.05rem;color:#fff}.aqua-action[data-tone="priority"] .aqua-action-caption{color:#b8eaff}
 .aqua-action[data-tone="aqua"] .aqua-action-orb{color:#dff8ff!important;background:radial-gradient(circle at 37% 24%,rgba(179,244,255,.78),rgba(14,152,229,.58) 28%,rgba(2,65,124,.92) 58%,#031831 82%)!important;border-color:rgba(126,224,255,.44)!important}
 @media(max-width:520px){.aqua-action[data-tone="priority"]{min-height:158px!important}.aqua-action[data-tone="priority"] .aqua-action-orb{width:73px!important;height:73px!important}}
 `;if(!document.getElementById(style.id))document.head.appendChild(style);
 window.app=function(){
  const state=previous();
  state.persianDate=function(value){return jalaliWords(value,false)};
  state.persianDateTime=function(value){return jalaliWords(value,true)};
  state.quickActions=[
   {id:'smart',label:'ثبت هوشمند',caption:'متن، صدا و GPS',icon:'smart',tone:'priority'},
   {id:'aqua-ai',label:'هوش آکوا',caption:'چت، صدا و فرمان',icon:'smart',tone:'priority'},
   {id:'bale-jobs',label:'کارهای جدید',caption:'ورودی مستقیم از بله',icon:'services',tone:'priority'},
   {id:'customers',label:'مشتری‌ها',caption:'پرونده و سوابق',icon:'customers',tone:'aqua'},
   {id:'services',label:'سرویس‌ها',caption:'ثبت و پیگیری',icon:'services',tone:'aqua'},
   {id:'invoices',label:'فاکتورها',caption:'صدور و ارسال',icon:'invoices',tone:'aqua'},
   {id:'products',label:'محصولات',caption:'کاتالوگ و قیمت',icon:'products',tone:'aqua'},
   {id:'finance',label:'گزارش مالی',caption:'سود و تسویه',icon:'finance',tone:'aqua'},
   {id:'map',label:'نقشه',caption:'مشتری و مسیر',icon:'map',tone:'aqua'},
   {id:'settings',label:'تنظیمات',caption:'امنیت و بکاپ',icon:'settings',tone:'aqua'}
  ];
  return state;
 };
})();
"""


@app_v3.app.get("/aqua-scoped-ui.js")
def aqua_scoped_ui_js():
    return Response(SCOPED_UI_JS, mimetype="application/javascript", headers={"Cache-Control": "no-store, max-age=0"})


@app_v3.app.after_request
def inject_aqua_scoped_ui(response):
    try:
        if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
            response.direct_passthrough = False
            body = response.get_data(as_text=True)
            body = re.sub(r'<script src="/aqua-scoped-ui\.js\?v=[^"]+"></script>', "", body)
            position = body.lower().find("</head>")
            if position >= 0:
                tag = '<script src="/aqua-scoped-ui.js?v=20260901-1"></script>'
                body = body[:position] + tag + body[position:]
                response.set_data(body)
                response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_scoped_ui_inject_failed detail=%s", str(exc)[:200])
    return response
