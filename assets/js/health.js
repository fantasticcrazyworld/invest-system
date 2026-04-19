function saveHealthSnapshot(){
  if(!allData.length)return;
  var today=new Date().toISOString().slice(0,10);
  var hist=[];try{hist=JSON.parse(localStorage.getItem('health_history')||'[]');}catch(e){}
  if(hist.length&&hist[hist.length-1].date===today)return; // already saved today
  var pass=allData.filter(function(x){return x.passed;}).length;
  var perfect=allData.filter(function(x){return x.score==='7/7';}).length;
  var nearHigh=allData.filter(function(x){return x.passed&&x.high52&&x.price>=x.high52*0.95;}).length;
  hist.push({date:today,pass:pass,perfect:perfect,near_high:nearHigh});
  if(hist.length>365)hist=hist.slice(-365);
  localStorage.setItem('health_history',JSON.stringify(hist));
}
var healthChart=null;
function renderHealthChart(){
  var hist=[];try{hist=JSON.parse(localStorage.getItem('health_history')||'[]');}catch(e){}
  var el=document.getElementById('health-date');
  if(el)el.textContent=hist.length+'日分のデータ';
  // Update metrics from latest
  if(hist.length){
    var latest=hist[hist.length-1];
    document.getElementById('hm-pass').textContent=latest.pass;
    document.getElementById('hm-perfect').textContent=latest.perfect;
    document.getElementById('hm-nearhigh').textContent=latest.near_high;
  }
  var container=document.getElementById('health-chart');
  if(!container||hist.length<1)return;
  container.innerHTML='';
  healthChart=LightweightCharts.createChart(container,{
    width:container.clientWidth,height:300,
    layout:{background:{type:'solid',color:'#0d1117'},textColor:'#8b949e'},
    grid:{vertLines:{color:'#161b22'},horzLines:{color:'#161b22'}},
    rightPriceScale:{borderColor:'#30363d'},
    timeScale:{borderColor:'#30363d',timeVisible:false},
  });
  var passSeries=healthChart.addLineSeries({color:'#f0b429',lineWidth:2,title:'PASS数'});
  passSeries.setData(hist.map(function(h){return{time:h.date,value:h.pass};}));
  var perfectSeries=healthChart.addLineSeries({color:'#3fb950',lineWidth:1,title:'満点'});
  perfectSeries.setData(hist.map(function(h){return{time:h.date,value:h.perfect};}));
  healthChart.timeScale().fitContent();
  window.addEventListener('resize',function(){if(healthChart)healthChart.applyOptions({width:container.clientWidth});});
}

// === Feature: Equity Curve ===
function renderSectorDist(){
  var el=document.getElementById('sector-dist');
  if(!el)return;
  var codes={};
  var wl=[];try{wl=JSON.parse(localStorage.getItem('wl_local')||'[]');}catch(e){}
  wl.forEach(function(w){codes[w.code]='監視';});
  var pf=getLocalPF();Object.keys(pf).forEach(function(k){if(k!=='__meta__')codes[k]='保有';});
  var svPF=window._portfolio||{};Object.keys(svPF).forEach(function(k){if(k!=='__meta__')codes[k]='保有';});
  if(!Object.keys(codes).length){el.innerHTML='<div style="color:#8b949e;font-size:12px;padding:8px 0">監視/保有銘柄がありません</div>';return;}
  var sectors={};
  Object.keys(codes).forEach(function(c){
    var sec=codeSector(c);
    if(!sectors[sec])sectors[sec]=0;
    sectors[sec]++;
  });
  var sorted=Object.entries(sectors).sort(function(a,b){return b[1]-a[1];});
  var max=sorted[0][1];
  var h='';
  sorted.forEach(function(s){
    var pct=(s[1]/max*100).toFixed(0);
    h+='<div class="sector-row"><span class="sector-label">'+s[0]+'</span><div class="sector-bar" style="width:'+pct+'%"></div><span class="sector-count">'+s[1]+'</span></div>';
  });
  el.innerHTML=h;
}

