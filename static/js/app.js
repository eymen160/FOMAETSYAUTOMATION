const $=s=>document.querySelector(s);
const ALANLAR=[["ciro","Ciro"],["vergi","Vergi"],["kargo_musteri","Kargo müşteri"],["kargo","Kargo (maliyet)"],["adet","Parça adedi"]];
const CIRO_ETIKET={subtotal_shipping:"Subtotal + kargo (vergisiz)",order_total:"Order Total",amount_paid:"Amount Paid"};
let durumBilgi=null, sonAnaliz=null, sonDenetim=null, demoMod=false;

function bekle(a,metin){$("#yuk-metin").textContent=metin||"İşleniyor…";$("#yukleniyor").style.display=a?"flex":"none";}
function mesaj(t,tip){const d=document.createElement("div");d.className=tip||"uyari";d.textContent=t;$("#mesajlar").appendChild(d);setTimeout(()=>d.remove(),9000);}
function tl(n){return n==null?"—":Number(n).toLocaleString("tr-TR",{maximumFractionDigits:0});}
function tl2(n){return n==null?"—":Number(n).toLocaleString("tr-TR",{minimumFractionDigits:2,maximumFractionDigits:2});}
function pct(n){return n==null?"—":(n*100).toFixed(1)+"%";}

async function api(yol,govde,metin){
  bekle(true,metin);
  try{
    const r=await fetch(yol,govde?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(govde)}:{method:"POST"});
    if(r.status===401){ window.location="/giris"; return null; }
    const j=await r.json();
    if(!r.ok){mesaj(j.hata||"Bilinmeyen hata","hata");return null;}
    return j;
  }catch(e){mesaj("Sunucuya ulaşılamadı: "+e.message,"hata");return null;}
  finally{bekle(false);}
}

/* ---- stepper ---- */
function adimGoster(n){
  for(let i=1;i<=5;i++){$("#p"+i).classList.toggle("aktif",i===n);}
  document.querySelectorAll(".stepper .st").forEach(st=>{
    const s=+st.dataset.step;
    st.classList.toggle("aktif",s===n);
    st.classList.toggle("tamam",s<n);
  });
  window.scrollTo({top:0,behavior:"smooth"});
}
document.querySelectorAll(".stepper .st").forEach(st=>{
  st.addEventListener("click",()=>{
    if(!sonAnaliz)return;
    let n=+st.dataset.step;
    if(sonAnaliz.mod==="formsuz"&&n===4)n=5;  // formsuz'da denetim adımı yok
    adimGoster(n);
  });
});

/* ---- başlangıç durumu ---- */
async function durumYukle(){
  const r=await fetch("/api/durum");
  if(r.status===401){ window.location="/giris"; return; }
  durumBilgi=await r.json();
  const aySec=$("#ay"),yilSec=$("#yil");
  if(!aySec.options.length){
    durumBilgi.aylar.forEach(a=>aySec.add(new Option(a,a)));
    const yb=new Date().getFullYear();
    for(let y=yb-2;y<=yb+1;y++)yilSec.add(new Option(y,y));
    if(durumBilgi.donemler&&durumBilgi.donemler.length){
      const son=durumBilgi.donemler[durumBilgi.donemler.length-1];
      aySec.value=son.donem;yilSec.value=son.yil;
    }
  }
  if(!durumBilgi.demo_var){$("#btn-demo").disabled=true;$("#btn-demo").textContent="Demo verisi bulunamadı";}
}

/* ---- DEMO akışı ---- */
$("#btn-demo").addEventListener("click",async()=>{
  const d=await api("/api/demo",null,"Demo verisi yükleniyor…");
  if(!d)return;
  demoMod=true; $("#ust-alt").textContent="Demo · "+d.ay+" "+d.yil;
  $("#landing").style.display="none"; $("#app").style.display="block";
  $("#ay").value=d.ay; $("#yil").value=d.yil;
  await analizCalistir(true);
});
$("#btn-kendi").addEventListener("click",()=>{
  demoMod=false; $("#ust-alt").textContent="Aylık Rapor Otomasyonu";
  $("#landing").style.display="none"; $("#app").style.display="block";
  $("#p2-kendi").classList.remove("gizli");
  durumGoster(); adimGoster(1);
});

