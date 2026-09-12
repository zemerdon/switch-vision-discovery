let creditsV25Ctx=null;
let creditsV25Dpr=1;
let creditsV25Pieces=[];
let creditsV25BuildTotal=0;
let creditsV25StartTime=0;
let creditsV25Timers=[];
let creditsV25ResizeTimer=null;
let creditsV25RunToken=0;

function clearCreditsV25Timers(){
  creditsV25Timers.forEach(clearTimeout);
  creditsV25Timers=[];
  if(creditsAnimationFrame){cancelAnimationFrame(creditsAnimationFrame);creditsAnimationFrame=null}
  if(creditsV25ResizeTimer){clearTimeout(creditsV25ResizeTimer);creditsV25ResizeTimer=null}
}
function resizeCreditsV25Canvas(){
  const card=$('creditsCard'),canvas=$('creditsMatrix');
  if(!card||!canvas)return false;
  const rect=card.getBoundingClientRect();
  creditsV25Dpr=Math.min(window.devicePixelRatio||1,2);
  canvas.width=Math.max(1,Math.floor(rect.width*creditsV25Dpr));
  canvas.height=Math.max(1,Math.floor(rect.height*creditsV25Dpr));
  canvas.style.width=rect.width+'px';
  canvas.style.height=rect.height+'px';
  creditsV25Ctx=canvas.getContext('2d');
  if(!creditsV25Ctx)return false;
  creditsV25Ctx.setTransform(creditsV25Dpr,0,0,creditsV25Dpr,0,0);
  return true;
}
function copyCreditsV25ComputedStylesDeep(source,clone){
  if(source.nodeType!==Node.ELEMENT_NODE||clone.nodeType!==Node.ELEMENT_NODE)return;
  const computed=getComputedStyle(source);
  for(const prop of computed){
    if(prop==='animation'||prop.startsWith('animation-')||prop==='transition'||prop.startsWith('transition-'))continue;
    try{clone.style.setProperty(prop,computed.getPropertyValue(prop),computed.getPropertyPriority(prop))}catch(_e){}
  }
  const sourceChildren=[...source.children],cloneChildren=[...clone.children];
  for(let i=0;i<sourceChildren.length;i++)if(cloneChildren[i])copyCreditsV25ComputedStylesDeep(sourceChildren[i],cloneChildren[i]);
}
function makeCreditsV25SnapshotDataURL(){
  const source=$('creditsBuildSource');
  if(!source)throw new Error('Credits build source is unavailable');
  const rect=source.getBoundingClientRect(),w=rect.width,h=rect.height;
  const renderScale=Math.min(window.devicePixelRatio||1,2);
  const clone=source.cloneNode(true);
  copyCreditsV25ComputedStylesDeep(source,clone);
  clone.style.opacity='1';clone.style.visibility='visible';clone.style.animation='none';clone.style.transition='none';clone.style.transform='none';
  clone.style.position='relative';clone.style.left='0';clone.style.top='0';clone.style.width=`${w}px`;clone.style.height=`${h}px`;clone.style.margin='0';
  for(const el of clone.querySelectorAll('*')){el.style.animation='none';el.style.transition='none'}
  const wrapper=document.createElement('div');
  wrapper.setAttribute('xmlns','http://www.w3.org/1999/xhtml');
  wrapper.style.width=`${w}px`;wrapper.style.height=`${h}px`;wrapper.style.margin='0';wrapper.style.padding='0';wrapper.style.overflow='hidden';
  wrapper.appendChild(clone);
  const serialized=new XMLSerializer().serializeToString(wrapper);
  const pixelW=Math.max(1,Math.round(w*renderScale)),pixelH=Math.max(1,Math.round(h*renderScale));
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${pixelW}" height="${pixelH}" viewBox="0 0 ${w} ${h}"><foreignObject x="0" y="0" width="${w}" height="${h}">${serialized}</foreignObject></svg>`;
  return {url:`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`,w,h,renderScale,pixelW,pixelH};
}
function loadCreditsV25Image(url){return new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=reject;img.src=url})}
function creditsV25EaseOutCubic(t){return 1-Math.pow(1-t,3)}
async function prepareCreditsV25Pieces(){
  if(!resizeCreditsV25Canvas())throw new Error('Credits canvas is unavailable');
  const card=$('creditsCard'),source=$('creditsBuildSource');
  if(!card||!source)throw new Error('Credits build geometry is unavailable');
  const snap=makeCreditsV25SnapshotDataURL(),img=await loadCreditsV25Image(snap.url);
  const cardRect=card.getBoundingClientRect(),sourceRect=source.getBoundingClientRect();
  const offsetX=sourceRect.left-cardRect.left,offsetY=sourceRect.top-cardRect.top;
  const buffer=document.createElement('canvas');buffer.width=snap.pixelW;buffer.height=snap.pixelH;
  const bctx=buffer.getContext('2d',{willReadFrequently:true});if(!bctx)throw new Error('Credits build buffer is unavailable');
  bctx.drawImage(img,0,0,snap.pixelW,snap.pixelH);
  const imageData=bctx.getImageData(0,0,snap.pixelW,snap.pixelH).data;
  creditsV25Pieces=[];
  const tile=4,cols=Math.ceil(snap.w/tile),rows=Math.ceil(snap.h/tile),s=snap.renderScale;
  for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){
    const dx=c*tile,dy=r*tile,dw=Math.min(tile,snap.w-dx),dh=Math.min(tile,snap.h-dy);if(dw<=0||dh<=0)continue;
    const sx=Math.max(0,Math.floor(dx*s)),sy=Math.max(0,Math.floor(dy*s));
    const sw=Math.max(1,Math.min(snap.pixelW-sx,Math.ceil(dw*s))),sh=Math.max(1,Math.min(snap.pixelH-sy,Math.ceil(dh*s)));
    let maxAlpha=0;
    outer:for(let py=sy;py<sy+sh;py++)for(let px=sx;px<sx+sw;px++){const a=imageData[(py*snap.pixelW+px)*4+3];if(a>maxAlpha)maxAlpha=a;if(maxAlpha>8)break outer}
    if(maxAlpha<3)continue;
    const worldX=offsetX+dx,worldY=offsetY+dy,visualRow=rows-1-r;
    creditsV25Pieces.push({sx,sy,sw,sh,tx:worldX,ty:worldY,dw,dh,x:worldX+(Math.random()*8-4),y:-70-Math.random()*170-visualRow*2.1,delay:visualRow*18+Math.floor(c/3)*5+Math.random()*55,duration:280+Math.random()*130});
  }
  creditsV25BuildTotal=(creditsV25Pieces.length?Math.max(...creditsV25Pieces.map(p=>p.delay+p.duration)):0)+500;
  return {buffer};
}
function drawCreditsV25Pieces(buffer,now){
  const canvas=$('creditsMatrix');if(!creditsV25Ctx||!canvas)return;
  const card=$('creditsCard'),rect=card?.getBoundingClientRect();
  creditsV25Ctx.clearRect(0,0,rect?.width||canvas.width,rect?.height||canvas.height);
  for(const p of creditsV25Pieces){
    const t=now-p.delay;if(t<0)continue;
    const k=t>=p.duration?1:creditsV25EaseOutCubic(Math.max(0,Math.min(1,t/p.duration)));
    creditsV25Ctx.globalAlpha=.1+.9*k;
    creditsV25Ctx.drawImage(buffer,p.sx,p.sy,p.sw,p.sh,p.x+(p.tx-p.x)*k,p.y+(p.ty-p.y)*k,p.dw,p.dh);
  }
  creditsV25Ctx.globalAlpha=1;
}
function animateCreditsV25Pieces(buffer,token){
  creditsV25StartTime=performance.now();
  function frame(ts){
    if(token!==creditsV25RunToken||currentView!=='credits'){creditsAnimationFrame=null;return}
    const elapsed=ts-creditsV25StartTime;drawCreditsV25Pieces(buffer,elapsed);
    const prog=Math.min(1,elapsed/Math.max(1,creditsV25BuildTotal));$('creditsProgress').style.width=`${Math.round(prog*100)}%`;
    if(elapsed<creditsV25BuildTotal)creditsAnimationFrame=requestAnimationFrame(frame);
    else{$('creditsProgress').style.width='100%';creditsAnimationFrame=null;finishCreditsV25Build(token)}
  }
  creditsAnimationFrame=requestAnimationFrame(frame);
}
function moveCreditsV25SoftSpotlight(){
  const card=$('creditsCard');if(!card||currentView!=='credits')return;
  card.style.setProperty('--soft-x',`${14+Math.random()*72}%`);card.style.setProperty('--soft-y',`${-330+Math.random()*150}px`);
  const t=setTimeout(moveCreditsV25SoftSpotlight,7500+Math.random()*5000);creditsV25Timers.push(t);
}
function moveCreditsV25NarrowSpotlight(){
  const card=$('creditsCard');if(!card||currentView!=='credits')return;
  card.style.setProperty('--narrow-x',`${10+Math.random()*80}%`);card.style.setProperty('--narrow-angle',`${-18+Math.random()*36}deg`);
  const t=setTimeout(moveCreditsV25NarrowSpotlight,6333+Math.random()*3500);creditsV25Timers.push(t);
}
function moveCreditsV25SweepLight(){
  const sweep=$('creditsSweepLight');if(!sweep||currentView!=='credits')return;
  const duration=4.3+Math.random()*1.8,angle=104+Math.random()*26,reverse=Math.random()>.5;
  const start=reverse?(48+Math.random()*14):(-62+Math.random()*14),end=reverse?(-62+Math.random()*14):(48+Math.random()*14);
  sweep.style.setProperty('--sweep-duration',`${duration}s`);sweep.style.setProperty('--sweep-angle',`${angle}deg`);sweep.style.setProperty('--sweep-start',`${start}%`);sweep.style.setProperty('--sweep-end',`${end}%`);
  sweep.classList.remove('sweep-run');void sweep.offsetWidth;sweep.classList.add('sweep-run');
  const t=setTimeout(moveCreditsV25SweepLight,2000+Math.random()*3500);creditsV25Timers.push(t);
}
function startCreditsV25Lights(){moveCreditsV25SoftSpotlight();moveCreditsV25NarrowSpotlight();moveCreditsV25SweepLight()}
function finishCreditsV25Build(token=creditsV25RunToken){
  if(token!==creditsV25RunToken)return;
  const card=$('creditsCard'),track=$('creditsRollTrack'),canvas=$('creditsMatrix');if(!card||!track||!canvas)return;
  card.classList.add('credits-settled');
  track.style.opacity='1';
  canvas.style.display='none';
  card.classList.remove('credits-matrix-active');
  const t=setTimeout(()=>{if(token===creditsV25RunToken&&currentView==='credits')track.classList.add('credits-rolling')},1600);
  creditsV25Timers.push(t);
}
function resetCreditsV25(){
  creditsV25RunToken+=1;clearCreditsV25Timers();
  const card=$('creditsCard'),track=$('creditsRollTrack'),canvas=$('creditsMatrix'),progress=$('creditsProgress'),sweep=$('creditsSweepLight');
  if(card){card.classList.remove('credits-settled');card.classList.add('credits-matrix-active')}
  if(track){track.classList.remove('credits-rolling');track.style.opacity='0'}
  if(progress)progress.style.width='0';
  if(canvas){canvas.style.display='block';if(creditsV25Ctx){const rect=card?.getBoundingClientRect();creditsV25Ctx.clearRect(0,0,rect?.width||canvas.width,rect?.height||canvas.height)}}
  if(sweep)sweep.classList.remove('sweep-run');
}
async function startCreditsV25Animation(){
  resetCreditsV25();const token=creditsV25RunToken;startCreditsV25Lights();
  const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
  if(reduced){const card=$('creditsCard'),track=$('creditsRollTrack'),canvas=$('creditsMatrix'),progress=$('creditsProgress');if(card){card.classList.remove('credits-matrix-active');card.classList.add('credits-settled')}if(track)track.style.opacity='1';if(canvas)canvas.style.display='none';if(progress)progress.style.width='100%';return}
  try{const {buffer}=await prepareCreditsV25Pieces();if(token!==creditsV25RunToken||currentView!=='credits')return;animateCreditsV25Pieces(buffer,token)}
  catch(err){console.error(err);if(token===creditsV25RunToken&&currentView==='credits')finishCreditsV25Build(token)}
}
window.addEventListener('resize',()=>{
  if(currentView!=='credits')return;if(creditsV25ResizeTimer)clearTimeout(creditsV25ResizeTimer);
  creditsV25ResizeTimer=setTimeout(()=>{creditsV25ResizeTimer=null;startCreditsV25Animation()},160)
});
