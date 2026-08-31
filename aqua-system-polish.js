(()=>{
 const previous=window.app;if(typeof previous!=='function')return;
 const fa=n=>String(n).replace(/\d/g,d=>'Û°Û±Û²Û³Û´ÛµÛ¶Û·Û¸Û¹'[Number(d)]),pad=n=>fa(String(n).padStart(2,'0'));
 const jalali=value=>{const d=value instanceof Date?value:new Date(value),parts=new Intl.DateTimeFormat('en-US-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(d),o={};parts.forEach(p=>{if(['year','month','day'].includes(p.type))o[p.type]=Number(p.value)});return o};
 const isoDate=value=>{const p=jalali(value);return `\u2066${fa(p.year)}/${pad(p.month)}/${pad(p.day)}\u2069`};
 const urlKeyToBytes=s=>{const p='='.repeat((4-s.length%4)%4),raw=atob((s+p).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from([...raw],c=>c.charCodeAt(0))};
 const palette=['#2dd4bf','#22d3ee','#8b5cf6','#f59e0b','#f43f5e','#38bdf8','#a3e635'];
 window.app=function(){
  const s=previous();
  Object.assign(s,{pushBusy:false,pushActive:false,pushPermission:(window.Notification?.permission||'default'),financePolarChart:null});
  s.persianDate=function(v){if(!v)return'';const d=/^\d{4}-\d{2}-\d{2}$/.test(v)?new Date(v+'T12:00:00+03:30'):new Date(v),weekday=new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',weekday:'long'}).format(d);return `${weekday}ØŒ ${isoDate(d)}`};
  s.persianDateTime=function(v){if(!v)return'';try{const d=new Date(v),t=new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);return `${isoDate(d)} â€¢ ${t}`}catch{return v}};
  s.refreshPushStatus=async function(){this.pushPermission=window.Notification?.permission||'unsupported';if(!('serviceWorker'in navigator)||!('PushManager'in window))return this.pushActive=false;try{const r=await navigator.serviceWorker.ready,sub=await r.pushManager.getSubscription();this.pushActive=!!sub}catch{this.pushActive=false}};
  s.enableAquaPush=async function(){if(this.pushBusy)return;if(!('serviceWorker'in navigator)||!('PushManager'in window)||!window.Notification)return this.toast?.('Push Ø±ÙˆÛŒ Ø§ÛŒÙ† Ù…Ø±ÙˆØ±Ú¯Ø± Ù¾Ø´ØªÛŒØ¨Ø§Ù†ÛŒ Ù†Ù…ÛŒâ€ŒØ´ÙˆØ¯','error');this.pushBusy=true;try{const permission=await Notification.requestPermission();this.pushPermission=permission;if(permission!=='granted')throw Error('Ø§Ø¬Ø§Ø²Ù‡ Ù†ÙˆØªÛŒÙÛŒÚ©ÛŒØ´Ù† Ø¯Ø§Ø¯Ù‡ Ù†Ø´Ø¯');const key=await this.api('/push/public-key'),reg=await navigator.serviceWorker.ready;let sub=await reg.pushManager.getSubscription();if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlKeyToBytes(key.public_key)});await this.api('/push/subscribe',{method:'POST',body:JSON.stringify(sub.toJSON())});this.pushActive=true;this.toast?.('Ù†ÙˆØªÛŒÙÛŒÚ©ÛŒØ´Ù† Ú©Ø§Ø±Ù‡Ø§ÛŒ Ø¬Ø¯ÛŒØ¯ Ø±ÙˆÛŒ Ø§ÛŒÙ† Ú¯ÙˆØ´ÛŒ ÙØ¹Ø§Ù„ Ø´Ø¯','success')}catch(e){this.toast?.(e.message||'ÙØ¹Ø§Ù„â€ŒØ³Ø§Ø²ÛŒ Push Ø§Ù†Ø¬Ø§Ù… Ù†Ø´Ø¯','error')}finally{this.pushBusy=false}};
  s.disableAquaPush=async function(){if(this.pushBusy)return;this.pushBusy=true;try{const reg=await navigator.serviceWorker.ready,sub=await reg.pushManager.getSubscription();if(sub){await this.api('/push/subscribe',{method:'DELETE',body:JSON.stringify({endpoint:sub.endpoint})});await sub.unsubscribe()}this.pushActive=false;this.toast?.('Push Ø§ÛŒÙ† Ú¯ÙˆØ´ÛŒ ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´Ø¯','info')}catch(e){this.toast?.(e.message||'ØºÛŒØ±ÙØ¹Ø§Ù„â€ŒØ³Ø§Ø²ÛŒ Push Ø§Ù†Ø¬Ø§Ù… Ù†Ø´Ø¯','error')}finally{this.pushBusy=false}};
  s.sendFinanceBaleImage=async function(){if(this.pushBusy)return;this.pushBusy=true;try{const r=await this.api('/reports/finance-image/send',{method:'POST',body:'{}'});if(!r.ok)throw Error(r.error||'Ø§Ø±Ø³Ø§Ù„ ØªØµÙˆÛŒØ± Ø§Ù†Ø¬Ø§Ù… Ù†Ø´Ø¯');this.toast?.('Ú¯Ø²Ø§Ø±Ø´ ØªØµÙˆÛŒØ±ÛŒ Ù…Ø§Ù„ÛŒ Ø¨Ù‡ Ú†Øª Ø®ØµÙˆØµÛŒ Ø¨Ù„Ù‡ Ø§Ø±Ø³Ø§Ù„ Ø´Ø¯','success')}catch(e){this.toast?.(e.message||'Ø§Ø±Ø³Ø§Ù„ Ú¯Ø²Ø§Ø±Ø´ ØªØµÙˆÛŒØ±Ûˆ6a¶)öavb6`v`ˆ6*6b6+ÉË	Ù\œ›Ü‰Ê_Yš[˜[^İ\Ëœ\Ú\ŞOY˜[Ù__NÂˆËœ™[™\Ú\ÏY[˜İ[ÛŠ
^ÂˆÛÛœİ[ÛÏ]\Ëš˜[[S[ÛSY]šXÜß×KX™[Ï[[ÛË›X\
OO›K›X™[
KÛÛ[[Û^Ü™\ÜÛœÚ]™NYKXZ[Z[\ÜXİ˜][Î™˜[ÙKYÚ[œÎÛYÙ[™ÜÜÚ][Û‰Ø›İÛIËX™[ÎØÛÛÜ‰ÈÎY˜™	Ë\ÙTÚ[İ[NY___KØØ[\ÎŞİXÚÜÎØÛÛÜ‰ÈÎMXXIßKÜšYØÛÛÜ‰Ü™Ø˜JMMŒËNŒ
Iß_KNİXÚÜÎØÛÛÜ‰ÈÎMXXIßKÜšYØÛÛÜ‰Ü™Ø˜JMMŒËNŒ
Iß___NÂˆÛÛœİÌOYØİ[Y[™Ù][[Y[RY
	Û[ÛPÚ\	ÊNÖØÌKØİ[Y[™Ù][[Y[RY
	ŞYX\›PÚ\	ÊKØİ[Y[™Ù][[Y[RY
	ÜÙ\šXÙPÚ\	ÊWK™š[\Š›ÛÛX[ŠK™›Ü‘XXÚ
ÏOÚYŠËœ\™[[[Y[
XËœ\™[[[Y[œİ[K›Z[’ZYÚIÌÍ	ßJNÚYŠÌJ^İ\Ë›[ÛPÚ\Ë™\İ›ŞOËŠ
Nİ\Ë›[ÛPÚ\[™]ÈÚ\
ÌKİ\N‰Û[™IË]NÛX™[Ë]\Ù]Î–ŞÛX™[‰ö+ö,vã6)ö`v*¶ã	Ë]N›[ÛË›X\
OO›Kœ™XÙZ]™Y
K›Ü™\ÛÛÜœ[]VÌK˜XÚÙÜ›İ[™ÛÛÜ‰Ü™Ø˜JKŒL‹NLKŒM
IËš[YK[œÚ[Û‹ŒÎ›Ü™\•ÚYŒËÚ[˜Y]\ÎKÛX™[‰ö,öb6+È6+¶)öa6-IË]N›[ÛË›X\
OO›K›™]Ü›Ùš]
K›Ü™\ÛÛÜœ[]VÌ—K˜XÚÙÜ›İ[™ÛÛÜ‰Ü™Ø˜JLÎKL‹‹ŒL
IËš[YK[œÚ[Û‹ŒÎ›Ü™\•ÚYŒËÚ[˜Y]\ÎKÛX™[‰öaö,¶ã6a¶aÉË]N›[ÛË›X\
OO›K™^[œÙ\ÊK›Ü™\ÛÛÜœ[]VÌ×K[œÚ[Û‹ŒÌ‹›Ü™\•ÚYŒŸW_KÜ[ÛœÎ˜ÛÛ[[ÛŸJ_BˆÛÛœİYX\œÏ]\Ëš˜[[VYX\›SY]šXÜß×KŞOYØİ[Y[™Ù][[Y[RY
	ŞYX\›PÚ\	ÊNÚYŠŞJ^İ\ËYX\›PÚ\Ë™\İ›ŞOËŠ
Nİ\ËYX\›PÚ\[™]ÈÚ\
ŞKİ\N‰Ø˜\‰Ë]NÛX™[ÎYX\œË›X\
OO™˜JKYX\ŠJK]\Ù]Î–ŞÛX™[‰ö+ö,vã6)ö`v*¶ã	Ë]NYX\œË›X\
OOKœ™XÙZ]™Y
K˜XÚÙÜ›İ[™ÛÛÜ‰Ü™Ø˜JÍŒLKŒÎÌŠIË›Ü™\”˜Y]\ÎŒMKÛX™[‰ö,öb6+È6+¶)öa6-IË]NYX\œË›X\
OOK›™]Ü›Ùš]
K˜XÚÙÜ›İ[™ÛÛÜ‰Ü™Ø˜JLÎKL‹‹ÌŠIË›Ü™\”˜Y]\ÎŒMW_KÜ[ÛœÎ˜ÛÛ[[ÛŸJ_BˆÛÛœİ\\Ï]\Ë˜[˜[]XÜÏËœÙ\šXÙWİ\\ß×KÜÏYØİ[Y[™Ù][[Y[RY
	ÜÙ\šXÙPÚ\	ÊNÚYŠÜÊ^İ\ËœÙ\šXÙPÚ\Ë™\İ›ŞOËŠ
Nİ\ËœÙ\šXÙPÚ\[™]ÈÚ\
ÜËİ\N‰ÙİYÚ]	Ë]NÛX™[Î\\Ë›X\
OœÙ\šXÙWİ\_›X™[	ö,ö,vb6ã6,ÉÊK]\Ù]Î–ŞÙ]N\\Ë›X\
O“[X™\Šœ™XÙZ]™YÏŞ˜[[İ[ÏŞ˜Ûİ[ÏÌ
JK˜XÚÙÜ›İ[™ÛÛÜ\\Ë›X\

ËJOOœ[]VÚI\[]K›[™İJK›Ü™\•ÚYŒİ™\“Ù™œÙ]_W_KÜ[ÛœÎÜ™\ÜÛœÚ]™NYKXZ[Z[\ÜXİ˜][Î™˜[ÙKİ]İ]‰ÍŒ‰IËYÚ[œÎÛYÙ[™ÜÜÚ][Û‰Ø›İÛIËX™[ÎØÛÛÜ‰ÈÎY˜™	Ë\ÙTÚ[İ[NY_____J_BˆÛÛœİÜYØİ[Y[™Ù][[Y[RY
	Ùš[˜[˜ÙTÛ\Ú\	ÊNÚYŠÜ
^İ\Ë™š[˜[˜ÙTÛ\Ú\Ë™\İ›ŞOËŠ
NØÛÛœİ]\Ë˜[˜[]XÜÏËİ[ßßK]OVÓ[X™\Šœ™XÙZ]™Y
K[X™\Š˜ÛÛ\[WÜÚ\™_
K[X™\Š™^[œÙ\ß
KX]›X^
[X™\Š›™]Ü›Ùš]
K
WNİ\Ë™š[˜[˜ÙTÛ\Ú\[™]ÈÚ\
Üİ\N‰ÜÛ\\™XIË]NÛX™[Î–Éö+ö,vã6)ö`v*¶ã	Ë	ö,öaöaH6-6,vªv*‰Ë	öaö,¶ã6a¶aÉË	ö,öb6+É×K]\Ù]Î–ŞÙ]K˜XÚÙÜ›İ[™ÛÛÜ–ÉÜ™Ø˜JKŒL‹NLKÌŠIË	Ü™Ø˜JÍŒLKŒÎÌŠIË	Ü™Ø˜JKMNLKÌŠIË	Ü™Ø˜JLÎKL‹‹ÌŠIË_W_KÜ[ÛœÎÜ™\ÜÛœÚ]™NYKXZ[Z[\ÜXİ˜][Î™˜[ÙKYÚ[œÎÛYÙ[™ÜÜÚ][Û‰Ø›İÛIËX™[ÎØÛÛÜ‰ÈÎY˜™	Ë\ÙTÚ[İ[NY___KØØ[\ÎÜİXÚÜÎÙ\Ü^N™˜[Ù_KÜšYØÛÛÜ‰Ü™Ø˜JMMŒËNŒLŠIß____J_BˆNÂˆÛÛœİÛ[İ[\Ë›[İ[[š[˜Ù[Y[ÏË˜š[™
ÊNÜË›[İ[[š[˜Ù[Y[ÏY[˜İ[ÛŠ
^ØÛÛœİ[Û[İ[ËŠ
NÜÙ][Y[İ]


OOÙØİ[Y[œ]Y\TÙ[XİÜ[
	Ë˜\KY›Ø]	ÊK™›Ü‘XXÚ
Oœ™[[İ™J
JNİ\Ëœ™Yœ™\Ú\Úİ]\ÏËŠ
_K
NÜ™]\›ˆŸNÂˆ™]\›ˆÂˆNÂˆÛÛœİ[İ[J
OOÂˆØİ[Y[œ]Y\TÙ[XİÜ[
	Ë˜\KY›Ø]	ÊK™›Ü‘XXÚ
Oœ™[[İ™J
JNÂˆÛÛœİÙ][™ÜÏVË‹‹™Øİ[Y[œ]Y\TÙ[XİÜ[
	ÜÙXİ[Û‰ÊWK™š[™
OŠ™Ù]]šX]J	Ş\ÚİÉÊ_	ÉÊKš[˜ÛY\ÊœYÙOOOIÜÙ][™ÜÉÈŠJNÂˆYŠÙ][™ÜÉ‰ˆ\Ù][™ÜËœ]Y\TÙ[XİÜŠ	Ë˜\K\\ÚXØ\™	ÊJ^ØÛÛœİØ\™YØİ[Y[˜Ü™X]Q[[Y[
	Ù]‰ÊNØØ\™˜Û\ÜÓ˜[YOIØØ\™MH\K\\ÚXØ\™	ÎØØ\™š[›™\’SX]ˆÛ\ÜÏH™›^\İYKX™]ÙY[ˆØ\LÈ]ÈÛ\ÜÏHœÙXİ[Û‹]]H¶a¶b6*¶ã6`vã6ªvã6-6aˆ6«öb6-6ãÚÏÛ\ÜÏH^\ÛH]]Y]LH¶*6)È6,v,öã6+öaˆ6ªv)ö,H6+6+öã6+È6)ö,ˆ6*6a6aö#6+v*¶ã6b6`¶*¶ã\]XQÛÛ6*6)ö,ˆ6a¶ã6,ö*ˆ6,vb6ã6«öb6-6ã6)ö.va6)öaˆ6*6«öã6,KÜÙ]Ü[ˆÛ\ÜÏH˜Ú\ˆ˜Û\ÜÏHœ\ÚXİ]™OÉØ™ËY[Y\˜[MLÌL^Y[Y\˜[ML	Î‰Ø™Ë\Û]KMLÌL]]Y	Èˆ]^Hœ\ÚXİ]™OÉö`v.v)öa	Î‰ö.¶ã6,v`v.v)öa	ÈÜÜ[Ù]]ˆÛ\ÜÏH™ÜšYÜšYXÛÛËLˆØ\Lˆ]M]ÛˆÛ\ÜÏH˜ˆš[X\HˆÛXÚÏH™[˜X›P\]XT\Úˆ™\ØX›YHœ\Ú\ŞH¶`v.v)öa8 #6,ö)ö,¶ã6,vb6ã6)öã6aˆ6«öb6-6ãØ]Û]ÛˆÛ\ÜÏH˜ˆÛÙˆÛXÚÏH™\ØX›P\]XT\Úˆ™\ØX›YHœ\Ú\ŞH¶.¶ã6,v`v.v)öa8 #6,ö)ö,¶ãØ]ÛÙ]]ˆÛ\ÜÏH^^È]]Y]LÈ¶+ö,HTÛ™H6*6)öã6+È\]XQÛÛ6*6aÈÛYHØÜ™Y[ˆ6)ö-¶)ö`vaÈ6-6+öaÈ6*6)ö-6+Ëˆ6)ö+6)ö,¶aÈ6)ö.va6)öaˆ6`v`¶-È6*6)È6a6av,È6+öªvavaÈ6*6)öa6)È6+ö,v+¶b6)ö,ö*ˆ6avã8 #6-6b6+ËÙ]˜ÜÙ][™ÜËš[œÙ\™Y›Ü™JØ\™Ù][™ÜË™š\œİÚ[
NİÚ[™İË[[™OËš[š]™YOËŠØ\™
_BˆÛÛœİš[˜[˜ÙOVË‹‹™Øİ[Y[œ]Y\TÙ[XİÜ[
	ÜÙXİ[Û‰ÊWK™š[™
OŠ™Ù]]šX]J	Ş\ÚİÉÊ_	ÉÊKš[˜ÛY\ÊœYÙOOOIÙš[˜[˜ÙIÈŠJNÂˆYŠš[˜[˜ÙI‰ˆYš[˜[˜ÙKœ]Y\TÙ[XİÜŠ	Ë˜\KYš[˜[˜ÙK]š\İX[ÉÊJ^ØÛÛœİ›ØÚÏYØİ[Y[˜Ü™X]Q[[Y[
	Ù]‰ÊNØ›ØÚË˜Û\ÜÓ˜[YOIÙÜšYÎ™ÜšYXÛÛËLˆØ\M\KYš[˜[˜ÙK]š\İX[ÉÎØ›ØÚËš[›™\’SX]ˆÛ\ÜÏH˜Ø\™MH]ˆÛ\ÜÏH™›^\İYKX™]ÙY[ˆØ\Lˆ][\ËXÙ[\ˆ]ÈÛ\ÜÏH™›ÛX›XÚÈ¶*¶,vªvã6*6av)öa6ãÚÏÛ\ÜÏH^^È]]Y¶a¶av)öã6+ö)öã6,vaø #6)öã6+ö,vã6)ö`v*¶ã6#6,öaöaH6-6,vªv*¶#6aö,¶ã6a¶aÈ6b6,öb6+ÏÜÙ]]Ûˆ\ÚİÏH˜Ø[YZ[ˆˆÛ\ÜÏH˜ˆÛÙ\KLˆˆÛXÚÏHœÙ[™š[˜[˜ÙP˜[R[XYÙH¶)ö,v,ö)öa6*¶-vb6ã6,H6*6aÈ6*6a6aÏØ]ÛÙ]]ˆİ[OHšZYÚŒÌLˆÛ\ÜÏH›]LÈØ[˜\ÈYH™š[˜[˜ÙTÛ\Ú\ØØ[˜\ÏÙ]Ù]]ˆÛ\ÜÏH˜Ø\™MHÈÛ\ÜÏH™›ÛX›XÚÈ¶,v)öaöa¶av)öã6a¶avb6+ö)ö,vaö)ÏÚÏ]ˆÛ\ÜÏH™ÜšYÜšYXÛÛËLˆØ\LÈ]M^\ÛH]ˆÛ\ÜÏHœ›İ[™YLM™Ë]X[MLÌL¸¥ãÈ6+¶-öãˆ6,vb6a¶+È6av)öaö)öa¶aÏÙ]]ˆÛ\ÜÏHœ›İ[™YLM™ËXŞX[‹MLÌL¸¥¨6,ö*¶b6a¶ãˆ6av`¶)öã6,öaÈ6,ö)öa8 #6aö)ÏÙ]]ˆÛ\ÜÏHœ›İ[™YLM™Ë]š[Û]MLÌL¸¥âH6+ö)öã6,vaø #6)öãˆ6,öaöaH6,ö,vb6ã6,ø #6aö)ÏÙ]]ˆÛ\ÜÏHœ›İ[™YLM™ËX[X™\‹MLÌL¸§)ˆ6`¶-ö*6ãˆ6*¶,vªvã6*6av)öa6ãÙ]Ù]Û\ÜÏH^^È]]Y]M¶«ö,¶)ö,v-6*¶-vb6ã6,vã6aöavã6aˆ6*6+¶-6aö,H6-6*6,ö)ö.v*ˆ6ì¶ìÈ6`v`¶-È6*6aÈ6¡¶*ˆ6+¶-vb6-vã6av+öã6,vã6*¶ã6*6a6aÈ6)ö,v,ö)öa6avã8 #6-6b6+ËÜÙ]˜Ùš[˜[˜ÙK˜\[™Ú[
›ØÚÊNİÚ[™İË[[™OËš[š]™YOËŠ›ØÚÊNÜÙ][Y[İ]


OOİ^İÚ[™İË[[™OË‰]OËŠØİ[Y[˜›ÙJOËœ™[™\Ú\ÏËŠ
_XØ]Úß_KN
_BˆÛÛœİÛØÚÏYØİ[Y[™Ù][[Y[RY
	Ø\]XKZ˜[[KXÛØÚÉÊNÚYŠÛØÚÊ^ØÛÛœİ[™]È]J
KÙYZÙ^O[™]È[‘]U[YQ›Ü›X]
	Ù˜KRT‰Ëİ[YV›Û™N‰Ğ\ÚXKÕZ˜[‰ËÙYZÙ^N‰ÛÛ™ÉßJK™›Ü›X]

K[™]È[‘]U[YQ›Ü›X]
	Ù˜KRT‰Ëİ[YV›Û™N‰Ğ\ÚXKÕZ˜[‰Ëİ\‰Ì‹YYÚ]	ËZ[]N‰Ì‹YYÚ]	Ëİ\ŒL™˜[Ù_JK™›Ü›X]

K^X	İÙYZÙ^_H8 (ˆ	Ú\ÛÑ]J
_H8 (ˆ6,ö)ö.v*ˆ	İXÚYŠÛØÚË^ÛÛ[OO]^
XÛØÚË^ÛÛ[]^BˆNÂˆÛÛœİİ\J
OOÛ[İ[

NÛ™]È]]][Û“ØœÙ\™\Š[İ[
K›ØœÙ\™JØİ[Y[˜›ÙKØÚ[\İYKİX™YNY_JNÜÙ][\˜[
[İ[L
_NÂˆYŠØİ[Y[œ™XYTİ]OOOIÛØY[™ÉÊYØİ[Y[˜Y]™[\İ[™\Š	ÑÓPÛÛ[ØYY	Ëİ\ÛÛ˜ÙNY_JNÙ[ÙHİ\

NÂŸJJ
NÂ