/* ---- adım 1: analiz ---- */
$("#btn-analiz").addEventListener("click",()=>analizCalistir(false));
async function analizCalistir(otomatik){
  const formsuz=$("#formsuz-toggle")&&$("#formsuz-toggle").checked;
  const j=await api("/api/analiz",{ay:$("#ay").value,yil:$("#yil").value,formsuz:formsuz},"Veriler işleniyor…");
  if(!j)return;
  sonAnaliz=j;
  durumGoster();
  if(j.mod==="formsuz"){
    $("#analiz-ozet").textContent=`${j.ay} ${j.yil}: ${j.magaza_sayisi} mağaza (ham veriden).`;
    elleGirdiCiz(j);
    adimGoster(3);
    return;
  }
  $("#analiz-ozet").textContent=`${j.ay} ${j.yil}: ${j.form_magaza_sayisi} mağaza formu bulundu.`;
  eslestirmeCiz(j.eslestirme);
  if(otomatik){ adimGoster(3); } else { adimGoster(2); }
}

// Formsuz mod: eşleştirme panelini elle-girdi tablosuna çevirir
function elleGirdiCiz(j){
  document.querySelector('.stepper .st[data-step="3"]').querySelector('.n').nextSibling;
  let h=`<p class="alt2">Reklam, İlave ödeme ve Upgrade ham veride yok — buradan girin (dönem bazında kaydedilir). Diğer tüm kolonlar ShipStation'dan otomatik.</p>`;
  h+=`<div class="tablosar"><table id="t-elle"><tr><th>Mağaza</th><th>Reklam ($)</th><th>İlave ödeme ($)</th><th>Upgrade (adet)</th></tr>`;
  j.magazalar.forEach(m=>{
    const e=(j.elle&&j.elle[m])||{};
    h+=`<tr><td class="ad">${m}</td>
      <td><input type="number" step="0.01" data-m="${m.replace(/"/g,'&quot;')}" data-f="reklam" value="${e.reklam||''}" style="width:110px"></td>
      <td><input type="number" step="0.01" data-m="${m.replace(/"/g,'&quot;')}" data-f="ilave_odeme" value="${e.ilave_odeme||''}" style="width:110px"></td>
      <td><input type="number" step="1" data-m="${m.replace(/"/g,'&quot;')}" data-f="upgrade" value="${e.upgrade||''}" style="width:90px"></td></tr>`;
  });
  h+=`</table></div>`;
  if(j.amazon&&j.amazon.length) h+=`<div class="uyari" style="margin-top:10px">Rapor dışı (Amazon): ${j.amazon.map(a=>`${a.magaza} (${tl(a.siparis)} sipariş)`).join(" · ")}</div>`;
  $("#esl-icerik").innerHTML=h;
  $("#esl-ozet").textContent=`${j.magaza_sayisi} mağaza · ham veriden`;
  $("#btn-esl-onayla").textContent="Kaydet ve rapora geç →";
}

/* ---- adım 2: veri durumu ---- */
function durumGoster(){
  fetch("/api/durum").then(r=>r.json()).then(s=>{
    const mk=$("#vk-master"),ok=$("#vk-ozet"),kk=$("#vk-kalem");
    if(s.master){mk.classList.add("dolu");$("#vk-master-ad").textContent="✓ "+s.master;}
    if(s.orders){ok.classList.add("dolu");$("#vk-ozet-ad").textContent="✓ "+s.orders;}
    if(s.kalem){kk.classList.add("dolu");$("#vk-kalem-ad").textContent="✓ "+s.kalem;}
  });
}
$("#btn-p2-devam").addEventListener("click",()=>{ if(sonAnaliz) adimGoster(3); else mesaj("Önce analiz çalıştırın.","uyari"); });

/* kendi dosya yükleme */
async function dosyaYukle(tip,inp){
  if(!inp.files[0])return;
  bekle(true,"Dosya yükleniyor…");
  const fd=new FormData();fd.append("dosya",inp.files[0]);
  try{
    const r=await fetch("/api/yukle/"+tip,{method:"POST",body:fd});const j=await r.json();
    if(!r.ok){mesaj(j.hata,"hata");return;}
    mesaj(inp.files[0].name+" yüklendi.","bilgi");durumGoster();
  }finally{bekle(false);}
}
$("#f-master")&&$("#f-master").addEventListener("change",e=>dosyaYukle("master",e.target));
$("#f-orders")&&$("#f-orders").addEventListener("change",e=>dosyaYukle("orders",e.target));
$("#f-kalem")&&$("#f-kalem").addEventListener("change",e=>dosyaYukle("kalem",e.target));

