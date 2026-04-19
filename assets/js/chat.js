function toggleChat(){
  const p=document.getElementById("chat-panel");
  if(!p) return;
  p.classList.toggle("open");
  if(p.classList.contains("open")&&chatHistory.length===0){
    addChatMsg("ai","こんにちは！投資システムについて何でも聞いてください。\n\n例: 今日のPASS銘柄数は？RS26w強い銘柄は？");
  }
}
function addChatMsg(role, text){
  const el=document.getElementById("chat-messages");
  if(!el) return;
  const div=document.createElement("div");
  div.className="chat-msg "+role;
  div.textContent=text;
  el.appendChild(div);
  el.scrollTop=el.scrollHeight;
  return div;
}
function sendSuggestion(text){
  document.getElementById("chat-suggestions").style.display="none";
  const inp=document.getElementById("chat-input");
  if(inp) inp.value=text;
  sendChat();
}
async function sendChat(){
  const inp=document.getElementById("chat-input");
  const text=inp?.value?.trim();
  if(!text) return;

  inp.value="";
  addChatMsg("user",text);
  chatHistory.push({role:"user",content:text});
  const sendBtn=document.getElementById("chat-send");
  if(sendBtn) sendBtn.disabled=true;
  const loadDiv=addChatMsg("ai","分析中...");
  loadDiv.classList.add("loading");
  const passCount=allData.filter(x=>x.passed).length;
  const top5=allData.filter(x=>x.passed).sort((a,b)=>parseInt(b.score)-parseInt(a.score)).slice(0,5).map(x=>x.code+"("+x.name+","+x.score+",RS26w:"+( x.rs26w?.toFixed(2)||"N/A")+")").join(", ");
  const systemPrompt="あなたはミネルヴィニ流成長株投資の専門AIアシスタントです。\n現在のスクリーニングデータ:\n- 対象銘柄数: "+allData.length+"\n- PASS銘柄数(6/7以上): "+passCount+"\n- 上位5銘柄: "+top5+"\n\nユーザーの質問に日本語で簡潔に答えてください。";
  try{
    const res=await fetch(CLAUDE_API,{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({model:"claude-sonnet-4-6",max_tokens:600,system:systemPrompt,messages:chatHistory})
    });
    const data=await res.json();
    if(!res.ok) throw new Error(data.error?.message||"APIエラー");
    const reply=data.content?.[0]?.text||"回答を取得できませんでした";
    loadDiv.remove();
    addChatMsg("ai",reply);
    chatHistory.push({role:"assistant",content:reply});
    if(chatHistory.length>20) chatHistory=chatHistory.slice(-20);
  }catch(e){
    loadDiv.remove();
    addChatMsg("ai","エラー: "+e.message);
  }finally{
    if(sendBtn) sendBtn.disabled=false;
  }
}
