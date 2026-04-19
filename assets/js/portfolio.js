function renderPortfolio(){
  var pf=window._portfolio||{};
  var codes=Object.keys(pf).filter(function(k){return k!=="__meta__";});
  document.getElementById("pf-count").textContent=codes.length+"件";
  if(!codes.length){document.getElementById("pf-content").innerHTML='<div class="loading"><div class="loading-text">保有銘柄なし</div></div>';return;}
  var h='<div class="table-wrap"><table><thead><tr><th>コード</th><th>銘柄名</th><th class="r">保有株数</th><th class="r">取得単価</th><th class="r">現在値</th><th class="r">損益</th><th>パターン</th></tr></thead><tbody>';
  codes.forEach(function(code){
    var p=pf[code]||{};
    var s=allData.find(function(x){return x.code===code;})||{};
    var curPrice=s.price||0;
    var cost=p.cost||0;
    var shares=p.shares||0;
    var pl=shares*(curPrice-cost);
    var plPct=cost>0?((curPrice-cost)/cost*100):0;
    var plClass=pl>=0?"rs-pos":"rs-neg";
    var pat=window._patternData||{};var sp=pat[code];
    var pb=sp&&sp.patterns&&sp.patterns.length?sp.patterns.map(function(pp){var cls=pp==="cup_with_handle"?"pattern-cup":pp==="vcp"?"pattern-vcp":"pattern-flat";var lbl=pp==="cup_with_handle"?"CwH":pp==="vcp"?"VCP":"Flat";return'<span class="pattern-badge '+cls+'">'+lbl+'</span>';}).join(""):'<span class="pattern-none">-</span>';
    h+='<tr onclick="openChart(\''+code+'\')"><td class="code">'+code+'</td><td class="name">'+(p.name||s.name||"-")+'</td><td class="r">'+shares+'</td><td class="r price-val">'+Number(cost).toLocaleString()+'</td><td class="r price-val">'+Number(curPrice).toLocaleString()+'</td><td class="r"><span class="'+plClass+'">'+(pl>=0?"+":"")+Number(Math.round(pl)).toLocaleString()+' ('+plPct.toFixed(1)+'%)</span></td><td>'+pb+'</td></tr>';
  });
  document.getElementById("pf-content").innerHTML=h+"</tbody></table></div>";
}

// Financial data
const FINS_DATA_URL=DATA_BASE+"fins_data.json";
const TIMELINE_URL=DATA_BASE+"timeline_data.json";
const KNOWLEDGE_URL=DATA_BASE+"knowledge_data.json";
const INDEX_DATA_URL=DATA_BASE+"index_data.json";
window._finsData={};window._timeline={};window._knowledge={};window._indexData={};
function addToPortfolio(){
  var code=document.getElementById('pf-add-code').value.trim();
  var shares=parseFloat(document.getElementById('pf-add-shares').value)||0;
  var cost=parseFloat(document.getElementById('pf-add-cost').value)||0;
  var target=parseFloat(document.getElementById('pf-add-target').value)||0;
  var stop=parseFloat(document.getElementById('pf-add-stop').value)||0;
  if(!code||!shares||!cost){alert('コード・株数・取得単価は必須です');return;}
  if(!target||!stop){alert('利確目標価格と損切り価格は必須です。\n売買ルールを明確にしてからエントリーしてください。');return;}
  if(target<=cost){alert('利確目標は取得単価より高く設定してください');return;}
  if(stop>=cost){alert('損切り価格は取得単価より低く設定してください');return;}
  var s=allData.find(function(x){return x.code===code;});
  var expectedProfit=(target-cost)*shares;
  var expectedLoss=(stop-cost)*shares;
  var riskReward=Math.abs(expectedProfit/expectedLoss);
  if(!confirm('確認:\n銘柄: '+(s?s.name:code)+' ('+code+')\n株数: '+shares+'\n取得単価: '+Number(cost).toLocaleString()+'円\n利確目標: '+Number(target).toLocaleString()+'円 (+'+Number(Math.round(expectedProfit)).toLocaleString()+'円)\n損切り: '+Number(stop).toLocaleString()+'円 ('+Number(Math.round(expectedLoss)).toLocaleString()+'円)\nリスクリワード比: '+riskReward.toFixed(2)+'\n\n追加しますか？'))return;
  var pf=getLocalPF();
  pf[code]={code:code,name:s?s.name:'',shares:shares,cost:cost,target_price:target,stop_price:stop,added_at:new Date().toISOString()};
  saveLocalPF(pf);
  ['pf-add-code','pf-add-shares','pf-add-cost','pf-add-target','pf-add-stop'].forEach(function(id){document.getElementById(id).value='';});
  renderPortfolio();
}
function sellStock(code){
  var pf=getLocalPF();
  var p=pf[code];if(!p)return;
  var sellPrice=prompt('売却価格を入力してください:');
  if(!sellPrice)return;
  sellPrice=parseFloat(sellPrice);
  if(isNaN(sellPrice)||sellPrice<=0){alert('有効な価格を入力してください');return;}
  var pl=(sellPrice-p.cost)*p.shares;
  var plPct=((sellPrice-p.cost)/p.cost*100);
  var hitTarget=sellPrice>=p.target_price;
  var hitStop=sellPrice<=p.stop_price;
  // Save to history
  var hist=[];
  try{hist=JSON.parse(localStorage.getItem('pf_history')||'[]');}catch(e){}
  hist.unshift({
    code:code,name:p.name,shares:p.shares,cost:p.cost,
    target_price:p.target_price,stop_price:p.stop_price,
    sell_price:sellPrice,sell_date:new Date().toISOString().slice(0,10),
    buy_date:p.added_at?p.added_at.slice(0,10):'',
    pl:Math.round(pl),pl_pct:plPct.toFixed(1),
    hit_target:hitTarget,hit_stop:hitStop
  });
  localStorage.setItem('pf_history',JSON.stringify(hist));
  // Remove from portfolio
  delete pf[code];
  saveLocalPF(pf);
  alert('売却完了: '+(pl>=0?'+':'')+Number(Math.round(pl)).toLocaleString()+'円 ('+plPct.toFixed(1)+'%)');
  renderPortfolio();
}
function removeFromPortfolio(code){
  var pf=getLocalPF();
  delete pf[code];
  saveLocalPF(pf);
  var sp=window._portfolio||{};
  delete sp[code];
  renderPortfolio();
}