/* ---- adım 3: eşleştirme ---- */
function secenekListesi(secili){
  let s=`<option value="-">— (rapora girmesin)</option><option value="Rapor Dışı (Amazon)">Rapor Dışı (Amazon)</option>`;
  sonAnaliz.magazalar.forEach(x=>{s+=`<option ${x===secili?"selected":""}>${x}</option>`;});
  return s;
}
function eslestirmeCiz(liste){
  const onayli=liste.filter(e=>e.durum==="eslesik");
  const incele=liste.filter(e=>e.durum==="oneri"||e.durum==="bilinmiyor");
  const amazon=liste.filter(e=>e.durum==="amazon");
  let h="";
  if(onayli.length){
    h+=`<div class="esl-grup"><h3><span class="rozet iyi">Otomatik eşleşti</span> ${onayli.length} mağaza</h3>`;
    onayli.forEach(e=>{h+=eslKart(e,true);});
    h+=`</div>`;
  }
  if(incele.length){
    h+=`<div class="esl-grup"><h3><span class="rozet incele">İnceleme gerekli</span> ${incele.length} mağaza — adı benzer, onayınızı bekliyor</h3>`;
    incele.forEach(e=>{h+=eslKart(e,false);});
    h+=`</div>`;
  }
  if(amazon.length){
    h+=`<div class="esl-grup"><h3><span class="rozet notr">Rapor dışı (Amazon)</span> ${amazon.length} mağaza</h3>`;
    amazon.forEach(e=>{h+=eslKart(e,true);});
    h+=`</div>`;
  }
  $("#esl-icerik").innerHTML=h;
  liste.forEach(e=>{const sel=document.querySelector(`select[data-ss="${CSS.escape(e.shipstation)}"]`);
    if(sel&&e.master)sel.value=e.master;});
  $("#esl-ozet").textContent=`${onayli.length} otomatik · ${incele.length} inceleme`;
}
function eslKart(e,kilit){
  const skor=e.skor?`<span class="notmetin">benzerlik ${Math.round(e.skor)}%</span>`:"";
  return `<div class="esl-kart"><span class="ss">${e.shipstation}</span><span class="ok">→</span>
    <select data-ss="${e.shipstation.replace(/"/g,'&quot;')}">${secenekListesi(e.master||"-")}</select> ${skor}</div>`;
}
$("#btn-esl-onayla").addEventListener("click",async()=>{
  if(sonAnaliz&&sonAnaliz.mod==="formsuz"){
    const girdiler={};
    document.querySelectorAll("#t-elle input").forEach(inp=>{
      if(inp.value!==""){ (girdiler[inp.dataset.m]=girdiler[inp.dataset.m]||{})[inp.dataset.f]=parseFloat(inp.value)||0; }
    });
    const r=await api("/api/formsuz/elle",{girdiler},"Kaydediliyor…");
    if(!r)return;
    await raporGoster(); adimGoster(5);
    return;
  }
  const eslesmeler={};
  document.querySelectorAll("#esl-icerik select").forEach(s=>eslesmeler[s.dataset.ss]=s.value);
  const j=await api("/api/eslestirme/kaydet",{eslesmeler},"Eşleştirmeler kaydediliyor…");
  if(!j)return;
  await denetimYukle(); adimGoster(4);
});