// === Feature: Index Charts ===
var indexChart=null,curIdx='nikkei225',curIdxTF='daily';
function switchIndex(name,btn){
  curIdx=name;
  document.querySelectorAll('.idx-tab').forEach(function(b){b.classList.remove('active');b.style.background='';b.style.color='';b.style.borderColor='';});
  if(btn){btn.classList.add('active');btn.style.background='#f0b429';btn.style.color='#0d1117';btn.style.borderColor='#f0b429';}
  renderIndexChart();
}
function switchIdxTF(tf,btn){
  curIdxTF=tf;
  document.querySelectorAll('.idx-tf').forEach(function(b){b.style.background='';b.style.color='';b.style.borderColor='';b.style.fontWeight='';});
  if(btn){btn.style.background='#f0b429';btn.style.color='#0d1117';btn.style.borderColor='#f0b429';btn.style.fontWeight='600';}
  renderIndexChart();
}
function renderIndexChart(){
  var data=(window._indexData||{})[curIdx];
  if(data&&data.length){
    if(curIdxTF==='weekly')data=resampleWeekly(data);
    else if(curIdxTF==='monthly')data=resampleMonthly(data);
  }
  var container=document.getElementById('index-chart');
  if(!container)return;
  if(!data||!data.length){container.innerHTML='<div style="padding:40px;text-align:center;color:#8b949e;font-size:12px">指数データなし（GitHub Actions実行後に表示されます）</div>';return;}
  container.innerHTML='';
  indexChart=LightweightCharts.createChart(container,{
    width:container.clientWidth,height:300,
    layout:{background:{type:'solid',color:'#0d1117'},textColor:'#8b949e'},
    grid:{vertLines:{color:'#161b22'},horzLines:{color:'#161b22'}},
    rightPriceScale:{borderColor:'#30363d'},
    timeScale:{borderColor:'#30363d',timeVisible:false},
  });
  var cs=indexChart.addCandlestickSeries({upColor:'#26a69a',downColor:'#ef5350',borderUpColor:'#26a69a',borderDownColor:'#ef5350',wickUpColor:'#26a69a',wickDownColor:'#ef5350'});
  cs.setData(data.map(function(d){return{time:d.time,open:d.open,high:d.high,low:d.low,close:d.close};}));
  indexChart.timeScale().fitContent();
  window.addEventListener('resize',function(){if(indexChart)indexChart.applyOptions({width:container.clientWidth});});
  // Performance display (always use daily data)
  renderIdxPerf((window._indexData||{})[curIdx]);
}
function renderIdxPerf(data){
  var el=document.getElementById('idx-perf');if(!el||!data.length)return;
  var last=data[data.length-1].close;
  function pct(daysAgo){var idx=Math.max(0,data.length-1-daysAgo);var old=data[idx].close;return old?((last-old)/old*100):0;}
  function fmtPct(v){var cls=v>=0?'color:#3fb950':'color:#f85149';return '<span style="'+cls+';font-weight:600">'+(v>=0?'+':'')+v.toFixed(1)+'%</span>';}
  var names={nikkei225:'日経225',sp500:'S&P 500',dow:'ダウ平均',nasdaq:'NASDAQ'};
  el.innerHTML='<span style="font-size:13px;font-weight:600;color:#f0b429">'+(names[curIdx]||curIdx)+'</span> '+
    '<span style="color:#e6edf3;font-size:13px;font-weight:600">'+Number(last.toFixed(0)).toLocaleString()+'</span> '+
    '1日: '+fmtPct(pct(1))+' | 1週: '+fmtPct(pct(5))+' | 1月: '+fmtPct(pct(22))+' | 3月: '+fmtPct(pct(66));
}