// Override renderWatchlist to merge local + server data and add delete buttons
var _origRenderWL=renderWatchlist;
renderWatchlist=function(){
  var wl=Object.assign({},window._watchlist||{},getLocalWL());
  var codes=Object.keys(wl).filter(function(k){return k!=='__meta__';});
  document.getElementById('wl-count').textContent=codes.length+'件';
  if(!codes.length){document.getElementById('wl-content').innerHTML='<div class="loading"><div class="loading-text">監視銘柄なし</div></div>';return;}
  var h='<div class="table-wrap"><table><thead><tr><th>コード</th><th>銘柄名</th><th>登録日</th><th>メモ</th><th>スコア</th><th>パターン</th><th class="r">株価</th><th></th></tr></thead><tbody>';
  codes.forEach(function(code){
    var w=wl[code]||{};var s=allData.find(function(x){return x.code===code;})||{};
    var pat=window._patternData||{};var sp=pat[code];
    var pb=sp&&sp.patterns&&sp.patterns.length?sp.patterns.map(function(p){var cls=p==='cup_with_handle'?'pattern-cup':p==='vcp'?'pattern-vcp':'pattern-flat';var lbl=p==='cup_with_handle'?'CwH':p==='vcp'?'VCP':'Flat';return'<span class="pattern-badge '+cls+'">'+lbl+'</span>';}).join(''):'<span class="pattern-none">-</span>';
    var memo=w.memo||getMemo(code)||'';
    var addedAt=w.added_at?(w.added_at.slice(0,10)):'-';
    h+='<tr><td class="code" style="cursor:pointer" onclick="openChart(\''+code+'\')">'+code+'</td><td class="name">'+(w.name||s.name||'-')+'</td><td style="font-size:11px;color:#8b949e">'+addedAt+'</td><td class="wl-memo">'+memo+'</td><td>'+(s.score||'-')+'</td><td>'+pb+'</td><td class="r price-val">'+(s.price?Number(s.price).toLocaleString():'-')+'</td><td><button onclick="removeFromWatchlist(\''+code+'\')" style="background:none;border:1px solid #f85149;color:#f85149;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px">削除</button></td></tr>';
  });
  document.getElementById('wl-content').innerHTML=h+'</tbody></table></div>';
};