/* ---- adım 4: denetim ---- */
function kaynakSecimCiz(){
  const k=$("#kaynaklar"); k.innerHTML="<b style='font-size:13.5px'>Rapor kaynağı:</b>";
  ALANLAR.forEach(([alan,et])=>{
    const d=document.createElement("label");
    d.innerHTML=`${et}: <select data-alan="${alan}"><option value="shipstation">ShipStation</option><option value="form">Form</option></select>`;
    k.appendChild(d);
  });
  const c=document.createElement("label");
  c.innerHTML=`Ciro tanımı: <select id="ciro-kaynagi">
    <option value="subtotal_shipping">Subtotal+kargo</option><option value="order_total">Order Total</option><option value="amount_paid">Amount Paid</option></select>`;
  k.appendChild(c);
  // varsayılanlar: ShipStation; Vergi → Form (Etsy kesintisi, kıyas dışı)
  k.querySelector('select[data-alan="vergi"]').value="form";
  k.querySelectorAll("select").forEach(s=>s.addEventListener("change",denetimYukle));
}
async function denetimYukle(){
  if(!$("#kaynaklar").children.length) kaynakSecimCiz();
  const ck=($("#ciro-kaynagi")||{}).value;
  const j=await api("/api/denetim",{ciro_kaynagi:ck},"Denetleniyor…");
  if(!j)return; sonDenetim=j;
  const kal=j.kalibrasyon;let kh="";
  if(kal&&kal.magaza_sayisi){
    const sap=Object.entries(kal.medyan_sapmalar||{}).filter(([,v])=>v!=null).map(([a,v])=>`${CIRO_ETIKET[a]||a}: ${pct(v)}`).join(" · ");
    kh=`<div class="bilgi">Ciro kalibrasyonu (${kal.magaza_sayisi} mağaza, medyan sapma): ${sap}. ${kal.net?("Önerilen tanım: <b>"+(CIRO_ETIKET[kal.oneri]||kal.oneri)+"</b>"):"Seçimi siz yapın."}</div>`;
    if(kal.net&&$("#ciro-kaynagi")&&!$("#ciro-kaynagi").dataset.elle)$("#ciro-kaynagi").value=kal.oneri;
  }
  kh+=`<div class="bilgi">Not: <b>Vergi</b> form beyanı Etsy kesintisidir; ShipStation satış vergisiyle birebir kıyaslanamaz → kaynak <b>Form</b> (varsayılan). Reklam ve İlave ödeme her zaman formdan.</div>`;
  $("#kalibrasyon").innerHTML=kh;
  if($("#ciro-kaynagi"))$("#ciro-kaynagi").addEventListener("change",()=>{$("#ciro-kaynagi").dataset.elle="1";},{once:true});
  let html="<tr><th>Mağaza</th>";
  ALANLAR.forEach(([a,et])=>{
    const ek = a==="vergi" ? " · kıyas dışı" : "";
    html+=`<th>${et}<br><span style='font-weight:400;font-size:11px'>form / gerçek / sapma${ek}</span></th>`;
  });
  html+="</tr>";
  j.tablo.forEach(s=>{
    html+=`<tr><td class="ad">${s.magaza}${s.ss_var?"":' <span class="rozet incele">SS yok</span>'}</td>`;
    ALANLAR.forEach(([a])=>{
      const v=s.alanlar[a];
      // Vergi yapısal olarak kıyaslanamaz (Etsy kesintisi vs satış vergisi) →
      // nötr göster, gerçek sapmalar (ciro/kargo/adet) öne çıksın
      const c = a==="vergi" ? "" : (v.renk==="sari"?"sari":v.renk==="kirmizi"?"kirmizi":"");
      const sap = a==="vergi" ? "—" : (v.sapma==null?"—":pct(v.sapma));
      html+=`<td class="${c}">${tl(v.form)} / ${tl(v.shipstation)} / ${sap}</td>`;
    });
    html+="</tr>";
  });
  $("#t-denetim").innerHTML=html;
  if(sonAnaliz&&sonAnaliz.kalem_var){ $("#urun-denetim-blok").classList.remove("gizli"); urunDenetimYukle(); }
  else { $("#urun-denetim-blok").classList.add("gizli"); }
}

