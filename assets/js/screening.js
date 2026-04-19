function updateLabel(sid,lid,fn){const v=parseInt(document.getElementById(sid).value);document.getElementById(lid).textContent=fn(v);applyFilters();}function toggleRS(){rsOn=!rsOn;document.getElementById("rs-toggle").classList.toggle("on",rsOn);document.getElementById("rs-label").textContent=rsOn?"プラスのみ":"全て表示";applyFilters();}function resetFilters(){document.getElementById("search-input").value="";document.getElementById("score-slider").value=6;document.getElementById("highpct-slider").value=90;document.getElementById("score-val").textContent="6/7以上";document.getElementById("highpct-val").textContent="90%以上";document.getElementById("sort-select").value="score";rsOn=false;document.getElementById("rs-toggle").classList.remove("on");document.getElementById("rs-label").textContent="全て表示";const ci=document.getElementById("custom-input");if(ci)ci.value="";volOn=false;const vb=document.getElementById("vol-btn");if(vb){vb.style.background="none";vb.style.color="#8b949e";vb.style.borderColor="#30363d";}ytdOn=false;const yb=document.getElementById("ytd-btn");if(yb){yb.style.background="none";yb.style.color="#8b949e";yb.style.borderColor="#30363d";}patOn=false;const pb2=document.getElementById("pat-btn");if(pb2){pb2.style.background="none";pb2.style.color="#8b949e";pb2.style.borderColor="#30363d";}applyFilters();}function applyFilters(){const q=document.getElementById("search-input").value.toLowerCase();const ms=parseInt(document.getElementById("score-slider").value);const mh=parseInt(document.getElementById("highpct-slider").value)/100;const sb=document.getElementById("sort-select").value;let d=allData.filter(x=>x.passed&&parseInt(x.score)>=ms);d=d.filter(x=>!x.high52||x.price/x.high52>=mh);if(rsOn)d=d.filter(x=>x.rs26w!=null&&x.rs26w>0);if(ytdOn)d=d.filter(x=>x.ytd_high&&x.price>=x.ytd_high*0.98);if(volOn)d=d.filter(x=>x.vol_ratio!=null&&x.vol_ratio>=1.5);
if(patOn){const pp=window._patternData||{};d=d.filter(x=>pp[x.code]&&pp[x.code].patterns&&pp[x.code].patterns.length>0);}
  const customExpr=document.getElementById("custom-input")?.value?.trim();
  const errEl=document.getElementById("custom-error");
  if(customExpr){
    try{
      d=d.filter(x=>evalCustomFilter(x,customExpr));
      if(errEl){errEl.textContent="";errEl.classList.remove("show");}
    }catch(e){
      if(errEl){errEl.textContent="条件式エラー: "+e.message;errEl.classList.add("show");}
    }
  }if(q)d=d.filter(x=>(x.code||"").includes(q)||(x.name||"").toLowerCase().includes(q));d.sort((a,b)=>{if(sb==="rs26w")return(b.rs26w??-99)-(a.rs26w??-99);if(sb==="high_pct"){return(b.high52?b.price/b.high52:0)-(a.high52?a.price/a.high52:0);}if(sb==="price")return b.price-a.price;if(sb==="pattern"){const pp=window._patternData||{};const pa=(pp[a.code]?.patterns?.length)||0;const pbb=(pp[b.code]?.patterns?.length)||0;if(pbb!==pa)return pbb-pa;return parseInt(b.score)-parseInt(a.score);}return parseInt(b.score)-parseInt(a.score);});document.getElementById("display-count").textContent=d.length+"件";renderTable(d);window._fd=d;}function renderTable(data){if(!data.length){document.getElementById("screening-content").innerHTML='<div class="loading"><div class="loading-text">該当銘柄なし</div></div>';return;}let h='<div class="table-wrap"><table><thead><tr><th>コード</th><th>銘柄名</th><th>スコア</th><th>パターン</th><th>YTD高値日</th><th class="r">株価</th><th class="r">高値比</th><th class="r">前日比</th><th class="r">出来高比</th><th class="r">RS6w</th><th class="r">RS26w</th></tr></thead><tbody>';data.forEach((s,i)=>{const n=parseInt(s.score),dots=Array.from({length:7},(_,j)=>'<div class="dot '+(j<n?"on":"off")+'"></div>').join(""),hp=s.high52?(s.price/s.high52*100):null,pc=hp>=98?"pct-hot":hp>=95?"pct-warm":"pct-cold",ps=hp?hp.toFixed(1)+"%":"-",rc=v=>v==null?"rs-neu":v>0?"rs-pos":"rs-neg",rs=v=>v==null?"N/A":(v>0?"+":"")+v.toFixed(2);const cp=s.change_pct!=null?(s.change_pct>0?"+":"")+s.change_pct.toFixed(2)+"%":"N/A";
const cpClass=s.change_pct==null?"rs-neu":s.change_pct>0?"rs-pos":"rs-neg";
const vr=s.vol_ratio!=null?s.vol_ratio.toFixed(1)+"x":"N/A";
const vrClass=s.vol_ratio>=1.5?"pct-hot":s.vol_ratio>=1.0?"pct-warm":"pct-cold";
const pat=window._patternData||{};const sp=pat[s.code];const pb=sp&&sp.patterns&&sp.patterns.length?sp.patterns.map(function(p){var cls=p==="cup_with_handle"?"pattern-cup":p==="vcp"?"pattern-vcp":"pattern-flat";var lbl=p==="cup_with_handle"?"CwH":p==="vcp"?"VCP":"Flat";return'<span class="pattern-badge '+cls+'">'+lbl+'</span>';}).join(""):'<span class="pattern-none">-</span>';
const tld=window._timeline||{};const stl=tld[s.code]||{};const _ytdDateStr=stl.ytd_high_date||s.ytd_high_date;const ytdDate=_ytdDateStr?(_ytdDateStr.slice(5)):'-';const ytdNear=s.ytd_high&&s.price>=s.ytd_high*0.98;
h+='<tr onclick="showDetail('+i+')"><td class="code">'+s.code+'</td><td class="name">'+(s.name||"-")+'</td><td><div class="dots">'+dots+'</div></td><td>'+pb+'</td><td style="font-size:11px;color:'+(ytdNear?'#f0b429':'#8b949e')+'">'+ytdDate+'</td><td class="r price-val">'+Number(s.price).toLocaleString()+'</td><td class="r"><span class="'+pc+'">'+ps+'</span></td><td class="r"><span class="'+cpClass+'">'+cp+'</span></td><td class="r"><span class="'+vrClass+'">'+vr+'</span></td><td class="r"><span class="'+rc(s.rs6w)+'">'+rs(s.rs6w)+'</span></td><td class="r"><span class="'+rc(s.rs26w)+'">'+rs(s.rs26w)+'</span></td></tr>';});document.getElementById("screening-content").innerHTML=h+"</tbody></table></div>";window._fd=data;}function showDetail(idx){const s=(window._fd||[])[idx];if(!s)return;const hp=s.high52?(s.price/s.high52*100).toFixed(1)+"%":"-",rs=v=>v==null?"N/A":(v>0?"+":"")+v.toFixed(2),rc=v=>v==null?"muted":v>0?"green":"red",cc=(s.conditions||[]).map((p,i)=>'<div class="cond"><div class="cond-icon '+(p?"pass":"fail")+'">'+(p?"&#10003;":"&#10007;")+'</div><div class="cond-text">'+(CL[i]||"")+"</div></div>").join("");const dpat=window._patternData||{};const dsp=dpat[s.code];const patHtml=dsp&&dsp.patterns&&dsp.patterns.length?'<div style="margin:8px 0 12px">'+dsp.patterns.map(function(p){var cls=p==="cup_with_handle"?"pattern-cup":p==="vcp"?"pattern-vcp":"pattern-flat";var lbl=p==="cup_with_handle"?"Cup with Handle":p==="vcp"?"VCP":"Flat Base";var det=dsp.details[p]||{};var conf=det.confidence?(Math.round(det.confidence*100)+"%"):"";var reason=det.reason||"";var extra=reason||( p==="cup_with_handle"&&det.details?"Pivot: "+Number(det.details.pivot_price||0).toLocaleString()+" / 深さ: "+det.details.cup_depth_pct+"%":p==="vcp"&&det.details?"収縮: "+det.details.contractions+"回 / レンジ: "+det.details.current_range_pct+"%":p==="flat_base"&&det.details?"期間: "+det.details.length_days+"日 / レンジ: "+det.details.range_pct+"%":"");return'<div style="background:#0d1117;border-radius:8px;padding:10px 12px;margin-bottom:6px"><span class="pattern-badge '+cls+'" style="font-size:12px;padding:3px 8px">'+lbl+'</span> <span style="color:#8b949e;font-size:11px;margin-left:6px">信頼度: '+conf+'</span><div style="font-size:11px;color:#e6edf3;margin-top:4px">'+extra+'</div></div>';}).join("")+'</div>':'';
const tl2=window._timeline||{};const stl2=tl2[s.code]||{};
document.getElementById("detail-content").innerHTML='<div class="detail-title">'+(s.name||s.code)+'</div><div class="detail-code">'+s.code+" | スコア "+s.score+" | 高値比 "+hp+(stl2.ytd_high_date?' | YTD高値: '+Number(stl2.ytd_high_price||0).toLocaleString()+'円 ('+stl2.ytd_high_date+')':'')+'</div>'+patHtml+'<div class="detail-grid"><div class="detail-card"><div class="detail-card-label">株価</div><div class="detail-card-value">'+Number(s.price).toLocaleString()+'</div></div><div class="detail-card"><div class="detail-card-label">52週高値</div><div class="detail-card-value gold">'+Number(s.high52||0).toLocaleString()+'</div></div><div class="detail-card"><div class="detail-card-label">RS6w</div><div class="detail-card-value '+rc(s.rs6w)+'">'+rs(s.rs6w)+'</div></div><div class="detail-card"><div class="detail-card-label">RS26w</div><div class="detail-card-value '+rc(s.rs26w)+'">'+rs(s.rs26w)+'</div></div></div><div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px;">7条件チェック</div><div class="conditions-grid">'+cc+'</div><div class="ai-section"><div class="ai-section-title">AI&#20998;&#26512;</div><div class="ai-key-setup"><div class="ai-key-label" style="color:#3fb950">APIキー不要（Vercelプロキシで自動管理）</div><div class="ai-tabs"><div class="ai-tab active" id="tab-news" onclick="swTab(\'news\')">&#128240; ニュース</div><div class="ai-tab" id="tab-trend" onclick="swTab(\'trend\')">&#128200; 動向</div><div class="ai-tab" id="tab-judge" onclick="swTab(\'judge\')">&#127919; 判定</div><div class="ai-tab" id="tab-overview" onclick="swTab(\'overview\')">&#127970; 概要</div><div class="ai-tab" id="tab-plan" onclick="swTab(\'plan\')">&#128203; 中期計画</div><div class="ai-tab" id="tab-free" onclick="swTab(\'free\')">&#9997; 自由</div></div><div style="margin:8px 0"><textarea class="memo-area" id="ai-free-input" placeholder="自由に質問を入力..." style="height:40px;display:none"></textarea></div><div class="ai-loading" id="ai-loading"><div class="ai-spinner"></div>分析中...</div><div class="ai-error" id="ai-error"></div><div class="ai-result" id="ai-result"></div><button class="ai-btn gemini" id="btn-g" onclick="runG(\''+s.code+'\',\''+(s.name||s.code).replace(/'/g,"")+'\')">\u2736 Geminiで検索・分析</button><button class="ai-btn claude" id="btn-c" onclick="runC(\''+s.code+'\',\''+(s.name||s.code).replace(/'/g,"")+'\',\''+s.score+'\',\''+hp+'\',\''+rs(s.rs26w)+'\')">&#9670; Claudeで分析</button><div style="margin-top:6px"><button onclick="saveKnowledge(\''+s.code+'\')" style="background:none;border:1px solid #30363d;color:#8b949e;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:11px">&#128218; この回答をナレッジに保存</button></div></div><div class="ai-history"><div class="ai-history-title">&#23653;&#27508; (&#26368;&#22810;5&#20214;)</div><div id="ai-history-list"></div></div><div style="margin-top:12px;border-top:1px solid #30363d;padding-top:12px"><div class="memo-label">メモ</div><textarea class="memo-area" id="detail-memo" onchange="saveMemo(\''+s.code+'\',this.value)" placeholder="メモを入力...">'+getMemo(s.code)+'</textarea></div><button class="close-btn" style="background:#1a2a3a;border-color:#58a6ff;color:#58a6ff;margin-bottom:6px" onclick="closeDetail();openChart(\''+s.code+'\')">&#128202; ローソク足チャートを表示</button><button class="close-btn" style="background:#1a2a0d;border-color:#f0b429;color:#f0b429;margin-bottom:6px" onclick="closeDetail();openFins(\''+s.code+'\')">&#128200; 業績を表示</button><button class="close-btn" onclick="closeDetail()">&#38281;&#12376;&#12427;</button>';curTab="news";document.getElementById("detail-panel").classList.add("open");setTimeout(()=>renderAIHistory(s.code),100);document.getElementById("overlay").classList.add("show");}function swTab(t){curTab=t;document.querySelectorAll(".ai-tab").forEach(x=>x.classList.remove("active"));var tabEl=document.getElementById("tab-"+t);if(tabEl)tabEl.classList.add("active");const r=document.getElementById("ai-result");if(r){r.classList.remove("show");r.textContent="";}var fi=document.getElementById("ai-free-input");if(fi)fi.style.display=t==="free"?"block":"none";}function aiLoad(on){const l=document.getElementById("ai-loading"),g=document.getElementById("btn-g"),c=document.getElementById("btn-c");if(l)l.className="ai-loading"+(on?" show":"");if(g)g.disabled=on;if(c)c.disabled=on;if(on){const r=document.getElementById("ai-result"),e=document.getElementById("ai-error");if(r)r.classList.remove("show");if(e)e.classList.remove("show");}}function aiShow(txt,code,tab,model){const r=document.getElementById("ai-result");if(r){r.textContent=txt;r.classList.add("show");}if(code&&tab&&model){saveAIHistory(code,tab,model,txt);renderAIHistory(code);}}function aiErr(msg){const e=document.getElementById("ai-error");if(e){e.textContent=msg;e.classList.add("show");}aiLoad(false);}async function runG(code,name){const t=curTab;
  var freeText=(document.getElementById("ai-free-input")||{}).value||"";
  var knCtx=getKnowledgeContext(code);
  var prompt;
  if(t==="news")prompt="日本株「"+name+"（証券コード"+code+"）」の最新ニュースを日本語のみにて簡潔に3件要約してください。"+factRule+knCtx;
  else if(t==="trend")prompt="日本株「"+name+"（"+code+"）」の最近の株価動向と主な上昇・下落要因を日本語のみで簡潔に説明してください。"+factRule+knCtx;
  else if(t==="overview")prompt="日本株「"+name+"（証券コード"+code+"）」について以下を日本語で簡潔に教えてください:\n1. 業界・セクター\n2. 主要事業と売上構成\n3. 競合企業\n4. 強み・弱み\n5. 市場でのポジション"+factRule+knCtx;
  else if(t==="plan")prompt="日本株「"+name+"（証券コード"+code+"）」の中期経営計画について以下を日本語で教えてください:\n1. 計画名称と期間\n2. 売上・利益目標の数値\n3. 重点戦略\n4. 設備投資計画\n5. 配当方針\n事実のみを記載し、見つからない場合はその旨を明記してください。"+factRule+knCtx;
  else if(t==="judge")prompt="ミネルヴィニ流成長株投資の観点から「"+name+"（"+code+"）」のエントリー判断をしてください。"+factRule+knCtx;
  else if(t==="free"&&freeText)prompt="日本株「"+name+"（"+code+"）」について: "+freeText+factRule+knCtx;
  else{aiErr("自由入力欄に質問を入力してください");return;}
  aiLoad(true);try{const res=await fetch(GEMINI_API,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model:"gemini-2.5-flash",contents:[{parts:[{text:prompt}]}],tools:[{google_search:{}}]})});const data=await res.json();if(!res.ok)throw new Error(data.error?.message||"Geminiエラー");aiShow(data.candidates?.[0]?.content?.parts?.[0]?.text||"結果を取得できませんでした",code,t,"Gemini");}catch(e){aiErr("Geminiエラー: "+e.message);}finally{aiLoad(false);}}async function runC(code,name,score,hp,rs26w){
  var t=curTab;var freeText=(document.getElementById("ai-free-input")||{}).value||"";
  var knCtx=getKnowledgeContext(code);
  var sysPrompt="あなたはミネルヴィニ流成長株投資の専門家です。回答は「事実」と「推測・見解」を明確に分けて記述してください。事実には根拠を示し、推測には「推測:」と明記してください。日本語で簡潔に答えてください。";
  var userPrompt;
  if(t==="free"&&freeText)userPrompt="銘柄: "+name+"（"+code+"）について: "+freeText+knCtx;
  else if(t==="overview")userPrompt="銘柄: "+name+"（"+code+"）の業界概要、主要事業、競合、強み・弱みを教えてください。"+knCtx;
  else if(t==="plan")userPrompt="銘柄: "+name+"（"+code+"）の中期経営計画の内容（売上・利益目標、戦略、配当方針）を教えてください。事実のみを記載してください。"+knCtx;
  else userPrompt="銘柄: "+name+"（"+code+"）\nミネルヴィニスコア: "+score+"\n52週高値比: "+hp+"\nRS26w: "+rs26w+"\n\n1. スコア評価\n2. RSの強さ\n3. 高値更新圏かどうか\n4. エントリー可否の結論\n5. リスク要因"+knCtx;
  aiLoad(true);try{const res=await fetch(CLAUDE_API,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model:"claude-sonnet-4-6",max_tokens:1000,system:sysPrompt,messages:[{role:"user",content:userPrompt}]})});const data=await res.json();if(!res.ok)throw new Error(data.error?.message||"Claudeエラー");aiShow(data.content?.[0]?.text||"結果を取得できませんでした",code,t,"Claude");}catch(e){aiErr("Claudeエラー: "+e.message);}finally{aiLoad(false);}}let volOn=false;function toggleVol(){volOn=!volOn;const b=document.getElementById("vol-btn");if(volOn){b.style.background="#3fb950";b.style.color="#0d1117";b.style.borderColor="#3fb950";}else{b.style.background="none";b.style.color="#8b949e";b.style.borderColor="#30363d";}applyFilters();}function toggleYTD(){ytdOn=!ytdOn;const b=document.getElementById("ytd-btn");if(ytdOn){b.style.background="#f0b429";b.style.color="#0d1117";b.style.borderColor="#f0b429";}else{b.style.background="none";b.style.color="#8b949e";b.style.borderColor="#30363d";}applyFilters();}function saveAIHistory(code, tab, model, text){
  const key = "ai_hist_" + code;
  let hist = [];
  try { hist = JSON.parse(localStorage.getItem(key) || "[]"); } catch(e){}
  hist.unshift({date: new Date().toLocaleDateString("ja-JP"), tab, model, text});
  if(hist.length > 5) hist = hist.slice(0, 5);
  localStorage.setItem(key, JSON.stringify(hist));
}
function loadAIHistory(code){
  const key = "ai_hist_" + code;
  try { return JSON.parse(localStorage.getItem(key) || "[]"); } catch(e){ return []; }
}
function renderAIHistory(code){
  const hist = loadAIHistory(code);
  const el = document.getElementById("ai-history-list");
  if(!el) return;
  if(!hist.length){ el.innerHTML = ""; return; }
  const tabNames = {news:"ニュース", trend:"動向分析", judge:"買い時判定"};
  el.innerHTML = hist.map((h,i) => 
    "<div class='ai-history-item' onclick='toggleHistory(" + i + ")'>" +
    "<div class='ai-history-meta'><span>" + (tabNames[h.tab]||h.tab) + " / " + h.model + "</span><span>" + h.date + "</span></div>" +
    "<div class='ai-history-preview' id='hist-preview-" + i + "'>" + h.text.slice(0,60) + "...</div>" +
    "<div class='ai-history-full' id='hist-full-" + i + "'>" + h.text + "</div>" +
    "</div>"
  ).join("");
}
function toggleHistory(i){
  const p = document.getElementById("hist-preview-" + i);
  const f = document.getElementById("hist-full-" + i);
  if(!p||!f) return;
  if(f.style.display === "block"){f.style.display="none";p.style.display="block";}
  else{f.style.display="block";p.style.display="none";}
}
function evalCustomFilter(s, expr){
  if(!expr.trim()) return true;
  try{
    const score=parseInt(s.score);
    const price=s.price||0;
    const high_pct=s.high52?(s.price/s.high52):0;
    const rs6w=s.rs6w||0;
    const rs13w=s.rs13w||0;
    const rs26w=s.rs26w||0;
    const volume=s.volume||0;
    const vol_ratio=s.vol_ratio||0;
    const change_pct=s.change_pct||0;
    return eval(expr);
  }catch(e){return true;}
}
function savePreset(){
  const expr=document.getElementById("custom-input")?.value?.trim();
  if(!expr) return;
  let presets=[];
  try{presets=JSON.parse(localStorage.getItem("cf_presets")||"[]");}catch(e){}
  if(!presets.includes(expr)){
    presets.unshift(expr);
    if(presets.length>5) presets=presets.slice(0,5);
    localStorage.setItem("cf_presets",JSON.stringify(presets));
  }
  renderPresets();
}
function renderPresets(){
  const el=document.getElementById("preset-row");
  if(!el) return;
  let presets=[];
  try{presets=JSON.parse(localStorage.getItem("cf_presets")||"[]");}catch(e){}
  el.innerHTML=presets.map(p=>
    "<button class='preset-btn' onclick='applyPreset("+JSON.stringify(p)+")'>"+p+"</button>"
  ).join("");
}
function applyPreset(p){
  const el=document.getElementById("custom-input");
  if(el){el.value=p;applyFilters();}
}
let chatHistory=[];
function togglePat(){patOn=!patOn;var b=document.getElementById("pat-btn");if(patOn){b.style.background="#58a6ff";b.style.color="#0d1117";b.style.borderColor="#58a6ff";}else{b.style.background="none";b.style.color="#8b949e";b.style.borderColor="#30363d";}applyFilters();}

// Memo functions (localStorage)
