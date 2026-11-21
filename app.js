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
    b.addEventListener("click",()=>{selected=s.id;renderSubjects();renderLectures();document.querySelector(".lecture-block").scrollIntoView({behavior:"smooth",block:"start"});});
    grid.appendChild(b);
  });
}
function renderLectures(){
  const s=COURSE_DATA.find(x=>x.id===selected); if(!s)return;
  heading.textContent=s.name+" lectures"; list.innerHTML="";
  const q=(search.value||"").trim().toLowerCase();
  const rows=(s.lectures||[]).filter(l=>l.title.toLowerCase().includes(q));
  if(!rows.length){list.innerHTML='<div class="empty-state">No matching lectures yet. New classes will appear here.</div>';return;}
  rows.forEach(l=>{
    const card=document.createElement("article");card.className="lecture-card";
    const thumb=document.createElement("div");thumb.className="lecture-thumb";thumb.textContent="▶";
    const meta=document.createElement("div");meta.className="lecture-meta";
    const title=document.createElement("strong");title.textContent=l.title;
    const small=document.createElement("small");small.textContent=l.duration||"Recorded class";
    meta.append(title,small);
    const btn=document.createElement("button");btn.className="watch-button";btn.textContent=l.videoUrl?"WATCH":"COMING SOON";btn.disabled=!l.videoUrl;
    btn.addEventListener("click",()=>{if(!l.videoUrl)return;if(tg?.openLink)tg.openLink(l.videoUrl);else window.open(l.videoUrl,"_blank","noopener");});
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