let sonUrunKat=[];
async function urunDenetimYukle(){
  const j=await api("/api/urun/denetim",{},"Ürünler sınıflanıyor…");
  if(!j)return;
  sonUrunKat=j.kategoriler||[];
  const k=j.kapsama;
  $("#urun-kapsama").textContent=`${k.toplam} adetin %${Math.round(k.oran*100)}'i bilinen kategoriye eşlendi, kalanı "Diğer Ürün".`;
  let h="<tr><th>Mağaza</th><th>Form toplam</th><th>ShipStation (oto)</th><th>Sapma</th></tr>";
  j.tablo.forEach(s=>{
    const c=s.renk==="sari"?"sari":s.renk==="kirmizi"?"kirmizi":"";
    h+=`<tr><td class="ad">${s.magaza}</td><td>${tl(s.form_toplam)}</td><td>${tl(s.oto_toplam)}</td><td class="${c}">${pct(s.sapma)}</td></tr>`;
  });
  $("#t-urun-denetim").innerHTML=h;
  // Bilinmeyen SKU öğretme
  if(j.bilinmeyen&&j.bilinmeyen.length){
    const opt=sonUrunKat.map(c=>`<option>${c}</option>`).join("");
    let s=`<b style="font-size:13.5px">Bilinmeyen SKU'ları öğret</b> <span class="notmetin">(Diğer Ürün'e düşenler; eşleyince sözlüğe kaydedilir ve sonraki aylarda otomatik tanınır)</span>`;
    j.bilinmeyen.forEach(([sku,adet])=>{
      const skuKod=sku.split("|")[0].trim();
      s+=`<div class="esl-kart"><span class="ss">${sku} <span class="notmetin">(${adet})</span></span><span class="ok">→</span>
        <select data-sku="${skuKod.replace(/"/g,'&quot;')}"><option value="">— seç —</option>${opt}</select></div>`;
    });
    s+=`<button class="acc" id="btn-sku-ogret" style="margin-top:6px">Seçilenleri öğret</button>`;
    $("#sku-ogret").innerHTML=s;
    $("#btn-sku-ogret").addEventListener("click",async()=>{
      const esl={};
      document.querySelectorAll('#sku-ogret select[data-sku]').forEach(x=>{ if(x.value) esl[x.dataset.sku]=x.value; });
      if(!Object.keys(esl).length){mesaj("Önce en az bir SKU için kategori seçin.","uyari");return;}
      const r=await api("/api/urun/ogret",{eslesmeler:esl},"Öğretiliyor…");
      if(r){mesaj(r.ogretilen+" SKU öğretildi.","bilgi"); urunDenetimYukle();}
    });
  } else { $("#sku-ogret").innerHTML=""; }
}
function urunKaynagi(){ const r=document.querySelector('input[name="urun-kaynagi"]:checked'); return r?r.value:"form"; }
document.addEventListener("change",e=>{ if(e.target.name==="urun-kaynagi") {/* rapor adımında uygulanır */} });

$("#btn-rapor-uret").addEventListener("click",async()=>{
  await raporGoster(); adimGoster(5);
});