// === Feature: Trend Analysis ===
function calcTrend(closes){
  if(!closes||closes.length<200)return{trend:'unknown',label:'データ不足',cls:'trend-flat'};
  var n=closes.length;var price=closes[n-1];
  var sma50=0,sma150=0,sma200=0;
  for(var i=n-50;i<n;i++)sma50+=closes[i];sma50/=50;
  for(var i=n-150;i<n;i++)sma150+=closes[i];sma150/=150;
  for(var i=n-200;i<n;i++)sma200+=closes[i];sma200/=200;
  // SMA200 direction (compare current vs 1 month ago)
  var sma200prev=0;for(var i=n-200-22;i<n-22;i++){if(i>=0)sma200prev+=closes[i];}sma200prev/=200;
  var sma200up=sma200>sma200prev;
  if(price>sma50&&sma50>sma150&&sma150>sma200&&sma200up)return{trend:'up',label:'上昇トレンド',cls:'trend-up'};
  if(price<sma50&&sma50<sma150)return{trend:'down',label:'下降トレンド',cls:'trend-down'};
  return{trend:'flat',label:'横ばい',cls:'trend-flat'};
}
function renderMarketTrend(){
  var el=document.getElementById('market-trend-banner');if(!el)return;
  var names={nikkei225:'日経225',sp500:'S&P 500',dow:'ダウ',nasdaq:'NASDAQ'};
  var h='<div class="trend-banner">';
  ['nikkei225','sp500','dow','nasdaq'].forEach(function(key){
    var data=(window._indexData||{})[key];
    if(!data||!data.length){h+='<div class="trend-item">'+names[key]+': <span class="trend-badge trend-flat">-</span></div>';return;}
    var closes=data.map(function(d){return d.close;});
    var t=calcTrend(closes);
    h+='<div class="trend-item">'+names[key]+': <span class="trend-badge '+t.cls+'">'+t.label+'</span></div>';
  });
  h+='</div>';
  el.innerHTML=h;
}
// Trend badge for individual stock on chart page
function onIdxCompareChange(){
  var sel=document.getElementById('idx-compare-select');
  idxCompareKey=sel?sel.value:'';
  if(idxCompareKey)showIdxCompare();
  else hideIdxCompare();
}
function showIdxCompare(){
  if(!lwChart||!candleSeries)return;
  var nk=(window._indexData||{})[idxCompareKey];
  var code=(document.getElementById('chart-code-input')||{}).value||'';
  var cd=window._chartData||{};var stockData=cd[code];
  if(!nk||!nk.length||!stockData||!stockData.length){return;}
  // Resample index to match current stock timeframe
  var nkResampled=nk;
  if(curTF==='weekly')nkResampled=resampleWeekly(nk);
  else if(curTF==='monthly')nkResampled=resampleMonthly(nk);
  // Also resample stock data to match
  var stockResampled=stockData;
  if(curTF==='weekly')stockResampled=resampleWeekly(stockData);
  else if(curTF==='monthly')stockResampled=resampleMonthly(stockData);
  // Find overlapping date range
  var stockMap={};stockResampled.forEach(function(d){stockMap[d.time]=d.close;});
  var nkMap={};nkResampled.forEach(function(d){nkMap[d.time]=d.close;});
  var dates=Object.keys(stockMap).filter(function(d){return nkMap[d];}).sort();
  if(dates.length<2)return;
  // Normalize: scale index to stock's price range for overlay
  var stockFirst=stockMap[dates[0]],nkFirst=nkMap[dates[0]];
  var nkScaled=dates.map(function(d){return{time:d,value:stockFirst*(nkMap[d]/nkFirst)};});
  // Add line on same price scale (no extra axis)
  try{if(idxCompareSeries)lwChart.removeSeries(idxCompareSeries);}catch(e){}
  idxCompareSeries=null;
  var idxNames={nikkei225:'日経225',sp500:'S&P500',dow:'ダウ',nasdaq:'NASDAQ'};
  idxCompareSeries=lwChart.addLineSeries({color:'#ff6b6b',lineWidth:2,lineStyle:2,priceLineVisible:false,lastValueVisible:false,title:idxNames[idxCompareKey]||''});
  idxCompareSeries.setData(nkScaled);
}
function hideIdxCompare(){
  try{if(lwChart&&idxCompareSeries)lwChart.removeSeries(idxCompareSeries);}catch(e){}
  idxCompareSeries=null;
}