// Override renderPortfolio to merge local + server data and add delete buttons
var _origRenderPF=renderPortfolio;
renderPortfolio=function(){
  var pf=Object.assign({},window._portfolio||{},getLocalPF());
  var codes=Object.keys(pf).filter(function(k){return k!=='__meta__';});
  document.getElementById('pf-count').textContent=codes.length+'件';
  if(!codes.length){document.getElementById('pf-content').innerHTML='<div class="loading"><div class="loading-text">保有銘柄なし</div></div>';document.getElementById('pf-alert-area').innerHTML='';renderEquityCurve();return;}
  // Stop loss alert scan
  var alertCodes=[],warnCodes=[];
  codes.forEach(function(code){
    var p=pf[code]||{};var s=allData.find(function(x){return x.code===code;})||{};
    var curPrice=s.price||0;var stop=p.stop_price||0;
    if(curPrice>0&&stop>0){
      if(curPrice<=stop)alertCodes.push(code);
      else if(curPrice<=stop*1.03)warnCodes.push(code);
    }
  });
  var alertHtml='';
  if(alertCodes.length)alertHtml+='<div class="stop-alert-banner">&#9888; 損切りライン到達: '+alertCodes.join(', ')+'</div>';
  if(warnCodes.length)alertHtml+='<div class="stop-warn-banner">&#9888; 損切り3%以内: '+warnCodes.join(', ')+'</div>';
  document.getElementById('pf-alert-area').innerHTML=alertHtml;
  var h='<div class="table-wrap"><table><thead><tr><th>コード</th><th>銘柄名</th><th>購入日</th><th class="r">株数</th><th class="r">取得単価</th><th class="r">現在値</th><th class="r">含み損益</th><th class="r">利確目標</th><th class="r">損切り</th><th></th></tr></thead><tbody>';
  codes.forEach(function(code){
    var p=pf[code]||{};var s=allData.find(function(x){return x.code===code;})||{};
    var curPrice=s.price||0;var cost=p.cost||0;var shares=p.shares||0;
    var target=p.target_price||0;var stop=p.stop_price||0;
    var pl=shares*(curPrice-cost);var plPct=cost>0?((curPrice-cost)/cost*100):0;
    var plClass=pl>=0?'rs-pos':'rs-neg';
    var addedAt=p.added_at?(p.added_at.slice(0,10)):'-';
    // Stop loss alert class
    var stopAlert=curPrice>0&&stop>0&&curPrice<=stop;
    var stopWarn=!stopAlert&&curPrice>0&&stop>0&&curPrice<=stop*1.03;
    var rowClass=stopAlert?'pf-row-danger':stopWarn?'pf-row-warning':'';
    // Distance to target/stop
    var tgtDist=curPrice>0&&target?((target-curPrice)/curPrice*100).toFixed(1):'-';
    var stpDist=curPrice>0&&stop?((stop-curPrice)/curPrice*100).toFixed(1):'-';
    // Progress bar: where is current price between stop and target?
    var progress=target>stop?Math.min(100,Math.max(0,(curPrice-stop)/(target-stop)*100)):50;
    var barColor=progress>66?'#3fb950':progress>33?'#f0b429':'#f85149';
    h+='<tr class="'+rowClass+'"><td class="code" style="cursor:pointer" onclick="openChart(\''+code+'\')">'+code+'</td><td class="name">'+(p.name||s.name||'-')+(stopAlert?' <span style="color:#f85149">&#9888;</span>':'')+'</td><td style="font-size:11px;color:#8b949e">'+addedAt+'</td><td class="r">'+shares+'</td><td class="r price-val">'+Number(cost).toLocaleString()+'</td><td class="r price-val">'+Number(curPrice).toLocaleString()+'</td><td class="r"><span class="'+plClass+'">'+(pl>=0?'+':'')+Number(Math.round(pl)).toLocaleString()+'<br><span style="font-size:10px">('+plPct.toFixed(1)+'%)</span></span></td><td class="r"><span style="color:#3fb950;font-size:11px">'+Number(target).toLocaleString()+'<br>(+'+tgtDist+'%)</span></td><td class="r"><span style="color:#f85149;font-size:11px">'+Number(stop).toLocaleString()+'<br>('+stpDist+'%)</span></td><td style="white-space:nowrap"><div style="width:60px;height:4px;background:#30363d;border-radius:2px;margin-bottom:4px"><div style="width:'+progress+'%;height:100%;background:'+barColor+';border-radius:2px"></div></div><button onclick="sellStock(\''+code+'\')" style="background:none;border:1px solid #58a6ff;color:#58a6ff;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px;margin-right:2px">売却</button><button onclick="removeFromPortfolio(\''+code+'\')" style="background:none;border:1px solid #f85149;color:#f85149;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:10px">削除</button></td></tr>';
  });
  // Sell history
  var hist=[];try{hist=JSON.parse(localStorage.getItem('pf_history')||'[]');}catch(e){}
  if(hist.length){
    h+='</tbody></table></div><div style="padding:12px 0"><div class="fins-section-title">売却履歴</div>';
    h+='<div class="table-wrap"><table class="fins-table"><thead><tr><th>銘柄</th><th>購入日</th><th>売却日</th><th class="r">取得</th><th class="r">目標</th><th class="r">損切</th><th class="r">売却</th><th class="r">損益</th><th>結果</th></tr></thead><tbody>';
    hist.forEach(function(hh){
      var cls=hh.pl>=0?'pos':'neg';
      var result=hh.hit_target?'利確到達':hh.hit_stop?'損切り到達':'途中売却';
      h+='<tr><td>'+hh.code+' '+(hh.name||'')+'</td><td style="font-size:10px">'+hh.buy_date+'</td><td style="font-size:10px">'+hh.sell_date+'</td><td class="r">'+Number(hh.cost).toLocaleString()+'</td><td class="r" style="color:#3fb950">'+Number(hh.target_price||0).toLocaleString()+'</td><td class="r" style="color:#f85149">'+Number(hh.stop_price||0).toLocaleString()+'</td><td class="r">'+Number(hh.sell_price).toLocaleString()+'</td><td class="r '+cls+'">'+(hh.pl>=0?'+':'')+Number(hh.pl).toLocaleString()+'円<br>('+hh.pl_pct+'%)</td><td style="font-size:10px">'+result+'</td></tr>';
    });
    h+='</tbody></table></div></div>';
  }
  document.getElementById('pf-content').innerHTML=h+'</tbody></table></div>';

  // Calculate total portfolio value
  var cash=loadCash();
  var stockValue=0;
  codes.forEach(function(code){
    var p=pf[code]||{};var s=allData.find(function(x){return x.code===code;})||{};
    stockValue+=(p.shares||0)*(s.price||0);
  });
  var total=cash+stockValue;
  var totalEl=document.getElementById('pf-total');
  if(totalEl)totalEl.innerHTML='株式評価額: <b>'+Number(Math.round(stockValue)).toLocaleString()+'</b> / 合計: <b style="color:#f0b429">'+Number(Math.round(total)).toLocaleString()+'円</b>';
  saveEquitySnapshot(total,cash,stockValue);
  renderEquityCurve();
};