/* ---- adım 5: sonuç + CEO ---- */
function kaynaklarTopla(){
  const k={};document.querySelectorAll('#kaynaklar select[data-alan]').forEach(s=>k[s.dataset.alan]=s.value);
  return {kaynaklar:k,ciro_kaynagi:($("#ciro-kaynagi")||{}).value,urun_kaynagi:urunKaynagi()};
}
async function raporGoster(){
  const cfg=kaynaklarTopla();
  const s=await api("/api/sonuc",cfg,"Sonuç hesaplanıyor…");
  if(!s)return;
  const u=await api("/api/rapor",cfg,"Excel hazırlanıyor…");
  $("#rapor-baslik").textContent=`Sonuç — ${s.ay} ${s.yil}`;
  const c=s.ceo;
  $("#ceo-kartlar").innerHTML=`
    ${kart("İşlenen sipariş",tl(c.islenen_siparis),"ShipStation'dan otomatik")}
    ${kart("Toplam ciro",tl(c.toplam_ciro)+" $","")}
    ${kart("Toplam kargo",tl(c.toplam_kargo)+" $","gerçek maliyet")}
    ${kartVurgu("Toplam kalan",tl(c.toplam_kalan)+" $","ciro − vergi − reklam − kargo")}
    ${kart("Eşleşen mağaza",c.eslesen_magaza+"/"+c.toplam_magaza,"eşleşme oranı %"+c.match_rate)}
    ${kart("Otomatik hesaplanan",c.otomatik_kolon+" kolon","ShipStation gerçeğinden")}
    ${kart("Manuel giriş",c.manuel_kolon+" kolon","reklam, vergi, ilave ödeme")}
    ${kart("Amazon (rapor dışı)",tl(c.amazon_siparis)+" sipariş","ayrı listelenir")}`;
  $("#ceo-serit").innerHTML=`⏱ Tahmini zaman tasarrufu: <b style="margin-left:6px">${c.zaman_tasarrufu}</b>`;
  raporTablo(s);
  const uk=urunKaynagi();
  $("#urun-notu").innerHTML = uk==="shipstation"
    ? `Ürün adetleri (${s.urun_basliklari.length} kolon) <b>ShipStation kalem verisinden otomatik SKU sınıflandırma</b> ile dolduruldu (Diğer Ürün dahil).`
    : `Ürün adetleri (${s.urun_basliklari.length} kolon) <b>form beyanından</b> yazıldı. Kalem detayı yüklersen otomatik SKU sınıflandırmaya geçebilirsin.`;
  $("#amazon-notu").innerHTML = s.amazon&&s.amazon.length
    ? `<div class="uyari">Rapor dışı (Amazon): ${s.amazon.map(a=>`${a.magaza} (${tl(a.siparis)} sipariş)`).join(" · ")}</div>` : "";
  if(sonAnaliz&&sonAnaliz.kalem_var){ $("#siparis-icerik-blok").classList.remove("gizli"); siparisIcerikYukle(""); }
  else { $("#siparis-icerik-blok").classList.add("gizli"); }
}
async function siparisIcerikYukle(ara){
  const j=await api("/api/siparis_icerik",{ara:ara||""},"Sipariş içerikleri çözülüyor…");
  if(!j)return;
  $("#si-ozet").textContent=`${j.coklu} çok-ürünlü, ${j.tekil} tekil sipariş (toplam ${j.toplam_siparis}).`;
  let h="<tr><th>Sipariş No</th><th>Mağaza</th><th>Adet</th><th>İçindekiler</th></tr>";
  j.kayitlar.forEach(k=>{
    const items=k.items.map(it=>`${it.adet}× ${it.ad} <span class="notmetin">[${it.kategori}]</span>`).join("<br>");
    h+=`<tr><td class="ad">${k.order_no}</td><td>${k.store}</td><td>${tl(k.toplam_adet)}</td><td style="text-align:left;white-space:normal">${items}</td></tr>`;
  });
  $("#t-siparis-icerik").innerHTML=h;
}
$("#btn-si-ara")&&$("#btn-si-ara").addEventListener("click",()=>siparisIcerikYukle($("#si-ara").value));
$("#si-ara")&&$("#si-ara").addEventListener("keydown",e=>{if(e.key==="Enter")siparisIcerikYukle($("#si-ara").value);});
function kart(k,v,s){return `<div class="kart"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s||""}</div></div>`;}
function kartVurgu(k,v,s){return `<div class="kart vurgu"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s||""}</div></div>`;}
function raporTablo(s){
  const C=[["magaza","Mağaza"],["ciro","Ciro"],["pb_ciro","Parça başı ciro"],["vergi","Vergi"],["reklam","Reklam"],
    ["kargo_musteri","Kargo müşteri"],["kargo_pb_odenen","Krg pb ödenen"],["kargo_pb_kalan","Krg pb kalan"],
    ["kargo","Kargo"],["adet","Parça adedi"],["ilave_odeme","İlave ödeme"],["kalan","Kalan"],
    ["yuzde_reklam","%Reklam"],["yuzde_vergi","%Vergi"],["pb_kalan","Parça başı kalan"],["upgrade","Upgrade"]];
  const ondalik=new Set(["pb_ciro","kargo_pb_odenen","kargo_pb_kalan","pb_kalan"]);
  const yuzde=new Set(["yuzde_reklam","yuzde_vergi"]);
  const tamsayi=new Set(["adet","upgrade"]);
  const fmt=(k,v)=>k==="magaza"?v:yuzde.has(k)?pct(v):ondalik.has(k)?tl2(v):tamsayi.has(k)?tl(v):tl(v);
  let h="<tr>";C.forEach(([,et])=>h+=`<th>${et}</th>`);h+="</tr>";
  s.tablo.forEach(row=>{h+="<tr>";C.forEach(([k])=>{h+=`<td class="${k==='magaza'?'ad':''}">${fmt(k,row[k])}</td>`;});h+="</tr>";});
  const t=s.toplam;
  h+='<tr class="toplam"><td>TOPLAM</td>';
  C.slice(1).forEach(([k])=>{
    let v = (k in t)?t[k]:null;
    if(["pb_ciro","kargo_pb_odenen","kargo_pb_kalan","pb_kalan"].includes(k)) v=null; // toplamda anlamsız
    h+=`<td>${v==null?"":fmt(k,v)}</td>`;
  });
  h+="</tr>";
  $("#t-rapor").innerHTML=h;
}
$("#btn-indir").addEventListener("click",()=>{ window.location="/api/rapor/indir"; });

durumYukle();
