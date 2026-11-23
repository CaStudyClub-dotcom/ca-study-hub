const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); try { tg.setHeaderColor("#0b1220"); tg.setBackgroundColor("#f6f8fc"); } catch(e) {} }

const grid=document.getElementById("subject-grid"), list=document.getElementById("lecture-list");
const heading=document.getElementById("lecture-heading"), search=document.getElementById("search");
const total=document.getElementById("total-lectures");
let selected=COURSE_DATA[0]?.id;
const countLectures=()=>COURSE_DATA.reduce((n,s)=>n+(s.lectures?.length||0),0);
total.textContent=String(countLectures()).padStart(2,"0");

function renderSubjects(){
  grid.innerHTML="";
  COURSE_DATA.forEach((s,i)=>{
    const b=document.createElement("button");
    b.className=`subject-card ${s.theme}`;
    b.innerHTML=`<div class="subject-top"><span class="subject-icon">${s.icon}</span><span class="subject-number">SUBJECT 0${i+1}</span></div><strong>${s.name}</strong><small>${s.description}</small><span class="arrow">↗</span>`;
    b.addEventListener("click",()=>{selected=s.id;renderSubjects();loadLectureCatalogue();document.querySelector(".lecture-block").scrollIntoView({behavior:"smooth",block:"start"});});
    grid.appendChild(b);
  });
}

let serverLectures=[];
let accessActive=false;
let accessRemaining=0;
let sendingLecture=false;
async function loadLectureCatalogue(){
  if(!tg?.initData){list.innerHTML='<div class="empty-state">Open this app from the Telegram bot to load your lectures.</div>';return;}
  try{
    const r=await fetch("https://ca-study-hub.onrender.com/api/lectures/list",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({initData:tg.initData})});
    const d=await r.json(); if(!r.ok)throw new Error(d.message||"Could not load lectures");
    serverLectures=d.lectures||[];
    total.textContent=String(serverLectures.length).padStart(2,"0");
    renderLectures();
  }catch(e){list.innerHTML='<div class="empty-state">'+e.message+'</div>';}
}
function renderLectures(){
  const s=COURSE_DATA.find(x=>x.id===selected); if(!s)return;
  heading.textContent=s.name+" lectures"; list.innerHTML="";
  const q=(search.value||"").trim().toLowerCase();
  const aliases={accounts:["ACCOUNTS","ACCOUNTANCY"],law:["LAW","BUSINESS LAWS"],qa:["QA","QUANTITATIVE APTITUDE"],economics:["ECONOMICS","BUSINESS ECONOMICS"]};
  const rows=serverLectures.filter(l=>(aliases[s.id]||[]).includes(String(l.subject||"").toUpperCase()) &&
    (String(l.chapter_name||"").toLowerCase().includes(q)||("lecture "+l.lecture_number).includes(q)||String(l.caption||"").toLowerCase().includes(q)));
  if(!rows.length){list.innerHTML='<div class="empty-state">No uploaded lectures for this subject yet.</div>';return;}
  rows.forEach(l=>{
    const card=document.createElement("article");card.className="lecture-card";
    const thumb=document.createElement("div");thumb.className="lecture-thumb";thumb.textContent="▶";
    const meta=document.createElement("div");meta.className="lecture-meta";
    const title=document.createElement("strong");title.textContent="Lecture "+l.lecture_number;
    const small=document.createElement("small");small.textContent=l.chapter_name;
    meta.append(title,small);
    const btn=document.createElement("button");btn.className="watch-button";
    btn.textContent=sendingLecture?"PLEASE WAIT":(accessActive&&accessRemaining>0?"SEND TO BOT":"LOCKED");
    btn.disabled=!accessActive||accessRemaining<=0||sendingLecture;
    btn.addEventListener("click",async()=>{
      if(!accessActive){accessMessage.textContent="Unlock your 12-hour access first.";return;}
      sendingLecture=true;renderLectures();
      try{
        const r=await fetch("https://ca-study-hub.onrender.com/api/lectures/send",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({initData:tg.initData,lecture_id:l.id})});
        const d=await r.json();if(!r.ok)throw new Error(d.message||"Could not send lecture");
        accessMessage.textContent="✅ Lecture sent to your Telegram bot chat!";
        await refreshAccess();
      }catch(e){accessMessage.textContent=e.message;}
      finally{sendingLecture=false;renderLectures();}
    });
    card.append(thumb,meta,btn);list.appendChild(card);
  });
}

search.addEventListener("input",renderLectures);
document.getElementById("all-lectures").addEventListener("click",()=>{search.value="";selected=COURSE_DATA[0].id;renderSubjects();renderLectures();});
document.querySelectorAll(".nav-item").forEach(btn=>btn.addEventListener("click",()=>{
  document.querySelectorAll(".nav-item").forEach(x=>x.classList.remove("active"));btn.classList.add("active");
  const tab=btn.dataset.tab;
  if(tab==="home")window.scrollTo({top:0,behavior:"smooth"});
  else if(tab==="courses")document.querySelector(".section-block").scrollIntoView({behavior:"smooth"});
  else if(tab==="notes")alert("Notes library is coming in the next build.");
  else if(tab==="profile")alert("Student profile and progress tracking will be added in the next build.");
}));
document.getElementById("profile-button").addEventListener("click",()=>alert("Student profile will be added in the next build."));
renderSubjects();renderLectures();

/* Telegram Mini App access: identity is verified by the backend from signed initData. */
const accessMessage=document.getElementById("access-message");
const unlockButton=document.getElementById("unlock-button");
const accessDetails=document.getElementById("access-details");
const accessExpiry=document.getElementById("access-expiry");
const accessRemaining=document.getElementById("access-remaining");
const ACCESS_API="https://ca-study-hub.onrender.com/api/access";
async function accessRequest(action){
  if(!tg?.initData) throw new Error("Please open this app from the CA Study Hub Telegram bot.");
  const response=await fetch(ACCESS_API+"/"+action,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({initData:tg.initData})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok) throw new Error(data.message||"Could not check access. Please try again.");
  return data;
}
function showAccess(data){
  const active=!!data.active;
  document.getElementById("access-icon").textContent=active?"🔓":"🔒";
  accessMessage.textContent=data.message||(active?"Your study pass is active.":"Unlock your study pass to start learning.");
  accessDetails.hidden=!active;
  if(active){accessExpiry.textContent="Expires: "+new Date(data.expires_at).toLocaleString();accessRemaining.textContent=data.remaining+" / 10 lectures left";}
  unlockButton.disabled=false;unlockButton.textContent=active?"Access active ✓":"Unlock free access";unlockButton.classList.toggle("is-active",active);
}
async function refreshAccess(){
  if(!tg?.initData){accessMessage.textContent="Open this Mini App from the Telegram bot to verify your account.";unlockButton.textContent="Open via Telegram";unlockButton.disabled=true;return;}
  try{const data=await accessRequest("status");showAccess(data);accessActive=!!data.active;accessRemaining=Number(data.remaining||0);renderLectures();}
  catch(e){accessMessage.textContent=e.message;unlockButton.textContent="Try again";unlockButton.disabled=false;}
}
unlockButton.addEventListener("click",async()=>{unlockButton.disabled=true;unlockButton.textContent="Activating…";try{const data=await accessRequest("unlock");showAccess(data);accessActive=!!data.active;accessRemaining=Number(data.remaining||0);renderLectures();}catch(e){accessMessage.textContent=e.message;unlockButton.disabled=false;unlockButton.textContent="Try again";}});
refreshAccess();
