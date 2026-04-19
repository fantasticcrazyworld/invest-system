function renderWatchlist(){
  var wl=window._watchlist||{};
  var codes=Object.keys(wl).filter(function(k){return k!=="__meta__";});
  document.getElementById("wl-count").textContent=codes.length+"件";
  if(!codes.length){document.getElementById("wl-content").innerHTML='<div class="loading"><div class="loading-text">監視銘柄なし</div></div>';return;}
  var h='<div class="table-wrap"><table><thead><tr><th>コード</th><th>銘柄名</th><th>メモ</th><th>スコア</th><th>パターン</th><th class="r">株価</th></tr></thead><tbody>';
  codes.forEach(function(code){
    var w=wl[code]||{};
    var s=allData.find(function(x){return x.code===code;})||{};
    var pat=window._patternData||{};var sp=pat[code];
    var pb=sp&&sp.patterns&&sp.patterns.length?sp.patterns.map(function(p){var cls=p==="cup_with_handle"?"pattern-cup":p==="vcp"?"pattern-vcp":"pattern-flat";var lbl=p==="cup_with_handle"?"CwH":p==="vcp"?"VCP":"Flat";return'<span class="pattern-badge '+cls+'">'+lbl+'</span>';}).join(""):'<span class="pattern-none">-</span>';
    var memo=w.memo||getMemo(code)||"";
    h+='<tr onclick="openChart(\''+code+'\')"><td class="code">'+code+'</td><td class="name">'+(w.name||s.name||"-")+'</td><td class="wl-memo">'+memo+'</td><td>'+(s.score||"-")+'</td><td>'+pb+'</td><td class="r price-val">'+(s.price?Number(s.price).toLocaleString():"-")+'</td></tr>';
  });
  document.getElementById("wl-content").innerHTML=h+"</tbody></table></div>";
}

// Portfolio rendering
function addToWatchlist(){
  var code=document.getElementById('wl-add-code').value.trim();
  if(!code)return;
  var memo=document.getElementById('wl-add-memo').value.trim();
  var s=allData.find(function(x){return x.code===code;});
  var wl=getLocalWL();
  wl[code]={code:code,name:s?s.name:'',memo:memo,added_at:new Date().toISOString()};
  saveLocalWL(wl);
  document.getElementById('wl-add-code').value='';
  document.getElementById('wl-add-memo').value='';
  renderWatchlist();
}
function removeFromWatchlist(code){
  var wl=getLocalWL();
  delete wl[code];
  saveLocalWL(wl);
  // Also remove from server data display
  var sw=window._watchlist||{};
  delete sw[code];
  renderWatchlist();
}