// Simulation
var simCode='';
var simBaseData={};
function saveCash(){
  var cash=parseFloat(document.getElementById('pf-cash').value)||0;
  localStorage.setItem('pf_cash',cash);
  renderPortfolio();
}
function loadCash(){
  var cash=parseFloat(localStorage.getItem('pf_cash'))||0;
  var el=document.getElementById('pf-cash');
  if(el)el.value=cash||'';
  return cash;
}
function saveEquitySnapshot(total,cash,stocks){
  if(!total||total<=0)return;
  var today=new Date().toISOString().slice(0,10);
  var hist=[];try{hist=JSON.parse(localStorage.getItem('equity_history')||'[]');}catch(e){}
  if(hist.length&&hist[hist.length-1].date===today){hist[hist.length-1]={date:today,value:Math.round(total),cash:Math.round(cash),stocks:Math.round(stocks)};}
  else{hist.push({date:today,value:Math.round(total),cash:Math.round(cash),stocks:Math.round(stocks)});}
  if(hist.length>1095)hist=hist.slice(-1095);
  localStorage.setItem('equity_history',JSON.stringify(hist));
}
var equityChart=null;
function renderEquityCurve(){
  var hist=[];try{hist=JSON.parse(localStorage.getItem('equity_history')||'[]');}catch(e){}
  var container=document.getElementById('equity-chart');
  if(!container)return;
  if(hist.length<1){container.innerHTML='<div style="padding:20px;text-align:center;color:#8b949e;font-size:12px">資産データは日々の訪問で蓄積されます</div>';return;}
  container.innerHTML='';
  equityChart=LightweightCharts.createChart(container,{
    width:container.clientWidth,height:220,
    layout:{background:{type:'solid',color:'#0d1117'},textColor:'#8b949e'},
    grid:{vertLines:{color:'#161b22'},horzLines:{color:'#161b22'}},
    rightPriceScale:{borderColor:'#30363d'},
    timeScale:{borderColor:'#30363d',timeVisible:false},
  });
  var line=equityChart.addLineSeries({color:'#58a6ff',lineWidth:2,title:'総資産'});
  line.setData(hist.map(function(h){return{time:h.date,value:h.value};}));
  // Target line at 1億円
  line.createPriceLine({price:100000000,color:'#f0b429',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'目標: 1億円'});
  equityChart.timeScale().fitContent();
  window.addEventListener('resize',function(){if(equityChart)equityChart.applyOptions({width:container.clientWidth});});
}

// === Feature: Sector Distribution ===
