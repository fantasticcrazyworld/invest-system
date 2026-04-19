const DATA_URL="https://raw.githubusercontent.com/yangpinggaoye15-dotcom/invest-data/main/screen_full_results.json";const CLAUDE_API="/api/claude";const GEMINI_API="/api/gemini";let allData=[],rsOn=false,ytdOn=false,curTab="news";const CL=["Price > SMA150/200","SMA150 > SMA200","SMA200 上昇中","SMA50 > SMA150/200","Price > SMA50","Price > 52wLow x1.25","Price > 52wHigh x0.75"];function gk(k){return localStorage.getItem(k)||""}function sk(k,v){localStorage.setItem(k,v)}async function loadData(){try{const r=await fetch(DATA_URL+"?t="+Date.now());if(!r.ok)throw new Error("HTTP "+r.status);const j=await r.json();const m=j["__meta__"]||{};allData=Object.entries(j).filter(([k,v])=>k!=="__meta__"&&!v.error&&v.passed!==undefined).map(([k,v])=>v);const p=allData.filter(x=>x.passed).length,pf=allData.filter(x=>x.score==="7/7").length,nh=allData.filter(x=>x.passed&&x.high52&&x.price>=x.high52*0.95).length;document.getElementById("m-total").textContent=(m.total||allData.length).toLocaleString();document.getElementById("m-pass").textContent=p.toLocaleString();document.getElementById("m-perfect").textContent=pf.toLocaleString();document.getElementById("m-nearhigh").textContent=nh.toLocaleString();document.getElementById("updated").textContent="更新: "+(m.finished_at?m.finished_at.replace("T"," ").slice(0,16):"-");applyFilters();saveHealthSnapshot();renderHealthChart();}catch(e){document.getElementById("screening-content").innerHTML='<div class="error-box">読み込み失敗: '+e.message+"</div>";}}function getKnowledge(code){
  // Merge: file-based (from knowledge_data.json) + localStorage buffer
  var fileKl=(window._knowledge||{})[code]||[];
  var localKl=[];
  try{localKl=JSON.parse(localStorage.getItem("knowledge_"+code)||"[]");}catch(e){}
  return fileKl.concat(localKl);
}
function saveKnowledge(code){
  var r=document.getElementById("ai-result");
  if(!r||!r.textContent){alert("保存する回答がありません");return;}
  // Save to localStorage as buffer (MCP export_knowledge で永続化)
  var kl=[];
  try{kl=JSON.parse(localStorage.getItem("knowledge_"+code)||"[]");}catch(e){}
  kl.unshift({date:new Date().toISOString().slice(0,10),category:curTab,text:r.textContent.slice(0,500)});
  if(kl.length>10)kl=kl.slice(0,10);
  localStorage.setItem("knowledge_"+code,JSON.stringify(kl));
  alert("ナレッジに保存しました ("+kl.length+"件)\n※ Claude Desktopで export_knowledge を実行すると永続化されます");
}
function getKnowledgeContext(code){
  var kl=getKnowledge(code);
  if(!kl.length)return"";
  return"\n\n【過去のナレッジ】\n"+kl.slice(0,5).map(function(k){return"["+k.date+"] "+k.text.slice(0,200);}).join("\n");
}
var factRule="\n\n【重要ルール】\n1. 回答は「事実」と「推測・見解」を明確に分けて記述してください\n2. 事実には必ず情報源（出典名、URL等）を記載してください\n3. 推測には「推測:」と明記してください\n4. 情報源はHTTPSのサイトのみを参照してください。HTTPのサイトは絶対に参照しないでください\n5. 情報源URLがある場合は末尾に【出典】として列挙してください";
function closeDetail(){document.getElementById("detail-panel").classList.remove("open");document.getElementById("overlay").classList.remove("show");}function showPage(n,btn){document.querySelectorAll(".page").forEach(p=>p.classList.remove("active"));document.querySelectorAll(".nav-btn").forEach(b=>b.classList.remove("active"));document.getElementById("page-"+n).classList.add("active");btn.classList.add("active");if(n==='simulation')initSimPage();if(n==='kpi')initKpiPage();if(n==='report')initReportPage();}
const REPORT_BASE="https://raw.githubusercontent.com/yangpinggaoye15-dotcom/invest-data/main/reports/";
let currentReportTeam='latest_report',currentReportDate='',reportPageInited=false;
function mdToHtml(md){
  if(!md)return'';
  return md
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/^#{3}\s(.+)$/gm,'<h3>$1</h3>')
    .replace(/^#{2}\s(.+)$/gm,'<h2>$1</h2>')
    .replace(/^#{1}\s(.+)$/gm,'<h1>$1</h1>')
    .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/^\|(.+)\|$/gm,function(_,r){const cells=r.split('|');return'<tr>'+cells.map(c=>c.trim().match(/^[-:]+$/)?'':'<td>'+c.trim()+'</td>').filter(c=>c!='').join('')+'</tr>';})
    .replace(/(<tr>.*<\/tr>\n?)+/g,'<table>$&</table>')
    .replace(/^[-*]\s(.+)$/gm,'<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g,'<ul>$&</ul>')
    .replace(/^>\s(.+)$/gm,'<blockquote>$1</blockquote>')
    .replace(/\[事実\]/g,'<span style="background:#0d2d15;color:#3fb950;padding:1px 6px;border-radius:3px;font-size:11px">[事実]</span>')
    .replace(/\[AI分析\]/g,'<span style="background:#1a1a2e;color:#79c0ff;padding:1px 6px;border-radius:3px;font-size:11px">[AI分析]</span>')
    .replace(/\n\n/g,'</p><p>')
    .replace(/^([^<\n].+)$/gm,'<p>$1</p>');
}
async function loadKpiLog(){const r=await fetch(KPI_LOG_URL+'?t='+Date.now());if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}
async function loadSimLog(){
  if(simLog)return simLog;
  const r=await fetch(SIM_URL+"?t="+Date.now());
  if(!r.ok)throw new Error("HTTP "+r.status);
  simLog=await r.json();
  return simLog;
}
async function loadChartData(){try{const r=await fetch(CHART_DATA_URL+"?t="+Date.now());if(r.ok)window._chartData=await r.json();}catch(e){}}
async function loadPatternData(){try{const r=await fetch(PATTERN_DATA_URL+"?t="+Date.now());if(r.ok){window._patternData=await r.json();applyFilters();}}catch(e){}}
async function loadWatchlist(){try{const r=await fetch(WATCHLIST_URL+"?t="+Date.now());if(r.ok){window._watchlist=await r.json();renderWatchlist();}}catch(e){document.getElementById("wl-content").innerHTML='<div class="loading"><div class="loading-text">監視リストなし</div></div>';}}
async function loadPortfolio(){try{const r=await fetch(PORTFOLIO_URL+"?t="+Date.now());if(r.ok){window._portfolio=await r.json();renderPortfolio();}}catch(e){document.getElementById("pf-content").innerHTML='<div class="loading"><div class="loading-text">ポートフォリオなし</div></div>';}}

// Timeframe switching
var curTF='daily';
function getMemo(code){return localStorage.getItem("memo_"+code)||"";}
function saveMemo(code,text){if(text.trim())localStorage.setItem("memo_"+code,text);else localStorage.removeItem("memo_"+code);}

// Watchlist rendering
async function loadFinsData(){try{const r=await fetch(FINS_DATA_URL+"?t="+Date.now());if(r.ok)window._finsData=await r.json();}catch(e){}}
async function loadTimeline(){try{const r=await fetch(TIMELINE_URL+"?t="+Date.now());if(r.ok)window._timeline=await r.json();}catch(e){}}
async function loadKnowledge(){try{const r=await fetch(KNOWLEDGE_URL+"?t="+Date.now());if(r.ok)window._knowledge=await r.json();}catch(e){}}
async function loadIndexData(){try{const r=await fetch(INDEX_DATA_URL+"?t="+Date.now());if(r.ok){window._indexData=await r.json();renderIndexChart();renderMarketTrend();}}catch(e){}}

// Deduplicate FY records: keep latest (by date) record per fiscal year
function dedupFY(arr){
  var sorted=arr.slice().sort(function(a,b){return a.fy.localeCompare(b.fy)||(a.date||'').localeCompare(b.date||'');});
  var map={};
  sorted.forEach(function(r){
    var key=r.fy;
    if(!map[key]||(!map[key].sales&&r.sales)||((r.date||'')>=(map[key].date||'')&&(r.sales||r.eps))){map[key]=r;}
  });
  return Object.keys(map).sort().map(function(k){return map[k];});
}
function fmtYen(v){
  if(v==null)return'-';
  var abs=Math.abs(v);
  var sign=v<0?'-':'';
  if(abs>=1e12)return sign+(abs/1e12).toFixed(1)+'兆';
  if(abs>=1e8)return sign+(abs/1e8).toFixed(0)+'億';
  if(abs>=1e4)return sign+(abs/1e4).toFixed(0)+'万';
  return sign+Number(Math.round(v)).toLocaleString();
}
function fmtNum(v,d){return v==null?'-':Number(v).toFixed(d||1);}
function growthClass(cur,prev){if(cur==null||prev==null||prev==0)return'';return cur>prev?'pos':'neg';}

function getLocalWL(){try{return JSON.parse(localStorage.getItem('wl_local')||'{}');}catch(e){return {};}}
function saveLocalWL(d){localStorage.setItem('wl_local',JSON.stringify(d));}
function getLocalPF(){try{return JSON.parse(localStorage.getItem('pf_local')||'{}');}catch(e){return {};}}
function saveLocalPF(d){localStorage.setItem('pf_local',JSON.stringify(d));}

function analyzeVolume(ohlcv){
  var el=document.getElementById('vol-analysis');
  if(!ohlcv||ohlcv.length<21){el.innerHTML='';return;}
  var markers=[];var accDays=0,distDays=0;
  for(var i=20;i<ohlcv.length;i++){
    var sum=0;for(var j=i-20;j<i;j++)sum+=ohlcv[j].volume;
    var avg=sum/20;
    var d=ohlcv[i];
    if(d.volume>avg*2){
      if(d.close>d.open){accDays++;markers.push({time:d.time,position:'belowBar',color:'#3fb950',shape:'arrowUp',text:'集'});}
      else{distDays++;markers.push({time:d.time,position:'aboveBar',color:'#f85149',shape:'arrowDown',text:'散'});}
    }
  }
  // Limit markers to last 60 days to avoid clutter
  var recent=markers.slice(-30);
  if(candleSeries&&recent.length)candleSeries.setMarkers(recent);
  // Count only last 60 trading days
  var last60=ohlcv.slice(-60);var accR=0,distR=0;
  for(var k=0;k<last60.length;k++){
    var sum2=0,cnt=0;for(var m=Math.max(0,k-20);m<k;m++){sum2+=last60[m].volume;cnt++;}
    if(cnt<10)continue;var avg2=sum2/cnt;
    if(last60[k].volume>avg2*2){if(last60[k].close>last60[k].open)accR++;else distR++;}
  }
  el.innerHTML='<span class="vol-acc">▲ 集積(60日): <b>'+accR+'日</b></span><span class="vol-dist">▼ 分散(60日): <b>'+distR+'日</b></span><span style="color:#8b949e">| 判定: '+(accR>distR?'<span style="color:#3fb950">買い優勢</span>':accR<distR?'<span style="color:#f85149">売り優勢</span>':'中立')+'</span>';
}

// === Feature: Market Health (Pass Count Trend) ===
function codeSector(code){
  var n=parseInt(code);
  if(n<1500)return'水産・建設';if(n<2000)return'鉱業・石油';if(n<2500)return'食品';
  if(n<3000)return'繊維・紙';if(n<3500)return'化学';if(n<4000)return'医薬・ゴム';
  if(n<4500)return'サービス・情報';if(n<5000)return'電気・ガス';if(n<5500)return'鉄鋼・金属';
  if(n<6000)return'機械';if(n<6500)return'電機';if(n<7000)return'精密・その他製造';
  if(n<7500)return'自動車・輸送';if(n<8000)return'商社・小売';if(n<8500)return'銀行・証券';
  if(n<9000)return'保険・不動産';if(n<9500)return'運輸・通信';return'電力・サービス';
}
