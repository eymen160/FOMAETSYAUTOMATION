const $=s=>document.querySelector(s);
$("#form").addEventListener("submit",async e=>{
  e.preventDefault();
  $("#btn").disabled=true; $("#hata").style.display="none";
  try{
    const r=await fetch("/giris",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kullanici:$("#kullanici").value,sifre:$("#sifre").value})});
    const j=await r.json();
    if(r.ok&&j.tamam){ window.location="/"; return; }
    $("#hata").textContent=j.hata||"Giriş başarısız."; $("#hata").style.display="block";
  }catch(err){ $("#hata").textContent="Sunucuya ulaşılamadı."; $("#hata").style.display="block"; }
  finally{ $("#btn").disabled=false; }
});
